"""Hook-Einträge in ~/.claude/settings.json ein- und austragen (von install.sh/uninstall.sh aufgerufen).

Nur eigene Einträge (erkennbar am Pfad hooks/claude_hook.py) werden angefasst. Vor dem Schreiben
wird geprüft, dass alle fremden Einträge (Orca, git-schutz.sh, Einstellungen) unverändert bleiben.
Aufruf: python3 -m lw.installer eintragen|austragen|pruefen <settings.json>
"""

import copy
import json
import os
import shlex
import shutil
import sys
import tempfile

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


def fremde_teile(settings):
    """Kopie ohne unsere Gruppen (zum Vergleich vorher/nachher)."""
    s = copy.deepcopy(settings)
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
    if len(argv) != 2 or argv[0] not in ("eintragen", "austragen", "pruefen"):
        print("python3 -m lw.installer eintragen|austragen|pruefen <settings.json>")
        return 2
    aktion, datei = argv
    with open(datei, encoding="utf-8") as f:
        vorher = json.load(f)
    if aktion == "pruefen":
        print(anzahl_eigene(vorher))
        return 0
    nachher = eintragen(vorher) if aktion == "eintragen" else austragen(vorher)
    if fremde_teile(nachher) != fremde_teile(vorher):
        print(t("inst_abbruch"))
        return 1
    _schreiben(datei, nachher)
    print(t("inst_ok_" + aktion, anzahl=anzahl_eigene(nachher), datei=datei))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
