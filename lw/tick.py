"""Ein Durchlauf des Wächters (launchd alle 60 s): Daten -> Phasen -> Meldungen -> Aktionen."""

import time

from . import bericht, codex, fortsetzen, nacht, orte, phasen, quellen, register, sprache, texte, util, wach
from .sprache import t
from .orca import OrcaFehler
from . import nutzung  # v1.4 A

ZUSTAND = ("state", "zustand.json")
CURRENT = ("state", "current.json")
PAUSE = ("state", "pause.json")
PRIO = {"warnung": 3, "stopp": 4, "limit": 4}
TAGS = {"warnung": ["warning"], "stopp": ["octagonal_sign"], "limit": ["hourglass"]}


def pause_info(now):
    p = util.lies_json(util.pfad(*PAUSE), {}) or {}
    aktiv = bool(p.get("aktiv")) and (p.get("bis") is None or p["bis"] > now)
    return aktiv, p.get("bis")


def daten_sammeln(ctx, sim=None, abrufen=True):
    k, now = ctx.k, ctx.now
    vorhanden = ctx.orca_vorhanden()
    d = {"orca_ok": vorhanden, "orca_vorhanden": vorhanden, "fehler": []}
    if sim is not None:
        d.update(sim)
        if "rollouts" not in sim:
            d["rollouts"] = quellen.rollout_dateien(k["daten"]["codex_sessions"], now)
        return d
    lim = {}
    if vorhanden:                     # ohne Orca: kein Aufruf, kein Fehler, keine Log-Zeile (v1.3)
        try:
            lim = quellen.orca_limits(ctx.orca.konten())
        except OrcaFehler as e:
            d["orca_ok"] = False
            d["fehler"].append(str(e))
    rollouts = quellen.rollout_dateien(k["daten"]["codex_sessions"], now)
    roll = quellen.codex_nutzung(rollouts)
    d["rollouts"] = rollouts
    sl = quellen.claude_statusline(util.pfad(*quellen.STATUSLINE_DATEI))
    # v1.4 A: offizielle Nutzungsanzeige zuerst (gedrosselt abrufen; status liest nur den Zwischenspeicher)
    off = {"claude": None, "codex": None}
    if k["daten"].get("offiziell", True):
        if abrufen and not util.offline():
            nutzung.aktualisieren(k, util.lies_json(util.pfad(*ZUSTAND), {}) or {}, register.alle(), now)
        off = nutzung.lesen(k, now)
    max_alter = int(k["daten"].get("offiziell_max_alter_minuten", 10)) * 60
    # offizielle Quelle hat Vorrang, sonst frischester Stand, Gleichstand: Orca
    d["claude"] = phasen.waehle_quelle(off["claude"], lim.get("claude"), sl, now=now, max_alter_s=max_alter)
    d["claude_quellen"] = {"orca": (lim.get("claude") or {}).get("stand"), "statusline": (sl or {}).get("stand"),
                           "offiziell": (off["claude"] or {}).get("stand")}
    d["codex"] = phasen.waehle_quelle(off["codex"], lim.get("codex"), roll, now=now, max_alter_s=max_alter)
    d["offiziell"] = nutzung.info(k, now)
    if abrufen and k["daten"].get("offiziell", True):
        _hinweis_offiziell_fehlt(ctx, d["offiziell"])
    d["codex_credits"] = (roll or {}).get("credits")
    d["codex_reset_credits"] = (lim.get("codex") or {}).get("reset_credits")
    return d


def _hinweis_offiziell_fehlt(ctx, info):
    """Abgelaufene Anmeldung einmal je Ausfall melden, aber nur wenn eine Sitzung auf ein Reset wartet –
    genau dann hängen die Orca-Werte womöglich hinterher. Das Token wird nie selbst erneuert."""
    if not any(s.get("status") in register.WARTET for s in register.alle()):
        return
    cache = nutzung.cache_lesen()
    for anb in ("claude", "codex"):
        i = (info or {}).get(anb) or {}
        if i.get("fehler") != "abgelaufen":
            continue
        seit = int((cache.get(anb) or {}).get("fehler_seit") or 0)
        ctx.melder.senden(t("nz_push_abgelaufen", n=texte.NAME[anb]), prio=2, tags=["warning"],
                          schluessel=f"offiziell_abgelaufen:{anb}:{seit}")


FRUEH_VERTRAUT_S = 300          # statusline/rollout zählen fürs frühe Reset nur, wenn höchstens so alt


