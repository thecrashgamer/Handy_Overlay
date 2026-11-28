import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import claude_eingabe as ce

MIN = 60_000


class EingabeTests(unittest.TestCase):
    def setUp(self):
        self.e = ce.Eingabe()

    def test_einreihen_und_abholen(self):
        a = self.e.einreihen("  Mach den Button gruen  ", "Timo", 1000)
        self.assertEqual((a["id"], a["status"], a["text"]), (1, "wartet", "Mach den Button gruen"))
        self.assertEqual(self.e.abholen(2000), "Mach den Button gruen")
        self.assertIsNone(self.e.abholen(3000), "eine Anweisung darf nur einmal uebergeben werden")
        self.assertEqual(self.e.anzeige()[0]["status"], "uebergeben")

    def test_mehrere_werden_zusammen_in_reihenfolge_uebergeben(self):
        self.e.einreihen("erstens", "Timo", 1000)
        self.e.einreihen("zweitens", "Timo", 2000)
        self.assertEqual(self.e.abholen(3000), "erstens\n\nzweitens")
        self.assertEqual([x["status"] for x in self.e.anzeige()], ["uebergeben", "uebergeben"])

    def test_leer_und_zu_lang(self):
        for text in ("", "   ", None, "\n\t"):
            with self.assertRaises(ce.EingabeFehler, msg=repr(text)):
                self.e.einreihen(text, "Timo", 0)
        with self.assertRaises(ce.EingabeFehler):
            self.e.einreihen("x" * (ce.MAX_TEXT + 1), "Timo", 0)
        self.assertEqual(self.e.einreihen("x" * ce.MAX_TEXT, "Timo", 0)["status"], "wartet")

    def test_hoechstens_fuenf_wartende(self):
        for i in range(ce.MAX_WARTEND):
            self.e.einreihen(f"a{i}", "Timo", i)
        with self.assertRaises(ce.EingabeFehler):
            self.e.einreihen("zu viel", "Timo", 10)
        self.e.abholen(20)
        self.assertEqual(self.e.einreihen("jetzt wieder", "Timo", 30)["status"], "wartet")

    def test_verfall_nach_15_minuten(self):
        self.e.einreihen("alt", "Timo", 0)
        self.assertEqual(self.e.abholen(14 * MIN), "alt")
        self.e.einreihen("zu alt", "Timo", 100 * MIN)
        self.assertIsNone(self.e.abholen(100 * MIN + 16 * MIN), "nach 15 Minuten darf nichts mehr uebergeben werden")
        self.assertEqual(self.e.anzeige()[-1]["status"], "verfallen")

    def test_aufraeumen_meldet_aenderungen(self):
        self.e.einreihen("x", "Timo", 0)
        self.assertFalse(self.e.aufraeumen(MIN))
        self.assertTrue(self.e.aufraeumen(20 * MIN))
        self.assertFalse(self.e.aufraeumen(21 * MIN))

    def test_zurueckziehen(self):
        a = self.e.einreihen("doch nicht", "Timo", 0)
        self.assertTrue(self.e.zurueckziehen(a["id"]))
        self.assertFalse(self.e.zurueckziehen(a["id"]), "nur wartende lassen sich zurueckziehen")
        self.assertFalse(self.e.zurueckziehen(999))
        self.assertIsNone(self.e.abholen(1))
        b = self.e.einreihen("schon weg", "Timo", 2)
        self.e.abholen(3)
        self.assertFalse(self.e.zurueckziehen(b["id"]), "Uebergebenes laesst sich nicht mehr zurueckziehen")

    def test_ausschalten_leert_die_warteschlange(self):
        self.e.einreihen("a", "Timo", 0)
        self.e.einreihen("b", "Timo", 0)
        self.e.leeren()
        self.assertIsNone(self.e.abholen(1))

    def test_anzeige_ist_begrenzt_und_nach_benutzer_filterbar(self):
        for i in range(30):
            self.e.einreihen(f"n{i}", "Timo" if i % 2 else "Anna", i)
            self.e.abholen(i)
        self.assertLessEqual(len(self.e.anzeige()), ce.MAX_ANZEIGE)
        self.assertTrue(all(x["von"] == "Anna" for x in self.e.anzeige(nur_von="Anna")))
        self.assertEqual(self.e.anzeige()[-1]["text"], "n29")

    def test_ids_steigen(self):
        ids = [self.e.einreihen(f"t{i}", "Timo", i)["id"] for i in range(3)]
        self.assertEqual(ids, [1, 2, 3])
        self.assertNotIn("erledigt", self.e.anzeige()[0])  # nur Noetiges nach aussen


if __name__ == "__main__":
    unittest.main()
