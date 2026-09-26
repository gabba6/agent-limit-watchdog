"""Mac wach halten, solange eine Fortsetzung geplant ist (caffeinate -i -s bis Reset + Nachlauf).

-s wirkt nur am Netzteil; zugeklappt hilft nur der Remote-Modus (wird nur geprüft, nie geschaltet).
"""

import os
import subprocess

from . import util
from .sprache import t

DATEI = ("state", "wach.json")


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
    d = util.lies_json(util.pfad(*DATEI), {}) or {}
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
    util.schreib_json(util.pfad(*DATEI), {"pid": p.pid, "bis": bis, "gestartet": now})
    return t("wach_start", zeit=util.uhrzeit(bis, now), pid=p.pid)
