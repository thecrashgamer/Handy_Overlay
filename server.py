# server.py - Phonebox-Server: Spotify, Lautstaerke und Claude-Status
import asyncio
import contextlib
import json
import os
import signal
import time
import traceback
from pathlib import Path

import psutil
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketDisconnected
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

import admin
import auth
import claude_eingabe
import claude_einrichten
import claude_ereignisse
import geraete
import medien as medien_modul
import protokoll
import seitencheck
import shortcuts
import zertifikate
from konten import Konten, rechte
from protokoll import log

ORDNER = Path(__file__).parent
TEST = os.environ.get("PHONEBOX_TEST") == "1"  # Fake-Daten statt Windows/Spotify
VERSION = "v29 (Claude-Antwort)"
FRIST_MS = int(float(os.environ.get("PHONEBOX_FRIST_S", "10")) * 1000)  # Zeit zum Bestaetigen
PORT = int(os.environ.get("PHONEBOX_PORT", "8000"))
# HTTPS: im WLAN nur verschluesselt (Port 8443); http gibt es dann nur noch am PC selbst (localhost)
HTTPS_AN = os.environ.get("PHONEBOX_HTTPS", "0" if TEST else "1") == "1"
HTTPS_PORT = int(os.environ.get("PHONEBOX_HTTPS_PORT", "8443"))
ZUSATZ_NAMEN = [n for n in os.environ.get("PHONEBOX_ZUSATZ_NAMEN", "").split(",") if n.strip()]  # z. B. Tailscale-Name

SEITE_ERWARTET = VERSION.split(" ")[0]  # so muss SEITE in index.html heissen
DATEN = Path(os.environ.get("PHONEBOX_DATEN", ORDNER / "daten"))  # hier liegen die Benutzerkonten
konten = Konten(DATEN / "phonebox.db")
auth.einrichten(konten, ORDNER)
medien = medien_modul.erstellen(TEST)
gpu_holen, akkus_holen = geraete.erstellen(TEST, leer=os.environ.get("PHONEBOX_TEST_OHNE_GERAETE") == "1")
clients = set()
ws_ip = {}  # WebSocket -> Adresse des Geraets, fuers Aktivitaetsprotokoll
ws_token = {}  # WebSocket -> Sitzungs-Schluessel, damit gesperrte oder abgemeldete Geraete getrennt werden
seiten = {}  # WebSocket -> Version der Seite (aus ?seite=...), "" bei alten Seiten
SHORTCUT_VORLAGE = ORDNER / "shortcuts.json"  # mitgelieferte Standardliste (im Git)
SHORTCUT_DATEI = DATEN / "shortcuts.json"  # eigene Liste aus dem Admin-Bereich (bleibt bei Updates erhalten)
admin.einrichten(SHORTCUT_DATEI, SHORTCUT_VORLAGE, ORDNER)
zustand = {
    "medien": {},
    "claude": {"status": "", "text": "", "aktion": "", "projekt": "", "seit": 0, "dauer": 0, "verlauf": []},
    "system": {"cpu": 0, "ram": 0, "gpu": [], "akkus": []},
    "shortcut": {"nr": 0, "name": "", "ok": True},  # zuletzt ausgeloest, fuer die Rueckmeldung
}
claude_zuletzt = 0  # wann zuletzt etwas von Claude kam (ms)
CLAUDE_ABLAUF_MS = 10 * 60 * 1000  # nach 10 Minuten Stille gilt Claude als ruhig
if os.environ.get("PHONEBOX_EINGABE_VERFALL_S"):  # nur fuer Tests: kuerzerer Verfall
    claude_eingabe.VERFALL_MS = int(float(os.environ["PHONEBOX_EINGABE_VERFALL_S"]) * 1000)
eingabe = claude_eingabe.Eingabe()  # Anweisungen vom Handy an Claude, nur im Arbeitsspeicher
eingabe_bremse = auth.Bremse(max_fehler=10, fenster=60, sperre=60)  # hoechstens 10 Anweisungen pro Minute und Benutzer
zustand["rueckfrage"] = None  # wartet auf Bestaetigung: {"nr", "name", "icon", "frage", "bis"}
shortcut_liste = []
shortcut_stand = None  # (Pfad, Aenderungszeit) der geladenen Liste


class Verboten(Exception):
    """Der Benutzer darf das nicht. Wird dem Geraet als Meldung gezeigt und im Aktivitaetsprotokoll vermerkt."""

    def __init__(self, was, text="Dafür hast du keine Berechtigung."):
        super().__init__(text)
        self.was, self.text = was, text


_eingabe_cache = {"an": None}
claude_antwort = {"text": "", "zeit": 0}  # Claudes letzte Antwort (nur im Arbeitsspeicher, nur fuer Administratoren am Handy)
ANTWORT_MAX = 4000


def eingabe_an():
    """Ist das Schreiben an Claude eingeschaltet? Standard: aus. Gilt nur, wenn ein Administrator es bewusst einschaltet."""
    if _eingabe_cache["an"] is None:
        _eingabe_cache["an"] = konten.einstellung("claude_eingabe", "aus") == "an"
    return _eingabe_cache["an"]


def jetzt_ms():
    return int(time.time() * 1000)


def claude_aufraeumen():
    """Setzt einen haengengebliebenen Claude-Status zurueck (z. B. wenn Claude Code abstuerzt)."""
    c = zustand["claude"]
    if c["status"] in ("arbeitet", "fertig") and jetzt_ms() - claude_zuletzt > CLAUDE_ABLAUF_MS:
        c.update(status="", text="", aktion="", seit=jetzt_ms())
        return True
    return False


