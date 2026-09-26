"""Benachrichtigungen: ntfy aufs iPhone und macOS-Banner.

Das ntfy-Topic steht nur im macOS-Schlüsselbund (Dienst in config: melden.ntfy_dienst).
Nachrichten enthalten nur kurze Statustexte, keine Projektinhalte.
"""

import json
import subprocess
import urllib.request

from . import util
from .sprache import t

MELDUNGEN_DATEI = ("state", "meldungen.json")
AUFBEWAHREN_S = 14 * 86400


def topic_lesen(dienst):
    try:
        r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", dienst, "-w"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    wert = r.stdout.strip() if r.returncode == 0 else ""
    return wert or None


def topic_vorhanden(dienst):
    try:
        r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", dienst],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class Melder:
    def __init__(self, k, dry_run=False, still=False):
        self.k = k
        self.dry_run = dry_run
        self.still = still
        self.protokoll = []          # für Tests und Simulation
        self._topic = None

    def bereits(self, schluessel):
        """Nur nachsehen, ob eine Meldung mit diesem Schlüssel schon ging (ohne sie zu markieren)."""
        d = util.lies_json(util.pfad(*MELDUNGEN_DATEI), {}) or {}
        return schluessel in d

    def bereits_markieren(self, schluessel):
        """Schlüssel als erledigt vermerken, ohne zu senden (z. B. Hinweis steckte schon in einer anderen Meldung)."""
        self._schon_gesendet(schluessel)

    def _schon_gesendet(self, schluessel):
        datei = util.pfad(*MELDUNGEN_DATEI)
        with util.sperre(datei):
            d = util.lies_json(datei, {}) or {}
            jetzt = util.jetzt()
            d = {s: zeit for s, zeit in d.items() if jetzt - zeit < AUFBEWAHREN_S}
            if schluessel in d:
                return True
            d[schluessel] = jetzt
            util.schreib_json(datei, d)
            return False

    def senden(self, text, prio=3, tags=None, schluessel=None, titel=None, push=True, banner=True):
        """Gibt True zurück, wenn gemeldet (bzw. im Dry-Run protokolliert) wurde."""
        if schluessel and self._schon_gesendet(schluessel):
            return False
        titel = titel or t("app")
        modus = t("modus_dry") if self.dry_run else t("modus_still") if self.still else ""
        util.log(t("log_meldung", modus=modus, prio=prio, text=text))
        util.ereignis("meldung", text=text, prio=prio)
        self.protokoll.append({"text": text, "prio": prio, "schluessel": schluessel})
        if self.dry_run or self.still:
            return True
        if push and self.k["melden"]["ntfy"]:
            self._ntfy(text, titel, prio, tags)
        if banner and self.k["melden"]["banner"]:
            self._banner(text, titel)
        return True

    def _ntfy(self, text, titel, prio, tags):
        if self._topic is None:
            self._topic = topic_lesen(self.k["melden"]["ntfy_dienst"]) or ""
        if not self._topic:
            util.log(t("log_kein_topic"))
            return False
        nutzlast = {"topic": self._topic, "message": text, "title": titel, "priority": int(prio)}
        if tags:
            nutzlast["tags"] = list(tags)
        anfrage = urllib.request.Request(self.k["melden"]["ntfy_server"].rstrip("/") + "/",
                                         data=json.dumps(nutzlast).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(anfrage, timeout=15) as antwort:
                return 200 <= antwort.status < 300
        except Exception as e:  # Netzwerkfehler dürfen den Wächter nie stoppen
            util.log(t("log_ntfy_fehler", typ=type(e).__name__))
            return False

    def _banner(self, text, titel):
        skript = ["-e", "on run argv", "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
                  "-e", "end run"]
        try:
            subprocess.run(["/usr/bin/osascript", *skript, text, titel], capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            util.log(t("log_banner_fehler"))
