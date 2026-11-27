"""Anmeldung und Zugriffsschutz der Phonebox: Routen, Cookie, Bremse gegen Raten."""
import asyncio
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from konten import Bremse, KontoFehler
from protokoll import log

COOKIE = "phonebox_session"
router = APIRouter()
konten = None
ordner = Path(".")

bremse_konto = Bremse(max_fehler=5, fenster=600, sperre=300)  # pro Adresse und Name
bremse_adresse = Bremse(max_fehler=20, fenster=600, sperre=300)  # pro Adresse, gegen das Durchprobieren vieler Namen
bremse_anlegen = Bremse(max_fehler=10, fenster=3600, sperre=3600)  # neue Konten pro Adresse und Stunde


def einrichten(k, seiten_ordner):
    global konten, ordner
    konten, ordner = k, Path(seiten_ordner)


def ist_lokal(host):
    return host in ("127.0.0.1", "::1", "localhost") or str(host).startswith("::ffff:127.")


WEITERLEITUNG = ("x-forwarded-for", "forwarded", "x-real-ip", "cf-connecting-ip", "x-forwarded-host")


def lokal(request):
    """Nur wirklich vom PC selbst. Kommt die Anfrage ueber einen Tunnel oder Proxy auf dem PC
    (erkennbar an Weiterleitungs-Kopfzeilen), gilt sie als von aussen."""
    return ist_lokal(adresse(request)) and not any(h in request.headers for h in WEITERLEITUNG)


def benutzer_aus(cookies):
    return konten.sitzung_pruefen(cookies.get(COOKIE)) if cookies.get(COOKIE) else None


def adresse(request):
    return request.client.host if request.client else "?"


def fehler_antwort(text, status=400):
    return JSONResponse({"fehler": text}, status_code=status, headers={"Cache-Control": "no-store"})


def cookie_setzen(antwort, token, dauer):
    antwort.set_cookie(COOKIE, token, httponly=True, samesite="lax", path="/", max_age=dauer)


def seite(name):
    html = (ordner / name).read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


def warte_text(sekunden):
    return f"Zu viele Versuche. Bitte warte {max(1, (sekunden + 59) // 60)} Minute(n)."


class Name(BaseModel):
    name: str = Field(max_length=100)


class RegistrierenEin(Name):
    passwort: str = Field(max_length=400)


class AnmeldenEin(RegistrierenEin):
    merken: bool = False


class PwAendernEin(BaseModel):
    altes: str = Field(max_length=400)
    neues: str = Field(max_length=400)


class PasswortEin(BaseModel):
    passwort: str = Field(max_length=400)


class ZuruecksetzenEin(Name):
    code: str = Field(max_length=100)
    neues: str = Field(max_length=400)


class AktionEin(BaseModel):
    id: int
    aktion: str = Field(max_length=20)


class EinstellungEin(BaseModel):
    registrierung: str = Field(max_length=20)


# ---------------------------------------------------------------- Seiten

@router.get("/anmelden")
async def anmelden_seite(request: Request):
    if benutzer_aus(request.cookies):
        return RedirectResponse("/", status_code=303)
    return seite("anmelden.html")


@router.get("/konto")
async def konto_seite(request: Request):
    if not benutzer_aus(request.cookies):
        return RedirectResponse("/anmelden", status_code=303)
    return seite("konto.html")


# ---------------------------------------------------------------- Konto-Schnittstelle

@router.get("/api/start")
async def start_info():
    """Oeffentlich: was die Anmeldeseite zum Beschriften braucht."""
    return JSONResponse({"ersteinrichtung": konten.anzahl_benutzer() == 0, "registrierung": konten.registrierung()},
                        headers={"Cache-Control": "no-store"})


@router.get("/api/ich")
async def ich(request: Request):
    b = benutzer_aus(request.cookies)
    if not b:
        return fehler_antwort("Nicht angemeldet.", 401)
    return JSONResponse({"id": b["id"], "name": b["name"], "rolle": b["rolle"],
                         "codes_uebrig": konten.codes_uebrig(b["id"])}, headers={"Cache-Control": "no-store"})


