# Phonebox – iPhone 6s als Spotify-Steuerung

Ein Python-Server am Windows-PC steuert Spotify (Desktop-App) über die Windows-Mediensteuerung. Das iPhone öffnet im gleichen WLAN eine Webseite mit Albumcover, Titel, Künstler, Tasten (Play/Pause, Weiter, Zurück), Lautstärke-Regler und Claude-Status. Über die Taste unten rechts wechselst du zur Extras-Ansicht mit Uhr, CPU- und RAM-Anzeige und Shortcut-Tasten.

## Einrichten (Windows)

`start.bat` doppelklicken. Das Skript installiert die Pakete, richtet den Autostart ein, startet den Server und zeigt die Adresse fürs iPhone an. Fragt die Firewall nach, „Private Netzwerke“ erlauben.

Am iPhone in Safari `http://<PC-IP>:8000` öffnen und „Zum Home-Bildschirm“ wählen.

Von Hand geht es auch: `pip install -r requirements.txt`, dann `python server.py`.

## Shortcut-Tasten

Die Kacheln stehen in `shortcuts.json` am PC und werden bei Änderungen automatisch neu geladen. Jeder Eintrag hat `name`, optional `icon` und entweder `programm` (Programm, Datei oder Webadresse starten) oder `tasten` (Tastenkürzel, z. B. `win+shift+s`, `ctrl+shift+esc`, `f5`, `stumm`, `playpause`). Das iPhone schickt nur die Nummer der Kachel, nie einen freien Befehl.

## Claude-Status

Die Hooks in `hooks/` melden „Claude arbeitet“, „Claude braucht dich“ und „Claude ist fertig“ ans iPhone. `hooks/settings-beispiel.json` in die Claude-Code-Einstellungen (`~/.claude/settings.json`) übernehmen und den Pfad anpassen. Läuft Claude Code auf einem anderen Rechner, `PHONEBOX_URL=http://<PC-IP>:8000/claude` setzen.

Achtung: `/claude` ist im ganzen WLAN ohne Passwort erreichbar. Für ein Heimnetz in Ordnung.

## Testen ohne Windows

```
pip install fastapi "uvicorn[standard]"
PHONEBOX_TEST=1 python server.py      # Fake-Songs statt Spotify
node tests/ui.test.js                 # UI-Test mit Playwright
python3 -m unittest tests.test_shortcuts
```

## Dateien

| Datei | Inhalt |
|---|---|
| `server.py` | Webserver, WebSocket, Claude-Endpunkt |
| `medien.py` | Spotify, Cover und Lautstärke (Windows) bzw. Fake-Daten (Test) |
| `shortcuts.py`, `shortcuts.json` | Shortcut-Tasten und ihre Liste |
| `index.html` | Oberfläche fürs iPhone |
| `start.bat` | Einrichtung und Autostart |
| `hooks/` | Claude-Code-Hooks |
| `tests/` | UI-Test und Shortcut-Tests |
