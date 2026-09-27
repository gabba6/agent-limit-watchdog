#!/usr/bin/python3
"""Statusline-Kette des Limit-Wächters (v1.3, eingetragen als statusLine in ~/.claude/settings.json).

Claude Code übergibt der Statusline per stdin JSON (rate_limits, context_window, model, session_id …). Dieses Skript
  1. schreibt die Füllstände nach <LIMIT_WAECHTER_HOME>/state/statusline.json (atomar, höchstens alle 20 s,
     außer die Werte ändern sich) – der Tick liest sie über quellen.claude_statusline();
  2. v1.4: schreibt den Kontextfüllstand der Sitzung (nur Zahlen, keine Inhalte) nach
     state/kontext/claude-<session_id>.json (lw/kontextfenster.py);
  3. führt danach die ursprüngliche Statusline (gesichert in state/statusline-original.json) mit /bin/sh -c aus:
     stdin = unveränderte Bytes (danach geschlossen), Umgebung unverändert, stderr und Exitcode unverändert; ihre
     Ausgabe wird unverändert und sofort weitergegeben;
  4. v1.4: hängt eine eigene kompakte Zeile an ([statusline] anzeigen, Standard an):
        Opus 5.5 · ctx ████░░░░░░ 41% 412k/1M · 5h 63% ↻14:20 · wk 38% · ☾
     ANSI-Farben nach den Schwellen, Abbau nach COLUMNS, fehlende Daten lassen ihr Segment weg.
Ohne Original und ohne eigene Zeile zeigt es die knappe Zeile von 1.3. Der eigene Teil blockiert nie (Alarm) und
schreibt nie auf stderr; ein Fehler dort verhindert nie die ursprüngliche Statusline (dann nur deren Ausgabe).
"""

import json
import os
import re
import signal
import subprocess
import sys
import time

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROSSEL_S = 20
MARKER = "# limit-watchdog-statusline"
ANSI = re.compile(r"\033\[[0-9;]*m")
R, D, B = "\033[0m", "\033[2m", "\033[1m"
FARBE = {"ok": "\033[32m", "warnung": "\033[33m", "kritisch": "\033[31m"}


class _Zeit(Exception):
    pass


def _basis():
    return os.environ.get("LIMIT_WAECHTER_HOME") or os.path.expanduser("~/.limit-waechter")


def _fenster(f):
    if not isinstance(f, dict) or f.get("used_percentage") is None:
        return None
    return {"pct": float(f["used_percentage"]), "reset": f.get("resets_at")}


def _current():
    sys.path.insert(0, WURZEL)
    from lw import util
    cur = util.lies_json(os.path.join(_basis(), "state", "current.json"), {})
    return cur if isinstance(cur, dict) else {}


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
        try:
            util.schreib_json(datei, {"version": 1, "stand": jetzt, "fuenf": fuenf, "woche": woche})
        except OSError:
            pass                                      # nicht schreibbar: trotzdem anzeigen
    return fuenf, woche


def kontext_mitschreiben(roh, cur):
    """v1.4 N4: Kontextfüllstand der Sitzung sichern. -> Eintrag für die eigene Zeile oder None.
    Liefert Claude noch keine Zahl (neue Sitzung, direkt nach /compact), gilt das Transcript (compact_boundary = 0);
    sonst bleibt der gespeicherte Stand unverändert."""
    sys.path.insert(0, WURZEL)
    from lw import kontextfenster, util
    daten = json.loads(roh.decode("utf-8") or "{}")
    if not isinstance(daten, dict) or not isinstance(daten.get("session_id"), str) or not daten["session_id"]:
        return None
    standard = ((cur.get("kontext") or {}).get("standard_fenster")) or kontextfenster.STANDARD_FENSTER
    now = util.jetzt()
    e = kontextfenster.aus_statusline(daten, now, standard)
    if e is None:
        e = kontextfenster.aus_transcript(daten.get("transcript_path"), standard)
        if e is None:
            return kontextfenster.lesen("claude", daten["session_id"])
        e["stand"] = now
    try:
        return kontextfenster.speichern("claude", daten["session_id"], e, now)
    except OSError:
        return e


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
    """Knappe Zeile von 1.3 (ohne Original und ohne eigene v1.4-Zeile)."""
    sys.path.insert(0, WURZEL)
    from lw import sprache
    cur = _current()
    sprache.setzen(cur.get("sprache") or "en", cur.get("name") or "")

    def pct(f):
        return f"{f['pct']:.0f}%" if f else "–"
    return sprache.t("sl_anzeige", p5=pct(fuenf), pw=pct(woche))


def sichtbar(text):
    return len(ANSI.sub("", text))


def _stufe(pct, warn, stopp):
    return "kritisch" if pct >= stopp else "warnung" if pct >= warn else "ok"


