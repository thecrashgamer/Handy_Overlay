# Phonebox – iPhone 6s als Spotify-Steuerung

Ein Python-Server am Windows-PC steuert Spotify (Desktop-App) über die Windows-Mediensteuerung. Das iPhone öffnet im gleichen WLAN eine Webseite mit Albumcover, Titel, Künstler, Tasten (Play/Pause, Weiter, Zurück), Lautstärke-Regler und Claude-Status. Über die Taste unten rechts wechselst du zur Extras-Ansicht mit Uhr, CPU- und RAM-Anzeige und Shortcut-Tasten.

## Einrichten (Windows)

`start.bat` doppelklicken. Das Skript installiert die Pakete, richtet den Autostart ein, startet den Server und zeigt die Adresse fürs iPhone an. Fragt die Firewall nach, „Private Netzwerke“ erlauben.

Am iPhone in Safari `https://<PC-IP>:8443` öffnen (die Adresse zeigt `start.bat`) und „Zum Home-Bildschirm“ wählen. Beim ersten Mal das Zertifikat installieren, siehe „HTTPS“.

Von Hand geht es auch: `pip install -r requirements.txt`, dann `python server.py`.

## GPU und Akkus der Geräte

Die Extras-Ansicht zeigt unter CPU und RAM auch die **GPU** (Auslastung, Name, Grafikspeicher, Temperatur) und die **Akkustände** verbundener Geräte (Headset, Maus, Tastatur, Controller und der Akku des PCs, falls er ein Laptop ist). Schwache Akkus (unter 20 %) sind rot, ein ladendes Gerät zeigt ⚡. Im Standby erscheint nur noch ein Hinweis, wenn ein Akku unter 15 % fällt und nicht lädt.

Woher die Werte kommen (alles ohne zusätzliche Programme):
- **GPU:** bei NVIDIA über `nvidia-smi` (genau, mit Grafikspeicher und Temperatur). Bei AMD und Intel über die Windows-Leistungsdaten (nur Auslastung und belegter Grafikspeicher).
- **Bluetooth-Geräte** (Headset, Maus, Tastatur): über die Akkuanzeige, die Windows selbst für gekoppelte Geräte führt.
- **Xbox-Controller:** über XInput. Windows liefert nur vier Stufen (Leer, Niedrig, Mittel, Voll), mit Kabel gibt es keinen Akkustand.

**Grenzen:** Welche Geräte ihren Akkustand melden, entscheidet das Gerät. Funk-Geräte mit eigenem USB-Stick (Logitech, Razer, Corsair, SteelSeries) und PlayStation-Controller verraten ihn Windows meist nicht und erscheinen deshalb nicht. Dafür bräuchte es das Programm des Herstellers.

**Fehlersuche:** `python geraete.py` im Phonebox-Ordner zeigt, was gefunden wurde, samt Rohdaten. Welche Geräte der Server erkannt hat, steht auch im Protokoll (`/log`, Zeile „Akku-Geraete“). Die GPU- und Akku-Abfragen laufen in eigenen Threads und bremsen sich selbst, wenn Windows langsam antwortet.

## Standby (dunkle Uhr)

Wird die Phonebox eine Weile nicht benutzt, wird der Bildschirm schwarz und zeigt nur eine große Uhr mit Datum. Läuft Musik, siehst du darunter Cover, Titel und Künstler. Der Claude-Status bleibt als kleine Zeile sichtbar. Ein Tipp (oder eine Taste) weckt auf. Der erste Tipp löst nichts darunter aus. Eine Rückfrage (z. B. Herunterfahren) und „Claude braucht dich“ wecken automatisch auf, und während einer Rückfrage schläft sie nie ein. Der Mond-Knopf unten schickt sie sofort in den Standby.

