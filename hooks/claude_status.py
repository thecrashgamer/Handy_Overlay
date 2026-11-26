"""Schickt den Claude-Status an die Phonebox.

Aufruf (von einem Claude-Code-Hook):  python claude_status.py arbeitet|fertig|wartet
Die Adresse laesst sich mit PHONEBOX_URL aendern. Fehler werden still geschluckt,
damit ein ausgeschalteter Phonebox-Server Claude Code nie ausbremst.
"""
import json
import os
import sys
import urllib.request

URL = os.environ.get("PHONEBOX_URL", "http://localhost:8000/claude")


def main():
    status = sys.argv[1] if len(sys.argv) > 1 else "fertig"
    text = ""
    try:  # Claude Code liefert bei Benachrichtigungen den Text auf stdin
        if not sys.stdin.isatty():
            text = str(json.load(sys.stdin).get("message", "")) if status == "wartet" else ""
    except Exception:
        pass
    anfrage = urllib.request.Request(
        URL,
        data=json.dumps({"status": status, "text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(anfrage, timeout=2).read()
    except Exception:
        pass


main()
