"""Shortcut-Tasten: Programme starten oder Tastenkuerzel am PC senden.

Die Liste steht in shortcuts.json am PC. Das iPhone schickt nur die Nummer eines
Eintrags, nie einen freien Befehl. Beispiele:
  { "name": "Rechner",  "icon": "🧮", "programm": "calc.exe" }
  { "name": "Desktop",  "icon": "🖥️", "tasten": "win+d" }
  { "name": "Webseite", "icon": "🌐", "programm": "https://example.com" }
"""
import json
import os
import subprocess
import sys
import time

# Windows-Tastencodes (virtual key codes)
TASTEN = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "esc": 0x1B, "enter": 0x0D, "tab": 0x09, "space": 0x20, "backspace": 0x08,
    "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "stumm": 0xAD, "leiser": 0xAE, "lauter": 0xAF,
    "naechster": 0xB0, "vorheriger": 0xB1, "playpause": 0xB3,
}
for _n in range(1, 13):
    TASTEN[f"f{_n}"] = 0x70 + _n - 1
ERWEITERT = {0x2E, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x5B}


def laden(pfad):
    """Liest shortcuts.json. Kaputte Eintraege werden uebersprungen."""
    try:
        with open(pfad, encoding="utf-8") as datei:
            roh = json.load(datei)
    except FileNotFoundError:
        return []
    except Exception as fehler:
        print("shortcuts.json konnte nicht gelesen werden:", fehler)
        return []
    liste = []
    for eintrag in roh if isinstance(roh, list) else []:
        if (
            isinstance(eintrag, dict)
            and isinstance(eintrag.get("name"), str)
            and (isinstance(eintrag.get("programm"), str) or isinstance(eintrag.get("tasten"), str))
        ):
            liste.append(eintrag)
    return liste


def tasten_parsen(text):
    """'ctrl+shift+esc' -> Liste von Tastencodes. Wirft ValueError bei Unbekanntem."""
    codes = []
    for teil in text.lower().replace(" ", "").split("+"):
        if teil in TASTEN:
            codes.append(TASTEN[teil])
        elif len(teil) == 1 and teil.isalnum() and teil.isascii():
            codes.append(ord(teil.upper()))
        else:
            raise ValueError(f"Unbekannte Taste: {teil!r}")
    if not codes:
        raise ValueError("Keine Tasten angegeben")
    return codes


def ausfuehren(eintrag):
    if "programm" in eintrag:
        _programm_starten(eintrag["programm"], eintrag.get("argumente", []))
    else:
        _tasten_senden(tasten_parsen(eintrag["tasten"]))


def _programm_starten(programm, argumente):
    if sys.platform == "win32" and not argumente:
        os.startfile(programm)  # startet auch Dateien und Webadressen
    else:
        subprocess.Popen([programm, *argumente])


def _tasten_senden(codes):
    if sys.platform != "win32":
        raise RuntimeError("Tastenkuerzel gehen nur unter Windows")
    import ctypes

    keybd_event = ctypes.windll.user32.keybd_event
    for code in codes:  # alle runterdruecken ...
        keybd_event(code, 0, 1 if code in ERWEITERT else 0, 0)
        time.sleep(0.02)
    for code in reversed(codes):  # ... und in umgekehrter Reihenfolge loslassen
        keybd_event(code, 0, (1 if code in ERWEITERT else 0) | 2, 0)
        time.sleep(0.02)
