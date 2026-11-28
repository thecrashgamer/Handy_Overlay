import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shortcuts


class ShortcutTests(unittest.TestCase):
    def test_tasten(self):
        self.assertEqual(shortcuts.tasten_parsen("ctrl+shift+esc"), [0x11, 0x10, 0x1B])
        self.assertEqual(shortcuts.tasten_parsen("Win + D"), [0x5B, 0x44])
        self.assertEqual(shortcuts.tasten_parsen("f5"), [0x74])

    def test_unbekannte_taste(self):
        with self.assertRaises(ValueError):
            shortcuts.tasten_parsen("ctrl+quatsch")

    def test_laden_ueberspringt_kaputtes(self):
        daten = [{"name": "A", "programm": "calc.exe"}, {"name": "B"}, "x", {"programm": "y"},
                 {"name": "C", "tasten": "win+d"}]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(daten, f)
        try:
            self.assertEqual([e["name"] for e in shortcuts.laden(f.name)], ["A", "C"])
        finally:
            os.unlink(f.name)

    def test_aktionen(self):
        daten = [{"name": "S", "aktion": "sperren"}, {"name": "X", "aktion": "unbekannt"},
                 {"name": "Aus", "aktion": "herunterfahren"}]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(daten, f)
        try:
            self.assertEqual([e["name"] for e in shortcuts.laden(f.name)], ["S", "Aus"])
        finally:
            os.unlink(f.name)

    def test_bestaetigung(self):
        self.assertTrue(shortcuts.braucht_bestaetigung({"name": "Aus", "aktion": "herunterfahren"}))
        self.assertTrue(shortcuts.braucht_bestaetigung({"name": "A", "programm": "x", "bestaetigen": True}))
        self.assertFalse(shortcuts.braucht_bestaetigung({"name": "Sperren", "aktion": "sperren"}))
        self.assertFalse(shortcuts.braucht_bestaetigung({"name": "Rechner", "programm": "calc.exe"}))

    def test_shutdown_befehl(self):
        befehl = shortcuts.shutdown_befehl()
        self.assertEqual(befehl[:4], ["shutdown", "/s", "/t", str(shortcuts.HERUNTERFAHREN_SEKUNDEN)])

    def test_aktionen_nur_unter_windows(self):
        if sys.platform != "win32":
            with self.assertRaises(RuntimeError):
                shortcuts.ausfuehren({"name": "S", "aktion": "sperren"})

    def test_ruhemodus(self):
        e = {"name": "Ruhe", "aktion": "ruhemodus"}
        self.assertIn("ruhemodus", shortcuts.AKTIONEN)
        self.assertIn("ruhemodus", shortcuts.AKTION_NAMEN)
        self.assertEqual(shortcuts.meldung(e), "PC geht in den Ruhemodus")
        self.assertFalse(shortcuts.braucht_admin(e))
        self.assertTrue(shortcuts.braucht_bestaetigung({**e, "bestaetigen": True}))
        if sys.platform != "win32":
            with self.assertRaises(RuntimeError):
                shortcuts.ausfuehren(e)

    def test_standarddatei_ist_gueltig(self):
        pfad = os.path.join(os.path.dirname(__file__), "..", "shortcuts.json")
        liste = shortcuts.laden(pfad)
        self.assertGreater(len(liste), 0)
        for e in liste:
            if "tasten" in e:
                shortcuts.tasten_parsen(e["tasten"])


class RechteTests(unittest.TestCase):
    ADMIN = {"musik": True, "shortcuts": True, "admin": True}
    NUTZER = {"musik": True, "shortcuts": True, "admin": False}
    GAST = {"musik": True, "shortcuts": False, "admin": False}

    def test_herunterfahren_nur_admin(self):
        for aktion in ("herunterfahren", "herunterfahren_stoppen"):
            e = {"name": "X", "aktion": aktion}
            self.assertTrue(shortcuts.braucht_admin(e))
            self.assertTrue(shortcuts.darf_ausloesen(e, self.ADMIN))
            self.assertFalse(shortcuts.darf_ausloesen(e, self.NUTZER))
            self.assertFalse(shortcuts.darf_ausloesen(e, self.GAST))

    def test_normale_kachel(self):
        e = {"name": "Rechner", "programm": "calc.exe"}
        self.assertTrue(shortcuts.darf_ausloesen(e, self.ADMIN))
        self.assertTrue(shortcuts.darf_ausloesen(e, self.NUTZER))
        self.assertFalse(shortcuts.darf_ausloesen(e, self.GAST))

    def test_nur_admin_flag(self):
        e = shortcuts.pruefen({"name": "Gefaehrlich", "programm": "cmd.exe", "nur_admin": True})
        self.assertTrue(e["nur_admin"])
        self.assertFalse(shortcuts.darf_ausloesen(e, self.NUTZER))
        self.assertTrue(shortcuts.darf_ausloesen(e, self.ADMIN))
        self.assertNotIn("nur_admin", shortcuts.pruefen({"name": "A", "programm": "a", "nur_admin": False}))
        self.assertNotIn("nur_admin", shortcuts.pruefen({"name": "B", "programm": "a", "nur_admin": "ja"}))  # nur echtes True

    def test_ohne_rechte_nichts(self):
        self.assertFalse(shortcuts.darf_ausloesen({"name": "A", "programm": "a"}, {}))


