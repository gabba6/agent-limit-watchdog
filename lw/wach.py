"""Mac wach halten (v1.4: Wach-Modus, ersetzt das frühere Skript remote.sh).

Zwei Wege:
  automatisch  (nur der Tick, ohne Passwort): solange eine Fortsetzung ansteht oder der Nachtmodus aktiv ist,
               caffeinate -i -s (wie bisher, wirkt nur am Netzteil) und – falls Amphetamine installiert ist und
               die Automation erlaubt wurde – eine eigene, befristete Amphetamine-Sitzung mit „closed display
               mode“ (wach auch zugeklappt). Beendet werden nur selbst gestartete Sitzungen.
  manuell      `waechter.py wach an|aus` (en: awake on|off): Passwortdialog, Bildschirmsperre aus bzw. wieder
               an, unbegrenzte Amphetamine-Sitzung. Das Passwort wird nie gespeichert oder geloggt.

Alle Systemaufrufe laufen über _ausfuehren() mit Argumentlisten (nie eine Shell) und Timeouts. Tests setzen
RUNNER auf eine Attrappe; bei util.offline() ohne Attrappe gibt es keinen einzigen Systemaufruf.

Amphetamine: „enable closed display mode“ und „prevent screen saver“ werden NACH dem Start geschickt und ändern
damit laut sdef nur die laufende Sitzung, nicht die globalen Einstellungen. Deshalb muss beim Beenden einer
automatischen Sitzung nichts wiederhergestellt werden (sdef hat zwar den Getter „closed display mode enabled“,
er wird dafür nicht gebraucht). „allow screen saver“ nur beim manuellen `wach aus` (wie im Original), weil
Amphetamine dabei in Sonderfällen einen Dialog zeigt – nie unbeaufsichtigt.
"""

import math
import os
import re
import subprocess
import sys
import time

from . import util
from .sprache import t

DATEI = ("state", "wach.json")              # caffeinate + eigene Amphetamine-Sitzung + Automations-Probe
MODUS_DATEI = ("state", "wach-modus.json")  # manueller Wach-Modus (nie ein Passwort)
AMPH_PFADE = ("/Applications/Amphetamine.app", "~/Applications/Amphetamine.app")
RUNNER = None           # Tests: Attrappe mit der Signatur von subprocess.run
TIMEOUT = 10
# Passwortdialog schließt sich nach DIALOG_AUFGEBEN_S selbst; zusammen mit den übrigen Aufrufen bleibt
# `wach an|aus` so sicher unter dem Zeitlimit der App (Befehle.wachZeitlimit = 180 s).
DIALOG_AUFGEBEN_S = 110
DIALOG_TIMEOUT = 120
# Passwortdialog schließt sich nach DIALOG_AUFGEBEN_S selbst; zusammen mit den übrigen Aufrufen bleibt
# `wach an|aus` so sicher unter dem Zeitlimit der App (Befehle.wachZeitlimit = 180 s).
DIALOG_AUFGEBEN_S = 110
DIALOG_TIMEOUT = 120
PROBE_TIMEOUT = 60      # erste Automation-Anfrage: macOS fragt nach, der Nutzer braucht einen Moment
AN = ("an", "on", "ein")
AUS = ("aus", "off")
STATUS = ("status",)


# ------------------------------------------------------------------ Systemaufrufe

def _runner(runner=None):
    if runner is not None:
        return runner
    if RUNNER is not None:
        return RUNNER
    return None if util.offline() else subprocess.run


