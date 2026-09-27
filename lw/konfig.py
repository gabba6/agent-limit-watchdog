"""Konfiguration aus config.toml.

/usr/bin/python3 ist 3.9 und hat kein tomllib. Deshalb ein kleiner Parser für die
Teilmenge, die config.toml nutzt: [abschnitt], schluessel = wert, Strings, Zahlen,
true/false, einzeilige Listen und Kommentare.
"""

import copy
import os
import re
import shutil
import tempfile

from . import sprache, util

STANDARD = {
    "allgemein": {
        "sprache": "en",                          # "de" | "en"
        "name": "",                               # optional: dein Name für die Hook-Texte
        "launchagent_label": "local.limit-waechter",
        "nur_orca": False,                        # v1.3: True = nur Orca-Terminals überwachen (Verhalten bis 1.2)
    },
    "schwellen": {
        "warnung": 80,          # % im 5h-Fenster
        "stopp": 92,            # % im 5h-Fenster
        "woche_warnung": 80,    # % im Wochenfenster
        "woche_stopp": 92,      # % im Wochenfenster
        "wochen_reserve": 20,   # ab 100 - Reserve % Wochenverbrauch keine automatische Fortsetzung
    },
    "fortsetzen": {
        "aktiv": True,
        "nur_mit_nachtmodus": True,         # v1.1: nur Sitzungen im Nachtmodus automatisch fortsetzen
        "puffer_minuten": 2,
        "max_pro_fenster": 2,
        "pro_tick": 2,
        "claude_limit_resume": "waechter",   # "waechter" | "orca"
        "claude_eingebaut_karenz_minuten": 5,
        "reserve_sperrt_eingebaute_fortsetzung": True,
        "claude_befehl": "",                      # leer = automatisch suchen
        "claude_modus": "auto",
        "codex_befehl": "",
        "codex_sandbox": "workspace-write",
        "codex_stopp_senden": True,
        "codex_queue": False,                     # v1.3: Codex außerhalb von Orca per `codex queue` stoppen/fortsetzen
                                                  # (nicht echt getestet -> Standard aus, dann nur Warnung/Push)
        "pruefen_nach_minuten": 2,
        "belege_pruefen": True,                   # v1.4 B: Orca-"working" nur mit Belegen (Bildschirm/Transcript) glauben
        "aktiv_frist_minuten": 10,                # v1.4 B: letzter Protokolleintrag jünger -> Turn gilt als laufend
        "max_nachpruefungen": 3,                  # v1.4 B: "läuft bereits" ohne Beleg -> zurück ins Warten, danach blockiert
    },
    "daten": {
        "orca": "/Applications/Orca.app/Contents/Resources/bin/orca",
        "codex_sessions": "~/.codex/sessions",
        "orca_hook_status": "~/Library/Application Support/orca/agent-hooks/last-status.json",
        "max_alter_minuten": 30,
        "hook_zustand_max_alter_minuten": 10,
        # v1.4 A: offizielle Nutzungsanzeige (nur lesender Abruf, Token nur zur Laufzeit)
        "offiziell": True,                          # v1.4 A
        "offiziell_intervall_minuten": 3,           # v1.4 A
        "offiziell_intervall_eng_minuten": 1,       # v1.4 A: bei Warnung/Stopp/Limit oder anstehender Fortsetzung
        "offiziell_max_alter_minuten": 10,          # v1.4 A: jünger -> offizielle Quelle hat Vorrang
        "offiziell_timeout_sekunden": 8,            # v1.4 A
        "claude_usage_url": "https://api.anthropic.com/api/oauth/usage",       # v1.4 A
        "codex_usage_url": "https://chatgpt.com/backend-api/wham/usage",       # v1.4 A
        "claude_schluesselbund_dienst": "Claude Code-credentials",             # v1.4 A
        "codex_auth": "~/.codex/auth.json",         # v1.4 A (expanduser beim Lesen in nutzung.codex_token)
        "frueh_reset_abfall": 20,                   # v1.4 A: Prozentpunkte
    },
    "melden": {
        "ntfy": True,
        "ntfy_server": "https://ntfy.sh",
        "ntfy_dienst": "limit-waechter-ntfy",
        "banner": True,
    },
    "wach": {
        "caffeinate": True,
        "nachlauf_minuten": 15,
        "max_stunden_voraus": 12,
        "remote_modus_pruefen": True,
        "remote_modus_befehl": "",                # nur für den Push-Text; leer = eigener Befehl "waechter.py wach an"
        "amphetamine": True,                      # v1.4 C: Amphetamine nutzen, falls installiert (sonst nur caffeinate)
        "amphetamine_zugeklappt": True,           # v1.4 C: "closed display mode" für eigene Sitzungen
        "bei_nachtmodus": True,                   # v1.4 C: während Nachtmodus automatisch wach halten
        "sperre_standard": 300,                   # v1.4 C: Sperrzeit für "wach aus" ohne gesicherten Wert
        "remote_alt_zustand": "",                 # v1.4 C: alte Zustandsdatei von remote.sh (einmal lesen)
    },
    "bericht": {
        "uhrzeit": "08:00",
    },
}


