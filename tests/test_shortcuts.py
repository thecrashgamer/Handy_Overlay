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

    def test_standarddatei_ist_gueltig(self):
        pfad = os.path.join(os.path.dirname(__file__), "..", "shortcuts.json")
        liste = shortcuts.laden(pfad)
        self.assertGreater(len(liste), 0)
        for e in liste:
            if "tasten" in e:
                shortcuts.tasten_parsen(e["tasten"])


if __name__ == "__main__":
    unittest.main()
