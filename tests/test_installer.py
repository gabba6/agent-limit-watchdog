import json
import os
import shutil
import subprocess
import tempfile
import unittest

from hilfe import PROJEKT

from lw import installer

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


if __name__ == "__main__":
    unittest.main()
