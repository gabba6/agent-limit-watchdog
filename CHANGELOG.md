# Changelog

## 1.3.0 – 2026-09-26

Without Orca. Orca is now optional.

- Claude Code in **normal terminals** is watched too: the hooks register the session with its location
  (`orca` / `terminal` / `desktop`, new `lw/orte.py`), warn, deny new subagents/workflows and give the checkpoint
  request (tested live). Claude Desktop is recognised by `CLAUDE_CODE_ENTRYPOINT` (probably; not confirmed).
  Headless runs outside Orca (`claude -p`, Agent SDK) and Claude Code on the web are ignored.
- Outside Orca the watchdog never types, reads screens or opens windows. Claude continues only through its built-in
  auto-continue (with night mode); otherwise a push with a command to copy (`claude --resume <id>`).
- Codex outside Orca: sessions found from recent rollout files (`originator`); warning and push with
  `codex resume <id>`. Experimental, untested option `[fortsetzen] codex_queue = true`: stop message and
  continuation via `codex queue`. The Codex app is display/warning only.
- New **status line chain** (`hooks/statusline.py`): `install.sh` wraps the existing `statusLine`, stores Claude's
  usage in `state/statusline.json` and runs the original unchanged; `uninstall.sh` restores it. The fresher of
  Orca and status line wins. If the status line gets replaced, `status` and the app show a hint.
- Without Orca installed: no Orca calls, errors or “Orca unreachable” pushes.
- New option `[allgemein] nur_orca` (`true` = behaviour up to 1.2).
- `status` and the app show location and capabilities per session and the state of the status line chain;
  `status --json` has new keys (`orca_vorhanden`, `nur_orca`, `statusline`, per session `ort`, `ort_text`,
  `faehigkeiten`, `faehigkeiten_text`, `automatisch`); existing keys are unchanged.

## 1.2.0 – 2026-09-26

Menu bar app.

- New optional **SwiftUI menu bar app** (macOS 14+): ring icon with the highest 5-hour usage (coloured from the
  warning phase on, moon in night mode), popover with a card per provider (5 h and weekly rings, phase, reset,
  countdown), current sessions, pause (30 min / 2 h / open / off), night mode for all or per session, thresholds,
  report and log. It only calls `waechter.py`; it never types into terminals.
- `./install.sh app` builds it with `swift build`, signs it ad hoc, copies it to `~/Applications` and adds a
  login LaunchAgent `<label>.app`; `./uninstall.sh` unloads it and moves app and plist to the backups.
- New command `thresholds` / `schwellen` (`set warn=80 stop=92 weekly_warn=… weekly_stop=… weekly_reserve=…`,
  `--json`): validated, writes only `[schwellen]` in `config.local.toml`, keeps comments.
- `status --json` has new keys (`version`, `jetzt`, `sprache`, `pause_bis`, `letzter_tick`, `nur_mit_nachtmodus`,
  `bericht_uhrzeit`, `schwellen`, per session `projekt`, `status_text` and `wartet`); existing keys are unchanged.
- `night`/`nacht` and `thresholds`/`schwellen` work in both languages. Config validation messages are translated.
- CI also builds the app and runs its self-test.

## 1.1.0 – 2026-09-26

Night mode. **Behaviour change:** automatic continuation after the reset is now opt-in per session.

- The warning and the orderly stop still run for all sessions.
- Only sessions in **night mode** are continued automatically after the reset. All other sessions wait for you
  to type "continue"; Claude's built-in auto-continue is blocked for them too. You get one push per provider
  ("limit has reset – n session(s) waiting for you to type \"continue\"").
- Night mode lasts until the next report time (`[bericht] uhrzeit`, default 08:00) and then switches itself off.
- Switch it on with `waechter.py night on [session|all]` (German: `nacht an`), or type `#night` / `#nacht` in a
  Claude session (the hook catches it, nothing goes to the model; works via Remote Control). Codex only via the
  command. `night off`, `#night off` switch it off; `night` shows the current state. Switched on after the reset,
  it still picks up sessions that have been waiting for less than 12 hours.
- `status` shows night mode globally and per session; `status --json` has `nacht` / `nacht_bis`.
- New session status `wartet_auf_weiter`; morning report lists waiting sessions, blocked built-in continuations
  and night-mode changes. `caffeinate` and the night warning only run for sessions that will be continued.
- `[fortsetzen] nur_mit_nachtmodus = false` restores the 1.0 behaviour (continue everything).

## 1.0.0 – 2026-09-26

First public release.

- Watches the 5-hour and weekly usage of Claude Code and Codex running in Orca terminals (data from Orca and
  Codex session files; no extra API calls).
- Phases OK → warning (80 %) → orderly stop (92 %) → limit, per provider; weekly reserve (80 %).
- Claude Code hooks: deny new subagents/workflows in the stop phase, one checkpoint request per session and
  window, limit detection from the transcript, tracking of Claude's built-in auto-continue.
- Codex: orderly stop via a short message, limit detection from the rollout files.
- Continuing after the reset with a screen check before every keystroke (menus, purchase options and unclear
  screens are never typed into), at most two attempts per session and window, restart via `--resume` if the
  terminal is gone.
- ntfy push notifications (topic stored in the keychain) and macOS banners, morning report, `caffeinate` while
  a continuation is pending, night warning if the Mac would sleep.
- English and German texts (`sprache = "en" | "de"`), `config.local.toml` for personal settings.
- `install.sh` / `uninstall.sh` with backups; the installer only touches its own hook entries.
- Setup prompt for coding agents (`docs/SETUP_PROMPT.md`).
