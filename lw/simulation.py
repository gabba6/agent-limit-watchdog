"""Simulation ohne Verbrauch: alles läuft in einem Sandbox-Zustandsordner, nichts wird gesendet.

  simulate warn|stop|limit  -> was der Wächter JETZT bei diesen Werten täte (echte Orca-Terminals nur lesen)
  simulate reset            -> welche Orca-Sitzungen er nach einem Reset fortsetzen würde (Bildschirme lesen)
  simulate zyklus           -> kompletter Probelauf mit Probezeiten und Orca-Attrappe (Warnung bis Fortsetzung)
  simulate stop --sitzung   -> scharf, aber nur für EINE Sitzung (state/simulation.json, läuft ab)
"""

import contextlib
import copy
import importlib.util
import json
import os
import shutil
import tempfile
import time

from . import konfig, melden, nacht, register, sprache, tick, util
from .sprache import t
from .attrappe import OrcaAttrappe
from .kontext import Kontext
from .orca import Orca

HOOK_PFAD = os.path.join(util.PROJEKT, "hooks", "claude_hook.py")


def hook_modul():
    spec = importlib.util.spec_from_file_location("claude_hook", HOOK_PFAD)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@contextlib.contextmanager
def sandbox(kopieren=True):
    alt_home = os.environ.get("LIMIT_WAECHTER_HOME")
    alt_now = os.environ.get("LIMIT_WAECHTER_NOW")
    quelle = os.path.join(util.basis(), "state")
    tmp = tempfile.mkdtemp(prefix="lw-sim-")
    if kopieren and os.path.isdir(quelle):
        shutil.copytree(quelle, os.path.join(tmp, "state"),
                        ignore=shutil.ignore_patterns("*.lock", ".tmp-*"))
    os.environ["LIMIT_WAECHTER_HOME"] = tmp
    try:
        util.schreib_json(util.pfad("state", "pause.json"), {"aktiv": False})
        util.schreib_json(util.pfad("state", "wach.json"), {})
        yield tmp
    finally:
        for name, wert in (("LIMIT_WAECHTER_HOME", alt_home), ("LIMIT_WAECHTER_NOW", alt_now)):
            if wert is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = wert
        shutil.rmtree(tmp, ignore_errors=True)


def _fenster(pct, reset):
    return {"pct": float(pct), "reset": reset, "minuten": 300}


def _ausgabe(titel, erg, now):
    print(f"\n== {titel} ({time.strftime('%H:%M', time.localtime(now))}) ==")
    for a in ("claude", "codex"):
        p = erg["phasen"][a]
        print(t("sim_zeile", a=a, phase=p["phase"], p5=p["pct5"], pw=p["pctw"]))
    for m in erg["meldungen"]:
        print(t("sim_push", prio=m["prio"], text=m["text"]))
    for a in erg["aktionen"]:
        print(t("sim_aktion", text=a))
    if not erg["meldungen"] and not erg["aktionen"]:
        print(t("sim_nichts"))


# ---------------------------------------------------------------- jetzt mit echten Terminals (nur lesen)

def jetzt_mit_werten(fall, anbieter="claude"):
    k = konfig.laden()
    now = util.jetzt()
    echte_orca = Orca(k["daten"]["orca"], dry_run=True)
    with sandbox(kopieren=True):
        daten = tick.daten_sammeln(Kontext(k, echte_orca, melden.Melder(k, dry_run=True), now, dry_run=True))
        sim = copy.deepcopy(daten)
        eintrag = sim.get(anbieter) or {"fuenf": None, "woche": None}
        reset5 = (eintrag.get("fuenf") or {}).get("reset") or now + 3600
        if reset5 <= now:
            reset5 = now + 3600
        pct = {"warn": k["schwellen"]["warnung"] + 1, "stop": k["schwellen"]["stopp"] + 1, "limit": 100,
               "reset": 5}[fall]
        eintrag = dict(eintrag)
        eintrag["fuenf"] = _fenster(pct, reset5)
        eintrag["stand"] = now
        eintrag["quelle"] = "simulation"
        sim[anbieter] = eintrag
        if fall == "reset":
            _alle_als_gestoppt(anbieter, now)
        melder = melden.Melder(k, dry_run=True)
        ctx = Kontext(k, echte_orca, melder, now, dry_run=True)
        erg = tick.ausfuehren(ctx, sim=sim)
        _ausgabe(t("sim_jetzt", fall=fall, anbieter=anbieter), erg, now)
        if fall in ("stop", "limit") and anbieter == "claude":
            print(t("sim_hooks"))
        return erg


