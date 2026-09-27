"""Datenquellen: Orca-Limits, Codex-rollout-Dateien, Claude-Transcripts, Mac-Energiezustand.

Alle Parser lesen tolerant: fehlende oder geänderte Felder ergeben None statt Absturz.
"""

import calendar
import glob
import json
import os
import re
import subprocess
import time

FUENF_H_MINUTEN_MAX = 24 * 60   # Fenster bis 1 Tag gelten als "5h"-Fenster, darüber als Woche


# ---------------------------------------------------------------- Orca account list

def _fenster_orca(f):
    if not isinstance(f, dict) or f.get("usedPercent") is None:
        return None
    reset = f.get("resetsAt")
    return {
        "pct": float(f["usedPercent"]),
        "reset": reset / 1000.0 if reset else None,
        "minuten": f.get("windowMinutes"),
    }


def orca_limits(result):
    """result = .result von `orca account list --json` -> {'claude': {...}, 'codex': {...}}."""
    rl = (result or {}).get("rateLimits") or {}
    daten = {}
    for anbieter in ("claude", "codex"):
        r = rl.get(anbieter) or {}
        eintrag = {
            "fuenf": _fenster_orca(r.get("session")),
            "woche": _fenster_orca(r.get("weekly")),
            "stand": (r.get("updatedAt") or 0) / 1000.0 or None,
            "fehler": r.get("error"),
            "status": r.get("status"),
            "quelle": "orca",
        }
        if anbieter == "codex":
            rc = r.get("rateLimitResetCredits") or {}
            eintrag["reset_credits"] = rc.get("availableCount")
        daten[anbieter] = eintrag
    return daten


# ---------------------------------------------------------------- Claude-Statusline-Kette (v1.3)

STATUSLINE_DATEI = ("state", "statusline.json")          # relativ zu util.basis(); geschrieben von hooks/statusline.py


def _fenster_sl(f, minuten):
    if not isinstance(f, dict) or f.get("pct") is None:
        return None
    try:
        return {"pct": float(f["pct"]), "reset": float(f["reset"]) if f.get("reset") else None, "minuten": minuten}
    except (TypeError, ValueError):
        return None


