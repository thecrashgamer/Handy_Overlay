import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import claude_ereignisse as ce


class AuswertungTests(unittest.TestCase):
    def test_eingabe_des_nutzers(self):
        m = ce.meldung_aus_ereignis({"hook_event_name": "UserPromptSubmit", "prompt": "Baue bitte  eine\nZeitleiste ein", "cwd": "C:\\Users\\timo\\Handy_Overlay"})
        self.assertEqual(m, {"projekt": "Handy_Overlay", "status": "arbeitet", "neu": True, "aktion": "Neue Aufgabe: Baue bitte eine Zeitleiste ein"})

    def test_werkzeuge(self):
        faelle = [
            ("Read", {"file_path": "C:\\Users\\timo\\Handy_Overlay\\server.py"}, "Liest server.py"),   # Windows-Pfad
            ("Edit", {"file_path": "/home/user/x/medien.py", "old_string": "geheim"}, "Bearbeitet medien.py"),
            ("Write", {"file_path": "C:/a/b/neu.html"}, "Schreibt neu.html"),
            ("MultiEdit", {"file_path": "x.py"}, "Bearbeitet x.py"),
            ("Bash", {"command": "curl -H 'Authorization: Bearer GEHEIM' https://x"}, "F\u00fchrt einen Befehl aus (curl)"),
            ("Bash", {"command": "git push", "description": "Sichert die \u00c4nderungen"}, "Sichert die \u00c4nderungen"),
            ("PowerShell", {"command": "Get-Process"}, "F\u00fchrt einen Befehl aus (Get-Process)"),
            ("Grep", {"pattern": "def status"}, "Sucht def status"),
            ("WebSearch", {}, "Sucht im Web"),
            ("Agent", {}, "Startet einen Hilfsagenten"),
            ("mcp__github__create_pull_request", {}, "Nutzt create_pull_request"),
            ("Unbekannt", {}, "Unbekannt"),
            ("", None, "Arbeitet"),
        ]
        for werkzeug, eingabe, soll in faelle:
            m = ce.meldung_aus_ereignis({"hook_event_name": "PreToolUse", "tool_name": werkzeug, "tool_input": eingabe})
            self.assertEqual(m["aktion"], soll, werkzeug)
            self.assertEqual(m["status"], "arbeitet")

    def test_befehle_und_inhalte_werden_nie_uebernommen(self):
        m = ce.meldung_aus_ereignis({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                     "tool_input": {"command": "curl -H 'Authorization: Bearer GEHEIM123' https://x.de"}})
        e = ce.meldung_aus_ereignis({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                                     "tool_input": {"file_path": "a.py", "new_string": "passwort = GEHEIM123"}})
        self.assertNotIn("GEHEIM123", str(m) + str(e))

    def test_erlaubnis_ist_noetig(self):
        m = ce.meldung_aus_ereignis({"hook_event_name": "PermissionRequest", "tool_name": "Edit", "tool_input": {"file_path": "C:\\a\\server.py"}})
        self.assertEqual((m["status"], m["text"]), ("wartet", "Erlaubnis n\u00f6tig: Bearbeitet server.py"))

    def test_benachrichtigungen(self):
        for art in ("permission_prompt", "elicitation_dialog", "agent_needs_input"):
            m = ce.meldung_aus_ereignis({"hook_event_name": "Notification", "notification_type": art, "message": "Claude braucht deine Erlaubnis"})
            self.assertEqual((m["status"], m["text"]), ("wartet", "Claude braucht deine Erlaubnis"), art)
        for art in ("idle_prompt", "auth_success", "plugin_notification", "", None):
            self.assertIsNone(ce.meldung_aus_ereignis({"hook_event_name": "Notification", "notification_type": art, "message": "x"}), repr(art))

    def test_fertig(self):
        self.assertEqual(ce.meldung_aus_ereignis({"hook_event_name": "Stop", "cwd": "/home/x/proj", "last_assistant_message": "Fertig"}),
                         {"projekt": "proj", "status": "fertig"})

    def test_uninteressante_ereignisse(self):
        for e in ("SessionStart", "SessionEnd", "PostToolUse", "SubagentStop", "PreCompact", "", "Unbekannt"):
            self.assertIsNone(ce.meldung_aus_ereignis({"hook_event_name": e}), e)

    def test_unbrauchbare_eingaben_werfen_nichts(self):
        for daten in (None, [], "text", 5, {}, {"hook_event_name": None}, {"hook_event_name": "PreToolUse"},
                      {"hook_event_name": "PreToolUse", "tool_input": "kein dict"},
                      {"hook_event_name": "PermissionRequest", "tool_name": 5, "tool_input": [1]},
                      {"hook_event_name": "UserPromptSubmit", "prompt": None, "cwd": 5}):
            ce.meldung_aus_ereignis(daten)  # darf nie eine Ausnahme werfen

    def test_lange_texte_werden_gekuerzt(self):
        m = ce.meldung_aus_ereignis({"hook_event_name": "UserPromptSubmit", "prompt": "wort " * 500})
        self.assertLessEqual(len(m["aktion"]), len("Neue Aufgabe: ") + 60)
        n = ce.meldung_aus_ereignis({"hook_event_name": "Notification", "notification_type": "permission_prompt", "message": "x" * 1000})
        self.assertLessEqual(len(n["text"]), 100)

    def test_dateiname(self):
        for pfad, soll in (("C:\\a\\b\\c.py", "c.py"), ("/a/b/c.py", "c.py"), ("c.py", "c.py"), ("C:\\a\\b\\", "b"), ("", ""), (None, ""), ("/", "")):
            self.assertEqual(ce.dateiname(pfad), soll, repr(pfad))


if __name__ == "__main__":
    unittest.main()
