#!/usr/bin/python3
"""Claude-Code-Hook des Limit-Wächters (zusätzlich zu Orcas Hooks in ~/.claude/settings.json).

Ereignisse:
  SessionStart / UserPromptSubmit  Sitzung registrieren (Ort orca/terminal/desktop, in Orca mit Terminal-Handle);
                                    Reserve-Sperre der eingebauten Fortsetzung (sonst wird sie seit 1.4 nie gesperrt,
                                    "nativ zuerst"); '#nacht' schaltet den Nachtmodus (block, geht nicht ans Modell)
  PreToolUse (Agent|Task|Workflow)  im STOPP/LIMIT: deny (keine neuen Subagents/Workflows)
  PostToolUse                       im STOPP einmal je Sitzung und Fenster: additionalContext
  Stop                              nur beim geordneten Stopp (Woche/Reserve oder claude_stopp_art = "geordnet")
                                    einmal: decision=block mit Sicherungsauftrag, danach gestoppt. Der sanfte Stopp
                                    (Standard am 5h-Stopp) verweigert nur neue Subagents/Workflows und gibt einmal
                                    je Sitzung und Fenster einen kurzen Hinweis.
  Kontext (v1.4)                    optional ([kontext] hinweis_an_sitzung): einmal je Stufe additionalContext
  StopFailure (rate_limit)          Sitzung am Limit, Reset aus dem Transcript (quotaLimits)
  Notification (quota_auto_resume_*, permission_prompt), PermissionDenied, SessionEnd: Register/Bericht

Greift seit 1.3 überall ein, wo Claude Code auf diesem Mac läuft (Orca, Terminal, IDE, vermutlich Desktop; nicht
bei Claude Code im Web, siehe lw/orte.py). Mit [allgemein] nur_orca = true (in state/current.json) nur in
Orca-Terminals wie bis 1.2. Außerhalb von Orca werden keine Orca-Felder gespeichert und der Sicherungsauftrag
verspricht keine automatische Fortsetzung. Nie, wenn der Wächter pausiert ist oder sein Zustand veraltet ist.
Fehler führen nie zu einer Blockade: dann gibt der Hook nichts aus.
"""

import json
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lw import kontextfenster, nacht, orte, phasen, quellen, register, sprache, texte, util  # noqa: E402
from lw.sprache import t  # noqa: E402

GESPERRTE_WERKZEUGE = {"Agent", "Task", "Workflow"}
STANDARD_MAX_ALTER_S = 600
STANDARD_PUFFER_S = 120


def zustand(sid, now):
    """-> (phase-dict | None, grund, current)"""
    cur = util.lies_json(util.pfad("state", "current.json"), {}) or {}
    pause = util.lies_json(util.pfad("state", "pause.json"), {}) or {}
    if pause.get("aktiv") and (pause.get("bis") is None or pause["bis"] > now):
        return None, "pausiert", cur
    sim = util.lies_json(util.pfad("state", "simulation.json"), {}) or {}
    if sim.get("aktiv") and sim.get("bis", 0) > now and sid in (sim.get("sitzungen") or []):
        return sim.get("claude") or {}, "simulation", cur
    stand = cur.get("stand")
    if not stand or now - stand > cur.get("hook_max_alter_s", STANDARD_MAX_ALTER_S):
        return None, "veraltet", cur
    p = cur.get("claude") or {}
    if p.get("phase") in ("stopp", "limit") and (not p.get("reset") or p["reset"] <= now):
        return None, "abgelaufen", cur
    return p, "aktuell", cur


ORCA_FELDER = ("terminal", "pane_key", "worktree_id", "worktree")


def _basis(payload, env, ort):
    def setzen(d):
        d["ort"] = ort
        if ort != "orca":                            # nie ein altes Orca-Handle ansprechen
            for feld in ORCA_FELDER:
                d.pop(feld, None)
        for feld, wert in (("cwd", payload.get("cwd")), ("transcript", payload.get("transcript_path")),
                           ("modus", payload.get("permission_mode")),
                           ("entrypoint", env.get("CLAUDE_CODE_ENTRYPOINT"))):
            if wert:
                d[feld] = wert
        if ort == "orca":
            for feld, wert in (("terminal", env.get("ORCA_TERMINAL_HANDLE")), ("pane_key", env.get("ORCA_PANE_KEY"))):
                if wert:
                    d[feld] = wert
            wt = env.get("ORCA_WORKTREE_ID")
            if wt:
                d["worktree_id"] = wt
                d["worktree"] = wt.split("::", 1)[-1]
    return setzen