def rueckfrage_aufraeumen():
    r = zustand["rueckfrage"]
    if r and jetzt_ms() > r["bis"]:
        zustand["rueckfrage"] = None
        return True
    return False


def shortcuts_neu_laden():
    """Liest shortcuts.json neu, sobald sich die Datei geaendert hat."""
    global shortcut_liste, shortcut_stand
    pfad = shortcut_pfad()
    try:
        stand = (str(pfad), pfad.stat().st_mtime)
    except OSError:
        stand = None
    if stand != shortcut_stand:
        shortcut_stand = stand
        shortcut_liste = shortcuts.laden(pfad)
        return True
    return False


def shortcut_pfad():
    """Die eigene Liste, sonst die mitgelieferte Vorlage."""
    return SHORTCUT_DATEI if SHORTCUT_DATEI.exists() else SHORTCUT_VORLAGE


def nachricht_bauen(benutzer):
    """Die Nachricht fuer genau dieses Geraet: mit seinen Rechten, ohne fremde Rueckfragen."""
    r = rechte(benutzer)
    frage = zustand["rueckfrage"]
    eigene_frage = frage if frage and frage.get("von") == benutzer["id"] else None
    return json.dumps({
        "version": VERSION,
        **zustand["medien"],
        "claude": {**zustand["claude"], "jetzt": jetzt_ms()},
        "system": zustand["system"],
        "rechte": r,
        "shortcuts": [{"name": e["name"], "icon": e.get("icon", ""), "bild": e.get("bild", ""),
                       "erlaubt": shortcuts.darf_ausloesen(e, r)} for e in shortcut_liste],
        "shortcut": zustand["shortcut"],
        "claude_eingabe": {"an": eingabe_an(), "darf": r["admin"],
                           "eintraege": eingabe.anzeige() if (r["admin"] and eingabe_an()) else [],
                           "antwort": claude_antwort if (r["admin"] and eingabe_an() and claude_antwort["text"]) else None},
        "rueckfrage": {**{k: v for k, v in eigene_frage.items() if k != "von"}, "jetzt": jetzt_ms()} if eigene_frage else None,
    })


async def an_alle_senden():
    for client in list(clients):
        benutzer = konten.sitzung_pruefen(ws_token.get(client))
        if benutzer is None:  # Sitzung beendet: verbindungen_pruefen trennt das Geraet gleich
            continue
        try:
            await client.send_text(nachricht_bauen(benutzer))
        except Exception:
            clients.discard(client)
            seiten.pop(client, None)
            ws_token.pop(client, None)
            ws_ip.pop(client, None)


async def aktualisieren():
    """Liest den Medienstatus und meldet ihn allen iPhones, wenn er sich geaendert hat."""
    try:
        neu = await asyncio.wait_for(medien.status(), timeout=5)  # haengt nie ewig
    except Exception as fehler:
        neu = {"spielt": False, "titel": "Fehler: " + (str(fehler) or type(fehler).__name__),
               "kuenstler": "", "cover": "", "laut": None, "dauer": 0, "position": 0}
    system = {"cpu": round(psutil.cpu_percent()), "ram": round(psutil.virtual_memory().percent),
              "gpu": zustand["system"]["gpu"], "akkus": zustand["system"]["akkus"]}
    geaendert = shortcuts_neu_laden() | claude_aufraeumen() | rueckfrage_aufraeumen() | eingabe.aufraeumen(jetzt_ms())
    if neu != zustand["medien"] or system != zustand["system"] or geaendert:
        zustand["medien"] = neu
        zustand["system"] = system
        await an_alle_senden()


def eintrag_holen(befehl):
    """'shortcut:3' -> (3, Eintrag). Nur Nummern aus shortcuts.json sind moeglich."""
    try:
        nummer = int(befehl.split(":", 1)[1])
        if nummer < 0:
            return None, None
        return nummer, shortcut_liste[nummer]
    except (ValueError, IndexError):
        return None, None


async def shortcut_anfragen(befehl, benutzer, ip):
    """Antippen einer Kachel. Gefaehrliches (z. B. Herunterfahren) wird erst nach Rueckfrage ausgefuehrt."""
    nummer, eintrag = eintrag_holen(befehl)
    if eintrag is None:
        return
    if not shortcuts.darf_ausloesen(eintrag, rechte(benutzer)):
        raise Verboten(f"Shortcut \u201e{eintrag['name']}\u201c")
    if shortcuts.braucht_bestaetigung(eintrag):
        zustand["rueckfrage"] = {
            "nr": nummer,
            "name": eintrag["name"],
            "icon": eintrag.get("icon", ""),
            "frage": shortcuts.frage(eintrag),
            "bis": jetzt_ms() + FRIST_MS,
            "von": benutzer["id"],  # nur dieser Benutzer sieht die Frage und darf sie bestaetigen
        }
        await an_alle_senden()
        # Belegt im Protokoll, dass die Rueckfrage rausging und an welche Seiten
        alte = [v or "alt" for v in seiten.values() if v != SEITE_ERWARTET]
        log(f"Rueckfrage gesendet: {eintrag['name']} an {len(clients)} Seite(n)"
            + (f", davon zu alt: {', '.join(alte)} (dort erscheint kein Fenster)" if alte else ""))
        return
    await shortcut_ausfuehren(eintrag, benutzer, ip)


