import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import claude_einrichten as ce


class EinrichtenTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.pfad = Path(self.t.name) / ".claude" / "settings.json"

    def tearDown(self):
        self.t.cleanup()

    def lesen(self):
        return json.loads(self.pfad.read_text(encoding="utf-8"))

    def schreiben(self, daten):
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(json.dumps(daten), encoding="utf-8")

    def test_neue_datei_mit_dokumentierter_struktur(self):
        ce.einrichten("http", 8000, self.pfad)
        h = self.lesen()["hooks"]
        self.assertEqual(sorted(h), sorted(ce.EREIGNISSE))
        for ereignis, gruppen in h.items():
            self.assertIsInstance(gruppen, list)
            self.assertEqual(len(gruppen), 1)
            handler = gruppen[0]["hooks"][0]
            self.assertEqual(handler, {"type": "http", "url": "http://127.0.0.1:8000/claude-hook",
                                       "timeout": 600 if ereignis == "Stop" else 3})
        self.assertEqual(h["Notification"][0]["matcher"], ce.BENACHRICHTIGUNG_MATCHER)
        for e in ("UserPromptSubmit", "PreToolUse", "PermissionRequest", "Stop"):
            self.assertNotIn("matcher", h[e][0], e + ": Matcher weglassen")

    def test_python_form_ohne_shell(self):
        exe = Path(self.t.name) / "python.exe"
        skript = Path(self.t.name) / "hooks" / "claude_status.py"
        ce.einrichten("python", 8000, self.pfad, python_exe=str(exe), skript=skript)
        h = self.lesen()["hooks"]
        for ereignis, gruppen in h.items():
            handler = gruppen[0]["hooks"][0]
            self.assertEqual((handler["type"], handler["command"], handler["args"]), ("command", str(exe), [str(skript)]))
            self.assertEqual(handler.get("async", False), ereignis == "PreToolUse")  # nur PreToolUse laeuft im Hintergrund
        # JSON-Escaping: der Pfad muss unveraendert wieder herauskommen, auch mit Rueckwaertsschraegstrichen
        ce.einrichten("python", 8000, self.pfad, python_exe="C:\\Users\\timo\\AppData\\Local\\Python\\python.exe", skript="C:\\Users\\timo\\Ordner mit Leerzeichen\\hooks\\claude_status.py")
        handler = self.lesen()["hooks"]["Stop"][0]["hooks"][0]
        self.assertEqual(handler["command"], "C:\\Users\\timo\\AppData\\Local\\Python\\python.exe")
        self.assertEqual(handler["args"], ["C:\\Users\\timo\\Ordner mit Leerzeichen\\hooks\\claude_status.py"])

    def test_nie_pythonw(self):
        verz = Path(self.t.name)
        (verz / "python.exe").write_text("")
        (verz / "pythonw.exe").write_text("")
        self.assertEqual(ce.python_ohne_fenster_problem(str(verz / "pythonw.exe")), str(verz / "python.exe"))

    def test_fremde_einstellungen_und_hooks_bleiben(self):
        fremd = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mein-pruefer.sh"}]}],
                           "SessionStart": [{"hooks": [{"type": "command", "command": "echo hallo"}]}]},
                 "permissions": {"allow": ["Bash(git status)"]}, "model": "opus", "env": {"A": "1"}}
        self.schreiben(fremd)
        ce.einrichten("http", 8000, self.pfad)
        d = self.lesen()
        self.assertEqual((d["permissions"], d["model"], d["env"]), (fremd["permissions"], "opus", {"A": "1"}))
        self.assertEqual(d["hooks"]["SessionStart"], fremd["hooks"]["SessionStart"])
        pre = d["hooks"]["PreToolUse"]
        self.assertEqual(pre[0], fremd["hooks"]["PreToolUse"][0])  # der fremde Hook steht unveraendert vorn
        self.assertEqual(len(pre), 2)

    def test_mehrfach_einrichten_verdoppelt_nichts(self):
        for _ in range(3):
            ce.einrichten("http", 8000, self.pfad)
        for gruppen in self.lesen()["hooks"].values():
            self.assertEqual(len(gruppen), 1)

    def test_wechsel_der_art_und_des_ports_ersetzt_nur_unsere(self):
        self.schreiben({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mein-stop.sh"}]}]}})
        ce.einrichten("http", 8000, self.pfad)
        ce.einrichten("python", 8000, self.pfad, python_exe="p.exe", skript="s/claude_status.py")
        ce.einrichten("http", 9001, self.pfad)
        stop = self.lesen()["hooks"]["Stop"]
        self.assertEqual(len(stop), 2)
        self.assertEqual(stop[0]["hooks"][0]["command"], "mein-stop.sh")
        self.assertEqual(stop[1]["hooks"][0]["url"], "http://127.0.0.1:9001/claude-hook")

    def test_alte_shell_eintraege_werden_ersetzt(self):
        alt = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python C:\\Phonebox\\hooks\\claude_status.py"}]}],
                         "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python C:\\Phonebox\\hooks\\claude_status.py"}]}]}}
        self.schreiben(alt)
        ce.einrichten("http", 8000, self.pfad)
        text = json.dumps(self.lesen())
        self.assertNotIn("claude_status.py", text)

    def test_entfernen(self):
        fremd = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mein-stop.sh"}]}]}, "model": "opus"}
        self.schreiben(fremd)
        ce.einrichten("http", 8000, self.pfad)
        erg = ce.entfernen(self.pfad)
        self.assertEqual(erg["entfernt"], 5)
        self.assertEqual(self.lesen(), fremd)  # genau der Ausgangszustand
        self.assertEqual(ce.entfernen(self.pfad)["entfernt"], 0)  # ein zweites Mal: nichts zu tun
        leer = Path(self.t.name) / "neu" / "settings.json"
        ce.einrichten("http", 8000, leer)
        ce.entfernen(leer)
        self.assertNotIn("hooks", json.loads(leer.read_text()))  # keine leeren Reste

    def test_kaputte_datei_wird_nicht_angefasst(self):
        self.pfad.parent.mkdir(parents=True)
        for inhalt in ('{"hooks": {}, }', '// Kommentar\n{"a": 1}', "kein json", "[1, 2]"):
            self.pfad.write_text(inhalt, encoding="utf-8")
            with self.assertRaises(ce.EinrichtungsFehler, msg=inhalt):
                ce.einrichten("http", 8000, self.pfad)
            with self.assertRaises(ce.EinrichtungsFehler):
                ce.entfernen(self.pfad)
            self.assertEqual(self.pfad.read_text(encoding="utf-8"), inhalt)
        for daten in ({"hooks": []}, {"hooks": {"Stop": "kaputt"}}):
            self.schreiben(daten)
            vorher = self.pfad.read_text(encoding="utf-8")
            with self.assertRaises(ce.EinrichtungsFehler):
                ce.einrichten("http", 8000, self.pfad)
            self.assertEqual(self.pfad.read_text(encoding="utf-8"), vorher)

    def test_unbekannte_art(self):
        with self.assertRaises(ce.EinrichtungsFehler):
            ce.einrichten("shell", 8000, self.pfad)
        self.assertFalse(self.pfad.exists())

    def test_sicherung(self):
        self.schreiben({"model": "alt"})
        erg = ce.einrichten("http", 8000, self.pfad)
        self.assertEqual(json.loads(Path(erg["sicherung"]).read_text())["model"], "alt")
        self.assertIsNone(ce.einrichten("http", 8000, Path(self.t.name) / "x" / "settings.json")["sicherung"])  # nichts zu sichern
        for _ in range(5):
            ce.einrichten("http", 8000, self.pfad)
            os.utime(self.pfad, None)
        self.assertLessEqual(len(list(self.pfad.parent.glob("settings.json.phonebox-sicherung-*"))), ce.SICHERUNGEN_BEHALTEN)
        self.assertEqual(list(self.pfad.parent.glob("*.neu")), [])

    def test_utf8_mit_bom_und_umlaute(self):
        self.pfad.parent.mkdir(parents=True)
        self.pfad.write_bytes(b"\xef\xbb\xbf" + json.dumps({"hinweis": "Gr\u00fc\u00dfe"}).encode("utf-8"))
        ce.einrichten("http", 8000, self.pfad)
        self.assertEqual(self.lesen()["hinweis"], "Gr\u00fc\u00dfe")

    def test_claude_config_dir(self):
        alt = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = self.t.name
        try:
            self.assertEqual(ce.settings_pfad(), Path(self.t.name) / "settings.json")
        finally:
            os.environ.pop("CLAUDE_CONFIG_DIR") if alt is None else os.environ.update(CLAUDE_CONFIG_DIR=alt)


class PruefenTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.pfad = Path(self.t.name) / "settings.json"

    def tearDown(self):
        self.t.cleanup()

    def test_ohne_datei(self):
        p = ce.pruefen(8000, self.pfad)
        self.assertEqual((p["vorhanden"], p["gueltig"], p["modus"], p["ereignisse"]), (False, True, None, []))
        self.assertEqual(p["fehlend"], list(ce.EREIGNISSE))

    def test_eingerichtet(self):
        ce.einrichten("http", 8000, self.pfad)
        p = ce.pruefen(8000, self.pfad)
        self.assertEqual((p["modus"], p["fehlend"], p["url_passt"], p["hinweise"]), ("http", [], True, []))

    def test_falscher_port_wird_gemeldet(self):
        ce.einrichten("http", 8000, self.pfad)
        p = ce.pruefen(8123, self.pfad)
        self.assertFalse(p["url_passt"])
        self.assertTrue(any("Port" in h for h in p["hinweise"]))

    def test_python_programm_fehlt(self):
        ce.einrichten("python", 8000, self.pfad, python_exe="/gibt/es/nicht/python.exe", skript="/gibt/es/nicht/claude_status.py")
        p = ce.pruefen(8000, self.pfad)
        self.assertEqual(p["modus"], "python")
        self.assertFalse(p["python_ok"])
        self.assertTrue(any("gibt es nicht mehr" in h for h in p["hinweise"]))

    def test_hooks_abgeschaltet(self):
        ce.einrichten("http", 8000, self.pfad)
        d = json.loads(self.pfad.read_text())
        d["disableAllHooks"] = True
        self.pfad.write_text(json.dumps(d))
        self.assertTrue(any("disableAllHooks" in h for h in ce.pruefen(8000, self.pfad)["hinweise"]))

    def test_kaputte_datei(self):
        self.pfad.write_text("{kaputt")
        p = ce.pruefen(8000, self.pfad)
        self.assertFalse(p["gueltig"])
        self.assertIn("JSON", p["fehler"])

    def test_teilweise_eingerichtet(self):
        ce.einrichten("http", 8000, self.pfad)
        d = json.loads(self.pfad.read_text())
        del d["hooks"]["Stop"]
        self.pfad.write_text(json.dumps(d))
        self.assertEqual(ce.pruefen(8000, self.pfad)["fehlend"], ["Stop"])


if __name__ == "__main__":
    unittest.main()