KX_STUFE = {"ok": 0, "warnung": 1, "kritisch": 2}


def kontext_hinweis(payload, cur, sid):
    """v1.4 N4: einmal je Stufe ein kurzer Hinweis an die Sitzung ([kontext] hinweis_an_sitzung). Nach einer
    Kompaktierung (wieder ok) darf er erneut kommen. -> Text oder None."""
    kc = cur.get("kontext") or {}
    if not kc.get("hinweis"):
        return None
    kx = kontextfenster.lesen("claude", sid) \
        or kontextfenster.aus_transcript(payload.get("transcript_path"), kc.get("standard_fenster") or 200000)
    if not kx:
        return None
    stufe = kontextfenster.stufe(kx["prozent"], kc.get("warnung", 70), kc.get("kritisch", 85))
    nr = KX_STUFE.get(stufe, 0)
    d = register.lesen("claude", sid) or {}
    alt = int(d.get("kontext_hinweis") or 0)
    if nr == alt or (nr < alt and nr > 0):
        return None

    def merken(d):
        d["kontext_hinweis"] = nr
    register.aktualisieren("claude", sid, merken)
    return texte.kontext_hinweis(kx) if nr > alt else None


def _mit_kontext(ausgabe, ev, extra):
    """additionalContext um den Kontext-Hinweis ergänzen (oder neu anlegen)."""
    if not extra:
        return ausgabe
    ausgabe = ausgabe or {}
    hso = ausgabe.setdefault("hookSpecificOutput", {"hookEventName": ev})
    hso["additionalContext"] = (hso.get("additionalContext") + "\n" if hso.get("additionalContext") else "") + extra
    return ausgabe


