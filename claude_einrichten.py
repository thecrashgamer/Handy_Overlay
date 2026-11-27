"""Traegt die Phonebox-Hooks sicher in die settings.json von Claude Code ein (und wieder aus).

Aufbau laut Dokumentation (code.claude.com/docs/en/hooks): "hooks" -> Ereignis -> Liste von Gruppen (optional "matcher")
-> "hooks": Liste von Handlern. Zwei Arten von Handlern stehen zur Wahl:
  http    Claude Code schickt das Ereignis direkt an den Server. Kein Python, kein PATH, keine Shell. (Standard)
  python  Claude Code startet python.exe direkt ("args": keine Shell, keine Probleme mit Pfaden unter Windows).
Es werden nur Eintraege angefasst, die von der Phonebox stammen. Alles andere in der Datei bleibt, wie es ist. Ist die Datei
kein gueltiges JSON, wird sie nicht veraendert. Vor jeder Aenderung entsteht eine Sicherung.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

EREIGNISSE = ("UserPromptSubmit", "PreToolUse", "PermissionRequest", "Notification", "Stop")
BENACHRICHTIGUNG_MATCHER = "permission_prompt|elicitation_dialog|agent_needs_input"
SICHERUNGEN_BEHALTEN = 3


class EinrichtungsFehler(Exception):
    pass


def settings_pfad():
    basis = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(basis) if basis else Path.home() / ".claude") / "settings.json"


def hook_url(port):
    return f"http://127.0.0.1:{int(port)}/claude-hook"  # 127.0.0.1 statt localhost: kein Ausweichen auf IPv6


def python_ohne_fenster_problem(exe=None):
    """python.exe, nie pythonw.exe: ein Hook muss das Ereignis von stdin lesen koennen."""
    pfad = Path(exe or sys.executable)
    if pfad.name.lower() == "pythonw.exe" and pfad.with_name("python.exe").exists():
        return str(pfad.with_name("python.exe"))
    return str(pfad)


def ist_unser(handler):
    """Gehoert dieser Handler zur Phonebox? (neue http- und python-Eintraege und die aelteren Shell-Eintraege)"""
    if not isinstance(handler, dict):
        return False
    if handler.get("type") == "http":
        return "/claude-hook" in str(handler.get("url", ""))
    if handler.get("type", "command") == "command":
        teile = [str(handler.get("command", ""))] + [str(a) for a in handler.get("args") or []]
        return any("claude_status.py" in t for t in teile)
    return False


def hooks_bauen(modus, port, python_exe=None, skript=None):
    """Die Eintraege, die die Phonebox braucht: {Ereignis: Gruppe}."""
    if modus == "http":
        def handler(ereignis):
            return {"type": "http", "url": hook_url(port), "timeout": 3}
    elif modus == "python":
        exe = python_ohne_fenster_problem(python_exe)
        skript = str(skript)

        def handler(ereignis):
            h = {"type": "command", "command": exe, "args": [skript], "timeout": 10}
            if ereignis == "PreToolUse":
                h["async"] = True  # das Melden darf Claude bei jedem Werkzeug nicht bremsen
            return h
    else:
        raise EinrichtungsFehler("Unbekannte Art der Einrichtung.")
    gruppen = {}
    for ereignis in EREIGNISSE:
        gruppe = {"hooks": [handler(ereignis)]}
        if ereignis == "Notification":
            gruppe = {"matcher": BENACHRICHTIGUNG_MATCHER, **gruppe}
        gruppen[ereignis] = gruppe
    return gruppen


def laden(pfad):
    """Die Einstellungen als dict. Fehlt die Datei: leer. Ist sie kaputt: Fehler (und nichts wird angefasst)."""
    pfad = Path(pfad)
    if not pfad.exists():
        return {}
    try:
        text = pfad.read_text(encoding="utf-8-sig")
        daten = json.loads(text) if text.strip() else {}
    except (OSError, ValueError) as fehler:
        raise EinrichtungsFehler(f"Die Datei {pfad} ist kein gueltiges JSON ({fehler}). Ich aendere sie nicht. Bitte erst reparieren.")
    if not isinstance(daten, dict):
        raise EinrichtungsFehler(f"Die Datei {pfad} hat ein unerwartetes Format. Ich aendere sie nicht.")
    return daten


def _ohne_unsere(gruppen):
    sauber = []
    for g in gruppen:
        if isinstance(g, dict) and isinstance(g.get("hooks"), list):
            rest = [h for h in g["hooks"] if not ist_unser(h)]
            if rest:
                sauber.append({**g, "hooks": rest})
        else:
            sauber.append(g)  # Unbekanntes bleibt unberuehrt
    return sauber


def _schreiben(pfad, daten):
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    sicherung = None
    if pfad.exists():
        sicherung = pfad.with_name(f"{pfad.name}.phonebox-sicherung-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(pfad, sicherung)
        alle = sorted(pfad.parent.glob(pfad.name + ".phonebox-sicherung-*"))
        for alt in alle[:-SICHERUNGEN_BEHALTEN]:
            try:
                alt.unlink()
            except OSError:
                pass
    hilfe = pfad.with_name(pfad.name + ".neu")
    hilfe.write_text(json.dumps(daten, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(hilfe, pfad)
    return sicherung


def einrichten(modus, port, pfad=None, python_exe=None, skript=None):
    pfad = Path(pfad or settings_pfad())
    daten = laden(pfad)
    hooks = daten.get("hooks", {})
    if not isinstance(hooks, dict):
        raise EinrichtungsFehler('In der Datei ist "hooks" kein Objekt. Ich aendere sie nicht.')
    neu = hooks_bauen(modus, port, python_exe, skript)
    for ereignis in EREIGNISSE:
        vorhanden = hooks.get(ereignis, [])
        if not isinstance(vorhanden, list):
            raise EinrichtungsFehler(f'In der Datei ist "{ereignis}" keine Liste. Ich aendere sie nicht.')
        hooks[ereignis] = _ohne_unsere(vorhanden) + [neu[ereignis]]
    # Eintraege in anderen Ereignissen (z. B. aus aelteren Versionen) aufraeumen
    for ereignis in list(hooks):
        if ereignis not in EREIGNISSE and isinstance(hooks[ereignis], list):
            hooks[ereignis] = _ohne_unsere(hooks[ereignis])
            if not hooks[ereignis]:
                del hooks[ereignis]
    daten["hooks"] = hooks
    sicherung = _schreiben(pfad, daten)
    return {"pfad": str(pfad), "sicherung": str(sicherung) if sicherung else None, "modus": modus}


def entfernen(pfad=None):
    pfad = Path(pfad or settings_pfad())
    if not pfad.exists():
        return {"pfad": str(pfad), "sicherung": None, "entfernt": 0}
    daten = laden(pfad)
    hooks = daten.get("hooks")
    entfernt = 0
    if isinstance(hooks, dict):
        for ereignis in list(hooks):
            if isinstance(hooks[ereignis], list):
                vorher = sum(len(g.get("hooks", [])) for g in hooks[ereignis] if isinstance(g, dict) and isinstance(g.get("hooks"), list))
                hooks[ereignis] = _ohne_unsere(hooks[ereignis])
                nachher = sum(len(g.get("hooks", [])) for g in hooks[ereignis] if isinstance(g, dict) and isinstance(g.get("hooks"), list))
                entfernt += vorher - nachher
                if not hooks[ereignis]:
                    del hooks[ereignis]
        if not hooks:
            del daten["hooks"]
    sicherung = _schreiben(pfad, daten) if entfernt else None
    return {"pfad": str(pfad), "sicherung": str(sicherung) if sicherung else None, "entfernt": entfernt}


def pruefen(port, pfad=None):
    """Was steht aktuell in der Datei? Fuer die Diagnose im Admin-Bereich."""
    pfad = Path(pfad or settings_pfad())
    erg = {"pfad": str(pfad), "vorhanden": pfad.exists(), "gueltig": True, "fehler": None, "modus": None,
           "ereignisse": [], "fehlend": list(EREIGNISSE), "url_passt": None, "python_ok": None, "hinweise": []}
    try:
        daten = laden(pfad)
    except EinrichtungsFehler as f:
        erg.update(gueltig=False, fehler=str(f))
        return erg
    hooks = daten.get("hooks") if isinstance(daten.get("hooks"), dict) else {}
    arten, urls_ok, python_ok = set(), [], []
    for ereignis in EREIGNISSE:
        gruppen = hooks.get(ereignis) if isinstance(hooks.get(ereignis), list) else []
        eigene = [h for g in gruppen if isinstance(g, dict) and isinstance(g.get("hooks"), list) for h in g["hooks"] if ist_unser(h)]
        if eigene:
            erg["ereignisse"].append(ereignis)
        for h in eigene:
            if h.get("type") == "http":
                arten.add("http")
                urls_ok.append(h.get("url") == hook_url(port))
            else:
                arten.add("python")
                python_ok.append(Path(str(h.get("command", ""))).is_file() and all(Path(str(a)).is_file() for a in h.get("args") or []))
    erg["fehlend"] = [e for e in EREIGNISSE if e not in erg["ereignisse"]]
    erg["modus"] = None if not arten else (next(iter(arten)) if len(arten) == 1 else "gemischt")
    erg["url_passt"] = all(urls_ok) if urls_ok else None
    erg["python_ok"] = all(python_ok) if python_ok else None
    if daten.get("disableAllHooks") is True:
        erg["hinweise"].append('In der Datei steht "disableAllHooks": true. Damit laufen keine Hooks.')
    if daten.get("allowManagedHooksOnly") is True:
        erg["hinweise"].append('In der Datei steht "allowManagedHooksOnly": true. Damit laufen nur Hooks der Organisation.')
    if erg["ereignisse"] and erg["url_passt"] is False:
        erg["hinweise"].append("Die Adresse in den Hooks passt nicht zum Port dieses Servers. Richte sie neu ein.")
    if erg["ereignisse"] and erg["python_ok"] is False:
        erg["hinweise"].append("Das Python-Programm oder das Skript in den Hooks gibt es nicht mehr. Richte sie neu ein.")
    return erg
