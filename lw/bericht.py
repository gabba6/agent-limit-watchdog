"""Morgenbericht aus den Ereignissen der Nacht (lokal ausführlich, als Push nur eine Zeile)."""

import os
import time

from . import util
from .sprache import t

REIHENFOLGE = ["limit", "gestoppt", "fortgesetzt", "eingebaut", "blockiert", "haengt", "wartet_auf_freigabe",
               "freigabe_blockiert", "reserve_gesperrt", "wartet_auf_weiter", "eingebaut_gesperrt", "ueberziehung",
               "nachtmodus", "meldung"]
NICHT_RELEVANT = ("meldung", "nachtmodus")


def ueberschrift(typ):
    return t("b_" + typ)


def _zeile(e):
    zeit = time.strftime("%d.%m. %H:%M", time.localtime(e["ts"]))
    projekt = os.path.basename(e.get("cwd") or "") or ""
    teile = [zeit, e.get("anbieter", ""), projekt]
    for feld in ("weg", "grund", "text", "werkzeug", "art"):
        if e.get(feld):
            teile.append(str(e[feld])[:160])
    if e.get("dry_run"):
        teile.append("(dry-run)")
    return "- " + " · ".join(teil for teil in teile if teil)


def erstellen(seit, bis):
    ereignisse = util.lies_ereignisse(seit, bis)
    gruppen = {}
    for e in ereignisse:
        gruppen.setdefault(e.get("typ"), []).append(e)
    zeilen = [t("bericht_titel", datum=time.strftime("%d.%m.%Y %H:%M", time.localtime(bis))), "",
              t("bericht_zeitraum", von=time.strftime("%d.%m. %H:%M", time.localtime(seit)),
                bis=time.strftime("%d.%m. %H:%M", time.localtime(bis))), ""]
    relevant = 0
    for typ in REIHENFOLGE:
        liste = gruppen.get(typ) or []
        if not liste:
            continue
        if typ not in NICHT_RELEVANT:
            relevant += len(liste)
        zeilen.append(f"## {ueberschrift(typ)} ({len(liste)})")
        zeilen.extend(_zeile(e) for e in liste[-40:])
        zeilen.append("")
    if not relevant:
        zeilen.append(t("bericht_leer"))
    kurz = ", ".join(f"{len(gruppen[typ])}× {ueberschrift(typ).split(' (')[0]}" for typ in REIHENFOLGE
                     if gruppen.get(typ) and typ not in NICHT_RELEVANT)
    return {"text": "\n".join(zeilen), "relevant": relevant, "kurz": kurz}


def speichern(text, bis):
    datei = util.pfad("berichte", time.strftime("%Y-%m-%d", time.localtime(bis)) + ".md")
    with open(datei, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return datei
