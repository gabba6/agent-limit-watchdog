#!/bin/zsh
# Limit Watchdog – uninstall: unload the LaunchAgent, remove only our own Claude hooks (with backup),
# stop our caffeinate. Nothing is deleted: the plist is moved to the backups, state/logs
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

say "1/4 LaunchAgent entladen …" "1/4 Unloading the LaunchAgent …"
if launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null; then say "   entladen." "   unloaded."
else say "   war nicht geladen." "   was not loaded."; fi
if [[ -f "$PLIST" ]]; then
  mv "$PLIST" "$LW/backups/$LABEL.plist.$TS"
  say "   plist verschoben nach $LW/backups/$LABEL.plist.$TS" "   plist moved to $LW/backups/$LABEL.plist.$TS"
fi

say "2/4 Backups …" "2/4 Backups …"
cp -p "$SETTINGS" "$LW/backups/claude-settings.json.$TS"
[[ -f "$CODEX_HOOKS" ]] && cp -p "$CODEX_HOOKS" "$LW/backups/codex-hooks.json.$TS"
print -- "   $LW/backups/claude-settings.json.$TS"

say "3/4 Claude-Hooks austragen (nur die eigenen) …" "3/4 Removing Claude hooks (only our own) …"
(cd "$PROJ" && $PY -m lw.installer austragen "$SETTINGS")

say "4/4 Eigenes caffeinate beenden …" "4/4 Stopping our caffeinate …"
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
