import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import medien


def s(app, spielt=False):
    return (app, spielt, app + "-sitzung")


class SitzungWahlTests(unittest.TestCase):
    def test_spotify(self):
        liste = [s("Chrome", True), s("Spotify.exe"), s("com.github.th-ch.youtube-music", True)]
        self.assertEqual(medien.passende_sitzung(liste, "spotify"), "Spotify.exe-sitzung")
        self.assertIsNone(medien.passende_sitzung([s("Chrome")], "spotify"))

    def test_ytmusic_eigene_app_geht_vor_browser(self):
        liste = [s("Chrome", True), s("com.github.th-ch.youtube-music"), s("Spotify.exe", True)]
        self.assertEqual(medien.passende_sitzung(liste, "ytmusic"), "com.github.th-ch.youtube-music-sitzung")

    def test_ytmusic_im_browser_die_spielende(self):
        liste = [s("Firefox"), s("MSEdge", True), s("Spotify.exe", True)]
        self.assertEqual(medien.passende_sitzung(liste, "ytmusic"), "MSEdge-sitzung")
        self.assertEqual(medien.passende_sitzung([s("Chrome._crx_abc"), s("Brave")], "ytmusic"), "Chrome._crx_abc-sitzung")

    def test_ytmusic_ohne_passende_sitzung(self):
        self.assertIsNone(medien.passende_sitzung([s("Spotify.exe", True)], "ytmusic"))
        self.assertIsNone(medien.passende_sitzung([], "ytmusic"))

    def test_unbekannte_quelle_ist_spotify(self):
        m = medien.TestMedien()
        m.quelle_setzen("unsinn")
        self.assertEqual(m.quelle, "spotify")


if __name__ == "__main__":
    unittest.main()
