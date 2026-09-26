"""Fortsetzen nach dem Reset (M4).

Reihenfolge je wartender Sitzung (nach resets_at + Puffer, Wochenreserve beachten):
  Terminal arbeitet bereits          -> nur Register aktualisieren
  Bildschirm zeigt Menü/Kaufoption   -> NICHTS senden, Push an den Nutzer
  Bildschirm 'stale' (Enter nötig)   -> nur Enter
  Terminal ruht (leere Eingabe)      -> Fortsetzungsprompt senden
  Terminal fehlt, Session-ID bekannt -> neues Orca-Terminal mit claude --resume / codex resume
Höchstens max_pro_fenster automatische Fortsetzungen je Sitzung und Fenster, danach Push.

Außerhalb von Orca (v1.3, Ort terminal/desktop) wird nie getippt, nie ein Bildschirm gelesen und nie ein
Terminal geöffnet: Codex im Terminal per `codex queue` (wenn eingeschaltet), sonst Status wartet_auf_weiter
und Push mit Kopierbefehl.
"""

import os
import shlex
import subprocess

from . import bildschirm, orte, quellen, register, texte, util
from .sprache import t
from .orca import OrcaFehler, pane_key


GESCHUETZT = ("~/Documents", "~/Desktop", "~/Downloads", "~/Library/CloudStorage", "~/Library/Mobile Documents",
              "~/Pictures", "~/Movies", "~/Music")


def ordner_ok(pfad):
    """Existiert der Ordner? In von macOS geschützten Bereichen nicht selbst nachsehen (TCC-Abfrage
    aus dem LaunchAgent nachts); dort entscheidet das Orca-Terminal, das die Rechte schon hat."""
    if not pfad:
        return False
    for g in GESCHUETZT:
        basis = os.path.expanduser(g)
        if pfad == basis or pfad.startswith(basis + "/"):
            return True
    return os.path.isdir(pfad)


def finde_terminal(ctx, s):
    kandidaten = ctx.agent_terminals(s["anbieter"])
    for term in kandidaten:
        if s.get("terminal") and term.get("handle") == s["terminal"]:
            return term
    for term in kandidaten:
        if s.get("pane_key") and pane_key(term) == s["pane_key"]:
            return term
    return None


def _kurz(s):
    return f"{s['anbieter']} {str(s['id'])[:8]} ({os.path.basename(s.get('cwd') or '') or '?'})"


def _setze(s, status, notiz=None, **felder):
    def aenderung(d):
        d["status"] = status
        d.update(felder)
    return register.aktualisieren(s["anbieter"], s["id"], aenderung, notiz)


def faellig(s, phase, k, now):
    """-> (faellig: bool, grund) für eine wartende Sitzung."""
    f = k["fortsetzen"]
    if s.get("status") not in register.WARTET:
        return False, "nicht wartend"
    ab = s.get("fortsetzen_ab")
    if not ab or ab > now:
        return False, "Reset noch nicht erreicht"
    if phase["phase"] in ("stopp", "limit"):
        return False, f"{phase['anbieter']} noch in Phase {phase['phase']}"
    if s["anbieter"] == "claude" and s["status"] in ("limit", "stale", "disabled", "eingebaut_wartet") \
            and f["claude_limit_resume"] == "orca" and orte.ort(s) == "orca":
        return False, "Claude-Fortsetzung am Limit übernimmt Orca"
    if s["anbieter"] == "claude" and s["status"] == "limit" \
            and now < (s.get("reset") or 0) + f["claude_eingebaut_karenz_minuten"] * 60:
        return False, "Karenz für Claudes eingebaute Fortsetzung"
    if s["status"] == "eingebaut_wartet" \
            and now < (s.get("reset") or 0) + 3 * f["claude_eingebaut_karenz_minuten"] * 60:
        return False, "Claudes eingebautes Warten läuft (Wächter übernimmt erst nach Reset + 3× Karenz)"
    return True, ""