Die Zeit stellst du **pro Gerät** unter Konto → „Anzeige auf diesem Gerät“ ein (Standard: 10 Minuten, oder „Nie“). Eine Webseite kann die Helligkeit des Bildschirms nicht ändern. Damit das iPhone nicht von selbst sperrt, stell dort Einstellungen → Anzeige & Helligkeit → Automatische Sperre auf „Nie“ (oder nutze den Geführten Zugriff).

## Aktualisieren

`update.bat` doppelklicken. Das Skript lädt die neueste Version von GitHub, tauscht nur Programmdateien aus und startet den Server neu. Konten, Shortcuts und Zertifikate (Ordner `daten`) bleiben unberührt. Was ersetzt wird, liegt vorher als Sicherung in `daten/update-sicherung/` (die letzten 3 bleiben).

- `python update.py --trocken` zeigt nur, was sich ändern würde.
- `python update.py --zurueck` stellt die Dateien der letzten Sicherung wieder her.
- `python update.py --quelle <Adresse oder ZIP-Datei>` nimmt eine andere Quelle.

**Update per Knopf:** Im Admin-Bereich (`/admin`, ganz unten „System und Update“) kannst du nach einer neuen Version suchen und sie mit einem Klick einspielen, ohne `update.bat`. Das braucht dein Passwort. Der Server startet dabei etwa eine halbe Minute neu, die Seite zeigt den Fortschritt und lädt danach neu. Konten, Shortcuts, Bilder und deine Anmeldung bleiben erhalten. Dort gibt es auch „Zur letzten Sicherung zurückkehren“. Start und Ergebnis stehen im Aktivitätsprotokoll. Es läuft immer nur ein Update gleichzeitig, und schlägt eines fehl (z. B. kein Internet), läuft der Server unverändert weiter.

**Wichtig:** Ein Update führt Code aus deinem GitHub-Repository auf deinem PC aus. Sichere deshalb dein GitHub-Konto mit Zwei-Faktor-Anmeldung. Die Quelle ist fest eingebaut und lässt sich nicht über die Webseite ändern (nur über die Umgebungsvariable `PHONEBOX_UPDATE_QUELLE` des Servers).

Aus Sicherheitsgründen akzeptiert das Skript keine ZIP-Dateien mit unsicheren Pfaden (`../`), Verknüpfungen oder ohne `server.py`, und es beendet nur Prozesse, die `server.py` auf den Phonebox-Ports ausführen.

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

## Rechte und Aktivitätsprotokoll

Administratoren dürfen alles. Für normale Benutzer stellst du unter Konto → Verwalten pro Konto ein:
- **Musik** (Standard: an): Titel wechseln, Pause, Lautstärke, Zeitleiste.
- **Shortcuts** (Standard: aus): Kacheln auslösen. Im Admin-Bereich kannst du einzelne Kacheln zusätzlich auf „Nur für Administratoren“ setzen. **Herunterfahren** und **Herunterfahren stoppen** sind immer nur für Administratoren.

Gesperrte Kacheln erscheinen mit einem Schloss. Der Server prüft die Rechte bei **jedem** Befehl neu, nicht nur die Oberfläche. Wer Befehle an der Oberfläche vorbei schickt, wird abgewiesen und im Protokoll vermerkt. Eine Rückfrage (z. B. vor dem Herunterfahren) sieht und bestätigt nur der, der sie ausgelöst hat. Rechte, die du änderst, gelten sofort, auch für schon geöffnete Seiten.

Unter Konto → „Aktivitätsprotokoll ansehen“ (nur Administratoren) steht, wer wann was getan hat: Anmeldungen und Fehlversuche (mit Adresse), ausgelöste Shortcuts, Musiksteuerung, verweigerte Zugriffe und alle Änderungen in der Verwaltung. Passwörter stehen dort nie. Aufbewahrt werden die letzten 5000 Einträge. Eine Sperre wegen vieler Fehlversuche erscheint nur einmal pro 5 Minuten, damit niemand das Protokoll fluten kann.

