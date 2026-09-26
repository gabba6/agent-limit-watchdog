#!/bin/zsh
# Baut Limit-Waechter.app (SwiftUI-Menüleisten-App) und signiert sie ad hoc.
# Aufruf: app/build.sh [--ausgabe DIR] [--projekt PFAD]
# Kein Netzwerk, kein Developer-Account, keine Installation (das macht install.sh).
set -euo pipefail

APP_DIR="${0:A:h}"
PROJEKT="${APP_DIR:h}"
AUSGABE="$APP_DIR/build"
PY=/usr/bin/python3

while (( $# > 0 )); do
  case "$1" in
    --ausgabe) AUSGABE="${2:?--ausgabe braucht einen Pfad}"; shift 2 ;;
    --projekt) PROJEKT="${2:?--projekt braucht einen Pfad}"; shift 2 ;;
    *) print -u2 "Unbekannte Option: $1"; exit 2 ;;
  esac
done
PROJEKT="${PROJEKT:A}"
[[ -f "$PROJEKT/waechter.py" ]] || { print -u2 "waechter.py fehlt in $PROJEKT"; exit 1; }
mkdir -p "$AUSGABE"
AUSGABE="${AUSGABE:A}"

LABEL="$("$PY" "$PROJEKT/waechter.py" config-get allgemein.launchagent_label)"
VERSION="$("$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); import lw; print(lw.VERSION)' "$PROJEKT")"
TITEL="$("$PY" "$PROJEKT/waechter.py" app-texte 2>/dev/null \
  | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["texte"]["app_titel"])' 2>/dev/null || true)"
[[ -n "$TITEL" ]] || TITEL="Limit-Waechter"

swift build -c release --package-path "$APP_DIR" >&2
BIN="$(swift build -c release --package-path "$APP_DIR" --show-bin-path)/LimitWaechter"

APP="$AUSGABE/Limit-Waechter.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/LimitWaechter"

"$PY" - "$APP/Contents/Info.plist" "$LABEL.app" "$VERSION" "$TITEL" "$PROJEKT" <<'PYEOF'
import plistlib, sys
pfad, kennung, version, titel, projekt = sys.argv[1:6]
daten = {
    "CFBundleIdentifier": kennung,
    "CFBundleExecutable": "LimitWaechter",
    "CFBundleName": titel,
    "CFBundleDisplayName": titel,
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": version,
    "CFBundleVersion": version,
    "CFBundleInfoDictionaryVersion": "6.0",
    "LSMinimumSystemVersion": "14.0",
    "LSUIElement": True,
    "NSHighResolutionCapable": True,
    "LWProjekt": projekt,
}
with open(pfad, "wb") as f:
    plistlib.dump(daten, f)
PYEOF

codesign --force --sign - --timestamp=none "$APP" >&2
codesign --verify --strict "$APP" >&2
print -r -- "$APP"