def _frueh_vertraut(d, now):
    """Nur verlässliche Quellen dürfen ein frühes Reset auslösen – nie Orca allein."""
    q = (d or {}).get("quelle")
    if q == "offiziell":
        return True
    return q in ("statusline", "rollout") and bool(d.get("stand")) and now - d["stand"] <= FRUEH_VERTRAUT_S


def _kurz_nutzung(d):
    f5, fw = d.get("fuenf") or {}, d.get("woche") or {}
    return {"pct5": f5.get("pct"), "reset5": f5.get("reset"), "pctw": fw.get("pct"), "resetw": fw.get("reset"),
            "quelle": d.get("quelle")}


def _nach_daten(ctx, daten, zustand, sitzungen):
    """v1.4 A: fruehes Reset erkennen. -> True, wenn Sitzungen geaendert wurden.

    Anthropic/OpenAI setzen Fenster gelegentlich vorzeitig zurück. Fällt der Füllstand eines noch laufenden
    Fensters deutlich oder rückt sein Reset nach vorn, werden wartende Sitzungen sofort fällig."""
    k, now = ctx.k, ctx.now
    abfall = k["daten"].get("frueh_reset_abfall", 20)
    puffer_s = k["fortsetzen"]["puffer_minuten"] * 60
    alt_alle = zustand.get("nutzung") or {}
    neu_alle = {}
    geaendert = False
    for anb in ("claude", "codex"):
        d = daten.get(anb)
        alt = alt_alle.get(anb) or {}
        if not d:
            if alt:
                neu_alle[anb] = alt
            continue
        neu = _kurz_nutzung(d)
        neu_alle[anb] = neu
        if not alt or not _frueh_vertraut(d, now):
            continue
        for art, pk, rk, stopp in (("fuenf", "pct5", "reset5", k["schwellen"]["stopp"]),
                                   ("woche", "pctw", "resetw", k["schwellen"]["woche_stopp"])):
            ar, nr, ap, np = alt.get(rk), neu.get(rk), alt.get(pk), neu.get(pk)
            if not ar or ar <= now + 300:          # altes Fenster endet ohnehin gleich: normales Reset
                continue
            if nr is not None and nr <= now:       # neue Angabe schon abgelaufen: unbrauchbar
                continue
            vorgezogen = bool(nr) and nr < ar - 600
            gefallen = ap is not None and np is not None and ap - np >= abfall and np < stopp
            if not (vorgezogen or gefallen):
                continue
            # Nur ein gesunkener Füllstand belegt, dass das Fenster schon zurückgesetzt ist. Rückt bloß das
            # Reset nach vorn, gilt das neue Reset samt Puffer (sonst Doppel-Fortsetzung mit Claudes eingebauter).
            sofort = gefallen or not nr
            ziel = now if sofort else nr + puffer_s
            for s in sitzungen:
                if s.get("anbieter") == anb and s.get("status") in register.WARTET \
                        and (s.get("art") or "fuenf") == art and (s.get("fortsetzen_ab") or 0) > ziel:
                    def aenderung(x, sofort=sofort, ziel=ziel, art=art):
                        x["fortsetzen_ab"] = ziel
                        x["reset"] = now if sofort else nr
                        if not sofort:
                            x["fenster_id"] = phasen.fenster_id(anb, art, nr)
                    register.aktualisieren(anb, s["id"], aenderung, "fruehes Reset" if sofort else "Reset vorgezogen")
                    geaendert = True
            util.ereignis("fruehes_reset", anbieter=anb, art=art, vorgezogen=not sofort)
            if sofort:
                util.log(t("nz_log_frueh", n=texte.NAME[anb], art=t("art_" + art)))
                ctx.melder.senden(t("nz_push_frueh", n=texte.NAME[anb], art=t("art_" + art)), prio=3,
                                  tags=["tada"], schluessel=f"frueh:{anb}:{art}:{int(ar)}")
            else:
                util.log(t("nz_log_vorgezogen", n=texte.NAME[anb], art=t("art_" + art),
                           zeit=util.uhrzeit(nr, now)))
    zustand["nutzung"] = neu_alle
    return geaendert


def limit_hinweise(sitzungen, now):
    h = {"claude": [], "codex": []}
    for s in sitzungen:
        if s.get("status") in ("limit", "eingebaut_wartet") and s.get("reset") and s["reset"] > now \
                and s.get("anbieter") in h:
            h[s["anbieter"]].append({"art": s.get("art") or "fuenf", "reset": s["reset"]})
    return h


