"""Hook fuer Gemini CLI: leitet ein Ereignis an die Phonebox weiter und gibt deren Antwort an Gemini CLI zurueck.

Gemini CLI kennt nur Hooks, die ein Programm starten (keine http-Hooks). Deshalb startet es dieses Skript; es liest das Ereignis
von stdin, schickt es an /gemini-hook der Phonebox auf diesem PC und druckt die Antwort (JSON) auf stdout. Mehr als dieses JSON
darf nicht auf stdout stehen (Vorgabe von Gemini CLI). Ist die Phonebox aus oder gibt es einen Fehler, wird {} gedruckt und mit
Code 0 beendet: Gemini CLI wird nie gebremst.

  python gemini_status.py            das Ereignis kommt von Gemini CLI auf stdin
  python gemini_status.py --test     schickt eine Testmeldung und zeigt, ob sie ankam

Jeder Aufruf steht kurz in daten/gemini-hook.log.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

DATEN = Path(__file__).resolve().parent.parent / "daten"
LOG = DATEN / "gemini-hook.log"
LANG = {"AfterAgent"}  # hier darf die Phonebox lange auf eine Anweisung vom Handy warten
KURZ_S, LANG_S = 3, 600


def basis_url():
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


def senden(daten, wartezeit):
    anfrage = urllib.request.Request(basis_url() + "/gemini-hook", data=daten, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(anfrage, timeout=wartezeit) as antwort:
        return antwort.status, antwort.read().decode("utf-8", errors="replace")


def main(argv):
    if argv[:1] == ["--test"]:
        ereignis = {"hook_event_name": "Notification", "notification_type": "ToolPermission",
                    "message": "Testmeldung vom Gemini-Skript", "cwd": os.getcwd()}
        try:
            status, _ = senden(json.dumps(ereignis).encode("utf-8"), KURZ_S)
            print(f"Gesendet an {basis_url()}: HTTP {status}. Auf dem Handy muss jetzt 'Gemini braucht dich' stehen "
                  "(wenn in /admin der Anbieter Gemini gewaehlt ist).")
            return 0
        except Exception as fehler:
            print(f"Fehler: {fehler!r}. Laeuft die Phonebox unter {basis_url()}?")
            return 1
    antwort = "{}"
    try:
        roh = b"" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.buffer.read()
        if not roh.strip():
            protokoll("aufgerufen, aber ohne Ereignis auf stdin")
        else:
            try:
                name = str(json.loads(roh).get("hook_event_name", "?"))
            except (ValueError, AttributeError):
                name = "?"
            status, text = senden(roh, LANG_S if name in LANG else KURZ_S)
            protokoll(f"{name}: HTTP {status}")
            try:
                if isinstance(json.loads(text), dict):
                    antwort = text.strip()
            except ValueError:
                pass
    except Exception as fehler:  # nie Gemini CLI stoeren
        protokoll(f"FEHLER: {fehler!r} (Phonebox erreichbar unter {basis_url()}?)")
    sys.stdout.write(antwort)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