PRUEF_ZUSATZ = []  # f(k) -> [fehlertexte]


class KonfigFehler(ValueError):
    pass


def _wert(roh, zeile_nr):
    roh = roh.strip()
    if not roh:
        raise KonfigFehler(f"Zeile {zeile_nr}: leerer Wert")
    if roh[0] == '"':
        m = re.match(r'"((?:[^"\\]|\\.)*)"$', roh)
        if not m:
            raise KonfigFehler(f"Zeile {zeile_nr}: String nicht geschlossen")
        ersatz = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}

        def _escape(t):
            if t.group(1):
                return chr(int(t.group(1), 16))
            if t.group(2) in ersatz:
                return ersatz[t.group(2)]
            raise KonfigFehler(f"Zeile {zeile_nr}: unbekanntes Escape \\{t.group(2)}")

        return re.sub(r"\\(?:u([0-9a-fA-F]{4})|(.))", _escape, m.group(1))
    if roh[0] == "'":
        if not roh.endswith("'") or len(roh) < 2:
            raise KonfigFehler(f"Zeile {zeile_nr}: String nicht geschlossen")
        return roh[1:-1]
    if roh[0] == "[":
        if not roh.endswith("]"):
            raise KonfigFehler(f"Zeile {zeile_nr}: Liste nicht geschlossen")
        innen = roh[1:-1].strip()
        if not innen:
            return []
        teile, aktuell, in_str = [], "", None
        for ch in innen:
            if in_str:
                aktuell += ch
                if ch == in_str:
                    in_str = None
            elif ch in "\"'":
                in_str = ch
                aktuell += ch
            elif ch == ",":
                teile.append(aktuell)
                aktuell = ""
            else:
                aktuell += ch
        if aktuell.strip():
            teile.append(aktuell)
        return [_wert(t, zeile_nr) for t in teile]
    if roh in ("true", "false"):
        return roh == "true"
    try:
        if re.fullmatch(r"[+-]?\d+", roh.replace("_", "")):
            return int(roh.replace("_", ""))
        return float(roh.replace("_", ""))
    except ValueError:
        raise KonfigFehler(f"Zeile {zeile_nr}: unbekannter Wert {roh!r}")


def _ohne_kommentar(zeile):
    in_str = None
    for i, ch in enumerate(zeile):
        if in_str:
            if ch == in_str and zeile[i - 1] != "\\":
                in_str = None
        elif ch in "\"'":
            in_str = ch
        elif ch == "#":
            return zeile[:i]
    return zeile


def parse_toml(text):
    daten = {}
    abschnitt = daten
    for nr, zeile in enumerate(text.splitlines(), 1):
        zeile = _ohne_kommentar(zeile).strip()
        if not zeile:
            continue
        m = re.fullmatch(r"\[([A-Za-z0-9_.-]+)\]", zeile)
        if m:
            abschnitt = daten
            for teil in m.group(1).split("."):
                abschnitt = abschnitt.setdefault(teil, {})
            continue
        if "=" not in zeile:
            raise KonfigFehler(f"Zeile {nr}: erwartet schluessel = wert")
        schluessel, wert = zeile.split("=", 1)
        schluessel = schluessel.strip().strip('"')
        if not re.fullmatch(r"[A-Za-z0-9_-]+", schluessel):
            raise KonfigFehler(f"Zeile {nr}: ungültiger Schlüssel {schluessel!r}")
        abschnitt[schluessel] = _wert(wert, nr)
    return daten


