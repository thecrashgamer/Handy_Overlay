# Phonebox – iPhone 6s als Spotify-Steuerung

Ein Python-Server am Windows-PC steuert Spotify (Desktop-App) über die Windows-Mediensteuerung. Das iPhone öffnet im gleichen WLAN eine Webseite mit Albumcover, Titel, Künstler, Tasten (Play/Pause, Weiter, Zurück), Lautstärke-Regler und Claude-Status. Über die Taste unten rechts wechselst du zur Extras-Ansicht mit Uhr, CPU- und RAM-Anzeige und Shortcut-Tasten.

## Einrichten (Windows)

`start.bat` doppelklicken. Das Skript installiert die Pakete, richtet den Autostart ein, startet den Server und zeigt die Adresse fürs iPhone an. Fragt die Firewall nach, „Private Netzwerke“ erlauben.

Am iPhone in Safari `https://<PC-IP>:8443` öffnen (die Adresse zeigt `start.bat`) und „Zum Home-Bildschirm“ wählen. Beim ersten Mal das Zertifikat installieren, siehe „HTTPS“.

Von Hand geht es auch: `pip install -r requirements.txt`, dann `python server.py`.

## Konten und Anmeldung

Die ganze Phonebox ist durch Benutzerkonten geschützt. Ohne Anmeldung kommt man weder auf die Seite noch an die Steuerung, das Cover oder das Protokoll.

- **Erstes Konto:** Beim ersten Start öffnest du am PC `http://localhost:8000`. Das erste Konto wird Administrator und lässt sich nur am PC selbst anlegen, nicht übers WLAN.
- **Registrieren:** Weitere Konten kann jeder anlegen, der die Seite erreicht, aber der Administrator muss sie freigeben, bevor man sich anmelden kann. Das ist unter Konto → Benutzer verwalten einstellbar (mit Freigabe, sofort aktiv oder gesperrt).
- **Angemeldet bleiben:** Das Häkchen merkt die Anmeldung 90 Tage. Das ist richtig für die Phonebox am iPhone. Der Passwortmanager des Browsers kann Name und Passwort speichern.
- **Passwort vergessen:** Beim Anlegen bekommt jedes Konto 8 Wiederherstellungscodes (einmalig sichtbar, jeder gilt einmal). Damit setzt man auf der Anmeldeseite das Passwort zurück. Neue Codes gibt es unter Konto. E-Mail gibt es noch nicht.
- **Ausgesperrt?** Am PC geht `python benutzer.py passwort <Name>` (und `liste`, `freigeben`, `sperren`, `admin`). Das funktioniert auch bei ausgeschaltetem Server.

Passwörter werden mit scrypt gespeichert, Sitzungen und Codes nur als Hash. Nach 5 falschen Versuchen wird 5 Minuten gesperrt. Die Daten liegen in `daten/phonebox.db` (nicht im Git). Der Claude-Status (`/claude`) braucht keine Anmeldung, wenn er vom PC selbst kommt.

Nie die Phonebox direkt ins Internet stellen. Von außerhalb nur über ein VPN wie Tailscale (siehe „HTTPS“ zu den Namen im Zertifikat).

## HTTPS

Im WLAN läuft die Phonebox nur verschlüsselt (`https://<PC-IP>:8443`), damit Passwörter nicht mitgelesen werden können. Unverschlüsseltes `http` gibt es nur am PC selbst (`http://localhost:8000`), und dort ohne Warnung. Der Claude-Status und das erste Konto bleiben darüber erreichbar.

Beim ersten Start legt der Server ein eigenes Zertifikat an (Ordner `daten/https`). Das Handy muss ihm einmal vertrauen:
1. Am Handy `https://<PC-IP>:8443/zertifikat` öffnen. Die Warnung „nicht privat“ einmal bestätigen (Details → Webseite besuchen).
2. Zertifikat laden, dann in den Einstellungen das Profil installieren.
3. **Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen:** „Phonebox Zertifikat“ einschalten. Ohne diesen Schritt bleibt die Warnung.
4. Der Fingerabdruck auf der Seite muss zu dem im Protokoll des Servers (`/log`) passen.

