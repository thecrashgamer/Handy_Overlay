"""Shortcut-Tasten: Programme starten oder Tastenkuerzel am PC senden.

Die Liste steht in shortcuts.json am PC. Das iPhone schickt nur die Nummer eines
Eintrags, nie einen freien Befehl. Beispiele:
  { "name": "Rechner",  "icon": "🧮", "programm": "calc.exe" }
  { "name": "Desktop",  "icon": "🖥️", "tasten": "win+d" }
  { "name": "Webseite", "icon": "🌐", "programm": "https://example.com" }
  { "name": "Sperren",  "icon": "🔒", "aktion": "sperren" }
  { "name": "Aus",      "icon": "⏻",  "aktion": "herunterfahren", "frage": "PC wirklich herunterfahren?" }

Aktionen (fest eingebaut): sperren, ruhemodus (Energiesparmodus), herunterfahren, herunterfahren_stoppen.
Mit "bestaetigen": true verlangt jeder Eintrag eine Rueckfrage; "herunterfahren" tut das immer.
Hinweis: Win+L laesst sich von Windows aus nicht simulieren, darum gibt es die Aktion "sperren".
"""
import json
import os
import re
import shutil
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
AKTIONEN = {"sperren", "ruhemodus", "herunterfahren", "herunterfahren_stoppen"}
BESTAETIGEN_PFLICHT = {"herunterfahren"}
ADMIN_AKTIONEN = {"herunterfahren", "herunterfahren_stoppen"}  # immer nur fuer Administratoren
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


MAX_SHORTCUTS = 24
AKTION_NAMEN = {
    "sperren": "PC sperren",
    "ruhemodus": "PC in den Ruhemodus schicken (Handy kann ihn nicht wecken)",
    "herunterfahren": "PC herunterfahren (fragt immer nach)",
    "herunterfahren_stoppen": "Herunterfahren abbrechen",
}


def _ohne_steuerzeichen(text):
    return all(ord(z) >= 32 for z in text)


def pruefen(roh):
    """Prueft einen Eintrag aus dem Admin-Bereich streng und gibt die saubere Form zurueck.
    Wirft ValueError mit einem Text fuer den Benutzer."""
    if not isinstance(roh, dict):
        raise ValueError("Ungueltiger Eintrag.")
    name = str(roh.get("name", "")).strip()
    if not 1 <= len(name) <= 30 or not _ohne_steuerzeichen(name):
        raise ValueError("Der Name braucht 1 bis 30 Zeichen.")
    icon = str(roh.get("icon", "")).strip()
    if len(icon) > 8 or not _ohne_steuerzeichen(icon):
        raise ValueError("Das Symbol ist zu lang, ein Emoji reicht.")
    bild = str(roh.get("bild", "") or "").strip()
    if bild and not re.match(r"^[0-9a-f]{16}\.png$", bild):
        raise ValueError("Das Bild ist ungueltig.")
    arten = [k for k in ("programm", "tasten", "aktion") if roh.get(k) not in (None, "")]
    if len(arten) != 1:
        raise ValueError("Waehle genau eins: Programm, Tastenkuerzel oder Aktion.")
    eintrag = {"name": name}
    if icon:
        eintrag["icon"] = icon
    if bild:
        eintrag["bild"] = bild  # Bild gewinnt gegen das Emoji
    art = arten[0]
    if art == "programm":
        programm = str(roh["programm"]).strip()
        if not programm or len(programm) > 300 or not _ohne_steuerzeichen(programm):
            raise ValueError("Das Programm fehlt oder ist ungueltig.")
        eintrag["programm"] = programm
        argumente = roh.get("argumente") or []
        if not isinstance(argumente, list) or len(argumente) > 10 or not all(
            isinstance(a, str) and len(a) <= 200 and _ohne_steuerzeichen(a) for a in argumente
        ):
            raise ValueError("Die Argumente sind ungueltig (hoechstens 10, je 200 Zeichen).")
        if argumente:
            eintrag["argumente"] = argumente
    elif art == "tasten":
        text = str(roh["tasten"]).lower().replace(" ", "")
        try:
            tasten_parsen(text)
        except ValueError as fehler:
            raise ValueError(f"Tastenkuerzel ungueltig: {fehler}")
        eintrag["tasten"] = text
    else:
        if roh["aktion"] not in AKTIONEN:
            raise ValueError("Unbekannte Aktion.")
        eintrag["aktion"] = roh["aktion"]
    if roh.get("bestaetigen") is True:
        eintrag["bestaetigen"] = True
    if roh.get("nur_admin") is True and eintrag.get("aktion") not in ADMIN_AKTIONEN:
        eintrag["nur_admin"] = True  # bei Herunterfahren ueberfluessig, das gilt immer
    frage_text = str(roh.get("frage", "")).strip()
    if frage_text:
        if len(frage_text) > 100 or not _ohne_steuerzeichen(frage_text):
            raise ValueError("Die Rueckfrage ist zu lang (hoechstens 100 Zeichen).")
        eintrag["frage"] = frage_text
    return eintrag


