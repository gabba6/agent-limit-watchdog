"""Hook-Einträge in ~/.claude/settings.json ein- und austragen (von install.sh/uninstall.sh aufgerufen).

Nur eigene Einträge (erkennbar am Pfad hooks/claude_hook.py) werden angefasst. Vor dem Schreiben
wird geprüft, dass alle fremden Einträge (Orca, git-schutz.sh, Einstellungen) unverändert bleiben.
Seit 1.3 außerdem die Statusline-Kette (hooks/statusline.py): 'statusline-ein' sichert die bisherige statusLine
nach state/statusline-original.json und trägt unsere ein, 'statusline-aus' stellt das Original wieder her.
Aufruf: python3 -m lw.installer eintragen|austragen|pruefen|statusline-ein|statusline-aus <settings.json>
"""

import copy
import json
import os
import shlex
import shutil
import sys
import tempfile
import time

from . import konfig, util
from .sprache import t

MARKER = "# limit-watchdog-hook"          # Shell-Kommentar am Ende des Hook-Befehls
HOOK_DATEI = "hooks/claude_hook.py"
TIMEOUT = 10
EINTRAEGE = [
    ("SessionStart", None),
    ("UserPromptSubmit", None),
    ("PreToolUse", "Agent|Task|Workflow"),
    ("PostToolUse", "*"),
    ("Stop", None),
    ("StopFailure", "rate_limit"),
    ("Notification", "quota_auto_resume_fired|quota_auto_resume_stale|quota_auto_resume_disabled|"
                     "quota_auto_resume_armed|permission_prompt"),
    ("PermissionDenied", "*"),
    ("SessionEnd", None),
]


SL_MARKER = "# limit-watchdog-statusline"   # Shell-Kommentar am Ende des Statusline-Befehls
SL_DATEI = "hooks/statusline.py"
SL_ORIGINAL = ("state", "statusline-original.json")  # relativ zu util.basis(): {"version", "gesichert", "statusLine"}


def ist_unsere_statusline(eintrag):
    return isinstance(eintrag, dict) and SL_MARKER in str(eintrag.get("command") or "")


def statusline_zustand(settings, original_datei=None):
    """-> 'aktiv' (unsere Kette steht in settings.json) | 'zurueckgeschrieben' (Original gesichert, aber
    der Eintrag ist nicht mehr unserer, z. B. von Orca ersetzt) | 'aus' (nie eingerichtet)."""
    if ist_unsere_statusline((settings or {}).get("statusLine")):
        return "aktiv"
    datei = original_datei or util.pfad(*SL_ORIGINAL)
    return "zurueckgeschrieben" if os.path.exists(datei) else "aus"


def statusline_befehl():
    pfad = os.path.join(util.PROJEKT, *SL_DATEI.split("/"))
    befehl = f"/usr/bin/python3 {shlex.quote(pfad)} {SL_MARKER}"
    assert "agent-hooks/claude-statusline" not in befehl     # sonst hielte Orca den Eintrag für seinen
    return befehl


def statusline_ein(settings, sichern):
    """-> neue settings mit unserer Statusline. sichern(original) wird nur aufgerufen, wenn der aktuelle Eintrag
    nicht unserer ist (idempotent). Übrige Schlüssel des Originals (padding, refreshInterval …) bleiben."""
    s = copy.deepcopy(settings)
    aktuell = s.get("statusLine")
    if not ist_unsere_statusline(aktuell):
        sichern(copy.deepcopy(aktuell) if "statusLine" in s else None)
    neu = dict(aktuell) if isinstance(aktuell, dict) else {}
    neu["type"] = "command"
    neu["command"] = statusline_befehl()
    s["statusLine"] = neu
    return s


def statusline_aus(settings, original):
    """-> (neue settings, geändert?). Nur wenn der aktuelle Eintrag unserer ist;
    original None = statusLine entfernen."""
    if not ist_unsere_statusline(settings.get("statusLine")):
        return settings, False
    s = copy.deepcopy(settings)
    if original is None:
        del s["statusLine"]
    else:
        s["statusLine"] = copy.deepcopy(original)
    return s, True


def _backup_ziel(name):
    """Freier Name backups/<name>.<TS>[-n] (nie ein vorhandenes Backup überschreiben)."""
    basis = util.pfad("backups", name + "." + time.strftime("%Y%m%d-%H%M%S"))
    ziel, n = basis, 1
    while os.path.exists(ziel):
        ziel, n = f"{basis}-{n}", n + 1
    return ziel


def _original_sichern(original):
    datei = util.pfad(*SL_ORIGINAL)
    # eigene atomare Schreibung statt util.schreib_json: ohne sort_keys, damit die Schlüsselreihenfolge des
    # Originals beim Zurückschreiben erhalten bleibt
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(datei), prefix=".lw-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "gesichert": util.jetzt(), "statusLine": original}, f, indent=1, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, datei)
    kopie = _backup_ziel("statusline-original.json")
    shutil.copy2(datei, kopie)
    print(t("inst_sl_gesichert", datei=kopie))


