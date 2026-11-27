"""Admin-Bereich: Shortcuts anlegen, aendern, loeschen. Nur fuer Administratoren."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

import auth
import shortcuts
from protokoll import log

router = APIRouter()
eigene_datei = Path("shortcuts.json")
vorlage_datei = Path("shortcuts.json")
ordner = Path(".")


def einrichten(eigene, vorlage, seiten_ordner):
    global eigene_datei, vorlage_datei, ordner
    eigene_datei, vorlage_datei, ordner = Path(eigene), Path(vorlage), Path(seiten_ordner)


class SpeichernEin(BaseModel):
    shortcuts: list = Field(max_length=100)
    passwort: str = Field(max_length=400)


@router.get("/admin")
async def admin_seite(request: Request):
    b = auth.benutzer_aus(request.cookies)
    if not b:
        return RedirectResponse("/anmelden", status_code=303)
    if b["rolle"] != "admin":
        return PlainTextResponse("Der Admin-Bereich ist nur fuer Administratoren.", status_code=403)
    return auth.seite("admin.html")


@router.get("/api/shortcuts")
async def liste_holen(request: Request):
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    quelle = eigene_datei if eigene_datei.exists() else vorlage_datei
    return JSONResponse(
        {
            "shortcuts": shortcuts.laden(quelle),
            "eigene": eigene_datei.exists(),
            "aktionen": shortcuts.AKTION_NAMEN,
            "maximal": shortcuts.MAX_SHORTCUTS,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/shortcuts/speichern")
async def speichern(ein: SpeichernEin, request: Request):
    b, fehler = auth.brauche_admin(request)
    if fehler:
        return fehler
    # Aenderungen, die Programme am PC starten, nur mit erneuter Passwort-Eingabe (falls eine Sitzung gestohlen wurde)
    schluessel = f"{auth.adresse(request)}|{b['name'].lower()}"
    rest = auth.bremse_konto.rest(schluessel)
    if rest:
        return auth.fehler_antwort(auth.warte_text(rest), 429)
    if not auth.konten.passwort_stimmt(b["id"], ein.passwort):
        auth.bremse_konto.fehler(schluessel)
        auth.konten.protokoll("sicherheit", "Shortcuts speichern mit falschem Passwort", b, auth.adresse(request))
        return auth.fehler_antwort("Das Passwort stimmt nicht.", 403)
    auth.bremse_konto.erfolg(schluessel)
    try:
        liste = shortcuts.pruefen_liste(ein.shortcuts)
    except ValueError as f:
        return auth.fehler_antwort(str(f), 400)
    shortcuts.speichern(eigene_datei, liste)
    log(f"Admin {b['name']}: Shortcuts gespeichert ({len(liste)} Eintraege): " + ", ".join(e["name"] for e in liste))
    auth.konten.protokoll("admin", f"Shortcuts gespeichert ({len(liste)} Einträge)", b, auth.adresse(request))
    return JSONResponse({"ok": True, "shortcuts": liste})
