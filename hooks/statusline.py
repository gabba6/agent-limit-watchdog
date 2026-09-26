#!/usr/bin/python3
"""Statusline-Kette des Limit-Wächters (v1.3, eingetragen als statusLine in ~/.claude/settings.json).

Claude Code übergibt der Statusline per stdin JSON mit rate_limits.five_hour/seven_day. Dieses Skript
  1. schreibt die Füllstände nach <LIMIT_WAECHTER_HOME>/state/statusline.json (atomar, höchstens alle 20 s,
     außer die Werte ändern sich) – der Tick liest sie über quellen.claude_statusline();
  2. führt danach die ursprüngliche Statusline (gesichert in state/statusline-original.json) mit /bin/sh -c aus:
     stdin = unveränderte Bytes (danach geschlossen), Umgebung unverändert, stdout/stderr/Exitcode unverändert.
Ohne Original zeigt es eine knappe eigene Zeile. Der eigene Teil blockiert nie (Alarm ~1 s) und schreibt nie
auf stderr; ein Fehler dort verhindert nie die ursprüngliche Statusline.
"""

import json
import os
import signal
import subprocess
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROSSEL_S = 20
MARKER = "# limit-watchdog-statusline"


class _Zeit(Exception):
    pass


def _basis():
    return os.environ.get("LIMIT_WAECHTER_HOME") or os.path.expanduser("~/.limit-waechter")


def _fenster(f):
    if not isinstance(f, dict) or f.get("used_percentage") is None:
        return None
    return {"pct": float(f["used_percentage"]), "reset": f.get("resets_at")}


def mitschreiben(roh):
    """Füllstände aus dem Statusline-JSON sichern. -> Anzeige-Werte (fuenf, woche) für die eigene Zeile."""
    sys.path.insert(0, WURZEL)
    from lw import util
    daten = json.loads(roh.decode("utf-8") or "{}")
    rl = daten.get("rate_limits") if isinstance(daten, dict) else None
    if not isinstance(rl, dict):
        return None, None
    fuenf, woche = _fenster(rl.get("five_hour")), _fenster(rl.get("seven_day"))
    if not (fuenf or woche):
        return None, None
    datei = os.path.join(_basis(), "state", "statusline.json")
    jetzt = util.jetzt()
    alt = util.lies_json(datei, {}) or {}
    if not (alt.get("fuenf") == fuenf and alt.get("woche") == woche
            and isinstance(alt.get("stand"), (int, float)) and 0 <= jetzt - alt["stand"] < DROSSEL_S):
        util.schreib_json(datei, {"version": 1, "stand": jetzt, "fuenf": fuenf, "woche": woche})
    return fuenf, woche


def original_befehl():
    try:
        with open(os.path.join(_basis(), "state", "statusline-original.json"), encoding="utf-8") as f:
            eintrag = (json.load(f) or {}).get("statusLine")
    except (OSError, ValueError, AttributeError):
        return None
    befehl = eintrag.get("command") if isinstance(eintrag, dict) else None
    if not isinstance(befehl, str) or not befehl.strip() or MARKER in befehl:
        return None                                   # nie sich selbst aufrufen
    return befehl


def eigene_zeile(fuenf, woche):
    sys.path.insert(0, WURZEL)
    from lw import sprache, util
    cur = util.lies_json(os.path.join(_basis(), "state", "current.json"), {}) or {}
    sprache.setzen(cur.get("sprache") or "en", cur.get("name") or "")

    def pct(f):
        return f"{f['pct']:.0f}%" if f else "–"
    return sprache.t("sl_anzeige", p5=pct(fuenf), pw=pct(woche))


def _alarm(*_):
    raise _Zeit()


def main():
    roh, fuenf, woche, befehl = b"", None, None, None
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, 1.0)
    try:
        try:
            roh = sys.stdin.buffer.read()
            befehl = original_befehl()
            fuenf, woche = mitschreiben(roh)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)   # auch ein Alarm genau hier landet im äußeren except
    except BaseException:                             # auch _Zeit: eigener Teil darf nie stören
        pass
    if befehl is None:
        befehl = original_befehl()
    if befehl:
        try:
            return subprocess.run(["/bin/sh", "-c", befehl], input=roh).returncode
        except OSError:
            return 0
    try:
        sys.stdout.write(eigene_zeile(fuenf, woche) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