async def shortcut_bestaetigt(befehl, benutzer, ip):
    """Nur gueltig, wenn dieser Benutzer vorher genau diesen Eintrag angefragt hat und die Frist noch laeuft."""
    r = zustand["rueckfrage"]
    nummer, eintrag = eintrag_holen(befehl)
    if r and r.get("von") != benutzer["id"]:  # fremde Rueckfrage: nicht anfassen und nicht bestaetigen
        raise Verboten("Bestätigung einer fremden Rückfrage")
    zustand["rueckfrage"] = None
    if not r or eintrag is None or r["nr"] != nummer or r["name"] != eintrag["name"] or jetzt_ms() > r["bis"]:
        log("Bestaetigung abgelehnt (keine offene Rueckfrage oder abgelaufen):", befehl)
        await an_alle_senden()
        return
    if not shortcuts.darf_ausloesen(eintrag, rechte(benutzer)):  # Rechte koennen sich inzwischen geaendert haben
        raise Verboten(f"Shortcut \u201e{eintrag['name']}\u201c")
    await shortcut_ausfuehren(eintrag, benutzer, ip)


async def shortcut_ausfuehren(eintrag, benutzer, ip):
    ok = True
    if not TEST:  # im Testmodus nichts am Rechner ausfuehren
        try:
            await asyncio.to_thread(shortcuts.ausfuehren, eintrag)
        except Exception as fehler:
            log("Shortcut fehlgeschlagen:", eintrag["name"], fehler)
            ok = False
    zustand["shortcut"] = {
        "nr": zustand["shortcut"]["nr"] + 1,
        "name": eintrag["name"],
        "ok": ok,
        "text": shortcuts.meldung(eintrag),
    }
    log("Shortcut:", eintrag["name"], "ok" if ok else "FEHLER", "von", benutzer["name"])
    konten.protokoll("shortcut", f"{eintrag['name']}: " + ("ausgelöst" if ok else "FEHLER"), benutzer, ip)
    await an_alle_senden()


async def verbindungen_pruefen():
    """Trennt Geraete, deren Sitzung beendet wurde (abgemeldet, gesperrt, Passwort geaendert)."""
    for client, token in list(ws_token.items()):
        if konten.sitzung_pruefen(token) is None:
            ws_token.pop(client, None)
            clients.discard(client)
            try:
                await client.close(code=1008)
            except Exception:
                pass


async def geraete_schleife():
    """Liest GPU und Akkus in eigenen Threads (die Abfragen koennen langsam sein) und bremst sich bei langsamen
    Abfragen selbst, damit der PC im Dauerbetrieb nicht belastet wird."""
    naechste_gpu = naechster_akku = 0.0
    bekannt = None
    while True:
        try:
            jetzt = time.monotonic()
            if jetzt >= naechste_gpu:
                start = time.monotonic()
                zustand["system"]["gpu"] = await asyncio.to_thread(gpu_holen)
                naechste_gpu = time.monotonic() + max(2.0, (time.monotonic() - start) * 5)
            if jetzt >= naechster_akku:
                start = time.monotonic()
                akkus = await asyncio.to_thread(akkus_holen)
                zustand["system"]["akkus"] = akkus
                naechster_akku = time.monotonic() + max(30.0, (time.monotonic() - start) * 10)
                namen = sorted(a["name"] for a in akkus)
                if namen != bekannt:  # nur bei Aenderungen ins Protokoll, hilft bei der Fehlersuche
                    bekannt = namen
                    log("Akku-Geraete:", ", ".join(f"{a['name']} ({a['prozent'] if a['prozent'] is not None else a.get('stufe')})" for a in akkus) or "keine")
        except Exception as fehler:
            log("Geraete lesen fehlgeschlagen:", repr(fehler))
            naechste_gpu = naechster_akku = time.monotonic() + 30
        await asyncio.sleep(1)


async def schleife():
    zaehler = 0
    while True:
        try:
            await aktualisieren()
            zaehler += 1
            if zaehler % 15 == 0:
                await verbindungen_pruefen()
            if zaehler % 3600 == 0:
                konten.aufraeumen()
        except Exception as fehler:  # die Schleife darf nie sterben
            log("Aktualisieren fehlgeschlagen:", repr(fehler))
        await asyncio.sleep(1)


app = FastAPI()
zertifikat_info = None  # gesetzt, sobald HTTPS laeuft: Pfade und Fingerabdruck der eigenen CA
app.include_router(auth.router)
app.include_router(admin.router)


@app.middleware("http")
async def herkunft_pruefen(request: Request, call_next):
    abgelehnt = auth.pruefe_herkunft(request)
    return abgelehnt if abgelehnt else await call_next(request)


@app.get("/")
async def startseite(request: Request):
    if not auth.benutzer_aus(request.cookies):
        return RedirectResponse("/anmelden", status_code=303)
    html = (ORDNER / "index.html").read_text(encoding="utf-8")
    text = seitencheck.warnung(html, VERSION)
    if text:  # eine alte index.html wird trotzdem ausgeliefert, aber mit roter Warnleiste
        log("WARNUNG:", text)
        html = seitencheck.mit_warnung(html, text)
    # no-store: Safari darf die Seite nie aus dem Zwischenspeicher zeigen, sonst passen Seite und Server nicht zusammen
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/zertifikat")
async def zertifikat_seite(request: Request):
    """Oeffentlich: Anleitung, das Zertifikat am Handy zu installieren (enthaelt nur den oeffentlichen Teil)."""
    if not zertifikat_info:
        return PlainTextResponse("HTTPS ist nicht eingeschaltet.", status_code=404)
    html = (ORDNER / "zertifikat.html").read_text(encoding="utf-8")
    html = html.replace("{{FINGERABDRUCK}}", zertifikat_info["fingerabdruck"])
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/ca.crt")
async def ca_zertifikat():
    if not zertifikat_info:
        return Response(status_code=404)
    daten = Path(zertifikat_info["ca"]).read_bytes()  # nur ca.pem, nie ein privater Schluessel
    return Response(daten, media_type="application/x-x509-ca-cert", headers={"Cache-Control": "no-store"})


