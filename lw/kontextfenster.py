"""Kontextfüllstand je Sitzung (v1.4): Tokens im Kontext / Kontextfenster des Modells. Nur lesend, ohne Inhalte.

Quellen (in dieser Reihenfolge):
  statusline  hooks/statusline.py bekommt je Claude-Sitzung `context_window` (current_usage, used_percentage,
              context_window_size) und speichert Zahlen in state/kontext/claude-<id>.json
  transcript  Ersatz für Claude: letzter assistant-Eintrag ohne Sidechain/API-Fehler
              (usage input + cache_creation + cache_read; ein system/compact_boundary davor = 0)
  rollout     Codex: letztes event_msg token_count mit info (last_token_usage.total_tokens,
              model_context_window), Modell aus turn_context

Prozent immer roh (ohne Auto-Compact-Puffer), passend zu Claudes /context. Die Stufe (ok/warnung/kritisch) kommt
aus [kontext] warnung/kritisch.
"""

import json
import os
import re

from . import util

STANDARD_FENSTER = 200_000
EINE_MIO = 1_000_000
SCHWANZ_BYTES = 262_144
KOPF_BYTES = 262_144
VERLAUF_MAX = 20
STUFEN = ("ok", "warnung", "kritisch")
DROSSEL_S = 20
EINS_M = re.compile(r"\[1m\]|\(1m\)|[-_ ]1m\b", re.IGNORECASE)