Ändert sich die IP-Adresse des PCs, erneuert der Server beim nächsten Start nur das Server-Zertifikat. Das Handy muss nichts neu installieren. Weitere Namen, etwa einen Tailscale-Namen, trägst du in der Umgebungsvariable `PHONEBOX_ZUSATZ_NAMEN` ein (kommagetrennt). Mit `PHONEBOX_HTTPS=0` gibt es wieder nur unverschlüsseltes http im ganzen Netz. Das ist nicht empfohlen. Klappt HTTPS nicht (z. B. fehlt `cryptography`), läuft die Phonebox nur am PC und nie unverschlüsselt im WLAN.

**Wichtig:** Die Datei `daten/https/ca-key.pem` ist der geheime Schlüssel deiner Zertifizierungsstelle. Wer ihn hat, könnte Zertifikate ausstellen, denen dein Handy vertraut. Gib den Ordner `daten` nie weiter. Hast du den Verdacht, dass er geklaut wurde: Ordner `daten/https` löschen, Server neu starten, das Profil am Handy entfernen und das neue installieren.

## Shortcut-Tasten und Admin-Bereich

Administratoren legen die Kacheln auf einer eigenen Seite an: `http://localhost:8000/admin` (auch über Konto → „Shortcuts anlegen und bearbeiten“). Dort gibt es eine Vorschau wie am Handy, Vorlagen, eine Symbol-Auswahl, eine Aufnahme für Tastenkürzel und Pfeile für die Reihenfolge. Gespeichert wird nur mit deinem Passwort. Am Handy erscheint die neue Liste sofort, ohne Neuladen.

Eine Kachel kann:
- ein **Programm, eine Datei oder eine Webadresse** öffnen (optional mit Argumenten),
- ein **Tastenkürzel** senden (z. B. `win+shift+s`, `ctrl+shift+esc`, `f5`, `stumm`, `playpause`),
- eine feste **Aktion** auslösen: `sperren` (Win+L lässt sich von Windows aus nicht simulieren, darum die echte Sperr-Funktion), `herunterfahren` oder `herunterfahren_stoppen`.

Das Herunterfahren verlangt immer eine Rückfrage, die der Server selbst prüft (10 Sekunden Zeit, nur genau für diese Kachel). Danach läuft der PC mit 15 Sekunden Verzögerung herunter, und die Kachel „Herunterfahren stoppen“ bricht es ab. Jede andere Kachel kann mit „Vor dem Ausführen nachfragen“ ebenfalls eine Rückfrage bekommen.

Deine Liste liegt in `daten/shortcuts.json` und bleibt bei Updates erhalten. Die mitgelieferte `shortcuts.json` ist nur die Vorlage, solange du noch nichts gespeichert hast. Vor jedem Speichern wird die alte Fassung als `shortcuts.json.bak` gesichert. Freie Befehle (Skripte, Shell) gibt es bewusst nicht. Das Handy schickt nur die Nummer der Kachel.

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
node tests/admin.test.js              # Admin-Bereich-Test
node tests/https.test.js              # HTTPS-Test
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Dateien

| Datei | Inhalt |
|---|---|
| `server.py` | Webserver, WebSocket, Claude-Endpunkt |
| `medien.py` | Spotify, Cover und Lautstärke (Windows) bzw. Fake-Daten (Test) |
| `shortcuts.py`, `shortcuts.json` | Shortcut-Logik, Prüfung und Vorlage |
| `admin.py`, `admin.html` | Admin-Bereich für die Shortcuts |
| `index.html` | Oberfläche fürs iPhone |
| `zertifikate.py`, `zertifikat.html` | HTTPS: eigenes Zertifikat und Anleitung für das Handy |
| `anmelden.html`, `konto.html` | Anmeldung, Konto und Benutzerverwaltung |
| `auth.py`, `konten.py` | Routen und Logik der Konten |
| `benutzer.py` | Konten am PC verwalten |
| `start.bat` | Einrichtung und Autostart |
| `hooks/` | Claude-Code-Hooks |
| `tests/` | UI-Test und Shortcut-Tests |
