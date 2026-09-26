"""Wo läuft eine Sitzung (Orca / Terminal / Desktop) und was kann der Wächter dort (v1.3).

Ort:
  orca      Claude: ORCA_TERMINAL_HANDLE im Hook gesetzt; Codex: Thread einem Orca-Terminal zugeordnet
  terminal  Claude: normales Terminal oder IDE (CLAUDE_CODE_ENTRYPOINT cli, claude-vscode …;
            headless sdk-*/mcp und remote werden ignoriert);
            Codex: rollout mit originator "codex-tui"
  desktop   Claude: CLAUDE_CODE_ENTRYPOINT "claude-desktop"/"desktop"/"local-agent" (vermutlich, noch nicht bestätigt);
            Codex: rollout mit originator "Codex Desktop"

Fähigkeiten je Sitzung: warnen / stoppen / fortsetzen, jeweils "ja" | "nein" | "push" ("push" = nur Push mit
Kopierbefehl, der Wächter selbst setzt nicht fort). Außerhalb von Orca wird nie getippt und nie ein Bildschirm gelesen.
"""

ORTE = ("orca", "terminal", "desktop")
DESKTOP_ENTRYPOINTS = ("claude-desktop", "desktop", "local-agent")
IGNORIERT_ENTRYPOINTS = ("remote", "sdk-cli", "sdk-ts", "sdk-py", "mcp")  # Web bzw. headless (claude -p, SDK)
CODEX_ORIGINATOR = {"codex-tui": "terminal", "Codex Desktop": "desktop"}


def ort_claude(env):
    """Ort einer Claude-Sitzung aus der Hook-Umgebung. None = ignorieren (z. B. Claude Code im Web)."""
    if env.get("ORCA_TERMINAL_HANDLE"):
        return "orca"
    ep = (env.get("CLAUDE_CODE_ENTRYPOINT") or "").strip()
    if ep in IGNORIERT_ENTRYPOINTS:
        return None
    if ep in DESKTOP_ENTRYPOINTS:
        return "desktop"
    return "terminal"


def ort_codex(originator):
    """Ort eines Codex-Threads außerhalb von Orca aus session_meta.originator. None = nicht überwachen."""
    return CODEX_ORIGINATOR.get(originator or "")


def ort(s):
    """Ort einer Registerzeile; ältere Einträge (vor 1.3) ohne 'ort': mit Terminal-Handle/Pane = Orca."""
    o = s.get("ort")
    if o in ORTE:
        return o
    return "orca" if (s.get("terminal") or s.get("pane_key")) else "terminal"


def codex_queue_an(k):
    """Codex außerhalb von Orca per `codex queue` stoppen/fortsetzen? Standard aus: im Echttest nicht belegbar
    (Codex verlangt für neue Ordner eine dauerhafte Vertrauensfreigabe)."""
    return bool(k["fortsetzen"].get("codex_queue", False))


def faehigkeiten(s, k, orca_ok=True):
    """-> {'warnen', 'stoppen', 'fortsetzen'} mit Werten 'ja' | 'nein' | 'push'."""
    f = k["fortsetzen"]
    o = ort(s)
    anbieter = s.get("anbieter")
    warnen = "ja"
    if o == "orca":
        if anbieter == "codex":
            stoppen = "ja" if (f.get("codex_stopp_senden", True) and orca_ok) else "nein"
        else:
            stoppen = "ja"                      # Claude-Hooks wirken auch ohne laufendes Orca
        fortsetzen = "ja" if orca_ok else "push"
    elif anbieter == "claude":
        stoppen = "ja"                          # Hooks greifen (sonst stünde die Sitzung nicht im Register)
        fortsetzen = "push"                     # nur Claudes eingebautes Auto-Continue am Limit, sonst Push
    elif o == "terminal" and codex_queue_an(k):
        stoppen = "ja" if f.get("codex_stopp_senden", True) else "nein"
        fortsetzen = "ja"
    else:
        stoppen = "nein"
        fortsetzen = "push"
    if not f.get("aktiv", True):
        fortsetzen = "nein"
    return {"warnen": warnen, "stoppen": stoppen, "fortsetzen": fortsetzen}


def kopierbefehl(s):
    """Befehl zum Weitermachen von Hand (Push/Status), ohne Pfade oder Projektnamen."""
    sid = str(s.get("id") or "")
    return f"claude --resume {sid}" if s.get("anbieter") == "claude" else f"codex resume {sid}"