def bearbeiten(ctx, s, phase):
    """Eine fällige Sitzung fortsetzen. -> kurzer Ergebnistext."""
    k, now = ctx.k, ctx.now
    f = k["fortsetzen"]
    fid = s.get("fenster_id")

    if phase.get("reserve_erreicht") or s.get("reserve_bei_halt"):
        _setze(s, "reserve", "Wochenreserve erreicht – keine automatische Fortsetzung")
        ctx.melder.senden(t("push_reserve_halt", n=texte.NAME[s["anbieter"]]), prio=4, schluessel=f"reserve-halt:{s['anbieter']}:{fid}")
        return "reserve"
    if register.versuche(s, fid) >= f["max_pro_fenster"]:
        _setze(s, "aufgegeben", "zu viele automatische Fortsetzungen in diesem Fenster")
        ctx.melder.senden(t("push_aufgegeben", n=texte.NAME[s["anbieter"]], max=f["max_pro_fenster"]), prio=4, schluessel=f"aufgegeben:{s['id']}:{fid}")
        return "aufgegeben"

    if orte.ort(s) != "orca" or not ctx.orca_vorhanden():
        if s["anbieter"] == "codex" and orte.ort(s) == "terminal" and orte.codex_queue_an(k):
            info = _codex_info(ctx, s)
            if info and (info.get("laeuft") or (info.get("letzte_aktivitaet") or 0) > (s.get("reset") or now)):
                _setze(s, "fortgesetzt", "läuft bereits (von Hand)", geprueft=True)
                return "laeuft"
            register.aktualisieren(s["anbieter"], s["id"], lambda d: register.zaehle_versuch(d, fid))
            if _codex_queue(ctx, s, f["pruefen_nach_minuten"] * 60):
                return "fortgesetzt"
        auf_weiter_setzen(s, "außerhalb von Orca: wartet auf weiter")
        return "weiter"
    term = finde_terminal(ctx, s)
    if term is not None:
        return _im_terminal(ctx, s, term)
    if ctx.orca_fehler:
        ctx.melder.senden(t("push_orca_weg"), prio=4,
                          schluessel=f"orca-weg:{int(now // 3600)}")
        return "orca-fehler"
    return _neu_starten(ctx, s)


def _blockiert(ctx, s, grund, art):
    fid = s.get("fenster_id")
    _setze(s, "blockiert", grund)
    util.ereignis("blockiert", anbieter=s["anbieter"], sitzung=s["id"], cwd=s.get("cwd"), grund=grund)
    text = t({"menue": "blockiert_menue", "geld": "blockiert_geld",
              "eingabe_belegt": "blockiert_belegt"}.get(art, "blockiert_unklar"))
    ctx.melder.senden(t("push_blockiert", n=texte.NAME[s["anbieter"]], text=text), prio=4,
                      schluessel=f"blockiert:{s['id']}:{fid}")
    ctx.aktion(t("aktion_blockiert", s=_kurz(s), grund=grund))
    return "blockiert"


def _im_terminal(ctx, s, term):
    k, now = ctx.k, ctx.now
    fid = s.get("fenster_id")
    handle = term["handle"]
    zustand = ctx.agent_zustand(term)
    if zustand == "working":
        _setze(s, "fortgesetzt", "läuft bereits (eingebaute Fortsetzung oder von Hand)", terminal=handle)
        ctx.aktion(t("aktion_laeuft", s=_kurz(s)))
        return "laeuft"
    try:
        bild = ctx.orca.bildschirm(handle)
    except OrcaFehler as e:
        return _blockiert(ctx, s, t("grund_bild", fehler=e), "unbekannt")
    art, grund = bildschirm.klassifiziere(bild["zeilen"], s["anbieter"])
    util.log(t("log_bildschirm", s=_kurz(s), art=art, grund=grund, ausschnitt=bildschirm.ausschnitt(bild["zeilen"])))
    if art == "beschaeftigt":
        _setze(s, "fortgesetzt", "läuft bereits", terminal=handle)
        return "laeuft"
    if art == "eingebaut_wartet" and s["anbieter"] == "claude" \
            and now < (s.get("reset") or 0) + 3 * k["fortsetzen"]["claude_eingebaut_karenz_minuten"] * 60:
        ctx.aktion(t("aktion_warte", s=_kurz(s)))
        return "warten"
    if art == "stale":
        ergebnis = ctx.orca.senden(handle, text=None, enter=True, warten=0)
        weg = t("weg_enter")
    elif art == "bereit":
        ergebnis = ctx.orca.senden(handle, text=texte.fortsetzungsprompt(), enter=True, warten=60)
        weg = t("weg_prompt")
    else:
        return _blockiert(ctx, s, grund, art)

    def zaehlen(d):
        register.zaehle_versuch(d, fid)
    register.aktualisieren(s["anbieter"], s["id"], zaehlen)
    if ergebnis.get("angenommen"):
        _setze(s, "fortgesetzt", f"{weg} gesendet", terminal=handle,
               pruefen_ab=now + k["fortsetzen"]["pruefen_nach_minuten"] * 60, geprueft=False)
        util.ereignis("fortgesetzt", anbieter=s["anbieter"], sitzung=s["id"], cwd=s.get("cwd"), weg=weg,
                      dry_run=ctx.dry_run)
        ctx.aktion(t("aktion_fortgesetzt", s=_kurz(s), weg=weg))
        return "fortgesetzt"
    if s["anbieter"] == "codex" and not ergebnis.get("fehler") and not ctx.dry_run:
        # Orca hat ausdrücklich nicht angenommen (nichts zugestellt) -> Fallback codex queue
        if _codex_queue(ctx, s):
            return "fortgesetzt"
    return _blockiert(ctx, s, t("grund_senden", fehler=ergebnis.get("fehler") or t("grund_nicht_angenommen")),
                      "unbekannt")