def _alle_als_gestoppt(anbieter, now):
    anzahl = 0
    for s in register.alle(anbieter):
        if s.get("status") in ("beendet",) or not s.get("terminal"):
            continue

        def gestoppt(d):
            register.warten_auf_reset(d, "gestoppt", f"{anbieter}-sim", now - 180, "fuenf", 120, "Simulation")
            d["reserve_bei_halt"] = False
            d.setdefault("versuche", {}).pop(f"{anbieter}-sim", None)
        register.aktualisieren(anbieter, s["id"], gestoppt)
        anzahl += 1
    print(t("sim_gestoppt", anzahl=anzahl, anbieter=anbieter))


# ---------------------------------------------------------------- kompletter Zyklus mit Attrappe

CLAUDE_BEREIT = ["⏺ Progress saved, WIP commit created.", "✻ Worked for 12s", "─" * 40, "❯", "─" * 40,
                 "  ⏵⏵ auto mode on (shift+tab to cycle)"]
CLAUDE_MENUE = ["You've hit your session limit · resets 4:30pm (Europe/Berlin)",
                "❯ 1. Stop and wait for limit to reset", "  2. Switch to usage credits", "  3. Upgrade your plan"]
CLAUDE_ARBEITET = ["✻ Pondering… (8s · ↓ 1.2k tokens · esc to interrupt)", "─" * 40, "❯", "─" * 40]
CODEX_BEREIT = ["• Progress saved.", "", "› Ask Codex to do anything", "", "  ⏎ send   ⌃J newline   ⌃C quit"]


def _rollout_anlegen(ordner, tid, cwd, now):
    tag = time.strftime("%Y/%m/%d", time.localtime(now))
    datei = os.path.join(ordner, tag, f"rollout-2026-01-01T00-00-00-{tid}.jsonl")
    os.makedirs(os.path.dirname(datei), exist_ok=True)
    iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now))
    zeilen = [
        {"timestamp": iso, "type": "session_meta",
         "payload": {"id": tid, "cwd": cwd, "originator": "codex-tui", "source": "cli"}},
        {"timestamp": iso, "type": "event_msg", "payload": {"type": "task_started"}},
    ]
    with open(datei, "w") as f:
        for z in zeilen:
            f.write(json.dumps(z) + "\n")
    return datei


def _protokoll_anhaengen(transcript, rollout, zeit):
    iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(zeit))
    with open(transcript, "a") as f:
        f.write(json.dumps({"type": "assistant", "isSidechain": False, "timestamp": iso,
                            "message": {"content": [{"type": "text", "text": "..."}]}}) + "\n")
    with open(rollout, "a") as f:
        f.write(json.dumps({"timestamp": iso, "type": "event_msg", "payload": {"type": "task_started"}}) + "\n")


