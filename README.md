# 🐍 Python-Werkstatt

Python lernen durch kleine Projekte zum Selberbasteln. Läuft komplett im Browser (Python via [Pyodide](https://pyodide.org)), ohne Installation und ohne Server.

## Starten

```bash
python3 -m http.server 8000
# dann http://localhost:8000 öffnen
```

(Beim ersten Laden wird Python aus dem Internet geholt, danach cached der Browser es.)

## Aufbau

| Datei | Inhalt |
|---|---|
| `lessons.js` | Alle Projekte und Schritte (hier neue Projekte ergänzen) |
| `app.js` | Logik: Ansichten, Editor, Python-Ausführung, Fortschritt |
| `style.css`, `index.html` | Oberfläche |

## Neues Projekt hinzufügen

Einen Eintrag in `PROJECTS` in `lessons.js` anlegen: `id`, `icon`, `title`, `level`, `summary`, `concepts`, `steps` (jeweils `title`, `text`, `code`, `hint`) und `ideas`.

Fortschritt und eigener Code werden im `localStorage` des Browsers gespeichert.
