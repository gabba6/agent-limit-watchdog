import json
import os
import shutil
import subprocess
import tempfile
import unittest

from hilfe import PROJEKT, TempHome

from lw import installer, util

ORCA = "if [ -z \"${HOME-}\" ]; then printf '{}\\n'; fi  # orca-wrapper"
BEISPIEL = {
    "permissions": {"allow": ["Edit(~/x/**)"]},
    "model": "opus[1m]",
    "hooks": {
        "SessionStart": [{"hooks": [{"type": "command", "command": ORCA, "timeout": 10}]}],
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "$HOME/.claude/hooks/git-schutz.sh",
                                           "if": "Bash(git *)", "timeout": 10}]},
            {"matcher": "*", "hooks": [{"type": "command", "command": ORCA, "timeout": 10}]}],
        "Stop": [{"hooks": [{"type": "command", "command": ORCA, "timeout": 10}]}],
    },
    "statusLine": {"type": "command", "command": ORCA},
}


class InstallerTest(unittest.TestCase):
    def test_eintragen_austragen(self):
        s = installer.eintragen(json.loads(json.dumps(BEISPIEL)))
        self.assertEqual(installer.anzahl_eigene(s), len(installer.EINTRAEGE))
        self.assertEqual(installer.fremde_teile(s), BEISPIEL)
        self.assertEqual(s["hooks"]["PreToolUse"][-1]["matcher"], "Agent|Task|Workflow")
        self.assertEqual(s["hooks"]["StopFailure"][0]["matcher"], "rate_limit")
        self.assertIn(os.path.join(PROJEKT, "hooks", "claude_hook.py"), s["hooks"]["Stop"][-1]["hooks"][0]["command"])
        # idempotent
        s2 = installer.eintragen(s)
        self.assertEqual(installer.anzahl_eigene(s2), len(installer.EINTRAEGE))
        self.assertEqual(installer.austragen(s2), BEISPIEL)

    def test_alte_eintraege_ohne_markierung_werden_erkannt(self):
        alt = json.loads(json.dumps(BEISPIEL))
        alt["hooks"]["Stop"].append({"hooks": [{"type": "command", "timeout": 10, "command":
            "/usr/bin/python3 /Users/x/Projects/Tools/Limit-Waechter/hooks/claude_hook.py"}]})
        self.assertEqual(installer.anzahl_eigene(alt), 1)
        neu = installer.eintragen(alt)
        self.assertEqual(installer.anzahl_eigene(neu), len(installer.EINTRAEGE), "alter Eintrag ersetzt, nicht doppelt")
        self.assertEqual(installer.austragen(neu), BEISPIEL)

    def test_beliebiger_ordnername_dank_markierung(self):
        befehl = "/usr/bin/python3 '/Users/x/code/agent limit watchdog/hooks/claude_hook.py' " + installer.MARKER
        s = installer.eintragen(json.loads(json.dumps(BEISPIEL)), befehl)
        self.assertEqual(installer.anzahl_eigene(s), len(installer.EINTRAEGE))
        self.assertEqual(installer.austragen(s), BEISPIEL)
        self.assertFalse(installer._ist_unser_befehl("/usr/bin/python3 /opt/anderes-tool/hooks/claude_hook.py"))

    def test_cli_an_kopie_der_echten_settings(self):
        echt = os.path.expanduser("~/.claude/settings.json")
        if not os.path.exists(echt):
            self.skipTest("keine echte settings.json")
        tmp = tempfile.mkdtemp(prefix="lw-inst-")
        try:
            kopie = os.path.join(tmp, "settings.json")
            shutil.copy2(echt, kopie)
            with open(kopie, "rb") as f:
                original = f.read()
            if installer.anzahl_eigene(json.loads(original)):
                subprocess.run(["/usr/bin/python3", "-m", "lw.installer", "austragen", kopie], cwd=PROJEKT, check=True,
                               capture_output=True)
                with open(kopie, "rb") as f:
                    original = f.read()
            for aktion in ("eintragen", "eintragen", "austragen"):
                r = subprocess.run(["/usr/bin/python3", "-m", "lw.installer", aktion, kopie], cwd=PROJEKT,
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(kopie, "rb") as f:
                self.assertEqual(f.read(), original, "Austragen stellt die Datei byte-genau wieder her")
            self.assertEqual(os.stat(kopie).st_mode, os.stat(echt).st_mode)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class StatuslineInstallerTest(TempHome):
    """v1.3: Statusline-Kette über die CLI an einer Kopie im Wegwerf-HOME."""

    def setUp(self):
        super().setUp()
        self.settings = os.path.join(self.home, "settings.json")
        self.orig = os.path.join(self.home, "state", "statusline-original.json")

    def schreib(self, daten):
        with open(self.settings, "w", encoding="utf-8") as f:
            f.write(json.dumps(daten, indent=2, ensure_ascii=False) + "\n")
        os.chmod(self.settings, 0o644)
        with open(self.settings, "rb") as f:
            return f.read()

    def lies(self):
        with open(self.settings, encoding="utf-8") as f:
            return json.load(f)

    def cli(self, aktion):
        r = subprocess.run(["/usr/bin/python3", "-m", "lw.installer", aktion, self.settings], cwd=PROJEKT,
                           capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def backups(self):
        return sorted(n for n in os.listdir(os.path.join(self.home, "backups")) if n.startswith("statusline-original"))

    def test_ein_idempotent_aus_stellt_her(self):
        vorher = json.loads(json.dumps(BEISPIEL))
        vorher["statusLine"]["padding"] = 2
        roh = self.schreib(vorher)
        self.cli("eintragen")
        self.cli("statusline-ein")
        s = self.lies()
        self.assertTrue(installer.ist_unsere_statusline(s["statusLine"]))
        self.assertEqual(s["statusLine"]["padding"], 2)
        self.assertNotIn("agent-hooks/claude-statusline", s["statusLine"]["command"])
        self.assertIn(os.path.join(PROJEKT, "hooks", "statusline.py"), s["statusLine"]["command"])
        self.assertEqual(installer.fremde_teile(s, True), installer.fremde_teile(installer.eintragen(vorher), True))
        g = util.lies_json(self.orig)
        self.assertEqual((g["version"], g["statusLine"]), (1, vorher["statusLine"]))
        self.assertEqual(os.stat(self.orig).st_mode & 0o777, 0o600)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(installer.statusline_zustand(s, self.orig), "aktiv")
        self.cli("statusline-ein")                    # idempotent: Original nicht mit unserem überschrieben
        self.assertEqual(util.lies_json(self.orig)["statusLine"], vorher["statusLine"])
        self.assertEqual(len(self.backups()), 1)
        self.cli("statusline-aus")
        self.cli("austragen")
        with open(self.settings, "rb") as f:
            self.assertEqual(f.read(), roh, "byte-genau wiederhergestellt")
        self.assertFalse(os.path.exists(self.orig), "Original in die Backups verschoben")
        self.assertEqual(len(self.backups()), 2)
        self.assertEqual(installer.statusline_zustand(self.lies(), self.orig), "aus")

    def test_ohne_bisherige_statusline(self):
        vorher = json.loads(json.dumps(BEISPIEL))
        del vorher["statusLine"]
        roh = self.schreib(vorher)
        self.cli("statusline-ein")
        self.assertIsNone(util.lies_json(self.orig)["statusLine"])
        self.assertEqual(self.lies()["statusLine"]["type"], "command")
        self.cli("statusline-aus")
        with open(self.settings, "rb") as f:
            self.assertEqual(f.read(), roh)

    def test_fremder_eintrag_nach_rueckschreibung_bleibt(self):
        self.schreib(BEISPIEL)
        self.cli("statusline-ein")
        s = self.lies()
        s["statusLine"] = {"type": "command", "command": "~/.orca/agent-hooks/claude-statusline"}
        self.schreib(s)
        self.assertEqual(installer.statusline_zustand(s, self.orig), "zurueckgeschrieben")
        self.cli("statusline-aus")
        self.assertEqual(self.lies(), s, "fremder Eintrag nicht angefasst")
        # veraltetes Original wandert in die Backups (nicht gelöscht), status meldet danach "aus"
        self.assertFalse(os.path.exists(self.orig))
        self.assertTrue(any(n.startswith("statusline-original.json.")
                            for n in os.listdir(os.path.join(self.home, "backups"))))
        self.assertEqual(installer.statusline_zustand(s, self.orig), "aus")
        # erneutes Einrichten sichert den neuen Eintrag als Original
        self.cli("statusline-ein")
        self.assertEqual(util.lies_json(self.orig)["statusLine"], s["statusLine"])

    def test_funktionen(self):
        gesichert = []
        s = installer.statusline_ein({"statusLine": {"type": "command", "command": "x", "refreshInterval": 5}},
                                     gesichert.append)
        self.assertEqual(gesichert, [{"type": "command", "command": "x", "refreshInterval": 5}])
        self.assertEqual(s["statusLine"]["refreshInterval"], 5)
        self.assertEqual(installer.statusline_ein(s, gesichert.append), s)
        self.assertEqual(len(gesichert), 1)
        self.assertEqual(installer.statusline_aus(s, None), ({}, True))
        fremd = {"statusLine": {"type": "command", "command": "y"}}
        self.assertEqual(installer.statusline_aus(fremd, None), (fremd, False))
        self.assertEqual(installer.statusline_zustand({}, self.orig), "aus")
        # Hooks-Aktionen dürfen die Statusline nicht verändern
        self.assertNotEqual(installer.fremde_teile(s), installer.fremde_teile({}))


if __name__ == "__main__":
    unittest.main()
