# Changelog

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