def phasen_berechnen(k, daten, sitzungen, now):
    hinweise = limit_hinweise(sitzungen, now)
    return {a: phasen.berechne(a, daten.get(a), hinweise[a], k, now) for a in ("claude", "codex")}


def current_schreiben(k, ph, pausiert, now):
    util.schreib_json(util.pfad(*CURRENT), {
        "version": 1,
        "stand": now,
        "pausiert": pausiert,
        "puffer_s": k["fortsetzen"]["puffer_minuten"] * 60,
        "hook_max_alter_s": k["daten"]["hook_zustand_max_alter_minuten"] * 60,
        "reserve_sperre": bool(k["fortsetzen"]["reserve_sperrt_eingebaute_fortsetzung"]),
        "nur_nacht": bool(k["fortsetzen"]["aktiv"] and k["fortsetzen"]["nur_mit_nachtmodus"]),
        "nacht_ende": str(k["bericht"]["uhrzeit"]),
        "sprache": k["allgemein"]["sprache"],
        "nur_orca": bool(k["allgemein"].get("nur_orca")),
        "name": k["allgemein"]["name"],
        "claude": ph["claude"],
        "codex": ph["codex"],
    })


class _Mac:
    """mac_status nur bei Bedarf abfragen (vier kleine Systembefehle)."""

    def __init__(self, sim=None):
        self._wert = sim

    def __call__(self):
        if self._wert is None:
            self._wert = quellen.mac_status()
        return self._wert


def _remote_hinweis(mac):
    m = mac()
    if not m.get("netzteil"):
        return t("hinweis_kein_netzteil")
    if not m.get("wach_bei_deckel_zu"):
        return t("hinweis_remote_aus")
    return ""


def _nacht_hinweis(mac):
    m = mac()
    if not m.get("netzteil"):
        return t("nacht_kein_netzteil")
    if not m.get("wach_bei_deckel_zu"):
        return t("nacht_remote_aus")
    return ""


def _nacht(now):
    stunde = time.localtime(now).tm_hour
    return stunde >= 22 or stunde < 8


def _nacht_schluessel(now):
    """Eine Nacht (22–8 Uhr) bekommt einen gemeinsamen Schlüssel: Datum von now - 12 h."""
    return "remote:" + time.strftime("%Y-%m-%d", time.localtime(now - 12 * 3600))


def _meldungen_phasen(ctx, ph, zustand, sitzungen, mac):
    for anb in ("claude", "codex"):
        p = ph[anb]
        alt = zustand.get(anb) or {}
        wartend = sum(1 for s in sitzungen if s.get("anbieter") == anb and s.get("status") in register.WARTET)
        # im Push nur Sitzungen zählen, die wirklich automatisch fortgesetzt werden
        auto = sum(1 for s in sitzungen if s.get("anbieter") == anb and s.get("status") in register.WARTET
                   and _wird_fortgesetzt(ctx.k, s, ctx.now))
        if p["phase"] in PRIO and p["fenster_id"]:
            schluessel = f"{p['phase']}:{p['fenster_id']}"
            if not (p["phase"] == "warnung" and p["art"] == "woche" and p["reserve_erreicht"]) \
                    and not ctx.melder.bereits(schluessel):
                remote = _remote_hinweis(mac) if p["phase"] in ("stopp", "limit") and auto else ""
                if remote and _nacht(ctx.now):
                    ctx.melder.bereits_markieren(_nacht_schluessel(ctx.now))
                ctx.melder.senden(texte.push_phase(anb, p, auto, remote), prio=PRIO[p["phase"]],
                                  tags=TAGS[p["phase"]], schluessel=schluessel)
        if p["reserve_erreicht"] and p["resetw"]:
            ctx.melder.senden(t("push_reserve", n=texte.NAME[anb], pctw=sprache.prozent(p["pctw"]),
                                reset=util.uhrzeit(p["resetw"])), prio=4,
                              tags=["warning"],
                              schluessel=f"reserve:{phasen.fenster_id(anb, 'woche', p['resetw'])}")
        # auch "wartet auf weiter" zählt: dafür kommt ein eigener Push, kein zusätzliches "Limit zurückgesetzt"
        # (nur noch nicht gemeldete: alte, nie fortgesetzte Sitzungen dürfen den Reset-Push nicht dauerhaft sperren)
        weiter = sum(1 for s in sitzungen if s.get("anbieter") == anb and s.get("status") == "wartet_auf_weiter"
                     and s.get("weiter_gemeldet") is False)
        if alt.get("phase") in ("stopp", "limit") and p["phase"] in ("ok", "warnung") and not wartend \
                and not weiter \
                and alt.get("fenster_id") and alt.get("fenster_id") != p.get("fenster_id"):
            ctx.melder.senden(t("push_reset", n=texte.NAME[anb]), prio=2,
                              schluessel=f"reset:{alt['fenster_id']}")
        if alt.get("phase") != p["phase"]:
            util.log(t("log_phase", anb=anb, alt=alt.get("phase", "-"), neu=p["phase"],
                       stand=texte.stand(p) if p["reset"] else "-"))
            util.ereignis("phase", anbieter=anb, phase=p["phase"], pct=p["pct"], art=p["art"])
        zustand[anb] = {"phase": p["phase"], "fenster_id": p["fenster_id"]}


