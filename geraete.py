"""GPU-Auslastung und Akkustaende angeschlossener Geraete (Headset, Maus, Controller ...).

Ohne zusaetzliche Pakete: nvidia-smi (NVIDIA-Treiber), Windows-Leistungsdaten per PowerShell, die Bluetooth-Akkuanzeige
von Windows, XInput (Xbox-Controller) und psutil (Akku des PCs). Das Auswerten der Rohdaten (parse_*) ist vom Abrufen
getrennt und laesst sich ohne Windows testen. Fehlt etwas, liefert die jeweilige Funktion einfach eine leere Liste.

Diagnose am PC:  python geraete.py   (zeigt, was gefunden wurde, und die Rohdaten)
"""
import csv
import ctypes
import io
import json
import os
import re
import shutil
import subprocess
import sys

KEIN_FENSTER = 0x08000000  # kein aufblitzendes Konsolenfenster
STUFEN = {0: ("Leer", 5), 1: ("Niedrig", 25), 2: ("Mittel", 60), 3: ("Voll", 100)}  # XInput kennt nur 4 Stufen


# ---------------------------------------------------------------- Hilfen

def _ausfuehren(kommando, timeout=8):
    """Startet ein Programm ohne Fenster. Gibt die Ausgabe zurueck, bei jedem Problem einen leeren Text."""
    try:
        r = subprocess.run(kommando, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
                           creationflags=KEIN_FENSTER if os.name == "nt" else 0)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _powershell(skript, timeout=15):
    vorspann = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ErrorActionPreference='SilentlyContinue'; "
    return _ausfuehren(["powershell", "-NoProfile", "-NonInteractive", "-Command", vorspann + skript], timeout)


def _zahl(text):
    """'[N/A]', '[Not Supported]' oder leer ergibt None, sonst eine ganze Zahl."""
    try:
        return int(round(float(str(text).strip())))
    except (ValueError, TypeError):
        return None


def _liste(daten):
    """PowerShell macht aus genau einem Eintrag ein Objekt statt einer Liste: immer eine Liste daraus machen."""
    if daten is None:
        return []
    return daten if isinstance(daten, list) else [daten]


def _json(text):
    try:
        return json.loads(text) if text and text.strip() else None
    except ValueError:
        return None


# ---------------------------------------------------------------- GPU

def parse_nvidia(text):
    """Ausgabe von: nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits"""
    gpus = []
    for zeile in csv.reader(io.StringIO(text or ""), skipinitialspace=True):
        if len(zeile) < 5:
            continue
        name, last, benutzt, gesamt, temp = (z.strip() for z in zeile[:5])
        auslastung = _zahl(last)
        if not name or auslastung is None:
            continue
        gpus.append({"name": name, "auslastung": max(0, min(100, auslastung)),
                     "vram_benutzt": _zahl(benutzt), "vram_gesamt": _zahl(gesamt), "temperatur": _zahl(temp)})
    return gpus


def _nvidia_smi():
    pfad = shutil.which("nvidia-smi")
    if not pfad:
        for kandidat in (os.path.expandvars(r"%ProgramFiles%\NVIDIA Corporation\NVSMI\nvidia-smi.exe"),
                         os.path.expandvars(r"%SystemRoot%\System32\nvidia-smi.exe")):
            if os.path.isfile(kandidat):
                pfad = kandidat
                break
    return pfad


_ENGINE = re.compile(r"(luid_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+_phys_\d+).*?engtype_(\w+)")
_ADAPTER = re.compile(r"(luid_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+_phys_\d+)")


