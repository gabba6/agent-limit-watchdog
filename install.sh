#!/bin/zsh
# Limit Watchdog – install (idempotent, safe to run again)
#   ./install.sh          tests, backups, Claude hooks, ntfy topic, LaunchAgent
#   ./install.sh hooks    only tests, backups and Claude hooks (no LaunchAgent)
# Undo: ./uninstall.sh
set -euo pipefail

PROJ="${0:A:h}"
PY=/usr/bin/python3
LW="${LIMIT_WAECHTER_HOME:-$HOME/.limit-waechter}"
SETTINGS="$HOME/.claude/settings.json"
CODEX_HOOKS="$HOME/.codex/hooks.json"
MODUS="${1:-alles}"
[[ "$MODUS" == all ]] && MODUS=alles
TS=$(date +%Y%m%d-%H%M%S)

[[ -x $PY ]] || { print -- "/usr/bin/python3 not found (install the Xcode Command Line Tools: xcode-select --install)"; exit 1; }
LANGUAGE=$($PY "$PROJ/waechter.py" config-get allgemein.sprache)
LABEL=$($PY "$PROJ/waechter.py" config-get allgemein.launchagent_label)
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
say() { [[ "$LANGUAGE" == de ]] && print -- "$1" || print -- "$2"; }

[[ "$MODUS" == alles || "$MODUS" == hooks ]] || { say "Aufruf: install.sh [hooks]" "Usage: install.sh [hooks]"; exit 2; }
[[ -f "$SETTINGS" ]] || { say "~/.claude/settings.json fehlt – ist Claude Code installiert?" \
                             "~/.claude/settings.json is missing – is Claude Code installed?"; exit 1; }

say "1/6 Tests mit Probedaten …" "1/6 Running tests with sample data …"
if ! (cd "$PROJ/tests" && $PY -m unittest -q 2>&1 | tail -3); then   # pipefail: unittest exit code counts
  say "Tests fehlgeschlagen – nichts installiert." "Tests failed – nothing installed."; exit 1
fi

say "2/6 Backups nach $LW/backups/ …" "2/6 Backups to $LW/backups/ …"
mkdir -p "$LW/backups" "$LW/log" "$LW/state"
chmod 700 "$LW"
cp -p "$SETTINGS" "$LW/backups/claude-settings.json.$TS"
print -- "   $LW/backups/claude-settings.json.$TS"
if [[ -f "$CODEX_HOOKS" ]]; then
  cp -p "$CODEX_HOOKS" "$LW/backups/codex-hooks.json.$TS"
  say "   $LW/backups/codex-hooks.json.$TS (Codex-Hooks bleiben unverändert)" \
      "   $LW/backups/codex-hooks.json.$TS (Codex hooks stay unchanged)"
fi

say "3/6 Claude-Hooks eintragen (Hooks anderer Tools bleiben unberührt) …" \
    "3/6 Adding Claude hooks (hooks of other tools stay untouched) …"
(cd "$PROJ" && $PY -m lw.installer eintragen "$SETTINGS")
$PY -c "import json,sys; json.load(open(sys.argv[1]))" "$SETTINGS" || {
  say "settings.json ungültig – stelle Backup wieder her" "settings.json invalid – restoring backup"
  cp -p "$LW/backups/claude-settings.json.$TS" "$SETTINGS"; exit 1; }

if [[ "$MODUS" == hooks ]]; then
  say "Fertig (nur Hooks). Ohne LaunchAgent bleiben die Hooks passiv." \
      "Done (hooks only). Without the LaunchAgent the hooks stay passive."
  exit 0
fi

say "4/6 ntfy-Topic im Schlüsselbund …" "4/6 ntfy topic in the keychain …"
$PY "$PROJ/waechter.py" ntfy-setup

say "5/6 Erster Tick …" "5/6 First tick …"
$PY "$PROJ/waechter.py" tick

say "6/6 LaunchAgent $LABEL …" "6/6 LaunchAgent $LABEL …"
mkdir -p "$HOME/Library/LaunchAgents"
$PY - "$PLIST" "$PROJ" "$LW" "$HOME" "$LABEL" <<'PYEOF'
import plistlib, sys
plist, proj, lw, home, label = sys.argv[1:6]
daten = {
    "Label": label,
    "ProgramArguments": ["/usr/bin/python3", f"{proj}/waechter.py", "tick"],
    "StartInterval": 60,
    "RunAtLoad": True,
    "AbandonProcessGroup": True,
    "ProcessType": "Standard",
    "StandardOutPath": f"{lw}/log/launchd.out.log",
    "StandardErrorPath": f"{lw}/log/launchd.err.log",
    "EnvironmentVariables": {
        "PATH": f"{home}/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "en_US.UTF-8",
    },
}
with open(plist, "wb") as f:
    plistlib.dump(daten, f)
PYEOF
plutil -lint "$PLIST" >/dev/null
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl print "gui/$(id -u)/$LABEL" >/dev/null && say "   geladen." "   loaded."

print -- ""
$PY "$PROJ/waechter.py" status
print -- ""
say "Installiert. iPhone: waechter.py ntfy-abo (Topic in die Zwischenablage), dann waechter.py test-push." \
    "Installed. iPhone: waechter.py ntfy-subscribe (copies the topic), then waechter.py test-push."