def _meldungen_geld(ctx, daten, zustand, sitzungen):
    neu = daten.get("codex_credits")
    alt = zustand.get("codex_credits")
    if neu is not None:
        if alt is not None and neu < alt - 0.01:
            ctx.melder.senden(t("push_credits", alt=f"{alt:.2f}", neu=f"{neu:.2f}"), prio=4,
                              tags=["moneybag"], schluessel=f"credits:{neu:.2f}")
        zustand["codex_credits"] = neu
    neu = daten.get("codex_reset_credits")
    alt = zustand.get("codex_reset_credits")
    if neu is not None:
        if alt is not None and neu < alt:
            ctx.melder.senden(t("push_reset_credits", alt=alt, neu=neu), prio=4, tags=["moneybag"], schluessel=f"resetcredits:{neu}:{int(ctx.now // 86400)}")
        zustand["codex_reset_credits"] = neu
    for s in sitzungen:
        if s.get("ueberziehung"):
            ctx.melder.senden(t("push_ueberziehung"), prio=5,
                              tags=["rotating_light"], schluessel=f"ueberziehung:{s['id']}:{s.get('fenster_id')}")
        if s.get("wartet_auf_freigabe") and s.get("status") in ("fortgesetzt", "eingebaut_fortgesetzt") \
                and s["wartet_auf_freigabe"] >= (s.get("status_seit") or 0):
            ctx.melder.senden(t("push_freigabe", n=texte.NAME[s["anbieter"]]), prio=4,
                              schluessel=f"freigabe:{s['id']}:{s.get('fenster_id')}")


def _bericht(ctx, zustand):
    k, now = ctx.k, ctx.now
    h, m = (int(x) for x in str(k["bericht"]["uhrzeit"]).split(":"))
    lt = time.localtime(now)
    heute = time.strftime("%Y-%m-%d", lt)
    if "bericht_bis" not in zustand:          # erster Lauf: erster Bericht am nächsten Morgen
        zustand["bericht_bis"] = now
        if (lt.tm_hour, lt.tm_min) >= (h, m):
            zustand["bericht_tag"] = heute
        return
    if zustand.get("bericht_tag") == heute or (lt.tm_hour, lt.tm_min) < (h, m):
        return
    b = bericht.erstellen(zustand["bericht_bis"], now)
    if b["relevant"]:
        datei = bericht.speichern(b["text"], now)
        ctx.aktion(t("aktion_bericht", datei=datei))
        ctx.melder.senden(t("push_morgenbericht", kurz=b["kurz"]), prio=2, tags=["sunrise"])
    zustand["bericht_tag"] = heute
    zustand["bericht_bis"] = now


def _nur_nacht(k):
    return bool(k["fortsetzen"]["nur_mit_nachtmodus"])


def _auf_weiter_setzen(s):
    """Ohne Nachtmodus: nichts senden, nur vermerken (der Nutzer tippt selbst "weiter")."""
    fortsetzen.auf_weiter_setzen(s)


