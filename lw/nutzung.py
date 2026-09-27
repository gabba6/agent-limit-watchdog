"""v1.4: offizielle Nutzungsanzeige (dieselben Werte wie Claude Desktop/claude.ai bzw. ChatGPT/Codex).

Nur lesender HTTP-Abruf, kein Modellaufruf. Die Zugangs-Tokens werden bei jedem Abruf frisch gelesen
(Claude: macOS-Schlüsselbund, Codex: ~/.codex/auth.json), nur als lokale Variable gehalten und nie
geloggt, gespeichert oder erneuert. Bei Fehlern fällt der Wächter still auf Orca/Statusline/rollout zurück.

Zwischenspeicher state/offiziell.json (ohne Token):
  {"version": 1, "<anbieter>": {"stand": <epoch letzter Erfolg>|null, "versuch": epoch, "naechster": epoch,
    "fehler": null|"auth"|"rate"|"netz"|"format"|"kein_token"|"abgelaufen"|"url", "fehler_seit": epoch|null,
    "backoff_s": int, "daten": {"fuenf", "woche", "woche_modell", ...}|null}}
"""

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from . import VERSION, quellen, register, util
from .sprache import t

CACHE = ("state", "offiziell.json")
ANBIETER = ("claude", "codex")
NAME = {"claude": "Claude", "codex": "Codex"}
AUTH_PAUSE_S = 15 * 60
RATE_START_S = 300
RATE_MAX_S = 3600
ENG_VORLAUF_S = 15 * 60
# Der Token geht nur per https an genau diese Hosts (auch bei geänderter Konfiguration).
HOSTS = {"claude": "api.anthropic.com", "codex": "chatgpt.com"}
STANDARD_URL = {"claude": "https://api.anthropic.com/api/oauth/usage",
                "codex": "https://chatgpt.com/backend-api/wham/usage"}


def url_erlaubt(anbieter, url):
    """Nur https und nur der erwartete Host (keine Zugangsdaten/Port-Tricks in der Adresse)."""
    try:
        teile = urllib.parse.urlsplit(url or "")
        port = teile.port
    except ValueError:
        return False
    return teile.scheme == "https" and (teile.hostname or "").lower() == HOSTS[anbieter] \
        and port in (None, 443) and not teile.username and not teile.password


# ---------------------------------------------------------------- Konfiguration

def _d(k):
    return k.get("daten") or {}


def aktiv(k):
    """Offizielle Quelle eingeschaltet und nicht im Offline-Modus (Tests/CI)?"""
    return bool(_d(k).get("offiziell", True)) and not util.offline()


def _intervall_s(k, eng):
    d = _d(k)
    return int(d.get("offiziell_intervall_eng_minuten" if eng else "offiziell_intervall_minuten", 1 if eng else 3)) * 60


# ---------------------------------------------------------------- Tokens (nur lesen)