def _zahl(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else None


def fenster_aus_modell(modell_id, standard=STANDARD_FENSTER):
    """Kontextfenster aus der Modellkennung: [1m]/(1M)/-1m -> 1 000 000, sonst `standard`."""
    return EINE_MIO if EINS_M.search(str(modell_id or "")) else int(standard or STANDARD_FENSTER)


def modell_name(modell_id=None, anzeige=None):
    """Kurzer Anzeigename: display_name mit Version, sonst aus der ID ("claude-opus-5-5[1m]" -> "Opus 5.5")."""
    if isinstance(anzeige, str) and re.search(r"\d", anzeige):
        kurz = re.sub(r"\s*\([^)]*\)\s*$", "", anzeige.strip())     # "Opus 5.5 (1M context)" -> "Opus 5.5"
        return (kurz or anzeige.strip())[:40]
    mid = EINS_M.sub("", str(modell_id or "")).strip()
    m = re.match(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?!\d)", mid, re.IGNORECASE)
    if m:
        return f"{m.group(1).capitalize()} {m.group(2)}" + (f".{m.group(3)}" if m.group(3) else "")
    wert = (anzeige if isinstance(anzeige, str) and anzeige.strip() else mid) or ""
    return wert.strip()[:40] or None


def stufe(prozent, warnung=70, kritisch=85):
    if prozent is None:
        return None
    return "kritisch" if prozent >= kritisch else "warnung" if prozent >= warnung else "ok"


def _eintrag(tokens, fenster, modell, quelle, stand, prozent=None):
    if prozent is None:
        prozent = tokens / fenster * 100 if fenster else 0.0
    return {"prozent": round(max(0.0, prozent), 1), "tokens": int(round(max(0.0, tokens))), "fenster": int(fenster),
            "modell": modell, "quelle": quelle, "stand": stand}


# ---------------------------------------------------------------- Parser

def aus_statusline(daten, now, standard=STANDARD_FENSTER):
    """Eingabe der Claude-Statusline -> Eintrag oder None (keine Zahl: vorhandenen Stand nicht überschreiben)."""
    if not isinstance(daten, dict):
        return None
    cw = daten.get("context_window") if isinstance(daten.get("context_window"), dict) else {}
    modell = daten.get("model") if isinstance(daten.get("model"), dict) else {}
    mid = modell.get("id")
    fenster = _zahl(cw.get("context_window_size"))
    if not fenster or fenster <= 0:
        fenster = fenster_aus_modell(mid, standard)
    tokens = None
    cu = cw.get("current_usage")
    if isinstance(cu, dict):
        teile = [_zahl(cu.get(n)) for n in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")]
        if any(x is not None for x in teile):
            tokens = sum(x or 0.0 for x in teile)
    prozent = _zahl(cw.get("used_percentage"))
    if tokens is None and prozent is None:
        return None
    if tokens is None:
        tokens = prozent / 100.0 * fenster
    return _eintrag(tokens, fenster, modell_name(mid, modell.get("display_name")), "statusline", now)


def _kopf(pfad, max_bytes=KOPF_BYTES):
    """Die ersten Zeilen einer JSONL-Datei (letzte, evtl. abgeschnittene Zeile verworfen)."""
    try:
        with open(pfad, "rb") as f:
            daten = f.read(max_bytes)
    except OSError:
        return []
    zeilen = daten.decode("utf-8", "replace").splitlines()
    return zeilen[:-1] if len(daten) >= max_bytes and zeilen else zeilen


def _modell_anhang(zeilen):
    """Letzte Modellangabe des Transcripts (attachment type=model, identity.modelId, z. B. "claude-opus-5-5[1m]").
    Die assistant-Einträge nennen nur "claude-opus-5-5" ohne Fensterkennung."""
    for zeile in reversed(zeilen):
        if '"type":"model"' not in zeile.replace(" ", ""):
            continue
        try:
            e = json.loads(zeile)
        except ValueError:
            continue
        a = e.get("attachment") if isinstance(e, dict) and isinstance(e.get("attachment"), dict) else {}
        ident = a.get("identity") if isinstance(a.get("identity"), dict) else {}
        if a.get("type") == "model" and isinstance(ident.get("modelId"), str):
            return ident["modelId"]
    return None


def aus_transcript(pfad, standard=STANDARD_FENSTER, fenster_hinweis=None):
    """Claude-Transcript (nur das Ende) -> Eintrag oder None."""
    if not pfad or not os.path.isfile(pfad):
        return None
    from . import quellen            # spät: die Statusline braucht quellen nur in diesem Ersatzfall
    kompakt_ts = None
    schwanz = quellen.lies_schwanz(pfad, SCHWANZ_BYTES)
    if not fenster_hinweis:          # [1m] steht nur in der Modellangabe (Anhang), nicht in message.model
        anhang = _modell_anhang(schwanz) or _modell_anhang(_kopf(pfad))
        if anhang and fenster_aus_modell(anhang, standard) == EINE_MIO:
            fenster_hinweis = EINE_MIO
    for zeile in reversed(schwanz):
        try:
            e = json.loads(zeile)
        except ValueError:
            continue
        if not isinstance(e, dict) or e.get("isSidechain"):
            continue
        if e.get("type") == "system" and e.get("subtype") == "compact_boundary" and kompakt_ts is None:
            kompakt_ts = quellen.iso_zu_epoch(e.get("timestamp")) or os.path.getmtime(pfad)
            continue
        if e.get("type") != "assistant" or e.get("isApiErrorMessage"):
            continue
        msg = e.get("message") if isinstance(e.get("message"), dict) else {}
        u = msg.get("usage") if isinstance(msg.get("usage"), dict) else None
        mid = msg.get("model")
        if not u or _zahl(u.get("input_tokens")) is None or mid == "<synthetic>":
            continue
        fenster = fenster_hinweis or fenster_aus_modell(mid, standard)
        if kompakt_ts is not None:           # nach /compact: noch keine neue Antwort -> 0
            return _eintrag(0, fenster, modell_name(mid), "transcript", kompakt_ts)
        tokens = sum(_zahl(u.get(n)) or 0.0 for n in ("input_tokens", "cache_creation_input_tokens",
                                                        "cache_read_input_tokens"))
        if tokens > fenster:                 # mehr als das Standardfenster: muss ein 1M-Fenster sein
            fenster = max(fenster, EINE_MIO)
        stand = quellen.iso_zu_epoch(e.get("timestamp")) or os.path.getmtime(pfad)
        return _eintrag(tokens, fenster, modell_name(mid), "transcript", stand)
    if kompakt_ts is not None:
        return _eintrag(0, fenster_hinweis or standard, None, "transcript", kompakt_ts)
    return None


def aus_rollout(pfad):
    """Codex-rollout (nur das Ende) -> Eintrag oder None. Tokens = last_token_usage.total_tokens (wie Codex)."""
    if not pfad or not os.path.isfile(pfad):
        return None
    from . import quellen
    zaehler, modell = None, None
    zeilen = quellen.lies_schwanz(pfad, SCHWANZ_BYTES)
    for zeile in reversed(zeilen):
        try:
            e = json.loads(zeile)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if zaehler is None and e.get("type") == "event_msg" and p.get("type") == "token_count" \
                and isinstance(p.get("info"), dict):
            zaehler = (p["info"], e.get("timestamp"))
        elif modell is None and e.get("type") == "turn_context" and isinstance(p.get("model"), str):
            modell = p["model"]
        if zaehler and modell:
            break
    if not zaehler:
        return None
    if modell is None:               # langer Turn: turn_context steht nur weiter vorn
        for zeile in reversed(_kopf(pfad)):
            if '"turn_context"' not in zeile:
                continue
            try:
                e = json.loads(zeile)
            except ValueError:
                continue
            p = e.get("payload") if isinstance(e, dict) and isinstance(e.get("payload"), dict) else {}
            if e.get("type") == "turn_context" and isinstance(p.get("model"), str):
                modell = p["model"]
                break
    info, ts = zaehler
    last = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
    tokens, fenster = _zahl(last.get("total_tokens")), _zahl(info.get("model_context_window"))
    if tokens is None or not fenster or fenster <= 0:
        return None
    stand = quellen.iso_zu_epoch(ts) or os.path.getmtime(pfad)
    return _eintrag(tokens, fenster, modell_name(modell), "rollout", stand)


# ---------------------------------------------------------------- Speicher (state/kontext/<anbieter>-<id>.json)

def _datei(anbieter, sid):
    sicher = re.sub(r"[^A-Za-z0-9_.-]", "_", str(sid))[:120]
    return util.pfad("state", "kontext", f"{anbieter}-{sicher}.json")


def lesen(anbieter, sid):
    d = util.lies_json(_datei(anbieter, sid))
    return d if isinstance(d, dict) and _zahl(d.get("prozent")) is not None else None


def speichern(anbieter, sid, eintrag, now):
    """Eintrag atomar sichern (höchstens alle 20 s, außer die Zahlen ändern sich). Kurzer Verlauf für die App,
    ein Absturz um mehr als 10 Punkte gilt als Kompaktierung. -> gespeicherter Stand."""
    alt = lesen(anbieter, sid) or {}
    gleich = all(alt.get(n) == eintrag.get(n) for n in ("prozent", "tokens", "fenster", "modell"))
    if gleich and _zahl(alt.get("stand")) is not None and 0 <= now - alt["stand"] < DROSSEL_S:
        return alt
    verlauf = [p for p in (alt.get("verlauf") or []) if isinstance(p, list) and len(p) == 2]
    if not verlauf or verlauf[-1][1] != eintrag["prozent"] or now - verlauf[-1][0] >= 60:
        verlauf.append([round(now), eintrag["prozent"]])
    neu = dict(eintrag, version=1, anbieter=anbieter, id=str(sid), stand=now, verlauf=verlauf[-VERLAUF_MAX:],
               kompaktiert=alt.get("kompaktiert"))
    if _zahl(alt.get("prozent")) is not None and alt["prozent"] - eintrag["prozent"] >= 10:
        neu["kompaktiert"] = now
    util.schreib_json(_datei(anbieter, sid), neu)
    return neu


# ---------------------------------------------------------------- je Sitzung (status --json, Tick, Hook)

def schwellen(k):
    kx = (k or {}).get("kontext") or {}
    return {"warnung": kx.get("warnung", 70), "kritisch": kx.get("kritisch", 85)}


def ermitteln(x, k, rollout_index=None):
    """Kontextstand einer Registerzeile -> Vertragsform für status --json oder None.

    Claude: gespeicherter Statusline-Stand; ist das Transcript deutlich neuer (> 5 min), das Transcript.
    Codex: rollout-Datei des Threads (Index id -> Pfad, sonst Suche in den Sitzungsordnern)."""
    anb, sid = x.get("anbieter"), x.get("id")
    if not sid:
        return None
    kx = (k or {}).get("kontext") or {}
    standard = kx.get("standard_fenster", STANDARD_FENSTER)
    e = None
    if anb == "claude":
        gespeichert = lesen("claude", sid)
        tr = x.get("transcript")
        try:
            tr_zeit = os.path.getmtime(tr) if tr else None
        except OSError:
            tr_zeit = None
        if gespeichert and (tr_zeit is None or tr_zeit <= (gespeichert.get("stand") or 0) + 300):
            e = gespeichert
        else:
            e = aus_transcript(tr, standard, (gespeichert or {}).get("fenster")) or gespeichert
    elif anb == "codex":
        pfad = (rollout_index or {}).get(sid)
        if pfad is None and rollout_index is None:
            from . import codex, quellen
            pfad = codex.id_index(quellen.rollout_dateien(k["daten"]["codex_sessions"], util.jetzt())).get(sid)
        e = aus_rollout(pfad)
    if not e:
        return None
    s = schwellen(k)
    return {"prozent": e["prozent"], "tokens": e["tokens"], "fenster": e["fenster"], "modell": e.get("modell"),
            "stufe": stufe(e["prozent"], s["warnung"], s["kritisch"]), "stand": e.get("stand"),
            "quelle": e.get("quelle")}


def tokens_text(n):
    """412k, 1M, 1.2M (wie in der Terminal-Zeile und in der App)."""
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if n >= 1000:
        return f"{round(n / 1000)}k"
    return str(n)
