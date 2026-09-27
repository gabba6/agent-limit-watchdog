"""Zweisprachigkeit: jeder Text in de und en, gleiche Platzhalter, englische Ausgabe wirklich englisch."""

import json
import os
import string
import subprocess
import unittest

from hilfe import PROJEKT, TempHome, nutzung

from lw import melden, sprache, texte, tick, util
from lw.attrappe import OrcaAttrappe
from lw.kontext import Kontext


def platzhalter(text):
    return sorted({f[1].split(".")[0].split("[")[0] for f in string.Formatter().parse(text) if f[1]})


class SprachtabelleTest(unittest.TestCase):
    def test_alle_schluessel_zweisprachig_mit_gleichen_platzhaltern(self):
        for schluessel, eintrag in sprache.TEXTE.items():
            with self.subTest(schluessel=schluessel):
                self.assertEqual(set(eintrag), {"de", "en"})
                self.assertEqual(platzhalter(eintrag["de"]), platzhalter(eintrag["en"]))

    def test_englisch_ohne_umlaute(self):
        for schluessel, eintrag in sprache.TEXTE.items():
            with self.subTest(schluessel=schluessel):
                self.assertNotRegex(eintrag["en"], "[äöüÄÖÜß]")

    def test_unbekannte_sprache_faellt_auf_englisch(self):
        sprache.setzen("fr")
        self.assertEqual(sprache.AKTUELL, "en")


class EnglischTest(TempHome):
    def setUp(self):
        super().setUp()
        self.k["allgemein"]["sprache"] = "en"
        sprache.setzen("en")

    def test_texte_und_zeiten(self):
        p = {"art": "woche", "pct": 93.0, "reset": self.now + 3 * 86400, "phase": "stopp", "reserve_erreicht": True,
             "pctw": 93.0}
        self.assertIn("week 93%", texte.stand(p))
        self.assertIn("the user will continue manually", texte.sicherungsauftrag(p))
        self.assertRegex(util.uhrzeit(self.now + 3 * 86400), r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d\d:\d\d$")
        self.assertEqual(util.dauer_text(5400), "1.5 h")
        sprache.setzen("en", "Alex")
        self.assertIn("hook installed by Alex", texte.sicherungsauftrag(p))

    def test_tick_meldet_englisch(self):
        orca = OrcaAttrappe()
        melder = melden.Melder(self.k, dry_run=True)
        ctx = Kontext(self.k, orca, melder, self.now, dry_run=True, claude_agenten=[])
        tick.ausfuehren(ctx, sim={"claude": nutzung(93, self.now + 3600, stand=self.now)},
                        mac_sim={"netzteil": True, "wach_bei_deckel_zu": True})
        self.assertIn("stop threshold reached", melder.protokoll[0]["text"])
        cur = util.lies_json(util.pfad("state", "current.json"))
        self.assertEqual(cur["sprache"], "en")

    def test_hook_antwortet_englisch_und_erkennt_beide_praefixe(self):
        reset = self.now + 3600
        util.schreib_json(util.pfad("state", "current.json"), {
            "version": 1, "stand": self.now, "pausiert": False, "puffer_s": 120, "hook_max_alter_s": 600,
            "sprache": "en", "name": "", "claude_stopp_art": "geordnet",
            "claude": {"phase": "stopp", "art": "fuenf", "pct": 93, "reset": reset, "fenster_id": "f",
                       "pct5": 93, "reset5": reset, "pctw": 40, "resetw": reset + 86400, "reserve_erreicht": False}})
        env = dict(os.environ, ORCA_TERMINAL_HANDLE="term_x", ORCA_PANE_KEY="a:b")

        def ruf(payload):
            r = subprocess.run(["/usr/bin/python3", os.path.join(PROJEKT, "hooks", "claude_hook.py")],
                               input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=20)
            return json.loads(r.stdout) if r.stdout.strip() else None

        basis = {"session_id": "s-en", "cwd": "/tmp", "transcript_path": "/tmp/x.jsonl"}
        out = ruf(dict(basis, hook_event_name="PreToolUse", tool_name="Agent"))
        self.assertIn("No new subagents", out["hookSpecificOutput"]["permissionDecisionReason"])
        block = ruf(dict(basis, hook_event_name="Stop", stop_hook_active=False))
        self.assertIn("WIP commit", block["reason"])
        cur = util.lies_json(util.pfad("state", "current.json"))
        cur["claude_stopp_art"] = "sanft"
        util.schreib_json(util.pfad("state", "current.json"), cur)
        out = ruf(dict(basis, session_id="s-en2", hook_event_name="PreToolUse", tool_name="Workflow"))
        self.assertIn("limit close", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(ruf(dict(basis, session_id="s-en2", hook_event_name="Stop", stop_hook_active=False)))
        for praefix in texte.PRAEFIXE:
            ruf(dict(basis, hook_event_name="UserPromptSubmit", prompt=praefix + " The usage limit has reset."))
            from lw import register
            self.assertEqual(register.lesen("claude", "s-en")["status"], "fortgesetzt")


if __name__ == "__main__":
    unittest.main()
