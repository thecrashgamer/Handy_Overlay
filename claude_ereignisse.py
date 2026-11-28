"""Macht aus den Ereignissen von Claude Code (Hooks) eine Statusmeldung fuer die Phonebox.

Claude Code schickt je Ereignis ein JSON (Felder laut Dokumentation: hook_event_name, cwd, prompt, tool_name, tool_input,
message, notification_type ...). Hier wird nur ausgewertet, was fuer die Anzeige noetig ist: Dateinamen, Beschreibungen,
der Name des Programms eines Befehls. Dateiinhalte und ganze Befehle werden weder gespeichert noch angezeigt.
"""
import re

# Notification-Arten, bei denen Claude auf dich wartet. idle_prompt (60 s nach dem Ende) und auth_* bleiben aussen vor.
BRAUCHT_DICH = {"permission_prompt", "elicitation_dialog", "agent_needs_input"}


def kurz(text, laenge=70):
    text = " ".join(str(text).split())
    return text if len(text) <= laenge else text[: laenge - 1] + "\u2026"


def dateiname(pfad):
    """Letzter Teil eines Pfades, egal ob mit \\ (Windows) oder / geschrieben."""
    teile = [t for t in re.split(r"[\\/]", str(pfad or "")) if t]
    return teile[-1] if teile else ""


def beschreibe(werkzeug, eingabe):
    werkzeug = str(werkzeug or "")
    eingabe = eingabe if isinstance(eingabe, dict) else {}
    datei = dateiname(eingabe.get("file_path") or eingabe.get("absolute_path") or eingabe.get("notebook_path"))
    # Werkzeugnamen von Gemini CLI stehen gleich mit dabei (read_file, replace, run_shell_command ...)
    if werkzeug in ("Read", "read_file"):
        return f"Liest {datei}"
    if werkzeug == "read_many_files":
        return "Liest mehrere Dateien"
    if werkzeug == "list_directory":
        return "Listet einen Ordner auf"
    if werkzeug in ("Edit", "MultiEdit", "NotebookEdit", "replace"):
        return f"Bearbeitet {datei}"
    if werkzeug in ("Write", "write_file"):
        return f"Schreibt {datei}"
    if werkzeug in ("Bash", "PowerShell", "run_shell_command"):
        if eingabe.get("description"):
            return kurz(eingabe["description"])
        erstes = str(eingabe.get("command", "")).split()
        return f"F\u00fchrt einen Befehl aus ({kurz(erstes[0], 30)})" if erstes else "F\u00fchrt einen Befehl aus"
    if werkzeug in ("Grep", "Glob", "glob", "grep_search", "search_file_content"):
        return f"Sucht {kurz(eingabe.get('pattern', ''), 40)}"
    if werkzeug in ("WebSearch", "WebFetch", "google_web_search", "web_fetch"):
        return "Sucht im Web"
    if werkzeug in ("Agent", "Task"):
        return "Startet einen Hilfsagenten"
    if werkzeug.startswith("mcp__"):
        return f"Nutzt {werkzeug.split('__')[-1]}"
    return werkzeug or "Arbeitet"


def meldung_aus_ereignis(daten):
    """Gibt die Felder fuer eine Statusmeldung zurueck oder None, wenn das Ereignis die Anzeige nicht aendern soll."""
    if not isinstance(daten, dict):
        return None
    ereignis = str(daten.get("hook_event_name", ""))
    meldung = {"projekt": dateiname(daten.get("cwd"))}
    if ereignis == "UserPromptSubmit":
        meldung.update(status="arbeitet", neu=True, aktion="Neue Aufgabe: " + kurz(daten.get("prompt", ""), 60))
    elif ereignis == "PreToolUse":
        meldung.update(status="arbeitet", aktion=beschreibe(daten.get("tool_name"), daten.get("tool_input")))
    elif ereignis == "PermissionRequest":  # die Erlaubnis-Abfrage ist da: sofort melden, nicht erst nach ~6 Sekunden
        meldung.update(status="wartet", text="Erlaubnis n\u00f6tig: " + beschreibe(daten.get("tool_name"), daten.get("tool_input")))
    elif ereignis == "Notification":
        if str(daten.get("notification_type", "")) not in BRAUCHT_DICH:
            return None
        meldung.update(status="wartet", text=kurz(daten.get("message") or "Claude braucht dich", 100))
    elif ereignis == "Stop":
        meldung.update(status="fertig")
    else:
        return None
    return meldung
