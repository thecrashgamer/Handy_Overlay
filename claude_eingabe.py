"""Warteschlange fuer Anweisungen, die man auf dem Handy an Claude Code schickt.

Eine Anweisung wartet hier, bis ein Hook von Claude Code sie abholt (zum Beispiel wenn Claude fertig ist oder den naechsten
Schritt macht). Aus Sicherheitsgruenden verfaellt sie nach 15 Minuten: Eine Anweisung von vorhin darf nicht Stunden spaeter
ploetzlich losgehen. Alles liegt nur im Arbeitsspeicher, nichts wird auf die Festplatte geschrieben.
"""
import itertools

MAX_TEXT = 2000
MAX_WARTEND = 5
VERFALL_MS = 15 * 60 * 1000
MAX_ANZEIGE = 8  # so viele Eintraege (auch erledigte) bleiben sichtbar


class EingabeFehler(Exception):
    pass


class Eingabe:
    def __init__(self):
        self._eintraege = []
        self._ids = itertools.count(1)

    # --- Schreiben
    def einreihen(self, text, von, jetzt):
        text = str(text or "").strip()
        if not text:
            raise EingabeFehler("Schreib erst etwas.")
        if len(text) > MAX_TEXT:
            raise EingabeFehler(f"Der Text ist zu lang (hoechstens {MAX_TEXT} Zeichen).")
        self.aufraeumen(jetzt)
        if len(self.wartende()) >= MAX_WARTEND:
            raise EingabeFehler(f"Es warten schon {MAX_WARTEND} Anweisungen. Warte, bis Claude sie abgeholt hat.")
        eintrag = {"id": next(self._ids), "text": text, "von": str(von), "zeit": jetzt, "status": "wartet", "erledigt": None}
        self._eintraege.append(eintrag)
        self._eintraege = self._eintraege[-(MAX_ANZEIGE + MAX_WARTEND):]
        return dict(eintrag)

    def zurueckziehen(self, eintrag_id):
        """Eine noch wartende Anweisung zurueckziehen. True, wenn sie noch wartete."""
        for e in self._eintraege:
            if e["id"] == eintrag_id and e["status"] == "wartet":
                e["status"], e["erledigt"] = "zurueckgezogen", None
                return True
        return False

    # --- Abholen (durch einen Hook)
    def wartende(self):
        return [e for e in self._eintraege if e["status"] == "wartet"]

    def abholen(self, jetzt):
        """Gibt den Text aller wartenden Anweisungen zurueck (aelteste zuerst) und markiert sie als uebergeben."""
        self.aufraeumen(jetzt)
        offen = self.wartende()
        if not offen:
            return None
        for e in offen:
            e["status"], e["erledigt"] = "uebergeben", jetzt
        return "\n\n".join(e["text"] for e in offen)

    def aufraeumen(self, jetzt):
        """Verfallene Anweisungen verwerfen. True, wenn sich etwas geaendert hat."""
        geaendert = False
        for e in self._eintraege:
            if e["status"] == "wartet" and jetzt - e["zeit"] > VERFALL_MS:
                e["status"], e["erledigt"] = "verfallen", jetzt
                geaendert = True
        return geaendert

    # --- Anzeige
    def anzeige(self, nur_von=None):
        """Fuer die Oberflaeche: die letzten Eintraege, neueste zuletzt. Mit nur_von sieht man nur eigene."""
        liste = [e for e in self._eintraege if nur_von is None or e["von"] == nur_von][-MAX_ANZEIGE:]
        return [{"id": e["id"], "text": e["text"], "status": e["status"], "zeit": e["zeit"], "von": e["von"]} for e in liste]

    def leeren(self):
        for e in self._eintraege:
            if e["status"] == "wartet":
                e["status"], e["erledigt"] = "zurueckgezogen", None
