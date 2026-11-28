"""Benutzerkonten der Phonebox: Registrieren, Anmelden, Sitzungen, Wiederherstellungscodes.

Nur Standardbibliothek (sqlite3, hashlib.scrypt). Passwoerter werden nie im Klartext gespeichert,
Sitzungs-Schluessel und Wiederherstellungscodes nur als Hash. Alle Zeitangaben in Sekunden (Unix-Zeit);
Methoden nehmen optional `jetzt`, damit sich Ablaeufe testen lassen.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
import unicodedata

NAME_MUSTER = re.compile(r"^[A-Za-z0-9ÄÖÜäöüß._-]{3,30}$")
PW_MIN = 8
PW_MAX = 200
SCHWACHE_PASSWOERTER = {
    "12345678", "123456789", "1234567890", "00000000", "11111111", "12341234",
    "password", "password1", "passwort", "passwort1", "qwertzui", "qwertyui",
    "qwertzuiop", "qwertyuiop", "iloveyou", "abcd1234", "test1234",
}
CODE_ZEICHEN = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ohne leicht verwechselbare Zeichen (0/O, 1/I)
CODE_ANZAHL = 8
SITZUNG_KURZ = 12 * 3600  # ohne "Angemeldet bleiben", verlaengert sich bei Benutzung
SITZUNG_LANG = 90 * 24 * 3600  # mit "Angemeldet bleiben"
REGISTRIERUNG = ("freigabe", "offen", "geschlossen")


def rechte(benutzer):
    """Was darf dieser Benutzer? Administratoren dürfen alles."""
    if not benutzer:
        return {"musik": False, "shortcuts": False, "admin": False}
    admin = benutzer.get("rolle") == "admin"
    return {"musik": admin or bool(benutzer.get("darf_musik")),
            "shortcuts": admin or bool(benutzer.get("darf_shortcuts")),
            "admin": admin}


class KontoFehler(Exception):
    """Fehler mit Text fuer den Benutzer und passendem HTTP-Status."""

    def __init__(self, text, status=400):
        super().__init__(text)
        self.text = text
        self.status = status


# ---------------------------------------------------------------- Passwoerter

def _b64(daten):
    return base64.b64encode(daten).decode("ascii")


def _normal(passwort):
    # NFKC: dasselbe Passwort ergibt auf iPhone und Windows denselben Hash
    return unicodedata.normalize("NFKC", passwort)


def pw_hash(passwort):
    salz = secrets.token_bytes(16)
    n, r, p = 2 ** 14, 8, 1
    h = hashlib.scrypt(_normal(passwort).encode("utf-8"), salt=salz, n=n, r=r, p=p,
                       dklen=32, maxmem=64 * 1024 * 1024)
    return f"scrypt${n}${r}${p}${_b64(salz)}${_b64(h)}"


def pw_pruefen(passwort, gespeichert):
    try:
        art, n, r, p, salz, soll = gespeichert.split("$")
        if art != "scrypt":
            return False
        h = hashlib.scrypt(_normal(passwort).encode("utf-8"), salt=base64.b64decode(salz),
                           n=int(n), r=int(r), p=int(p), dklen=32, maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(h, base64.b64decode(soll))
    except Exception:
        return False


_ATTRAPPE = None


def _attrappe():
    """Ein Hash, gegen den bei unbekanntem Namen geprueft wird, damit die Antwortzeit nichts verraet."""
    global _ATTRAPPE
    if _ATTRAPPE is None:
        _ATTRAPPE = pw_hash(secrets.token_urlsafe(12))
    return _ATTRAPPE


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pw_regeln(name, passwort):
    if not isinstance(passwort, str) or len(passwort) < PW_MIN:
        raise KontoFehler(f"Das Passwort braucht mindestens {PW_MIN} Zeichen.")
    if len(passwort) > PW_MAX:
        raise KontoFehler("Das Passwort ist zu lang.")
    if passwort.lower() in SCHWACHE_PASSWOERTER:
        raise KontoFehler("Dieses Passwort ist zu einfach zu erraten. Nimm ein anderes.")
    if name and passwort.lower() == name.lower():
        raise KontoFehler("Das Passwort darf nicht dem Namen gleichen.")


def code_normal(code):
    return re.sub(r"[^A-Z0-9]", "", str(code).upper())


# ---------------------------------------------------------------- Bremse

class Bremse:
    """Sperrt nach zu vielen Fehlversuchen fuer eine Weile (im Arbeitsspeicher)."""

    def __init__(self, max_fehler=5, fenster=600, sperre=300):
        self.max_fehler, self.fenster, self.sperre = max_fehler, fenster, sperre
        self._fehler = {}
        self._gesperrt = {}
        self._lock = threading.Lock()

    def rest(self, schluessel, jetzt=None):
        """Sekunden, die noch gesperrt ist (0 = frei)."""
        jetzt = time.time() if jetzt is None else jetzt
        with self._lock:
            bis = self._gesperrt.get(schluessel, 0)
            if bis <= jetzt:
                self._gesperrt.pop(schluessel, None)
                return 0
            return int(bis - jetzt) + 1

    def fehler(self, schluessel, jetzt=None):
        jetzt = time.time() if jetzt is None else jetzt
        with self._lock:
            liste = [t for t in self._fehler.get(schluessel, []) if t > jetzt - self.fenster]
            liste.append(jetzt)
            self._fehler[schluessel] = liste
            if len(liste) >= self.max_fehler:
                self._gesperrt[schluessel] = jetzt + self.sperre
                self._fehler.pop(schluessel, None)

    def erfolg(self, schluessel):
        with self._lock:
            self._fehler.pop(schluessel, None)


# ---------------------------------------------------------------- Konten

class Konten:
    def __init__(self, pfad):
        ordner = os.path.dirname(os.path.abspath(pfad))
        os.makedirs(ordner, exist_ok=True)
        self.db = sqlite3.connect(pfad, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.execute("PRAGMA foreign_keys = ON")
            self.db.executescript(
                """
                CREATE TABLE IF NOT EXISTS benutzer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    name_klein TEXT NOT NULL UNIQUE,
                    pw_hash TEXT NOT NULL,
                    rolle TEXT NOT NULL DEFAULT 'benutzer',
                    status TEXT NOT NULL DEFAULT 'wartet',
                    erstellt INTEGER NOT NULL,
                    letzte_anmeldung INTEGER
                );
                CREATE TABLE IF NOT EXISTS sitzungen (
                    token_hash TEXT PRIMARY KEY,
                    benutzer_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
                    erstellt INTEGER NOT NULL,
                    zuletzt INTEGER NOT NULL,
                    laeuft_ab INTEGER NOT NULL,
                    merken INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    benutzer_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
                    code_hash TEXT NOT NULL UNIQUE,
                    benutzt INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS einstellungen (
                    schluessel TEXT PRIMARY KEY,
                    wert TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS aktivitaet (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zeit INTEGER NOT NULL,
                    benutzer_id INTEGER,
                    benutzer TEXT NOT NULL DEFAULT '',
                    art TEXT NOT NULL,
                    text TEXT NOT NULL,
                    ip TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS aktivitaet_zeit ON aktivitaet(zeit);
                """
            )
            # Alte Datenbanken bekommen die Rechte-Spalten nachtraeglich, ohne dass etwas verloren geht
            spalten = {r["name"] for r in self.db.execute("PRAGMA table_info(benutzer)")}
            if "darf_musik" not in spalten:
                self.db.execute("ALTER TABLE benutzer ADD COLUMN darf_musik INTEGER NOT NULL DEFAULT 1")
            if "darf_shortcuts" not in spalten:
                self.db.execute("ALTER TABLE benutzer ADD COLUMN darf_shortcuts INTEGER NOT NULL DEFAULT 0")
            self.db.commit()

    # --- Hilfen
    def _benutzer(self, zeile):
        if zeile is None:
            return None
        b = {k: zeile[k] for k in ("id", "name", "rolle", "status", "erstellt", "letzte_anmeldung")}
        b["darf_musik"] = bool(zeile["darf_musik"])
        b["darf_shortcuts"] = bool(zeile["darf_shortcuts"])
        return b

    def anzahl_benutzer(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM benutzer").fetchone()[0]

    def registrierung(self):
        with self.lock:
            z = self.db.execute("SELECT wert FROM einstellungen WHERE schluessel='registrierung'").fetchone()
        return z["wert"] if z and z["wert"] in REGISTRIERUNG else "freigabe"

    def registrierung_setzen(self, modus):
        if modus not in REGISTRIERUNG:
            raise KontoFehler("Unbekannte Einstellung.")
        with self.lock:
            self.db.execute("INSERT INTO einstellungen(schluessel, wert) VALUES('registrierung', ?) "
                            "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert", (modus,))
            self.db.commit()

    def einstellung(self, schluessel, standard=""):
        with self.lock:
            z = self.db.execute("SELECT wert FROM einstellungen WHERE schluessel=?", (schluessel,)).fetchone()
        return z["wert"] if z else standard

    def einstellung_setzen(self, schluessel, wert):
        with self.lock:
            self.db.execute("INSERT INTO einstellungen(schluessel, wert) VALUES(?, ?) "
                            "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert", (schluessel, str(wert)))
            self.db.commit()

    # --- Registrieren
    def registrieren(self, name, passwort, lokal=True, jetzt=None):
        """Legt ein Konto an. Gibt Benutzer und Wiederherstellungscodes zurueck (Codes nur dieses eine Mal)."""
        jetzt = int(time.time() if jetzt is None else jetzt)
        name = str(name).strip()
        if not NAME_MUSTER.match(name):
            raise KontoFehler("Der Name braucht 3 bis 30 Zeichen: Buchstaben, Zahlen, Punkt, Unterstrich oder Minus.")
        pw_regeln(name, passwort)
        gespeichert = pw_hash(passwort)  # rechenintensiv, darum vor der Datenbanksperre
        with self.lock:
            erster = self.anzahl_benutzer() == 0
            if erster and not lokal:
                raise KontoFehler("Das erste Konto legst du am PC selbst an: http://localhost:8000", 403)
            modus = self.registrierung()
            if not erster and modus == "geschlossen":
                raise KontoFehler("Neue Konten sind gerade nicht erlaubt. Frag den Administrator.", 403)
            rolle = "admin" if erster else "benutzer"
            status = "aktiv" if (erster or modus == "offen") else "wartet"
            try:
                cur = self.db.execute(
                    "INSERT INTO benutzer(name, name_klein, pw_hash, rolle, status, erstellt) VALUES(?,?,?,?,?,?)",
                    (name, name.lower(), gespeichert, rolle, status, jetzt),
                )
            except sqlite3.IntegrityError:
                raise KontoFehler("Diesen Namen gibt es schon.", 409)
            benutzer_id = cur.lastrowid
            codes = self._codes_erzeugen(benutzer_id)
            self.db.commit()
            z = self.db.execute("SELECT * FROM benutzer WHERE id=?", (benutzer_id,)).fetchone()
        return self._benutzer(z), codes

    def _codes_erzeugen(self, benutzer_id):
        self.db.execute("DELETE FROM codes WHERE benutzer_id=?", (benutzer_id,))
        codes = []
        for _ in range(CODE_ANZAHL):
            roh = "".join(secrets.choice(CODE_ZEICHEN) for _ in range(12))
            self.db.execute("INSERT INTO codes(benutzer_id, code_hash) VALUES(?,?)", (benutzer_id, _hash(roh)))
            codes.append(f"{roh[0:4]}-{roh[4:8]}-{roh[8:12]}")
        return codes

    # --- Anmelden und Sitzungen
    def anmelden(self, name, passwort, merken=False, jetzt=None):
        """Gibt (Sitzungs-Schluessel, Benutzer, Cookie-Dauer oder None) zurueck oder wirft KontoFehler."""
        jetzt = int(time.time() if jetzt is None else jetzt)
        with self.lock:
            z = self.db.execute("SELECT * FROM benutzer WHERE name_klein=?", (str(name).strip().lower(),)).fetchone()
        if z is None:
            pw_pruefen(str(passwort), _attrappe())  # gleiche Rechenzeit wie bei einem echten Konto
            raise KontoFehler("Name oder Passwort stimmt nicht.", 401)
        if not pw_pruefen(str(passwort), z["pw_hash"]):
            raise KontoFehler("Name oder Passwort stimmt nicht.", 401)
        if z["status"] == "wartet":
            raise KontoFehler("Dein Konto wartet noch auf die Freigabe durch den Administrator.", 403)
        if z["status"] != "aktiv":
            raise KontoFehler("Dieses Konto ist gesperrt.", 403)
        token, dauer = self.sitzung_erstellen(z["id"], merken, jetzt)
        return token, self._benutzer(z), dauer

    def sitzung_erstellen(self, benutzer_id, merken=False, jetzt=None):
        """Neue Sitzung. Gibt (Schluessel, Cookie-Dauer oder None fuer ein Sitzungs-Cookie) zurueck."""
        jetzt = int(time.time() if jetzt is None else jetzt)
        token = secrets.token_urlsafe(32)
        dauer = SITZUNG_LANG if merken else SITZUNG_KURZ
        with self.lock:
            self.db.execute(
                "INSERT INTO sitzungen(token_hash, benutzer_id, erstellt, zuletzt, laeuft_ab, merken) VALUES(?,?,?,?,?,?)",
                (_hash(token), benutzer_id, jetzt, jetzt, jetzt + dauer, 1 if merken else 0),
            )
            self.db.execute("UPDATE benutzer SET letzte_anmeldung=? WHERE id=?", (jetzt, benutzer_id))
            self.db.commit()
        return token, (dauer if merken else None)

    def sitzung_pruefen(self, token, jetzt=None):
        """Benutzer zur Sitzung oder None. Verlaengert die Sitzung bei Benutzung."""
        if not token:
            return None
        jetzt = int(time.time() if jetzt is None else jetzt)
        th = _hash(token)
        with self.lock:
            s = self.db.execute(
                "SELECT s.*, b.name, b.rolle, b.status, b.erstellt AS b_erstellt, b.letzte_anmeldung, "
                "b.darf_musik, b.darf_shortcuts "
                "FROM sitzungen s JOIN benutzer b ON b.id = s.benutzer_id WHERE s.token_hash=?", (th,)
            ).fetchone()
            if s is None:
                return None
            if s["laeuft_ab"] <= jetzt or s["status"] != "aktiv":
                self.db.execute("DELETE FROM sitzungen WHERE token_hash=?", (th,))
                self.db.commit()
                return None
            if jetzt - s["zuletzt"] > 600:  # hoechstens alle 10 Minuten schreiben
                dauer = SITZUNG_LANG if s["merken"] else SITZUNG_KURZ
                self.db.execute("UPDATE sitzungen SET zuletzt=?, laeuft_ab=? WHERE token_hash=?",
                                (jetzt, jetzt + dauer, th))
                self.db.commit()
        return {"id": s["benutzer_id"], "name": s["name"], "rolle": s["rolle"], "status": s["status"],
                "erstellt": s["b_erstellt"], "letzte_anmeldung": s["letzte_anmeldung"],
                "darf_musik": bool(s["darf_musik"]), "darf_shortcuts": bool(s["darf_shortcuts"])}

    def abmelden(self, token):
        if token:
            with self.lock:
                self.db.execute("DELETE FROM sitzungen WHERE token_hash=?", (_hash(token),))
                self.db.commit()

    def aufraeumen(self, jetzt=None):
        jetzt = int(time.time() if jetzt is None else jetzt)
        with self.lock:
            self.db.execute("DELETE FROM sitzungen WHERE laeuft_ab <= ?", (jetzt,))
            self.db.commit()
        self.aktivitaet_aufraeumen()

    def _sitzungen_loeschen(self, benutzer_id, ausser=None):
        if ausser:
            self.db.execute("DELETE FROM sitzungen WHERE benutzer_id=? AND token_hash<>?", (benutzer_id, _hash(ausser)))
        else:
            self.db.execute("DELETE FROM sitzungen WHERE benutzer_id=?", (benutzer_id,))

    # --- Passwort
    def passwort_aendern(self, benutzer_id, altes, neues, behalte_token=None):
        with self.lock:
            z = self.db.execute("SELECT * FROM benutzer WHERE id=?", (benutzer_id,)).fetchone()
        if z is None or not pw_pruefen(str(altes), z["pw_hash"]):
            raise KontoFehler("Das alte Passwort stimmt nicht.", 403)
        pw_regeln(z["name"], neues)
        gespeichert = pw_hash(neues)
        with self.lock:
            self.db.execute("UPDATE benutzer SET pw_hash=? WHERE id=?", (gespeichert, benutzer_id))
            self._sitzungen_loeschen(benutzer_id, ausser=behalte_token)  # andere Geraete muessen sich neu anmelden
            self.db.commit()

    def passwort_stimmt(self, benutzer_id, passwort):
        with self.lock:
            z = self.db.execute("SELECT pw_hash FROM benutzer WHERE id=?", (benutzer_id,)).fetchone()
        return z is not None and pw_pruefen(str(passwort), z["pw_hash"])

    def codes_neu(self, benutzer_id, passwort):
        with self.lock:
            z = self.db.execute("SELECT * FROM benutzer WHERE id=?", (benutzer_id,)).fetchone()
        if z is None or not pw_pruefen(str(passwort), z["pw_hash"]):
            raise KontoFehler("Das Passwort stimmt nicht.", 403)
        with self.lock:
            codes = self._codes_erzeugen(benutzer_id)
            self.db.commit()
        return codes

    def codes_uebrig(self, benutzer_id):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM codes WHERE benutzer_id=? AND benutzt=0", (benutzer_id,)).fetchone()[0]

    def zuruecksetzen(self, name, code, neues):
        """Passwort mit einem Wiederherstellungscode ersetzen. Jeder Code gilt nur einmal."""
        fehler = KontoFehler("Name oder Code stimmt nicht.", 403)
        with self.lock:
            z = self.db.execute("SELECT * FROM benutzer WHERE name_klein=?", (str(name).strip().lower(),)).fetchone()
        if z is None:
            raise fehler
        roh = code_normal(code)
        if len(roh) != 12:
            raise fehler
        with self.lock:
            c = self.db.execute("SELECT id FROM codes WHERE benutzer_id=? AND code_hash=? AND benutzt=0",
                                (z["id"], _hash(roh))).fetchone()
        if c is None:
            raise fehler
        pw_regeln(z["name"], neues)  # erst nach dem Code pruefen, damit er bei einem Tippfehler nicht verbraucht ist
        gespeichert = pw_hash(neues)
        with self.lock:
            self.db.execute("UPDATE codes SET benutzt=1 WHERE id=?", (c["id"],))
            self.db.execute("UPDATE benutzer SET pw_hash=? WHERE id=?", (gespeichert, z["id"]))
            self._sitzungen_loeschen(z["id"])
            self.db.commit()

    def passwort_setzen(self, name, neues):
        """Fuer das Kommandozeilenwerkzeug am PC: setzt ein Passwort ohne altes."""
        with self.lock:
            z = self.db.execute("SELECT * FROM benutzer WHERE name_klein=?", (str(name).strip().lower(),)).fetchone()
        if z is None:
            raise KontoFehler("Dieses Konto gibt es nicht.", 404)
        pw_regeln(z["name"], neues)
        gespeichert = pw_hash(neues)
        with self.lock:
            self.db.execute("UPDATE benutzer SET pw_hash=? WHERE id=?", (gespeichert, z["id"]))
            self._sitzungen_loeschen(z["id"])
            self.db.commit()

    # --- Verwaltung (nur fuer Administratoren; die Pruefung der Rolle macht der Aufrufer)
    def liste(self):
        with self.lock:
            zeilen = self.db.execute("SELECT * FROM benutzer ORDER BY id").fetchall()
        return [self._benutzer(z) for z in zeilen]

    def finden(self, name):
        with self.lock:
            return self._benutzer(self.db.execute("SELECT * FROM benutzer WHERE name_klein=?",
                                                  (str(name).strip().lower(),)).fetchone())

    def _aktive_admins(self):
        return self.db.execute("SELECT COUNT(*) FROM benutzer WHERE rolle='admin' AND status='aktiv'").fetchone()[0]

    def status_setzen(self, benutzer_id, status, durch_id=None):
        if status not in ("aktiv", "gesperrt"):
            raise KontoFehler("Unbekannter Status.")
        with self.lock:
            z = self.db.execute("SELECT * FROM benutzer WHERE id=?", (benutzer_id,)).fetchone()
            if z is None:
                raise KontoFehler("Dieses Konto gibt es nicht.", 404)
            if status == "gesperrt":
                if durch_id == benutzer_id:
                    raise KontoFehler("Du kannst dich nicht selbst sperren.", 400)
                if z["rolle"] == "admin" and z["status"] == "aktiv" and self._aktive_admins() <= 1:
                    raise KontoFehler("Der letzte Administrator kann nicht gesperrt werden.", 400)
                self._sitzungen_loeschen(benutzer_id)
            self.db.execute("UPDATE benutzer SET status=? WHERE id=?", (status, benutzer_id))
            self.db.commit()

    def rolle_setzen(self, benutzer_id, rolle, durch_id=None):
        if rolle not in ("admin", "benutzer"):
            raise KontoFehler("Unbekannte Rolle.")
        with self.lock:
            z = self.db.execute("SELECT * FROM benutzer WHERE id=?", (benutzer_id,)).fetchone()
            if z is None:
                raise KontoFehler("Dieses Konto gibt es nicht.", 404)
            if rolle == "benutzer" and z["rolle"] == "admin" and z["status"] == "aktiv" and self._aktive_admins() <= 1:
                raise KontoFehler("Es muss mindestens ein Administrator bleiben.", 400)
            self.db.execute("UPDATE benutzer SET rolle=? WHERE id=?", (rolle, benutzer_id))
            self.db.commit()

    def recht_setzen(self, benutzer_id, recht, wert):
        spalte = {"musik": "darf_musik", "shortcuts": "darf_shortcuts"}.get(recht)
        if spalte is None:
            raise KontoFehler("Unbekanntes Recht.")
        with self.lock:
            z = self.db.execute("SELECT rolle FROM benutzer WHERE id=?", (benutzer_id,)).fetchone()
            if z is None:
                raise KontoFehler("Dieses Konto gibt es nicht.", 404)
            self.db.execute(f"UPDATE benutzer SET {spalte}=? WHERE id=?", (1 if wert else 0, benutzer_id))
            self.db.commit()

    # --- Aktivitaetsprotokoll
    def protokoll(self, art, text, benutzer=None, ip="", jetzt=None):
        """Haelt fest, wer wann was getan hat. Fehler hier duerfen nie die eigentliche Aktion stoeren."""
        jetzt = int(time.time() if jetzt is None else jetzt)
        try:
            with self.lock:
                self.db.execute(
                    "INSERT INTO aktivitaet(zeit, benutzer_id, benutzer, art, text, ip) VALUES(?,?,?,?,?,?)",
                    (jetzt, benutzer["id"] if benutzer else None, benutzer["name"] if benutzer else "",
                     str(art)[:30], str(text)[:300], str(ip)[:60]),
                )
                self.db.commit()
        except Exception:
            pass

    def aktivitaet_liste(self, limit=200, art=None, benutzer=None):
        limit = max(1, min(int(limit), 2000))
        sql, args = "SELECT * FROM aktivitaet", []
        bedingungen = []
        if art:  # eine Art oder mehrere, durch Komma getrennt
            arten = [a.strip() for a in str(art).split(",") if a.strip()][:10]
            bedingungen.append("art IN (" + ",".join("?" * len(arten)) + ")")
            args.extend(arten)
        if benutzer:
            bedingungen.append("lower(benutzer)=?")
            args.append(str(benutzer).lower())
        if bedingungen:
            sql += " WHERE " + " AND ".join(bedingungen)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            zeilen = self.db.execute(sql, args).fetchall()
        return [{k: z[k] for k in ("id", "zeit", "benutzer", "art", "text", "ip")} for z in zeilen]

    def aktivitaet_aufraeumen(self, behalten=5000):
        with self.lock:
            self.db.execute("DELETE FROM aktivitaet WHERE id <= (SELECT COALESCE(MAX(id), 0) - ? FROM aktivitaet)", (behalten,))
            self.db.commit()

    def loeschen(self, benutzer_id, durch_id=None):
        with self.lock:
            z = self.db.execute("SELECT * FROM benutzer WHERE id=?", (benutzer_id,)).fetchone()
            if z is None:
                raise KontoFehler("Dieses Konto gibt es nicht.", 404)
            if durch_id == benutzer_id:
                raise KontoFehler("Du kannst dein eigenes Konto hier nicht loeschen.", 400)
            if z["rolle"] == "admin" and z["status"] == "aktiv" and self._aktive_admins() <= 1:
                raise KontoFehler("Der letzte Administrator kann nicht geloescht werden.", 400)
            self.db.execute("DELETE FROM benutzer WHERE id=?", (benutzer_id,))
            self.db.commit()
