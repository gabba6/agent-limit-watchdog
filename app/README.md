# Limit Watchdog menu bar app

A small SwiftUI `MenuBarExtra` (macOS 14+) that shows the watchdog's state and controls it.
It never talks to terminals and never buys anything: every action is a call to
`/usr/bin/python3 <project>/waechter.py …` (`status --json`, `pause`, `nacht`, `schwellen`, `report`, `app-texte`).

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
number once loaded, so `screencapture -o -l <number> shot.png` captures only that window. Point
`LIMIT_WAECHTER_PROJEKT` at a folder with a stand-in `waechter.py` to use demo data instead of your real sessions.

Installation and the autostart LaunchAgent are handled by `install.sh`.