def claude_token(k, runner=None, now=None):
    """-> (token, None) | (None, "kein_token"|"abgelaufen"). Token nie loggen oder weitergeben."""
    runner = runner or subprocess.run
    now = util.jetzt() if now is None else now
    dienst = _d(k).get("claude_schluesselbund_dienst") or "Claude Code-credentials"
    try:
        r = runner(["/usr/bin/security", "find-generic-password", "-s", dienst, "-w"], capture_output=True,
                   text=True, timeout=5, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None, "kein_token"
    if getattr(r, "returncode", 1) != 0:
        return None, "kein_token"
    try:
        oauth = (json.loads(r.stdout or "") or {}).get("claudeAiOauth") or {}
    except (ValueError, AttributeError):
        return None, "kein_token"
    token = oauth.get("accessToken") if isinstance(oauth, dict) else None
    if not token or not isinstance(token, str):
        return None, "kein_token"
    ablauf = oauth.get("expiresAt")
    if isinstance(ablauf, (int, float)) and ablauf <= now * 1000:
        return None, "abgelaufen"
    return token, None


def codex_token(k):
    """-> (token, account_id) | (None, "kein_token")."""
    datei = os.path.expanduser(_d(k).get("codex_auth") or "~/.codex/auth.json")
    daten = util.lies_json(datei)
    tokens = (daten or {}).get("tokens") if isinstance(daten, dict) else None
    if not isinstance(tokens, dict):
        return None, "kein_token"
    token, konto = tokens.get("access_token"), tokens.get("account_id")
    if not token or not konto or not isinstance(token, str):
        return None, "kein_token"
    return token, str(konto)


# ---------------------------------------------------------------- Antworten lesen

def _zahl(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def _fenster_claude(f, minuten):
    if not isinstance(f, dict):
        return None
    pct = _zahl(f.get("utilization"))
    if pct is None:
        return None
    return {"pct": pct, "reset": quellen.iso_zone_zu_epoch(f.get("resets_at")), "minuten": minuten}


def parse_claude(obj):
    """Antwort von /api/oauth/usage -> {'fuenf', 'woche', 'woche_modell', 'quelle'} oder None."""
    if not isinstance(obj, dict):
        return None
    fuenf = _fenster_claude(obj.get("five_hour"), 300)
    woche = _fenster_claude(obj.get("seven_day"), 10080)
    limits = obj.get("limits") if isinstance(obj.get("limits"), list) else []
    modell = []
    for li in limits:
        if not isinstance(li, dict):
            continue
        art = li.get("kind")
        pct = _zahl(li.get("percent"))
        if pct is None:
            pct = _zahl(li.get("utilization"))
        reset = quellen.iso_zone_zu_epoch(li.get("resets_at") or li.get("reset_at"))
        if art == "weekly_scoped":
            name = (((li.get("scope") or {}).get("model") or {}).get("display_name")
                    if isinstance(li.get("scope"), dict) else None)
            if name and pct is not None:
                modell.append({"name": str(name), "pct": pct, "reset": reset})
        elif art == "session" and fuenf is None and pct is not None:      # Rückfall, falls five_hour fehlt
            fuenf = {"pct": pct, "reset": reset, "minuten": 300}
        elif art == "weekly_all" and woche is None and pct is not None:
            woche = {"pct": pct, "reset": reset, "minuten": 10080}
    if not (fuenf or woche):
        return None
    return {"fuenf": fuenf, "woche": woche, "woche_modell": modell, "quelle": "offiziell"}


def _fenster_codex(f):
    if not isinstance(f, dict):
        return None
    pct = _zahl(f.get("used_percent"))
    if pct is None:
        return None
    sek = _zahl(f.get("limit_window_seconds"))
    reset = _zahl(f.get("reset_at"))
    return {"pct": pct, "reset": reset, "minuten": int(sek / 60) if sek else None}


def parse_codex(obj):
    """Antwort von /backend-api/wham/usage -> {'fuenf', 'woche', 'erreicht', 'quelle'} oder None."""
    rl = (obj or {}).get("rate_limit") if isinstance(obj, dict) else None
    if not isinstance(rl, dict):
        return None
    eintrag = {"fuenf": None, "woche": None, "woche_modell": [], "erreicht": bool(rl.get("limit_reached")),
               "quelle": "offiziell"}
    for f in (_fenster_codex(rl.get("primary_window")), _fenster_codex(rl.get("secondary_window"))):
        if not f:
            continue
        art = "fuenf" if (f.get("minuten") or 300) <= quellen.FUENF_H_MINUTEN_MAX else "woche"
        eintrag[art] = f
    if not (eintrag["fuenf"] or eintrag["woche"]):
        return None
    return eintrag


# ---------------------------------------------------------------- Zwischenspeicher

def cache_lesen():
    d = util.lies_json(util.pfad(*CACHE), {}) or {}
    return d if isinstance(d, dict) else {}


def _cache_schreiben(anbieter, eintrag):
    datei = util.pfad(*CACHE)
    with util.sperre(datei):
        d = cache_lesen()
        d["version"] = 1
        d[anbieter] = eintrag
        util.schreib_json(datei, d)
        try:
            os.chmod(datei, 0o600)
        except OSError:
            pass


def faellig(k, eintrag_cache, eng, now):
    """Ist ein neuer Abruf dran? Nach auth/rate gilt der gespeicherte Zeitpunkt (Backoff), sonst das Intervall."""
    if not eintrag_cache or not eintrag_cache.get("versuch"):
        return True
    if eintrag_cache.get("fehler") in ("auth", "rate"):
        return now >= (eintrag_cache.get("naechster") or 0)
    # 5 s Spielraum: der Tick läuft jede Minute und nie auf die Sekunde gleich
    return now >= eintrag_cache["versuch"] + _intervall_s(k, eng) - 5


def eng_noetig(zustand, sitzungen, now):
    """Enger abrufen, solange es darauf ankommt: Warnung/Stopp/Limit, bald fällige oder ungeprüfte Fortsetzung."""
    for anb in ANBIETER:
        if ((zustand or {}).get(anb) or {}).get("phase") in ("warnung", "stopp", "limit"):
            return True
    for s in sitzungen or []:
        if s.get("status") in register.WARTET and (s.get("fortsetzen_ab") or now + ENG_VORLAUF_S + 1) \
                <= now + ENG_VORLAUF_S:
            return True
        if s.get("status") == "fortgesetzt" and s.get("geprueft") is False:
            return True
    return False


# ---------------------------------------------------------------- Abruf

class _KeineWeiterleitung(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nie folgen: urllib gäbe sonst den Authorization-Kopf an jedes Ziel weiter."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):   # noqa: D401
        return None


_OPENER = urllib.request.build_opener(_KeineWeiterleitung)


def _http(req, timeout):
    # 30x ergibt so einen HTTPError (-> "netz"), der Token verlässt nie den geprüften Host
    return _OPENER.open(req, timeout=timeout)


def _anfrage(k, anbieter, runner, now):
    """-> (urllib.request.Request, None) | (None, fehlercode). Der Token lebt nur im Request-Objekt."""
    d = _d(k)
    ua = f"agent-limit-watchdog/{VERSION}"
    if anbieter == "claude":
        url = d.get("claude_usage_url") or STANDARD_URL["claude"]
        if not url_erlaubt("claude", url):
            return None, "url"
        token, fehler = claude_token(k, runner, now)
        if not token:
            return None, fehler
        req = urllib.request.Request(url,
                                     headers={"Authorization": "Bearer " + token,
                                              "anthropic-beta": "oauth-2025-04-20",
                                              "Accept": "application/json", "User-Agent": ua})
    else:
        url = d.get("codex_usage_url") or STANDARD_URL["codex"]
        if not url_erlaubt("codex", url):
            return None, "url"
        token, konto = codex_token(k)
        if not token:
            return None, konto
        req = urllib.request.Request(url,
                                     headers={"Authorization": "Bearer " + token, "ChatGPT-Account-Id": konto,
                                              "Accept": "application/json", "User-Agent": ua})
    del token
    return req, None


def _retry_after(headers):
    try:
        wert = (headers or {}).get("Retry-After")
        return int(float(wert)) if wert is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def abrufen(k, anbieter, now, opener=None, runner=None):
    """Einen Anbieter abrufen und das Ergebnis (ohne Token) in den Zwischenspeicher schreiben.
    -> Fehlercode oder None. Kein Refresh, nichts wird in Schlüsselbund oder auth.json geschrieben."""
    opener = opener or _http
    alt = cache_lesen().get(anbieter) or {}
    timeout = int(_d(k).get("offiziell_timeout_sekunden", 8))
    normal = _intervall_s(k, False)
    fehler, daten, retry = None, None, None
    req, fehler = _anfrage(k, anbieter, runner, now)
    if req is not None:
        try:
            antwort = opener(req, timeout)
            try:
                roh = antwort.read()
            finally:
                close = getattr(antwort, "close", None)
                if close:
                    close()
            daten = (parse_claude if anbieter == "claude" else parse_codex)(json.loads(roh))
            if daten is None:
                fehler = "format"
        except urllib.error.HTTPError as e:
            code = e.code
            retry = _retry_after(getattr(e, "headers", None))
            try:
                e.close()
            except Exception:           # noqa: BLE001 – nur aufräumen
                pass
            fehler = "auth" if code in (401, 403) else "rate" if code == 429 else "netz"
        except ValueError:
            fehler = "format"
        except Exception:                # noqa: BLE001 – Netz, Timeout, SSL: nie den Tick abbrechen
            fehler = "netz"
        req = None                       # Request-Objekt mit Token sofort freigeben
    eintrag = {"stand": alt.get("stand"), "versuch": now, "fehler": fehler, "backoff_s": 0,
               "fehler_seit": None, "daten": alt.get("daten")}
    if fehler is None:
        eintrag.update(stand=now, daten=daten, naechster=now + normal)
    else:
        eintrag["fehler_seit"] = alt.get("fehler_seit") if alt.get("fehler") else now
        if fehler == "auth":
            eintrag["naechster"] = now + AUTH_PAUSE_S
        elif fehler == "rate":
            vorher = int(alt.get("backoff_s") or 0) if alt.get("fehler") == "rate" else 0
            backoff = min(RATE_MAX_S, vorher * 2 if vorher else RATE_START_S)
            if retry and retry > backoff:
                backoff = min(retry, 6 * 3600)
            eintrag["backoff_s"] = backoff
            eintrag["naechster"] = now + backoff
        else:
            eintrag["naechster"] = now + normal
    if fehler != alt.get("fehler"):
        if fehler:
            util.log(t("nz_log_fehler", n=NAME[anbieter], fehler=fehler))
        elif alt.get("fehler"):
            util.log(t("nz_log_ok", n=NAME[anbieter]))
    _cache_schreiben(anbieter, eintrag)
    return fehler


def lesen(k, now):
    """Zwischenspeicher -> {'claude': eintrag|None, 'codex': eintrag|None} in der Form der anderen Quellen."""
    cache = cache_lesen()
    ergebnis = {}
    for anb in ANBIETER:
        c = cache.get(anb) or {}
        daten = c.get("daten")
        if not isinstance(daten, dict) or not c.get("stand") or not (daten.get("fuenf") or daten.get("woche")):
            ergebnis[anb] = None
            continue
        ergebnis[anb] = dict(daten, stand=c["stand"], quelle="offiziell", fehler=None, status=None)
    return ergebnis


def info(k, now):
    """Für status --json: je Anbieter {'zustand': 'ok'|'aus'|'fehler', 'fehler': code|None, 'stand': epoch|None}."""
    cache = cache_lesen()
    ergebnis = {}
    for anb in ANBIETER:
        c = cache.get(anb) or {}
        if not _d(k).get("offiziell", True):
            ergebnis[anb] = {"zustand": "aus", "fehler": None, "stand": c.get("stand")}
        elif c.get("fehler"):
            ergebnis[anb] = {"zustand": "fehler", "fehler": c["fehler"], "stand": c.get("stand")}
        elif c.get("stand"):
            ergebnis[anb] = {"zustand": "ok", "fehler": None, "stand": c["stand"]}
        else:
            ergebnis[anb] = {"zustand": "fehler", "fehler": "noch_nicht", "stand": None}
    return ergebnis


def aktualisieren(k, zustand, sitzungen, now, opener=None, runner=None):
    """Im Tick: jeden Anbieter abrufen, dessen Intervall abgelaufen ist (nie bei offiziell=false oder offline)."""
    if not aktiv(k):
        return
    eng = eng_noetig(zustand, sitzungen, now)
    cache = cache_lesen()
    for anb in ANBIETER:
        if faellig(k, cache.get(anb), eng, now):
            abrufen(k, anb, now, opener=opener, runner=runner)

