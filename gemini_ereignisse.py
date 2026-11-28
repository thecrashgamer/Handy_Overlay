"""Macht aus den Hook-Ereignissen von Gemini CLI dieselbe Statusmeldung wie bei Claude Code.

Gemini CLI schickt je Ereignis ein JSON auf stdin (Felder laut github.com/google-gemini/gemini-cli, docs/hooks/reference.md:
session_id, cwd, hook_event_name, dazu je Ereignis prompt, tool_name, tool_input, notification_type, message ...).
Die Namen sind anders als bei Claude Code. Deshalb werden sie hier auf die Claude-Namen abgebildet, und die Auswertung
(claude_ereignisse) bleibt fuer beide gleich:

  BeforeAgent   -> UserPromptSubmit   (eine neue Aufgabe beginnt)
  BeforeTool    -> PreToolUse         (ein Werkzeug wird benutzt)
  Notification  -> Notification       (Erlaubnis-Abfrage: ToolPermission)
  AfterAgent    -> Stop               (die Antwort ist fertig)
"""
import claude_ereignisse

ZUORDNUNG = {"BeforeAgent": "UserPromptSubmit", "BeforeTool": "PreToolUse", "Notification": "Notification", "AfterAgent": "Stop"}


def intern(daten):
    """Der Claude-Name des Ereignisses ("" bei allem, was die Anzeige nicht braucht)."""
    if not isinstance(daten, dict):
        return ""
    return ZUORDNUNG.get(str(daten.get("hook_event_name", "")), "")


def als_claude(daten):
    """Das Ereignis im Format von Claude Code oder None."""
    name = intern(daten)
    if not name:
        return None
    neu = dict(daten)
    neu["hook_event_name"] = name
    if name == "Notification":
        # Gemini kennt nur die Erlaubnis-Abfrage; sie heisst dort ToolPermission
        if str(daten.get("notification_type", "")) != "ToolPermission":
            return None
        neu["notification_type"] = "permission_prompt"
        neu["message"] = str(daten.get("message") or "Gemini braucht dich")
    return neu


def meldung_aus_ereignis(daten):
    neu = als_claude(daten)
    return claude_ereignisse.meldung_aus_ereignis(neu) if neu else None
