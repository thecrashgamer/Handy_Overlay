# server.py - Phonebox-Server fuer Spotify
import asyncio
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
)

ORDNER = Path(__file__).parent
app = FastAPI()


async def spotify_finden():
    """Sucht die laufende Spotify-Sitzung in der Windows-Mediensteuerung."""
    manager = await MediaManager.request_async()
    for sitzung in manager.get_sessions():
        if "spotify" in sitzung.source_app_user_model_id.lower():
            return sitzung
    return None


async def status_lesen():
    sitzung = await spotify_finden()
    if sitzung is None:
        return {"spielt": False, "titel": "Spotify ist nicht offen", "kuenstler": ""}
    infos = await sitzung.try_get_media_properties_async()
    spielt = sitzung.get_playback_info().playback_status == Status.PLAYING
    return {"spielt": spielt, "titel": infos.title, "kuenstler": infos.artist}


@app.get("/")
async def startseite():
    return FileResponse(ORDNER / "index.html")


@app.websocket("/ws")
async def verbindung(websocket: WebSocket):
    await websocket.accept()

    async def status_senden():
        letzter = None
        while True:
            aktuell = await status_lesen()
            if aktuell != letzter:
                await websocket.send_json(aktuell)
                letzter = aktuell
            await asyncio.sleep(1)

    sender = asyncio.create_task(status_senden())
    try:
        while True:
            befehl = await websocket.receive_text()
            sitzung = await spotify_finden()
            if sitzung is None:
                continue
            if befehl == "playpause":
                await sitzung.try_toggle_play_pause_async()
            elif befehl == "weiter":
                await sitzung.try_skip_next_async()
            elif befehl == "zurueck":
                await sitzung.try_skip_previous_async()
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()


if __name__ == "__main__":
    print("Phonebox-Server laeuft auf Port 8000")
    # log_config=None, damit der Server auch ohne Konsolenfenster (pythonw) laeuft
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