Hinweis beim Update einer älteren Version: Bestehende normale Benutzer behalten die Musiksteuerung, bekommen aber **keine** Shortcuts mehr, bis du sie freigibst.

## Shortcut-Tasten und Admin-Bereich

Administratoren legen die Kacheln auf einer eigenen Seite an: `http://localhost:8000/admin` (auch über Konto → „Shortcuts anlegen und bearbeiten“). Dort gibt es eine Vorschau wie am Handy, Vorlagen, eine Symbol-Auswahl, eine Aufnahme für Tastenkürzel und Pfeile für die Reihenfolge. Gespeichert wird nur mit deinem Passwort. Am Handy erscheint die neue Liste sofort, ohne Neuladen.

Eine Kachel kann:
- ein **Programm, eine Datei oder eine Webadresse** öffnen (optional mit Argumenten),
- ein **Tastenkürzel** senden (z. B. `win+shift+s`, `ctrl+shift+esc`, `f5`, `stumm`, `playpause`),
- eine feste **Aktion** auslösen: `sperren` (Win+L lässt sich von Windows aus nicht simulieren, darum die echte Sperr-Funktion), `herunterfahren` oder `herunterfahren_stoppen`.

Das Herunterfahren verlangt immer eine Rückfrage, die der Server selbst prüft (10 Sekunden Zeit, nur genau für diese Kachel). Danach läuft der PC mit 15 Sekunden Verzögerung herunter, und die Kachel „Herunterfahren stoppen“ bricht es ab. Jede andere Kachel kann mit „Vor dem Ausführen nachfragen“ ebenfalls eine Rückfrage bekommen.

**Eigene Bilder als Symbol:** Ein Bild (PNG, JPG, SVG, WebP, GIF) lässt sich im Admin-Bereich auf eine Karte ziehen, mit Strg+V einfügen oder über „Bild wählen“ auswählen. Zieht man es in die gestrichelte Fläche unter der Liste, entsteht gleich ein neuer Shortcut mit dem Dateinamen. Der Browser wandelt jedes Bild in ein kleines PNG (128 Pixel) um, ein Skript in einem SVG verschwindet dabei. Der Server nimmt nur vollständig gültige PNG-Dateien an. Sie liegen in `daten/icons/` und werden nur Angemeldeten gezeigt. Ein Bild ersetzt das Emoji. Nicht mehr benutzte Bilder räumt der Server nach einem Tag auf.

Deine Liste liegt in `daten/shortcuts.json` und bleibt bei Updates erhalten. Die mitgelieferte `shortcuts.json` ist nur die Vorlage, solange du noch nichts gespeichert hast. Vor jedem Speichern wird die alte Fassung als `shortcuts.json.bak` gesichert. Freie Befehle (Skripte, Shell) gibt es bewusst nicht. Das Handy schickt nur die Nummer der Kachel.

## Claude-Status

Die Taste unten rechts wechselt durch drei Ansichten: Musik, Extras und Claude. Die Claude-Ansicht zeigt Projekt, Status, eine Stoppuhr, woran Claude gerade arbeitet („Bearbeitet server.py“, „Sucht im Web“ …) und die letzten Schritte. Oben auf den anderen Ansichten erscheint ein farbiges Banner.

**Einrichten (am PC):** `/admin` → Kasten „Claude-Status“ → Passwort eingeben → „Hooks einrichten“. Das trägt Hooks vom Typ `http` in die `settings.json` von Claude Code ein (`%USERPROFILE%\.claude\settings.json`). Sie schicken die Ereignisse direkt an die Phonebox, ganz ohne Python, PATH oder Shell. Deine übrigen Einstellungen und Hooks bleiben unberührt, vorher entsteht eine Sicherung, und eine fehlerhafte Datei wird nicht angefasst. „Hooks entfernen“ nimmt nur die Einträge der Phonebox wieder heraus. Die Python-Variante unter „Weitere Möglichkeiten“ ist nur für den Fall, dass dein Claude Code keine `http`-Hooks kennt.