def auf_weiter_setzen(s, notiz="ohne Nachtmodus: wartet auf weiter"):
    """Nichts senden, nur vermerken (der Nutzer tippt selbst "weiter"; Push kommt gebündelt vom Tick)."""
    def aenderung(d):
        d["status"] = "wartet_auf_weiter"
        d["weiter_gemeldet"] = False
    register.aktualisieren(s["anbieter"], s["id"], aenderung, notiz)
    util.ereignis("wartet_auf_weiter", anbieter=s["anbieter"], sitzung=s["id"], cwd=s.get("cwd"))


def codex_queue(ctx, sid, text):
    """Nachricht per `codex queue` an einen bestehenden Codex-Thread (Argumentliste, keine Shell).
    Im Dry-Run nur protokollieren (wie orca.senden). -> True bei Exitcode 0."""
    befehl = [ctx.k["fortsetzen"]["codex_befehl"], "queue", "--thread", sid, "--message", text]
    if ctx.dry_run:
        util.log(t("log_codex_queue_dry", id=str(sid)[:8], text=repr(text[:60])))
        return True
    try:
        r = subprocess.run(befehl, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        util.log(t("log_codex_queue_fehler", id=str(sid)[:8], fehler=e))
        return False
    if r.returncode != 0:
        util.log(t("log_codex_queue_fehler", id=str(sid)[:8], fehler=(r.stderr or "").strip()[:200] or r.returncode))
        return False
    return True


def _codex_queue(ctx, s, pruefen_s=120):
    if not codex_queue(ctx, s["id"], texte.fortsetzungsprompt()):
        return False
    _setze(s, "fortgesetzt", "codex queue", pruefen_ab=ctx.now + pruefen_s, geprueft=False)
    util.ereignis("fortgesetzt", anbieter="codex", sitzung=s["id"], cwd=s.get("cwd"), weg="codex queue")
    ctx.aktion(t("aktion_fortgesetzt", s=_kurz(s), weg="codex queue"))
    return True


def _neu_starten(ctx, s):
    k, now = ctx.k, ctx.now
    f = k["fortsetzen"]
    fid = s.get("fenster_id")
    cwd = s.get("cwd")
    if not ordner_ok(cwd):
        return _blockiert(ctx, s, t("grund_ordner"), "unbekannt")
    if s["anbieter"] == "claude":
        laufend = ctx.claude_agenten()
        if laufend is None:
            return _blockiert(ctx, s, t("grund_agents"), "unbekannt")
        if any(a.get("sessionId") == s["id"] for a in laufend):
            return _blockiert(ctx, s, t("grund_woanders"), "unbekannt")
        programm = (f"{shlex.quote(f['claude_befehl'])} --resume {shlex.quote(s['id'])} "
                    f"--permission-mode {shlex.quote(f['claude_modus'])} {shlex.quote(texte.fortsetzungsprompt())}")
    else:
        programm = (f"{shlex.quote(f['codex_befehl'])} resume {shlex.quote(s['id'])} "
                    f"--sandbox {shlex.quote(f['codex_sandbox'])} {shlex.quote(texte.fortsetzungsprompt())}")
    befehl = f"cd {shlex.quote(cwd)} && {programm}"
    auswahl = [f"id:{s['worktree_id']}"] if s.get("worktree_id") else []
    auswahl.append(f"path:{s.get('worktree') or cwd}")

    def zaehlen(d):
        register.zaehle_versuch(d, fid)
    register.aktualisieren(s["anbieter"], s["id"], zaehlen)
    letzter = None
    for sel in auswahl:
        try:
            r = ctx.orca.erstellen(sel, befehl, t("terminal_titel", app=t("app")))
        except OrcaFehler as e:
            letzter = str(e)
            continue
        _setze(s, "fortgesetzt", "neues Terminal mit --resume", terminal=r.get("handle"),
               pruefen_ab=now + max(3, f["pruefen_nach_minuten"]) * 60, geprueft=False)
        util.ereignis("fortgesetzt", anbieter=s["anbieter"], sitzung=s["id"], cwd=cwd, weg=t("weg_neu"),
                      dry_run=ctx.dry_run)
        ctx.aktion(t("aktion_neu", s=_kurz(s), sel=sel))
        return "neu"
    return _blockiert(ctx, s, t("grund_erstellen", fehler=letzter), "unbekannt")


def pruefen(ctx, s):
    """Ein paar Minuten nach der Fortsetzung nachsehen, ob der Agent arbeitet oder an einer Abfrage hängt."""
    if orte.ort(s) != "orca":
        return _pruefen_rollout(ctx, s)
    term = finde_terminal(ctx, s)
    if term is None:
        if ctx.now - (s.get("status_seit") or ctx.now) > 600:
            _setze(s, "fortgesetzt", "Terminal nach Fortsetzung nicht gefunden", geprueft=True)
            ctx.melder.senden(t("push_verloren", n=texte.NAME[s["anbieter"]]), prio=4, schluessel=f"verloren:{s['id']}:{s.get('fenster_id')}")
        return
    if ctx.agent_zustand(term) == "working":
        _setze(s, "fortgesetzt", "Prüfung: arbeitet", geprueft=True, terminal=term["handle"])
        return
    try:
        bild = ctx.orca.bildschirm(term["handle"])
    except OrcaFehler:
        return
    art, grund = bildschirm.klassifiziere(bild["zeilen"], s["anbieter"])
    if art in ("menue", "geld", "eingabe_belegt", "unbekannt", "stale"):
        util.log(t("log_pruefung", s=_kurz(s), art=art, ausschnitt=bildschirm.ausschnitt(bild["zeilen"])))
        _setze(s, "fortgesetzt", f"Prüfung: {grund}", geprueft=True, terminal=term["handle"])
        util.ereignis("haengt", anbieter=s["anbieter"], sitzung=s["id"], cwd=s.get("cwd"), grund=grund)
        ctx.melder.senden(t("push_haengt", n=texte.NAME[s["anbieter"]]), prio=4, schluessel=f"haengt:{s['id']}:{s.get('fenster_id')}")
    else:
        _setze(s, "fortgesetzt", f"Prüfung: {grund}", geprueft=True, terminal=term["handle"])


def _codex_info(ctx, s):
    """rollout-Info des Codex-Threads oder None (Datei liegt im Ordner ihres Erstelldatums, deshalb 8 Tage)."""
    ende = f"{s['id']}.jsonl"
    datei = next((p for p in quellen.rollout_dateien(ctx.k["daten"]["codex_sessions"], ctx.now)
                  if p.endswith(ende)), None)
    return quellen.codex_thread(datei) if datei else None


def _pruefen_rollout(ctx, s):
    """Außerhalb von Orca (codex queue): neue Aktivität in der rollout-Datei nach der Fortsetzung = arbeitet."""
    seit = s.get("status_seit") or ctx.now
    if s["anbieter"] == "codex":
        info = _codex_info(ctx, s)
        if info and (info.get("letzte_aktivitaet") or 0) > seit:
            _setze(s, "fortgesetzt", "Prüfung: arbeitet", geprueft=True)
            return
    if ctx.now - seit > 600:
        _setze(s, "fortgesetzt", "keine Aktivität nach Fortsetzung", geprueft=True)
        ctx.melder.senden(t("push_verloren", n=texte.NAME[s["anbieter"]]), prio=4,
                          schluessel=f"verloren:{s['id']}:{s.get('fenster_id')}")
