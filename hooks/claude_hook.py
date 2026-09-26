#!/usr/bin/python3
"""Claude-Code-Hook des Limit-Wächters (zusätzlich zu Orcas Hooks in ~/.claude/settings.json).

Ereignisse:
  SessionStart / UserPromptSubmit  Sitzung registrieren (Ort orca/terminal/desktop, in Orca mit Terminal-Handle);
                                    Reserve-Sperre der eingebauten Fortsetzung;
                                    '#nacht' schaltet den Nachtmodus (block, geht nicht ans Modell); ohne Nachtmodus
                                    wird Claudes eingebaute Fortsetzung gesperrt (v1.1, [fortsetzen] nur_mit_nachtmodus)
  PreToolUse (Agent|Task|Workflow)  im STOPP/LIMIT: deny (keine neuen Subagents/Workflows)
  PostToolUse                       im STOPP einmal je Sitzung und Fenster: additionalContext
  Stop                              im STOPP einmal: decision=block mit Sicherungsauftrag, danach gestoppt
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

from lw import nacht, orte, phasen, quellen, register, sprache, texte, util  # noqa: E402
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

    if ev == "PreToolUse":
        if p and phase in ("stopp", "limit") and payload.get("tool_name") in GESPERRTE_WERKZEUGE:
            util.log(f"HOOK deny {payload.get('tool_name')} in {sid[:8]} ({phase})")
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": texte.deny_grund(p, now)}}
        return None

    if unter:
        return None                                  # sonst nur Hauptsitzung

    if ev == "PostToolUse":
        if not p or phase != "stopp":
            return None
        fid = p.get("fenster_id")
        d = register.lesen("claude", sid) or {}
        if register.hinweis_gesetzt(d, fid, "post"):
            return None

        def post(d):
            basis(d)
            register.setze_hinweis(d, fid, "post")
        register.aktualisieren("claude", sid, post, "Stopp-Hinweis (PostToolUse)")
        return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                       "additionalContext": texte.stopp_kontext(p, now)}}

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
            if aktuell and cur.get("reserve_sperre", True) and c.get("reserve_erreicht"):
                def reserve(d):
                    basis(d)
                    d["status"] = "reserve"
                register.aktualisieren("claude", sid, reserve, "eingebaute Fortsetzung wegen Reserve gesperrt")
                util.ereignis("reserve_gesperrt", anbieter="claude", sitzung=sid, cwd=payload.get("cwd"))
                return {"decision": "block", "reason": texte.reserve_block(c, now)}
            if aktuell and cur.get("nur_nacht") and not nacht.aktiv(register.lesen("claude", sid), now):
                def gesperrt(d):
                    basis(d)
                    if d.get("status") != "wartet_auf_weiter":   # schon gemeldet: kein zweiter Push
                        d["weiter_gemeldet"] = False
                    d["status"] = "wartet_auf_weiter"
                register.aktualisieren("claude", sid, gesperrt, "eingebaute Fortsetzung gesperrt (kein Nachtmodus)")
                util.ereignis("eingebaut_gesperrt", anbieter="claude", sitzung=sid, cwd=payload.get("cwd"))
                return {"decision": "block", "reason": texte.weiter_block(now)}
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
            ausgabe = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                              "additionalContext": texte.prompt_hinweis(p, now)}}
        return ausgabe or None

    if ev == "Stop":
        ergebnis = {}

        def stop(d):
            basis(d)
            status = d.get("status")
            if status == "sicherung":
                d["status"] = "gestoppt"
                util.ereignis("gestoppt", anbieter="claude", sitzung=sid, cwd=d.get("cwd"))
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
                if neu == "eingebaut_fortgesetzt" and d.get("status") == "wartet_auf_weiter":
                    return                                   # schon gesperrt (UserPromptSubmit kam zuerst)
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