@app.get("/log")
async def protokoll_zeigen(request: Request):
    """Die letzten Meldungen des Servers, zum Nachlesen im Browser (nur Administratoren)."""
    b = auth.benutzer_aus(request.cookies)
    if not b:
        return RedirectResponse("/anmelden", status_code=303)
    if b["rolle"] != "admin":
        return PlainTextResponse("Das Protokoll darf nur ein Administrator sehen.", status_code=403)
    return PlainTextResponse("Phonebox " + VERSION + "\n\n" + "\n".join(protokoll.zeilen))


@app.get("/cover")
async def cover(request: Request, id: str = ""):
    if not auth.benutzer_aus(request.cookies):
        return Response(status_code=401)
    ergebnis = await medien.cover()
    if ergebnis is None:
        return Response(status_code=404)
    daten, art = ergebnis
    return Response(daten, media_type=art, headers={"Cache-Control": "no-store"})


class ClaudeMeldung(BaseModel):
    status: str = Field(pattern="^(arbeitet|fertig|wartet|)$", max_length=10)  # "" = ruht
    text: str = Field("", max_length=300)  # Ueberschrift fuer das Banner (z. B. die Frage bei "wartet")
    aktion: str = Field("", max_length=300)  # woran Claude gerade arbeitet
    projekt: str = Field("", max_length=200)
    neu: bool = False  # neue Aufgabe: Verlauf leeren
    ereignis: str = Field("", max_length=40)  # welches Hook-Ereignis die Meldung ausgeloest hat (fuer die Diagnose)


# Was bisher von Claude angekommen ist: hilft herauszufinden, ob die Hooks laufen
claude_diag = {"letzte": 0, "anzahl": 0, "ereignisse": {}, "quelle": ""}


def diag_zaehlen(ereignis, quelle):
    """Merkt sich, dass etwas von Claude angekommen ist (auch bei Ereignissen, die die Anzeige nicht aendern)."""
    claude_diag["letzte"] = jetzt_ms()
    claude_diag["anzahl"] += 1
    claude_diag["quelle"] = quelle
    name = ereignis or "(ohne Angabe)"
    claude_diag["ereignisse"][name] = claude_diag["ereignisse"].get(name, 0) + 1
    if claude_diag["anzahl"] == 1:
        log(f"Erste Meldung von Claude seit dem Start: {name} von {quelle}")


async def claude_verarbeiten(meldung, quelle):
    global claude_zuletzt
    c = zustand["claude"]
    jetzt = jetzt_ms()
    claude_zuletzt = jetzt
    diag_zaehlen(meldung.ereignis, quelle)
    if meldung.status != c["status"]:
        if c["status"] == "arbeitet" and meldung.status == "fertig":
            c["dauer"] = (jetzt - c["seit"]) // 1000  # so lange hat Claude gearbeitet
        c["seit"] = jetzt
    c["status"] = meldung.status
    c["text"] = meldung.text[:120]
    if meldung.projekt:
        c["projekt"] = meldung.projekt[:60]
    if meldung.neu:
        c["verlauf"] = []
    aktion = meldung.aktion[:120]
    if aktion:
        if not c["verlauf"] or c["verlauf"][-1]["text"] != aktion:
            c["verlauf"].append({"zeit": jetzt, "text": aktion})
            c["verlauf"] = c["verlauf"][-8:]
        c["aktion"] = aktion
    elif meldung.status != "arbeitet":
        c["aktion"] = ""
    await an_alle_senden()


@app.post("/claude")
async def claude_status(meldung: ClaudeMeldung, request: Request):
    """Wird von den Claude-Code-Hooks aufgerufen (siehe hooks/). Nur vom PC selbst oder mit Anmeldung."""
    if not (auth.lokal(request) or auth.benutzer_aus(request.cookies)):
        return PlainTextResponse("Nicht erlaubt.", status_code=403)
    await claude_verarbeiten(meldung, auth.adresse(request))
    return {"ok": True}


HOOK_MAX_BYTES = 5_000_000  # Ereignisse koennen grosse Werkzeug-Eingaben enthalten, aber nicht unbegrenzt


