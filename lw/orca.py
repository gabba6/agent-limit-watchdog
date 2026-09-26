"""Orca-CLI (immer mit absolutem Pfad, /usr/local/bin/orca ist nicht lesbar).

Lesen ist immer erlaubt. Senden/Erstellen passiert im Dry-Run nie, sondern wird nur protokolliert.
Handles werden nie zwischengespeichert, sondern bei jedem Tick neu gelesen.
"""

import json
import os
import subprocess

from . import util
from .sprache import t


class OrcaFehler(RuntimeError):
    pass


def pane_key(terminal):
    return f"{terminal.get('tabId')}:{terminal.get('leafId')}"


class Orca:
    def __init__(self, pfad, dry_run=False, timeout=30):
        self.pfad = pfad
        self.dry_run = dry_run
        self.timeout = timeout
        self.gesendet = []   # Protokoll (auch im Dry-Run)

    def _aufruf(self, args, timeout=None):
        try:
            r = subprocess.run([self.pfad, *args, "--json"], capture_output=True, text=True,
                               timeout=timeout or self.timeout)
        except subprocess.TimeoutExpired:
            raise OrcaFehler(t("orca_zeit", befehl=" ".join(args[:2])))
        except OSError as e:
            raise OrcaFehler(t("orca_start", fehler=e))
        try:
            d = json.loads(r.stdout)
        except ValueError:
            raise OrcaFehler(t("orca_json", befehl=" ".join(args[:2]), code=r.returncode))
        if d.get("ok") is False:
            fehler = d.get("error") or {}
            raise OrcaFehler(str(fehler.get("message") if isinstance(fehler, dict) else fehler)[:300])
        return d.get("result") or {}

    # ---------------------------------------------------------- lesen
    def vorhanden(self):
        """Ist Orca installiert (Programm ausführbar)? Ohne Orca läuft der Wächter trotzdem (v1.3)."""
        return bool(self.pfad) and os.access(self.pfad, os.X_OK)

    def erreichbar(self):
        try:
            r = self._aufruf(["status"], timeout=20)
        except OrcaFehler:
            return False
        return bool((r.get("runtime") or {}).get("reachable"))

    def konten(self):
        return self._aufruf(["account", "list"])

    def terminals(self):
        return self._aufruf(["terminal", "list"]).get("terminals") or []

    def agenten(self):
        """paneKey -> Agentenzustand aus `worktree ps` (state working/done/waiting …)."""
        ergebnis = {}
        for w in self._aufruf(["worktree", "ps"]).get("worktrees") or []:
            for a in w.get("agents") or []:
                if a.get("paneKey"):
                    eintrag = dict(a)
                    eintrag["worktree"] = w.get("path")
                    ergebnis[a["paneKey"]] = eintrag
        return ergebnis

    def bildschirm(self, handle):
        term = self._aufruf(["terminal", "read", "--terminal", handle, "--screen"]).get("terminal") or {}
        tail = term.get("tail") or []
        if isinstance(tail, str):
            tail = tail.splitlines()
        return {"zeilen": tail, "quelle": term.get("source"), "status": term.get("status")}

    # ---------------------------------------------------------- schreiben
    def senden(self, handle, text=None, enter=True, warten=60):
        """-> {'angenommen', 'gestartet', 'request', 'dry_run', 'fehler'}"""
        eintrag = {"handle": handle, "text": text, "enter": enter}
        self.gesendet.append(eintrag)
        if self.dry_run:
            util.log(t("orca_dry_senden", handle=handle, was="Enter" if not text else repr(text[:60])))
            return {"angenommen": True, "gestartet": False, "dry_run": True}
        args = ["terminal", "send", "--terminal", handle]
        if text:
            args += ["--text", text]
        if enter:
            args.append("--enter")
        if text and enter and warten:
            args += ["--wait-submit", str(int(warten))]
        try:
            r = self._aufruf(args, timeout=(warten or 0) + 40)
        except OrcaFehler as e:
            return {"angenommen": False, "gestartet": False, "fehler": str(e)}
        send = r.get("send") or {}
        prompt = send.get("prompt") or {}
        stufen = prompt.get("stages") or []
        return {"angenommen": bool(send.get("accepted")), "gestartet": "turn_started" in stufen,
                "stufen": stufen, "request": prompt.get("requestId")}

    def erstellen(self, worktree, befehl, titel):
        self.gesendet.append({"erstellen": worktree, "befehl": befehl})
        if self.dry_run:
            util.log(t("orca_dry_erstellen", wo=worktree, befehl=befehl[:120]))
            return {"handle": None, "dry_run": True}
        r = self._aufruf(["terminal", "create", "--worktree", worktree, "--command", befehl, "--title", titel])
        term = r.get("terminal") or r
        return {"handle": term.get("handle")}