def verarbeiten(payload, env, now):
    ev = payload.get("hook_event_name") or ""
    sid = payload.get("session_id")
    ort = orte.ort_claude(env)
    if not sid or not ort:
        return None                                  # z. B. Claude Code im Web
    unter = bool(payload.get("agent_id"))            # Subagent-Aufruf
    p, grund, cur = zustand(sid, now)
    if cur.get("nur_orca") and ort != "orca":
        return None                                  # nur_orca = true: Verhalten bis 1.2
    sprache.setzen(cur.get("sprache") or "en", cur.get("name") or "")
    phase = (p or {}).get("phase", "ok")
    puffer = cur.get("puffer_s", STANDARD_PUFFER_S)
    basis = _basis(payload, env, ort)
    sanft = bool(p) and phasen.claude_sanft(cur.get("claude_stopp_art"), p)   # v1.4 N2

    if ev == "PreToolUse":
        if p and phase in ("stopp", "limit") and payload.get("tool_name") in GESPERRTE_WERKZEUGE:
            util.log(f"HOOK deny {payload.get('tool_name')} in {sid[:8]} ({phase}{', sanft' if sanft else ''})")
            grund = texte.sanft_deny(p, now) if sanft else texte.deny_grund(p, now)
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": grund}}
        return None

    if unter:
        return None                                  # sonst nur Hauptsitzung

    if ev == "PostToolUse":
        ausgabe = None
        if p and phase == "stopp":
            ausgabe = _einmal_hinweis(sid, p, basis, sanft, "PostToolUse", now)
        if grund == "pausiert":
            return ausgabe
        return _mit_kontext(ausgabe, "PostToolUse", kontext_hinweis(payload, cur, sid))

    if ev == "SessionStart":
        def start(d):
            basis(d)
            d["quelle"] = payload.get("source")
            if d.get("status") in ("beendet",):
                d["status"] = "aktiv"
        register.aktualisieren("claude", sid, start)
        return None

    if ev == "UserPromptSubmit":
        prompt = payload.get("prompt") or payload.get("user_prompt") or ""
        ausgabe = {}

        befehl = nacht.befehl(prompt)                # '#nacht …': unabhängig von Pause/Zustand/Phase
        if befehl:
            uhr = cur.get("nacht_ende") or nacht.STANDARD_UHRZEIT
            wort, alle = befehl
            if wort == "aus":
                nacht.sitzung_aus("claude", sid, now, aenderung=basis)
                gb = nacht.global_bis(now)
                if gb:
                    return {"decision": "block", "reason": texte.nacht_antwort("aus_global", gb, now)}
                return {"decision": "block", "reason": texte.nacht_antwort("aus", bezug=now)}
            if alle:
                register.aktualisieren("claude", sid, basis)
                b = nacht.alle_an(now, uhr)
            else:
                b = nacht.sitzung_an("claude", sid, now, uhr, aenderung=basis)
            return {"decision": "block", "reason": texte.nacht_antwort("alle" if alle else "an", b, now)}

        if prompt.startswith(texte.EINGEBAUT_PRAEFIX):
            aktuell = grund in ("aktuell", "abgelaufen")
            c = cur.get("claude") or {}
            # v1.4 N1 "nativ zuerst": nur die Wochenreserve sperrt Claudes eingebaute Fortsetzung, nie der Nachtmodus
            if aktuell and cur.get("reserve_sperre", True) and c.get("reserve_erreicht"):
                def reserve(d):
                    basis(d)
                    d["status"] = "reserve"
                register.aktualisieren("claude", sid, reserve, "eingebaute Fortsetzung wegen Reserve gesperrt")
                util.ereignis("reserve_gesperrt", anbieter="claude", sitzung=sid, cwd=payload.get("cwd"))
                return {"decision": "block", "reason": texte.reserve_block(c, now)}
            neu, notiz = "eingebaut_fortgesetzt", "eingebaute Fortsetzung"
            util.ereignis("eingebaut", anbieter="claude", sitzung=sid, cwd=payload.get("cwd"),
                          weg="eingebaute Fortsetzung")
        elif prompt.startswith(texte.PRAEFIXE):
            neu, notiz = "fortgesetzt", "Fortsetzungsprompt angekommen"
        else:
            neu, notiz = "aktiv", None

        def prompt_da(d):
            basis(d)
            d["status"] = neu
        register.aktualisieren("claude", sid, prompt_da, notiz)
        if p and phase in ("stopp", "limit"):
            if sanft:
                ausgabe = _einmal_hinweis(sid, p, basis, sanft, "UserPromptSubmit", now)
            else:
                ausgabe = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                  "additionalContext": texte.prompt_hinweis(p, now)}}
        if grund != "pausiert":
            ausgabe = _mit_kontext(ausgabe, "UserPromptSubmit", kontext_hinweis(payload, cur, sid))
        return ausgabe or None

    if ev == "Stop":
        ergebnis = {}

        def stop(d):
            basis(d)
            status = d.get("status")
            if status == "sicherung":
                d["status"] = "gestoppt"
                util.ereignis("gestoppt", anbieter="claude", sitzung=sid, cwd=d.get("cwd"))
            elif p and phase == "stopp" and sanft:
                d["status"] = "aktiv"                # v1.4 N2: kein Stop-Block, nicht als gestoppt registrieren
            elif p and phase == "stopp":
                fid = p.get("fenster_id")
                if not register.hinweis_gesetzt(d, fid, "stop") and not payload.get("stop_hook_active"):
                    register.setze_hinweis(d, fid, "stop")
                    register.warten_auf_reset(d, "sicherung", fid, p.get("reset"), p.get("art"), puffer,
                                              "Sicherungsauftrag")
                    d["reserve_bei_halt"] = bool(p.get("reserve_erreicht"))
                    ergebnis["block"] = True
                else:
                    register.warten_auf_reset(d, "gestoppt", fid, p.get("reset"), p.get("art"), puffer, "Stopp-Phase")
                    d["reserve_bei_halt"] = bool(p.get("reserve_erreicht"))
                    util.ereignis("gestoppt", anbieter="claude", sitzung=sid, cwd=d.get("cwd"))
            elif phase in ("ok", "warnung") or not p:
                d["status"] = "aktiv"
        register.aktualisieren("claude", sid, stop)
        if ergebnis.get("block"):
            util.log(t("log_hook_block", sid=sid[:8]))
            # außerhalb von Orca setzt nach einem Wächter-Stopp niemand automatisch fort (Vertrag 6)
            automatisch = ort == "orca" and (not cur.get("nur_nacht")
                                             or nacht.aktiv(register.lesen("claude", sid), now))
            return {"decision": "block", "reason": texte.sicherungsauftrag(p, now, automatisch)}
        return None

    if ev == "StopFailure":
        if payload.get("error") != "rate_limit":
            return None
        text = payload.get("last_assistant_message") or payload.get("error_details") or ""
        lim = quellen.claude_limit_aus_transcript(payload.get("transcript_path"))
        if lim and lim.get("ts") and lim["ts"] < now - 300:
            lim = None                                # alter Eintrag, gehört nicht zu diesem Fehler
        text = text or (lim or {}).get("text") or ""
        planlimit = bool((lim and lim.get("status") == "rejected") or quellen.PLANLIMIT_TEXT.search(text)
                         or (lim and lim.get("reset")))
        if not planlimit:
            util.ereignis("drossel", anbieter="claude", sitzung=sid, text=text[:120])
            return None
        c = cur.get("claude") or {}
        art = quellen.art_kurz((lim or {}).get("art") or ("woche" if "week" in text.lower() else "fuenf"))
        reset = (lim or {}).get("reset") or quellen.claude_reset_aus_text(text, now) \
            or (c.get("resetw") if art == "woche" else c.get("reset5"))
        fid = phasen.fenster_id("claude", art, reset) if reset else None

        def limit(d):
            basis(d)
            register.warten_auf_reset(d, "limit", fid, reset, art, puffer, "StopFailure rate_limit")
            d["ueberziehung"] = bool((lim or {}).get("ueberziehung"))
            d["reserve_bei_halt"] = bool(c.get("reserve_erreicht"))
        register.aktualisieren("claude", sid, limit, "Limit erreicht")
        util.ereignis("limit", anbieter="claude", sitzung=sid, cwd=payload.get("cwd"), reset=reset, art=art)
        return None

    if ev == "Notification":
        typ = payload.get("notification_type") or ""
        neu = {"quota_auto_resume_armed": "eingebaut_wartet", "quota_auto_resume_fired": "eingebaut_fortgesetzt",
               "quota_auto_resume_stale": "stale", "quota_auto_resume_disabled": "disabled"}.get(typ)
        if neu:
            def quota(d):
                basis(d)
                if neu == "eingebaut_fortgesetzt" and d.get("status") == "reserve":
                    return                                   # wegen Reserve gesperrt (UserPromptSubmit kam zuerst)
                d["status"] = neu
                if neu in ("stale", "disabled"):
                    r = d.get("reset")
                    d["fortsetzen_ab"] = (r + puffer) if (r and r > now) else now
            register.aktualisieren("claude", sid, quota, typ)
            if neu != "eingebaut_wartet":
                util.ereignis("eingebaut", anbieter="claude", sitzung=sid, cwd=payload.get("cwd"), weg=typ)
        elif typ == "permission_prompt":
            d = register.lesen("claude", sid) or {}
            if d.get("status") in ("fortgesetzt", "eingebaut_fortgesetzt"):
                def freigabe(d):
                    d["wartet_auf_freigabe"] = now
                register.aktualisieren("claude", sid, freigabe, "wartet auf Freigabe")
                util.ereignis("wartet_auf_freigabe", anbieter="claude", sitzung=sid, cwd=payload.get("cwd"))
        return None

    if ev == "PermissionDenied":
        util.ereignis("freigabe_blockiert", anbieter="claude", sitzung=sid, cwd=payload.get("cwd"),
                      werkzeug=payload.get("tool_name"), grund=str(payload.get("reason") or "")[:160])
        return None

    if ev == "SessionEnd":
        def ende(d):
            basis(d)
            d["status"] = "beendet"
        register.aktualisieren("claude", sid, ende, f"SessionEnd {payload.get('reason') or ''}".strip())
        return None
    return None