def _mischen(basis, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(basis.get(k), dict):
            _mischen(basis[k], v)
        else:
            basis[k] = v
    return basis


def pruefen(k):
    s = k["schwellen"]
    fehler = []
    for name in ("warnung", "stopp", "woche_warnung", "woche_stopp", "wochen_reserve"):
        if not isinstance(s.get(name), (int, float)) or not 0 <= s[name] <= 100:
            fehler.append(sprache.t("kf_bereich", name=f"schwellen.{name}"))
    if not fehler:
        if s["warnung"] >= s["stopp"]:
            fehler.append(sprache.t("kf_warnung_stopp"))
        if s["woche_warnung"] > s["woche_stopp"]:
            fehler.append(sprache.t("kf_woche"))
    if k["allgemein"]["sprache"] not in ("de", "en"):
        fehler.append('allgemein.sprache muss "de" oder "en" sein')
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", str(k["allgemein"]["launchagent_label"])):
        fehler.append("allgemein.launchagent_label darf nur Buchstaben, Ziffern, . _ - enthalten")
    if k["fortsetzen"]["claude_limit_resume"] not in ("waechter", "orca"):
        fehler.append('fortsetzen.claude_limit_resume muss "waechter" oder "orca" sein')
    if not re.fullmatch(r"\d{1,2}:\d{2}", str(k["bericht"]["uhrzeit"])):
        fehler.append('bericht.uhrzeit muss wie "08:00" aussehen')
    for f in PRUEF_ZUSATZ:
        fehler.extend(f(k))
    return fehler


SUCHPFADE = ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin", "~/.npm-global/bin", "/usr/bin")


def konfig_pfad():
    return os.environ.get("LIMIT_WAECHTER_CONFIG") or os.path.join(util.PROJEKT, "config.toml")


def lokal_pfad(datei):
    """Persönliche Werte (nie im Repo): config.local.toml neben config.toml."""
    return os.path.join(os.path.dirname(datei), "config.local.toml")


def finde_programm(wert, name):
    """Angegebener Pfad, sonst PATH, sonst übliche Installationsorte (launchd hat einen kargen PATH)."""
    if wert:
        return os.path.expanduser(wert)
    gefunden = shutil.which(name)
    if gefunden:
        return gefunden
    for ordner in SUCHPFADE:
        kandidat = os.path.join(os.path.expanduser(ordner), name)
        if os.access(kandidat, os.X_OK):
            return kandidat
    return name


def laden(datei=None, streng=False):
    """Standardwerte + config.toml + config.local.toml. Bei Fehlern: Standardwerte und Logeintrag
    (streng=True: Ausnahme). Setzt außerdem Sprache und Namen für alle Texte."""
    k = copy.deepcopy(STANDARD)
    datei = datei or konfig_pfad()
    try:
        kandidat = copy.deepcopy(STANDARD)
        for quelle in (datei, lokal_pfad(datei)):
            try:
                with open(quelle, encoding="utf-8") as f:
                    _mischen(kandidat, parse_toml(f.read()))
            except FileNotFoundError:
                continue
        fehler = pruefen(kandidat)
        if fehler:
            raise KonfigFehler("; ".join(fehler))
        k = kandidat
    except KonfigFehler as e:
        if streng:
            raise
        util.log(sprache.t("log_konfig_fehler", datei=datei, fehler=e))
    for abschnitt, schluessel in (("daten", "codex_sessions"), ("daten", "orca_hook_status")):
        k[abschnitt][schluessel] = os.path.expanduser(k[abschnitt][schluessel])
    k["fortsetzen"]["claude_befehl"] = finde_programm(k["fortsetzen"]["claude_befehl"], "claude")
    k["fortsetzen"]["codex_befehl"] = finde_programm(k["fortsetzen"]["codex_befehl"], "codex")
    sprache.setzen(k["allgemein"]["sprache"], k["allgemein"]["name"])
    return k


def wert(k, pfad):
    """'allgemein.launchagent_label' -> Wert (für install.sh/uninstall.sh)."""
    for teil in pfad.split("."):
        k = k[teil]
    return k


def _toml_wert(w):
    if isinstance(w, bool):
        return "true" if w else "false"
    if isinstance(w, (int, float)):
        return str(w)
    return '"' + str(w).replace("\\", "\\\\").replace('"', '\\"') + '"'


def lokal_setzen(abschnitt, werte, datei=None):
    """Schreibt Werte in [abschnitt] von config.local.toml: andere Zeilen und Kommentare bleiben erhalten,
    vorhandene Schlüssel werden ersetzt, fehlende ergänzt. Atomar, Dateirechte bleiben (neu: 0o600)."""
    datei = datei or lokal_pfad(konfig_pfad())
    try:
        with open(datei, encoding="utf-8") as f:
            zeilen = f.read().splitlines()
        rechte = os.stat(datei).st_mode & 0o777
    except FileNotFoundError:
        zeilen, rechte = [], 0o600
    offen = dict(werte)
    aktuell, letzter_eintrag = None, None
    for i, zeile in enumerate(zeilen):
        roh = _ohne_kommentar(zeile).strip()
        m = re.fullmatch(r"\[([A-Za-z0-9_.-]+)\]", roh)
        if m:
            aktuell = m.group(1)
            continue
        if aktuell != abschnitt:
            continue
        if "=" in roh:
            letzter_eintrag = i
            schluessel = roh.split("=", 1)[0].strip().strip('"')
            if schluessel in werte:
                # alle Vorkommen ersetzen (parse_toml nimmt den letzten Wert)
                kommentar = zeile[len(_ohne_kommentar(zeile)):]
                zeilen[i] = f"{schluessel} = {_toml_wert(werte[schluessel])}" + (
                    "  " + kommentar.strip() if kommentar.strip() else "")
                offen.pop(schluessel, None)
    neu = [f"{s} = {_toml_wert(w)}" for s, w in offen.items()]
    if neu:
        kopf = [i for i, z in enumerate(zeilen) if _ohne_kommentar(z).strip() == f"[{abschnitt}]"]
        if kopf:
            # hinter den letzten Schlüssel/Wert-Eintrag des Abschnitts (Kommentare vor dem nächsten Kopf bleiben dort)
            pos = letzter_eintrag if letzter_eintrag is not None else kopf[-1]
            zeilen[pos + 1:pos + 1] = neu
        else:
            if zeilen and zeilen[-1].strip():
                zeilen.append("")
            zeilen += [f"[{abschnitt}]"] + neu
    ordner = os.path.dirname(os.path.abspath(datei))
    os.makedirs(ordner, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ordner, prefix=".tmp-", suffix=".toml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(zeilen) + "\n")
        os.chmod(tmp, rechte)
        os.replace(tmp, datei)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return datei


# ======== v1.4 A (Fuellstand) – nur zwischen diesen Zeilen einfuegen ========
def _pruefen_daten(k):
    """v1.4 A: Abrufintervalle der offiziellen Nutzungsanzeige."""
    d = k.get("daten") or {}
    fehler = []
    namen = ("offiziell_intervall_minuten", "offiziell_intervall_eng_minuten", "offiziell_max_alter_minuten",
             "offiziell_timeout_sekunden")
    ok = True
    for name in namen:
        w = d.get(name, STANDARD["daten"][name])
        if isinstance(w, bool) or not isinstance(w, int) or w < 1:
            fehler.append(sprache.t("nz_kf_ganzzahl", name=name))
            ok = False
    if ok:
        normal = d.get("offiziell_intervall_minuten", 3)
        if d.get("offiziell_intervall_eng_minuten", 1) > normal:
            fehler.append(sprache.t("nz_kf_eng"))
        if d.get("offiziell_max_alter_minuten", 10) < normal:
            fehler.append(sprache.t("nz_kf_alter"))
    abfall = d.get("frueh_reset_abfall", 20)
    if isinstance(abfall, bool) or not isinstance(abfall, (int, float)) or not 5 <= abfall <= 100:
        fehler.append(sprache.t("nz_kf_abfall"))
    return fehler


PRUEF_ZUSATZ.append(_pruefen_daten)

# ======== v1.4 A Ende ========

# ======== v1.4 B (Fortsetzen) – nur zwischen diesen Zeilen einfuegen ========
def _pruefen_b(k):
    f = k["fortsetzen"]
    fehler = []
    for name, grenzen in (("aktiv_frist_minuten", (1, 1440)), ("max_nachpruefungen", (0, 20))):
        wert = f.get(name)
        if isinstance(wert, bool) or not isinstance(wert, int) or not grenzen[0] <= wert <= grenzen[1]:
            fehler.append(sprache.t("fs_kf_bereich", name=f"fortsetzen.{name}", min=grenzen[0], max=grenzen[1]))
    if not isinstance(f.get("belege_pruefen"), bool):
        fehler.append(sprache.t("fs_kf_bool", name="fortsetzen.belege_pruefen"))
    return fehler


PRUEF_ZUSATZ.append(_pruefen_b)

# ======== v1.4 B Ende ========

# ======== v1.4 C (Wach-Modus) – nur zwischen diesen Zeilen einfuegen ========
def _pruefen_wach(k):
    w = k.get("wach", {})
    wert = w.get("sperre_standard")
    if isinstance(wert, bool) or not isinstance(wert, int) or not 0 <= wert <= 86400:
        return [sprache.t("wm_kf_sperre")]
    return []


PRUEF_ZUSATZ.append(_pruefen_wach)

# ======== v1.4 C Ende ========

# ======== v1.4 D (App) – nur zwischen diesen Zeilen einfuegen ========

# ======== v1.4 D Ende ========