@app.post("/claude-hook")
async def claude_hook(request: Request):
    """Hier schickt Claude Code seine Hook-Ereignisse hin (Hook-Typ "http"). Die Antwort ist {} (keine Entscheidung, Claude Code
    macht normal weiter), ausser es wartet eine Anweisung vom Handy: dann geht sie mit. Nur vom PC selbst oder mit Anmeldung."""
    if not (auth.lokal(request) or auth.benutzer_aus(request.cookies)):
        return PlainTextResponse("Nicht erlaubt.", status_code=403)
    if int(request.headers.get("content-length") or 0) > HOOK_MAX_BYTES:
        return JSONResponse({}, status_code=413)
    koerper = bytearray()
    async for teil in request.stream():
        koerper += teil
        if len(koerper) > HOOK_MAX_BYTES:
            return JSONResponse({}, status_code=413)
    try:
        daten = json.loads(bytes(koerper) or b"{}")
    except ValueError:
        return JSONResponse({"fehler": "kein JSON"}, status_code=400)
    ereignis = str(daten.get("hook_event_name", ""))[:40] if isinstance(daten, dict) else ""
    meldung = claude_ereignisse.meldung_aus_ereignis(daten)
    quelle = auth.adresse(request)
    if isinstance(daten, dict) and isinstance(daten.get("session_id"), str) and auth.lokal(request):
        letzte_hook["session"], letzte_hook["zeit"] = daten["session_id"][:100], time.time()
    # Wartende Anweisungen vom Handy gibt es nur an Claude Code auf dem PC selbst, nie an angemeldete Browser aus dem WLAN
    antwort, uebergeben = ({}, None)
    mod_da = mod_aktiv()  # Ist der Mod in Claude Code verbunden, holt er die Anweisungen selbst ab (zuverlaessiger)
    if auth.lokal(request) and not mod_da:
        antwort, uebergeben = eingabe_uebergabe(ereignis)
    if uebergeben and ereignis == "Stop":  # Claude arbeitet weiter: nicht "fertig" melden und nicht piepen
        meldung = {"status": "arbeitet", "aktion": "Anweisung vom Handy: " + claude_ereignisse.kurz(uebergeben, 50),
                   "projekt": (meldung or {}).get("projekt", "")}
    if meldung is None:
        diag_zaehlen(ereignis, quelle)  # angekommen, aendert die Anzeige aber nicht
    else:
        meldung["projekt"] = meldung.get("projekt", "")[:200]
        await claude_verarbeiten(ClaudeMeldung(**meldung, ereignis=ereignis), quelle)
    if not uebergeben and ereignis == "Stop" and auth.lokal(request) and eingabe_an() and not mod_da:
        # Claude ist fertig: kurz offen bleiben und auf eine Anweisung vom Handy warten (Claude Code wartet auf diese Antwort)
        antwort, uebergeben = await auf_anweisung_warten(request)
        if uebergeben:
            await claude_verarbeiten(ClaudeMeldung(status="arbeitet", aktion="Anweisung vom Handy: " + claude_ereignisse.kurz(uebergeben, 50),
                                                   projekt=(meldung or {}).get("projekt", ""), ereignis="Stop"), quelle)
    if uebergeben:
        await an_alle_senden()
    return JSONResponse(antwort)


letzte_hook = {"session": "", "zeit": 0.0}  # welche Claude-Sitzung zuletzt ein Hook-Ereignis geschickt hat
mod_sitzungen = {}  # session_id -> {"cwd", "zeit"}: Herzschlag des Claude-Mods
MOD_FRIST_S = 10


def mod_aktiv():
    jetzt = time.time()
    for sid in [k for k, v in mod_sitzungen.items() if jetzt - v["zeit"] > 60]:
        del mod_sitzungen[sid]
    return any(jetzt - v["zeit"] <= MOD_FRIST_S for v in mod_sitzungen.values())


def mod_ziel():
    """Die Sitzung, die Anweisungen bekommt: die mit dem juengsten Hook-Ereignis oder die zuletzt geoeffnete, je nachdem, was neuer ist."""
    jetzt = time.time()
    frisch = {k: v for k, v in mod_sitzungen.items() if jetzt - v["zeit"] <= MOD_FRIST_S}
    if len(frisch) < 2:
        return ""
    neueste = max(frisch, key=lambda k: frisch[k]["seit"])
    aktiv = letzte_hook["session"]
    if aktiv in frisch and letzte_hook["zeit"] >= frisch[neueste]["seit"]:
        return aktiv
    return neueste


class ModAbholen(BaseModel):
    session_id: str = Field(default="", max_length=100)
    cwd: str = Field(default="", max_length=300)


@app.post("/api/claude/mod/abholen")
async def claude_mod_abholen(ein: ModAbholen, request: Request):
    """Der Mod in Claude Code fragt hier regelmaessig nach einer Anweisung vom Handy. Nur vom PC selbst (nie von aussen).
    Er schickt sie als Nachricht in die Sitzung; das funktioniert auch, wenn Claude gerade fertig ist."""
    if not auth.lokal(request):
        return PlainTextResponse("Nicht erlaubt.", status_code=403)
    sid = ein.session_id or "unbekannt"
    if len(mod_sitzungen) < 50 or sid in mod_sitzungen:
        mod_sitzungen[sid] = {"cwd": ein.cwd[:300], "zeit": time.time(),
                              "seit": mod_sitzungen.get(sid, {}).get("seit", time.time())}
    if not eingabe_an():
        return {}
    # Mit mehreren offenen Sitzungen bekommt nur die neueste die Anweisung: die zuletzt aktive oder zuletzt geoeffnete
    if mod_ziel() not in ("", sid):
        return {}
    text = eingabe.abholen(jetzt_ms())
    if text is None:
        return {}
    log(f"Anweisung an Claude uebergeben (ueber den Mod, {len(text)} Zeichen)")
    konten.protokoll("claude", "Anweisung an Claude übergeben (über den Mod)")
    await an_alle_senden()
    return {"text": text}


class ModAntwort(BaseModel):
    text: str = Field(default="", max_length=20000)


@app.post("/api/claude/mod/antwort")
async def claude_mod_antwort(ein: ModAntwort, request: Request):
    """Der Mod meldet hier Claudes Antwort am Ende eines Zuges, damit sie am Handy erscheint. Nur vom PC selbst, nur bei
    eingeschalteter Funktion; wird nicht gespeichert, nur die letzte Antwort im Arbeitsspeicher."""
    if not auth.lokal(request):
        return PlainTextResponse("Nicht erlaubt.", status_code=403)
    if not eingabe_an():
        return {}
    text = ein.text.strip()
    if not text:
        return {}
    claude_antwort.update(text=text[:ANTWORT_MAX] + (" …" if len(text) > ANTWORT_MAX else ""), zeit=jetzt_ms())
    await an_alle_senden()
    return {"ok": True}