def _weiter_melden(ctx):
    """Je Anbieter ein Push für alle noch nicht gemeldeten Sitzungen im Status wartet_auf_weiter.
    Zurückhalten, solange eine weitere Sitzung desselben Anbieters in den nächsten 3 Minuten fällig wird."""
    now = ctx.now
    alle = register.alle()
    for anb in ("claude", "codex"):
        offen = [s for s in alle if s.get("anbieter") == anb and s.get("status") == "wartet_auf_weiter"
                 and s.get("weiter_gemeldet") is False]
        if not offen:
            continue
        if any(s.get("anbieter") == anb and s.get("status") in register.WARTET
               and now < (s.get("fortsetzen_ab") or 0) <= now + 180 for s in alle):
            continue
        text = t("push_wartet_auf_weiter", n=texte.NAME[anb], anzahl=len(offen))
        befehle = [orte.kopierbefehl(s) for s in offen if orte.ort(s) != "orca"]
        if befehle:                  # außerhalb von Orca: Kopierbefehl anhängen (höchstens zwei, kurz halten)
            text += "\n" + t("push_weiter_befehl", n=texte.NAME[anb],
                             befehl=" / ".join(befehle[:2]) + (" …" if len(befehle) > 2 else ""))
        ctx.melder.senden(text,
                          prio=2 if _nacht(now) else 3, tags=["hand"])
        for s in offen:
            register.aktualisieren(anb, s["id"], lambda d: d.update(weiter_gemeldet=True))


def _nachholen(k, sitzungen, now):
    """Nachtmodus nach dem Reset eingeschaltet: wartende Sitzungen wieder in die Fortsetzung geben
    (gleiches Fenster, gleiche Versuchszählung, gleiche Bildschirmprüfung). -> True, wenn etwas geändert wurde."""
    geaendert = False
    for s in sitzungen:
        if nacht.nachholbar(s, now, k["wach"]["max_stunden_voraus"]):
            def aenderung(d):
                d["status"] = "gestoppt"
                d["fortsetzen_ab"] = now
                d.pop("weiter_gemeldet", None)
            register.aktualisieren(s["anbieter"], s["id"], aenderung, "Nachtmodus nachträglich an")
            geaendert = True
    return geaendert


def _wird_fortgesetzt(k, s, now):
    """Würde diese wartende Sitzung beim Reset automatisch fortgesetzt (für Wachhalten/Remote-Hinweis)?"""
    if orte.ort(s) != "orca" and orte.faehigkeiten(s, k)["fortsetzen"] != "ja":
        return False                 # außerhalb von Orca ohne eigene Fortsetzung (nur Push): nicht wachhalten
    if not _nur_nacht(k):
        return True
    b = nacht.bis(s, now)
    return bool(b and b > (s.get("fortsetzen_ab") or 0))


def _wach_halten(ctx, mac, pausiert):
    """v1.4 C: Mac wach halten, solange eine Fortsetzung ansteht oder der Nachtmodus aktiv ist
    (caffeinate, eigene Amphetamine-Sitzung falls freigegeben); nachts einmal warnen, falls er zugeklappt schliefe."""
    k, now = ctx.k, ctx.now
    w = k["wach"]
    if pausiert:
        for text in wach.automatisch(ctx, None, now):
            ctx.aktion(text)
        return
    wartend = [s for s in register.alle() if s.get("status") in register.WARTET and s.get("fortsetzen_ab")
               and _wird_fortgesetzt(k, s, now)]
    grenze = now + w["max_stunden_voraus"] * 3600
    naechste = [max(s["fortsetzen_ab"], now) for s in wartend if s["fortsetzen_ab"] <= grenze]
    bedarf_bis = max(naechste) + w["nachlauf_minuten"] * 60 if naechste else None
    if w.get("bei_nachtmodus", True):
        # Nachtmodus: global oder eine nicht beendete Sitzung der letzten 2 Tage
        nb = [nacht.global_bis(now) or 0] + [nacht.bis(s, now) or 0 for s in register.alle()
                                              if s.get("status") != "beendet"
                                              and now - (s.get("zuletzt") or 0) < 2 * 86400]
        if max(nb):
            bedarf_bis = max(bedarf_bis or 0, max(nb))
    if bedarf_bis:
        bedarf_bis = min(bedarf_bis, grenze)
    for text in wach.automatisch(ctx, bedarf_bis, now):
        ctx.aktion(text)
    wach.probe(ctx, now)
    if naechste and w["remote_modus_pruefen"] and _nacht(now) and not ctx.melder.bereits(_nacht_schluessel(now)):
        if mac().get("netzteil") and wach.haelt_zugeklappt(k, now):
            return                   # am Netzteil und selbst zugeklappt wach gehalten: nichts zu tun
        hinweis = _nacht_hinweis(mac)
        if hinweis:
            befehl = wach.hinweis_befehl(k)
            aktion = t("nacht_aktion_befehl", befehl=befehl)
            ctx.melder.senden(t("push_remote_nacht", hinweis=hinweis, zeit=util.uhrzeit(min(naechste)),
                                aktion=aktion), prio=4,
                              tags=["electric_plug"], schluessel=_nacht_schluessel(now))


