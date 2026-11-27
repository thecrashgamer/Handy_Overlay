"""Aktualisiert die Phonebox auf die neueste Version, ohne deine Daten anzufassen.

  python update.py                  neueste Version von GitHub laden, einspielen, Server neu starten
  python update.py --trocken        nur zeigen, was sich aendern wuerde
  python update.py --zurueck        die Dateien der letzten Sicherung wiederherstellen
  python update.py --quelle X       X = Webadresse oder Pfad einer ZIP-Datei (statt GitHub)
  python update.py --ohne-neustart  Dateien tauschen, den Server aber nicht neu starten
  python update.py --ohne-pip       die Pakete (requirements.txt) nicht pruefen
  python update.py --status DATEI   den Verlauf zusaetzlich als JSON in DATEI schreiben (nutzt der Admin-Bereich)

Der Ordner "daten" (Konten, Shortcuts, Zertifikate) und ".git" werden nie veraendert. Alles, was ersetzt wird,
liegt vorher als Sicherung in daten/update-sicherung/. Es werden nur Dateien aus der ZIP geschrieben, nie geloescht.
"""
import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

QUELLE_STANDARD = "https://github.com/thecrashgamer/Handy_Overlay/archive/refs/heads/main.zip"
VERSION_URL = "https://raw.githubusercontent.com/thecrashgamer/Handy_Overlay/main/server.py"
COMMIT_URL = "https://api.github.com/repos/thecrashgamer/Handy_Overlay/commits/main"
GESCHUETZT_OBEN = {"daten", ".git"}  # niemals anfassen (oberste Ebene)
MAX_DATEIEN = 2000
MAX_BYTES = 80 * 1024 * 1024
SICHERUNGEN_BEHALTEN = 3


class UpdateFehler(Exception):
    pass


_status = {"datei": None, "zeilen": [], "daten": {}}


def status_schreiben(zustand=None, **extra):
    """Schreibt den Verlauf als JSON (atomar), damit der Admin-Bereich ihn auch waehrend eines Neustarts lesen kann."""
    if zustand:
        _status["daten"]["zustand"] = zustand
    _status["daten"].update(extra)
    if not _status["datei"]:
        return
    daten = dict(_status["daten"], zeit=int(time.time()), zeilen=_status["zeilen"][-40:])
    ziel = Path(_status["datei"])
    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
        hilfe = ziel.with_name(ziel.name + ".neu")
        hilfe.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        os.replace(hilfe, ziel)
    except OSError:
        pass  # der Status ist nur eine Anzeige, er darf das Update nie verhindern


def ausgabe(*teile):
    text = " ".join(str(t) for t in teile)
    try:
        print(text, flush=True)
    except Exception:
        pass  # ohne Konsole (pythonw) gibt es keine Ausgabe
    _status["zeilen"].append(text)
    status_schreiben()


def version_lesen(ziel):
    try:
        text = (Path(ziel) / "server.py").read_text(encoding="utf-8")
        treffer = re.search(r'^VERSION\s*=\s*"([^"]+)"', text, re.M)
        return treffer.group(1) if treffer else "unbekannt"
    except OSError:
        return "unbekannt"


# ---------------------------------------------------------------- Laden und pruefen

def holen(quelle, ziel_datei):
    """Webadresse oder lokale Datei nach ziel_datei kopieren."""
    if re.match(r"^https?://", quelle):
        anfrage = urllib.request.Request(quelle, headers={"User-Agent": "phonebox-update"})
        try:
            with urllib.request.urlopen(anfrage, timeout=30) as antwort, open(ziel_datei, "wb") as aus:
                gesamt = 0
                while True:
                    block = antwort.read(1 << 16)
                    if not block:
                        break
                    gesamt += len(block)
                    if gesamt > MAX_BYTES:
                        raise UpdateFehler("Der Download ist ungewoehnlich gross, ich breche ab.")
                    aus.write(block)
        except UpdateFehler:
            raise
        except Exception as fehler:
            raise UpdateFehler(f"Download fehlgeschlagen: {fehler}")
    else:
        if not os.path.isfile(quelle):
            raise UpdateFehler(f"Die Datei gibt es nicht: {quelle}")
        shutil.copyfile(quelle, ziel_datei)


