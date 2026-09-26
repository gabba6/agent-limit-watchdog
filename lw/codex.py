"""Codex in Orca-Terminals (M3): Thread-Zuordnung, Limit-Erkennung, geordneter Stopp per Steuernachricht.

Codex bekommt in v1 keinen eigenen Hook (neue Codex-Hooks brauchen eine Freigabe über /hooks und
könnten nachts eine Abfrage auslösen). Zuordnung Terminal -> Thread über Orcas Hook-Status
(paneKey -> providerSession), sonst über das Arbeitsverzeichnis der rollout-Datei.
"""

import os
import re

from . import bildschirm, nacht, quellen, register, texte, util
from .orca import OrcaFehler, pane_key
from .phasen import fenster_id
from .sprache import t

UUID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$")


def id_index(rollouts):
    index = {}
    for p in rollouts:
        m = UUID.search(p)
        if m and m.group(1) not in index:
            index[m.group(1)] = p     # rollouts sind nach mtime sortiert -> neueste Datei gewinnt
    return index


def _thread_per_cwd(rollouts, pfad_terminal, max_dateien=25):
    """Neueste interaktive Codex-CLI-Sitzung (codex-tui) im Arbeitsverzeichnis des Terminals."""
    if not pfad_terminal:
        return None
    for p in rollouts[:max_dateien]:
        kopf = quellen.lies_kopf(p) or {}
        meta = kopf.get("payload") or {}
        if kopf.get("type") != "session_meta" or meta.get("originator") != "codex-tui":
            continue
        cwd = meta.get("cwd") or ""
        if cwd == pfad_terminal or cwd.startswith(pfad_terminal.rstrip("/") + "/"):
            return meta.get("id")
    return None


def verwalten(ctx, phase, rollouts):
    """Pro Tick: Codex-Terminals registrieren, Limits erkennen, im STOPP Steuernachricht senden."""
    k, now = ctx.k, ctx.now
    terminals = ctx.agent_terminals("codex")
    if not terminals:
        return
    panes = quellen.orca_pane_sitzungen(k["daten"]["orca_hook_status"])
    index = id_index(rollouts)
    for term in terminals:
        pk = pane_key(term)
        eintrag = panes.get(pk) or {}
        tid = eintrag.get("id") if eintrag.get("anbieter") == "codex" else None
        tid = tid or _thread_per_cwd(rollouts, term.get("worktreePath"))
        if not tid:
            util.log(t("log_codex_kein_thread", handle=term.get("handle")))
            continue
        datei = index.get(tid)
        info = quellen.codex_thread(datei) if datei else None

        def basis(d, term=term, pk=pk, info=info):
            d["terminal"] = term.get("handle")
            d["pane_key"] = pk
            d["worktree"] = term.get("worktreePath")
            d["cwd"] = (info or {}).get("cwd") or d.get("cwd") or term.get("worktreePath")
            neu = info and (info.get("letzte_aktivitaet") or 0) > (d.get("status_seit") or 0)
            if d.get("status") == "fortgesetzt" and neu and not info["laeuft"] and not info["limit"]:
                d["status"] = "aktiv"
            elif d.get("status") == "wartet_auf_weiter" and neu:     # Nutzer hat selbst weitergemacht
                d["status"] = "aktiv"
        s = register.aktualisieren("codex", tid, basis)

        # Limit erkannt (task_complete mit usage_limit_exceeded)?
        lim = (info or {}).get("limit")
        if lim and lim.get("ts") and lim["ts"] > (s.get("limit_ts") or 0) and s.get("status") not in ("beendet",):
            reset = lim.get("reset") or phase.get("reset")
            art = lim.get("art") or "fuenf"

            def als_limit(d, lim=lim, reset=reset, art=art):
                register.warten_auf_reset(d, "limit", fenster_id("codex", art, reset), reset, art,
                                          k["fortsetzen"]["puffer_minuten"] * 60, "usage_limit_exceeded")
                d["limit_ts"] = lim["ts"]
                d["reserve_bei_halt"] = bool(phase.get("reserve_erreicht"))
            s = register.aktualisieren("codex", tid, als_limit, "Limit erkannt (rollout)")
            util.ereignis("limit", anbieter="codex", sitzung=tid, cwd=s.get("cwd"), reset=reset)
            ctx.aktion(t("aktion_codex_limit", id=tid[:8], zeit=util.uhrzeit(reset)))

        # Geordneter Stopp vor dem Limit
        if phase["phase"] == "stopp" and k["fortsetzen"]["codex_stopp_senden"] \
                and ctx.agent_zustand(term) == "working" \
                and not register.hinweis_gesetzt(s, phase["fenster_id"], "stop"):
            _stopp_senden(ctx, s, term, phase)


def _stopp_senden(ctx, s, term, phase):
    k = ctx.k
    try:
        bild = ctx.orca.bildschirm(term["handle"])
    except OrcaFehler as e:
        util.log(t("log_codex_bild", fehler=e))
        return
    art, grund = bildschirm.klassifiziere(bild["zeilen"], "codex")
    if art not in ("beschaeftigt", "bereit"):
        util.log(t("log_codex_nichts", id=s["id"][:8], grund=grund, ausschnitt=bildschirm.ausschnitt(bild["zeilen"])))
        return
    automatisch = not k["fortsetzen"].get("nur_mit_nachtmodus") or nacht.aktiv(s, ctx.now)
    ergebnis = ctx.orca.senden(term["handle"], text=texte.codex_stopp(phase, ctx.now, automatisch), enter=True,
                               warten=30)

    def markieren(d):
        register.setze_hinweis(d, phase["fenster_id"], "stop")
        if ergebnis.get("angenommen"):
            register.warten_auf_reset(d, "gestoppt", phase["fenster_id"], phase["reset"], phase["art"],
                                      k["fortsetzen"]["puffer_minuten"] * 60, "Steuernachricht gesendet")
            d["reserve_bei_halt"] = bool(phase.get("reserve_erreicht"))
    register.aktualisieren("codex", s["id"], markieren, "Stopp-Steuernachricht")
    util.ereignis("gestoppt", anbieter="codex", sitzung=s["id"], cwd=s.get("cwd"),
                  angenommen=bool(ergebnis.get("angenommen")), dry_run=ctx.dry_run)
    ctx.aktion(t("aktion_codex_stopp", id=s["id"][:8], projekt=os.path.basename(s.get("cwd") or ""),
                 ergebnis=t("angenommen") if ergebnis.get("angenommen") else t("nicht_angenommen")))