def hook_befehl():
    pfad = os.path.join(util.PROJEKT, "hooks", "claude_hook.py")
    return f"/usr/bin/python3 {shlex.quote(pfad)} {MARKER}"


def _ist_unser_befehl(befehl):
    befehl = str(befehl)
    if MARKER in befehl:
        return True
    # ältere Einträge ohne Markierung (Installationen vor 1.0.0)
    return HOOK_DATEI in befehl and ("Limit-Waechter" in befehl or "limit-watchdog" in befehl)


def _ist_unser(gruppe):
    return any(_ist_unser_befehl(h.get("command", "")) for h in (gruppe.get("hooks") or []) if isinstance(h, dict))


def fremde_teile(settings, ohne_statusline=False):
    """Kopie ohne unsere Gruppen (zum Vergleich vorher/nachher); ohne_statusline: auch ohne statusLine
    (nur beim Statusline-Wechsel, der selbst eigens geprüft wird)."""
    s = copy.deepcopy(settings)
    if ohne_statusline:
        s.pop("statusLine", None)
    hooks = s.get("hooks") or {}
    for ev in list(hooks):
        hooks[ev] = [g for g in hooks[ev] if not _ist_unser(g)]
        if not hooks[ev]:
            del hooks[ev]
    if "hooks" in s and not s["hooks"]:
        del s["hooks"]
    return s


def austragen(settings):
    s = fremde_teile(settings)
    if "hooks" not in s and "hooks" in settings:
        s["hooks"] = {}
    return s


def eintragen(settings, befehl=None):
    s = austragen(settings)
    hooks = s.setdefault("hooks", {})
    for ev, matcher in EINTRAEGE:
        gruppe = {}
        if matcher:
            gruppe["matcher"] = matcher
        gruppe["hooks"] = [{"type": "command", "command": befehl or hook_befehl(), "timeout": TIMEOUT}]
        hooks.setdefault(ev, []).append(gruppe)
    return s


def anzahl_eigene(settings):
    return sum(1 for gruppen in (settings.get("hooks") or {}).values() for g in gruppen if _ist_unser(g))


def _schreiben(datei, daten):
    text = json.dumps(daten, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(datei), prefix=".lw-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    shutil.copymode(datei, tmp)
    os.replace(tmp, datei)


def main(argv):
    konfig.laden()                      # setzt die Sprache der Ausgaben
    if len(argv) != 2 or argv[0] not in ("eintragen", "austragen", "pruefen", "statusline-ein", "statusline-aus"):
        print("python3 -m lw.installer eintragen|austragen|pruefen|statusline-ein|statusline-aus <settings.json>")
        return 2
    aktion, datei = argv
    with open(datei, encoding="utf-8") as f:
        vorher = json.load(f)
    if aktion == "pruefen":
        print(anzahl_eigene(vorher))
        return 0
    if aktion.startswith("statusline-"):
        return _statusline(aktion, datei, vorher)
    nachher = eintragen(vorher) if aktion == "eintragen" else austragen(vorher)
    if fremde_teile(nachher) != fremde_teile(vorher):
        print(t("inst_abbruch"))
        return 1
    _schreiben(datei, nachher)
    print(t("inst_ok_" + aktion, anzahl=anzahl_eigene(nachher), datei=datei))
    return 0


def _statusline(aktion, datei, vorher):
    orig_datei = util.pfad(*SL_ORIGINAL)
    if aktion == "statusline-ein":
        gesichert = []
        nachher = statusline_ein(vorher, gesichert.append)
        pruefen = gesichert[0] if gesichert else None
    else:
        gesichert = util.lies_json(orig_datei)
        if not ist_unsere_statusline(vorher.get("statusLine")):
            print(t("inst_sl_fremd"))
            if os.path.exists(orig_datei):       # veraltet: in die Backups (sonst meldet status "zurückgeschrieben")
                os.replace(orig_datei, _backup_ziel("statusline-original.json"))
            return 0
        if not isinstance(gesichert, dict):
            print(t("inst_sl_ohne_original"))
        nachher, _ = statusline_aus(vorher, (gesichert or {}).get("statusLine") if isinstance(gesichert, dict)
                                    else None)
        pruefen = None
    if fremde_teile(nachher, True) != fremde_teile(vorher, True):
        print(t("inst_abbruch"))
        return 1
    if aktion == "statusline-ein":
        if gesichert:
            _original_sichern(pruefen)
        if nachher != vorher:
            _schreiben(datei, nachher)
        print(t("inst_sl_ein", datei=datei))
        return 0
    _schreiben(datei, nachher)
    if os.path.exists(orig_datei):
        os.replace(orig_datei, _backup_ziel("statusline-original.json"))
    print(t("inst_sl_aus", datei=datei))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