def pruefen_liste(roh):
    if not isinstance(roh, list):
        raise ValueError("Die Liste ist ungueltig.")
    if len(roh) > MAX_SHORTCUTS:
        raise ValueError(f"Es sind hoechstens {MAX_SHORTCUTS} Shortcuts moeglich.")
    liste, namen = [], set()
    for nr, e in enumerate(roh, 1):
        try:
            eintrag = pruefen(e)
        except ValueError as fehler:
            bezeichnung = str(e.get("name", "")).strip() if isinstance(e, dict) else ""
            raise ValueError(f"Nr. {nr}{' (' + bezeichnung + ')' if bezeichnung else ''}: {fehler}")
        if eintrag["name"].lower() in namen:
            raise ValueError(f"Nr. {nr}: Der Name \u201e{eintrag['name']}\u201c kommt doppelt vor.")
        namen.add(eintrag["name"].lower())
        liste.append(eintrag)
    return liste


def speichern(pfad, liste):
    """Schreibt die Liste sicher: erst in eine Hilfsdatei, dann austauschen. Die alte Fassung bleibt als .bak."""
    pfad = str(pfad)
    os.makedirs(os.path.dirname(os.path.abspath(pfad)), exist_ok=True)
    hilfe = pfad + ".neu"
    with open(hilfe, "w", encoding="utf-8") as datei:
        json.dump(liste, datei, ensure_ascii=False, indent=2)
        datei.write("\n")
        datei.flush()
        os.fsync(datei.fileno())
    if os.path.exists(pfad):
        shutil.copyfile(pfad, pfad + ".bak")
    os.replace(hilfe, pfad)


def braucht_admin(eintrag):
    """Darf nur ein Administrator ausloesen?"""
    return bool(eintrag.get("nur_admin")) or eintrag.get("aktion") in ADMIN_AKTIONEN


def darf_ausloesen(eintrag, rechte):
    """rechte = Ergebnis von konten.rechte(...)."""
    if rechte.get("admin"):
        return True
    return bool(rechte.get("shortcuts")) and not braucht_admin(eintrag)


def braucht_bestaetigung(eintrag):
    return bool(eintrag.get("bestaetigen")) or eintrag.get("aktion") in BESTAETIGEN_PFLICHT


def frage(eintrag):
    return eintrag.get("frage") or f"\u201e{eintrag['name']}\u201c wirklich ausf\u00fchren?"


def meldung(eintrag):
    """Text, den das iPhone nach dem Ausloesen kurz zeigt."""
    if eintrag.get("aktion") == "herunterfahren":
        return f"PC f\u00e4hrt in {HERUNTERFAHREN_SEKUNDEN} Sekunden herunter. Zum Abbrechen: Herunterfahren stoppen"
    if eintrag.get("aktion") == "ruhemodus":
        return "PC geht in den Ruhemodus"
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
    elif name == "ruhemodus":
        import ctypes

        # SetSuspendState(Ruhezustand=0, erzwingen=0, Aufwachen=0): Energiesparmodus (Standby), kein Ruhezustand
        ctypes.windll.powrprof.SetSuspendState(0, 0, 0)
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