def schoene_zeile(daten, kx, fuenf, woche, cur, spalten, nacht_an=False, now=None):
    """v1.4 N5: Modell · Kontextbalken · 5h + Reset · Woche · ☾ – oder None, wenn es nichts zu zeigen gibt."""
    sys.path.insert(0, WURZEL)
    from lw import kontextfenster, sprache
    sprache.setzen(cur.get("sprache") or "en", cur.get("name") or "")
    now = now or time.time()
    sw = cur.get("schwellen") or {}
    ks = cur.get("kontext") or {}
    modell = None
    if isinstance(daten, dict) and isinstance(daten.get("model"), dict):
        modell = kontextfenster.modell_name(daten["model"].get("id"), daten["model"].get("display_name"))
    modell = modell or (kx or {}).get("modell")

    def fenster_aktiv(f):
        return f if f and (not f.get("reset") or f["reset"] > now) else None
    fuenf, woche = fenster_aktiv(fuenf), fenster_aktiv(woche)
    tr = f"{D} · {R}"
    teile_kurz = []
    ctx_teil = ctx_kurz = None
    if kx:
        p = float(kx["prozent"])
        c = FARBE[kontextfenster.stufe(p, ks.get("warnung", 70), ks.get("kritisch", 85))]
        breite = 10 if spalten >= 80 else 5
        n = max(0, min(breite, int(round(p / 100.0 * breite))))
        balken = f"{c}{'█' * n}{D}{'░' * (breite - n)}{R}"
        tok = f" {D}{kontextfenster.tokens_text(kx['tokens'])}/{kontextfenster.tokens_text(kx['fenster'])}{R}" \
            if spalten >= 100 else ""
        ctx_teil = f"{sprache.t('sl_kontext')} {balken} {c}{p:.0f}%{R}{tok}"
        ctx_kurz = f"{sprache.t('sl_kontext')} {c}{p:.0f}%{R}"
    f_teil = f_kurz = w_teil = None
    if fuenf:
        c5 = FARBE[_stufe(fuenf["pct"], sw.get("warnung", 80), sw.get("stopp", 92))]
        f_kurz = f"5h {c5}{fuenf['pct']:.0f}%{R}"
        uhr = f" {D}↻{time.strftime('%H:%M', time.localtime(fuenf['reset']))}{R}" \
            if fuenf.get("reset") and spalten >= 60 else ""
        f_teil = f_kurz + uhr
    if woche and spalten >= 60:
        cw = FARBE[_stufe(woche["pct"], sw.get("woche_warnung", 80), sw.get("woche_stopp", 92))]
        w_teil = f"{sprache.t('sl_woche')} {cw}{woche['pct']:.0f}%{R}"
    if spalten < 40:
        teile_kurz = [x for x in (ctx_kurz, f_kurz) if x]
        return tr.join(teile_kurz) or None
    teile = [x for x in (f"{B}{modell}{R}" if modell else None, ctx_teil, f_teil, w_teil) if x]
    if not [x for x in (ctx_teil, f_teil, w_teil) if x]:
        return None
    zeile = tr.join(teile) + (" ☾" if nacht_an else "")
    if sichtbar(zeile) > spalten and modell:           # zu breit: Modell zuerst weglassen
        zeile = tr.join(teile[1:]) + (" ☾" if nacht_an else "")
    return zeile


def _nacht_an(daten, now):
    sys.path.insert(0, WURZEL)
    from lw import nacht, register
    sid = daten.get("session_id") if isinstance(daten, dict) else None
    try:
        s = register.lesen("claude", sid) if isinstance(sid, str) and sid else None
        return nacht.aktiv(s or {}, now)
    except OSError:
        return False


def _spalten():
    try:
        return max(20, int(os.environ.get("COLUMNS") or 0)) if os.environ.get("COLUMNS") else 200
    except ValueError:
        return 200


def _alarm(*_):
    raise _Zeit()


def _geschuetzt(f, sekunden, *args):
    """f(*args) mit Zeitlimit; jede Ausnahme (auch _Zeit) -> None."""
    ergebnis = None
    signal.signal(signal.SIGALRM, _alarm)
    try:
        signal.setitimer(signal.ITIMER_REAL, sekunden)
        try:
            ergebnis = f(*args)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)   # auch ein Alarm genau hier landet im äußeren except
    except BaseException:                             # auch _Zeit: eigener Teil darf nie stören
        return None
    return ergebnis


def main():
    roh = _geschuetzt(sys.stdin.buffer.read, 1.0) or b""
    befehl = original_befehl()
    cur = _geschuetzt(_current, 0.3) or {}
    fuenf, woche = _geschuetzt(mitschreiben, 0.5, roh) or (None, None)
    kx = _geschuetzt(kontext_mitschreiben, 0.4, roh, cur)
    code = 0
    ausgabe = sys.stdout.buffer
    if befehl:
        try:
            r = subprocess.run(["/bin/sh", "-c", befehl], input=roh, stdout=subprocess.PIPE)
            code, text = r.returncode, r.stdout
        except OSError:
            text = b""
        try:
            ausgabe.write(text)
            ausgabe.flush()                           # sofort: ein neues Update bricht diesen Aufruf ab
        except (OSError, ValueError):
            return code
    else:
        text = b""
    zeile = None
    if cur.get("statusline_anzeigen", True):
        def bauen():
            daten = json.loads(roh.decode("utf-8") or "{}")
            now = time.time() if not os.environ.get("LIMIT_WAECHTER_NOW") else float(os.environ["LIMIT_WAECHTER_NOW"])
            return schoene_zeile(daten, kx, fuenf, woche, cur, _spalten(), _nacht_an(daten, now), now)
        zeile = _geschuetzt(bauen, 0.3)
    if zeile is None and not befehl:
        zeile = _geschuetzt(eigene_zeile, 0.3, fuenf, woche)
    if zeile:
        try:
            if text and not text.endswith(b"\n"):
                ausgabe.write(b"\n")
            ausgabe.write(zeile.encode("utf-8") + b"\n")
            ausgabe.flush()
        except (OSError, ValueError):
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
