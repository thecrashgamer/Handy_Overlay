# Phonebox – iPhone 6s als Spotify-Steuerung

Ein Python-Server am Windows-PC steuert Spotify (Desktop-App) über die Windows-Mediensteuerung. Das iPhone öffnet im gleichen WLAN eine Webseite mit Titel, Künstler und Tasten für Play/Pause, Weiter und Zurück.

## Installieren

```
pip install fastapi uvicorn winrt-Windows.Media.Control winrt-Windows.Foundation
```

## Starten

```
python server.py
```

Dann am iPhone in Safari `http://<PC-IP>:8000` öffnen (IP per `ipconfig`) und „Zum Home-Bildschirm“ wählen. Die Windows-Firewall muss für private Netzwerke freigegeben sein.

Für den Autostart `server.py` in `server.pyw` umbenennen und eine Verknüpfung in `shell:startup` legen.
