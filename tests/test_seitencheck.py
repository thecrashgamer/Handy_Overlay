import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import seitencheck


class SeitencheckTests(unittest.TestCase):
    def test_passt(self):
        self.assertIsNone(seitencheck.warnung('var SEITE = "v12";', "v12 (Selbstcheck)"))

    def test_alte_version(self):
        self.assertIn("v10", seitencheck.warnung('var SEITE = "v10";', "v12 (Selbstcheck)"))

    def test_sehr_alte_seite_ohne_kennung(self):
        self.assertIn("aelter", seitencheck.warnung("<html><body>alt</body></html>", "v12 (x)"))

    def test_einblenden(self):
        html = seitencheck.mit_warnung("<html><body>x</body></html>", "Warnung <b>")
        self.assertIn("Warnung &lt;b>", html)
        self.assertTrue(html.index("Warnung") < html.index("</body>"))


if __name__ == "__main__":
    unittest.main()