**Wichtig:** Hooks laufen nur in **lokalen** Sitzungen auf dem PC (Claude-App im Bereich „Code“ mit lokalem Ordner, oder das Terminal), **nicht in Cloud-Sitzungen**. Außerdem hält Claude Code Hooks zurück, bis du den Ordner als vertrauenswürdig bestätigt hast. Mit `/hooks` in Claude Code siehst du, ob die Einträge geladen sind.

**Fehlersuche:** Der Kasten zeigt, ob die Hooks eingetragen sind, wann zuletzt etwas ankam und wie viele Ereignisse je Art (UserPromptSubmit, PreToolUse, PermissionRequest, Notification, Stop). Steht dort „noch nichts angekommen“, gehst du die Liste im Kasten durch. Mit den Testknöpfen („Arbeitet“, „Braucht dich“, „Fertig“) prüfst du die Anzeige ohne Claude. Das Python-Skript schreibt jeden Aufruf in `daten/claude-hook.log`, und `python hooks/claude_status.py --test` schickt eine Testmeldung.

**Datenschutz:** Der Server wertet nur Dateinamen, Beschreibungen und das Programm eines Befehls aus. Dateiinhalte, ganze Befehle und Eingaben werden weder gespeichert noch angezeigt. Ereignisse nimmt der Server nur vom PC selbst an (oder mit Anmeldung), nicht aus dem WLAN.

**Ton und Blitz:** Wird Claude fertig oder braucht dich (Erlaubnis-Abfrage, Rückfrage), gibt es einen kurzen Ton und einen farbigen Blitz (grün: fertig, blau: braucht dich). Stellbar unter Konto → „Anzeige auf diesem Gerät“ (Ton und Blitz, nur Blitz, nichts). Auf dem iPhone kommt der Ton erst, nachdem du die Seite einmal angetippt hast, und Vibration gibt es dort nicht. Auf Android vibriert das Gerät zusätzlich.

## Testen ohne Windows