def ausfuehren(ctx, sim=None, mac_sim=None):
    """Kern eines Ticks. sim: vorgegebene Nutzungsdaten (Simulation/Tests)."""
    k, now = ctx.k, ctx.now
    pausiert, _ = pause_info(now)
    ctx.melder.still = ctx.melder.still or pausiert
    mac = _Mac(mac_sim)
    zustand = util.lies_json(util.pfad(*ZUSTAND), {}) or {}

    daten = daten_sammeln(ctx, sim)
    if not daten["orca_ok"] and daten.get("fehler"):
        ctx.orca_fehler = "; ".join(daten["fehler"])
    sitzungen = register.alle()
    if _nach_daten(ctx, daten, zustand, sitzungen):
        sitzungen = register.alle()
    ph = phasen_berechnen(k, daten, sitzungen, now)
    current_schreiben(k, ph, pausiert, now)

    if not pausiert:
        codex.verwalten(ctx, ph["codex"], daten.get("rollouts") or [], daten["orca_ok"])
        sitzungen = register.alle()
        if k["fortsetzen"]["aktiv"] and _nachholen(k, sitzungen, now):
            sitzungen = register.alle()
        ph = phasen_berechnen(k, daten, sitzungen, now)   # Codex-Limits aus rollouts einbeziehen
        current_schreiben(k, ph, pausiert, now)
    _meldungen_phasen(ctx, ph, zustand, sitzungen, mac)
    _meldungen_geld(ctx, daten, zustand, sitzungen)

    wartend = [s for s in sitzungen if s.get("status") in register.WARTET and s.get("fortsetzen_ab")]
    if not pausiert:
        if not daten["orca_ok"] and daten.get("orca_vorhanden", True) \
                and any(orte.ort(s) == "orca" for s in wartend):
            ctx.melder.senden(t("push_orca_weg"), prio=4,
                              schluessel=f"orca-weg:{int(now // 3600)}")
        if k["fortsetzen"]["aktiv"]:
            faellige = []
            for s in sorted(wartend, key=lambda s: s.get("fortsetzen_ab") or 0):
                if _nur_nacht(k) and s["fortsetzen_ab"] <= now \
                        and ph[s["anbieter"]]["phase"] not in ("stopp", "limit") and not nacht.aktiv(s, now) \
                        and not (ph[s["anbieter"]].get("reserve_erreicht") or s.get("reserve_bei_halt")):
                    _auf_weiter_setzen(s)
                    continue
                ok, grund = fortsetzen.faellig(s, ph[s["anbieter"]], k, now)
                if ok:
                    faellige.append(s)
            ergebnisse = {}
            for s in faellige[:k["fortsetzen"]["pro_tick"]]:
                erg = fortsetzen.bearbeiten(ctx, s, ph[s["anbieter"]])
                if erg in ("fortgesetzt", "neu"):
                    ergebnisse[s["anbieter"]] = ergebnisse.get(s["anbieter"], 0) + 1
            if len(faellige) > k["fortsetzen"]["pro_tick"]:
                util.log(t("log_weitere", anzahl=len(faellige) - k["fortsetzen"]["pro_tick"]))
            for anb, n in ergebnisse.items():
                ctx.melder.senden(t("push_fortgesetzt", n=texte.NAME[anb], anzahl=n), prio=2 if _nacht(now) else 3,
                                  tags=["arrow_forward"])
            _weiter_melden(ctx)
            for s in register.alle():
                if s.get("status") == "fortgesetzt" and s.get("geprueft") is False \
                        and (s.get("pruefen_ab") or now + 1) <= now:
                    fortsetzen.pruefen(ctx, s)

        _bericht(ctx, zustand)
    _wach_halten(ctx, mac, pausiert)

    zustand["letzter_tick"] = now
    if now - zustand.get("letztes_lebenszeichen", 0) > 1800:
        zustand["letztes_lebenszeichen"] = now
        util.log("tick: " + "; ".join(f"{a} {ph[a]['phase']} {ph[a]['pct5']:.0f}%/{ph[a]['pctw']:.0f}%"
                                       for a in ("claude", "codex")) + (t("log_pausiert") if pausiert else ""))
    util.schreib_json(util.pfad(*ZUSTAND), zustand)
    return {"phasen": ph, "aktionen": ctx.aktionen, "meldungen": ctx.melder.protokoll, "pausiert": pausiert,
            "orca_ok": daten["orca_ok"]}
