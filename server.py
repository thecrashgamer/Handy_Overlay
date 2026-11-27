# server.py - Phonebox-Server: Spotify, Lautstaerke und Claude-Status
import asyncio
import json
import os
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
VERSION = "v7 (Zeitleiste)"
PORT = int(os.environ.get("PHONEBOX_PORT", "8000"))

medien = medien_modul.erstellen(TEST)
clients = set()
SHORTCUT_DATEI = ORDNER / "shortcuts.json"
zustand = {
    "medien": {},
    "claude": {"status": "", "text": ""},
    "system": {"cpu": 0, "ram": 0},
    "shortcut": {"nr": 0, "name": "", "ok": True},  # zuletzt ausgeloest, fuer die Rueckmeldung
}
shortcut_liste = []
shortcut_stand = None  # Aenderungszeit von shortcuts.json


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
        "claude": zustand["claude"],
        "system": zustand["system"],
        "shortcuts": [{"name": e["name"], "icon": e.get("icon", "")} for e in shortcut_liste],
        "shortcut": zustand["shortcut"],
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
    geaendert = shortcuts_neu_laden()
    if neu != zustand["medien"] or system != zustand["system"] or geaendert:
        zustand["medien"] = neu
        zustand["system"] = system
        await an_alle_senden()


async def shortcut_ausloesen(befehl):
    """befehl = 'shortcut:<Nummer>'. Nur Eintraege aus shortcuts.json sind moeglich."""
    try:
        nummer = int(befehl.split(":", 1)[1])
        if nummer < 0:
            return
        eintrag = shortcut_liste[nummer]
    except (ValueError, IndexError):
        return
    ok = True
    if not TEST:  # im Testmodus nichts am Rechner ausfuehren
        try:
            await asyncio.to_thread(shortcuts.ausfuehren, eintrag)
        except Exception as fehler:
            log("Shortcut fehlgeschlagen:", eintrag["name"], fehler)
            ok = False
    zustand["shortcut"] = {"nr": zustand["shortcut"]["nr"] + 1, "name": eintrag["name"], "ok": ok}
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
    return FileResponse(ORDNER / "index.html")


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
    text: str = ""


@app.post("/claude")
async def claude_status(meldung: ClaudeMeldung):
    """Wird von den Claude-Code-Hooks aufgerufen (siehe hooks/)."""
    zustand["claude"] = {"status": meldung.status, "text": meldung.text}
    await an_alle_senden()
    return {"ok": True}


@app.websocket("/ws")
async def verbindung(websocket: WebSocket):
    await websocket.accept()
    shortcuts_neu_laden()
    clients.add(websocket)
    await websocket.send_text(nachricht_bauen())
    try:
        while True:
            befehl = await websocket.receive_text()
            if befehl.startswith("shortcut:"):
                await shortcut_ausloesen(befehl)
                continue
            try:
                await asyncio.wait_for(medien.befehl(befehl), timeout=5)
            except Exception as fehler:
                log("Befehl fehlgeschlagen:", befehl, repr(fehler))
            await asyncio.sleep(0.3)  # Spotify kurz Zeit geben, dann sofort aktualisieren
            try:
                await aktualisieren()
            except Exception as fehler:
                log("Aktualisieren fehlgeschlagen:", repr(fehler))
    except (WebSocketDisconnect, WebSocketDisconnected):
        pass  # iPhone hat die Verbindung geschlossen (z. B. Seite neu geladen)
    finally:
        clients.discard(websocket)


if __name__ == "__main__":
    log(f"Phonebox-Server {VERSION} laeuft auf Port {PORT}" + (" (Testmodus)" if TEST else ""))
    # log_config=None, damit der Server auch ohne Konsolenfenster (pythonw) laeuft
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None)
