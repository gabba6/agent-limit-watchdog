"""Kontext eines Durchlaufs: Konfiguration, Zeit, Orca, Melder und zwischengespeicherte Orca-Antworten."""

import json
import subprocess

from . import util
from .orca import OrcaFehler, pane_key


class Kontext:
    def __init__(self, k, orca, melder, now, dry_run=False, claude_agenten=None):
        self.k = k
        self.orca = orca
        self.melder = melder
        self.now = now
        self.dry_run = dry_run
        self._terminals = None
        self._agenten = None
        self._claude_agenten = claude_agenten
        self.orca_fehler = None
        self.aktionen = []      # was dieser Durchlauf getan hat (für Log/Simulation)

    def terminals(self):
        if self._terminals is None:
            try:
                self._terminals = self.orca.terminals()
            except OrcaFehler as e:
                self.orca_fehler = str(e)
                self._terminals = []
        return self._terminals

    def agent_terminals(self, anbieter):
        """Nur Terminals mit agentIdentity claude oder codex (Projektregel)."""
        return [t for t in self.terminals()
                if t.get("agentIdentity") == anbieter and t.get("connected", True)
                and not t.get("orphaned") and t.get("writable", True)]

    def agenten(self):
        if self._agenten is None:
            try:
                self._agenten = self.orca.agenten()
            except OrcaFehler as e:
                self.orca_fehler = str(e)
                self._agenten = {}
        return self._agenten

    def agent_zustand(self, terminal):
        return (self.agenten().get(pane_key(terminal)) or {}).get("state")

    def claude_agenten(self):
        """`claude agents --json` (kein Modellaufruf): laufende Claude-Sitzungen mit pid."""
        if self._claude_agenten is None:
            befehl = self.k["fortsetzen"]["claude_befehl"]
            try:
                r = subprocess.run(["/usr/bin/perl", "-e", "alarm 25; exec @ARGV", befehl, "agents", "--json"],
                                   capture_output=True, text=True, timeout=30)
                daten = json.loads(r.stdout)
                self._claude_agenten = daten if isinstance(daten, list) else []
            except (OSError, ValueError, subprocess.SubprocessError):
                self._claude_agenten = None
                return None
        return self._claude_agenten

    def aktion(self, text):
        self.aktionen.append(text)
        util.log(("DRY-RUN " if self.dry_run else "") + text)
