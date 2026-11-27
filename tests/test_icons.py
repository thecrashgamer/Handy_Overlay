import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import icons
import shortcuts


def chunk(typ, inhalt):
    return struct.pack(">I", len(inhalt)) + typ + inhalt + struct.pack(">I", zlib.crc32(typ + inhalt) & 0xFFFFFFFF)


def png(breite=16, hoehe=16, farbe=(200, 30, 30, 255)):
    zeile = b"\x00" + bytes(farbe) * breite
    return (icons.PNG_KOPF + chunk(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(zeile * hoehe)) + chunk(b"IEND", b""))


class PngTests(unittest.TestCase):
    def test_gueltig(self):
        self.assertEqual(icons.pruefen_png(png(16, 16)), (16, 16))
        self.assertEqual(icons.pruefen_png(png(128, 96)), (128, 96))

    def test_ungueltig(self):
        gut = png()
        schlecht = {
            "kein Bild": "text",
            "leer": b"",
            "HTML als Bild": b"<html><script>alert(1)</script></html>" + b" " * 80,
            "SVG": b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>" + b" " * 40,
            "falsche Kennung": b"\x89PNX" + gut[4:],
            "abgeschnitten": gut[:-8],
            "ohne Ende": gut[:-12],
            "Daten nach dem Ende": gut + b"<script>alert(1)</script>",
            "kaputte Pruefsumme": gut[:30] + bytes([gut[30] ^ 0xFF]) + gut[31:],
            "zu gross": png(600, 10),
            "Breite null": png(0, 5),
            "ohne Bilddaten": icons.PNG_KOPF + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 6, 0, 0, 0)) + chunk(b"IEND", b"") + b"\x00" * 40,
            "falscher erster Abschnitt": icons.PNG_KOPF + chunk(b"IDAT", b"x" * 30) + chunk(b"IEND", b"") + b"\x00" * 30,
        }
        for name, daten in schlecht.items():
            with self.assertRaises(icons.IconFehler, msg=name):
                icons.pruefen_png(daten)

    def test_zu_viele_bytes(self):
        riesig = png(8, 8) + b"\x00" * icons.MAX_BYTES
        with self.assertRaises(icons.IconFehler):
            icons.pruefen_png(riesig)


class SpeicherTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.ordner = Path(self.t.name) / "icons"

    def tearDown(self):
        self.t.cleanup()

    def test_speichern_und_laden(self):
        name = icons.speichern(self.ordner, png())
        self.assertTrue(icons.name_gueltig(name))
        self.assertEqual(icons.laden(self.ordner, name), png())
        self.assertEqual(icons.speichern(self.ordner, png()), name)  # dasselbe Bild: derselbe Name, keine Kopie
        self.assertEqual(len(list(self.ordner.iterdir())), 1)
        self.assertNotEqual(icons.speichern(self.ordner, png(farbe=(0, 0, 255, 255))), name)

    def test_name_kommt_aus_dem_inhalt(self):
        self.assertRegex(icons.speichern(self.ordner, png()), r"^[0-9a-f]{16}\.png$")
        self.assertEqual(sorted(p.suffix for p in self.ordner.iterdir()), [".png"])  # keine Hilfsdateien

    def test_pfadtricks_liefern_nichts(self):
        geheim = Path(self.t.name) / "geheim.png"
        geheim.write_bytes(png())
        icons.speichern(self.ordner, png())
        for name in ("../geheim.png", "..\\geheim.png", str(geheim), "/etc/passwd", "a/b.png", "0123456789abcdef.png/..",
                     "0123456789ABCDEF.png", "0123456789abcdef.PNG", "0123456789abcde.png", "", None, 5):
            self.assertIsNone(icons.laden(self.ordner, name), repr(name))
            self.assertFalse(icons.existiert(self.ordner, name), repr(name))

    def test_ungueltiges_wird_nicht_gespeichert(self):
        with self.assertRaises(icons.IconFehler):
            icons.speichern(self.ordner, b"<html>")
        self.assertFalse(self.ordner.exists() and any(self.ordner.iterdir()))

    def test_grenzen(self):
        alt = icons.MAX_DATEIEN
        icons.MAX_DATEIEN = 2
        try:
            icons.speichern(self.ordner, png(farbe=(1, 1, 1, 255)))
            icons.speichern(self.ordner, png(farbe=(2, 2, 2, 255)))
            icons.speichern(self.ordner, png(farbe=(1, 1, 1, 255)))  # schon vorhanden: erlaubt
            with self.assertRaises(icons.IconFehler):
                icons.speichern(self.ordner, png(farbe=(3, 3, 3, 255)))
        finally:
            icons.MAX_DATEIEN = alt

    def test_aufraeumen_nur_alte_unbenutzte(self):
        benutzt = icons.speichern(self.ordner, png(farbe=(1, 1, 1, 255)))
        alt_unbenutzt = icons.speichern(self.ordner, png(farbe=(2, 2, 2, 255)))
        frisch_unbenutzt = icons.speichern(self.ordner, png(farbe=(3, 3, 3, 255)))
        zwei_tage = 2 * 86400
        for n in (benutzt, alt_unbenutzt):
            os.utime(self.ordner / n, (os.path.getmtime(self.ordner / n) - zwei_tage,) * 2)
        self.assertEqual(icons.aufraeumen(self.ordner, {benutzt}), 1)
        self.assertTrue(icons.existiert(self.ordner, benutzt))
        self.assertFalse(icons.existiert(self.ordner, alt_unbenutzt))
        self.assertTrue(icons.existiert(self.ordner, frisch_unbenutzt), "frisch hochgeladene Bilder muessen bleiben")

    def test_aufraeumen_ohne_ordner(self):
        self.assertEqual(icons.aufraeumen(self.ordner, set()), 0)


class ShortcutBildTests(unittest.TestCase):
    def test_bild_feld(self):
        e = shortcuts.pruefen({"name": "A", "programm": "a", "bild": "0123456789abcdef.png"})
        self.assertEqual(e["bild"], "0123456789abcdef.png")
        self.assertNotIn("bild", shortcuts.pruefen({"name": "B", "programm": "a", "bild": ""}))
        for schlecht in ("../x.png", "http://x/y.png", "0123456789abcdef.svg", "x", "0123456789ABCDEF.png", "<script>"):
            with self.assertRaises(ValueError, msg=schlecht):
                shortcuts.pruefen({"name": "A", "programm": "a", "bild": schlecht})


if __name__ == "__main__":
    unittest.main()
