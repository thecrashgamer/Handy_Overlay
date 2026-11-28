"""Traegt die Phonebox-Hooks sicher in die settings.json von Gemini CLI ein (und wieder aus).

Aufbau laut Dokumentation (github.com/google-gemini/gemini-cli, docs/hooks): "hooks" -> Ereignis -> Liste von Gruppen
(optional "matcher") -> "hooks": Liste von Handlern. Gemini CLI kennt nur Handler vom Typ "command" (keine http-Hooks) und
rechnet "timeout" in Millisekunden. Der Handler startet hooks/gemini_status.py, das das Ereignis an die Phonebox weitergibt.
Es werden nur Eintraege angefasst, die von der Phonebox stammen. Alles andere bleibt, wie es ist. Ist die Datei kein
gueltiges JSON, wird sie nicht veraendert. Vor jeder Aenderung entsteht eine Sicherung (gleiche Regeln wie bei Claude).
"""
import os
import shlex
import subprocess
from pathlib import Path

import claude_einrichten as ce

EREIGNISSE = ("BeforeAgent", "BeforeTool", "Notification", "AfterAgent")
SKRIPT_NAME = "gemini_status.py"
KURZ_MS = 5000
LANG_MS = 600_000  # AfterAgent darf lange offen bleiben: dort wartet die Phonebox auf eine Anweisung vom Handy
EinrichtungsFehler = ce.EinrichtungsFehler


def settings_pfad():
    return Path.home() / ".gemini" / "settings.json"


def befehl(python_exe, skript):
    """Die Befehlszeile fuer den Hook. Anfuehrungszeichen nur, wo Leerzeichen im Pfad sind (das geht in cmd, PowerShell und bash)."""
    teile = [ce.python_ohne_fenster_problem(python_exe), str(skript)]
    return subprocess.list2cmdline(teile) if os.name == "nt" else shlex.join(teile)


def ist_unser(handler):
    return isinstance(handler, dict) and handler.get("type", "command") == "command" and SKRIPT_NAME in str(handler.get("command", ""))


def hooks_bauen(python_exe, skript):
    kommando = befehl(python_exe, skript)
    return {e: {"hooks": [{"type": "command", "name": "phonebox", "command": kommando,
                           "timeout": LANG_MS if e == "AfterAgent" else KURZ_MS}]} for e in EREIGNISSE}


def einrichten(skript, pfad=None, python_exe=None):
    pfad = Path(pfad or settings_pfad())
    daten = ce.laden(pfad)
    hooks = daten.get("hooks", {})
    if not isinstance(hooks, dict):
        raise EinrichtungsFehler('In der Datei ist "hooks" kein Objekt. Ich aendere sie nicht.')
    neu = hooks_bauen(python_exe, skript)
    for ereignis in EREIGNISSE:
        vorhanden = hooks.get(ereignis, [])
        if not isinstance(vorhanden, list):
            raise EinrichtungsFehler(f'In der Datei ist "{ereignis}" keine Liste. Ich aendere sie nicht.')
        hooks[ereignis] = ce._ohne_unsere(vorhanden, ist_unser) + [neu[ereignis]]
    daten["hooks"] = hooks
    sicherung = ce._schreiben(pfad, daten)
    return {"pfad": str(pfad), "sicherung": str(sicherung) if sicherung else None, "modus": "python"}


def _zaehlen(gruppen):
    return sum(len(g.get("hooks", [])) for g in gruppen if isinstance(g, dict) and isinstance(g.get("hooks"), list))


def entfernen(pfad=None):
    pfad = Path(pfad or settings_pfad())
    if not pfad.exists():
        return {"pfad": str(pfad), "sicherung": None, "entfernt": 0}
    daten = ce.laden(pfad)
    hooks = daten.get("hooks")
    entfernt = 0
    if isinstance(hooks, dict):
        for ereignis in list(hooks):
            if isinstance(hooks[ereignis], list):
                vorher = _zaehlen(hooks[ereignis])
                hooks[ereignis] = ce._ohne_unsere(hooks[ereignis], ist_unser)
                entfernt += vorher - _zaehlen(hooks[ereignis])
                if not hooks[ereignis]:
                    del hooks[ereignis]
        if not hooks:
            del daten["hooks"]
    sicherung = ce._schreiben(pfad, daten) if entfernt else None
    return {"pfad": str(pfad), "sicherung": str(sicherung) if sicherung else None, "entfernt": entfernt}


def pruefen(pfad=None):
    """Was steht aktuell in der Datei? Gleiche Form wie claude_einrichten.pruefen, damit die Oberflaeche beide gleich anzeigt."""
    pfad = Path(pfad or settings_pfad())
    erg = {"pfad": str(pfad), "vorhanden": pfad.exists(), "gueltig": True, "fehler": None, "modus": None,
           "ereignisse": [], "fehlend": list(EREIGNISSE), "url_passt": None, "python_ok": None, "hinweise": []}
    try:
        daten = ce.laden(pfad)
    except EinrichtungsFehler as f:
        erg.update(gueltig=False, fehler=str(f))
        return erg
    hooks = daten.get("hooks") if isinstance(daten.get("hooks"), dict) else {}
    skript_ok = []
    for ereignis in EREIGNISSE:
        gruppen = hooks.get(ereignis) if isinstance(hooks.get(ereignis), list) else []
        eigene = [h for g in gruppen if isinstance(g, dict) and isinstance(g.get("hooks"), list) for h in g["hooks"] if ist_unser(h)]
        if eigene:
            erg["ereignisse"].append(ereignis)
        for h in eigene:
            try:
                teile = shlex.split(str(h.get("command", "")), posix=os.name != "nt")
            except ValueError:
                teile = []
            skript_ok.append(bool(teile) and all(Path(t.strip('"')).is_file() for t in teile))
    erg["fehlend"] = [e for e in EREIGNISSE if e not in erg["ereignisse"]]
    erg["modus"] = "python" if erg["ereignisse"] else None
    erg["python_ok"] = all(skript_ok) if skript_ok else None
    hc = daten.get("hooksConfig")
    if isinstance(hc, dict) and hc.get("enabled") is False:
        erg["hinweise"].append('In der Datei steht "hooksConfig.enabled": false. Damit laufen in Gemini CLI keine Hooks.')
    if erg["ereignisse"] and erg["python_ok"] is False:
        erg["hinweise"].append("Das Python-Programm oder das Skript in den Hooks gibt es nicht mehr. Richte sie neu ein.")
    return erg
