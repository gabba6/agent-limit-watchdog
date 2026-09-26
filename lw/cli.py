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

from . import VERSION, bericht, konfig, melden, quellen, register, simulation, sprache, tick, util, wach
from .kontext import Kontext
from .orca import Orca
from .sprache import t

NAME = {"claude": "Claude", "codex": "Codex"}
AUS = ("aus", "off", "ende", "end", "stop")
SIM_ALIAS = {"cycle": "zyklus", "off": "aus"}


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


def cmd_status(args, k):
    now = util.jetzt()
    orca = Orca(k["daten"]["orca"], dry_run=True)
    ctx = Kontext(k, orca, melden.Melder(k, dry_run=True), now, dry_run=True)
    daten = tick.daten_sammeln(ctx)
    sitzungen = register.alle()
    ph = tick.phasen_berechnen(k, daten, sitzungen, now)
    zustand = util.lies_json(util.pfad(*tick.ZUSTAND), {}) or {}
    pausiert, pause_bis = tick.pause_info(now)
    geladen = _launchagent_geladen(k["allgemein"]["launchagent_label"])
    topic = melden.topic_vorhanden(k["melden"]["ntfy_dienst"])
    w = wach.zustand()
    if args.json:
        print(json.dumps({"phasen": ph, "pausiert": pausiert, "launchagent": geladen, "ntfy_topic": topic,
                          "orca_ok": daten["orca_ok"], "sitzungen": sitzungen}, ensure_ascii=False, indent=1))
        return 0
    print(t("st_kopf", version=VERSION, zeit=time.strftime("%d.%m. %H:%M", time.localtime(now))))
    letzter = zustand.get("letzter_tick")
    lauf = t("st_letzter", dauer=util.dauer_text(now - letzter)) if letzter else t("st_kein_tick")
    if pausiert:
        pause = t("st_pausiert_bis", zeit=util.uhrzeit(pause_bis, now)) if pause_bis else t("st_pausiert")
    else:
        pause = t("st_aktiv")
    print(t("st_wachter", pause=pause, lauf=lauf, agent=t("st_geladen") if geladen else t("st_nicht_geladen")))
    if not daten["orca_ok"]:
        print(t("st_orca_weg", fehler="; ".join(daten["fehler"])[:120]))
    for a in ("claude", "codex"):
        p = ph[a]
        alter = (t("st_daten", dauer=util.dauer_text(p["alter"]), quelle=p["quelle"]) if p["alter"] is not None
                 else t("st_keine_daten"))
        print(t("st_zeile", name=NAME[a], f5=_fenster_text(p["pct5"], p["reset5"], now),
                fw=_fenster_text(p["pctw"], p["resetw"], now), phase=t("phase_" + p["phase"]), alter=alter)
              + (t("st_reserve") if p["reserve_erreicht"] else ""))
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
        if x.get("status") in register.WARTET and x.get("fortsetzen_ab"):
            extra = t("st_ab", zeit=util.uhrzeit(x["fortsetzen_ab"], now))
        print(f"  {x['anbieter']:6} {str(x['id'])[:8]} {os.path.basename(x.get('cwd') or '?')[:28]:28} "
              f"{zustand_text(x.get('status')):26}{extra}")
    if not any(x.get("status") != "aktiv" for x in frisch) and not args.alle:
        print(t("st_keine_wartet"))
    mac = quellen.mac_status()
    print(t("st_mac", ac=_ja(mac["netzteil"], True), schlaf=_ja(mac["schlaf_aus"]),
            deckel=_ja(mac["wach_bei_deckel_zu"], True), amph=_ja(mac["amphetamine"])))
    wach_text = t("st_caffeinate", zeit=util.uhrzeit(w.get("bis"), now)) if w.get("laeuft") else t("st_aus")
    print(t("st_ntfy", topic="✓" if topic else t("st_topic_fehlt"), wach=wach_text))
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


def _namen(de, en):
    """Hauptname je nach Sprache, der andere als Alias."""
    return (de, [en]) if sprache.AKTUELL == "de" else (en, [de])


def main(argv=None):
    k = konfig.laden()
    ap = argparse.ArgumentParser(prog="waechter.py", description=t("cli_beschreibung"))
    liste = ["status", "tick", "simulate", "pause", _namen("weiter", "resume")[0], "report",
             _namen("ntfy-einrichten", "ntfy-setup")[0], _namen("ntfy-abo", "ntfy-subscribe")[0], "test-push"]
    sub = ap.add_subparsers(dest="befehl", required=True, metavar="{" + ",".join(liste) + "}")
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
    p = sub.add_parser("report", help=t("h_report"))
    p.add_argument("--stunden", "--hours", dest="stunden", type=float, default=24)
    p.set_defaults(f=cmd_report)
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
    args = ap.parse_args(argv)
    return args.f(args, k)


if __name__ == "__main__":
    sys.exit(main())
