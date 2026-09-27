# Setup prompt for your coding agent

Copy everything in the box below into **Claude Code or Codex** (running on the Mac where you want the watchdog).
The agent checks your setup, explains what it will change, asks you a few questions, installs with backups and
verifies the result. It never spends money and does not use model calls for testing.

Before you paste it: clone the repository (`git clone https://github.com/gabba6/agent-limit-watchdog.git`) and
start the agent **inside that folder**.

---

```text
You are helping me install "Agent Limit Watchdog" (https://github.com/gabba6/agent-limit-watchdog) on this Mac.
The current directory is the cloned repository. Work step by step, explain briefly what you do, and stop to ask
me whenever a step needs a decision or changes something outside this folder.

Hard rules (never break them):
- Never spend money: do not enable or buy extra usage, credits, plan upgrades or rate-limit reset credits,
  and never select an option in a usage-limit or purchase menu.
- Do not test with model calls (no `claude -p`, no `codex exec`). Use the test suite, `simulate` and `--dry-run`.
- Change global configuration (~/.claude/settings.json, ~/.codex/hooks.json, LaunchAgents) only through
  ./install.sh or ./uninstall.sh, which create backups. Never edit or remove hooks that belong to other tools.
- Never print, log or commit secrets. The ntfy topic is stored in the macOS keychain only; do not display it.
- Do not delete files. Do not push anything.

1. Read first: README.md, docs/ARCHITECTURE.md, install.sh, uninstall.sh, config.toml and hooks/claude_hook.py.
   Summarise for me in a few sentences what the watchdog will do on this Mac and which files it changes.

2. Check the prerequisites and report each result:
   - macOS, and /usr/bin/python3 works (`/usr/bin/python3 --version`, 3.9 or newer).
   - Orca (optional): /Applications/Orca.app/Contents/Resources/bin/orca exists, and
     `/Applications/Orca.app/Contents/Resources/bin/orca status --json` reports the runtime as reachable.
     Without Orca the watchdog still works in normal terminals (see README, "Where the watchdog can do what").
   - Claude Code is 2.1.234 or newer (`claude --version`) and ~/.claude/settings.json exists.
   - Codex CLI (optional): `codex --version`.
   - Amphetamine (optional, free; keeps the Mac awake with the lid closed): /Applications/Amphetamine.app exists.
   - Only if Orca is installed, read-only data check: `/Applications/Orca.app/Contents/Resources/bin/orca account list --json` contains
     result.rateLimits.claude (and .codex if used). Show me only the percentages, nothing else from that output.
   If something is missing, stop and tell me what to install. Do not install it yourself without asking.

3. Run the tests and the dry runs, and show me the short results:
   - `cd tests && /usr/bin/python3 -m unittest -q`
   - `./waechter.py simulate cycle`   (full cycle with sample data and a fake Orca; nothing is sent)
   - `./waechter.py tick --dry-run`   (one run against my real data on a copy of the state; nothing is sent)
   If a test fails, stop and show me the failure.

4. Ask me, one question at a time, with your recommendation:
   - Language of notifications and texts: English or German (`sprache = "en" | "de"`).
   - Optional: my first name for the texts the hooks show to Claude.
   - Thresholds: keep the defaults (warn 80 %, orderly stop 92 %, weekly reserve 20 %) or change them.
   - Whether sessions should be continued automatically after the reset (`[fortsetzen] aktiv = true/false`), and whether only sessions in night mode are continued (`nur_mit_nachtmodus = true`, default; `false` = continue every session, as in 1.0).
   - Whether to read the official usage numbers (`[daten] offiziell = true`, default). Explain honestly: it is an
     undocumented, read-only usage endpoint (the one Claude Desktop / ChatGPT use for their usage display) that
     uses my existing Claude Code / Codex login; the token is never stored, logged or renewed; `false` = Orca /
     status line only. Do not call these endpoints yourself during setup.
   - Whether the Mac should be kept awake automatically while night mode is on (`[wach] bei_nachtmodus = true`,
     default). Mention `./waechter.py awake on|off` (asks for my password in a macOS dialog; do not run it for me).
   Write my answers into config.local.toml (create it if needed; it is ignored by git). Only put the values I
   want to change there, and validate with `./waechter.py status`.

5. Tell me exactly what ./install.sh will change (hooks in ~/.claude/settings.json, a LaunchAgent,
   a keychain item, the state folder ~/.limit-waechter) and wait for my OK. Then run `./install.sh`.
   Afterwards:
   - Show the diff between ~/.claude/settings.json and the newest backup in ~/.limit-waechter/backups/
     and confirm that only lines were added and no existing hook was changed.
   - Confirm that ~/.codex/hooks.json is unchanged.
   - Run `./waechter.py status` and check that the LaunchAgent is loaded and the last tick is recent.
   Optional menu bar app: ask me whether I want it. It needs macOS 14+ and the Xcode Command Line Tools
   (`swift`). If yes, tell me that `./install.sh app` builds and ad-hoc signs it, copies it to ~/Applications
   and adds a login LaunchAgent, wait for my OK, then run it.

6. Notifications (optional): tell me to install the free ntfy app, then run `./waechter.py ntfy-subscribe`
   (it copies the topic to the clipboard without printing it) and guide me through subscribing. After I
   confirm, run `./waechter.py test-push`.

7. Finish with a short summary: what is installed, where the logs are (~/.limit-waechter/log/waechter.log),
   how to pause (`./waechter.py pause`, `pause off`), how to see what happened (`./waechter.py report`) and
   how to remove everything (`./uninstall.sh`, which keeps backups and deletes nothing).
```
