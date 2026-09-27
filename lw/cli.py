"""Kommandozeile / command line: waechter.py status | tick | simulate | pause | report | ntfy-setup | test-push

Deutsche und englische Befehlsnamen funktionieren beide (z. B. `pause aus` = `pause off`).
"""

import argparse
import json
import os
import secrets
import string
import subprocess
import sys
import time
import traceback

from . import (VERSION, bericht, installer, konfig, melden, nacht, orte, quellen, register, simulation, sprache,
               tick, util, wach)
from .kontext import Kontext
from .orca import Orca
from .sprache import t

NAME = {"claude": "Claude", "codex": "Codex"}
AUS = ("aus", "off", "ende", "end", "stop")
SIM_ALIAS = {"cycle": "zyklus", "off": "aus"}

# v1.4 Erweiterungspunkte: Umsetzer registrieren Funktionen NUR in ihren Markerbloecken am Dateiende.
STATUS_JSON_ZUSATZ = []   # f(ausgabe: dict, k, now, daten, sitzungen) -> None   (Gesamtausgabe status --json)
SITZUNG_JSON_ZUSATZ = []  # f(eintrag: dict, x: dict, k, now) -> None            (je Sitzung in status --json)
STATUS_TEXT_ZUSATZ = []   # f(k, now, daten) -> [str]                            (Zeilen vor st_log in der Textausgabe)
PARSER_ZUSATZ = []        # f(sub) -> str|None  registriert Unterbefehl, gibt Anzeigenamen fuer die Befehlsliste zurueck


