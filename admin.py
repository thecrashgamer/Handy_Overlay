"""Admin-Bereich: Shortcuts anlegen, aendern, loeschen. Nur fuer Administratoren."""
import asyncio
import base64
import binascii
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi import Response
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

import auth
import icons
import shortcuts
import update
from protokoll import log

router = APIRouter()
eigene_datei = Path("shortcuts.json")
vorlage_datei = Path("shortcuts.json")
ordner = Path(".")


def einrichten(eigene, vorlage, seiten_ordner):
    global eigene_datei, vorlage_datei, ordner
    eigene_datei, vorlage_datei, ordner = Path(eigene), Path(vorlage), Path(seiten_ordner)


# ---------------------------------------------------------------- Update aus dem Admin-Bereich
# Die Quelle ist fest (GitHub). Sie laesst sich nur ueber die Umgebung des Servers aendern, nie ueber die Seite.
UPDATE_QUELLE = os.environ.get("PHONEBOX_UPDATE_QUELLE", update.QUELLE_STANDARD)
HAENGT_NACH = 600  # Sekunden ohne Meldung: das Update gilt als haengengeblieben
_pruef_cache = {"zeit": 0, "daten": None}
_start_sperre = asyncio.Lock()


def status_datei():
    return eigene_datei.parent / "update-status.json"


def log_datei():
    return eigene_datei.parent / "update.log"


def status_lesen():
    try:
        d = json.loads(status_datei().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"zustand": "keiner"}
    if d.get("zustand") == "laeuft" and time.time() - d.get("zeit", 0) > HAENGT_NACH:
        d = {**d, "zustand": "fehler", "meldung": "Das Update scheint haengengeblieben zu sein (seit 10 Minuten keine Meldung)."}
    return d


def _status_schreiben(d):
    ziel = status_datei()
    ziel.parent.mkdir(parents=True, exist_ok=True)
    hilfe = ziel.with_name(ziel.name + ".neu")
    hilfe.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(hilfe, ziel)


def status_protokollieren(konten):
    """Schreibt das Ergebnis eines Updates einmal ins Aktivitaetsprotokoll (auch nach dem Neustart des Servers)."""
    d = status_lesen()
    if d.get("zustand") in ("fertig", "fehler") and not d.get("protokolliert"):
        was = "Wiederherstellung" if d.get("aktion") == "zurueck" else "Update"
        text = f"{was}: {d.get('von', '?')} -> {d.get('nach', d.get('von', '?'))}" if d["zustand"] == "fertig" else f"{was} fehlgeschlagen: {d.get('meldung', '')}"
        konten.protokoll("system", text)
        try:
            _status_schreiben({**d, "protokolliert": True})
        except OSError:
            pass


class UpdateEin(BaseModel):
    passwort: str = Field(max_length=400)
    zurueck: bool = False


def _passwort_pruefen(b, request, passwort):
    """Gemeinsame Pruefung fuer heikle Aktionen. Gibt eine Fehlerantwort zurueck oder None."""
    schluessel = f"{auth.adresse(request)}|{b['name'].lower()}"
    rest = auth.bremse_konto.rest(schluessel)
    if rest:
        return auth.fehler_antwort(auth.warte_text(rest), 429)
    if not auth.konten.passwort_stimmt(b["id"], passwort):
        auth.bremse_konto.fehler(schluessel)
        auth.konten.protokoll("sicherheit", "Update mit falschem Passwort versucht", b, auth.adresse(request))
        return auth.fehler_antwort("Das Passwort stimmt nicht.", 403)
    auth.bremse_konto.erfolg(schluessel)
    return None


@router.get("/api/update/pruefen")
async def update_pruefen(request: Request, neu: int = 0):
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    installiert = update.version_lesen(ordner)
    jetzt = time.time()
    if neu or _pruef_cache["daten"] is None or jetzt - _pruef_cache["zeit"] > 300:
        try:
            _pruef_cache["daten"] = await asyncio.to_thread(update.neueste_version, UPDATE_QUELLE)
            _pruef_cache["zeit"] = jetzt
        except update.UpdateFehler as f:
            return auth.fehler_antwort(str(f), 502)
    d = _pruef_cache["daten"]
    return JSONResponse({
        "installiert": installiert, "neueste": d["version"], "aenderung": d.get("aenderung", ""),
        "neu": update.version_nummer(d["version"]) > update.version_nummer(installiert),
        "geprueft": int(_pruef_cache["zeit"]),
    }, headers={"Cache-Control": "no-store"})


@router.get("/api/update/status")
async def update_status(request: Request):
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    status_protokollieren(auth.konten)
    return JSONResponse({**status_lesen(), "installiert": update.version_lesen(ordner)}, headers={"Cache-Control": "no-store"})


