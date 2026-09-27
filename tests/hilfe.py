"""Gemeinsame Testhelfer: temporärer Zustandsordner, Konfiguration, Probedaten."""

import copy
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

# Einige Fixtures enthalten Uhrzeiten als Text ("try again at 7:10 PM") aus Berlin:
# Zeitzone festlegen, damit die Tests überall gleich laufen (auch in Hook-Unterprozessen).
os.environ["TZ"] = "Europe/Berlin"
time.tzset()

PROJEKT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJEKT)
FIX = os.path.join(PROJEKT, "tests", "fixtures")

from lw import konfig, sprache  # noqa: E402


def fixture(*teile):
    return os.path.join(FIX, *teile)


def lies_fixture_json(name):
    with open(fixture(name), encoding="utf-8") as f:
        return json.load(f)


def bildschirm(name):
    with open(fixture("bildschirme", name), encoding="utf-8") as f:
        return f.read().splitlines()


class TempHome(unittest.TestCase):
    """Jeder Test bekommt einen eigenen LIMIT_WAECHTER_HOME und eine feste Uhrzeit."""

    NOW = 1790400000.0      # Sa 26.09.2026 07:20 MESZ

    def setUp(self):
        self._alt = {n: os.environ.get(n) for n in ("LIMIT_WAECHTER_HOME", "LIMIT_WAECHTER_NOW",
                                                    "LIMIT_WAECHTER_CONFIG", "LIMIT_WAECHTER_CLAUDE_SETTINGS",
                                                    "LIMIT_WAECHTER_OFFLINE")}
        self.home = tempfile.mkdtemp(prefix="lw-test-")
        os.environ["LIMIT_WAECHTER_HOME"] = self.home
        os.environ["LIMIT_WAECHTER_OFFLINE"] = "1"
        os.environ["LIMIT_WAECHTER_CONFIG"] = os.path.join(self.home, "gibt-es-nicht.toml")
        # status liest sonst ~/.claude/settings.json (Statusline-Zustand); Tests nie mit echten Dateien
        os.environ["LIMIT_WAECHTER_CLAUDE_SETTINGS"] = os.path.join(self.home, "claude-settings.json")
        self.setze_zeit(self.NOW)
        self.k = copy.deepcopy(konfig.laden())
        # Die meisten Tests prüfen die deutschen Texte; test_sprache.py prüft Englisch.
        self.k["allgemein"]["sprache"] = "de"
        sprache.setzen("de")
        self.k["daten"]["codex_sessions"] = os.path.join(self.home, "codex-sessions")
        self.k["daten"]["orca_hook_status"] = os.path.join(self.home, "orca-last-status.json")

    def tearDown(self):
        for n, w in self._alt.items():
            if w is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = w
        shutil.rmtree(self.home, ignore_errors=True)

    def setze_zeit(self, t):
        self.now = float(t)
        os.environ["LIMIT_WAECHTER_NOW"] = str(self.now)


def fenster(pct, reset, minuten=300):
    return {"pct": float(pct), "reset": reset, "minuten": minuten}


def nutzung(p5, reset5, pw=40.0, resetw=None, stand=None):
    return {"fuenf": fenster(p5, reset5), "woche": fenster(pw, resetw or reset5 + 3 * 86400, 10080),
            "stand": stand, "quelle": "test"}