@router.post("/api/registrieren")
async def registrieren(ein: RegistrierenEin, request: Request):
    ip = adresse(request)
    rest = bremse_anlegen.rest(ip)
    if rest:
        return fehler_antwort(warte_text(rest), 429)
    bremse_anlegen.fehler(ip)  # jeder Versuch zaehlt
    try:
        benutzer, codes = await asyncio.to_thread(konten.registrieren, ein.name, ein.passwort, lokal(request))
    except KontoFehler as f:
        return fehler_antwort(f.text, f.status)
    log(f"Konto angelegt: {benutzer['name']} ({benutzer['rolle']}, {benutzer['status']}) von {ip}")
    antwort = JSONResponse({"ok": True, "name": benutzer["name"], "status": benutzer["status"],
                            "rolle": benutzer["rolle"], "codes": codes},
                           headers={"Cache-Control": "no-store"})
    if benutzer["status"] == "aktiv":  # gleich angemeldet
        token, dauer = konten.sitzung_erstellen(benutzer["id"], merken=False)
        cookie_setzen(antwort, token, dauer)
    return antwort


@router.post("/api/anmelden")
async def anmelden(ein: AnmeldenEin, request: Request):
    ip = adresse(request)
    schluessel = f"{ip}|{ein.name.strip().lower()}"
    rest = max(bremse_konto.rest(schluessel), bremse_adresse.rest(ip))
    if rest:
        return fehler_antwort(warte_text(rest), 429)
    try:
        token, benutzer, dauer = await asyncio.to_thread(konten.anmelden, ein.name, ein.passwort, ein.merken)
    except KontoFehler as f:
        if f.status == 401:  # nur falsche Zugangsdaten zaehlen als Fehlversuch
            bremse_konto.fehler(schluessel)
            bremse_adresse.fehler(ip)
            log(f"Anmeldung fehlgeschlagen: {ein.name[:30]!r} von {ip}")
        return fehler_antwort(f.text, f.status)
    bremse_konto.erfolg(schluessel)
    log(f"Angemeldet: {benutzer['name']} von {ip}")
    antwort = JSONResponse({"ok": True, "name": benutzer["name"], "rolle": benutzer["rolle"]},
                           headers={"Cache-Control": "no-store"})
    cookie_setzen(antwort, token, dauer)
    return antwort


@router.post("/api/abmelden")
async def abmelden(request: Request):
    konten.abmelden(request.cookies.get(COOKIE))
    antwort = JSONResponse({"ok": True})
    antwort.delete_cookie(COOKIE, path="/")
    return antwort


def brauche_login(request):
    b = benutzer_aus(request.cookies)
    return b, (None if b else fehler_antwort("Nicht angemeldet.", 401))


@router.post("/api/passwort-aendern")
async def passwort_aendern(ein: PwAendernEin, request: Request):
    b, fehler = brauche_login(request)
    if fehler:
        return fehler
    schluessel = f"{adresse(request)}|{b['name'].lower()}"
    rest = bremse_konto.rest(schluessel)
    if rest:
        return fehler_antwort(warte_text(rest), 429)
    try:
        await asyncio.to_thread(konten.passwort_aendern, b["id"], ein.altes, ein.neues, request.cookies.get(COOKIE))
    except KontoFehler as f:
        if f.status == 403:
            bremse_konto.fehler(schluessel)
        return fehler_antwort(f.text, f.status)
    bremse_konto.erfolg(schluessel)
    log(f"Passwort geaendert: {b['name']}")
    return JSONResponse({"ok": True})


