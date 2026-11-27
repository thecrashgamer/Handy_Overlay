"""Python-Variante des Phonebox-Hooks. Leitet ein Ereignis von Claude Code an die Phonebox weiter.

Normalerweise brauchst du das nicht: Die Einrichtung im Admin-Bereich nutzt Hooks vom Typ "http", die ganz ohne Python
auskommen. Diese Variante ist der Ersatz, falls dein Claude Code keine http-Hooks kennt.

  python claude_status.py                         das Ereignis kommt von Claude Code auf stdin
  python claude_status.py --test                  schickt eine Testmeldung und zeigt, ob sie ankam
  python claude_status.py arbeitet|fertig|wartet  von Hand eine Meldung schicken

Jeder Aufruf steht kurz in daten/claude-hook.log, damit man sieht, ob Claude Code den Hook startet. Fehler bremsen Claude
Code nie: Ist die Phonebox aus, endet das Skript still mit Code 0.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

DATEN = Path(__file__).resolve().parent.parent / "daten"
LOG = DATEN / "claude-hook.log"


def basis_url():
    if os.environ.get("PHONEBOX_URL"):  # aelterer Name: Adresse mit /claude am Ende
        return os.environ["PHONEBOX_URL"].rsplit("/claude", 1)[0].rstrip("/")
    port = 8000
    try:
        port = int(json.loads((DATEN / "server.json").read_text(encoding="utf-8"))["port"])  # schreibt der Server beim Start
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return f"http://127.0.0.1:{port}"


def protokoll(text):
    try:
        DATEN.mkdir(exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 60_000:  # klein halten: nur die letzten 100 Zeilen
            LOG.write_text("\n".join(LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]) + "\n", encoding="utf-8")
        with open(LOG, "a", encoding="utf-8") as d:
            d.write(f"{time.strftime('%d.%m. %H:%M:%S')} {text}\n")
    except OSError:
        pass


def senden(pfad, daten):
    anfrage = urllib.request.Request(basis_url() + pfad, data=daten, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(anfrage, timeout=2) as antwort:
        antwort.read()
        return antwort.status


def main(argv):
    try:
        if argv[:1] == ["--test"]:
            ereignis = {"hook_event_name": "Notification", "notification_type": "permission_prompt",
                        "message": "Testmeldung vom Python-Skript", "cwd": os.getcwd()}
            status = senden("/claude-hook", json.dumps(ereignis).encode("utf-8"))
            print(f"Gesendet an {basis_url()}: HTTP {status}. Auf dem Handy muss jetzt 'Claude braucht dich' stehen.")
            protokoll(f"Test: HTTP {status}")
            return 0
        if argv and argv[0] in ("arbeitet", "fertig", "wartet"):
            status = senden("/claude", json.dumps({"status": argv[0], "ereignis": "von Hand"}).encode("utf-8"))
            protokoll(f"von Hand {argv[0]}: HTTP {status}")
            return 0
        roh = b"" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.buffer.read()
        if not roh.strip():
            protokoll("aufgerufen, aber ohne Ereignis auf stdin")
            return 0
        try:
            name = json.loads(roh).get("hook_event_name", "?")
        except (ValueError, AttributeError):
            name = "?"
        status = senden("/claude-hook", roh)
        protokoll(f"{name}: HTTP {status}")
    except Exception as fehler:  # nie Claude Code stoeren
        protokoll(f"FEHLER: {fehler!r} (Phonebox erreichbar unter {basis_url()}?)")
        if argv[:1] == ["--test"]:
            print(f"Fehler: {fehler!r}. Laeuft die Phonebox unter {basis_url()}?")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
