# Phonebox – iPhone 6s als Spotify-Steuerung

Ein Python-Server am Windows-PC steuert Spotify (Desktop-App) über die Windows-Mediensteuerung. Das iPhone öffnet im gleichen WLAN eine Webseite mit Albumcover, Titel, Künstler, Tasten (Play/Pause, Weiter, Zurück), Lautstärke-Regler und Claude-Status. Über die Taste unten rechts wechselst du zur Extras-Ansicht mit Uhr, CPU- und RAM-Anzeige und Shortcut-Tasten.

## Einrichten (Windows)

`start.bat` doppelklicken. Das Skript installiert die Pakete, richtet den Autostart ein, startet den Server und zeigt die Adresse fürs iPhone an. Fragt die Firewall nach, „Private Netzwerke“ erlauben.

Am iPhone in Safari `http://<PC-IP>:8000` öffnen und „Zum Home-Bildschirm“ wählen.

Von Hand geht es auch: `pip install -r requirements.txt`, dann `python server.py`.

## Konten und Anmeldung

Die ganze Phonebox ist durch Benutzerkonten geschützt. Ohne Anmeldung kommt man weder auf die Seite noch an die Steuerung, das Cover oder das Protokoll.

- **Erstes Konto:** Beim ersten Start öffnest du am PC `http://localhost:8000`. Das erste Konto wird Administrator und lässt sich nur am PC selbst anlegen, nicht übers WLAN.
- **Registrieren:** Weitere Konten kann jeder anlegen, der die Seite erreicht, aber der Administrator muss sie freigeben, bevor man sich anmelden kann. Das ist unter Konto → Benutzer verwalten einstellbar (mit Freigabe, sofort aktiv oder gesperrt).
- **Angemeldet bleiben:** Das Häkchen merkt die Anmeldung 90 Tage. Das ist richtig für die Phonebox am iPhone. Der Passwortmanager des Browsers kann Name und Passwort speichern.
- **Passwort vergessen:** Beim Anlegen bekommt jedes Konto 8 Wiederherstellungscodes (einmalig sichtbar, jeder gilt einmal). Damit setzt man auf der Anmeldeseite das Passwort zurück. Neue Codes gibt es unter Konto. E-Mail gibt es noch nicht.
- **Ausgesperrt?** Am PC geht `python benutzer.py passwort <Name>` (und `liste`, `freigeben`, `sperren`, `admin`). Das funktioniert auch bei ausgeschaltetem Server.

Passwörter werden mit scrypt gespeichert, Sitzungen und Codes nur als Hash. Nach 5 falschen Versuchen wird 5 Minuten gesperrt. Die Daten liegen in `daten/phonebox.db` (nicht im Git). Der Claude-Status (`/claude`) braucht keine Anmeldung, wenn er vom PC selbst kommt.

Hinweis: Die Verbindung ist im Heimnetz unverschlüsselt (http). Von außerhalb nur über ein VPN wie Tailscale gehen, nie die Phonebox direkt ins Internet stellen.

## Shortcut-Tasten

Die Kacheln stehen in `shortcuts.json` am PC und werden bei Änderungen automatisch neu geladen. Jeder Eintrag hat `name`, optional `icon` und entweder `programm` (Programm, Datei oder Webadresse starten) oder `tasten` (Tastenkürzel, z. B. `win+shift+s`, `ctrl+shift+esc`, `f5`, `stumm`, `playpause`). Außerdem gibt es feste Aktionen mit `aktion`: `sperren` (Win+L lässt sich von Windows aus nicht simulieren, darum die echte Sperr-Funktion), `herunterfahren` und `herunterfahren_stoppen`. Das Herunterfahren verlangt immer eine Rückfrage auf dem iPhone, die der Server selbst prüft (10 Sekunden Zeit, nur genau für diese Kachel) und startet dann mit 15 Sekunden Verzögerung. In dieser Zeit bricht die Kachel „Herunterfahren stoppen“ es ab. Jeder andere Eintrag kann mit `"bestaetigen": true` ebenfalls eine Rückfrage bekommen.

Erscheint die Rückfrage nicht, unter `http://<PC-IP>:8000/log` nachsehen: „Rueckfrage gesendet“ heißt, der Server hat sie geschickt, „Rueckfrage angezeigt“, dass eine Seite sie zeigt. „WARNUNG: Seite … verbunden“ bedeutet, dass eine alte `index.html` läuft (alte Datei im Ordner oder alte Seite im Browser). Dann alle Dateien aus der neuen Version kopieren und die Seite neu laden. JavaScript-Fehler zeigt die Seite selbst als rote Leiste oben.

Das iPhone schickt nur die Nummer der Kachel, nie einen freien Befehl.

## Claude-Status

Die Taste unten rechts wechselt durch drei Ansichten: Musik, Extras und Claude. Die Claude-Ansicht zeigt Projekt, Status, eine Stoppuhr, woran Claude gerade arbeitet („Bearbeitet server.py“, „Sucht im Web“ …) und die letzten Schritte. Oben auf allen anderen Ansichten erscheint dazu ein farbiges Banner.

Die Meldungen kommen von Claude-Code-Hooks. Sie laufen dort, wo Claude Code läuft, also auf deinem PC (Desktop-App oder Terminal), nicht in einer Cloud-Sitzung. Einrichten:

1. `hooks/settings-beispiel.json` in `~/.claude/settings.json` übernehmen (unter Windows `C:\Users\<Name>\.claude\settings.json`) und den Pfad zu `claude_status.py` anpassen.
2. Claude Code neu starten.

Gesendet werden nur Dateinamen, Beschreibungen und der Name des Programms eines Befehls, nie Dateiinhalte oder ganze Befehle. Läuft Claude Code auf einem anderen Rechner, `PHONEBOX_URL=http://<PC-IP>:8000/claude` setzen. Meldet Claude zehn Minuten lang nichts, gilt der Status als beendet.

Achtung: `/claude` ist im ganzen WLAN ohne Passwort erreichbar. Für ein Heimnetz in Ordnung.

## Testen ohne Windows

```
pip install fastapi "uvicorn[standard]"
PHONEBOX_TEST=1 python server.py      # Fake-Songs statt Spotify
node tests/ui.test.js                 # UI-Test mit Playwright
node tests/auth.test.js               # Konten-Test
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Dateien

| Datei | Inhalt |
|---|---|
| `server.py` | Webserver, WebSocket, Claude-Endpunkt |
| `medien.py` | Spotify, Cover und Lautstärke (Windows) bzw. Fake-Daten (Test) |
| `shortcuts.py`, `shortcuts.json` | Shortcut-Tasten und ihre Liste |
| `index.html` | Oberfläche fürs iPhone |
| `anmelden.html`, `konto.html` | Anmeldung, Konto und Benutzerverwaltung |
| `auth.py`, `konten.py` | Routen und Logik der Konten |
| `benutzer.py` | Konten am PC verwalten |
| `start.bat` | Einrichtung und Autostart |
| `hooks/` | Claude-Code-Hooks |
| `tests/` | UI-Test und Shortcut-Tests |
