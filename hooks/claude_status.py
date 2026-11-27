"""Meldet an die Phonebox, woran Claude Code gerade arbeitet.

Wird von den Claude-Code-Hooks aufgerufen (Beispiel: settings-beispiel.json). Claude Code
liefert das Ereignis als JSON auf stdin; daraus wird ein kurzer deutscher Satz wie
"Bearbeitet server.py". Es werden nur Dateinamen und Beschreibungen gesendet, nie der
Inhalt von Dateien oder ganze Befehle.

Die Adresse laesst sich mit PHONEBOX_URL aendern. Fehler werden still geschluckt, damit ein
ausgeschalteter Phonebox-Server Claude Code nie ausbremst.
"""
import json
import os
import sys
import urllib.request

URL = os.environ.get("PHONEBOX_URL", "http://localhost:8000/claude")


def kurz(text, laenge=70):
    text = " ".join(str(text).split())
    return text if len(text) <= laenge else text[: laenge - 1] + "\u2026"


def beschreibe(werkzeug, eingabe):
    datei = os.path.basename(eingabe.get("file_path") or eingabe.get("notebook_path") or "")
    if werkzeug == "Read":
        return f"Liest {datei}"
    if werkzeug in ("Edit", "MultiEdit", "NotebookEdit"):
        return f"Bearbeitet {datei}"
    if werkzeug == "Write":
        return f"Schreibt {datei}"
    if werkzeug == "Bash":
        if eingabe.get("description"):
            return kurz(eingabe["description"])
        erstes = str(eingabe.get("command", "")).split()
        return f"F\u00fchrt einen Befehl aus ({erstes[0]})" if erstes else "F\u00fchrt einen Befehl aus"
    if werkzeug in ("Grep", "Glob"):
        return f"Sucht {kurz(eingabe.get('pattern', ''), 40)}"
    if werkzeug in ("WebSearch", "WebFetch"):
        return "Sucht im Web"
    if werkzeug in ("Agent", "Task"):
        return "Startet einen Hilfsagenten"
    if werkzeug.startswith("mcp__"):
        return f"Nutzt {werkzeug.split('__')[-1]}"
    return werkzeug


def lesen():
    try:
        roh = sys.stdin.buffer.read().decode("utf-8", "replace")
        return json.loads(roh) if roh.strip() else {}
    except Exception:
        return {}


def main():
    daten = lesen()
    ereignis = daten.get("hook_event_name", "")
    projekt = os.path.basename(str(daten.get("cwd", "")).rstrip("\\/"))
    meldung = {"projekt": projekt}

    if ereignis == "UserPromptSubmit":
        meldung.update(status="arbeitet", neu=True,
                       aktion="Neue Aufgabe: " + kurz(daten.get("prompt", ""), 60))
    elif ereignis == "PreToolUse":
        meldung.update(status="arbeitet",
                       aktion=beschreibe(daten.get("tool_name", ""), daten.get("tool_input") or {}))
    elif ereignis == "Notification":
        meldung.update(status="wartet", text=kurz(daten.get("message", ""), 100))
    elif ereignis == "Stop":
        meldung.update(status="fertig")
    elif len(sys.argv) > 1:  # von Hand: python claude_status.py arbeitet|fertig|wartet
        meldung.update(status=sys.argv[1])
    else:
        return

    anfrage = urllib.request.Request(
        URL,
        data=json.dumps(meldung).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(anfrage, timeout=1).read()
    except Exception:
        pass


main()