def parse_gpu_windows(daten):
    """Auswertung der Windows-Leistungsdaten (fuer AMD, Intel und alles ohne nvidia-smi).
    Wie im Task-Manager: Pro Karte werden die Engines je Typ summiert, der hoechste Typ gilt als Auslastung."""
    daten = daten if isinstance(daten, dict) else {}
    summen = {}
    for e in _liste(daten.get("engines")):
        if not isinstance(e, dict):
            continue
        treffer = _ENGINE.search(str(e.get("Name", "")))
        wert = _zahl(e.get("UtilizationPercentage"))
        if treffer and wert is not None:
            schluessel = (treffer.group(1), treffer.group(2))
            summen[schluessel] = summen.get(schluessel, 0) + wert
    auslastung = {}
    for (karte, _typ), s in summen.items():
        auslastung[karte] = max(auslastung.get(karte, 0), s)
    speicher = {}
    for m in _liste(daten.get("speicher")):
        if isinstance(m, dict):
            treffer = _ADAPTER.search(str(m.get("Name", "")))
            byte = _zahl(m.get("DedicatedUsage"))
            if treffer and byte is not None:
                speicher[treffer.group(1)] = speicher.get(treffer.group(1), 0) + byte
    karten = [str(k.get("Name", "")).strip() for k in _liste(daten.get("karten")) if isinstance(k, dict) and k.get("Name")]
    echte = [k for k in karten if not re.search(r"microsoft|basic|remote|virtual", k, re.I)] or karten
    adapter = set(auslastung) | set(speicher)
    if not adapter:
        return []
    # Die Karte mit dem meisten Grafikspeicher ist meist die starke (dedizierte) Karte
    haupt = max(adapter, key=lambda a: (speicher.get(a, 0), auslastung.get(a, 0)))
    dediziert = [k for k in echte if not re.search(r"intel|uhd|iris", k, re.I)]
    name = (dediziert or echte or ["GPU"])[0]
    return [{"name": name, "auslastung": max(0, min(100, auslastung.get(haupt, 0))),
             "vram_benutzt": round(speicher[haupt] / 1048576) if haupt in speicher else None,
             "vram_gesamt": None, "temperatur": None}]


_GPU_SKRIPT = (
    "$e=Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine | Select-Object Name,UtilizationPercentage;"
    "$m=Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory | Select-Object Name,DedicatedUsage;"
    "$c=Get-CimInstance Win32_VideoController | Select-Object Name;"
    "@{engines=@($e);speicher=@($m);karten=@($c)} | ConvertTo-Json -Compress -Depth 3"
)


def gpu_lesen():
    """Liste der Grafikkarten. NVIDIA ueber nvidia-smi (genau und schnell), sonst ueber die Windows-Leistungsdaten."""
    pfad = _nvidia_smi()
    if pfad:
        gpus = parse_nvidia(_ausfuehren([pfad, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                                         "--format=csv,noheader,nounits"], timeout=5))
        if gpus:
            return gpus
    if os.name == "nt":
        return parse_gpu_windows(_json(_powershell(_GPU_SKRIPT, timeout=15)))
    return []


# ---------------------------------------------------------------- Akkus

ARTEN = (
    ("kopfhoerer", r"head ?set|head ?phone|kopfh|ohrh|earbud|buds|airpods|arctis|jabra|bose|\bwh-|\bwf-|\bqc\d|sennheiser|\bhyperx cloud|soundcore"),
    ("maus", r"mouse|maus|\bmx (master|anywhere)|\bg\d{3}\b|trackball|razer (deathadder|viper|basilisk)"),
    ("tastatur", r"keyboard|tastatur|\bmx keys|\bk\d{3}\b"),
    ("controller", r"controller|gamepad|xbox|dualsense|dualshock|wireless controller|joy-?con|pro controller"),
)


def art_von(name):
    for art, muster in ARTEN:
        if re.search(muster, str(name), re.I):
            return art
    return "geraet"


def parse_bluetooth(daten):
    """Auswertung der Bluetooth-Abfrage: Liste aus {Name, Akku, Verbunden}. Getrennte Geraete werden ausgelassen."""
    akkus, gesehen = [], set()
    for e in _liste(daten):
        if not isinstance(e, dict):
            continue
        name, prozent = str(e.get("Name") or "").strip(), _zahl(e.get("Akku"))
        if not name or prozent is None or not 0 <= prozent <= 100 or e.get("Verbunden") is False:
            continue
        if name.lower() in gesehen:  # Bluetooth-Geraete tauchen oft mehrfach auf
            continue
        gesehen.add(name.lower())
        akkus.append({"name": name, "art": art_von(name), "prozent": prozent, "stufe": None, "laedt": None})
    return akkus


_BT_SKRIPT = (
    "Get-PnpDevice -Class Bluetooth -PresentOnly | Where-Object { $_.InstanceId -like 'BTHENUM\\DEV_*' -or $_.InstanceId -like 'BTHLE\\DEV_*' } | "
    "ForEach-Object { $id=$_.InstanceId; "
    "$a=(Get-PnpDeviceProperty -InstanceId $id -KeyName '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2').Data; "
    "$v=(Get-PnpDeviceProperty -InstanceId $id -KeyName '{83DA6326-97A6-4088-9453-A1923F573B29} 15').Data; "
    "if ($a -ne $null) { [pscustomobject]@{Name=$_.FriendlyName; Akku=[int]$a; Verbunden=$v} } } | ConvertTo-Json -Compress"
)


def _bluetooth_akkus():
    if os.name != "nt":
        return []
    return parse_bluetooth(_json(_powershell(_BT_SKRIPT, timeout=20)))