def _einmal_hinweis(sid, p, basis, sanft, ev, now):
    """Stopp-Hinweis höchstens einmal je Sitzung und Fenster (sanft: kurzer Text, geordnet: Stopp-Auftrag)."""
    fid = p.get("fenster_id")
    d = register.lesen("claude", sid) or {}
    if register.hinweis_gesetzt(d, fid, "post"):
        return None

    def post(d):
        basis(d)
        register.setze_hinweis(d, fid, "post")
    register.aktualisieren("claude", sid, post, f"Stopp-Hinweis ({ev}{', sanft' if sanft else ''})")
    text = texte.sanft_kontext(p, now) if sanft else texte.stopp_kontext(p, now)
    return {"hookSpecificOutput": {"hookEventName": ev, "additionalContext": text}}


def main():
    signal.signal(signal.SIGALRM, lambda *_: sys.exit(0))
    signal.alarm(8)
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    try:
        ausgabe = verarbeiten(payload, os.environ, util.jetzt())
    except Exception as e:   # ein Fehler im Wächter darf Claude nie blockieren
        try:
            util.log(t("log_hook_fehler", ev=payload.get("hook_event_name"), typ=type(e).__name__, fehler=e))
        except Exception:
            pass
        return 0
    if ausgabe:
        sys.stdout.write(json.dumps(ausgabe, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
