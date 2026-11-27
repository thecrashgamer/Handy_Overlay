"""Prueft, ob index.html zur Server-Version passt (haeufiger Fehler beim Kopieren einzelner Dateien)."""
import re

MUSTER = re.compile(r'SEITE\s*=\s*"(v\d+)')


def seiten_version(html):
    treffer = MUSTER.search(html)
    return treffer.group(1) if treffer else None


def warnung(html, server_version):
    """Gibt einen Warntext zurueck, wenn die Seite nicht zum Server passt, sonst None."""
    seite = seiten_version(html)
    erwartet = server_version.split(" ")[0]
    if seite == erwartet:
        return None
    return (
        f"index.html ist veraltet (Seite: {seite or 'aelter als v10'}, Server: {erwartet}). "
        "Bitte index.html aus der neuen ZIP in den Server-Ordner kopieren."
    )


def mit_warnung(html, text):
    """Blendet die Warnung als rote Leiste in die ausgelieferte Seite ein, auch in eine alte Seite."""
    leiste = (
        '<div style="position:fixed;left:0;right:0;bottom:0;z-index:99;background:#e5484d;'
        'color:#fff;padding:12px;font:bold 15px sans-serif;text-align:center">'
        + text.replace("&", "&amp;").replace("<", "&lt;")
        + "</div>"
    )
    return html.replace("</body>", leiste + "</body>", 1) if "</body>" in html else html + leiste
