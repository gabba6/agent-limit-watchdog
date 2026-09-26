import json
import os
import shutil
import tempfile
import time
import unittest

from hilfe import TempHome, fixture, lies_fixture_json

from lw import konfig, quellen


class KonfigTest(unittest.TestCase):
    def test_parser_teilmenge(self):
        d = konfig.parse_toml('''
# Kommentar
[schwellen]
warnung = 75   # Kommentar hinter Wert
stopp = 90.5
[fortsetzen]
claude_limit_resume = "orca"
text = "a # kein Kommentar \\u00e4 \\"x\\""
liste = ["a", 'b', 3, true]
aktiv = false
''')
        self.assertEqual(d["schwellen"], {"warnung": 75, "stopp": 90.5})
        self.assertEqual(d["fortsetzen"]["claude_limit_resume"], "orca")
        self.assertEqual(d["fortsetzen"]["text"], 'a # kein Kommentar ä "x"')
        self.assertEqual(d["fortsetzen"]["liste"], ["a", "b", 3, True])
        self.assertIs(d["fortsetzen"]["aktiv"], False)

    def test_fehler(self):
        with self.assertRaises(konfig.KonfigFehler):
            konfig.parse_toml("x = \"offen")
        with self.assertRaises(konfig.KonfigFehler):
            konfig.parse_toml("nur text")

    def test_projekt_config_gueltig(self):
        datei = os.path.join(os.path.dirname(fixture()), "..", "config.toml")
        k = konfig.laden(datei, streng=True)
        # Standardwerte nur aus config.toml: eigene Schwellen in config.local.toml dürfen den Test nicht brechen
        with open(datei, encoding="utf-8") as f:
            s = konfig.parse_toml(f.read())["schwellen"]
        self.assertEqual((s["warnung"], s["stopp"], s["wochen_reserve"]), (80, 92, 20))
        self.assertEqual(k["fortsetzen"]["max_pro_fenster"], 2)
        befehl = k["fortsetzen"]["claude_befehl"]
        self.assertTrue(os.path.isabs(befehl) or befehl == "claude", befehl)   # CI-Runner ohne Claude Code

    def test_programm_suche(self):
        tmp = tempfile.mkdtemp(prefix="lw-prog-")
        try:
            programm = os.path.join(tmp, "claude")
            with open(programm, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(programm, 0o755)
            self.assertEqual(konfig.finde_programm("~/x/claude", "claude"), os.path.expanduser("~/x/claude"))
            alt = os.environ.get("PATH", "")
            os.environ["PATH"] = tmp
            try:
                self.assertEqual(konfig.finde_programm("", "claude"), programm)
                self.assertEqual(konfig.finde_programm("", "gibt-es-nicht-xyz"), "gibt-es-nicht-xyz")
            finally:
                os.environ["PATH"] = alt
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ungueltige_schwellen_fallen_auf_standard(self):
        home = TempHome("run")
        home.setUp()
        try:
            datei = os.path.join(home.home, "c.toml")
            with open(datei, "w") as f:
                f.write("[schwellen]\nwarnung = 95\nstopp = 90\n")
            self.assertEqual(konfig.laden(datei)["schwellen"]["warnung"], 80)
            with self.assertRaises(konfig.KonfigFehler):
                konfig.laden(datei, streng=True)
        finally:
            home.tearDown()


class QuellenTest(TempHome):
    def test_orca_limits(self):
        d = quellen.orca_limits(lies_fixture_json("orca_account_list.json")["result"])
        self.assertEqual(d["claude"]["fuenf"]["pct"], 93.0)
        self.assertEqual(d["claude"]["fuenf"]["reset"], 1790433000.0)
        self.assertEqual(d["claude"]["woche"]["pct"], 45.0)
        self.assertAlmostEqual(d["claude"]["stand"], 1790415814.037)
        self.assertEqual(d["codex"]["reset_credits"], 1)
        self.assertEqual(quellen.orca_limits({})["claude"]["fuenf"], None)

    def test_codex_snapshot_und_premium(self):
        with open(fixture("rollout-2026-09-20T17-25-00-01a0bf6b-ae1f-7de0-8b05-aa0baa8a6479.jsonl")) as f:
            zeilen = f.read().splitlines()
        snaps = [quellen.codex_snapshot(json.loads(z)) for z in zeilen if '"rate_limits"' in z]
        self.assertEqual(snaps[0]["fuenf"]["pct"], 90.0)
        self.assertEqual(snaps[0]["woche"]["reset"], 1790400000)
        self.assertAlmostEqual(snaps[0]["credits"], 120.50)
        self.assertIsNone(snaps[1], "limit_id premium ohne Fenster wird ignoriert")

    def _sessions(self):
        tag = os.path.join(self.home, "codex-sessions", time.strftime("%Y/%m/%d", time.localtime(self.now)))
        os.makedirs(tag, exist_ok=True)
        pfade = []
        for name in ("rollout-2026-09-20T17-25-00-01a0bf6b-ae1f-7de0-8b05-aa0baa8a6479.jsonl",
                     "rollout-2026-09-26T01-30-00-01a0da88-ad20-7542-b024-9d2ddfe7cc90.jsonl"):
            ziel = os.path.join(tag, name)
            shutil.copy(fixture(name), ziel)
            pfade.append(ziel)
        os.utime(pfade[0], (self.now - 100, self.now - 100))
        os.utime(pfade[1], (self.now - 10, self.now - 10))
        return pfade

    def test_codex_nutzung_nimmt_neuesten(self):
        self._sessions()
        dateien = quellen.rollout_dateien(os.path.join(self.home, "codex-sessions"), self.now)
        self.assertEqual(len(dateien), 2)
        n = quellen.codex_nutzung(dateien)
        self.assertEqual(n["fuenf"]["pct"], 3.0)
        self.assertAlmostEqual(n["credits"], 98.25)

    def test_codex_thread_limit(self):
        alt, neu = self._sessions()
        info = quellen.codex_thread(alt)
        self.assertEqual(info["id"], "01a0bf6b-ae1f-7de0-8b05-aa0baa8a6479")
        self.assertEqual(info["cwd"], "/tmp/projekt")
        self.assertFalse(info["laeuft"])
        self.assertIsNotNone(info["limit"])
        # 7:10 PM passt zum Snapshot-Reset 1789924214 (19:10:14 MESZ) -> exakter Wert aus dem Snapshot
        self.assertEqual(info["limit"]["reset"], 1789924214)
        info2 = quellen.codex_thread(neu)
        self.assertIsNone(info2["limit"])
        self.assertFalse(info2["laeuft"])

    def test_zeit_aus_text(self):
        bezug = time.mktime((2026, 9, 26, 12, 0, 0, 0, 0, -1))
        t = time.localtime(quellen.zeit_aus_text("7:10 PM", bezug))
        self.assertEqual((t.tm_mday, t.tm_hour, t.tm_min), (26, 19, 10))
        t = time.localtime(quellen.zeit_aus_text("6:30am", bezug))
        self.assertEqual((t.tm_mday, t.tm_hour, t.tm_min), (27, 6, 30))
        t = time.localtime(quellen.zeit_aus_text("Sun 3am", bezug))
        self.assertEqual((t.tm_wday, t.tm_hour), (6, 3))
        t = time.localtime(quellen.zeit_aus_text("Oct 3rd, 2026 3:00 PM", bezug))
        self.assertEqual((t.tm_mon, t.tm_mday, t.tm_hour), (10, 3, 15))
        self.assertIsNone(quellen.zeit_aus_text("bald", bezug))

    def test_claude_transcript(self):
        lim = quellen.claude_limit_aus_transcript(fixture("transcript_limit.jsonl"))
        self.assertEqual(lim["reset"], 1790267400, "Sidechain-Eintrag (Subagent) wird übersprungen")
        self.assertEqual(lim["art"], "five_hour")
        self.assertEqual(lim["status"], "rejected")
        self.assertFalse(lim["ueberziehung"])
        self.assertEqual(quellen.art_kurz("seven_day"), "woche")
        self.assertEqual(quellen.art_kurz("five_hour"), "fuenf")
        self.assertIsNone(quellen.claude_limit_aus_transcript("/gibt/es/nicht.jsonl"))

    def test_claude_reset_text(self):
        bezug = time.mktime((2026, 9, 24, 16, 17, 0, 0, 0, -1))
        t = time.localtime(quellen.claude_reset_aus_text(
            "You've hit your session limit · resets 6:30pm (Europe/Berlin)", bezug))
        self.assertEqual((t.tm_mday, t.tm_hour, t.tm_min), (24, 18, 30))

    def test_planlimit_text(self):
        self.assertTrue(quellen.PLANLIMIT_TEXT.search("You've hit your session limit · resets 6:30pm"))
        self.assertTrue(quellen.PLANLIMIT_TEXT.search("You've hit your weekly limit"))
        self.assertFalse(quellen.PLANLIMIT_TEXT.search("API Error: Rate limit reached"))
        self.assertFalse(quellen.PLANLIMIT_TEXT.search("Server is temporarily limiting requests"))

    def test_orca_pane_sitzungen(self):
        m = quellen.orca_pane_sitzungen(fixture("orca_last_status.json"))
        self.assertEqual(m["tab2:leaf2"]["anbieter"], "codex")
        self.assertEqual(m["tab2:leaf2"]["id"], "01a0bf6b-ae1f-7de0-8b05-aa0baa8a6479")
        self.assertEqual(quellen.orca_pane_sitzungen("/gibt/es/nicht"), {})


if __name__ == "__main__":
    unittest.main()