```
pip install fastapi "uvicorn[standard]"
PHONEBOX_TEST=1 python server.py      # Fake-Songs statt Spotify
node tests/ui.test.js                 # UI-Test mit Playwright
node tests/auth.test.js               # Konten-Test
node tests/admin.test.js              # Admin-Bereich-Test
node tests/https.test.js              # HTTPS-Test
node tests/rechte.test.js             # Rechte und Aktivitätsprotokoll
node tests/standby.test.js            # Standby-Modus
node tests/icons.test.js              # Bilder als Symbole
node tests/geraete.test.js            # GPU und Akkus
node tests/claude.test.js             # Claude-Status, Hooks, Ton
node tests/adminupdate.test.js        # Update per Knopf (mit echtem Neustart, dauert etwas)
# test_update.py prüft das Update-Skript, auch mit einem echten Neustart
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Dateien

| Datei | Inhalt |
|---|---|
| `server.py` | Webserver, WebSocket, Claude-Endpunkt |
| `medien.py` | Spotify, Cover und Lautstärke (Windows) bzw. Fake-Daten (Test) |
| `shortcuts.py`, `shortcuts.json` | Shortcut-Logik, Prüfung und Vorlage |
| `admin.py`, `admin.html` | Admin-Bereich für die Shortcuts |
| `aktivitaet.html` | Aktivitätsprotokoll |
| `icons.py` | Prüfung und Ablage der Symbolbilder |
| `geraete.py` | GPU und Akkustände der Geräte |
| `index.html` | Oberfläche fürs iPhone |
| `zertifikate.py`, `zertifikat.html` | HTTPS: eigenes Zertifikat und Anleitung für das Handy |
| `anmelden.html`, `konto.html` | Anmeldung, Konto und Benutzerverwaltung |
| `auth.py`, `konten.py` | Routen und Logik der Konten |
| `benutzer.py` | Konten am PC verwalten |
| `start.bat` | Einrichtung und Autostart |
| `update.bat`, `update.py` | Aktualisieren auf die neueste Version |
| `hooks/` | Python-Variante des Claude-Hooks |
| `claude_ereignisse.py`, `claude_einrichten.py` | Auswertung der Claude-Ereignisse, Eintragen in die settings.json |
| `tests/` | UI-Test und Shortcut-Tests |

## Anweisungen vom Handy an Claude (v23)

Im Claude-Fenster der Phonebox gibt es ein Textfeld, mit dem du Claude Code auf dem PC etwas mitteilen kannst.

- **Standardmäßig aus.** Einschalten nur als Administrator unter /admin (mit Passwort).
- Nur Administratoren sehen das Feld. Grenzen: 2000 Zeichen, höchstens 5 wartende Anweisungen, 10 pro Minute, Verfall nach 15 Minuten. Alles steht im Aktivitätsprotokoll.
- **Zustellung** über die Hooks: Claude holt die Anweisung ab, sobald er den nächsten Schritt macht (zusätzlicher Kontext) oder fertig werden will (er arbeitet dann weiter). Abgeholt wird nur von Claude Code auf dem PC selbst, nie von außen.
- **Nach dem Fertigwerden** bleibt Claude noch bis zu 9 Minuten offen (Stop-Hook) und nimmt eine Anweisung vom Handy sofort an. Dafür muss der Hook einmal neu eingerichtet werden (Knopf „Einrichten“ in /admin), damit der Stop-Hook das lange Zeitfenster bekommt.
- **Grenze:** Ist die 9-Minuten-Frist vorbei, wird er nicht mehr geweckt. Die Anweisung kommt erst, wenn du am PC etwas eingibst. Für echte Fernsteuerung gibt es offiziell „Remote Control“ von Claude Code.
- Auf echtem Windows/Desktop-App ist das Verhalten noch nicht erprobt.

### Claude-Mod (v26): die zuverlässige Zustellung

Die Hook-Wege oben haben sich auf dem echten PC als unzuverlässig erwiesen, sobald Claude fertig ist. Deshalb gibt es im Ordner `claude-mod` einen kleinen **Claude-Code-Mod** (offizielle Plugin-Art, läuft im Code-Tab der Desktop-App ab Version 2.1.286, nicht in WSL/SSH-Sitzungen). Er fragt alle 2 Sekunden die Phonebox auf **diesem** PC (127.0.0.1:8000) und schickt eine wartende Anweisung als normale Nachricht in die Sitzung, auch wenn Claude gerade fertig ist.

Einmal einrichten. Im Dialog „Marketplace hinzufügen“ der Desktop-App genügt `thecrashgamer/Handy_Overlay` (GitHub), dann das Plugin „phonebox“ installieren. Oder in einer Claude-Code-Sitzung, Pfad zum Ordner `claude-mod` im Phonebox-Ordner anpassen):

```
/plugin marketplace add C:\Pfad\zu\Handy_Overlay\claude-mod
/plugin install phonebox@phonebox
/reload-plugins
```

Sobald der Mod verbunden ist, zeigt die Diagnose in /admin „Mod aktiv“, und die Hook-Wege halten sich zurück. Das Textfeld muss weiterhin in /admin eingeschaltet sein. Der Mod läuft ohne Sandbox mit deinen Rechten; er ist klein und im Ordner einsehbar. Nach Esc oder Stopp in Claude wird eine Anweisung nach dem nächsten Zug erneut zugestellt.

Ab v29 (Mod 0.2.0) erscheint Claudes letzte Antwort im Claude-Fenster am Handy („Antwort von Claude“, höchstens 4000 Zeichen, nur im Arbeitsspeicher, nur für Administratoren, nur bei eingeschalteter Funktion). Der Mod meldet sie am Ende jedes Zuges an die Phonebox auf dem PC.
