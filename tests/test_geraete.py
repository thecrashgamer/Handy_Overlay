import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import geraete


class NvidiaTests(unittest.TestCase):
    def test_eine_karte(self):
        gpus = geraete.parse_nvidia("NVIDIA GeForce RTX 3070, 12, 1523, 8192, 45\n")
        self.assertEqual(gpus, [{"name": "NVIDIA GeForce RTX 3070", "auslastung": 12, "vram_benutzt": 1523, "vram_gesamt": 8192, "temperatur": 45}])

    def test_zwei_karten(self):
        text = "NVIDIA GeForce RTX 4090, 99, 20000, 24564, 71\nNVIDIA GeForce GTX 1060 6GB, 0, 300, 6144, 33\n"
        self.assertEqual([g["name"] for g in geraete.parse_nvidia(text)], ["NVIDIA GeForce RTX 4090", "NVIDIA GeForce GTX 1060 6GB"])

    def test_nicht_unterstuetzte_werte(self):
        g = geraete.parse_nvidia("NVIDIA Quadro, 5, [N/A], [Not Supported], [N/A]\n")[0]
        self.assertEqual((g["vram_benutzt"], g["vram_gesamt"], g["temperatur"]), (None, None, None))

    def test_unbrauchbares(self):
        for text in ("", "   \n", "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.",
                     "kaputt, zeile", ",,,,\n", "Name, [N/A], 1, 2, 3\n", None):
            self.assertEqual(geraete.parse_nvidia(text), [], repr(text))

    def test_auslastung_wird_begrenzt(self):
        self.assertEqual(geraete.parse_nvidia("X, 250, 1, 2, 3")[0]["auslastung"], 100)


class WindowsGpuTests(unittest.TestCase):
    ENGINES = [
        {"Name": "pid_1234_luid_0x00000000_0x0000F7E5_phys_0_eng_0_engtype_3D", "UtilizationPercentage": 20},
        {"Name": "pid_5678_luid_0x00000000_0x0000F7E5_phys_0_eng_0_engtype_3D", "UtilizationPercentage": 15},
        {"Name": "pid_1234_luid_0x00000000_0x0000F7E5_phys_0_eng_1_engtype_Copy", "UtilizationPercentage": 4},
        {"Name": "pid_1234_luid_0x00000000_0x0000F7E5_phys_0_eng_2_engtype_VideoDecode", "UtilizationPercentage": 50},
        {"Name": "pid_9_luid_0x00000000_0x0000AAAA_phys_0_eng_0_engtype_3D", "UtilizationPercentage": 1},
    ]
    SPEICHER = [
        {"Name": "luid_0x00000000_0x0000F7E5_phys_0", "DedicatedUsage": 2147483648},
        {"Name": "luid_0x00000000_0x0000AAAA_phys_0", "DedicatedUsage": 104857600},
    ]
    KARTEN = [{"Name": "Intel(R) UHD Graphics 630"}, {"Name": "AMD Radeon RX 6700 XT"}]

    def test_wie_im_task_manager(self):
        g = geraete.parse_gpu_windows({"engines": self.ENGINES, "speicher": self.SPEICHER, "karten": self.KARTEN})[0]
        self.assertEqual(g["auslastung"], 50)  # die hoechste Engine-Art (VideoDecode 50), nicht die Summe aller (89)
        self.assertEqual(g["vram_benutzt"], 2048)
        self.assertEqual(g["name"], "AMD Radeon RX 6700 XT")  # die dedizierte Karte, nicht die Intel-Grafik
        self.assertIsNone(g["vram_gesamt"])

    def test_nur_eine_karte_aus_einem_einzelnen_objekt(self):
        daten = {"engines": {"Name": "pid_1_luid_0x00000000_0x00001111_phys_0_eng_0_engtype_3D", "UtilizationPercentage": 7},
                 "speicher": {"Name": "luid_0x00000000_0x00001111_phys_0", "DedicatedUsage": 52428800},
                 "karten": {"Name": "NVIDIA T400"}}  # PowerShell macht aus einem Eintrag ein Objekt statt einer Liste
        g = geraete.parse_gpu_windows(daten)[0]
        self.assertEqual((g["name"], g["auslastung"], g["vram_benutzt"]), ("NVIDIA T400", 7, 50))

    def test_summen_ueber_100_werden_begrenzt(self):
        e = [{"Name": f"pid_{i}_luid_0x00000000_0x00001111_phys_0_eng_0_engtype_3D", "UtilizationPercentage": 40} for i in range(5)]
        self.assertEqual(geraete.parse_gpu_windows({"engines": e, "speicher": [], "karten": []})[0]["auslastung"], 100)

    def test_ohne_daten(self):
        for d in (None, {}, [], "x", {"engines": [], "speicher": [], "karten": []}, {"engines": [{"Name": "kaputt"}]}):
            self.assertEqual(geraete.parse_gpu_windows(d), [], repr(d))

    def test_microsoft_basic_wird_nicht_als_name_gewaehlt(self):
        daten = {"engines": self.ENGINES, "speicher": [], "karten": [{"Name": "Microsoft Basic Display Adapter"}, {"Name": "NVIDIA RTX A2000"}]}
        self.assertEqual(geraete.parse_gpu_windows(daten)[0]["name"], "NVIDIA RTX A2000")