def _launchagent_geladen(label):
    try:
        r = subprocess.run(["/bin/launchctl", "print", f"gui/{os.getuid()}/{label}"], capture_output=True,
                           text=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _fenster_text(pct, reset, now):
    return t("st_fenster", pct=sprache.prozent(pct), reset=util.uhrzeit(reset, now)) if reset else "  – "


def zustand_text(status):
    return t("z_" + status) if ("z_" + str(status)) in sprache.TEXTE else str(status)


def _ja(wert, gross=False):
    return t("ja") if wert else t("NEIN" if gross else "nein")


SCHWELLEN = ("warnung", "stopp", "woche_warnung", "woche_stopp", "wochen_reserve")
SCHWELLEN_ALIAS = {"warn": "warnung", "stop": "stopp", "weekly_warn": "woche_warnung", "weekly_stop": "woche_stopp",
                   "weekly_reserve": "wochen_reserve"}
APP_PRAEFIXE = ("app_", "phase_", "z_")


def _projekt(x):
    ordner = (x.get("cwd") or x.get("worktree") or "").rstrip("/")
    return os.path.basename(ordner) or None


CLAUDE_SETTINGS = "~/.claude/settings.json"


def statusline_info(settings_pfad=None):
    """-> {'zustand': 'aktiv'|'zurueckgeschrieben'|'aus', 'stand': epoch|None}; settings.json wird nur gelesen.
    Pfad per Parameter oder LIMIT_WAECHTER_CLAUDE_SETTINGS (Tests), sonst ~/.claude/settings.json."""
    pfad = settings_pfad or os.environ.get("LIMIT_WAECHTER_CLAUDE_SETTINGS") or os.path.expanduser(CLAUDE_SETTINGS)
    settings = util.lies_json(pfad, {})
    if not isinstance(settings, dict):
        settings = {}
    sl = quellen.claude_statusline(util.pfad(*quellen.STATUSLINE_DATEI))
    return {"zustand": installer.statusline_zustand(settings), "stand": (sl or {}).get("stand")}


def _orca_vorhanden(k, daten, orca):
    if "orca_vorhanden" in daten:
        return bool(daten["orca_vorhanden"])
    if hasattr(orca, "vorhanden"):
        return bool(orca.vorhanden())
    return os.access(k["daten"]["orca"], os.X_OK)


def automatisch(x, k, now, orca_ok=True):
    """Wird diese wartende Sitzung nach dem Reset automatisch fortgesetzt (für die Anzeige)?
    Außerhalb von Orca nur Codex per codex queue oder Claudes eingebaute Fortsetzung am harten Limit."""
    f = orte.faehigkeiten(x, k, orca_ok)["fortsetzen"]
    eingebaut = x.get("anbieter") == "claude" and x.get("status") in ("limit", "eingebaut_wartet")
    if f != "ja" and not (f == "push" and eingebaut):
        return False
    nb = nacht.bis(x, now)
    return bool(not k["fortsetzen"]["nur_mit_nachtmodus"] or (nb and nb > (x.get("fortsetzen_ab") or 0)))


def faehigkeiten_text(f):
    teile = [t("f_warnt"), t("f_stoppt" if f["stoppen"] == "ja" else "f_stoppt_nicht"),
             t({"ja": "f_setzt_fort", "push": "f_nur_push"}.get(f["fortsetzen"], "f_kein_fortsetzen"))]
    return t("f_trenner").join(teile)


def _statusline_zeile(sl, now):
    if sl["zustand"] == "aktiv":
        return (t("st_sl_aktiv", dauer=util.dauer_text(now - sl["stand"])) if sl["stand"]
                else t("st_sl_aktiv_leer"))
    return t("st_sl_zurueck" if sl["zustand"] == "zurueckgeschrieben" else "st_sl_aus")


def cmd_status(args, k):
    now = util.jetzt()
    orca = Orca(k["daten"]["orca"], dry_run=True)
    ctx = Kontext(k, orca, melden.Melder(k, dry_run=True), now, dry_run=True)
    daten = tick.daten_sammeln(ctx, abrufen=False)
    sitzungen = register.alle()
    ph = tick.phasen_berechnen(k, daten, sitzungen, now)
    zustand = util.lies_json(util.pfad(*tick.ZUSTAND), {}) or {}
    pausiert, pause_bis = tick.pause_info(now)
    geladen = _launchagent_geladen(k["allgemein"]["launchagent_label"])
    topic = melden.topic_vorhanden(k["melden"]["ntfy_dienst"])
    w = wach.zustand()
    orca_da = _orca_vorhanden(k, daten, orca)
    sl = statusline_info()
    if args.json:
        liste = []
        for x in sitzungen:
            f = orte.faehigkeiten(x, k, daten["orca_ok"])
            eintrag = dict(x, nacht_bis=nacht.bis(x, now), projekt=_projekt(x),
                           status_text=zustand_text(x.get("status")), wartet=x.get("status") in register.WARTET,
                           automatisch=automatisch(x, k, now, daten["orca_ok"]),
                           ort=orte.ort(x), ort_text=t("ort_" + orte.ort(x)), faehigkeiten=f,
                           faehigkeiten_text=faehigkeiten_text(f))
            for fz in SITZUNG_JSON_ZUSATZ:
                fz(eintrag, x, k, now)
            liste.append(eintrag)
        ausgabe = {"version": VERSION, "jetzt": now, "sprache": sprache.AKTUELL,
                   "phasen": ph, "pausiert": pausiert, "pause_bis": pause_bis,
                   "letzter_tick": zustand.get("letzter_tick"), "launchagent": geladen, "ntfy_topic": topic,
                   "orca_ok": daten["orca_ok"],
                   "orca_vorhanden": orca_da, "nur_orca": bool(k["allgemein"].get("nur_orca", False)),
                   "statusline": sl, "nacht": nacht.global_bis(now),
                   "nur_mit_nachtmodus": bool(k["fortsetzen"]["nur_mit_nachtmodus"]),
                   "bericht_uhrzeit": str(k["bericht"]["uhrzeit"]),
                   "schwellen": {n: k["schwellen"][n] for n in SCHWELLEN},
                   "sitzungen": liste}
        for fz in STATUS_JSON_ZUSATZ:
            fz(ausgabe, k, now, daten, sitzungen)
        print(json.dumps(ausgabe, ensure_ascii=False, indent=1))
        return 0
    print(t("st_kopf", version=VERSION, zeit=time.strftime("%d.%m. %H:%M", time.localtime(now))))
    letzter = zustand.get("letzter_tick")
    lauf = t("st_letzter", dauer=util.dauer_text(now - letzter)) if letzter else t("st_kein_tick")
    if pausiert:
        pause = t("st_pausiert_bis", zeit=util.uhrzeit(pause_bis, now)) if pause_bis else t("st_pausiert")
    else:
        pause = t("st_aktiv")
    print(t("st_wachter", pause=pause, lauf=lauf, agent=t("st_geladen") if geladen else t("st_nicht_geladen")))
    gb = nacht.global_bis(now)
    print(t("n_global_an", zeit=util.uhrzeit(gb, now)) if gb else t("n_global_aus"))
    if not orca_da:
        print(t("st_orca_fehlt"))
    elif not daten["orca_ok"]:
        print(t("st_orca_weg", fehler="; ".join(daten["fehler"])[:120]))
    for a in ("claude", "codex"):
        p = ph[a]
        alter = (t("st_daten", dauer=util.dauer_text(p["alter"]), quelle=p["quelle"]) if p["alter"] is not None
                 else t("st_keine_daten"))
        print(t("st_zeile", name=NAME[a], f5=_fenster_text(p["pct5"], p["reset5"], now),
                fw=_fenster_text(p["pctw"], p["resetw"], now), phase=t("phase_" + p["phase"]), alter=alter)
              + (t("st_reserve") if p["reserve_erreicht"] else ""))
    print(_statusline_zeile(sl, now))
    s = k["schwellen"]
    print(t("st_schwellen", w=s["warnung"], s=s["stopp"], ww=s["woche_warnung"], ws=s["woche_stopp"],
            r=s["wochen_reserve"], ab=100 - s["wochen_reserve"]))
    frisch = [x for x in sitzungen if now - x.get("zuletzt", 0) < 2 * 86400 and x.get("status") != "beendet"]
    print(t("st_sitzungen", c=sum(1 for x in frisch if x["anbieter"] == "claude"),
            x=sum(1 for x in frisch if x["anbieter"] == "codex")))
    for x in sorted(frisch, key=lambda x: -x.get("zuletzt", 0)):
        if x.get("status") == "aktiv" and not args.alle:
            continue
        extra = ""
        nb = nacht.bis(x, now)
        if x.get("status") in register.WARTET and x.get("fortsetzen_ab"):
            extra = t("st_ab" if automatisch(x, k, now, daten["orca_ok"]) else "st_weiter_noetig", zeit=util.uhrzeit(x["fortsetzen_ab"], now))
        if nb:
            extra += t("st_nacht", zeit=util.uhrzeit(nb, now))
        print(f"  {x['anbieter']:6} {str(x['id'])[:8]} {t('ort_' + orte.ort(x))[:8]:8} "
              f"{os.path.basename(x.get('cwd') or '?')[:28]:28} "
              f"{zustand_text(x.get('status')):26}{extra}")
    if not any(x.get("status") != "aktiv" for x in frisch) and not args.alle:
        print(t("st_keine_wartet"))
    mac = quellen.mac_status()
    print(t("st_mac", ac=_ja(mac["netzteil"], True), schlaf=_ja(mac["schlaf_aus"]),
            deckel=_ja(mac["wach_bei_deckel_zu"], True), amph=_ja(mac["amphetamine"])))
    wach_text = t("st_caffeinate", zeit=util.uhrzeit(w.get("bis"), now)) if w.get("laeuft") else t("st_aus")
    print(t("st_ntfy", topic="✓" if topic else t("st_topic_fehlt"), wach=wach_text))
    for fz in STATUS_TEXT_ZUSATZ:
        for z in fz(k, now, daten):
            print(z)
    print(t("st_log", pfad=util.pfad("log", "waechter.log")))
    return 0


def cmd_tick(args, k):
    if args.dry_run:
        with simulation.sandbox(kopieren=True):
            now = util.jetzt()
            ctx = Kontext(k, Orca(k["daten"]["orca"], dry_run=True), melden.Melder(k, dry_run=True), now,
                          dry_run=True)
            erg = tick.ausfuehren(ctx)
            simulation._ausgabe(t("tick_dry"), erg, now)
        return 0
    try:
        with util.sperre(util.pfad("state", "tick"), warten=False):
            now = util.jetzt()
            ctx = Kontext(k, Orca(k["daten"]["orca"]), melden.Melder(k), now)
            try:
                erg = tick.ausfuehren(ctx)
            except Exception as e:
                zeilen = traceback.format_exc().strip().splitlines()
                util.log(t("log_tickfehler", typ=type(e).__name__, fehler=e,
                           spur=" | ".join(z.strip() for z in zeilen[-4:])))
                ctx.melder.senden(t("push_tickfehler", app=t("app")), prio=3,
                                  schluessel=f"tickfehler:{time.strftime('%Y-%m-%d', time.localtime(now))}")
                return 1
    except RuntimeError:
        util.log(t("log_tick_laeuft"))
        return 0
    if args.verbose:
        simulation._ausgabe("Tick", erg, now)
    return 0


def cmd_simulate(args, k):
    fall = SIM_ALIAS.get(args.fall, args.fall)
    if fall == "aus":
        simulation.aus()
        return 0
    if fall == "zyklus":
        simulation.zyklus()
        print("\n" + t("zyklus_fertig"))
        return 0
    if args.sitzung:
        if fall != "stop":
            print(t("nur_stop"))
            return 2
        simulation.scharf_eine_sitzung(args.sitzung, args.minuten)
        return 0
    simulation.jetzt_mit_werten(fall, args.anbieter)
    return 0


def cmd_pause(args, k):
    now = util.jetzt()
    if args.dauer in AUS:
        util.schreib_json(util.pfad(*tick.PAUSE), {"aktiv": False, "beendet": now})
        util.log(t("log_pause_ende"))
        print(t("pause_ende"))
        return 0
    bis = None
    if args.dauer:
        try:
            bis = now + util.parse_dauer(args.dauer)
        except ValueError:
            print(t("pause_dauer"))
            return 2
    util.schreib_json(util.pfad(*tick.PAUSE), {"aktiv": True, "seit": now, "bis": bis})
    util.log(t("log_pause", wie=t("pause_bis", zeit=util.uhrzeit(bis, now)) if bis else t("pause_ohne_ende")))
    print(t("pause_ok", wie=t("pause_bis", zeit=util.uhrzeit(bis, now)) if bis else t("pause_bis_aus")))
    return 0


def _sitzung_kurz(x):
    return f"{x['anbieter']} {str(x['id'])[:8]} ({os.path.basename((x.get('cwd') or '').rstrip('/')) or '?'})"


def _kandidaten(liste):
    for x in liste:
        print("  " + _sitzung_kurz(x))
    if not liste:
        print(t("n_keine_liste"))


def _hinweis_schon_wartend(liste, k, now):
    """Sitzungen, die schon auf „weiter“ warten, setzt der nächste Tick fort (tick._nachholen)."""
    liste = [x for x in liste if nacht.nachholbar(x, now, k["wach"]["max_stunden_voraus"])]
    if liste:
        print(t("n_schon_wartend", anzahl=len(liste)))
        for x in liste:
            print(f"  {_sitzung_kurz(x)}")


def cmd_nacht(args, k):
    now = util.jetzt()
    uhrzeit = str(k["bericht"]["uhrzeit"])
    aktion = (args.aktion or "status").lower()
    ziel = args.ziel
    if aktion == "status":
        gb = nacht.global_bis(now)
        print(t("n_global_an", zeit=util.uhrzeit(gb, now)) if gb else t("n_global_aus"))
        eigene = [x for x in register.alle() if x.get("status") != "beendet" and (x.get("nacht_bis") or 0) > now]
        print(t("n_sitzungen"))
        for x in eigene:
            print(f"  {_sitzung_kurz(x)}{t('st_nacht', zeit=util.uhrzeit(x['nacht_bis'], now))}")
        if not eigene:
            print(t("n_keine_liste"))
        if not k["fortsetzen"]["nur_mit_nachtmodus"]:
            print(t("n_nur_nacht_aus"))
        return 0
    if aktion not in nacht.AN + nacht.AUS:
        print(t("n_aktion", aktion=aktion))
        return 2
    an = aktion in nacht.AN
    if not ziel or ziel.lower() in nacht.ALLE:
        if an:
            print(t("n_an_alle", zeit=util.uhrzeit(nacht.alle_an(now, uhrzeit), now)))
            _hinweis_schon_wartend(register.alle(), k, now)
        else:
            nacht.alle_aus(now)
            for x in register.alle():
                if x.get("nacht_bis"):
                    nacht.sitzung_aus(x["anbieter"], x["id"], now)
            print(t("n_aus_alle"))
        return 0
    treffer = nacht.finden(ziel, now)
    if len(treffer) != 1:
        print(t("n_mehrdeutig" if treffer else "n_keine", ziel=ziel))
        _kandidaten(treffer or [x for x in register.alle() if x.get("status") != "beendet"
                                and now - (x.get("zuletzt") or 0) < 2 * 86400])
        return 2
    x = treffer[0]
    if an:
        b = nacht.sitzung_an(x["anbieter"], x["id"], now, uhrzeit)
        print(t("n_an", sitzung=_sitzung_kurz(x), zeit=util.uhrzeit(b, now)))
        _hinweis_schon_wartend([register.lesen(x["anbieter"], x["id"]) or x], k, now)
    else:
        nacht.sitzung_aus(x["anbieter"], x["id"], now)
        print(t("n_aus", sitzung=_sitzung_kurz(x)))
        gb = nacht.global_bis(now)
        if gb:
            print(t("n_global_noch", zeit=util.uhrzeit(gb, now)))
    return 0


def cmd_report(args, k):
    now = util.jetzt()
    print(bericht.erstellen(now - args.stunden * 3600, now)["text"])
    return 0


def cmd_ntfy_einrichten(args, k):
    dienst = k["melden"]["ntfy_dienst"]
    if melden.topic_vorhanden(dienst):
        print(t("ntfy_schon", dienst=dienst))
        return 0
    zeichen = string.ascii_lowercase + string.digits
    topic = "lw-" + "".join(secrets.choice(zeichen) for _ in range(24))
    r = subprocess.run(["/usr/bin/security", "add-generic-password", "-s", dienst, "-a", "limit-waechter",
                        "-l", t("ntfy_label"), "-w", topic], capture_output=True, text=True)
    del topic
    if r.returncode != 0:
        print(t("ntfy_fehler"))
        return 1
    print(t("ntfy_neu", dienst=dienst))
    return 0


def cmd_ntfy_abo(args, k):
    topic = melden.topic_lesen(k["melden"]["ntfy_dienst"])
    if not topic:
        print(t("ntfy_keins"))
        return 1
    subprocess.run(["/usr/bin/pbcopy"], input=topic, text=True)
    del topic
    print(t("ntfy_abo_1"))
    print(t("ntfy_abo_2"))
    return 0


def cmd_test_push(args, k):
    melden.Melder(k).senden(t("push_test"), prio=3, tags=["white_check_mark"])
    print(t("test_ok"))
    return 0


def cmd_konfig_wert(args, k):
    """Für install.sh/uninstall.sh: einzelnen Konfigurationswert ausgeben."""
    print(konfig.wert(k, args.schluessel))
    return 0


def _schwellen_ausgabe(s, als_json):
    if als_json:
        print(json.dumps({"ok": True, "schwellen": s}, ensure_ascii=False))
    else:
        for n in SCHWELLEN:
            print(t("sw_zeile", name=n, wert=s[n]))


def cmd_schwellen(args, k):
    aktuell = {n: k["schwellen"][n] for n in SCHWELLEN}
    aktion = (args.aktion or "").lower()
    if not aktion:
        _schwellen_ausgabe(aktuell, args.json)
        return 0
    fehler, werte = [], {}
    if aktion not in ("setzen", "set"):
        fehler.append(t("sw_aktion", aktion=aktion))
    elif not args.werte:
        fehler.append(t("sw_leer"))
    for teil in args.werte if not fehler else []:
        if "=" not in teil:
            fehler.append(t("sw_format", teil=teil))
            continue
        name, roh = (x.strip() for x in teil.split("=", 1))
        name = SCHWELLEN_ALIAS.get(name.lower(), name.lower())
        if name not in SCHWELLEN:
            fehler.append(t("sw_schluessel", name=name))
            continue
        grenzen = (0, 50) if name == "wochen_reserve" else (1, 99)
        try:
            zahl = int(roh)
        except ValueError:
            zahl = None
        if zahl is None or not grenzen[0] <= zahl <= grenzen[1]:
            fehler.append(t("sw_zahl", name=name, min=grenzen[0], max=grenzen[1]))
            continue
        werte[name] = zahl
    if not fehler:
        probe = {a: dict(v) if isinstance(v, dict) else v for a, v in k.items()}
        probe["schwellen"].update(werte)
        fehler = konfig.pruefen(probe)
    if fehler:
        if args.json:
            print(json.dumps({"ok": False, "fehler": fehler}, ensure_ascii=False))
        else:
            print(t("sw_fehler", fehler="; ".join(fehler)))
        return 2
    datei = konfig.lokal_setzen("schwellen", werte)
    aktuell.update(werte)
    if not args.json:
        print(t("sw_gespeichert", datei=datei))
    _schwellen_ausgabe(aktuell, args.json)
    return 0


def cmd_app_texte(args, k):
    texte = {n: (e.get(sprache.AKTUELL) or e["en"]) for n, e in sprache.TEXTE.items() if n.startswith(APP_PRAEFIXE)}
    print(json.dumps({"sprache": sprache.AKTUELL, "texte": texte}, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


def _namen(de, en):
    """Hauptname je nach Sprache, der andere als Alias."""
    return (de, [en]) if sprache.AKTUELL == "de" else (en, [de])


def main(argv=None):
    k = konfig.laden()
    ap = argparse.ArgumentParser(prog="waechter.py", description=t("cli_beschreibung"))
    liste = ["status", "tick", "simulate", "pause", _namen("nacht", "night")[0], _namen("weiter", "resume")[0], "report",
             _namen("schwellen", "thresholds")[0], _namen("ntfy-einrichten", "ntfy-setup")[0],
             _namen("ntfy-abo", "ntfy-subscribe")[0], "test-push"]
    sub = ap.add_subparsers(dest="befehl", required=True)
    p = sub.add_parser("status", help=t("h_status"))
    p.add_argument("--json", action="store_true")
    p.add_argument("--alle", "--all", dest="alle", action="store_true", help=t("h_alle"))
    p.set_defaults(f=cmd_status)
    p = sub.add_parser("tick", help=t("h_tick"))
    p.add_argument("--dry-run", action="store_true", help=t("h_dry"))
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(f=cmd_tick)
    p = sub.add_parser("simulate", help=t("h_simulate"))
    p.add_argument("fall", choices=["warn", "stop", "limit", "reset", "zyklus", "cycle", "aus", "off"])
    p.add_argument("--anbieter", "--provider", dest="anbieter", choices=["claude", "codex"], default="claude")
    p.add_argument("--sitzung", "--session", dest="sitzung", help=t("h_sitzung"))
    p.add_argument("--minuten", "--minutes", dest="minuten", type=int, default=10)
    p.set_defaults(f=cmd_simulate)
    p = sub.add_parser("pause", help=t("h_pause"))
    p.add_argument("dauer", nargs="?")
    p.set_defaults(f=cmd_pause)
    name, alias = _namen("weiter", "resume")
    p = sub.add_parser(name, aliases=alias, help=t("h_weiter"))
    p.set_defaults(f=lambda a, k: cmd_pause(argparse.Namespace(dauer="aus"), k))
    name, alias = _namen("nacht", "night")
    p = sub.add_parser(name, aliases=alias, help=t("h_nacht"))
    p.add_argument("aktion", nargs="?", metavar=t("n_meta_aktion"), help=t("n_hilfe_aktion"))
    p.add_argument("ziel", nargs="?", metavar=t("n_meta_ziel"), help=t("n_hilfe_ziel"))
    p.set_defaults(f=cmd_nacht)
    p = sub.add_parser("report", help=t("h_report"))
    p.add_argument("--stunden", "--hours", dest="stunden", type=float, default=24)
    p.set_defaults(f=cmd_report)
    name, alias = _namen("schwellen", "thresholds")
    p = sub.add_parser(name, aliases=alias, help=t("h_schwellen"))
    p.add_argument("aktion", nargs="?")
    p.add_argument("werte", nargs="*")
    p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_schwellen)
    name, alias = _namen("ntfy-einrichten", "ntfy-setup")
    p = sub.add_parser(name, aliases=alias, help=t("h_ntfy_setup"))
    p.set_defaults(f=cmd_ntfy_einrichten)
    name, alias = _namen("ntfy-abo", "ntfy-subscribe")
    p = sub.add_parser(name, aliases=alias, help=t("h_ntfy_abo"))
    p.set_defaults(f=cmd_ntfy_abo)
    p = sub.add_parser("test-push", help=t("h_test_push"))
    p.set_defaults(f=cmd_test_push)
    p = sub.add_parser("config-get", aliases=["konfig-wert"])
    p.add_argument("schluessel")
    p.set_defaults(f=cmd_konfig_wert)
    p = sub.add_parser("app-texte", aliases=["app-texts"])
    p.set_defaults(f=cmd_app_texte)
    for f in PARSER_ZUSATZ:
        n = f(sub)
        if n:
            liste.append(n)
    sub.metavar = "{" + ",".join(liste) + "}"
    args = ap.parse_args(argv)
    return args.f(args, k)


# ======== v1.4 A (Fuellstand) – nur zwischen diesen Zeilen einfuegen ========

# ======== v1.4 A Ende ========

# ======== v1.4 B (Fortsetzen) – nur zwischen diesen Zeilen einfuegen ========

# ======== v1.4 B Ende ========

# ======== v1.4 C (Wach-Modus) – nur zwischen diesen Zeilen einfuegen ========
def cmd_wach(args, k):
    """wach an|aus|status (en: awake on|off|status) – ersetzt das frühere remote.sh."""
    now = util.jetzt()
    aktion = (args.aktion or "status").lower()
    if aktion in wach.AN:
        erg = wach.wach_an(k, now)
    elif aktion in wach.AUS:
        erg = wach.wach_aus(k, now)
    elif aktion in wach.STATUS:
        erg = {"ok": True, "fehler": None, "text": None}
    else:
        if args.json:
            print(json.dumps({"ok": False, "fehler": "aktion", "text": t("wm_aktion", aktion=aktion),
                              "wach": None}, ensure_ascii=False))
        else:
            print(t("wm_aktion", aktion=aktion))
        return 2
    block = wach.status_block(k, util.jetzt())
    if args.json:
        print(json.dumps({"ok": bool(erg["ok"]), "fehler": erg["fehler"], "text": erg["text"], "wach": block},
                         ensure_ascii=False, indent=1))
    else:
        if erg["text"]:
            print(erg["text"])
        for z in _wach_zeilen(k, block):
            print(z)
    return 0 if erg["ok"] else 1


def _wach_zeilen(k, block):
    return [t("wm_st_zeile", text=block["text"], sperre=wach.sperre_text(block["sperre"]),
              amph=t("wm_amph_" + block["amphetamine"]))]


def _parser_wach(sub):
    name, alias = _namen("wach", "awake")
    p = sub.add_parser(name, aliases=alias, help=t("wm_hilfe"))
    p.add_argument("aktion", nargs="?", metavar=t("wm_meta_aktion"))
    p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_wach)
    return name


def _status_json_wach(ausgabe, k, now, daten, sitzungen):
    ausgabe["wach"] = wach.status_block(k, now)


def _status_text_wach(k, now, daten):
    return _wach_zeilen(k, wach.status_block(k, now))


PARSER_ZUSATZ.append(_parser_wach)
STATUS_JSON_ZUSATZ.append(_status_json_wach)
STATUS_TEXT_ZUSATZ.append(_status_text_wach)

# ======== v1.4 C Ende ========

# ======== v1.4 D (App) – nur zwischen diesen Zeilen einfuegen ========

# ======== v1.4 D Ende ========


if __name__ == "__main__":
    sys.exit(main())
