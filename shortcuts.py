"""Shortcut-Tasten: Programme starten oder Tastenkuerzel am PC senden.

Die Liste steht in shortcuts.json am PC. Das iPhone schickt nur die Nummer eines
Eintrags, nie einen freien Befehl. Beispiele:
  { "name": "Rechner",  "icon": "🧮", "programm": "calc.exe" }
  { "name": "Desktop",  "icon": "🖥️", "tasten": "win+d" }
  { "name": "Webseite", "icon": "🌐", "programm": "https://example.com" }
  { "name": "Sperren",  "icon": "🔒", "aktion": "sperren" }
  { "name": "Aus",      "icon": "⏻",  "aktion": "herunterfahren", "frage": "PC wirklich herunterfahren?" }

Aktionen (fest eingebaut): sperren, herunterfahren, herunterfahren_stoppen.
Mit "bestaetigen": true verlangt jeder Eintrag eine Rueckfrage; "herunterfahren" tut das immer.
Hinweis: Win+L laesst sich von Windows aus nicht simulieren, darum gibt es die Aktion "sperren".
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
AKTIONEN = {"sperren", "herunterfahren", "herunterfahren_stoppen"}
BESTAETIGEN_PFLICHT = {"herunterfahren"}
HERUNTERFAHREN_SEKUNDEN = 15  # so lange kann man noch mit "herunterfahren_stoppen" abbrechen
KEIN_FENSTER = 0x08000000  # CREATE_NO_WINDOW: kein aufblitzendes Konsolenfenster
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
            and (
                isinstance(eintrag.get("programm"), str)
                or isinstance(eintrag.get("tasten"), str)
                or eintrag.get("aktion") in AKTIONEN
            )
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


def braucht_bestaetigung(eintrag):
    return bool(eintrag.get("bestaetigen")) or eintrag.get("aktion") in BESTAETIGEN_PFLICHT


def frage(eintrag):
    return eintrag.get("frage") or f"\u201e{eintrag['name']}\u201c wirklich ausf\u00fchren?"


def meldung(eintrag):
    """Text, den das iPhone nach dem Ausloesen kurz zeigt."""
    if eintrag.get("aktion") == "herunterfahren":
        return f"PC f\u00e4hrt in {HERUNTERFAHREN_SEKUNDEN} Sekunden herunter. Zum Abbrechen: Herunterfahren stoppen"
    return f"{eintrag['name']} ausgel\u00f6st"


def shutdown_befehl():
    return [
        "shutdown", "/s", "/t", str(HERUNTERFAHREN_SEKUNDEN), "/c",
        "Phonebox: Der PC faehrt gleich herunter. Abbrechen mit: shutdown /a",
    ]


def _aktion(name):
    if sys.platform != "win32":
        raise RuntimeError("Diese Aktion gibt es nur unter Windows")
    if name == "sperren":
        import ctypes

        if not ctypes.windll.user32.LockWorkStation():
            raise OSError("LockWorkStation ist fehlgeschlagen")
    elif name == "herunterfahren":
        subprocess.Popen(shutdown_befehl(), creationflags=KEIN_FENSTER)
    elif name == "herunterfahren_stoppen":
        # Meldet einen Fehler, wenn gar nichts lief. Das ist in Ordnung.
        subprocess.run(["shutdown", "/a"], creationflags=KEIN_FENSTER, capture_output=True)


def ausfuehren(eintrag):
    if "aktion" in eintrag:
        _aktion(eintrag["aktion"])
    elif "programm" in eintrag:
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