@router.post("/api/codes-neu")
async def codes_neu(ein: PasswortEin, request: Request):
    b, fehler = brauche_login(request)
    if fehler:
        return fehler
    schluessel = f"{adresse(request)}|{b['name'].lower()}"
    rest = bremse_konto.rest(schluessel)
    if rest:
        return fehler_antwort(warte_text(rest), 429)
    try:
        codes = await asyncio.to_thread(konten.codes_neu, b["id"], ein.passwort)
    except KontoFehler as f:
        if f.status == 403:
            bremse_konto.fehler(schluessel)
        return fehler_antwort(f.text, f.status)
    bremse_konto.erfolg(schluessel)
    return JSONResponse({"ok": True, "codes": codes}, headers={"Cache-Control": "no-store"})


@router.post("/api/zuruecksetzen")
async def zuruecksetzen(ein: ZuruecksetzenEin, request: Request):
    ip = adresse(request)
    schluessel = f"reset|{ip}|{ein.name.strip().lower()}"
    rest = max(bremse_konto.rest(schluessel), bremse_adresse.rest(ip))
    if rest:
        return fehler_antwort(warte_text(rest), 429)
    try:
        await asyncio.to_thread(konten.zuruecksetzen, ein.name, ein.code, ein.neues)
    except KontoFehler as f:
        if f.status == 403:  # falscher Name oder Code
            bremse_konto.fehler(schluessel)
            bremse_adresse.fehler(ip)
            log(f"Zuruecksetzen fehlgeschlagen: {ein.name[:30]!r} von {ip}")
        return fehler_antwort(f.text, f.status)
    bremse_konto.erfolg(schluessel)
    log(f"Passwort zurueckgesetzt: {ein.name[:30]} von {ip}")
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------- Verwaltung (nur Admin)

def brauche_admin(request):
    b, fehler = brauche_login(request)
    if fehler:
        return None, fehler
    if b["rolle"] != "admin":
        return None, fehler_antwort("Das darf nur ein Administrator.", 403)
    return b, None


@router.get("/api/benutzer")
async def benutzer_liste(request: Request):
    b, fehler = brauche_admin(request)
    if fehler:
        return fehler
    return JSONResponse({"benutzer": konten.liste(), "registrierung": konten.registrierung(), "ich": b["id"]},
                        headers={"Cache-Control": "no-store"})


@router.post("/api/benutzer/aktion")
async def benutzer_aktion(ein: AktionEin, request: Request):
    b, fehler = brauche_admin(request)
    if fehler:
        return fehler
    try:
        if ein.aktion == "freigeben":
            konten.status_setzen(ein.id, "aktiv", b["id"])
        elif ein.aktion == "sperren":
            konten.status_setzen(ein.id, "gesperrt", b["id"])
        elif ein.aktion in ("admin", "benutzer"):
            konten.rolle_setzen(ein.id, ein.aktion, b["id"])
        elif ein.aktion == "loeschen":
            konten.loeschen(ein.id, b["id"])
        else:
            return fehler_antwort("Unbekannte Aktion.")
    except KontoFehler as f:
        return fehler_antwort(f.text, f.status)
    log(f"Admin {b['name']}: {ein.aktion} fuer Konto {ein.id}")
    return JSONResponse({"ok": True})


@router.post("/api/einstellungen")
async def einstellungen(ein: EinstellungEin, request: Request):
    b, fehler = brauche_admin(request)
    if fehler:
        return fehler
    try:
        konten.registrierung_setzen(ein.registrierung)
    except KontoFehler as f:
        return fehler_antwort(f.text, f.status)
    log(f"Admin {b['name']}: Registrierung = {ein.registrierung}")
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------- Schutz gegen fremde Webseiten

def pruefe_herkunft(request: Request):
    """Aenderungen ueber /api nur mit eigenem Kopfzeilen-Eintrag (eine fremde Webseite kann den nicht setzen)."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api/") \
            and request.headers.get("x-phonebox") != "1":
        return fehler_antwort("Ungueltige Anfrage.", 403)
    return None


def herkunft_passt(headers):
    """WebSocket: Der Origin-Kopf (falls vorhanden) muss zum Host passen."""
    origin = headers.get("origin")
    return not origin or urlparse(origin).netloc == headers.get("host")
