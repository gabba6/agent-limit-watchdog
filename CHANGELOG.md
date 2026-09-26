# Changelog

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