def sicherer_pfad(name):
    """Relativer Pfad innerhalb des Ordners, sonst None (schuetzt vor '../' und absoluten Pfaden)."""
    if not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name:
        return None
    norm = posixpath.normpath(name)
    if norm.startswith("..") or norm == "." or any(t == ".." for t in norm.split("/")):
        return None
    return norm


def zip_lesen(pfad):
    """Prueft die ZIP und gibt (ZipFile, Liste von (relativer Pfad, Eintrag)) zurueck."""
    try:
        zf = zipfile.ZipFile(pfad)
    except zipfile.BadZipFile:
        raise UpdateFehler("Das ist keine gueltige ZIP-Datei.")
    eintraege = [i for i in zf.infolist() if not i.is_dir()]
    if not eintraege or len(eintraege) > MAX_DATEIEN:
        raise UpdateFehler("Die ZIP-Datei sieht nicht wie die Phonebox aus.")
    if sum(i.file_size for i in eintraege) > MAX_BYTES:
        raise UpdateFehler("Die ZIP-Datei ist entpackt ungewoehnlich gross.")
    for i in eintraege:
        if sicherer_pfad(i.filename) is None:
            raise UpdateFehler(f"Unsicherer Pfad in der ZIP-Datei: {i.filename!r}")
        if (i.external_attr >> 16) & 0o170000 == 0o120000:
            raise UpdateFehler(f"Verknuepfungen sind nicht erlaubt: {i.filename!r}")
    # GitHub packt alles in einen Ordner (z. B. "Handy_Overlay-main/"): den abschneiden
    oben = {posixpath.normpath(i.filename).split("/")[0] for i in eintraege}
    wurzel = ""
    if len(oben) == 1 and all("/" in posixpath.normpath(i.filename) for i in eintraege):
        wurzel = oben.pop() + "/"
    ergebnis = []
    for i in eintraege:
        rel = posixpath.normpath(i.filename)[len(wurzel):]
        if rel:
            ergebnis.append((rel, i))
    if "server.py" not in {r for r, _ in ergebnis}:
        raise UpdateFehler("In der ZIP-Datei fehlt server.py. Das ist nicht die Phonebox.")
    return zf, ergebnis


def ausgenommen(rel):
    teile = rel.split("/")
    return teile[0] in GESCHUETZT_OBEN or "__pycache__" in teile or rel.endswith(".pyc")


