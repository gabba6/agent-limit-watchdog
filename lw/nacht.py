"""Nachtmodus (v1.1): nur Sitzungen im Nachtmodus werden nach dem Reset automatisch fortgesetzt.

Der Nachtmodus gilt bis zur nächsten Berichtszeit ([bericht] uhrzeit, Standard 08:00) und schaltet sich
dann von selbst ab (es wird nur ein Zeitstempel verglichen). Zwei Stufen:
  je Sitzung   Feld `nacht_bis` in der Sitzungsdatei (state/sitzungen/<anbieter>-<id>.json)
  alle         state/nacht.json {"alle_bis": ts}: gilt für jede Sitzung, auch später gestartete

Einschalten: `waechter.py nacht an [sitzung|alle]`, in Claude-Sitzungen `#nacht` tippen (der Hook fängt
die Eingabe ab, kein Modellaufruf). Ohne Nachtmodus wird nach dem Reset nichts automatisch fortgesetzt
(abschaltbar mit [fortsetzen] nur_mit_nachtmodus = false).
"""

import os
import re
import time

from . import register, util

DATEI = ("state", "nacht.json")
STANDARD_UHRZEIT = "08:00"
ALLE = ("alle", "all")
AN = ("an", "on", "ein")
AUS = ("aus", "off")

# "#nacht", "#nacht an", "#nacht aus", "#nacht alle", "#night on", "#night off", "#night all" (ohne Groß/klein)
BEFEHL = re.compile(r"^#(?:nacht|night)(?:\s+(an|on|ein|aus|off|alle|all))?\s*$", re.IGNORECASE)


def ende(now, uhrzeit=STANDARD_UHRZEIT):
    """Nächster Zeitpunkt `uhrzeit` (lokal) strikt nach now."""
    try:
        h, m = (int(x) for x in str(uhrzeit or STANDARD_UHRZEIT).split(":"))
    except ValueError:
        h, m = 8, 0
    lt = time.localtime(now)
    ziel = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, m, 0, 0, 0, -1))
    if ziel <= now:
        # Folgetag über die mktime-Normalisierung (now + 86400 springt vor der Sommerzeit einen Tag zu weit)
        ziel = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + 1, h, m, 0, 0, 0, -1))
    return ziel


def global_bis(now):
    """Ende des Nachtmodus für alle Sitzungen oder None."""
    d = util.lies_json(util.pfad(*DATEI), {}) or {}
    bis = d.get("alle_bis")
    return bis if bis and bis > now else None


def bis(s, now):
    """Bis wann gilt der Nachtmodus für diese Sitzung (eigener oder globaler)? -> ts oder None."""
    werte = [w for w in ((s or {}).get("nacht_bis"), global_bis(now)) if w and w > now]
    return max(werte) if werte else None


def aktiv(s, now):
    return bis(s, now) is not None


def befehl(prompt):
    """'#nacht …' erkennen -> ("an" | "aus", alle: bool) oder None."""
    m = BEFEHL.match((prompt or "").strip())
    if not m:
        return None
    wort = (m.group(1) or "an").lower()
    if wort in ALLE:
        return "an", True
    return ("aus" if wort in AUS else "an"), False


def alle_an(now, uhrzeit=STANDARD_UHRZEIT):
    b = ende(now, uhrzeit)
    util.schreib_json(util.pfad(*DATEI), {"alle_bis": b, "seit": now})
    util.ereignis("nachtmodus", anbieter="", weg="an", art="alle", bis=b)
    return b


def alle_aus(now):
    util.schreib_json(util.pfad(*DATEI), {"alle_bis": None, "beendet": now})
    util.ereignis("nachtmodus", anbieter="", weg="aus", art="alle")


def sitzung_an(anbieter, sid, now, uhrzeit=STANDARD_UHRZEIT, aenderung=None):
    """Nachtmodus für eine Sitzung einschalten. aenderung(d): optional weitere Felder (z. B. vom Hook)."""
    b = ende(now, uhrzeit)

    def setzen(d):
        if aenderung:
            aenderung(d)
        d["nacht_bis"] = b
    d = register.aktualisieren(anbieter, sid, setzen, "Nachtmodus an")
    util.ereignis("nachtmodus", anbieter=anbieter, sitzung=sid, cwd=d.get("cwd"), weg="an", bis=b)
    return b


def sitzung_aus(anbieter, sid, now, aenderung=None):
    def loeschen(d):
        if aenderung:
            aenderung(d)
        d["nacht_bis"] = None
    d = register.aktualisieren(anbieter, sid, loeschen, "Nachtmodus aus")
    util.ereignis("nachtmodus", anbieter=anbieter, sitzung=sid, cwd=d.get("cwd"), weg="aus")


def nachholbar(s, now, stunden=12):
    """Wartet diese Sitzung schon auf „weiter“ und ist der Nachtmodus jetzt an? Dann holt der Tick die
    Fortsetzung nach (Nachtmodus erst nach dem Reset eingeschaltet). Nur jüngere Fälle, keine alten Sitzungen."""
    return (s.get("status") == "wartet_auf_weiter" and aktiv(s, now)
            and now - (s.get("status_seit") or 0) < stunden * 3600)


def finden(ziel, now, max_alter_tage=2):
    """Sitzungen zu einem Ziel: Anfang der Session-/Thread-ID (ab 4 Zeichen) oder Name des Projektordners.
    Nur Sitzungen der letzten Tage, die nicht beendet sind."""
    ziel = (ziel or "").strip()
    if not ziel:
        return []
    kandidaten = [s for s in register.alle() if s.get("status") != "beendet"
                  and now - (s.get("zuletzt") or 0) < max_alter_tage * 86400]
    per_id = [s for s in kandidaten if len(ziel) >= 4 and str(s.get("id", "")).startswith(ziel)]
    if per_id:
        return per_id
    return [s for s in kandidaten if os.path.basename((s.get("cwd") or "").rstrip("/")) == ziel]
