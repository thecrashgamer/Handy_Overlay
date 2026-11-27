"""Bilder als Symbole fuer Shortcuts: strenge Pruefung und sichere Ablage.

Der Browser wandelt jedes Bild (PNG, JPG, SVG, WebP, GIF ...) in ein kleines PNG um. Der Server nimmt trotzdem NUR echte,
vollstaendig gueltige PNG-Dateien an: Er prueft die Kennung, jeden Abschnitt samt Pruefsumme, die Groesse und dass nach dem
Bildende nichts mehr kommt. Gespeichert wird unter einem Namen, der aus dem Inhalt berechnet wird (nie aus dem
Dateinamen des Benutzers), darum sind Pfad-Tricks nicht moeglich.
"""
import hashlib
import os
import re
import struct
import time
import zlib
from pathlib import Path

PNG_KOPF = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 200_000  # ein 128x128-PNG hat meist unter 30 KB
MAX_KANTE = 512
MAX_DATEIEN = 200
MAX_GESAMT = 30 * 1024 * 1024
NAME_MUSTER = re.compile(r"^[0-9a-f]{16}\.png$")


class IconFehler(Exception):
    pass


def name_gueltig(name):
    return isinstance(name, str) and NAME_MUSTER.match(name) is not None


def pruefen_png(daten):
    """Gibt (Breite, Hoehe) zurueck oder wirft IconFehler. Liest jeden Abschnitt und prueft die Pruefsumme."""
    if not isinstance(daten, (bytes, bytearray)):
        raise IconFehler("Das ist kein Bild.")
    daten = bytes(daten)
    if len(daten) > MAX_BYTES:
        raise IconFehler("Das Bild ist zu gross.")
    if len(daten) < 67 or not daten.startswith(PNG_KOPF):
        raise IconFehler("Das ist keine gueltige PNG-Datei.")
    pos, erstes, idat, breite, hoehe = len(PNG_KOPF), True, False, 0, 0
    while pos < len(daten):
        if pos + 12 > len(daten):
            raise IconFehler("Die PNG-Datei ist abgeschnitten.")
        laenge, typ = struct.unpack(">I4s", daten[pos:pos + 8])
        ende = pos + 8 + laenge + 4
        if ende > len(daten):
            raise IconFehler("Die PNG-Datei ist abgeschnitten.")
        inhalt = daten[pos + 8:pos + 8 + laenge]
        (crc,) = struct.unpack(">I", daten[ende - 4:ende])
        if zlib.crc32(typ + inhalt) & 0xFFFFFFFF != crc:
            raise IconFehler("Die PNG-Datei ist beschaedigt.")
        if erstes:
            if typ != b"IHDR" or laenge != 13:
                raise IconFehler("Die PNG-Datei ist ungueltig.")
            breite, hoehe = struct.unpack(">II", inhalt[:8])
            if not (1 <= breite <= MAX_KANTE and 1 <= hoehe <= MAX_KANTE):
                raise IconFehler(f"Das Bild darf hoechstens {MAX_KANTE} x {MAX_KANTE} Pixel gross sein.")
            erstes = False
        elif typ == b"IDAT":
            idat = True
        elif typ == b"IEND":
            if ende != len(daten):
                raise IconFehler("Nach dem Bild folgen unerwartete Daten.")
            if not idat:
                raise IconFehler("Die PNG-Datei enthaelt kein Bild.")
            return breite, hoehe
        pos = ende
    raise IconFehler("Die PNG-Datei ist unvollstaendig.")


def _dateien(ordner):
    ordner = Path(ordner)
    return [p for p in ordner.iterdir() if p.is_file() and name_gueltig(p.name)] if ordner.exists() else []


def speichern(ordner, daten):
    """Prueft und legt das Bild ab. Gibt den Dateinamen zurueck (gleiches Bild = gleicher Name)."""
    pruefen_png(daten)
    name = hashlib.sha256(daten).hexdigest()[:16] + ".png"
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / name
    if not ziel.exists():
        vorhanden = _dateien(ordner)
        if len(vorhanden) >= MAX_DATEIEN or sum(p.stat().st_size for p in vorhanden) + len(daten) > MAX_GESAMT:
            raise IconFehler("Es sind schon zu viele Bilder gespeichert. Loesche ungenutzte Shortcuts mit Bild und versuche es erneut.")
        hilfe = ordner / (name + ".neu")
        hilfe.write_bytes(daten)
        os.replace(hilfe, ziel)
    return name


def laden(ordner, name):
    """Die Bytes eines gespeicherten Bildes oder None. Nur gueltige Namen, nie ein Pfad."""
    if not name_gueltig(name):
        return None
    pfad = Path(ordner) / name
    try:
        return pfad.read_bytes() if pfad.is_file() else None
    except OSError:
        return None


def existiert(ordner, name):
    return name_gueltig(name) and (Path(ordner) / name).is_file()


def aufraeumen(ordner, benutzt, min_alter=86400, jetzt=None):
    """Loescht Bilder, die kein Shortcut mehr braucht und die aelter als min_alter Sekunden sind
    (frisch hochgeladene, noch nicht gespeicherte Bilder bleiben). Gibt die Anzahl zurueck."""
    jetzt = time.time() if jetzt is None else jetzt
    weg = 0
    for p in _dateien(ordner):
        if p.name not in benutzt and jetzt - p.stat().st_mtime > min_alter:
            try:
                p.unlink()
                weg += 1
            except OSError:
                pass
    return weg
