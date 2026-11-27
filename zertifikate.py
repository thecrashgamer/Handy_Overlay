"""HTTPS fuer die Phonebox mit einem eigenen Zertifikat.

Beim ersten Start entsteht eine eigene kleine "Zertifizierungsstelle" (CA) und ein Server-Zertifikat dafuer.
Das Handy installiert einmalig die CA (Seite /zertifikat). Aendert sich spaeter die IP-Adresse des PCs, wird nur
das Server-Zertifikat neu ausgestellt. Die CA bleibt, das Handy vertraut weiter.

Dateien in daten/https/: ca.pem (oeffentlich), ca-key.pem (GEHEIM), server.pem, server-key.pem (GEHEIM), server.json.
"""
import datetime
import hashlib
import ipaddress
import json
import os
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_JAHRE = 10
SERVER_TAGE = 800  # iOS lehnt Server-Zertifikate mit mehr als 825 Tagen Laufzeit ab
ERNEUERN_VOR_TAGEN = 30


def lokale_adressen():
    """IPv4-Adressen dieses PCs (WLAN, LAN, Tailscale ...) ohne Loopback und Link-Local."""
    adressen = set()
    try:
        import psutil

        for liste in psutil.net_if_addrs().values():
            for a in liste:
                if a.family == socket.AF_INET:
                    ip = ipaddress.ip_address(a.address)
                    if not ip.is_loopback and not ip.is_link_local:
                        adressen.add(a.address)
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_loopback and not ip.is_link_local:
                adressen.add(info[4][0])
    except Exception:
        pass
    return sorted(adressen, key=lambda a: tuple(int(t) for t in a.split(".")))


def namen_sammeln(zusatz=()):
    """Alle Namen und Adressen, fuer die das Server-Zertifikat gelten soll (sortiert, ohne Doppelte)."""
    host = socket.gethostname().strip()
    namen = {"localhost", "127.0.0.1", "::1"}
    if host:
        namen.update({host, host + ".local"})
    namen.update(lokale_adressen())
    namen.update(z.strip() for z in zusatz if z and z.strip())
    return sorted(namen)


def _als_eintrag(name):
    try:
        return x509.IPAddress(ipaddress.ip_address(name))
    except ValueError:
        return x509.DNSName(name)


def _jetzt():
    return datetime.datetime.now(datetime.timezone.utc)


def _schluessel():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _schluessel_schreiben(pfad, key):
    pfad.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    try:
        os.chmod(pfad, 0o600)  # unter Windows ohne Wirkung; dort schuetzt das Benutzerprofil
    except OSError:
        pass


def _ca_erstellen(ordner):
    key = _schluessel()
    host = socket.gethostname() or "PC"
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Phonebox Zertifikat ({host})"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Phonebox")])
    jetzt = _jetzt()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(jetzt - datetime.timedelta(days=1))
        .not_valid_after(jetzt + datetime.timedelta(days=365 * CA_JAHRE))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                     key_encipherment=False, data_encipherment=False, key_agreement=False,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    (ordner / "ca.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    _schluessel_schreiben(ordner / "ca-key.pem", key)


def _ca_laden(ordner):
    cert = x509.load_pem_x509_certificate((ordner / "ca.pem").read_bytes())
    key = serialization.load_pem_private_key((ordner / "ca-key.pem").read_bytes(), password=None)
    return cert, key


def _server_erstellen(ordner, namen):
    ca_cert, ca_key = _ca_laden(ordner)
    key = _schluessel()
    jetzt = _jetzt()
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Phonebox")]))
        .issuer_name(ca_cert.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(jetzt - datetime.timedelta(days=1))
        .not_valid_after(jetzt + datetime.timedelta(days=SERVER_TAGE))
        .add_extension(x509.SubjectAlternativeName([_als_eintrag(n) for n in namen]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, content_commitment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                     crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    (ordner / "server.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    _schluessel_schreiben(ordner / "server-key.pem", key)
    (ordner / "server.json").write_text(json.dumps({"namen": namen}), encoding="utf-8")


def _server_noch_gut(ordner, namen):
    """Gueltig genug und fuer genau diese Namen ausgestellt?"""
    try:
        gespeichert = json.loads((ordner / "server.json").read_text(encoding="utf-8"))["namen"]
        cert = x509.load_pem_x509_certificate((ordner / "server.pem").read_bytes())
        ca_cert, _ = _ca_laden(ordner)
        cert.verify_directly_issued_by(ca_cert)
        if not (ordner / "server-key.pem").exists():
            return False
        rest = cert.not_valid_after_utc - _jetzt()
        return gespeichert == namen and rest > datetime.timedelta(days=ERNEUERN_VOR_TAGEN)
    except Exception:
        return False


def fingerabdruck(ca_pfad):
    """SHA-256-Fingerabdruck der CA, in der Schreibweise, die Geraete anzeigen."""
    cert = x509.load_pem_x509_certificate(Path(ca_pfad).read_bytes())
    h = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


def vorbereiten(daten_ordner, zusatz=()):
    """Legt fehlende Zertifikate an oder erneuert sie. Gibt ein Dict mit Pfaden und Hinweisen zurueck."""
    ordner = Path(daten_ordner) / "https"
    ordner.mkdir(parents=True, exist_ok=True)
    neu_ca = neu_server = False
    if not ((ordner / "ca.pem").exists() and (ordner / "ca-key.pem").exists()):
        _ca_erstellen(ordner)
        neu_ca = True
    namen = namen_sammeln(zusatz)
    if neu_ca or not _server_noch_gut(ordner, namen):
        _server_erstellen(ordner, namen)
        neu_server = True
    return {
        "cert": str(ordner / "server.pem"), "key": str(ordner / "server-key.pem"), "ca": ordner / "ca.pem",
        "namen": namen, "neu_ca": neu_ca, "neu_server": neu_server, "fingerabdruck": fingerabdruck(ordner / "ca.pem"),
    }
