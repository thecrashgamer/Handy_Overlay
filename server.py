# server.py - Phonebox-Server: Spotify, Lautstaerke und Claude-Status
import asyncio
import json
import os
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

import psutil
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketDisconnected
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

import medien as medien_modul
import protokoll
import shortcuts
from protokoll import log

ORDNER = Path(__file__).parent
TEST = os.environ.get("PHONEBOX_TEST") == "1"  # Fake-Daten statt Windows/Spotify
VERSION = "v11 (Fehleranzeige)"
FRIST_MS = int(float(os.environ.get("PHONEBOX_FRIST_S", "10")) * 1000)  # Zeit zum Bestaetigen
PORT = int(os.environ.get("PHONEBOX_PORT", "8000"))

medien = medien_modul.erstellen(TEST)
clients = set()
SHORTCUT_DATEI = ORDNER / "shortcuts.json"
zustand = {
    "medien": {},
    "claude": {"status": "", "text": "", "aktion": "", "projekt": "", "seit": 0, "dauer": 0, "verlauf": []},
    "system": {"cpu": 0, "ram": 0},
    "shortcut": {"nr": 0, "name": "", "ok": True},  # zuletzt ausgeloest, fuer die Rueckmeldung
}
claude_zuletzt = 0  # wann zuletzt etwas von Claude kam (ms)
CLAUDE_ABLAUF_MS = 10 * 60 * 1000  # nach 10 Minuten Stille gilt Claude als ruhig
zustand["rueckfrage"] = None  # wartet auf Bestaetigung: {"nr", "name", "icon", "frage", "bis"}
shortcut_liste = []
shortcut_stand = None  # Aenderungszeit von shortcuts.json


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
    try:
        stand = SHORTCUT_DATEI.stat().st_mtime
    except OSError:
        stand = None
    if stand != shortcut_stand:
        shortcut_stand = stand
        shortcut_liste = shortcuts.laden(SHORTCUT_DATEI)
        return True
    return False


def nachricht_bauen():
    return json.dumps({
        "version": VERSION,
        **zustand["medien"],
        "claude": {**zustand["claude"], "jetzt": jetzt_ms()},
        "system": zustand["system"],
        "shortcuts": [{"name": e["name"], "icon": e.get("icon", "")} for e in shortcut_liste],
        "shortcut": zustand["shortcut"],
        "rueckfrage": {**zustand["rueckfrage"], "jetzt": jetzt_ms()} if zustand["rueckfrage"] else None,
    })


async def an_alle_senden():
    nachricht = nachricht_bauen()
    for client in list(clients):
        try:
            await client.send_text(nachricht)
        except Exception:
            clients.discard(client)


async def aktualisieren():
    """Liest den Medienstatus und meldet ihn allen iPhones, wenn er sich geaendert hat."""
    try:
        neu = await asyncio.wait_for(medien.status(), timeout=5)  # haengt nie ewig
    except Exception as fehler:
        neu = {"spielt": False, "titel": "Fehler: " + (str(fehler) or type(fehler).__name__),
               "kuenstler": "", "cover": "", "laut": None, "dauer": 0, "position": 0}
    system = {"cpu": round(psutil.cpu_percent()), "ram": round(psutil.virtual_memory().percent)}
    geaendert = shortcuts_neu_laden() | claude_aufraeumen() | rueckfrage_aufraeumen()
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


async def shortcut_anfragen(befehl):
    """Antippen einer Kachel. Gefaehrliches (z. B. Herunterfahren) wird erst nach Rueckfrage ausgefuehrt."""
    nummer, eintrag = eintrag_holen(befehl)
    if eintrag is None:
        return
    if shortcuts.braucht_bestaetigung(eintrag):
        zustand["rueckfrage"] = {
            "nr": nummer,
            "name": eintrag["name"],
            "icon": eintrag.get("icon", ""),
            "frage": shortcuts.frage(eintrag),
            "bis": jetzt_ms() + FRIST_MS,
        }
        await an_alle_senden()
        return
    await shortcut_ausfuehren(eintrag)


async def shortcut_bestaetigt(befehl):
    """Nur gueltig, wenn vorher genau dieser Eintrag angefragt wurde und die Frist noch laeuft."""
    r = zustand["rueckfrage"]
    nummer, eintrag = eintrag_holen(befehl)
    zustand["rueckfrage"] = None
    if not r or eintrag is None or r["nr"] != nummer or r["name"] != eintrag["name"] or jetzt_ms() > r["bis"]:
        log("Bestaetigung abgelehnt (keine offene Rueckfrage oder abgelaufen):", befehl)
        await an_alle_senden()
        return
    await shortcut_ausfuehren(eintrag)


