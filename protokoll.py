"""Kleines Protokoll: Meldungen erscheinen im Konsolenfenster UND unter /log im Browser.
So lassen sich Fehler auch lesen, wenn der Server unsichtbar (pythonw) laeuft."""
import time
from collections import deque

zeilen = deque(maxlen=300)


def log(*teile):
    text = time.strftime("%H:%M:%S ") + " ".join(str(t) for t in teile)
    zeilen.append(text)
    try:
        print(text)
    except Exception:
        pass
