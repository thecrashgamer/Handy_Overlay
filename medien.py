"""Medien-Anbindung der Phonebox.

WindowsMedien spricht mit der echten Windows-Mediensteuerung (Spotify) und
der Windows-Lautstaerke. TestMedien liefert Fake-Daten, damit sich Server und
Oberflaeche auch ohne Windows und Spotify testen lassen (PHONEBOX_TEST=1).
"""
import asyncio
import hashlib


def erstellen(test: bool):
    return TestMedien() if test else WindowsMedien()


class TestMedien:
    LIEDER = [
        ("Testlied Eins", "Test-Band", "#1db954"),
        ("Zweites Lied", "Die Pruefer", "#e91e63"),
        ("Nummer Drei", "DJ Mock", "#3f51b5"),
    ]

    def __init__(self):
        self.nr = 0
        self.spielt = True
        self.laut = 50

    async def status(self):
        titel, kuenstler, _ = self.LIEDER[self.nr]
        return {
            "spielt": self.spielt,
            "titel": titel,
            "kuenstler": kuenstler,
            "cover": f"t{self.nr}",
            "laut": self.laut,
        }

    async def befehl(self, befehl: str):
        if befehl == "playpause":
            self.spielt = not self.spielt
        elif befehl == "weiter":
            self.nr = (self.nr + 1) % len(self.LIEDER)
        elif befehl == "zurueck":
            self.nr = (self.nr - 1) % len(self.LIEDER)
        elif befehl.startswith("laut:"):
            self.laut = _prozent(befehl)

    async def cover(self):
        farbe = self.LIEDER[self.nr][2]
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300">'
            f'<rect width="300" height="300" fill="{farbe}"/>'
            '<circle cx="150" cy="150" r="70" fill="#000" opacity=".35"/></svg>'
        )
        return svg.encode(), "image/svg+xml"


class WindowsMedien:
    def __init__(self):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
        )

        self._MediaManager = MediaManager
        self._Status = Status
        self._cover = None
        self._cover_fuer = None
        self._cover_versuche = 0
        self._cover_task = None
        self._cover_id = ""
        self._laut_fehler_gezeigt = False

    async def _sitzung(self):
        """Sucht die laufende Spotify-Sitzung in der Windows-Mediensteuerung."""
        manager = await self._MediaManager.request_async()
        for sitzung in manager.get_sessions():
            if "spotify" in sitzung.source_app_user_model_id.lower():
                return sitzung
        return None

    async def status(self):
        laut = self._laut_lesen()
        sitzung = await self._sitzung()
        if sitzung is None:
            return {
                "spielt": False,
                "titel": "Spotify ist nicht offen",
                "kuenstler": "",
                "cover": "",
                "laut": laut,
            }
        infos = await sitzung.try_get_media_properties_async()
        spielt = sitzung.get_playback_info().playback_status == self._Status.PLAYING

        schluessel = (infos.title, infos.artist)
        if schluessel != self._cover_fuer:
            self._cover_fuer = schluessel
            self._cover = None
            self._cover_versuche = 0
            if self._cover_task is not None:
                self._cover_task.cancel()
                self._cover_task = None
        # Das Cover laedt im Hintergrund, damit ein haengendes Lesen nie die Steuerung blockiert.
        # Spotify liefert es manchmal erst kurz nach dem Titel nach, daher mehrere Versuche.
        if (
            self._cover is None
            and infos.thumbnail is not None
            and self._cover_versuche < 5
            and (self._cover_task is None or self._cover_task.done())
        ):
            self._cover_versuche += 1
            self._cover_task = asyncio.create_task(self._cover_holen(schluessel, infos.thumbnail))
        self._cover_id = (
            hashlib.md5(repr(schluessel).encode()).hexdigest()[:8] if self._cover else ""
        )
        return {
            "spielt": spielt,
            "titel": infos.title,
            "kuenstler": infos.artist,
            "cover": self._cover_id,
            "laut": laut,
        }

    async def befehl(self, befehl: str):
        if befehl.startswith("laut:"):
            self._laut_setzen(_prozent(befehl))
            return
        sitzung = await self._sitzung()
        if sitzung is None:
            return
        if befehl == "playpause":
            await sitzung.try_toggle_play_pause_async()
        elif befehl == "weiter":
            await sitzung.try_skip_next_async()
        elif befehl == "zurueck":
            await sitzung.try_skip_previous_async()

    async def cover(self):
        if not self._cover:
            return None
        daten = bytes(self._cover)
        art = "image/png" if daten.startswith(b"\x89PNG") else "image/jpeg"
        return daten, art

    async def _cover_holen(self, schluessel, thumbnail):
        try:
            daten = await asyncio.wait_for(self._cover_laden(thumbnail), timeout=5)
        except asyncio.TimeoutError:
            print("Cover: Zeitueberschreitung beim Lesen")
            return
        if daten and schluessel == self._cover_fuer:
            self._cover = daten

    async def _cover_laden(self, thumbnail):
        """Liest das Albumcover aus der Windows-Mediensteuerung."""
        try:
            from winrt.windows.storage.streams import Buffer, DataReader, InputStreamOptions

            strom = await thumbnail.open_read_async()
            groesse = strom.size
            puffer = Buffer(groesse)
            await strom.read_async(puffer, groesse, InputStreamOptions.READ_AHEAD)
            daten = bytearray(puffer.length)
            DataReader.from_buffer(puffer).read_bytes(daten)
            return bytes(daten)
        except Exception as fehler:  # Cover ist nur ein Extra, nie den Server stoppen
            print("Cover konnte nicht gelesen werden:", fehler)
            return None

    def _endpunkt(self):
        """Windows-Lautstaerke (pycaw). Gibt None zurueck, wenn nicht verfuegbar."""
        try:
            from ctypes import POINTER, cast

            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            geraet = AudioUtilities.GetSpeakers()
            if hasattr(geraet, "EndpointVolume"):  # neuere pycaw-Versionen
                return geraet.EndpointVolume
            schnittstelle = geraet.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(schnittstelle, POINTER(IAudioEndpointVolume))
        except Exception as fehler:
            if not self._laut_fehler_gezeigt:  # nur einmal melden, nicht jede Sekunde
                self._laut_fehler_gezeigt = True
                print("Lautstaerke nicht verfuegbar:", repr(fehler))
            return None

    def _laut_lesen(self):
        endpunkt = self._endpunkt()
        if endpunkt is None:
            return None
        return round(endpunkt.GetMasterVolumeLevelScalar() * 100)

    def _laut_setzen(self, prozent: int):
        endpunkt = self._endpunkt()
        if endpunkt is not None:
            endpunkt.SetMasterVolumeLevelScalar(prozent / 100, None)


def _prozent(befehl: str) -> int:
    try:
        return max(0, min(100, int(befehl.split(":", 1)[1])))
    except ValueError:
        return 0
