import os
import socket
import ssl
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID

import zertifikate


def lesen(pfad):
    with open(pfad, "rb") as d:
        return d.read()


def tls_verbindung(info, host):
    """Echter TLS-Handshake: Server mit dem Zertifikat, Client vertraut nur der CA und prueft den Namen."""
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(info["cert"], info["key"])
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]

    def bedienen():
        try:
            c, _ = sock.accept()
            with server_ctx.wrap_socket(c, server_side=True) as s:
                s.recv(1)
        except Exception:
            pass

    t = threading.Thread(target=bedienen, daemon=True)
    t.start()
    client_ctx = ssl.create_default_context(cafile=str(info["ca"]))  # vertraut NUR der Phonebox-CA
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        with client_ctx.wrap_socket(raw, server_hostname=host) as s:
            s.send(b"x")
            return s.version()


class ZertifikatTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.ordner = self.t.name

    def tearDown(self):
        self.t.cleanup()

    def test_kette_ist_gueltig_fuer_localhost_und_ip(self):
        info = zertifikate.vorbereiten(self.ordner, zusatz=["192.168.1.204"])
        self.assertTrue(info["neu_ca"] and info["neu_server"])
        for host in ("localhost", "127.0.0.1"):
            self.assertTrue(tls_verbindung(info, host).startswith("TLS"), host)

    def test_zusatzname_ist_im_zertifikat(self):
        info = zertifikate.vorbereiten(self.ordner, zusatz=["192.168.1.204", "pc.example.ts.net"])
        self.assertIn("192.168.1.204", info["namen"])
        cert = x509.load_pem_x509_certificate(lesen(info["cert"]))
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        self.assertIn("pc.example.ts.net", san.get_values_for_type(x509.DNSName))
        import ipaddress
        self.assertIn(ipaddress.ip_address("192.168.1.204"), san.get_values_for_type(x509.IPAddress))

    def test_vom_handy_geforderte_eigenschaften(self):
        info = zertifikate.vorbereiten(self.ordner)
        cert = x509.load_pem_x509_certificate(lesen(info["cert"]))
        laufzeit = (cert.not_valid_after_utc - cert.not_valid_before_utc).days
        self.assertLessEqual(laufzeit, 825, "iOS lehnt laengere Server-Zertifikate ab")
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        self.assertIn(ExtendedKeyUsageOID.SERVER_AUTH, eku)
        self.assertFalse(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        ca = x509.load_pem_x509_certificate(lesen(info["ca"]))
        bc = ca.extensions.get_extension_for_class(x509.BasicConstraints).value
        self.assertTrue(bc.ca)
        self.assertEqual(bc.path_length, 0)  # die CA darf keine weiteren CAs ausstellen

    def test_zweiter_start_aendert_nichts(self):
        a = zertifikate.vorbereiten(self.ordner, zusatz=["10.0.0.5"])
        vorher = lesen(a["cert"])
        b = zertifikate.vorbereiten(self.ordner, zusatz=["10.0.0.5"])
        self.assertFalse(b["neu_ca"] or b["neu_server"])
        self.assertEqual(lesen(b["cert"]), vorher)

    def test_neue_ip_erneuert_nur_das_serverzertifikat(self):
        a = zertifikate.vorbereiten(self.ordner, zusatz=["10.0.0.5"])
        b = zertifikate.vorbereiten(self.ordner, zusatz=["10.0.0.6"])
        self.assertTrue(b["neu_server"])
        self.assertFalse(b["neu_ca"])
        self.assertEqual(a["fingerabdruck"], b["fingerabdruck"])  # das Handy muss nichts neu installieren
        self.assertTrue(tls_verbindung(b, "localhost").startswith("TLS"))

    def test_bald_ablaufendes_zertifikat_wird_erneuert(self):
        zertifikate.vorbereiten(self.ordner)
        alt = zertifikate.ERNEUERN_VOR_TAGEN
        zertifikate.ERNEUERN_VOR_TAGEN = 10_000
        try:
            self.assertTrue(zertifikate.vorbereiten(self.ordner)["neu_server"])
        finally:
            zertifikate.ERNEUERN_VOR_TAGEN = alt

    def test_fremde_ca_wird_nicht_akzeptiert(self):
        info = zertifikate.vorbereiten(self.ordner)
        with tempfile.TemporaryDirectory() as anderer:
            fremd = zertifikate.vorbereiten(anderer)
            info_falsch = dict(info, ca=fremd["ca"])
            with self.assertRaises(ssl.SSLError):
                tls_verbindung(info_falsch, "localhost")

    def test_fingerabdruck_format(self):
        info = zertifikate.vorbereiten(self.ordner)
        self.assertRegex(info["fingerabdruck"], r"^([0-9A-F]{2}:){31}[0-9A-F]{2}$")

    def test_kaputte_dateien_werden_ersetzt(self):
        info = zertifikate.vorbereiten(self.ordner)
        with open(info["cert"], "w") as d:
            d.write("kaputt")
        self.assertTrue(zertifikate.vorbereiten(self.ordner)["neu_server"])


if __name__ == "__main__":
    unittest.main()