class PruefenTests(unittest.TestCase):
    def test_gueltige_eintraege(self):
        self.assertEqual(shortcuts.pruefen({"name": " Rechner ", "icon": "🧮", "programm": "calc.exe"}),
                         {"name": "Rechner", "icon": "🧮", "programm": "calc.exe"})
        self.assertEqual(shortcuts.pruefen({"name": "TM", "tasten": "Ctrl + Shift + Esc"})["tasten"], "ctrl+shift+esc")
        self.assertEqual(shortcuts.pruefen({"name": "Aus", "aktion": "herunterfahren", "frage": " Wirklich? "})["frage"], "Wirklich?")
        e = shortcuts.pruefen({"name": "N", "programm": "notepad.exe", "argumente": ["a b.txt"], "bestaetigen": True})
        self.assertEqual((e["argumente"], e["bestaetigen"]), (["a b.txt"], True))

    def test_ungueltige_eintraege(self):
        schlecht = [
            "text", {}, {"name": ""}, {"name": "x" * 31, "programm": "a"},
            {"name": "A"},                                                    # nichts gewaehlt
            {"name": "A", "programm": "a", "tasten": "win+d"},                # zwei Arten
            {"name": "A", "programm": "a\nb"},                                # Steuerzeichen
            {"name": "A", "programm": "a", "argumente": "nein"},
            {"name": "A", "programm": "a", "argumente": ["x"] * 11},
            {"name": "A", "tasten": "ctrl+quatsch"},
            {"name": "A", "aktion": "alles-loeschen"},
            {"name": "A", "icon": "x" * 9, "programm": "a"},
            {"name": "A", "programm": "a", "frage": "x" * 101},
        ]
        for e in schlecht:
            with self.assertRaises(ValueError, msg=str(e)):
                shortcuts.pruefen(e)

    def test_liste(self):
        ok = [{"name": "A", "programm": "a"}, {"name": "B", "tasten": "win+d"}]
        self.assertEqual(len(shortcuts.pruefen_liste(ok)), 2)
        with self.assertRaises(ValueError) as f:
            shortcuts.pruefen_liste(ok + [{"name": "a", "programm": "x"}])  # gleicher Name, egal ob gross/klein
        self.assertIn("doppelt", str(f.exception))
        with self.assertRaises(ValueError) as f:
            shortcuts.pruefen_liste([{"name": "A", "programm": "a"}, {"name": "B"}])
        self.assertIn("Nr. 2", str(f.exception))
        with self.assertRaises(ValueError):
            shortcuts.pruefen_liste([{"name": f"S{i}", "programm": "a"} for i in range(shortcuts.MAX_SHORTCUTS + 1)])
        with self.assertRaises(ValueError):
            shortcuts.pruefen_liste("quatsch")

    def test_speichern_sicher_mit_sicherung(self):
        with tempfile.TemporaryDirectory() as ordner:
            pfad = os.path.join(ordner, "unter", "shortcuts.json")
            shortcuts.speichern(pfad, [{"name": "A", "programm": "a"}])
            shortcuts.speichern(pfad, [{"name": "B", "programm": "b"}])
            self.assertEqual(shortcuts.laden(pfad)[0]["name"], "B")
            self.assertEqual(shortcuts.laden(pfad + ".bak")[0]["name"], "A")  # alte Fassung bleibt
            self.assertFalse(os.path.exists(pfad + ".neu"))                   # keine Hilfsdatei uebrig
            shortcuts.speichern(pfad, [{"name": "Umlaut \u00e4", "icon": "🔒", "aktion": "sperren"}])
            with open(pfad, encoding="utf-8") as d:
                self.assertIn("Umlaut \u00e4", d.read())  # lesbar, nicht als \\u-Folge


if __name__ == "__main__":
    unittest.main()
