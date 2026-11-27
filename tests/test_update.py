import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import update

REPO = Path(__file__).resolve().parent.parent


def zip_bauen(pfad, dateien, wurzel="Handy_Overlay-main/"):
    with zipfile.ZipFile(pfad, "w") as z:
        for name, inhalt in dateien.items():
            z.writestr(wurzel + name, inhalt)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.ziel = Path(self.t.name) / "phonebox"
        (self.ziel / "daten").mkdir(parents=True)
        (self.ziel / "server.py").write_text('VERSION = "v1 (alt)"\n', encoding="utf-8")
        (self.ziel / "gleich.txt").write_text("unveraendert", encoding="utf-8")
        (self.ziel / "daten" / "phonebox.db").write_text("MEINE KONTEN", encoding="utf-8")
        (self.ziel / "daten" / "shortcuts.json").write_text("[]", encoding="utf-8")
        self.zip = os.path.join(self.t.name, "neu.zip")

    def tearDown(self):
        self.t.cleanup()

    def lauf(self, **kw):
        kw.setdefault("neustart", False)
        kw.setdefault("pip", False)
        return update.aktualisieren(self.zip, self.ziel, **kw)

    def test_dateien_tauschen_daten_bleiben(self):
        zip_bauen(self.zip, {
            "server.py": 'VERSION = "v2 (neu)"\n', "gleich.txt": "unveraendert", "neu.html": "<b>neu</b>",
            "daten/phonebox.db": "DARF NIE ANKOMMEN", ".git/config": "nein", "__pycache__/x.pyc": "nein",
        })
        r = self.lauf()
        self.assertEqual((r["neu"], r["geaendert"]), (1, 1))
        self.assertIn("v2", update.version_lesen(self.ziel))
        self.assertEqual((self.ziel / "neu.html").read_text(), "<b>neu</b>")
        self.assertEqual((self.ziel / "daten" / "phonebox.db").read_text(), "MEINE KONTEN")
        self.assertFalse((self.ziel / ".git").exists())
        self.assertFalse((self.ziel / "__pycache__").exists())
        self.assertEqual([p.name for p in self.ziel.glob("*.update-neu")], [])  # keine Hilfsdateien uebrig

    def test_sicherung_und_zurueck(self):
        zip_bauen(self.zip, {"server.py": 'VERSION = "v2 (neu)"\n', "gleich.txt": "unveraendert"})
        r = self.lauf()
        gesichert = Path(r["sicherung"]) / "server.py"
        self.assertIn("v1", gesichert.read_text())  # nur die geaenderte Datei wurde gesichert
        self.assertFalse((Path(r["sicherung"]) / "gleich.txt").exists())
        self.assertEqual(update.zuruecksetzen(self.ziel), 1)
        self.assertIn("v1", update.version_lesen(self.ziel))

    def test_nur_drei_sicherungen(self):
        for i in range(5):
            zip_bauen(self.zip, {"server.py": f'VERSION = "v{i + 2}"\n'})
            self.lauf()
            time.sleep(1.1)  # Zeitstempel in Sekunden
        self.assertEqual(len(list(update.sicherung_ordner(self.ziel).iterdir())), update.SICHERUNGEN_BEHALTEN)

    def test_nichts_zu_tun(self):
        zip_bauen(self.zip, {"server.py": 'VERSION = "v1 (alt)"\n', "gleich.txt": "unveraendert"})
        self.assertEqual(self.lauf()["geaendert"], 0)
        self.assertFalse(update.sicherung_ordner(self.ziel).exists())

    def test_probelauf_aendert_nichts(self):
        zip_bauen(self.zip, {"server.py": 'VERSION = "v2"\n', "neu.txt": "x"})
        r = self.lauf(trocken=True)
        self.assertTrue(r["trocken"])
        self.assertIn("v1", update.version_lesen(self.ziel))
        self.assertFalse((self.ziel / "neu.txt").exists())

    def test_boese_zip_dateien_werden_abgelehnt(self):
        boese = [
            {"server.py": "x", "../ausbruch.py": "boese"},
            {"server.py": "x", "/etc/passwd": "boese"},
            {"server.py": "x", "a/../../ausbruch.py": "boese"},
            {"server.py": "x", "C:/Windows/system.ini": "boese"},
            {"server.py": "x", "a\\..\\b.py": "boese"},
        ]
        for dateien in boese:
            with zipfile.ZipFile(self.zip, "w") as z:
                for n, c in dateien.items():
                    z.writestr(n, c)
            with self.assertRaises(update.UpdateFehler, msg=str(list(dateien))):
                self.lauf()
        self.assertIn("v1", update.version_lesen(self.ziel))
        self.assertFalse((Path(self.t.name) / "ausbruch.py").exists())

    def test_verknuepfung_in_zip_wird_abgelehnt(self):
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr("server.py", "x")
            info = zipfile.ZipInfo("link")
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "/etc/passwd")
        with self.assertRaises(update.UpdateFehler):
            self.lauf()

    def test_falsche_oder_kaputte_dateien(self):
        zip_bauen(self.zip, {"anderes.txt": "x"})
        with self.assertRaises(update.UpdateFehler):  # kein server.py
            self.lauf()
        Path(self.zip).write_text("das ist keine zip")
        with self.assertRaises(update.UpdateFehler):
            self.lauf()
        with self.assertRaises(update.UpdateFehler):
            update.aktualisieren(os.path.join(self.t.name, "gibtsnicht.zip"), self.ziel, neustart=False, pip=False)
        with self.assertRaises(update.UpdateFehler):  # Zielordner ist keine Phonebox
            update.aktualisieren(self.zip, self.t.name, neustart=False, pip=False)
        self.assertIn("v1", update.version_lesen(self.ziel))

    def test_zip_ohne_wurzelordner(self):
        zip_bauen(self.zip, {"server.py": 'VERSION = "v3"\n'}, wurzel="")
        self.lauf()
        self.assertIn("v3", update.version_lesen(self.ziel))

    def test_pfad_pruefung(self):
        self.assertEqual(update.sicherer_pfad("a/b/c.py"), "a/b/c.py")
        for schlecht in ("../x", "/x", "a/../../x", "a\\b", "C:/x", "", "."):
            self.assertIsNone(update.sicherer_pfad(schlecht), schlecht)