def _ausfuehren(args, runner=None, timeout=TIMEOUT):
    """-> CompletedProcess oder None (offline, Fehler, Timeout). args immer als Liste, nie über eine Shell."""
    r = _runner(runner)
    if r is None:
        return None
    try:
        return r(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "timeout"
    except (OSError, subprocess.SubprocessError):
        return None


def _ergebnis(r):
    return r if r not in (None, "timeout") else None


def _systemzugriff():
    """Echte Systemaufrufe erlaubt? (offline nur mit Attrappe)"""
    return RUNNER is not None or not util.offline()


# ------------------------------------------------------------------ Zustandsdateien

def _lies():
    return util.lies_json(util.pfad(*DATEI), {}) or {}


def _schreib(d):
    util.schreib_json(util.pfad(*DATEI), d)


def modus_lesen():
    return util.lies_json(util.pfad(*MODUS_DATEI), {}) or {}


def _modus_schreiben(d):
    datei = util.pfad(*MODUS_DATEI)
    util.schreib_json(datei, d)
    try:
        os.chmod(datei, 0o600)
    except OSError:
        pass


# ------------------------------------------------------------------ caffeinate (wie bisher)

def _lebt(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    try:
        name = subprocess.run(["/bin/ps", "-p", str(int(pid)), "-o", "comm="], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return name.endswith("caffeinate")


def zustand():
    d = _lies()
    d["laeuft"] = _lebt(d.get("pid")) and d.get("bis", 0) > util.jetzt()
    return d


def sicherstellen(bis, now, dry_run=False):
    """caffeinate bis `bis` (Epoch) laufen lassen. -> Text der Aktion oder None."""
    if bis <= now:
        return None
    d = zustand()
    if d.get("laeuft") and d.get("bis", 0) >= bis - 60:
        return None
    sekunden = int(bis - now) + 1
    if dry_run:
        return t("wach_dry", sek=sekunden, zeit=util.uhrzeit(bis, now))
    try:
        p = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-s", "-t", str(sekunden)],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except OSError as e:
        return t("wach_fehler", fehler=e)
    d = _lies()                       # amph/probe erhalten
    d.update({"pid": p.pid, "bis": bis, "gestartet": now})
    _schreib(d)
    return t("wach_start", zeit=util.uhrzeit(bis, now), pid=p.pid)


# ------------------------------------------------------------------ Bildschirmsperre

def parse_sperre(text):
    """Ausgabe von `sysadminctl -screenLock status` -> "off" | "immediate" | "<sekunden>" | None."""
    text = text or ""
    m = re.search(r"screenLock delay is (\d+) seconds", text)
    if m:
        return m.group(1)
    if re.search(r"screenLock (?:delay )?is immediate", text):     # echt: "screenLock delay is immediate"
        return "immediate"
    if re.search(r"screenLock is off", text):
        return "off"
    return None


def sperre_status(runner=None):
    r = _ergebnis(_ausfuehren(["/usr/sbin/sysadminctl", "-screenLock", "status"], runner))
    if r is None:
        return None
    return parse_sperre((r.stderr or "") + "\n" + (r.stdout or ""))     # sysadminctl schreibt auf stderr


def passwort_dialog(runner=None):
    """Passwort per macOS-Dialog. -> str oder None (Abbruch). Texte als argv, nie in das Skript eingesetzt."""
    skript = ('text returned of (display dialog (item 1 of argv) default answer "" with hidden answer '
              'buttons {item 2 of argv, item 3 of argv} default button item 3 of argv with title (item 4 of argv) '
              f'giving up after {DIALOG_AUFGEBEN_S})')
    r = _ergebnis(_ausfuehren(["/usr/bin/osascript", "-e", "on run argv", "-e", skript, "-e", "end run",
                               t("wm_dialog_text"), t("wm_abbrechen"), t("wm_ok"), t("app")], runner,
                              timeout=DIALOG_TIMEOUT))
    if r is None or r.returncode != 0:
        return None
    wert = (r.stdout or "").rstrip("\n")
    return wert or None


def sperre_setzen(wert, passwort, runner=None):
    """Sperrzeit setzen ("off", "immediate" oder Sekunden). -> bool.

    Das Passwort geht wie im Original (remote.sh) als Argument an sysadminctl: `-password -` liest nur von
    einem Terminal (TTY) und ist aus der App und aus launchd nicht nutzbar. Es steht dadurch kurz in der
    Prozessliste, wird aber nie geloggt, gespeichert oder in eine Fehlermeldung übernommen."""
    wert = str(wert)
    r = _ergebnis(_ausfuehren(["/usr/sbin/sysadminctl", "-screenLock", wert, "-password", passwort], runner))
    del passwort
    if r is None or r.returncode != 0:
        return False
    neu = sperre_status(runner)       # sysadminctl meldet Fehler nicht immer über den Exit-Code
    return neu is None or neu == wert


# ------------------------------------------------------------------ Amphetamine

def amphetamine_installiert():
    if not _systemzugriff():
        return False
    return any(os.path.isdir(os.path.expanduser(p)) for p in AMPH_PFADE)


def amphetamine_laeuft(runner=None):
    """pgrep statt AppleScript: startet die App nicht und braucht keine Automation-Freigabe."""
    r = _ergebnis(_ausfuehren(["/usr/bin/pgrep", "-x", "Amphetamine"], runner))
    return bool(r is not None and r.returncode == 0)


def _skript(befehl, minuten=0, zugeklappt=True):
    """Feste AppleScript-Zeilen (nur eine ganze Zahl wird eingesetzt, nie Nutzertext)."""
    zeilen = ['tell application "Amphetamine"']
    if befehl == "starten":
        m = max(0, int(minuten))
        intervall = "minutes" if m else "0"
        zeilen.append(f"start new session with options {{duration:{m}, interval:{intervall}, "
                      "displaySleepAllowed:true}")
        if zugeklappt:
            zeilen.append("enable closed display mode")     # nach dem Start: gilt nur für diese Sitzung
        zeilen.append("prevent screen saver")
    elif befehl == "beenden":
        zeilen.append("end session")
    elif befehl == "beenden_manuell":
        zeilen += ["end session", "allow screen saver"]
    elif befehl == "lage":
        zeilen += ["if session is active then", 'return "aktiv " & (session time remaining as text)',
                   "else", 'return "inaktiv"', "end if"]
    else:
        raise ValueError(befehl)
    zeilen.append("end tell")
    args = ["/usr/bin/osascript"]
    for z in zeilen:
        args += ["-e", z]
    return args


def amphetamine(befehl, minuten=0, zugeklappt=True, runner=None, timeout=TIMEOUT):
    """-> (ok, antwort|fehler). fehler: "verweigert" (Automation nicht erlaubt), "timeout", "fehler"."""
    r = _ausfuehren(_skript(befehl, minuten, zugeklappt), runner, timeout)
    if r == "timeout":
        return False, "timeout"
    if r is None:
        return False, "fehler"
    if r.returncode != 0:
        fehltext = (r.stderr or "") + (r.stdout or "")
        if "-1743" in fehltext or "Not authorized" in fehltext or "nicht berechtigt" in fehltext:
            return False, "verweigert"
        return False, "fehler"
    return True, (r.stdout or "").strip()


def amphetamine_lage(runner=None, timeout=TIMEOUT):
    """-> (True, rest_s|None) aktiv, (False, None) inaktiv, oder (None, fehler)."""
    ok, antwort = amphetamine("lage", runner=runner, timeout=timeout)
    if not ok:
        return None, antwort
    if antwort.startswith("aktiv"):
        m = re.search(r"-?\d+(?:[.,]\d+)?", antwort)
        return True, (float(m.group(0).replace(",", ".")) if m else None)
    return False, None


def _eigen_plausibel(amph, rest, now):
    """Ist die laufende Sitzung wirklich unsere? Restzeit muss zu unserem Ende passen (±10 min);
    unbekannt oder unbegrenzt -> lieber fremd (dann endet unsere befristete Sitzung von selbst)."""
    return bool(rest and rest > 0 and abs(now + rest - (amph.get("bis") or 0)) <= 600)


# ------------------------------------------------------------------ manuell (mit Passwort)

def _banner(k, text, runner=None):
    if not k.get("melden", {}).get("banner", True):
        return
    _ausfuehren(["/usr/bin/osascript", "-e", "on run argv", "-e",
                 "display notification (item 1 of argv) with title (item 2 of argv)", "-e", "end run",
                 text, t("app")], runner)


ALT_ZUSTAND_NAME = ".vorherige-sperre"      # Zustandsdatei des früheren Skripts remote.sh (neben dem Skript)


def _skript_pfad(befehl):
    """Erstes Wort eines Befehls als Pfad (~ aufgelöst) oder None."""
    teile = str(befehl or "").split()
    return os.path.expanduser(teile[0]) if teile else None


def alt_zustand_datei(k):
    """Alte Zustandsdatei: ausdrücklich konfiguriert, sonst neben dem Skript aus remote_modus_befehl
    (so klappt der Umstieg von remote.sh ohne weitere Einstellung)."""
    w = k["wach"]
    datei = str(w.get("remote_alt_zustand") or "").strip()
    if datei:
        return datei
    skript = _skript_pfad(w.get("remote_modus_befehl"))
    return os.path.join(os.path.dirname(skript), ALT_ZUSTAND_NAME) if skript else ""


def hinweis_befehl(k):
    """Befehl für den Nacht-Hinweis: ein eingestellter fremder Befehl nur, solange sein Skript noch existiert
    (alte Skripte dürfen nach dem Umstieg gelöscht werden), sonst der eigene `wach an`."""
    befehl = str(k["wach"].get("remote_modus_befehl") or "").strip()
    skript = _skript_pfad(befehl)
    if befehl and skript and (os.path.exists(skript) or not os.path.isabs(skript)):
        return befehl
    return eigener_befehl()


def _alt_uebernehmen(k, m):
    """Einmalig die Sperrzeit aus einer alten Zustandsdatei (remote.sh) übernehmen; die Datei bleibt, wie sie ist."""
    datei = alt_zustand_datei(k)
    if not datei or m.get("uebernommen") or m.get("sperre_vorher"):
        return None
    try:
        with open(os.path.expanduser(datei), encoding="utf-8") as f:
            wert = f.read().strip()
    except OSError:
        return None
    m["uebernommen"] = True
    if re.fullmatch(r"\d{1,6}|immediate", wert):
        m["sperre_vorher"] = wert
        return wert
    return None


def wach_an(k, now, runner=None):
    """`wach an`: Passwortdialog, Sperre aus, unbegrenzte Amphetamine-Sitzung. -> {"ok", "fehler", "text"}."""
    passwort = passwort_dialog(runner)
    if passwort is None:
        return {"ok": False, "fehler": "abgebrochen", "text": t("wm_abgebrochen")}
    m = modus_lesen()
    hinweise = []
    alt = _alt_uebernehmen(k, m)
    if alt:
        hinweise.append(t("wm_uebernommen", wert=alt))
    aktuell = sperre_status(runner)
    if aktuell not in (None, "off"):       # schon aus: gesicherten Wert nicht überschreiben
        m["sperre_vorher"] = aktuell
    ok = sperre_setzen("off", passwort, runner)
    del passwort
    if not ok:
        text = t("wm_passwort")
        _banner(k, text, runner)
        return {"ok": False, "fehler": "passwort", "text": text}
    amph_ok = False
    if amphetamine_installiert():
        amph_ok, _ = amphetamine("starten", 0, True, runner)      # beendet auch eine eigene automatische Sitzung
        d = _lies()
        if (d.get("amph") or {}).get("eigen"):
            d["amph"] = dict(d["amph"], eigen=False)
            _schreib(d)
        text = t("wm_an") if amph_ok else t("wm_an_amph_fehler")
    else:
        text = t("wm_an_ohne_amph")
    m.update({"an": True, "seit": now, "amph": amph_ok})
    m.setdefault("sperre_vorher", None)
    m.setdefault("uebernommen", False)
    _modus_schreiben(m)
    util.ereignis("wach", weg="an")
    util.log(t("wm_log", text=text))
    _banner(k, text, runner)
    return {"ok": True, "fehler": None, "text": " ".join(hinweise + [text])}


def wach_aus(k, now, runner=None):
    """`wach aus`: Passwortdialog, Sperre wiederherstellen, Amphetamine-Sitzung beenden (wie remote.sh aus)."""
    passwort = passwort_dialog(runner)
    if passwort is None:
        return {"ok": False, "fehler": "abgebrochen", "text": t("wm_abgebrochen")}
    m = modus_lesen()
    # Eigene Amphetamine-Sitzung: vom manuellen Modus gestartet, oder beim Umstieg die des alten remote.sh
    eigene_sitzung = bool(m.get("an") and m.get("amph"))
    if _alt_uebernehmen(k, m):
        eigene_sitzung = True
    vorher = m.get("sperre_vorher") or str(k["wach"]["sperre_standard"])
    ok = sperre_setzen(vorher, passwort, runner)
    del passwort
    if not ok:
        text = t("wm_passwort")
        _banner(k, text, runner)
        return {"ok": False, "fehler": "passwort", "text": text}
    # Nur die eigene Sitzung beenden; eine selbst gestartete Amphetamine-Sitzung des Nutzers bleibt.
    if eigene_sitzung and amphetamine_installiert() and amphetamine_laeuft(runner):
        amphetamine("beenden_manuell", runner=runner)
        d = _lies()
        if (d.get("amph") or {}).get("eigen"):
            d["amph"] = dict(d["amph"], eigen=False)
            _schreib(d)
    m.update({"an": False, "seit": now, "amph": False})
    _modus_schreiben(m)
    text = t("wm_aus", sperre=sperre_text(vorher))
    util.ereignis("wach", weg="aus")
    util.log(t("wm_log", text=text))
    _banner(k, text, runner)
    return {"ok": True, "fehler": None, "text": text}


# ------------------------------------------------------------------ automatisch (Tick, ohne Passwort)

def _eigene_beenden(ctx, d, now):
    amph = d.get("amph") or {}
    if not amph.get("eigen"):
        return []
    if (amph.get("bis") or 0) <= now:        # von selbst abgelaufen
        d["amph"] = dict(amph, eigen=False)
        _schreib(d)
        return []
    if ctx.dry_run:
        return [t("wm_amph_ende_dry")]
    aktiv, rest = amphetamine_lage()
    if aktiv is None:
        return []                             # Zustand unklar: nächster Tick versucht es wieder
    texte = []
    if aktiv and _eigen_plausibel(amph, rest, now):
        ok, _ = amphetamine("beenden")
        if not ok:
            return []
        texte.append(t("wm_amph_ende"))
    d["amph"] = dict(amph, eigen=False)
    _schreib(d)
    return texte


def _verweigert(ctx, d, now):
    d["probe"] = {"ergebnis": "verweigert", "zeit": now}
    _schreib(d)
    ctx.melder.senden(t("wm_push_automation"), prio=3, tags=["lock"], schluessel="wach-automation")


def automatisch(ctx, bedarf_bis, now):
    """Bis bedarf_bis wach halten (None = kein Bedarf). Ruft ctx.aktion() nicht selbst auf. -> [Aktionstexte]."""
    k = ctx.k["wach"]
    d = _lies()
    amph = d.get("amph") or {}
    if not bedarf_bis or bedarf_bis <= now:
        return _eigene_beenden(ctx, d, now)
    texte = []
    if k["caffeinate"]:
        x = sicherstellen(bedarf_bis, now, ctx.dry_run)
        if x:
            texte.append(x)
        d = _lies()
        amph = d.get("amph") or {}
    if not k.get("amphetamine", True) or not amphetamine_installiert() or _manuell_haelt():
        return texte
    if (d.get("probe") or {}).get("ergebnis") != "ok":
        return texte                          # Automation nicht (nachweislich) erlaubt: keine Rückfrage nachts
    if amph.get("eigen") and (amph.get("bis") or 0) >= bedarf_bis - 60:
        return texte                          # eigene Sitzung reicht (ohne AppleScript-Abfrage)
    minuten = max(1, int(math.ceil((bedarf_bis - now) / 60.0)))
    bis = now + minuten * 60
    zugeklappt = bool(k.get("amphetamine_zugeklappt", True))
    if ctx.dry_run:
        return texte + [t("wm_amph_dry", zeit=util.uhrzeit(bis, now))]
    eigen = bool(amph.get("eigen")) and (amph.get("bis") or 0) > now
    aktiv, rest = amphetamine_lage()
    if aktiv is None:
        if rest == "verweigert":
            _verweigert(ctx, d, now)
        return texte
    if aktiv and not (eigen and _eigen_plausibel(amph, rest, now)):
        if eigen:                             # jemand hat eine andere Sitzung gestartet: nie anfassen
            d["amph"] = dict(amph, eigen=False)
            _schreib(d)
        return texte
    ok, fehler = amphetamine("starten", minuten, zugeklappt)
    if not ok:
        if fehler == "verweigert":
            _verweigert(ctx, d, now)
        return texte + [t("wm_amph_fehler", fehler=fehler)]
    d["amph"] = {"eigen": True, "bis": bis, "gestartet": now, "zugeklappt": zugeklappt}
    _schreib(d)
    return texte + [t("wm_amph_start", zeit=util.uhrzeit(bis, now))]


def _tagsueber(now):
    return 9 <= time.localtime(now).tm_hour <= 21


def probe(ctx, now):
    """Automation-Freigabe für Amphetamine prüfen: nur tagsüber (09–22 Uhr), höchstens alle 24 h, nur solange
    sie nicht nachgewiesen ist und nur bei laufender App. So kommt eine macOS-Rückfrage nie nachts."""
    k = ctx.k["wach"]
    if ctx.dry_run or not k.get("amphetamine", True) or not amphetamine_installiert():
        return None
    d = _lies()
    p = d.get("probe") or {}
    if p.get("ergebnis") == "ok" or not _tagsueber(now):
        return None
    if p.get("zeit") and now - p["zeit"] < 86400:
        return None
    if not amphetamine_laeuft():
        return None
    aktiv, fehler = amphetamine_lage(timeout=PROBE_TIMEOUT)
    if aktiv is not None:
        d["probe"] = {"ergebnis": "ok", "zeit": now}
        _schreib(d)
        return "ok"
    if fehler == "verweigert":
        _verweigert(ctx, d, now)
        return "verweigert"
    # Timeout (Rückfrage offen) oder anderer Fehler: in 10 Minuten noch einmal
    d["probe"] = {"ergebnis": p.get("ergebnis"), "zeit": now - 86400 + 600}
    _schreib(d)
    return None


def _manuell_haelt():
    """Manueller Wach-Modus an, seine Amphetamine-Sitzung gestartet und Amphetamine läuft noch?"""
    m = modus_lesen()
    return bool(m.get("an") and m.get("amph")) and amphetamine_laeuft()


def haelt_zugeklappt(k, now):
    """Hält der Wächter den Mac gerade selbst auch zugeklappt wach (manueller Modus oder eigene Sitzung)?"""
    if _manuell_haelt():
        return True
    amph = _lies().get("amph") or {}
    return bool(amph.get("eigen") and amph.get("zugeklappt") and (amph.get("bis") or 0) > now)


def eigener_befehl(aus=False):
    pfad = os.path.join(util.PROJEKT, "waechter.py")
    heim = os.path.expanduser("~")
    if pfad.startswith(heim + os.sep):
        pfad = "~" + pfad[len(heim):]
    return t("wm_befehl_aus" if aus else "wm_befehl", pfad=pfad)


# ------------------------------------------------------------------ Anzeige

def sperre_text(wert):
    if wert == "off":
        return t("wm_sperre_off")
    if wert == "immediate":
        return t("wm_sperre_sofort")
    if wert and str(wert).isdigit():
        return util.dauer_text(int(wert))
    return "?"


def amph_zustand(k=None):
    if not amphetamine_installiert():
        return "fehlt"
    ergebnis = (_lies().get("probe") or {}).get("ergebnis")
    return {"ok": "bereit", "verweigert": "verweigert"}.get(ergebnis, "ungeprueft")


def status_block(k, now, mac=None):
    """Block "wach" für status --json (ohne AppleScript; offline ohne Systemaufrufe)."""
    d = zustand()
    m = modus_lesen()
    amph = d.get("amph") or {}
    amph_eigen = bool(amph.get("eigen")) and (amph.get("bis") or 0) > now
    caf = bool(d.get("laeuft"))
    if m.get("an"):
        modus = "manuell"
        art = "amphetamine" if m.get("amph") else ("caffeinate" if caf else "aus")
        bis = None
    elif amph_eigen or caf:
        modus = "automatisch"
        art = "amphetamine" if amph_eigen else "caffeinate"
        bis = max((amph.get("bis") or 0) if amph_eigen else 0, (d.get("bis") or 0) if caf else 0) or None
    else:
        modus, art, bis = "aus", "aus", None
    if mac is None and _systemzugriff():
        try:
            from . import quellen
            mac = quellen.mac_status()
        except Exception:      # Anzeige darf nie scheitern
            mac = None
    mac = mac or {}
    sperre = sperre_status() if _systemzugriff() else None
    zugeklappt_selbst = art == "amphetamine" and (modus == "manuell" or bool(amph.get("zugeklappt")))
    if "wach_bei_deckel_zu" in mac:
        zugeklappt_ok = bool(mac.get("wach_bei_deckel_zu")) or zugeklappt_selbst
    else:
        zugeklappt_ok = True if zugeklappt_selbst else None
    netzteil = mac.get("netzteil") if "netzteil" in mac else None
    amph_z = amph_zustand(k)
    zu = t("wm_zu_ok") if zugeklappt_ok else (t("wm_zu_nein") if zugeklappt_ok is False else "")
    art_text = t("wm_art_" + art)
    if modus == "manuell":
        text = t("wm_text_manuell", art=art_text, zu=zu) if art != "aus" else t("wm_text_manuell_ohne")
    elif modus == "automatisch":
        text = t("wm_text_auto", zeit=util.uhrzeit(bis, now), art=art_text, zu=zu)
    else:
        text = t("wm_text_aus")
    return {"an": art != "aus", "art": art, "modus": modus, "bis": bis, "sperre": sperre,
            "zugeklappt_ok": zugeklappt_ok, "netzteil": netzteil, "amphetamine": amph_z, "text": text}


# ------------------------------------------------------------------ Rückbau (uninstall.sh)

class _RueckbauKontext:
    dry_run = False


def rueckbau(now=None):
    """Für uninstall.sh: eigene automatische Amphetamine-Sitzung beenden (nur wenn plausibel unsere) und
    warnen, falls der manuelle Wach-Modus noch an ist (dann bliebe die Bildschirmsperre dauerhaft aus).
    Ohne Passwort; die Sperre selbst wird hier nie geändert. -> Ausgabezeilen."""
    now = util.jetzt() if now is None else now
    zeilen = []
    if amphetamine_installiert() and (_lies().get("amph") or {}).get("eigen"):
        zeilen += _eigene_beenden(_RueckbauKontext(), _lies(), now)
    if modus_lesen().get("an"):
        zeilen.append(t("wm_rueckbau_modus_an", befehl=eigener_befehl(aus=True)))
    return zeilen or ["–"]


def main(argv):
    from . import konfig
    konfig.laden()                    # setzt die Sprache der Ausgaben
    if argv[:1] != ["rueckbau"]:
        print("usage: python3 -m lw.wach rueckbau", file=sys.stderr)
        return 2
    for zeile in rueckbau():
        print("   " + zeile)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