@router.post("/api/update/starten")
async def update_starten(ein: UpdateEin, request: Request):
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    if not (ordner / "update.py").exists():
        return auth.fehler_antwort("update.py fehlt im Ordner der Phonebox.", 500)
    falsch = _passwort_pruefen(b, request, ein.passwort)
    if falsch:
        return falsch
    async with _start_sperre:
        if status_lesen().get("zustand") == "laeuft":
            return auth.fehler_antwort("Es läuft schon ein Update.", 409)
        _pruef_cache["daten"] = None  # nach dem Update neu fragen
        von = update.version_lesen(ordner)
        _status_schreiben({"zustand": "laeuft", "von": von, "aktion": "zurueck" if ein.zurueck else "update",
                           "protokolliert": False, "zeit": int(time.time()), "zeilen": ["Das Update wird gestartet ..."]})
        argumente = ["--status", str(status_datei())] + (["--zurueck"] if ein.zurueck else ["--quelle", UPDATE_QUELLE])
        if os.environ.get("PHONEBOX_UPDATE_OHNE_PIP") == "1":  # nur fuer Tests: kein Netz fuer pip
            argumente.append("--ohne-pip")
        try:
            update.getrennt_starten(ordner, argumente, log_datei())
        except OSError as f:
            _status_schreiben({"zustand": "fehler", "von": von, "meldung": f"Das Update konnte nicht gestartet werden: {f}",
                               "protokolliert": False, "zeit": int(time.time()), "zeilen": []})
            return auth.fehler_antwort(f"Das Update konnte nicht gestartet werden: {f}", 500)
    log(f"Admin {b['name']}: {'Wiederherstellung' if ein.zurueck else 'Update'} gestartet (von {von})")
    auth.konten.protokoll("admin", ("Wiederherstellung" if ein.zurueck else "Update") + f" gestartet (von {von})", b, auth.adresse(request))
    return JSONResponse({"ok": True})


def icons_ordner():
    return eigene_datei.parent / "icons"


class IconEin(BaseModel):
    daten: str = Field(max_length=300_000)  # das Bild als PNG, base64-kodiert


@router.post("/api/icons")
async def icon_hochladen(ein: IconEin, request: Request):
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    try:
        roh = base64.b64decode(ein.daten, validate=True)
        name = icons.speichern(icons_ordner(), roh)
    except (binascii.Error, ValueError):
        return auth.fehler_antwort("Das Bild konnte nicht gelesen werden.", 400)
    except icons.IconFehler as f:
        return auth.fehler_antwort(str(f), 400)
    return JSONResponse({"ok": True, "name": name})


@router.get("/icons/{name}")
async def icon_holen(name: str, request: Request):
    """Ein Symbolbild. Nur fuer angemeldete Benutzer, nur gueltige Namen, nur echte PNG-Dateien."""
    if not auth.benutzer_aus(request.cookies):
        return Response(status_code=401)
    daten = icons.laden(icons_ordner(), name)
    if daten is None:
        return Response(status_code=404)
    return Response(daten, media_type="image/png", headers={
        "Cache-Control": "private, max-age=31536000, immutable",  # der Name entsteht aus dem Inhalt
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    })


class SpeichernEin(BaseModel):
    shortcuts: list = Field(max_length=100)
    passwort: str = Field(max_length=400)


@router.get("/admin")
async def admin_seite(request: Request):
    b = auth.benutzer_aus(request.cookies)
    if not b:
        return RedirectResponse("/anmelden", status_code=303)
    if b["rolle"] != "admin":
        return PlainTextResponse("Der Admin-Bereich ist nur fuer Administratoren.", status_code=403)
    return auth.seite("admin.html")


@router.get("/api/shortcuts")
async def liste_holen(request: Request):
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    quelle = eigene_datei if eigene_datei.exists() else vorlage_datei
    return JSONResponse(
        {
            "shortcuts": shortcuts.laden(quelle),
            "eigene": eigene_datei.exists(),
            "aktionen": shortcuts.AKTION_NAMEN,
            "maximal": shortcuts.MAX_SHORTCUTS,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/shortcuts/speichern")
async def speichern(ein: SpeichernEin, request: Request):
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    # Aenderungen, die Programme am PC starten, nur mit erneuter Passwort-Eingabe (falls eine Sitzung gestohlen wurde)
    schluessel = f"{auth.adresse(request)}|{b['name'].lower()}"
    rest = auth.bremse_konto.rest(schluessel)
    if rest:
        return auth.fehler_antwort(auth.warte_text(rest), 429)
    if not auth.konten.passwort_stimmt(b["id"], ein.passwort):
        auth.bremse_konto.fehler(schluessel)
        auth.konten.protokoll("sicherheit", "Shortcuts speichern mit falschem Passwort", b, auth.adresse(request))
        return auth.fehler_antwort("Das Passwort stimmt nicht.", 403)
    auth.bremse_konto.erfolg(schluessel)
    try:
        liste = shortcuts.pruefen_liste(ein.shortcuts)
    except ValueError as f:
        return auth.fehler_antwort(str(f), 400)
    fehlend = [e["name"] for e in liste if e.get("bild") and not icons.existiert(icons_ordner(), e["bild"])]
    if fehlend:
        return auth.fehler_antwort("Das Bild fehlt noch (bitte neu hineinziehen): " + ", ".join(fehlend), 400)
    shortcuts.speichern(eigene_datei, liste)
    icons.aufraeumen(icons_ordner(), {e["bild"] for e in liste if e.get("bild")})
    log(f"Admin {b['name']}: Shortcuts gespeichert ({len(liste)} Eintraege): " + ", ".join(e["name"] for e in liste))
    auth.konten.protokoll("admin", f"Shortcuts gespeichert ({len(liste)} Einträge)", b, auth.adresse(request))
    return JSONResponse({"ok": True, "shortcuts": liste})
