"""Sitzungsregister: eine Datei je Sitzung unter state/sitzungen/ (parallele Hooks ohne Konflikte).

Status einer Sitzung:
  aktiv                  läuft oder ruht normal
  sicherung              Stop-Hook hat den Sicherungsauftrag gegeben, Turn läuft noch
  gestoppt               vom Wächter geordnet angehalten, wartet auf Reset
  limit                  am Limit abgebrochen (StopFailure / Codex usage_limit_exceeded)
  eingebaut_wartet       Claudes eingebautes Auto-Continue wartet
  eingebaut_fortgesetzt  Claudes eingebautes Auto-Continue hat fortgesetzt
  stale                  Mac hat geschlafen, Claude wartet auf Enter
  disabled               eingebautes Warten ohne Fortsetzung beendet -> Wächter übernimmt
  fortgesetzt            Wächter hat fortgesetzt (Prompt gesendet / neu gestartet)
  wartet_auf_weiter      Reset erreicht, aber kein Nachtmodus -> nichts gesendet, Nutzer tippt "weiter"
  blockiert              Bildschirm unklar oder Kaufoption sichtbar -> nichts gesendet, Push
  reserve                Wochenreserve erreicht -> keine automatische Fortsetzung
  aufgegeben             zu viele Versuche in diesem Fenster
  beendet                Sitzung wurde beendet (SessionEnd) -> keine Fortsetzung
"""

import os
import re

from . import util

WARTET = ("gestoppt", "limit", "stale", "disabled", "eingebaut_wartet")
VERLAUF_MAX = 25


def _datei(anbieter, sid):
    sicher = re.sub(r"[^A-Za-z0-9_.-]", "_", str(sid))[:120]
    return util.pfad("state", "sitzungen", f"{anbieter}-{sicher}.json")


def lesen(anbieter, sid):
    return util.lies_json(_datei(anbieter, sid))


def aktualisieren(anbieter, sid, aenderung, notiz=None):
    """Liest, ändert (aenderung(d) -> None) und schreibt atomar unter Dateisperre."""
    datei = _datei(anbieter, sid)
    with util.sperre(datei):
        d = util.lies_json(datei) or {"anbieter": anbieter, "id": sid, "erstellt": util.jetzt(),
                                      "status": "aktiv", "versuche": {}, "hinweise": {}, "verlauf": []}
        vorher = d.get("status")
        aenderung(d)
        d["zuletzt"] = util.jetzt()
        if d.get("status") != vorher or notiz:
            d.setdefault("verlauf", []).append([round(util.jetzt()), d.get("status"), notiz or ""])
            d["verlauf"] = d["verlauf"][-VERLAUF_MAX:]
            d["status_seit"] = util.jetzt()
        util.schreib_json(datei, d)
        return d


def alle(anbieter=None, max_alter_tage=8):
    ordner = os.path.dirname(util.pfad("state", "sitzungen", "x"))
    grenze = util.jetzt() - max_alter_tage * 86400
    ergebnis = []
    try:
        namen = sorted(os.listdir(ordner))
    except OSError:
        return []
    for name in namen:
        if not name.endswith(".json") or name.startswith("."):
            continue
        if anbieter and not name.startswith(anbieter + "-"):
            continue
        d = util.lies_json(os.path.join(ordner, name))
        if d and d.get("zuletzt", 0) >= grenze:
            ergebnis.append(d)
    return ergebnis


def hinweis_gesetzt(d, fid, art):
    return bool(((d.get("hinweise") or {}).get(fid or "-") or {}).get(art))


def setze_hinweis(d, fid, art):
    d.setdefault("hinweise", {}).setdefault(fid or "-", {})[art] = True
    # nur die letzten Fenster aufheben
    if len(d["hinweise"]) > 6:
        for alt in sorted(d["hinweise"])[:-6]:
            d["hinweise"].pop(alt, None)


def versuche(d, fid):
    return int((d.get("versuche") or {}).get(fid or "-", 0))


def zaehle_versuch(d, fid):
    d.setdefault("versuche", {})[fid or "-"] = versuche(d, fid) + 1
    if len(d["versuche"]) > 6:
        for alt in sorted(d["versuche"])[:-6]:
            d["versuche"].pop(alt, None)


def warten_auf_reset(d, status, fid, reset, art, puffer_s, notiz=None):
    d["status"] = status
    d["fenster_id"] = fid
    d["reset"] = reset
    d["art"] = art
    d["fortsetzen_ab"] = (reset + puffer_s) if reset else None
    if notiz:
        d["grund"] = notiz
