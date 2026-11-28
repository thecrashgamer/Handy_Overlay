import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gemini_einrichten as ge
import gemini_ereignisse as gev


class EreignisTests(unittest.TestCase):
    def test_neue_aufgabe(self):
        m = gev.meldung_aus_ereignis({"hook_event_name": "BeforeAgent", "prompt": "Mach das", "cwd": "C:\\Projekte\\Haus"})
        self.assertEqual(m["status"], "arbeitet")
        self.assertTrue(m["neu"])
        self.assertEqual(m["projekt"], "Haus")
        self.assertIn("Mach das", m["aktion"])

    def test_werkzeuge_von_gemini(self):
        def aktion(name, eingabe):
            return gev.meldung_aus_ereignis({"hook_event_name": "BeforeTool", "tool_name": name, "tool_input": eingabe})["aktion"]
        self.assertEqual(aktion("read_file", {"file_path": "/a/b/server.py"}), "Liest server.py")
        self.assertEqual(aktion("read_file", {"absolute_path": "C:\\a\\b.py"}), "Liest b.py")
        self.assertEqual(aktion("replace", {"file_path": "/a/x.js"}), "Bearbeitet x.js")
        self.assertEqual(aktion("write_file", {"file_path": "/a/y.js"}), "Schreibt y.js")
        self.assertIn("(npm)", aktion("run_shell_command", {"command": "npm test"}))
        self.assertEqual(aktion("google_web_search", {"query": "x"}), "Sucht im Web")

    def test_erlaubnis_abfrage(self):
        m = gev.meldung_aus_ereignis({"hook_event_name": "Notification", "notification_type": "ToolPermission", "message": "Shell erlauben?"})
        self.assertEqual((m["status"], m["text"]), ("wartet", "Shell erlauben?"))

    def test_andere_hinweise_ignorieren(self):
        self.assertIsNone(gev.meldung_aus_ereignis({"hook_event_name": "Notification", "notification_type": "Sonstiges"}))

    def test_fertig(self):
        m = gev.meldung_aus_ereignis({"hook_event_name": "AfterAgent", "prompt_response": "Fertig."})
        self.assertEqual(m["status"], "fertig")

    def test_unbekanntes_ereignis(self):
        for name in ("SessionStart", "AfterTool", "BeforeModel", "AfterModel", "PreToolUse", "Stop"):
            self.assertIsNone(gev.meldung_aus_ereignis({"hook_event_name": name}), name)
        self.assertEqual(gev.intern({"hook_event_name": "AfterAgent"}), "Stop")
        self.assertEqual(gev.intern("kein dict"), "")


class EinrichtenTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.pfad = Path(self.t.name) / ".gemini" / "settings.json"
        self.skript = Path(self.t.name) / "gemini_status.py"
        self.skript.write_text("# test", encoding="utf-8")

    def tearDown(self):
        self.t.cleanup()

    def lesen(self):
        return json.loads(self.pfad.read_text(encoding="utf-8"))

    def test_neue_datei(self):
        ge.einrichten(self.skript, self.pfad)
        h = self.lesen()["hooks"]
        self.assertEqual(sorted(h), sorted(ge.EREIGNISSE))
        for ereignis, gruppen in h.items():
            handler = gruppen[0]["hooks"][0]
            self.assertEqual(handler["type"], "command")
            self.assertIn("gemini_status.py", handler["command"])
            self.assertEqual(handler["timeout"], 600_000 if ereignis == "AfterAgent" else 5000)  # Gemini rechnet in Millisekunden
        self.assertTrue(ge.pruefen(self.pfad)["python_ok"])
        self.assertEqual(ge.pruefen(self.pfad)["fehlend"], [])

    def test_fremdes_bleibt_und_doppeltes_einrichten(self):
        self.pfad.parent.mkdir(parents=True)
        fremd = {"hooks": [{"type": "command", "command": "echo hallo"}]}
        self.pfad.write_text(json.dumps({"theme": "dunkel", "hooks": {"AfterAgent": [fremd], "SessionStart": [fremd]}}), encoding="utf-8")
        ge.einrichten(self.skript, self.pfad)
        ge.einrichten(self.skript, self.pfad)
        daten = self.lesen()
        self.assertEqual(daten["theme"], "dunkel")
        self.assertEqual(daten["hooks"]["SessionStart"], [fremd])
        self.assertEqual(len(daten["hooks"]["AfterAgent"]), 2)  # fremder Eintrag + genau ein eigener
        self.assertEqual(daten["hooks"]["AfterAgent"][0], fremd)

    def test_entfernen_laesst_fremdes(self):
        self.pfad.parent.mkdir(parents=True)
        fremd = {"hooks": [{"type": "command", "command": "echo hallo"}]}
        self.pfad.write_text(json.dumps({"hooks": {"AfterAgent": [fremd]}}), encoding="utf-8")
        ge.einrichten(self.skript, self.pfad)
        erg = ge.entfernen(self.pfad)
        self.assertEqual(erg["entfernt"], len(ge.EREIGNISSE))
        self.assertEqual(self.lesen(), {"hooks": {"AfterAgent": [fremd]}})
        self.assertEqual(ge.pruefen(self.pfad)["ereignisse"], [])

    def test_kaputte_datei_bleibt_unveraendert(self):
        self.pfad.parent.mkdir(parents=True)
        self.pfad.write_text("{kaputt", encoding="utf-8")
        with self.assertRaises(ge.EinrichtungsFehler):
            ge.einrichten(self.skript, self.pfad)
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), "{kaputt")
        self.assertFalse(ge.pruefen(self.pfad)["gueltig"])

    def test_hooks_abgeschaltet_wird_gemeldet(self):
        self.pfad.parent.mkdir(parents=True)
        self.pfad.write_text(json.dumps({"hooksConfig": {"enabled": False}}), encoding="utf-8")
        self.assertTrue(ge.pruefen(self.pfad)["hinweise"])

    def test_pfad_mit_leerzeichen(self):
        d = Path(self.t.name) / "mein ordner"
        d.mkdir()
        skript = d / "gemini_status.py"
        skript.write_text("#", encoding="utf-8")
        ge.einrichten(skript, self.pfad)
        self.assertTrue(ge.pruefen(self.pfad)["python_ok"])


if __name__ == "__main__":
    unittest.main()