def claude_statusline(datei):
    """state/statusline.json -> {'fuenf', 'woche', 'stand', 'quelle': 'statusline'} (Form wie orca_limits) oder None.

    Dateiformat (Vertrag v1.3): {"version": 1, "stand": <epoch, Zeitpunkt des Schreibens>,
    "fuenf": {"pct": <0..100>, "reset": <epoch>}, "woche": {"pct": …, "reset": …}}; fehlende Fenster = null."""
    try:
        with open(datei, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    eintrag = {"fuenf": _fenster_sl(d.get("fuenf"), 300), "woche": _fenster_sl(d.get("woche"), 10080),
               "stand": d.get("stand") if isinstance(d.get("stand"), (int, float)) else None,
               "fehler": None, "status": None, "quelle": "statusline"}
    if not (eintrag["fuenf"] or eintrag["woche"]):
        return None
    return eintrag


# ---------------------------------------------------------------- Codex rollouts

def iso_zu_epoch(text):
    if not text:
        return None
    try:
        basis = calendar.timegm(time.strptime(text[:19], "%Y-%m-%dT%H:%M:%S"))
        m = re.match(r"\.(\d+)", text[19:])
        return basis + (float("0." + m.group(1)) if m else 0.0)
    except (ValueError, TypeError):
        return None


def rollout_dateien(sessions_dir, now, tage=8):
    """rollout-*.jsonl der letzten `tage` Tage, neueste (mtime) zuerst."""
    gefunden = set()
    for i in range(tage + 1):
        t = time.localtime(now - i * 86400)
        muster = os.path.join(sessions_dir, time.strftime("%Y/%m/%d", t), "rollout-*.jsonl")
        gefunden.update(glob.glob(muster))
    mit_zeit = []
    for p in gefunden:
        try:
            mit_zeit.append((os.path.getmtime(p), p))
        except OSError:
            continue
    return [p for _, p in sorted(mit_zeit, reverse=True)]


def lies_schwanz(datei, max_bytes=262144):
    try:
        with open(datei, "rb") as f:
            f.seek(0, os.SEEK_END)
            groesse = f.tell()
            start = max(0, groesse - max_bytes)
            f.seek(start)
            daten = f.read()
    except OSError:
        return []
    zeilen = daten.decode("utf-8", "replace").splitlines()
    if start > 0 and zeilen:
        zeilen = zeilen[1:]   # erste Zeile ist abgeschnitten
    return zeilen


def lies_kopf(datei):
    try:
        with open(datei, encoding="utf-8", errors="replace") as f:
            return json.loads(f.readline())
    except (OSError, ValueError):
        return None


def _fenster_codex(f):
    if not isinstance(f, dict) or f.get("used_percent") is None:
        return None
    return {"pct": float(f["used_percent"]), "reset": f.get("resets_at"), "minuten": f.get("window_minutes")}


def codex_snapshot(obj):
    """Ein token_count-Ereignis -> Nutzung, oder None wenn es kein Codex-Kontingent beschreibt."""
    pl = obj.get("payload") or {}
    rl = pl.get("rate_limits")
    if not isinstance(rl, dict):
        return None
    if rl.get("limit_id") not in (None, "codex"):
        return None
    fenster = [_fenster_codex(rl.get("primary")), _fenster_codex(rl.get("secondary"))]
    fenster = [f for f in fenster if f]
    if not fenster:
        return None
    snap = {"fuenf": None, "woche": None, "stand": iso_zu_epoch(obj.get("timestamp")), "quelle": "rollout"}
    for f in fenster:
        art = "fuenf" if (f.get("minuten") or 300) <= FUENF_H_MINUTEN_MAX else "woche"
        snap[art] = f
    credits = rl.get("credits") or {}
    try:
        snap["credits"] = float(credits["balance"]) if credits.get("balance") is not None else None
    except (TypeError, ValueError):
        snap["credits"] = None
    snap["plan"] = rl.get("plan_type")
    snap["erreicht"] = rl.get("rate_limit_reached_type")
    return snap


def codex_nutzung(dateien, max_dateien=6):
    """Neuester Codex-Nutzungsstand aus den zuletzt geänderten rollout-Dateien."""
    bester = None
    for datei in dateien[:max_dateien]:
        for zeile in reversed(lies_schwanz(datei)):
            if '"rate_limits"' not in zeile:
                continue
            try:
                snap = codex_snapshot(json.loads(zeile))
            except ValueError:
                continue
            if snap:
                if bester is None or (snap["stand"] or 0) > (bester["stand"] or 0):
                    bester = snap
                break
    return bester


MONATE = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                      "sep", "oct", "nov", "dec"], 1)}