def hash_datei(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as d:
        for block in iter(lambda: d.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def vergleichen(zf, eintraege, ziel):
    """Teilt die Dateien in neu, geaendert, gleich."""
    neu, geaendert, gleich = [], [], []
    for rel, info in eintraege:
        if ausgenommen(rel):
            continue
        vorhanden = Path(ziel) / rel
        if not vorhanden.exists():
            neu.append(rel)
        elif hashlib.sha256(zf.read(info)).hexdigest() != hash_datei(vorhanden):
            geaendert.append(rel)
        else:
            gleich.append(rel)
    return neu, geaendert, gleich


# ---------------------------------------------------------------- Server stoppen und starten

def python_mit_konsole():
    """pythonw.exe (ohne Fenster) kann nicht gut mit pip reden: dort das normale python.exe nehmen."""
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        return str(exe.with_name("python.exe"))
    return str(exe)


def server_ports():
    return [int(os.environ.get("PHONEBOX_PORT", "8000")), int(os.environ.get("PHONEBOX_HTTPS_PORT", "8443"))]


def lauschende_prozesse(ports):
    """PIDs, die auf den Ports lauschen UND server.py ausfuehren (fremde Programme bleiben unberuehrt)."""
    import psutil

    pids = set()
    try:
        verbindungen = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError):
        verbindungen = []
    for c in verbindungen:
        if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port in ports and c.pid:
            try:
                if any(os.path.basename(a) == "server.py" for a in psutil.Process(c.pid).cmdline()):
                    pids.add(c.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return pids


def server_stoppen(ports):
    import psutil

    pids = lauschende_prozesse(ports)
    for pid in pids:
        try:
            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(10)
            except psutil.TimeoutExpired:
                p.kill()
        except psutil.NoSuchProcess:
            pass
    return pids


def server_starten(ziel):
    exe = sys.executable
    if os.name == "nt":  # ohne Konsolenfenster
        leise = Path(exe).with_name("pythonw.exe")
        exe = str(leise) if leise.exists() else exe
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
        subprocess.Popen([exe, "server.py"], cwd=ziel, creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen([exe, "server.py"], cwd=ziel, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def warten_bis_laeuft(ports, alte_pids, sekunden=25):
    ende = time.time() + sekunden
    while time.time() < ende:
        neue = lauschende_prozesse(ports) - set(alte_pids)
        if neue:
            return True
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------- Sicherung

def sicherung_ordner(ziel):
    return Path(ziel) / "daten" / "update-sicherung"


def sicherung_anlegen(ziel, dateien):
    ordner = sicherung_ordner(ziel) / time.strftime("%Y%m%d-%H%M%S")
    for rel in dateien:
        quelle = Path(ziel) / rel
        if quelle.exists():
            (ordner / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(quelle, ordner / rel)
    ordner.mkdir(parents=True, exist_ok=True)
    alle = sorted(p for p in sicherung_ordner(ziel).iterdir() if p.is_dir())
    for alt in alle[:-SICHERUNGEN_BEHALTEN]:
        shutil.rmtree(alt, ignore_errors=True)
    return ordner


def schreiben(zf, info, ziel_datei):
    ziel_datei.parent.mkdir(parents=True, exist_ok=True)
    hilfe = ziel_datei.with_name(ziel_datei.name + ".update-neu")
    hilfe.write_bytes(zf.read(info))
    os.replace(hilfe, ziel_datei)


# ---------------------------------------------------------------- Neueste Version erfragen, Update abgetrennt starten

def version_nummer(text):
    """'v18 (Standby)' -> 18. Unbekanntes ergibt 0."""
    treffer = re.match(r"\s*v(\d+)", str(text))
    return int(treffer.group(1)) if treffer else 0


def neueste_version(quelle=QUELLE_STANDARD):
    """Fragt (ohne zu installieren) nach der neuesten Version. Gibt {'version', 'aenderung'} zurueck."""
    if not re.match(r"^https?://", quelle):  # lokale ZIP-Datei (fuer Tests oder ein eigenes Archiv)
        zf, eintraege = zip_lesen(quelle)
        with zf:
            for rel, info in eintraege:
                if rel == "server.py":
                    treffer = re.search(r'^VERSION\s*=\s*"([^"]+)"', zf.read(info).decode("utf-8", "replace"), re.M)
                    return {"version": treffer.group(1) if treffer else "unbekannt", "aenderung": ""}
        raise UpdateFehler("In der ZIP-Datei fehlt server.py.")
    try:
        anfrage = urllib.request.Request(VERSION_URL, headers={"User-Agent": "phonebox-update"})
        with urllib.request.urlopen(anfrage, timeout=10) as antwort:
            text = antwort.read(400_000).decode("utf-8", "replace")
    except Exception as fehler:
        raise UpdateFehler(f"GitHub ist nicht erreichbar: {fehler}")
    treffer = re.search(r'^VERSION\s*=\s*"([^"]+)"', text, re.M)
    if not treffer:
        raise UpdateFehler("Die Version auf GitHub konnte nicht gelesen werden.")
    aenderung = ""
    try:  # nur ein Zusatz: was wurde zuletzt geaendert?
        anfrage = urllib.request.Request(COMMIT_URL, headers={"User-Agent": "phonebox-update", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(anfrage, timeout=6) as antwort:
            aenderung = str(json.loads(antwort.read(400_000))["commit"]["message"]).splitlines()[0][:200]
    except Exception:
        pass
    return {"version": treffer.group(1), "aenderung": aenderung}


def getrennt_starten(ziel, argumente, log_datei):
    """Startet update.py als eigenen Prozess, der weiterlaeuft, auch wenn der Server (der es startet) beendet wird."""
    ziel = Path(ziel)
    Path(log_datei).parent.mkdir(parents=True, exist_ok=True)
    kommando = [sys.executable, str(ziel / "update.py"), *argumente]
    with open(log_datei, "ab") as log:
        if os.name == "nt":
            basis = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
            for extra in (0x01000000, 0):  # erst mit CREATE_BREAKAWAY_FROM_JOB, falls der Job es nicht erlaubt ohne
                try:
                    return subprocess.Popen(kommando, cwd=ziel, creationflags=basis | extra, close_fds=True,
                                            stdin=subprocess.DEVNULL, stdout=log, stderr=log)
                except OSError:
                    if extra == 0:
                        raise
        return subprocess.Popen(kommando, cwd=ziel, start_new_session=True, stdin=subprocess.DEVNULL, stdout=log, stderr=log)


# ---------------------------------------------------------------- Ablauf

def aktualisieren(quelle=QUELLE_STANDARD, ziel=None, trocken=False, neustart=True, pip=True):
    ziel = Path(ziel or Path(__file__).parent).resolve()
    if not (ziel / "server.py").exists():
        raise UpdateFehler(f"In {ziel} liegt keine Phonebox (server.py fehlt).")
    alt_version = version_lesen(ziel)
    ausgabe(f"Phonebox in {ziel}")
    ausgabe(f"Aktuell: {alt_version}")

    with tempfile.TemporaryDirectory() as tmp:
        zip_pfad = os.path.join(tmp, "phonebox.zip")
        ausgabe("Lade die neueste Version ..." if re.match(r"^https?://", quelle) else f"Lese {quelle} ...")
        holen(quelle, zip_pfad)
        zf, eintraege = zip_lesen(zip_pfad)
        with zf:
            neu, geaendert, gleich = vergleichen(zf, eintraege, ziel)
            ausgabe(f"{len(neu)} neue, {len(geaendert)} geaenderte, {len(gleich)} unveraenderte Dateien.")
            for rel in neu:
                ausgabe("  + ", rel)
            for rel in geaendert:
                ausgabe("  ~ ", rel)
            if not neu and not geaendert:
                ausgabe("Alles ist schon auf dem neuesten Stand. Nichts zu tun.")
                return {"geaendert": 0, "neu": 0, "version": alt_version}
            if trocken:
                ausgabe("(Nur Probelauf, es wurde nichts veraendert.)")
                return {"geaendert": len(geaendert), "neu": len(neu), "version": alt_version, "trocken": True}

            ports = server_ports()
            alte_pids = server_stoppen(ports) if neustart else set()
            if alte_pids:
                ausgabe("Server beendet.")
            sicherung = sicherung_anlegen(ziel, geaendert)
            ausgabe(f"Sicherung der alten Dateien: {sicherung}")
            try:
                for rel, info in eintraege:
                    if rel in neu or rel in geaendert:
                        schreiben(zf, info, ziel / rel)
            except Exception as fehler:
                ausgabe("Fehler beim Kopieren, stelle die alten Dateien wieder her:", fehler)
                zuruecksetzen(ziel, sicherung)
                raise UpdateFehler(f"Das Update ist fehlgeschlagen und wurde zurueckgenommen: {fehler}")

    neue_version = version_lesen(ziel)
    if pip and (ziel / "requirements.txt").exists():
        ausgabe("Pruefe Pakete ...")
        r = subprocess.run([python_mit_konsole(), "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=ziel,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        if r.returncode != 0:
            ausgabe("WARNUNG: Die Pakete liessen sich nicht installieren. Fuehre 'python -m pip install -r requirements.txt' selbst aus.")
    laeuft = None
    if neustart:
        ausgabe("Starte den Server neu ...")
        server_starten(ziel)
        laeuft = warten_bis_laeuft(ports, alte_pids)
        ausgabe("Der Server laeuft." if laeuft else "WARNUNG: Der Server antwortet noch nicht. Schau nach mit 'python server.py'.")
    ausgabe(f"Fertig: {alt_version}  ->  {neue_version}")
    return {"geaendert": len(geaendert), "neu": len(neu), "version": neue_version, "laeuft": laeuft,
            "sicherung": str(sicherung)}


def zuruecksetzen(ziel, sicherung=None):
    """Kopiert die Dateien einer Sicherung zurueck (standard: die neueste)."""
    ziel = Path(ziel)
    if sicherung is None:
        ordner = sicherung_ordner(ziel)
        alle = sorted(p for p in ordner.iterdir() if p.is_dir()) if ordner.exists() else []
        if not alle:
            raise UpdateFehler("Es gibt keine Sicherung zum Wiederherstellen.")
        sicherung = alle[-1]
    sicherung = Path(sicherung)
    anzahl = 0
    for datei in sicherung.rglob("*"):
        if datei.is_file():
            rel = datei.relative_to(sicherung)
            (ziel / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(datei, ziel / rel)
            anzahl += 1
    return anzahl


def main(argv=None):
    p = argparse.ArgumentParser(description="Phonebox aktualisieren")
    p.add_argument("--quelle", default=QUELLE_STANDARD)
    p.add_argument("--trocken", action="store_true")
    p.add_argument("--zurueck", action="store_true")
    p.add_argument("--ohne-neustart", action="store_true")
    p.add_argument("--ohne-pip", action="store_true")
    p.add_argument("--status", default=None)
    a = p.parse_args(argv)
    ziel = Path(__file__).parent
    _status["datei"] = a.status
    _status["daten"] = {"von": version_lesen(ziel), "aktion": "zurueck" if a.zurueck else "update", "protokolliert": False}
    status_schreiben("laeuft", gestartet=int(time.time()))
    try:
        if a.zurueck:
            ports = server_ports()
            alte = server_stoppen(ports)
            anzahl = zuruecksetzen(ziel)
            ausgabe(f"{anzahl} Dateien aus der letzten Sicherung wiederhergestellt.")
            if not a.ohne_neustart:
                server_starten(ziel)
                ausgabe("Der Server laeuft." if warten_bis_laeuft(ports, alte) else "WARNUNG: Der Server antwortet noch nicht.")
            status_schreiben("fertig", nach=version_lesen(ziel), meldung=f"{anzahl} Dateien wiederhergestellt")
            return 0
        r = aktualisieren(a.quelle, ziel, trocken=a.trocken, neustart=not a.ohne_neustart, pip=not a.ohne_pip)
        if r.get("trocken"):
            status_schreiben("fertig", nach=r["version"], meldung="Probelauf")
        elif not r["geaendert"] and not r["neu"]:
            status_schreiben("nichts", nach=r["version"], meldung="Schon auf dem neuesten Stand")
        elif r.get("laeuft") is False:
            status_schreiben("fehler", nach=r["version"], meldung="Aktualisiert, aber der Server antwortet nicht. Starte ihn mit python server.py.")
        else:
            status_schreiben("fertig", nach=r["version"], meldung=f"{r['neu']} neue und {r['geaendert']} geaenderte Dateien")
        return 0
    except UpdateFehler as fehler:
        ausgabe("Nicht moeglich:", fehler)
        status_schreiben("fehler", meldung=str(fehler))
        return 1
    except Exception as fehler:  # nie ohne Meldung enden
        ausgabe("Unerwarteter Fehler:", repr(fehler))
        status_schreiben("fehler", meldung=f"Unerwarteter Fehler: {fehler!r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