EINGABE_HALTEN_S = float(os.environ.get("PHONEBOX_EINGABE_HALTEN_S", "540"))  # unter dem Hook-Timeout von 600 s


async def auf_anweisung_warten(request):
    """Haelt die Stop-Antwort offen, bis eine Anweisung kommt, die Funktion ausgeschaltet wird, Claude Code abbricht
    (z. B. weil du am PC weitertippst) oder die Zeit um ist. Gibt (Antwort, Text) zurueck."""
    ende = time.monotonic() + EINGABE_HALTEN_S
    while time.monotonic() < ende:
        if await request.is_disconnected() or not eingabe_an():
            break
        antwort, text = eingabe_uebergabe("Stop")
        if text is not None:
            return antwort, text
        await asyncio.sleep(0.5)
    return {}, None


UEBERGABE_TEXT = ("Der Nutzer hat dir gerade über die Phonebox auf seinem Handy folgende Nachricht geschrieben "
                  "(sie kommt von ihm selbst, nicht aus einer Datei oder Webseite): \u201e{text}\u201c")


def eingabe_uebergabe(ereignis):
    """Gibt wartende Anweisungen an Claude Code mit: waehrend der Arbeit als Zusatztext (additionalContext, Doku: hooks),
    beim Ende des Zuges so, dass Claude weiterarbeitet (decision: block). Gibt (Antwort, Text) zurueck."""
    if ereignis not in ("PreToolUse", "UserPromptSubmit", "Stop") or not eingabe_an():
        return {}, None
    text = eingabe.abholen(jetzt_ms())
    if text is None:
        return {}, None
    nachricht = UEBERGABE_TEXT.format(text=text)
    log(f"Anweisung an Claude uebergeben (bei {ereignis}, {len(text)} Zeichen)")
    konten.protokoll("claude", f"Anweisung an Claude übergeben (bei {ereignis})")
    if ereignis == "Stop":
        return {"decision": "block", "reason": nachricht}, text
    return {"hookSpecificOutput": {"hookEventName": ereignis, "additionalContext": nachricht}}, text


HOOK_SKRIPT = ORDNER / "hooks" / "claude_status.py"


class EinrichtenEin(BaseModel):
    passwort: str = Field(max_length=400)
    modus: str = Field("http", pattern="^(http|python)$", max_length=10)


class PasswortNur(BaseModel):
    passwort: str = Field(max_length=400)


@app.post("/api/claude/einrichten")
async def claude_einrichten_route(ein: EinrichtenEin, request: Request):
    """Traegt die Hooks in die settings.json von Claude Code ein (nur Administratoren, mit Passwort)."""
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    falsch = admin._passwort_pruefen(b, request, ein.passwort)
    if falsch:
        return falsch
    if ein.modus == "python" and not HOOK_SKRIPT.exists():
        return auth.fehler_antwort("hooks/claude_status.py fehlt im Ordner der Phonebox.", 500)
    try:
        erg = claude_einrichten.einrichten(ein.modus, PORT, skript=HOOK_SKRIPT)
    except (claude_einrichten.EinrichtungsFehler, OSError) as f:
        return auth.fehler_antwort(str(f), 400)
    log(f"Admin {b['name']}: Claude-Hooks eingerichtet ({ein.modus}) in {erg['pfad']}")
    konten.protokoll("admin", f"Claude-Hooks eingerichtet ({ein.modus})", b, auth.adresse(request))
    return {"ok": True, **erg}


@app.post("/api/claude/entfernen")
async def claude_entfernen_route(ein: PasswortNur, request: Request):
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    falsch = admin._passwort_pruefen(b, request, ein.passwort)
    if falsch:
        return falsch
    try:
        erg = claude_einrichten.entfernen()
    except (claude_einrichten.EinrichtungsFehler, OSError) as f:
        return auth.fehler_antwort(str(f), 400)
    log(f"Admin {b['name']}: Claude-Hooks entfernt ({erg['entfernt']})")
    konten.protokoll("admin", f"Claude-Hooks entfernt ({erg['entfernt']} Eintraege)", b, auth.adresse(request))
    return {"ok": True, **erg}


class EingabeSchalter(BaseModel):
    passwort: str = Field(max_length=400)
    an: bool


class NachrichtEin(BaseModel):
    text: str = Field(max_length=claude_eingabe.MAX_TEXT + 500)


class NachrichtId(BaseModel):
    id: int


@app.post("/api/claude/eingabe")
async def claude_eingabe_schalten(ein: EingabeSchalter, request: Request):
    """Schaltet das Schreiben an Claude ein oder aus (nur Administratoren, mit Passwort). Standard: aus."""
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    falsch = admin._passwort_pruefen(b, request, ein.passwort)
    if falsch:
        return falsch
    konten.einstellung_setzen("claude_eingabe", "an" if ein.an else "aus")
    _eingabe_cache["an"] = ein.an
    if not ein.an:
        eingabe.leeren()  # nichts Wartendes darf nach dem Ausschalten noch losgehen
        claude_antwort.update(text="", zeit=0)
    log(f"Admin {b['name']}: Anweisungen an Claude {'eingeschaltet' if ein.an else 'ausgeschaltet'}")
    konten.protokoll("admin", f"Anweisungen vom Handy an Claude {'eingeschaltet' if ein.an else 'ausgeschaltet'}", b, auth.adresse(request))
    await an_alle_senden()
    return {"ok": True, "an": ein.an}


