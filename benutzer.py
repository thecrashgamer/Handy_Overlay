"""Konten am PC verwalten, auch wenn man sich ausgesperrt hat.

  python benutzer.py liste                 alle Konten zeigen
  python benutzer.py passwort <Name>       neues Passwort setzen (fragt es ab)
  python benutzer.py freigeben <Name>      Konto freigeben oder entsperren
  python benutzer.py sperren <Name>        Konto sperren
  python benutzer.py admin <Name>          zum Administrator machen
  python benutzer.py benutzer <Name>       Administrator-Rechte entziehen

Das geht nur, wer Zugriff auf den PC und die Datei daten/phonebox.db hat. Der Server muss dafuer nicht laufen.
"""
import getpass
import os
import sys
from pathlib import Path

from konten import KontoFehler, Konten

DATEN = Path(os.environ.get("PHONEBOX_DATEN", Path(__file__).parent / "daten"))


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "hilfe"):
        print(__doc__)
        return 0
    k = Konten(DATEN / "phonebox.db")
    befehl = argv[0]
    try:
        if befehl == "liste":
            for b in k.liste():
                print(f"{b['id']:>3}  {b['name']:<30} {b['rolle']:<9} {b['status']}")
            return 0
        if len(argv) < 2:
            print("Es fehlt der Name. Beispiel: python benutzer.py", befehl, "Timo")
            return 2
        b = k.finden(argv[1])
        if b is None:
            print("Dieses Konto gibt es nicht:", argv[1])
            return 1
        if befehl == "passwort":
            neu = getpass.getpass("Neues Passwort: ")
            if neu != getpass.getpass("Noch einmal: "):
                print("Die beiden Eingaben sind nicht gleich.")
                return 1
            k.passwort_setzen(b["name"], neu)
            print("Passwort gesetzt. Alle Geraete sind abgemeldet.")
        elif befehl == "freigeben":
            k.status_setzen(b["id"], "aktiv")
            print("Freigegeben:", b["name"])
        elif befehl == "sperren":
            k.status_setzen(b["id"], "gesperrt")
            print("Gesperrt:", b["name"])
        elif befehl in ("admin", "benutzer"):
            k.rolle_setzen(b["id"], befehl)
            print(b["name"], "ist jetzt", "Administrator" if befehl == "admin" else "Benutzer")
        else:
            print("Unbekannter Befehl:", befehl)
            print(__doc__)
            return 2
    except KontoFehler as f:
        print("Nicht moeglich:", f.text)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