def zyklus(ausgabe=True):
    """Kompletter Probelauf. Gibt die Ergebnisse je Schritt zurück (auch für Tests)."""
    k = konfig.laden()
    morgen = time.localtime(util.jetzt() + 86400)
    start = time.mktime((morgen.tm_year, morgen.tm_mon, morgen.tm_mday, 22, 0, 0, 0, 0, -1))   # morgen 22:00
    reset = start + 2 * 3600                                                                 # Reset um Mitternacht
    ergebnisse = []
    with sandbox(kopieren=False) as tmp:
        projekt = os.path.join(tmp, "projekt")
        os.makedirs(projekt)
        k = copy.deepcopy(k)
        k["daten"]["codex_sessions"] = os.path.join(tmp, "codex-sessions")
        k["daten"]["orca_hook_status"] = os.path.join(tmp, "orca-last-status.json")
        k["wach"]["remote_modus_pruefen"] = True
        # der Probelauf zeigt den geordneten Stopp mit eigener Fortsetzung (seit 1.4 nur noch bei Woche/Reserve
        # oder claude_stopp_art = "geordnet"; der sanfte Standard hält Claude am 5h-Stopp nicht an)
        k["schwellen"]["claude_stopp_art"] = "geordnet"
        tid = "01a0ffff-0000-7000-8000-00000000c0de"
        util.schreib_json(k["daten"]["orca_hook_status"], {"entries": {"p": {
            "paneKey": "tabX:leafX", "source": "codex", "providerSession": {"id": tid}}}})
        rollout = _rollout_anlegen(k["daten"]["codex_sessions"], tid, projekt, start)
        terminals = [
            {"handle": "term_A", "agentIdentity": "claude", "tabId": "tabA", "leafId": "leafA", "worktreePath": projekt},
            {"handle": "term_B", "agentIdentity": "claude", "tabId": "tabB", "leafId": "leafB", "worktreePath": projekt},
            {"handle": "term_C", "agentIdentity": "claude", "tabId": "tabC", "leafId": "leafC", "worktreePath": projekt},
            {"handle": "term_X", "agentIdentity": "codex", "tabId": "tabX", "leafId": "leafX", "worktreePath": projekt},
            {"handle": "term_Z", "agentIdentity": None, "tabId": "tabZ", "leafId": "leafZ", "worktreePath": projekt},
        ]
        orca = OrcaAttrappe(terminals=terminals,
                            agenten={"tabA:leafA": {"state": "working"}, "tabB:leafB": {"state": "working"},
                                     "tabC:leafC": {"state": "working"},
                                     "tabX:leafX": {"state": "working"}},
                            bildschirme={"term_A": CLAUDE_ARBEITET, "term_B": CLAUDE_ARBEITET,
                                         "term_C": CLAUDE_ARBEITET,
                                         "term_X": CODEX_BEREIT})
        hook = hook_modul()
        mac = {"netzteil": True, "wach_bei_deckel_zu": False, "schlaf_aus": False}

        def env(handle, pane):
            return {"ORCA_TERMINAL_HANDLE": handle, "ORCA_PANE_KEY": pane, "ORCA_WORKTREE_ID": f"repo::{projekt}"}

        def hook_ruf(sid, handle, pane, ev, **extra):
            payload = {"session_id": sid, "hook_event_name": ev, "cwd": projekt,
                       "transcript_path": os.path.join(tmp, f"{sid}.jsonl")}
            payload.update(extra)
            return hook.verarbeiten(payload, env(handle, pane), util.jetzt())

        def schritt(kennung, zeit, claude_pct, codex_pct, woche=40, fenster_reset=reset):
            os.environ["LIMIT_WAECHTER_NOW"] = str(zeit)
            sim = {"claude": {"fuenf": _fenster(claude_pct, fenster_reset), "woche": _fenster(woche, zeit + 4 * 86400),
                              "stand": zeit, "quelle": "simulation"},
                   "codex": {"fuenf": _fenster(codex_pct, fenster_reset), "woche": _fenster(woche, zeit + 4 * 86400),
                             "stand": zeit, "quelle": "simulation"},
                   "rollouts": [os.path.join(dp, f) for dp, _, fs in os.walk(k["daten"]["codex_sessions"]) for f in fs]}
            melder = melden.Melder(k, dry_run=True)
            ctx = Kontext(k, orca, melder, zeit, dry_run=True, claude_agenten=[])
            erg = tick.ausfuehren(ctx, sim=sim, mac_sim=mac)
            erg["schritt"] = kennung
            ergebnisse.append(erg)
            if ausgabe:
                _ausgabe(t("sim_" + kennung), erg, zeit)
            return erg

        # 1. Sitzungen melden sich an (SessionStart), alles normal
        os.environ["LIMIT_WAECHTER_NOW"] = str(start)
        hook_ruf("session-A", "term_A", "tabA:leafA", "SessionStart", source="startup")
        hook_ruf("session-B", "term_B", "tabB:leafB", "SessionStart", source="startup")
        hook_ruf("session-C", "term_C", "tabC:leafC", "SessionStart", source="startup")
        # Nachtmodus: A per "#nacht" (Hook, kein Modellaufruf), B und der Codex-Thread per Befehl; C ohne
        nacht_erg = hook_ruf("session-A", "term_A", "tabA:leafA", "UserPromptSubmit", prompt="#nacht")
        ergebnisse.append({"schritt": "nacht", "hook": nacht_erg})
        if ausgabe:
            print(t("sim_hook_nacht", wert=(nacht_erg or {}).get("decision") or "-"))
        schritt("s1", start, 50, 40)
        uhr = str(k["bericht"]["uhrzeit"])
        nacht.sitzung_an("claude", "session-B", start, uhr)
        nacht.sitzung_an("codex", tid, start, uhr)
        # 2. Warnung
        schritt("s2", start + 600, 82, 60)
        # 3. Stopp: Claude-Hooks greifen, Codex bekommt die Steuernachricht
        schritt("s3", start + 1200, 93, 93)
        os.environ["LIMIT_WAECHTER_NOW"] = str(start + 1210)
        deny = hook_ruf("session-A", "term_A", "tabA:leafA", "PreToolUse", tool_name="Agent")
        post = hook_ruf("session-A", "term_A", "tabA:leafA", "PostToolUse", tool_name="Bash")
        block = hook_ruf("session-A", "term_A", "tabA:leafA", "Stop", stop_hook_active=False)
        frei = hook_ruf("session-A", "term_A", "tabA:leafA", "Stop", stop_hook_active=True)
        hook_ruf("session-C", "term_C", "tabC:leafC", "Stop", stop_hook_active=False)
        hook_ruf("session-C", "term_C", "tabC:leafC", "Stop", stop_hook_active=True)
        hooks_erg = {"deny": deny, "post": post, "block": block, "frei": frei}
        ergebnisse.append({"schritt": "hooks", "hooks": hooks_erg})
        if ausgabe:
            print(t("sim_hook_deny", wert=(deny or {}).get("hookSpecificOutput", {}).get("permissionDecision")))
            print(t("sim_hook_post", wert="additionalContext" if post else "-"))
            print(t("sim_hook_stop", eins=(block or {}).get("decision"), zwei=frei or t("sim_frei")))
        orca.bildschirme["term_A"] = CLAUDE_BEREIT
        orca._agenten["tabA:leafA"] = {"state": "done"}
        orca.bildschirme["term_C"] = CLAUDE_BEREIT
        orca._agenten["tabC:leafC"] = {"state": "done"}
        # 4. Limit: Sitzung B scheitert am Limit (StopFailure) und zeigt das Kaufmenü
        zeit = start + 1800
        os.environ["LIMIT_WAECHTER_NOW"] = str(zeit)
        with open(os.path.join(tmp, "session-B.jsonl"), "w") as f:
            f.write(json.dumps({"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit",
                                "isSidechain": False,
                                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(zeit)),
                                "message": {"content": [{"type": "text", "text": "You've hit your session limit"}]},
                                "quotaLimits": {"status": "rejected", "resetsAt": int(reset),
                                                "rateLimitType": "five_hour", "isUsingOverage": False}}) + "\n")
        hook_ruf("session-B", "term_B", "tabB:leafB", "StopFailure", error="rate_limit",
                 last_assistant_message="You've hit your session limit · resets 4:30pm (Europe/Berlin)")
        orca.bildschirme["term_B"] = CLAUDE_MENUE
        orca._agenten["tabB:leafB"] = {"state": "done"}
        orca.bildschirme["term_X"] = CODEX_BEREIT
        orca._agenten["tabX:leafX"] = {"state": "done"}
        schritt("s4", zeit, 100, 97)
        # 5. Nachts: Reset + 3 min -> A und Codex (Nachtmodus) fortsetzen, B wartet auf Claudes eingebaute
        #    Fortsetzung, C (kein Nachtmodus) bekommt nichts gesendet -> wartet auf "weiter", ein Push
        neues_fenster = reset + 5 * 3600
        schritt("s5", reset + 180, 0, 0, fenster_reset=neues_fenster)
        # v1.4: die fortgesetzten Sitzungen arbeiten wieder -> neue Protokolleinträge als Beleg für die Nachprüfung
        _protokoll_anhaengen(os.path.join(tmp, "session-A.jsonl"), rollout, reset + 200)
        orca.bildschirme["term_A"] = CLAUDE_ARBEITET
        orca._agenten["tabA:leafA"] = {"state": "working"}
        # 6. Reset + 6 min: B ist fällig, am Bildschirm steht das Kaufmenü -> nichts senden, Push
        schritt("s6", reset + 360, 1, 1, fenster_reset=neues_fenster)
        # 7. Morgens: Bericht
        morgen = time.localtime(reset + 360)
        acht = time.mktime((morgen.tm_year, morgen.tm_mon, morgen.tm_mday + 1, 8, 1, 0, 0, 0, -1))
        schritt("s7", acht, 1, 1, fenster_reset=acht + 5 * 3600)
        endzustand = {s["id"]: s["status"] for s in register.alle()}
        ergebnisse.append({"schritt": "endzustand", "sitzungen": endzustand, "gesendet": list(orca.gesendet)})
        if ausgabe:
            print(t("sim_ende"))
            for sid, st in sorted(endzustand.items()):
                print(f"  {sid:40} {t('z_' + st) if ('z_' + st) in sprache.TEXTE else st}")
            print(t("sim_gesendet"))
            for g in orca.gesendet:
                print("   -", g.get("handle") or g.get("erstellen"), ":",
                      (g.get("text") or g.get("befehl") or "Enter")[:90])
    return ergebnisse


# ---------------------------------------------------------------- scharf für genau eine Sitzung

def scharf_eine_sitzung(sid, minuten=10):
    now = util.jetzt()
    reset = now + 3600
    util.schreib_json(util.pfad("state", "simulation.json"), {
        "aktiv": True, "bis": now + minuten * 60, "sitzungen": [sid],
        "claude": {"phase": "stopp", "art": "fuenf", "pct": 93.0, "reset": reset,
                   "fenster_id": f"claude-sim-{int(now)}", "pct5": 93.0, "reset5": reset,
                   "pctw": 40.0, "resetw": now + 4 * 86400, "reserve_erreicht": False}})
    print(t("sim_scharf", sid=sid, minuten=minuten))
    print(t("sim_scharf_ende"))


def aus():
    util.schreib_json(util.pfad("state", "simulation.json"), {"aktiv": False})
    print(t("sim_aus"))