def xinput_stufe(typ, stufe):
    """XInput: BatteryType (0 getrennt, 1 Kabel, 2 Alkali, 3 Akku, 255 unbekannt) und BatteryLevel (0 bis 3)
    -> (Anzeigetext oder None, ungefaehre Prozent oder None, 'Kabel'?). None, wenn kein Controller da ist."""
    if typ == 0:
        return None
    if typ == 1:
        return ("Kabel", None, True)
    text, prozent = STUFEN.get(stufe, (None, None))
    return (text, prozent, False) if text else None


def _xinput_akkus():
    if os.name != "nt":
        return []

    class Batterie(ctypes.Structure):
        _fields_ = [("BatteryType", ctypes.c_ubyte), ("BatteryLevel", ctypes.c_ubyte)]

    dll = None
    for name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            dll = ctypes.WinDLL(name)
            break
        except OSError:
            continue
    if dll is None or not hasattr(dll, "XInputGetBatteryInformation"):
        return []
    akkus = []
    for nr in range(4):
        info = Batterie()
        if dll.XInputGetBatteryInformation(nr, 0, ctypes.byref(info)) != 0:  # 0 = Erfolg, sonst nicht verbunden
            continue
        erg = xinput_stufe(info.BatteryType, info.BatteryLevel)
        if erg is None:
            continue
        text, prozent, kabel = erg
        akkus.append({"name": f"Xbox-Controller {nr + 1}", "art": "controller", "prozent": prozent,
                      "stufe": text, "laedt": None, "kabel": kabel})
    return akkus


def _pc_akku():
    """Akku des PCs selbst (Laptop). Ein normaler Desktop-PC hat keinen."""
    try:
        import psutil

        b = psutil.sensors_battery()
    except Exception:
        return []
    if b is None or b.percent is None:
        return []
    return [{"name": "PC (Akku)", "art": "pc", "prozent": int(round(b.percent)), "stufe": None, "laedt": bool(b.power_plugged)}]


def akkus_lesen():
    return _bluetooth_akkus() + _xinput_akkus() + _pc_akku()


# ---------------------------------------------------------------- Testdaten

class TestGeraete:
    """Feste Beispieldaten fuer den Testmodus (PHONEBOX_TEST=1): kein Windows und keine echten Geraete noetig."""

    def __init__(self, leer=False):
        self.leer = leer

    def gpu(self):
        return [] if self.leer else [{"name": "Test-GPU", "auslastung": 37, "vram_benutzt": 2048, "vram_gesamt": 8192, "temperatur": 54}]

    def akkus(self):
        if self.leer:
            return []
        return [
            {"name": "Test-Headset", "art": "kopfhoerer", "prozent": 82, "stufe": None, "laedt": False},
            {"name": "Test-Maus", "art": "maus", "prozent": 12, "stufe": None, "laedt": False},
            {"name": "Xbox-Controller 1", "art": "controller", "prozent": 60, "stufe": "Mittel", "laedt": None, "kabel": False},
            {"name": "PC (Akku)", "art": "pc", "prozent": 55, "stufe": None, "laedt": True},
        ]


def erstellen(test, leer=False):
    if test:
        t = TestGeraete(leer)
        return t.gpu, t.akkus
    return gpu_lesen, akkus_lesen


# ---------------------------------------------------------------- Diagnose

def diagnose():
    print("=== GPU")
    pfad = _nvidia_smi()
    print("nvidia-smi:", pfad or "nicht gefunden")
    if pfad:
        roh = _ausfuehren([pfad, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"], 5)
        print("Rohdaten:", roh.strip() or "(leer)")
    print("Ergebnis:", json.dumps(gpu_lesen(), ensure_ascii=False))
    if os.name == "nt":
        print("Windows-Leistungsdaten (Rohdaten, gekuerzt):", _powershell(_GPU_SKRIPT, 20)[:600] or "(leer)")
    print("\n=== Akkus")
    if os.name == "nt":
        print("Bluetooth (Rohdaten):", _powershell(_BT_SKRIPT, 25).strip() or "(leer: kein Geraet meldet einen Akkustand)")
    print("Ergebnis:", json.dumps(akkus_lesen(), ensure_ascii=False, indent=1))
    print("\nTipp: Meldet ein Geraet hier nichts, liegt es meist am Geraet: Funkgeraete mit eigenem USB-Stick und")
    print("PlayStation-Controller geben ihren Akkustand nicht ueber Windows weiter.")


if __name__ == "__main__":
    diagnose()
    sys.exit(0)