class AkkuTests(unittest.TestCase):
    def test_bluetooth_liste(self):
        daten = [{"Name": "WH-1000XM4", "Akku": 73, "Verbunden": True},
                 {"Name": "MX Master 3", "Akku": 18, "Verbunden": True},
                 {"Name": "Alter Lautsprecher", "Akku": 90, "Verbunden": False},      # nicht verbunden: weglassen
                 {"Name": "Ohne Wert", "Akku": None, "Verbunden": True},
                 {"Name": "Unsinn", "Akku": 250, "Verbunden": True},
                 {"Name": "WH-1000XM4", "Akku": 73, "Verbunden": True}]                # doppelt
        a = geraete.parse_bluetooth(daten)
        self.assertEqual([(x["name"], x["art"], x["prozent"]) for x in a],
                         [("WH-1000XM4", "kopfhoerer", 73), ("MX Master 3", "maus", 18)])

    def test_ein_einzelnes_objekt_statt_liste(self):
        a = geraete.parse_bluetooth({"Name": "Bluetooth Mouse", "Akku": 55, "Verbunden": None})
        self.assertEqual(len(a), 1)  # unbekannter Verbindungsstatus: behalten

    def test_unbrauchbares(self):
        for d in (None, [], {}, "text", [None, 5, "x"], [{"Akku": 5}]):
            self.assertEqual(geraete.parse_bluetooth(d), [], repr(d))

    def test_art_erkennen(self):
        faelle = {
            "Sony WH-1000XM5": "kopfhoerer", "Logitech G435 Headset": "kopfhoerer", "AirPods Pro": "kopfhoerer",
            "Arctis Nova 7": "kopfhoerer", "Kopfhörer von Timo": "kopfhoerer",
            "Logitech MX Master 3S": "maus", "Bluetooth Mouse": "maus", "Razer Viper": "maus",
            "Logitech MX Keys": "tastatur", "Bluetooth Keyboard": "tastatur",
            "Xbox Wireless Controller": "controller", "DualSense Wireless Controller": "controller", "Pro Controller": "controller",
            "Irgendein Lautsprecher": "geraet", "": "geraet",
        }
        for name, soll in faelle.items():
            self.assertEqual(geraete.art_von(name), soll, name)

    def test_xinput(self):
        self.assertIsNone(geraete.xinput_stufe(0, 3))                       # getrennt
        self.assertEqual(geraete.xinput_stufe(1, 3), ("Kabel", None, True))  # mit Kabel: kein Akku
        self.assertEqual(geraete.xinput_stufe(3, 2), ("Mittel", 60, False))
        self.assertEqual(geraete.xinput_stufe(2, 0), ("Leer", 5, False))
        self.assertEqual(geraete.xinput_stufe(2, 3), ("Voll", 100, False))
        self.assertIsNone(geraete.xinput_stufe(255, 9))                     # unbekannte Stufe

    def test_nicht_windows_liefert_leer_statt_fehler(self):
        if os.name != "nt":
            self.assertEqual(geraete._bluetooth_akkus(), [])
            self.assertEqual(geraete._xinput_akkus(), [])
            self.assertEqual(geraete.gpu_lesen() if not geraete._nvidia_smi() else [], [])

    def test_programm_fehlt_gibt_leeren_text(self):
        self.assertEqual(geraete._ausfuehren(["dieses-programm-gibt-es-nicht-xyz"]), "")
        self.assertEqual(geraete._ausfuehren([sys.executable, "-c", "import sys; sys.exit(3)"]), "")
        self.assertEqual(geraete._ausfuehren([sys.executable, "-c", "import time; time.sleep(5)"], timeout=1), "")

    def test_testdaten(self):
        gpu, akkus = geraete.erstellen(True)
        self.assertEqual(gpu()[0]["name"], "Test-GPU")
        self.assertTrue(any(a["prozent"] is not None and a["prozent"] < 20 for a in akkus()))  # ein schwacher Akku zum Testen
        gpu, akkus = geraete.erstellen(True, leer=True)
        self.assertEqual((gpu(), akkus()), ([], []))


if __name__ == "__main__":
    unittest.main()