def zeit_aus_text(text, bezug):
    """'7:10 PM', 'Sep 28th, 2026 3:00 PM', '6:30pm', 'Sun 3am' -> nächster passender Zeitpunkt nach bezug."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\b", text, re.I)
    if m:
        h, mi = int(m.group(1)) % 12, int(m.group(2) or 0)
        if m.group(3).lower() == "p":
            h += 12
    else:
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
        if not m:
            return None
        h, mi = int(m.group(1)), int(m.group(2))
    b = time.localtime(bezug)
    md = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?",
                   text, re.I)
    if md:
        jahr = int(md.group(3) or b.tm_year)
        ts = time.mktime((jahr, MONATE[md.group(1).lower()], int(md.group(2)), h, mi, 0, 0, 0, -1))
        if ts < bezug - 86400 and not md.group(3):
            ts = time.mktime((jahr + 1, MONATE[md.group(1).lower()], int(md.group(2)), h, mi, 0, 0, 0, -1))
        return ts
    tage = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    mw = re.search(r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b", text, re.I)
    for plus in range(0, 8):
        ts = time.mktime((b.tm_year, b.tm_mon, b.tm_mday + plus, h, mi, 0, 0, 0, -1))
        if ts <= bezug - 60:
            continue
        if mw and time.localtime(ts).tm_wday != tage.index(mw.group(1).lower()[:3]):
            continue
        return ts
    return None


def codex_thread(datei):
    """Zustand eines Codex-Threads aus seiner rollout-Datei."""
    kopf = lies_kopf(datei) or {}
    meta = kopf.get("payload") if kopf.get("type") == "session_meta" else {}
    meta = meta or {}
    info = {
        "id": meta.get("id") or meta.get("session_id"),
        "cwd": meta.get("cwd"),
        "originator": meta.get("originator"),
        "source": meta.get("source") if isinstance(meta.get("source"), str) else "subagent",
        "datei": datei,
        "laeuft": False,
        "limit": None,
        "letzte_aktivitaet": None,
    }
    if not info["id"]:
        m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$", datei)
        info["id"] = m.group(1) if m else None
    letzter_start = letztes_ende = None
    ende_obj = None
    snap = None
    for zeile in lies_schwanz(datei):
        if '"task_started"' not in zeile and '"task_complete"' not in zeile and '"rate_limits"' not in zeile:
            continue
        try:
            obj = json.loads(zeile)
        except ValueError:
            continue
        pl = obj.get("payload") or {}
        ts = iso_zu_epoch(obj.get("timestamp"))
        if pl.get("type") == "task_started":
            letzter_start = ts
        elif pl.get("type") == "task_complete":
            letztes_ende, ende_obj = ts, pl
        elif pl.get("type") == "token_count":
            snap = codex_snapshot(obj) or snap
    zeiten = [t for t in (letzter_start, letztes_ende) if t]
    info["letzte_aktivitaet"] = max(zeiten) if zeiten else None
    info["laeuft"] = bool(letzter_start and (not letztes_ende or letzter_start > letztes_ende))
    fehler = (ende_obj or {}).get("error") or {}
    if not info["laeuft"] and fehler.get("codex_error_info") == "usage_limit_exceeded":
        meldung = fehler.get("message") or ""
        info["limit"] = {"ts": letztes_ende, "reset": codex_reset(meldung, snap, letztes_ende or 0),
                         "art": _codex_art(snap)}
    return info


def _codex_art(snap):
    if snap and snap.get("woche") and snap["woche"]["pct"] >= 99 and not (snap.get("fuenf") and snap["fuenf"]["pct"] >= 99):
        return "woche"
    return "fuenf"


def codex_reset(meldung, snap, bezug):
    """Reset-Zeit einer Codex-Limitmeldung ('... try again at 7:10 PM.')."""
    m = re.search(r"try again at (.+?)\.?\s*$", meldung or "", re.I | re.S)
    aus_text = zeit_aus_text(m.group(1), bezug) if m else None
    kandidaten = []
    for art in ("fuenf", "woche"):
        f = (snap or {}).get(art)
        if f and f.get("reset") and f["reset"] > bezug:
            kandidaten.append(f["reset"])
    if aus_text:
        for k in kandidaten:
            if abs(k - aus_text) <= 90:
                return k
        return aus_text
    if kandidaten:
        voll = [(snap[a]["reset"]) for a in ("fuenf", "woche")
                if (snap or {}).get(a) and snap[a]["pct"] >= 95 and snap[a].get("reset")]
        return max(voll) if voll else min(kandidaten)
    return None


def orca_pane_sitzungen(datei):
    """Orcas Hook-Status: paneKey -> {'anbieter', 'id', 'transcript'} (nur diese Felder werden gelesen)."""
    try:
        with open(datei, encoding="utf-8") as f:
            daten = json.load(f)
    except (OSError, ValueError):
        return {}
    eintraege = daten.get("entries") or {}
    werte = eintraege.values() if isinstance(eintraege, dict) else eintraege
    ergebnis = {}
    for e in werte:
        if not isinstance(e, dict):
            continue
        ps = e.get("providerSession") or {}
        pane = e.get("paneKey")
        if pane and ps.get("id"):
            ergebnis[pane] = {"anbieter": e.get("source"), "id": ps.get("id"),
                              "transcript": ps.get("transcriptPath")}
    return ergebnis


# ---------------------------------------------------------------- Claude-Transcript

PLANLIMIT_TEXT = re.compile(r"hit your .{0,20}limit|usage limit|session limit|weekly limit", re.I)


def claude_limit_aus_transcript(datei, max_bytes=1_048_576):
    """Letzter Limit-Eintrag der Hauptsitzung (quotaLimits) aus dem Transcript."""
    if not datei:
        return None
    for zeile in reversed(lies_schwanz(datei, max_bytes)):
        if '"isApiErrorMessage"' not in zeile:
            continue
        try:
            obj = json.loads(zeile)
        except ValueError:
            continue
        if not obj.get("isApiErrorMessage") or obj.get("isSidechain"):
            continue
        text = ""
        inhalt = (obj.get("message") or {}).get("content")
        if isinstance(inhalt, list):
            text = " ".join(t.get("text", "") for t in inhalt if isinstance(t, dict))
        elif isinstance(inhalt, str):
            text = inhalt
        q = obj.get("quotaLimits") or {}
        return {
            "reset": q.get("resetsAt"),
            "art": q.get("rateLimitType"),
            "status": q.get("status"),
            "ueberziehung": bool(q.get("isUsingOverage")),
            "text": text[:300],
            "fehler": obj.get("error"),
            "ts": iso_zu_epoch(obj.get("timestamp")),
        }
    return None


def claude_reset_aus_text(text, bezug):
    """'You've hit your session limit · resets 6:30pm (Europe/Berlin)' -> Epoch."""
    m = re.search(r"resets?\s+(?:at\s+)?(.+?)(?:\(|$)", text or "", re.I)
    return zeit_aus_text(m.group(1), bezug) if m else None