def freier_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class NeustartTest(unittest.TestCase):
    """Echter Ablauf: laufenden Server beenden, Dateien tauschen, neuen Server starten."""

    def test_laufenden_server_ersetzen(self):
        port = freier_port()
        env_alt = dict(os.environ)
        os.environ.update(PHONEBOX_TEST="1", PHONEBOX_HTTPS="0", PHONEBOX_PORT=str(port), PHONEBOX_HTTPS_PORT=str(freier_port()))
        with tempfile.TemporaryDirectory() as tmp:
            ziel = Path(tmp) / "pb"
            ziel.mkdir()
            for muster in ("*.py", "*.html", "*.json", "requirements.txt"):
                for f in REPO.glob(muster):
                    shutil.copy2(f, ziel / f.name)
            (ziel / "daten").mkdir()
            os.environ["PHONEBOX_DATEN"] = str(ziel / "daten")
            (ziel / "daten" / "marker.txt").write_text("bleibt")
            alt = subprocess.Popen([sys.executable, "server.py"], cwd=ziel, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            neuer_pid = None
            try:
                for _ in range(40):
                    if update.lauschende_prozesse([port]):
                        break
                    time.sleep(0.25)
                self.assertEqual(update.lauschende_prozesse([port]), {alt.pid}, "der alte Server muss laufen")
                neu_zip = os.path.join(tmp, "neu.zip")
                dateien = {f.name: f.read_text(encoding="utf-8") for f in ziel.glob("*.py")}
                dateien["server.py"] = dateien["server.py"].replace("VERSION = \"", "VERSION = \"v99 NEU ", 1)
                dateien["neu.txt"] = "neu"
                zip_bauen(neu_zip, dateien)
                r = update.aktualisieren(neu_zip, ziel, neustart=True, pip=False)
                self.assertTrue(r["laeuft"], "der neue Server muss laufen")
                alt.wait(5)  # wirft, wenn der alte Server nicht beendet wurde
                neu = update.lauschende_prozesse([port])
                self.assertTrue(neu and alt.pid not in neu)
                neuer_pid = next(iter(neu))
                self.assertIn("v99", update.version_lesen(ziel))
                self.assertEqual((ziel / "daten" / "marker.txt").read_text(), "bleibt")
            finally:
                alt.kill()
                for pid in update.lauschende_prozesse([port]) | ({neuer_pid} if neuer_pid else set()):
                    try:
                        os.kill(pid, 9)
                    except OSError:
                        pass
                os.environ.clear()
                os.environ.update(env_alt)


if __name__ == "__main__":
    unittest.main()