async def shortcut_ausfuehren(eintrag):
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
    log("Shortcut:", eintrag["name"], "ok" if ok else "FEHLER")
    await an_alle_senden()


async def schleife():
    while True:
        try:
            await aktualisieren()
        except Exception as fehler:  # die Schleife darf nie sterben
            log("Aktualisieren fehlgeschlagen:", repr(fehler))
        await asyncio.sleep(1)


@asynccontextmanager
async def lebenszyklus(app):
    aufgabe = asyncio.create_task(schleife())
    yield
    aufgabe.cancel()


app = FastAPI(lifespan=lebenszyklus)


@app.get("/")
async def startseite():
    # no-store: Safari darf die Seite nie aus dem Zwischenspeicher zeigen, sonst passen Seite und Server nicht zusammen
    return FileResponse(ORDNER / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/log")
async def protokoll_zeigen():
    """Die letzten Meldungen des Servers, zum Nachlesen im Browser."""
    return PlainTextResponse("Phonebox " + VERSION + "\n\n" + "\n".join(protokoll.zeilen))


@app.get("/cover")
async def cover(id: str = ""):
    ergebnis = await medien.cover()
    if ergebnis is None:
        return Response(status_code=404)
    daten, art = ergebnis
    return Response(daten, media_type=art, headers={"Cache-Control": "no-store"})


class ClaudeMeldung(BaseModel):
    status: str  # "arbeitet", "fertig" oder "wartet"
    text: str = ""  # Ueberschrift fuer das Banner (z. B. die Frage bei "wartet")
    aktion: str = ""  # woran Claude gerade arbeitet
    projekt: str = ""
    neu: bool = False  # neue Aufgabe: Verlauf leeren


@app.post("/claude")
async def claude_status(meldung: ClaudeMeldung):
    """Wird von den Claude-Code-Hooks aufgerufen (siehe hooks/)."""
    global claude_zuletzt
    c = zustand["claude"]
    jetzt = jetzt_ms()
    claude_zuletzt = jetzt
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
    return {"ok": True}


async def befehl_bearbeiten(befehl):
    if TEST and befehl == "fehlertest":  # prueft im Test, dass Fehler auf dem iPhone ankommen
        raise RuntimeError("Testfehler")
    if befehl.startswith("shortcut:"):
        await shortcut_anfragen(befehl)
    elif befehl.startswith("bestaetigt:"):
        await shortcut_bestaetigt(befehl)
    elif befehl == "abbruch":
        zustand["rueckfrage"] = None
        await an_alle_senden()
    else:
        try:
            await asyncio.wait_for(medien.befehl(befehl), timeout=5)
        except Exception as fehler:
            log("Befehl fehlgeschlagen:", befehl, repr(fehler))
        await asyncio.sleep(0.3)  # Spotify kurz Zeit geben, dann sofort aktualisieren
        await aktualisieren()


@app.websocket("/ws")
async def verbindung(websocket: WebSocket):
    await websocket.accept()
    shortcuts_neu_laden()
    clients.add(websocket)
    await websocket.send_text(nachricht_bauen())
    try:
        while True:
            befehl = await websocket.receive_text()
            if not befehl.startswith(("laut:", "suche:")):  # nicht bei jedem Reglerschritt
                log("Befehl:", befehl)
            try:
                await befehl_bearbeiten(befehl)
            except Exception as fehler:
                # Fehler nie verschlucken: ins Protokoll und als rote Meldung aufs iPhone
                log("FEHLER bei", befehl, "\n" + traceback.format_exc())
                await websocket.send_text(json.dumps({"fehler": f"{type(fehler).__name__}: {fehler}"}))
    except (WebSocketDisconnect, WebSocketDisconnected):
        pass  # iPhone hat die Verbindung geschlossen (z. B. Seite neu geladen)
    finally:
        clients.discard(websocket)


if __name__ == "__main__":
    log(f"Phonebox-Server {VERSION} laeuft auf Port {PORT}" + (" (Testmodus)" if TEST else ""))
    # log_config=None, damit der Server auch ohne Konsolenfenster (pythonw) laeuft
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None)
