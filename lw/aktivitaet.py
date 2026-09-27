"""Belege, ob eine Sitzung seit einem Zeitpunkt wirklich gearbeitet hat (v1.4, nur lesend).

Hintergrund (27.09.2026): Orca meldete eine Sitzung als "working", weil nur noch ein Hintergrund-Task lief;
der Turn war längst beendet. Der Wächter glaubte das und setzte nie fort. Deshalb zählt jetzt nur, was im
Claude-Transcript bzw. in der Codex-rollout-Datei steht, zusammen mit dem Bildschirm. Orcas Zustand fließt
nicht ins Urteil ein.
"""

import json
import os

from . import quellen, texte

RELEVANT_SYSTEM = ("stop_hook_summary", "turn_duration")
SCHWANZ_BYTES = 1_048_576


def claude(transcript, seit, now=None):
    """-> {'neu', 'letzte', 'turn_offen', 'quelle'} aus dem Transcript oder None (Datei fehlt/unlesbar).

    Aktivität: assistant-Einträge und user-Einträge ohne isMeta (auch Tool-Ergebnisse). eine queue-operation
    mit unserem Prompt nach 'seit' ergibt nur 'zugestellt' (eingereiht, nicht erneut senden). Alles andere (attachment, last-prompt, mode, ai-title, file-history-*, …) zählt nicht; Sidechains
    (Unteragenten) ebenfalls nicht. Turn-Ende: system/stop_hook_summary oder system/turn_duration."""
    if not transcript or not os.path.isfile(transcript):
        return None
    zeilen = quellen.lies_schwanz(transcript, SCHWANZ_BYTES)
    letzte = None
    letztes_relevant = None          # "aktiv" | "ende"
    warteschlange = None             # letzte queue-operation nach 'seit': "enqueue" | "dequeue" | "remove"
    for zeile in zeilen:
        try:
            obj = json.loads(zeile)
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get("isSidechain"):
            continue
        typ = obj.get("type")
        if typ == "assistant" or (typ == "user" and not obj.get("isMeta")):
            ts = quellen.iso_zu_epoch(obj.get("timestamp"))
            if ts is not None and (letzte is None or ts > letzte):
                letzte = ts
            letztes_relevant = "aktiv"
        elif typ == "system" and obj.get("subtype") in RELEVANT_SYSTEM:
            letztes_relevant = "ende"
        elif typ == "queue-operation":
            # nur unser eigener Fortsetzungsprompt (Task-Benachrichtigungen u. a. werden auch eingereiht)
            inhalt = obj.get("content")
            ts = quellen.iso_zu_epoch(obj.get("timestamp"))
            if ts is not None and ts > (seit or 0) and isinstance(inhalt, str) \
                    and inhalt.lstrip().startswith(texte.PRAEFIXE):
                warteschlange = obj.get("operation")
    # Unser eingereihter Prompt (enqueue/dequeue, nicht per remove zurückgenommen) ist zugestellt, aber noch
    # keine Arbeit: nicht erneut senden, später nachsehen.
    return {"neu": bool(letzte is not None and letzte > (seit or 0)), "letzte": letzte,
            "turn_offen": None if letztes_relevant is None else letztes_relevant == "aktiv",
            "zugestellt": warteschlange in ("enqueue", "dequeue"), "quelle": "transcript"}


def codex(k, sid, seit, now):
    """Gleiche Form aus der rollout-Datei des Codex-Threads (task_started/task_complete) oder None."""
    if not sid:
        return None
    ende = f"{sid}.jsonl"
    datei = next((p for p in quellen.rollout_dateien(k["daten"]["codex_sessions"], now) if p.endswith(ende)), None)
    if not datei:
        return None
    info = quellen.codex_thread(datei)
    letzte = info.get("letzte_aktivitaet")
    return {"neu": bool(letzte and letzte > (seit or 0)), "letzte": letzte, "turn_offen": bool(info.get("laeuft")),
            "zugestellt": False, "quelle": "rollout"}


def belege(ctx, s, seit):
    """Belege für eine Sitzung (Claude: s['transcript'], Codex: rollout über die Sitzungs-ID) oder None."""
    if s.get("anbieter") == "codex":
        return codex(ctx.k, s.get("id"), seit, ctx.now)
    return claude(s.get("transcript"), seit, ctx.now)


def urteil(art, beleg, now=None, frist_s=None):
    """Bildschirm-Art + Belege -> 'arbeitet' | 'schon_fortgesetzt' | 'bereit' | 'bildschirm'.

    'bildschirm' = bisherige Behandlung nach der Bildschirm-Art (Menü, Kaufoption, stale, …)."""
    if art == "beschaeftigt":
        return "arbeitet"
    if art == "bereit":
        if beleg and beleg.get("neu"):
            return "schon_fortgesetzt"
        if beleg and beleg.get("zugestellt"):      # Nachricht liegt schon in Claudes Warteschlange
            return "arbeitet"
        # Turn laut Protokoll noch offen und eben erst aktiv: lieber nachprüfen als hineintippen
        if beleg and beleg.get("turn_offen") and beleg.get("letzte") and now is not None and frist_s \
                and now - beleg["letzte"] < frist_s:
            return "arbeitet"
        return "bereit"
    return "bildschirm"


def seit_fuer(s):
    """Ab wann Aktivität als Fortsetzung zählt: Reset des Fensters, sonst Beginn des aktuellen Status."""
    return s.get("reset") or s.get("status_seit") or 0