@app.post("/api/claude/nachricht")
async def claude_nachricht(ein: NachrichtEin, request: Request):
    """Eine Anweisung fuer Claude in die Warteschlange legen. Nur Administratoren, nur wenn eingeschaltet."""
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    if not eingabe_an():
        return auth.fehler_antwort("Das Schreiben an Claude ist ausgeschaltet. Ein Administrator kann es im Admin-Bereich einschalten.", 403)
    schluessel = f"{b['id']}"
    rest = eingabe_bremse.rest(schluessel)
    if rest:
        return auth.fehler_antwort(auth.warte_text(rest), 429)
    eingabe_bremse.fehler(schluessel)  # jeder Versuch zaehlt
    try:
        eintrag = eingabe.einreihen(ein.text, b["name"], jetzt_ms())
    except claude_eingabe.EingabeFehler as f:
        return auth.fehler_antwort(str(f), 400)
    log(f"Anweisung an Claude von {b['name']} ({len(eintrag['text'])} Zeichen)")
    konten.protokoll("claude", f"Anweisung an Claude ({len(eintrag['text'])} Zeichen): {eintrag['text'][:60]}", b, auth.adresse(request))
    await an_alle_senden()
    return {"ok": True, "id": eintrag["id"]}


@app.post("/api/claude/nachricht/zurueckziehen")
async def claude_nachricht_zurueck(ein: NachrichtId, request: Request):
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    if not eingabe.zurueckziehen(ein.id):
        return auth.fehler_antwort("Diese Anweisung wartet nicht mehr.", 409)
    konten.protokoll("claude", "Anweisung zurückgezogen", b, auth.adresse(request))
    await an_alle_senden()
    return {"ok": True}


@app.get("/api/claude/diagnose")
async def claude_diagnose(request: Request):
    """Fuer den Admin-Bereich: Kommt etwas von Claude an? (Die Hook-Einrichtung ergaenzt admin.py.)"""
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    return {**claude_diag, "jetzt": jetzt_ms(), "status": zustand["claude"]["status"], "port": PORT,
            "eingabe_an": eingabe_an(), "mod_aktiv": mod_aktiv(), "eingabe_wartend": len(eingabe.wartende()),
            "einrichtung": claude_einrichten.pruefen(PORT)}


class ClaudeTest(BaseModel):
    status: str = Field(pattern="^(arbeitet|fertig|wartet)$", max_length=10)


@app.post("/api/claude/test")
async def claude_test(ein: ClaudeTest, request: Request):
    """Zeigt eine Testmeldung auf allen Geraeten, damit man die Anzeige (und den Ton) pruefen kann."""
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    texte = {"arbeitet": "Testmeldung: Claude arbeitet", "wartet": "Testmeldung: Claude braucht dich", "fertig": ""}
    await claude_verarbeiten(ClaudeMeldung(status=ein.status, text=texte[ein.status], aktion="Testmeldung", projekt="Test",
                                           neu=ein.status == "arbeitet", ereignis="Test"), "Admin-Test")
    return {"ok": True}


MUSIK_TEXT = {"playpause": "Wiedergabe umgeschaltet", "weiter": "Nächster Titel", "zurueck": "Vorheriger Titel"}


async def befehl_bearbeiten(befehl, benutzer, ip):
    if TEST and befehl == "fehlertest":  # prueft im Test, dass Fehler auf dem iPhone ankommen
        raise RuntimeError("Testfehler")
    if befehl.startswith("shortcut:"):
        await shortcut_anfragen(befehl, benutzer, ip)
    elif befehl.startswith("bestaetigt:"):
        await shortcut_bestaetigt(befehl, benutzer, ip)
    elif befehl.startswith("gezeigt:"):  # die Seite meldet: Rueckfrage ist zu sehen
        log("Rueckfrage angezeigt auf einer Seite:", befehl)
    elif befehl == "abbruch":
        frage = zustand["rueckfrage"]
        if frage and (frage.get("von") == benutzer["id"] or rechte(benutzer)["admin"]):
            zustand["rueckfrage"] = None
            await an_alle_senden()
    else:  # alles andere ist Musiksteuerung
        if not rechte(benutzer)["musik"]:
            raise Verboten("Musiksteuerung", "Die Musiksteuerung ist für dein Konto abgeschaltet.")
        if befehl in MUSIK_TEXT:
            konten.protokoll("musik", MUSIK_TEXT[befehl], benutzer, ip)
        try:
            await asyncio.wait_for(medien.befehl(befehl), timeout=5)
        except Exception as fehler:
            log("Befehl fehlgeschlagen:", befehl, repr(fehler))
        await asyncio.sleep(0.3)  # Spotify kurz Zeit geben, dann sofort aktualisieren
        await aktualisieren()