def art_kurz(art):
    """quotaLimits.rateLimitType / Fensterangabe -> 'fuenf' | 'woche'."""
    art = (art or "").lower()
    return "woche" if ("seven" in art or "week" in art or art == "woche") else "fuenf"


# ---------------------------------------------------------------- Mac

def _befehl(args, timeout=10):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def mac_status():
    pm = _befehl(["/usr/bin/pmset", "-g"])
    batt = _befehl(["/usr/bin/pmset", "-g", "batt"])
    ass = _befehl(["/usr/bin/pmset", "-g", "assertions"])
    io = _befehl(["/usr/sbin/ioreg", "-r", "-k", "AppleClamshellState", "-d", "1"])
    m = re.search(r"SleepDisabled\s+(\d)", pm)
    schlaf_aus = bool(m and m.group(1) == "1")
    deckel = re.search(r'"AppleClamshellCausesSleep"\s*=\s*(Yes|No)', io)
    deckel_schlaeft = (deckel.group(1) == "Yes") if deckel else None
    m = re.search(r"(\d+)%", batt)
    return {
        "netzteil": "AC Power" in batt,
        "akku": int(m.group(1)) if m else None,
        "schlaf_aus": schlaf_aus,
        "deckel_schlaeft": deckel_schlaeft,
        "amphetamine": "Amphetamine" in ass,
        "wach_bei_deckel_zu": schlaf_aus or deckel_schlaeft is False,
    }


# ---------------------------------------------------------------- v1.4 A: Zeitangaben mit Zone

_ISO_ZONE = re.compile(r"^(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d:\d\d)(\.\d+)?\s*(Z|z|[+-]\d\d:?\d\d)?$")


def iso_zone_zu_epoch(text):
    """'2026-09-27T18:00:00.27+00:00' / '…Z' / '…+02:00' -> Epoch (float). Ohne Zone: UTC. Unlesbar -> None."""
    if not isinstance(text, str):
        return None
    m = _ISO_ZONE.match(text.strip())
    if not m:
        return None
    try:
        basis = calendar.timegm(time.strptime(m.group(1) + "T" + m.group(2), "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None
    wert = basis + (float("0" + m.group(3)) if m.group(3) else 0.0)
    zone = m.group(4)
    if zone and zone not in ("Z", "z"):
        vz = -1 if zone[0] == "-" else 1
        ziffern = zone[1:].replace(":", "")
        wert -= vz * (int(ziffern[:2]) * 3600 + int(ziffern[2:]) * 60)
    return wert
