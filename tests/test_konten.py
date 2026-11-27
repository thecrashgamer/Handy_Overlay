import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import konten
from konten import Bremse, KontoFehler, Konten

PW = "Sommer-Regen-42"


class KontenTests(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.k = Konten(os.path.join(self.ordner.name, "t.db"))

    def tearDown(self):
        self.k.db.close()
        self.ordner.cleanup()

    def admin(self):
        benutzer, codes = self.k.registrieren("Timo", PW)
        return benutzer, codes

    # --- Registrieren
    def test_erstes_konto_ist_admin_und_aktiv(self):
        b, codes = self.admin()
        self.assertEqual((b["rolle"], b["status"]), ("admin", "aktiv"))
        self.assertEqual(len(codes), konten.CODE_ANZAHL)

    def test_erstes_konto_nur_am_pc(self):
        with self.assertRaises(KontoFehler) as f:
            self.k.registrieren("Timo", PW, lokal=False)
        self.assertEqual(f.exception.status, 403)
        self.assertEqual(self.k.anzahl_benutzer(), 0)

    def test_weitere_konten_warten_auf_freigabe(self):
        self.admin()
        b, _ = self.k.registrieren("Gast", PW, lokal=False)
        self.assertEqual((b["rolle"], b["status"]), ("benutzer", "wartet"))
        with self.assertRaises(KontoFehler) as f:
            self.k.anmelden("Gast", PW)
        self.assertIn("Freigabe", f.exception.text)
        self.k.status_setzen(b["id"], "aktiv")
        token, _, _ = self.k.anmelden("Gast", PW)
        self.assertTrue(token)

    def test_registrierung_offen_und_geschlossen(self):
        self.admin()
        self.k.registrierung_setzen("offen")
        b, _ = self.k.registrieren("Offen1", PW, lokal=False)
        self.assertEqual(b["status"], "aktiv")
        self.k.registrierung_setzen("geschlossen")
        with self.assertRaises(KontoFehler):
            self.k.registrieren("Zu1", PW, lokal=False)
        with self.assertRaises(KontoFehler):
            self.k.registrierung_setzen("quatsch")

    def test_name_regeln_und_doppelt(self):
        for schlecht in ("ab", "x" * 31, "mit leer", "a;b", "<b>x</b>", ""):
            with self.assertRaises(KontoFehler):
                self.k.registrieren(schlecht, PW)
        self.admin()
        with self.assertRaises(KontoFehler) as f:
            self.k.registrieren("TIMO", PW)  # Gross-/Kleinschreibung zaehlt nicht
        self.assertEqual(f.exception.status, 409)

    def test_passwort_regeln(self):
        for schlecht in ("kurz", "12345678", "Password", "timo-timo"[:0] + "Timo", "a" * 201):
            with self.assertRaises(KontoFehler):
                self.k.registrieren("Timo", schlecht)

    def test_passwort_nie_im_klartext(self):
        self.admin()
        h = self.k.db.execute("SELECT pw_hash FROM benutzer").fetchone()[0]
        self.assertNotIn(PW, h)
        self.assertTrue(h.startswith("scrypt$"))

    # --- Anmelden und Sitzungen
    def test_anmelden_und_sitzung(self):
        self.admin()
        token, b, dauer = self.k.anmelden("timo", PW)  # Name egal ob gross/klein
        self.assertIsNone(dauer)
        self.assertEqual(self.k.sitzung_pruefen(token)["name"], "Timo")
        self.assertIsNone(self.k.sitzung_pruefen("falsch"))
        self.assertIsNone(self.k.sitzung_pruefen(""))
        self.k.abmelden(token)
        self.assertIsNone(self.k.sitzung_pruefen(token))

    def test_token_nur_als_hash_gespeichert(self):
        self.admin()
        token, _, _ = self.k.anmelden("Timo", PW)
        gespeichert = [r[0] for r in self.k.db.execute("SELECT token_hash FROM sitzungen")]
        self.assertNotIn(token, gespeichert)

    def test_falsche_anmeldung_gleiche_meldung(self):
        self.admin()
        meldungen = set()
        for name, pw in (("Timo", "falsch-falsch"), ("gibtsnicht", PW)):
            with self.assertRaises(KontoFehler) as f:
                self.k.anmelden(name, pw)
            meldungen.add((f.exception.text, f.exception.status))
        self.assertEqual(len(meldungen), 1)  # verraet nicht, ob es den Namen gibt

    def test_sitzung_laeuft_ab_und_verlaengert_sich(self):
        self.admin()
        t0 = 1_000_000
        token, _, _ = self.k.anmelden("Timo", PW, merken=False, jetzt=t0)
        self.assertIsNotNone(self.k.sitzung_pruefen(token, jetzt=t0 + 3600))
        self.assertIsNone(self.k.sitzung_pruefen(token, jetzt=t0 + konten.SITZUNG_KURZ + 3601))

        token, _, dauer = self.k.anmelden("Timo", PW, merken=True, jetzt=t0)
        self.assertEqual(dauer, konten.SITZUNG_LANG)
        jetzt = t0
        for _ in range(3):  # bleibt angemeldet, solange man sie benutzt
            jetzt += konten.SITZUNG_LANG // 2
            self.assertIsNotNone(self.k.sitzung_pruefen(token, jetzt=jetzt))
        self.assertIsNone(self.k.sitzung_pruefen(token, jetzt=jetzt + konten.SITZUNG_LANG + 1))

    def test_gesperrter_benutzer_verliert_sitzung(self):
        self.admin()
        g, _ = self.k.registrieren("Gast", PW, lokal=False)
        self.k.status_setzen(g["id"], "aktiv")
        token, _, _ = self.k.anmelden("Gast", PW)
        self.k.status_setzen(g["id"], "gesperrt")
        self.assertIsNone(self.k.sitzung_pruefen(token))
        with self.assertRaises(KontoFehler):
            self.k.anmelden("Gast", PW)

    # --- Passwort aendern / zuruecksetzen
    def test_passwort_aendern(self):
        b, _ = self.admin()
        t1, _, _ = self.k.anmelden("Timo", PW)
        t2, _, _ = self.k.anmelden("Timo", PW)
        with self.assertRaises(KontoFehler):
            self.k.passwort_aendern(b["id"], "falsch-falsch", "Neues-Passwort-7")
        self.k.passwort_aendern(b["id"], PW, "Neues-Passwort-7", behalte_token=t1)
        self.assertIsNotNone(self.k.sitzung_pruefen(t1))
        self.assertIsNone(self.k.sitzung_pruefen(t2))  # andere Geraete abgemeldet
        with self.assertRaises(KontoFehler):
            self.k.anmelden("Timo", PW)
        self.k.anmelden("Timo", "Neues-Passwort-7")

    def test_zuruecksetzen_mit_code(self):
        b, codes = self.admin()
        token, _, _ = self.k.anmelden("Timo", PW)
        self.k.zuruecksetzen("timo", codes[0].lower().replace("-", " "), "Ganz-Neu-9876")  # Format egal
        self.assertIsNone(self.k.sitzung_pruefen(token))  # alle Sitzungen beendet
        self.k.anmelden("Timo", "Ganz-Neu-9876")
        with self.assertRaises(KontoFehler):  # derselbe Code gilt nur einmal
            self.k.zuruecksetzen("Timo", codes[0], "Noch-Einmal-1234")
        self.assertEqual(self.k.codes_uebrig(b["id"]), konten.CODE_ANZAHL - 1)

    def test_zuruecksetzen_falsche_angaben_gleiche_meldung(self):
        _, codes = self.admin()
        texte = set()
        for name, code in (("Timo", "AAAA-BBBB-CCCC"), ("gibtsnicht", codes[0]), ("Timo", "zu kurz")):
            with self.assertRaises(KontoFehler) as f:
                self.k.zuruecksetzen(name, code, "Ganz-Neu-9876")
            texte.add(f.exception.text)
        self.assertEqual(len(texte), 1)

    def test_schwaches_neues_passwort_verbraucht_code_nicht(self):
        b, codes = self.admin()
        with self.assertRaises(KontoFehler):
            self.k.zuruecksetzen("Timo", codes[0], "12345678")
        self.assertEqual(self.k.codes_uebrig(b["id"]), konten.CODE_ANZAHL)

    def test_codes_neu_ersetzt_alte(self):
        b, alte = self.admin()
        with self.assertRaises(KontoFehler):
            self.k.codes_neu(b["id"], "falsch-falsch")
        neue = self.k.codes_neu(b["id"], PW)
        self.assertEqual(len(neue), konten.CODE_ANZAHL)
        with self.assertRaises(KontoFehler):
            self.k.zuruecksetzen("Timo", alte[0], "Ganz-Neu-9876")

    def test_codes_nur_als_hash(self):
        _, codes = self.admin()
        gespeichert = " ".join(r[0] for r in self.k.db.execute("SELECT code_hash FROM codes"))
        self.assertNotIn(codes[0].replace("-", ""), gespeichert)

    # --- Schutz vor Aussperren
    def test_letzter_admin_geschuetzt(self):
        b, _ = self.admin()
        with self.assertRaises(KontoFehler):
            self.k.status_setzen(b["id"], "gesperrt", durch_id=b["id"])
        with self.assertRaises(KontoFehler):
            self.k.rolle_setzen(b["id"], "benutzer", durch_id=b["id"])
        with self.assertRaises(KontoFehler):
            self.k.loeschen(b["id"], durch_id=b["id"])

    def test_zweiter_admin_erlaubt_aenderungen(self):
        a, _ = self.admin()
        g, _ = self.k.registrieren("Gast", PW, lokal=False)
        self.k.status_setzen(g["id"], "aktiv")
        self.k.rolle_setzen(g["id"], "admin")
        self.k.rolle_setzen(a["id"], "benutzer")  # jetzt gibt es noch einen Admin
        with self.assertRaises(KontoFehler):
            self.k.rolle_setzen(g["id"], "benutzer")  # der waere der letzte
        self.k.loeschen(a["id"], durch_id=g["id"])
        self.assertEqual(self.k.anzahl_benutzer(), 1)

    def test_passwort_setzen_fuer_konsole(self):
        self.admin()
        token, _, _ = self.k.anmelden("Timo", PW)
        self.k.passwort_setzen("timo", "Von-Der-Konsole-5")
        self.assertIsNone(self.k.sitzung_pruefen(token))
        self.k.anmelden("Timo", "Von-Der-Konsole-5")
        with self.assertRaises(KontoFehler):
            self.k.passwort_setzen("gibtsnicht", "Von-Der-Konsole-5")

    def test_sql_einschleusen_wirkungslos(self):
        self.admin()
        with self.assertRaises(KontoFehler):
            self.k.anmelden("' OR '1'='1", "' OR '1'='1")
        with self.assertRaises(KontoFehler):
            self.k.registrieren("x'); DROP TABLE benutzer;--", PW)
        self.assertEqual(self.k.anzahl_benutzer(), 1)


class BremseTests(unittest.TestCase):
    def test_sperrt_nach_fuenf_fehlern_und_gibt_wieder_frei(self):
        b = Bremse(max_fehler=5, fenster=600, sperre=300)
        for i in range(4):
            b.fehler("a", jetzt=1000 + i)
            self.assertEqual(b.rest("a", jetzt=1000 + i), 0)
        b.fehler("a", jetzt=1004)
        self.assertGreater(b.rest("a", jetzt=1005), 0)
        self.assertEqual(b.rest("a", jetzt=1004 + 301), 0)
        self.assertEqual(b.rest("anderer", jetzt=1005), 0)  # andere sind nicht betroffen

    def test_alte_fehler_verfallen(self):
        b = Bremse(max_fehler=3, fenster=60, sperre=300)
        b.fehler("a", jetzt=0)
        b.fehler("a", jetzt=10)
        b.fehler("a", jetzt=100)  # die ersten beiden sind schon aelter als 60 s
        self.assertEqual(b.rest("a", jetzt=101), 0)

    def test_erfolg_setzt_zurueck(self):
        b = Bremse(max_fehler=3)
        b.fehler("a", jetzt=0); b.fehler("a", jetzt=1)
        b.erfolg("a")
        b.fehler("a", jetzt=2)
        self.assertEqual(b.rest("a", jetzt=3), 0)


if __name__ == "__main__":
    unittest.main()