@app.websocket("/ws")
async def verbindung(websocket: WebSocket):
    token = websocket.cookies.get(auth.COOKIE)
    if not auth.herkunft_passt(websocket.headers) or not konten.sitzung_pruefen(token):
        await websocket.close(code=1008)  # nicht angemeldet oder fremde Webseite
        return
    await websocket.accept()
    ws_token[websocket] = token
    ws_ip[websocket] = websocket.client.host if websocket.client else ""
    shortcuts_neu_laden()
    seite = websocket.query_params.get("seite", "")[:20]
    if seite != SEITE_ERWARTET:
        # z. B. alte index.html im Ordner oder eine alte Seite aus dem Zwischenspeicher des Browsers
        log(f"WARNUNG: Seite {seite or 'ohne Versionskennung (aelter als v13)'} verbunden, Server ist {SEITE_ERWARTET}."
            " Rueckfragen (Herunterfahren) erscheinen dort evtl. nicht. index.html ersetzen und Seite neu laden.")
    clients.add(websocket)
    seiten[websocket] = seite
    await websocket.send_text(nachricht_bauen(konten.sitzung_pruefen(token)))
    try:
        while True:
            befehl = await websocket.receive_text()
            if not befehl.startswith(("laut:", "suche:")):  # nicht bei jedem Reglerschritt
                log("Befehl:", befehl)
            benutzer = konten.sitzung_pruefen(ws_token.get(websocket))  # Rechte bei jedem Befehl frisch pruefen
            if benutzer is None:
                await websocket.close(code=1008)
                break
            try:
                await befehl_bearbeiten(befehl, benutzer, ws_ip.get(websocket, ""))
            except Verboten as v:
                log(f"VERWEIGERT: {benutzer['name']} wollte {v.was} ({befehl})")
                konten.protokoll("verweigert", f"{v.was} ({befehl.split(':')[0]})", benutzer, ws_ip.get(websocket, ""))
                await websocket.send_text(json.dumps({"fehler": v.text}))
            except Exception as fehler:
                # Fehler nie verschlucken: ins Protokoll und als rote Meldung aufs iPhone
                log("FEHLER bei", befehl, "\n" + traceback.format_exc())
                await websocket.send_text(json.dumps({"fehler": f"{type(fehler).__name__}: {fehler}"}))
    except (WebSocketDisconnect, WebSocketDisconnected):
        pass  # iPhone hat die Verbindung geschlossen (z. B. Seite neu geladen)
    finally:
        clients.discard(websocket)
        seiten.pop(websocket, None)
        ws_token.pop(websocket, None)
        ws_ip.pop(websocket, None)


class OhneSignale(uvicorn.Server):
    """Zwei Server in einem Prozess: das Beenden uebernehmen wir selbst, damit beide sauber enden."""

    def install_signal_handlers(self):
        pass

    @contextlib.contextmanager
    def capture_signals(self):
        yield


def adressen_zeigen(info):
    log(f"Am PC:     http://localhost:{PORT}")
    if info:
        for ip in zertifikate.lokale_adressen():
            log(f"Am Handy:  https://{ip}:{HTTPS_PORT}   (Zertifikat einmalig installieren: https://{ip}:{HTTPS_PORT}/zertifikat)")
        log("Fingerabdruck des Zertifikats (SHA-256):", info["fingerabdruck"])


async def laufen():
    global zertifikat_info
    info = None
    if HTTPS_AN:
        try:
            info = zertifikate.vorbereiten(DATEN, ZUSATZ_NAMEN)
            zertifikat_info = info
            if info["neu_ca"]:
                log("Neues Zertifikat angelegt. Es muss am Handy einmal installiert werden (Seite /zertifikat).")
            elif info["neu_server"]:
                log("Zertifikat fuer neue Adressen erneuert. Das Handy muss nichts neu installieren.")
        except Exception as fehler:
            log("HTTPS ist nicht moeglich:", repr(fehler), "- Tipp: pip install cryptography")
            log("Aus Sicherheitsgruenden laeuft die Phonebox jetzt NUR am PC (localhost), nicht im WLAN.")
    # Mit HTTPS lauscht http nur am PC selbst; ohne HTTPS (bewusst abgeschaltet) wie frueher im ganzen Netz
    http_host = "0.0.0.0" if not HTTPS_AN else "127.0.0.1"
    server = [OhneSignale(uvicorn.Config(app, host=http_host, port=PORT, log_config=None))]
    if info:
        server.append(OhneSignale(uvicorn.Config(app, host="0.0.0.0", port=HTTPS_PORT, log_config=None,
                                                 ssl_certfile=info["cert"], ssl_keyfile=info["key"])))
    elif not HTTPS_AN:
        log("WARNUNG: HTTPS ist abgeschaltet. Passwoerter gehen im WLAN unverschluesselt durch die Luft.")

    def beenden(*_):
        for s in server:
            s.should_exit = True

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if getattr(signal, name, None):
            signal.signal(getattr(signal, name), beenden)

    try:  # das Hook-Skript liest hier den Port, falls er nicht der Standard ist
        (DATEN / "server.json").write_text(json.dumps({"port": PORT, "version": VERSION}), encoding="utf-8")
    except OSError:
        pass
    admin.status_protokollieren(konten)  # Ergebnis eines Updates, das diesen Neustart ausgeloest hat
    aufgabe = asyncio.create_task(schleife())
    geraete_aufgabe = asyncio.create_task(geraete_schleife())
    log(f"Phonebox-Server {VERSION} laeuft" + (" (Testmodus)" if TEST else ""))
    adressen_zeigen(info)
    if konten.anzahl_benutzer() == 0:
        log(f"Noch kein Konto: Oeffne am PC http://localhost:{PORT} und lege das erste Konto an (es wird Administrator).")
    try:
        await asyncio.gather(*(s.serve() for s in server))
    finally:
        aufgabe.cancel()
        geraete_aufgabe.cancel()


if __name__ == "__main__":
    # log_config=None, damit der Server auch ohne Konsolenfenster (pythonw) laeuft
    asyncio.run(laufen())
