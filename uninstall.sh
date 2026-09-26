#!/bin/zsh
# Limit Watchdog – uninstall: unload the LaunchAgent, remove only our own Claude hooks (with backup),
# unload and move the menu bar app, stop our caffeinate. Nothing is deleted: plists and app are moved to the backups, state/logs
# (~/.limit-waechter) and the ntfy topic in the keychain are kept.
set -euo pipefail

PROJ="${0:A:h}"
PY=/usr/bin/python3
LW="${LIMIT_WAECHTER_HOME:-$HOME/.limit-waechter}"
SETTINGS="$HOME/.claude/settings.json"
CODEX_HOOKS="$HOME/.codex/hooks.json"
TS=$(date +%Y%m%d-%H%M%S)
LANGUAGE=$($PY "$PROJ/waechter.py" config-get allgemein.sprache)
LABEL=$($PY "$PROJ/waechter.py" config-get allgemein.launchagent_label)
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
say() { [[ "$LANGUAGE" == de ]] && print -- "$1" || print -- "$2"; }

mkdir -p "$LW/backups"

say "1/5 LaunchAgent entladen …" "1/5 Unloading the LaunchAgent …"
if launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null; then say "   entladen." "   unloaded."
else say "   war nicht geladen." "   was not loaded."; fi
if [[ -f "$PLIST" ]]; then
  mv "$PLIST" "$LW/backups/$LABEL.plist.$TS"
  say "   plist verschoben nach $LW/backups/$LABEL.plist.$TS" "   plist moved to $LW/backups/$LABEL.plist.$TS"
fi

say "2/5 Menüleisten-App entladen und in die Backups verschieben …" "2/5 Unloading the menu bar app and moving it to the backups …"
APP_LABEL="$LABEL.app"
APP_PLIST="$HOME/Library/LaunchAgents/$APP_LABEL.plist"
APP="$HOME/Applications/Limit-Waechter.app"
launchctl bootout "gui/$(id -u)/$APP_LABEL" 2>/dev/null || true
if [[ -f "$APP_PLIST" ]]; then
  mv "$APP_PLIST" "$LW/backups/$APP_LABEL.plist.$TS"
  say "   plist verschoben nach $LW/backups/$APP_LABEL.plist.$TS" "   plist moved to $LW/backups/$APP_LABEL.plist.$TS"
fi
if [[ -e "$APP" ]]; then
  mv "$APP" "$LW/backups/Limit-Waechter.app.$TS"
  say "   App verschoben nach $LW/backups/Limit-Waechter.app.$TS" "   app moved to $LW/backups/Limit-Waechter.app.$TS"
fi

say "3/5 Backups …" "3/5 Backups …"
cp -p "$SETTINGS" "$LW/backups/claude-settings.json.$TS"
[[ -f "$CODEX_HOOKS" ]] && cp -p "$CODEX_HOOKS" "$LW/backups/codex-hooks.json.$TS"
print -- "   $LW/backups/claude-settings.json.$TS"

say "4/5 Claude-Hooks austragen (nur die eigenen) …" "4/5 Removing Claude hooks (only our own) …"
(cd "$PROJ" && $PY -m lw.installer austragen "$SETTINGS")

say "5/5 Eigenes caffeinate beenden …" "5/5 Stopping our caffeinate …"
$PY - "$LW/state/wach.json" <<'PYEOF'
import json, os, signal, subprocess, sys
try:
    d = json.load(open(sys.argv[1]))
    pid = int(d.get("pid") or 0)
    name = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True).stdout.strip()
    if pid and name.endswith("caffeinate"):
        os.kill(pid, signal.SIGTERM)
        print(f"   caffeinate {pid}: SIGTERM")
    else:
        print("   –")
except (OSError, ValueError):
    print("   –")
PYEOF

print -- ""
say "Zurückgebaut. Erhalten bleiben: $LW (Zustand, Logs, Berichte, Backups) und das ntfy-Topic im Schlüsselbund." \
    "Uninstalled. Kept: $LW (state, logs, reports, backups) and the ntfy topic in the keychain."
say "Entfernen nur bei Bedarf und bewusst:" "Remove them only if you really want to:"
print -- "  security delete-generic-password -s limit-waechter-ntfy"
