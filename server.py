# server.py - Phonebox-Server: Spotify, Lautstaerke und Claude-Status
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import medien as medien_modul

ORDNER = Path(__file__).parent
TEST = os.environ.get("PHONEBOX_TEST") == "1"  # Fake-Daten statt Windows/Spotify
PORT = int(os.environ.get("PHONEBOX_PORT", "8000"))

medien = medien_modul.erstellen(TEST)
clients = set()
zustand = {"medien": {}, "claude": {"status": "", "text": ""}}


def nachricht_bauen():
    return json.dumps({**zustand["medien"], "claude": zustand["claude"]})


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
        neu = await medien.status()
    except Exception as fehler:
        neu = {"spielt": False, "titel": "Fehler: " + str(fehler), "kuenstler": "", "cover": "", "laut": None}
    if neu != zustand["medien"]:
        zustand["medien"] = neu
        await an_alle_senden()


async def schleife():
    while True:
        await aktualisieren()
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
    clients.add(websocket)
    await websocket.send_text(nachricht_bauen())
    try:
        while True:
            befehl = await websocket.receive_text()
            await medien.befehl(befehl)
            await asyncio.sleep(0.3)  # Spotify kurz Zeit geben, dann sofort aktualisieren
            await aktualisieren()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)


if __name__ == "__main__":
    print(f"Phonebox-Server laeuft auf Port {PORT}" + (" (Testmodus)" if TEST else ""))
    # log_config=None, damit der Server auch ohne Konsolenfenster (pythonw) laeuft
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None)
