"""Claude-Hook mit Beispiel-Payloads per stdin (wie Claude Code ihn aufruft)."""

import json
import os
import shutil
import subprocess
import time
import unittest

from hilfe import PROJEKT, TempHome, fixture

from lw import register, util

HOOK = os.path.join(PROJEKT, "hooks", "claude_hook.py")


class HookTest(TempHome):
    SID = "11111111-2222-3333-4444-555555555555"
    sprache = "de"

    def setUp(self):
        super().setUp()
        self.reset = self.now + 3600
        self.current("ok")

    def current(self, phase, pct=None, reserve=False, stand=None, reset=None):
        reset = reset or self.reset
        pct = pct if pct is not None else {"ok": 20, "warnung": 82, "stopp": 93, "limit": 100}[phase]
        util.schreib_json(util.pfad("state", "current.json"), {
            "version": 1, "stand": stand or self.now, "pausiert": False, "puffer_s": 120, "reserve_sperre": True,
            "hook_max_alter_s": 600, "sprache": self.sprache, "name": "",
            "claude": {"phase": phase, "art": "fuenf", "pct": pct, "reset": reset,
                       "fenster_id": f"claude-fuenf-{int(round(reset / 600))}", "pct5": pct, "reset5": reset,
                       "pctw": 85.0 if reserve else 40.0, "resetw": self.now + 3 * 86400,
                       "reserve_erreicht": reserve}})

    def ruf(self, ev, orca=True, **felder):
        payload = {"session_id": self.SID, "transcript_path": "/tmp/gibt-es-nicht.jsonl", "cwd": "/tmp/projekt",
                   "permission_mode": "auto", "hook_event_name": ev}
        payload.update(felder)
        env = dict(os.environ)
        for n in list(env):
            if n.startswith("ORCA_"):
                del env[n]
        if orca:
            env.update({"ORCA_TERMINAL_HANDLE": "term_test", "ORCA_PANE_KEY": "tabT:leafT",
                        "ORCA_WORKTREE_ID": "repo-1::/tmp/projekt"})
        start = time.time()
        r = subprocess.run(["/usr/bin/python3", HOOK], input=json.dumps(payload), capture_output=True, text=True,
                           env=env, timeout=20)
        self.dauer = time.time() - start
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        return json.loads(r.stdout) if r.stdout.strip() else None

    def sitzung(self):
        return register.lesen("claude", self.SID) or {}

    # ------------------------------------------------------------ PreToolUse
    def test_deny_im_stopp(self):
        self.current("stopp")
        out = self.ruf("PreToolUse", tool_name="Agent", tool_input={})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Limit-Wächter", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(self.ruf("PreToolUse", tool_name="Workflow")["hookSpecificOutput"]["permissionDecision"],
                         "deny")
        self.assertIsNone(self.ruf("PreToolUse", tool_name="Bash"), "normale Werkzeuge bleiben erlaubt")
        # auch in Subagents keine neuen Agents
        self.assertIsNotNone(self.ruf("PreToolUse", tool_name="Agent", agent_id="sub1"))

    def test_kein_deny_wenn_ok_veraltet_pausiert_oder_ausserhalb_orca(self):
        self.assertIsNone(self.ruf("PreToolUse", tool_name="Agent"))
        self.current("stopp", stand=self.now - 3600)
        self.assertIsNone(self.ruf("PreToolUse", tool_name="Agent"), "veralteter Zustand -> nie blockieren")
        self.current("stopp", reset=self.now - 10)
        self.assertIsNone(self.ruf("PreToolUse", tool_name="Agent"), "Reset vorbei -> nicht mehr blockieren")
        self.current("stopp")
        util.schreib_json(util.pfad("state", "pause.json"), {"aktiv": True, "bis": None})
        self.assertIsNone(self.ruf("PreToolUse", tool_name="Agent"))
        util.schreib_json(util.pfad("state", "pause.json"), {"aktiv": False})
        self.assertIsNone(self.ruf("PreToolUse", orca=False, tool_name="Agent"), "nur Orca-Terminals")

    # ------------------------------------------------------------ PostToolUse / Stop
    def test_stopp_ablauf(self):
        self.ruf("SessionStart", source="startup")
        s = self.sitzung()
        self.assertEqual((s["terminal"], s["pane_key"], s["worktree"]), ("term_test", "tabT:leafT", "/tmp/projekt"))
        self.current("stopp")
        post = self.ruf("PostToolUse", tool_name="Bash")
        self.assertIn("Stopp-Phase", post["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.ruf("PostToolUse", tool_name="Bash"), "nur einmal je Fenster")
        self.assertIsNone(self.ruf("PostToolUse", tool_name="Bash", agent_id="sub"), "Subagents ignorieren")
        block = self.ruf("Stop", stop_hook_active=False, last_assistant_message="…")
        self.assertEqual(block["decision"], "block")
        self.assertIn("WIP-Commit", block["reason"])
        self.assertEqual(self.sitzung()["status"], "sicherung")
        self.assertIsNone(self.ruf("Stop", stop_hook_active=True))
        s = self.sitzung()
        self.assertEqual(s["status"], "gestoppt")
        self.assertEqual(s["fortsetzen_ab"], self.reset + 120)
        # nächster Turn im selben Fenster: kein zweiter Block
        self.ruf("UserPromptSubmit", prompt="noch eine Frage")
        self.assertIsNone(self.ruf("Stop", stop_hook_active=False))
        self.assertEqual(self.sitzung()["status"], "gestoppt")

    def test_sicherungsauftrag_bei_reserve_ohne_fortsetzungsversprechen(self):
        self.current("stopp", reserve=True)
        block = self.ruf("Stop", stop_hook_active=False)
        self.assertIn("keine automatische Fortsetzung", block["reason"])
        self.assertTrue(self.sitzung()["reserve_bei_halt"])

    def test_stop_hook_active_blockt_nie(self):
        self.current("stopp")
        self.assertIsNone(self.ruf("Stop", stop_hook_active=True))
        self.assertEqual(self.sitzung()["status"], "gestoppt")

    def test_sicherung_endet_auch_nach_reset_als_gestoppt(self):
        self.current("stopp")
        self.ruf("Stop", stop_hook_active=False)
        self.current("ok", reset=self.now + 5 * 3600)
        self.ruf("Stop", stop_hook_active=True)
        self.assertEqual(self.sitzung()["status"], "gestoppt")

    def test_stop_im_ok_setzt_aktiv(self):
        self.current("stopp")
        self.ruf("Stop", stop_hook_active=True)
        self.current("ok", reset=self.now + 5 * 3600)
        self.ruf("UserPromptSubmit", prompt="Limit-Wächter: Das Nutzungslimit ist zurückgesetzt. …")
        self.assertEqual(self.sitzung()["status"], "fortgesetzt")
        self.ruf("Stop", stop_hook_active=False)
        self.assertEqual(self.sitzung()["status"], "aktiv")

    # ------------------------------------------------------------ StopFailure
    def test_stopfailure_limit_aus_transcript(self):
        tr = os.path.join(self.home, "t.jsonl")
        shutil.copy(fixture("transcript_limit.jsonl"), tr)
        self.setze_zeit(1790267400 - 3000)      # kurz nach dem Eintrag
        self.current("warnung", reset=1790267400)
        self.ruf("StopFailure", error="rate_limit", transcript_path=tr,
                 last_assistant_message="You've hit your session limit · resets 6:30pm (Europe/Berlin)")
        s = self.sitzung()
        self.assertEqual((s["status"], s["reset"], s["art"]), ("limit", 1790267400, "fuenf"))
        self.assertEqual(s["fortsetzen_ab"], 1790267400 + 120)
        self.assertFalse(s["ueberziehung"])

    def test_stopfailure_drossel_ist_kein_limit(self):
        self.ruf("StopFailure", error="rate_limit", last_assistant_message="API Error: Rate limit reached")
        self.assertNotEqual(self.sitzung().get("status"), "limit")
        self.ruf("StopFailure", error="overloaded", last_assistant_message="overloaded")
        self.assertNotEqual(self.sitzung().get("status"), "limit")

    # ------------------------------------------------------------ Notification / Prompt / Ende
    def test_notifications(self):
        self.current("limit")
        self.ruf("Notification", notification_type="quota_auto_resume_fired", message="x")
        self.assertEqual(self.sitzung()["status"], "eingebaut_fortgesetzt")
        self.ruf("Notification", notification_type="quota_auto_resume_stale", message="x")
        s = self.sitzung()
        self.assertEqual(s["status"], "stale")
        self.assertLessEqual(s["fortsetzen_ab"], self.now + 1)
        self.ruf("Notification", notification_type="quota_auto_resume_disabled", message="x")
        self.assertEqual(self.sitzung()["status"], "disabled")

    def test_reserve_sperrt_eingebaute_fortsetzung(self):
        self.current("ok", reserve=True)
        out = self.ruf("UserPromptSubmit", prompt="Your claude.ai usage limit has reset. Continue the task you were "
                                                  "working on when the limit was reached; do not repeat work.")
        self.assertEqual(out["decision"], "block")
        self.assertEqual(self.sitzung()["status"], "reserve")
        self.current("ok", reserve=False)
        self.assertIsNone(self.ruf("UserPromptSubmit", prompt="Your claude.ai usage limit has reset. Continue."))
        self.assertEqual(self.sitzung()["status"], "eingebaut_fortgesetzt")

    def test_prompt_hinweis_im_stopp(self):
        self.current("stopp")
        out = self.ruf("UserPromptSubmit", prompt="mach weiter")
        self.assertIn("gesperrt", out["hookSpecificOutput"]["additionalContext"])

    def test_session_end(self):
        self.ruf("SessionStart", source="startup")
        self.ruf("SessionEnd", reason="prompt_input_exit")
        self.assertEqual(self.sitzung()["status"], "beendet")

    def test_permission_denied_protokolliert(self):
        self.ruf("PermissionDenied", tool_name="Bash", tool_input={"command": "geheim"}, reason="[Irreversible]")
        e = util.lies_ereignisse()
        self.assertEqual(e[-1]["typ"], "freigabe_blockiert")
        self.assertNotIn("geheim", json.dumps(e), "keine Befehlsinhalte im Bericht")

    def test_kaputte_eingabe(self):
        r = subprocess.run(["/usr/bin/python3", HOOK], input="kein json", capture_output=True, text=True, timeout=20)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_schnell(self):
        self.current("stopp")
        self.ruf("PreToolUse", tool_name="Agent")
        self.assertLess(self.dauer, 1.0, "Hook muss schnell sein")


if __name__ == "__main__":
    unittest.main()
