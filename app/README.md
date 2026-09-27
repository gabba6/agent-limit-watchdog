# Limit Watchdog menu bar app

A small SwiftUI `MenuBarExtra` (macOS 14+) that shows the watchdog's state and controls it.
It never talks to terminals and never buys anything: every action is a call to
`/usr/bin/python3 <project>/waechter.py …` (`status --json`, `pause`, `nacht`, `wach`, `schwellen`, `report`,
`app-texte`).

Layout (v1.4), top to bottom:

- **Status banner** – the overall state in one sentence (`gesamt` from `status --json`: all good, warning,
  stop, limit, sessions waiting, paused, watchdog not running).
- **Usage cards** for Claude and Codex – 5-hour value large, week smaller, bars with markers at the warning and
  stop thresholds, reset times and the data source with its age (orange when stale or when the official usage
  display reports an error; the tooltip says why).
- **Sessions** – project, location and a coloured state chip (working, waiting until …, "continue" needed,
  blocked …), sorted by what needs attention; night mode per session via the moon.
- **Quick switches** – night mode for all sessions, awake mode (`wach an|aus`; the password dialog comes from
  `waechter.py`, the app never sees the password) and pause (30 min, 2 h, until resumed).
- **Settings** (collapsed) – thresholds and notes (status line chain, Orca, official usage display, awake details).

The app refreshes every 30 s, every 10 s while the popover is open and a stop, limit or waiting session is shown.
Older `status --json` output without the v1.4 fields still works (the app derives what it needs).

Build (no network, ad-hoc signature):

```sh
app/build.sh [--ausgabe DIR] [--projekt PATH]   # prints the path of Limit-Waechter.app
```

The project path is stored in `Info.plist` (`LWProjekt`) and can be overridden with
`LIMIT_WAECHTER_PROJEKT`. All texts come from `lw/sprache.py` via `waechter.py app-texte`.

Checks without GUI:

```sh
Limit-Waechter.app/Contents/MacOS/LimitWaechter --version
Limit-Waechter.app/Contents/MacOS/LimitWaechter --selbsttest tests/fixtures/app/status.json
```

Screenshots: `LimitWaechter --vorschau` shows the popover content in a normal window and prints its window
number once loaded, so `screencapture -o -l <number> shot.png` captures only that window.
With demo data and without screen recording permission:

```sh
LimitWaechter --vorschau --demo tests/fixtures/app/status.json [--hell|--dunkel] --bild shot.png
```

`--demo` reads the status from the file (all buttons do nothing), `--bild` renders the window to a PNG and quits.

Installation and the autostart LaunchAgent are handled by `install.sh`.
