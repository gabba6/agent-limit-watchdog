"""User-facing texts in German and English (config: allgemein.sprache = "de" | "en").

Nutzertexte auf Deutsch und Englisch. Jeder Schlüssel hat beide Sprachen mit denselben Platzhaltern
(geprüft in tests/test_sprache.py). Interne Bezeichner im Code bleiben deutsch.
"""

AKTUELL = "en"
NUTZER = ""          # optionaler Name des Nutzers für Hook-Texte


def setzen(sprache, name=""):
    global AKTUELL, NUTZER
    AKTUELL = sprache if sprache in ("de", "en") else "en"
    NUTZER = name or ""


def t(schluessel, **werte):
    eintrag = TEXTE[schluessel]
    return (eintrag.get(AKTUELL) or eintrag["en"]).format(**werte)


def prozent(wert):
    return f"{wert:.0f} %" if AKTUELL == "de" else f"{wert:.0f}%"


def wer():
    return NUTZER or t("wer_nutzer")


WOCHENTAGE = {"de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
              "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

TEXTE = {
    # ------------------------------------------------------------ allgemein
    "app": {"de": "Limit-Wächter", "en": "Limit Watchdog"},
    "art_fuenf": {"de": "5h", "en": "5h"},
    "art_woche": {"de": "Woche", "en": "week"},
    "stand": {"de": "{art} {pct}, Reset {reset}", "en": "{art} {pct}, resets {reset}"},
    "wer_nutzer": {"de": "der Nutzer", "en": "the user"},
    "tage": {"de": "Tagen", "en": "days"},

    # ------------------------------------------------------------ Texte an die Agenten
    "prompt_fortsetzen": {
        "de": "Limit-Wächter: Das Nutzungslimit ist zurückgesetzt. Lies deine letzte Sicherung "
              "(Status-/Übergabedatei, letzte Nachricht, `git log -1`), prüfe den Stand und setze nur Offenes fort. "
              "Abgeschlossene Schritte nicht wiederholen. Ein unterbrochener Dynamic Workflow wird per "
              "`resumeFromRunId` fortgesetzt.",
        "en": "Limit Watchdog: The usage limit has reset. Read your last checkpoint (status/handoff file, "
              "last message, `git log -1`), check the current state and continue only what is still open. "
              "Do not repeat completed steps. Resume an interrupted Dynamic Workflow with `resumeFromRunId`.",
    },
    "hook_herkunft_name": {"de": "eigener Hook von {name}", "en": "hook installed by {name}"},
    "hook_herkunft": {"de": "eigener Hook des Nutzers", "en": "the user's own hook"},
    "sicherung_kopf": {
        "de": "{app} ({herkunft}): Das Claude-Nutzungslimit ist fast erreicht ({stand}). ",
        "en": "{app} ({herkunft}): The Claude usage limit is almost reached ({stand}). ",
    },
    "sicherung_kern": {
        "de": "Bitte jetzt geordnet anhalten: den aktuellen Schritt abschließen, keine neuen Subagents oder "
              "Workflows starten, die vorhandene Status- oder Übergabedatei des Projekts aktualisieren (fertig, "
              "offen, nächster Schritt; keine neue Datei auf Vorrat), bei einem Git-Repo einen WIP-Commit nur der "
              "eigenen Änderungen machen (ohne Push), laufende Dynamic Workflows mit Run-ID notieren und dann den "
              "Turn mit einer kurzen Zusammenfassung beenden.",
        "en": "Please stop in an orderly way now: finish the current step, do not start new subagents or "
              "workflows, update the project's existing status or handoff file (done, open, next step; no new "
              "file just in case), if this is a git repository make a WIP commit of your own changes only "
              "(no push), note the run ID of any running Dynamic Workflow, and then end the turn with a short "
              "summary.",
    },
    "codex_kopf": {
        "de": "{app}: Das Codex-Nutzungslimit ist fast erreicht ({stand}). ",
        "en": "{app}: The Codex usage limit is almost reached ({stand}). ",
    },
    "codex_kern": {
        "de": "Bitte jetzt geordnet anhalten: den aktuellen Schritt abschließen, keine neuen Subagents starten, "
              "die vorhandene Status- oder Übergabedatei des Projekts aktualisieren (fertig, offen, nächster "
              "Schritt; keine neue Datei auf Vorrat), bei einem Git-Repo einen WIP-Commit nur der eigenen "
              "Änderungen machen (ohne Push) und dann mit einer kurzen Zusammenfassung anhalten.",
        "en": "Please stop in an orderly way now: finish the current step, do not start new subagents, update "
              "the project's existing status or handoff file (done, open, next step; no new file just in case), "
              "if this is a git repository make a WIP commit of your own changes only (no push), and then stop "
              "with a short summary.",
    },
    "nach_reset": {"de": " Nach dem Reset setzt der Limit-Wächter automatisch fort.",
                   "en": " After the reset, Limit Watchdog will continue automatically."},
    "ohne_fortsetzung": {
        "de": " Wegen der Wochenreserve gibt es danach keine automatische Fortsetzung; {wer} setzt selbst fort.",
        "en": " Because the weekly reserve is reached there is no automatic continuation afterwards; {wer} will "
              "continue manually.",
    },
    "stopp_kontext": {
        "de": "{app}: Das Claude-Nutzungslimit ist fast erreicht ({stand}). Stopp-Phase: den aktuellen Schritt "
              "abschließen, keine neuen Subagents oder Workflows starten, den Stand sichern und den Turn danach "
              "beenden.",
        "en": "{app}: The Claude usage limit is almost reached ({stand}). Stop phase: finish the current step, "
              "do not start new subagents or workflows, save your progress and then end the turn.",
    },
    "deny_grund": {
        "de": "{app}: Nutzungslimit fast erreicht ({stand}). Bis zum Reset starten keine neuen Subagents oder "
              "Workflows. Bitte den aktuellen Schritt ohne sie abschließen und den Stand sichern.",
        "en": "{app}: Usage limit almost reached ({stand}). No new subagents or workflows until the reset. "
              "Please finish the current step without them and save your progress.",
    },
    "prompt_hinweis": {
        "de": "Hinweis {app}: Nutzungslimit {stand}. Neue Subagents und Workflows sind bis zum Reset gesperrt.",
        "en": "Note from {app}: usage limit {stand}. New subagents and workflows are blocked until the reset.",
    },
    "reserve_block": {
        "de": "{app}: Wochenreserve erreicht (Woche {pctw}). Die automatische Fortsetzung ist gesperrt; {wer} "
              "setzt selbst fort.",
        "en": "{app}: Weekly reserve reached (week {pctw}). Automatic continuation is blocked; {wer} will "
              "continue manually.",
    },
    "terminal_titel": {"de": "{app}: Fortsetzung", "en": "{app}: continuation"},

    # ------------------------------------------------------------ Pushes (kurz, ohne Projektinhalte)
    "push_warnung": {"de": "{n}: {art} bei {pct} (Warnschwelle). Reset {reset}.",
                     "en": "{n}: {art} at {pct} (warning threshold). Resets {reset}."},
    "push_stopp": {
        "de": "{n}: Stopp-Schwelle erreicht ({art} {pct}). Laufende Agenten sichern und halten an. "
              "Reset {reset}.{hinweis}",
        "en": "{n}: stop threshold reached ({art} {pct}). Running agents save their work and pause. "
              "Resets {reset}.{hinweis}",
    },
    "push_limit": {"de": "{n}: Limit erreicht ({art}). Reset {reset}.{warten}{hinweis}",
                   "en": "{n}: limit reached ({art}). Resets {reset}.{warten}{hinweis}"},
    "push_limit_warten": {"de": " {anzahl} Sitzung(en) warten auf Fortsetzung.",
                          "en": " {anzahl} session(s) waiting to continue."},
    "hinweis_kein_netzteil": {"de": " Hinweis: kein Netzteil.", "en": " Note: not on power."},
    "hinweis_remote_aus": {"de": " Hinweis: Remote-Modus aus (zugeklappt schläft der Mac).",
                           "en": " Note: the Mac will sleep if the lid is closed."},
    "nacht_kein_netzteil": {"de": "kein Netzteil.", "en": "not on power."},
    "nacht_remote_aus": {"de": "Remote-Modus aus (zugeklappt schläft der Mac).",
                         "en": "the Mac will sleep if the lid is closed."},
    "nacht_aktion_befehl": {"de": "{befehl} ausführen und das Netzteil anschließen",
                            "en": "run {befehl} and connect power"},
    "nacht_aktion": {"de": "den Mac wach halten (auch zugeklappt, z. B. mit Amphetamine) und ans Netzteil",
                     "en": "keep the Mac awake (also with the lid closed, e.g. with Amphetamine) and on power"},
    "push_remote_nacht": {"de": "Mac: {hinweis} Für die Fortsetzung um {zeit} bitte {aktion}.",
                          "en": "Mac: {hinweis} For the continuation at {zeit}, please {aktion}."},
    "push_reserve": {"de": "{n}: Wochenreserve erreicht (Woche {pctw}). Keine automatische Fortsetzung bis {reset}.",
                     "en": "{n}: weekly reserve reached (week {pctw}). No automatic continuation until {reset}."},
    "push_reset": {"de": "{n}: Limit zurückgesetzt.", "en": "{n}: limit has reset."},
    "push_credits": {"de": "Codex: Guthaben gesunken ({alt} → {neu}). Bitte prüfen.",
                     "en": "Codex: credit balance dropped ({alt} → {neu}). Please check."},
    "push_reset_credits": {
        "de": "Codex: Reset-Credits weniger geworden ({alt} → {neu}). Der Wächter nutzt sie nie – bitte prüfen.",
        "en": "Codex: fewer rate-limit reset credits ({alt} → {neu}). Limit Watchdog never uses them – please check.",
    },
    "push_ueberziehung": {"de": "Claude: Extra-Usage (Credits) war beim Limit aktiv! Bitte prüfen.",
                          "en": "Claude: extra usage (credits) was active at the limit! Please check."},
    "push_freigabe": {"de": "{n}: fortgesetzte Sitzung wartet auf eine Freigabe.",
                      "en": "{n}: a continued session is waiting for a permission prompt."},
    "push_orca_weg": {"de": "Orca nicht erreichbar – Fortsetzung nicht möglich. Bitte Orca öffnen.",
                      "en": "Orca is not reachable – cannot continue sessions. Please open Orca."},
    "push_fortgesetzt": {"de": "{n}: {anzahl} Sitzung(en) fortgesetzt.", "en": "{n}: {anzahl} session(s) continued."},
    "push_morgenbericht": {"de": "Morgenbericht: {kurz}. Details: waechter.py report",
                           "en": "Morning report: {kurz}. Details: waechter.py report"},
    "push_reserve_halt": {
        "de": "{n}: Wochenreserve erreicht – keine automatische Fortsetzung. Bitte selbst fortsetzen.",
        "en": "{n}: weekly reserve reached – no automatic continuation. Please continue manually.",
    },
    "push_aufgegeben": {"de": "{n}: Fortsetzung {max}× versucht – ich höre auf. Bitte selbst ansehen.",
                        "en": "{n}: tried to continue {max}× – giving up. Please take a look."},
    "blockiert_menue": {"de": "am Bildschirm steht ein Menü oder eine Abfrage", "en": "a menu or prompt is on screen"},
    "blockiert_geld": {"de": "am Bildschirm steht ein Kauf- oder Kostenhinweis",
                       "en": "a purchase or billing option is on screen"},
    "blockiert_belegt": {"de": "in der Eingabezeile steht schon Text", "en": "the input line already contains text"},
    "blockiert_unklar": {"de": "der Bildschirm ist unklar", "en": "the screen is unclear"},
    "push_blockiert": {"de": "{n}: Fortsetzung angehalten – {text}. Nichts gesendet, bitte selbst ansehen.",
                       "en": "{n}: continuation paused – {text}. Nothing was sent, please take a look."},
    "push_verloren": {"de": "{n}: fortgesetzte Sitzung nicht wiedergefunden – bitte selbst ansehen.",
                      "en": "{n}: could not find the continued session again – please take a look."},
    "push_haengt": {"de": "{n}: fortgesetzte Sitzung wartet auf eine Eingabe – bitte ansehen.",
                    "en": "{n}: a continued session is waiting for input – please take a look."},
    "push_tickfehler": {"de": "{app}: Fehler im Tick – bitte waechter.py status und das Log ansehen.",
                        "en": "{app}: error during a tick – please check waechter.py status and the log."},
    "push_test": {"de": "Test: Der Limit-Wächter kann dich erreichen.", "en": "Test: Limit Watchdog can reach you."},

    # ------------------------------------------------------------ Aktionen und Log
    "aktion_bericht": {"de": "Morgenbericht gespeichert: {datei}", "en": "Morning report saved: {datei}"},
    "aktion_blockiert": {"de": "BLOCKIERT {s}: {grund}", "en": "BLOCKED {s}: {grund}"},
    "aktion_laeuft": {"de": "LÄUFT BEREITS {s}", "en": "ALREADY RUNNING {s}"},
    "aktion_warte": {"de": "WARTE {s}: Claudes eingebautes Warten ist noch aktiv",
                     "en": "WAITING {s}: Claude's built-in wait is still active"},
    "aktion_fortgesetzt": {"de": "FORTGESETZT {s} per {weg}", "en": "CONTINUED {s} via {weg}"},
    "aktion_neu": {"de": "NEU GESTARTET {s} in {sel}", "en": "RESTARTED {s} in {sel}"},
    "aktion_codex_limit": {"de": "CODEX-LIMIT {id} Reset {zeit}", "en": "CODEX LIMIT {id} resets {zeit}"},
    "aktion_codex_stopp": {"de": "CODEX-STOPP {id} ({projekt}): {ergebnis}", "en": "CODEX STOP {id} ({projekt}): {ergebnis}"},
    "angenommen": {"de": "angenommen", "en": "accepted"},
    "nicht_angenommen": {"de": "NICHT angenommen", "en": "NOT accepted"},
    "weg_enter": {"de": "Enter (nach Schlaf)", "en": "Enter (after sleep)"},
    "weg_prompt": {"de": "Fortsetzungsprompt", "en": "continuation prompt"},
    "weg_neu": {"de": "neues Terminal", "en": "new terminal"},
    "grund_bild": {"de": "Bildschirm nicht lesbar: {fehler}", "en": "screen not readable: {fehler}"},
    "grund_senden": {"de": "Senden nicht bestätigt: {fehler}", "en": "sending not confirmed: {fehler}"},
    "grund_nicht_angenommen": {"de": "nicht angenommen", "en": "not accepted"},
    "grund_ordner": {"de": "Terminal fehlt und Projektordner unbekannt",
                     "en": "terminal missing and project folder unknown"},
    "grund_agents": {"de": "Terminal fehlt; `claude agents` nicht lesbar – kein Neustart auf Verdacht",
                     "en": "terminal missing; `claude agents` not readable – no blind restart"},
    "grund_woanders": {"de": "Sitzung läuft außerhalb eines Orca-Terminals – keine Kopie starten",
                       "en": "session is running outside an Orca terminal – not starting a copy"},
    "grund_erstellen": {"de": "Terminal konnte nicht erstellt werden: {fehler}",
                        "en": "could not create a terminal: {fehler}"},
    "log_bildschirm": {"de": "Bildschirm {s}: {art} ({grund}) :: {ausschnitt}",
                       "en": "Screen {s}: {art} ({grund}) :: {ausschnitt}"},
    "log_pruefung": {"de": "Prüfung {s}: {art} :: {ausschnitt}", "en": "Check {s}: {art} :: {ausschnitt}"},
    "log_weitere": {"de": "{anzahl} weitere Fortsetzung(en) im nächsten Tick",
                    "en": "{anzahl} more continuation(s) in the next tick"},
    "log_pausiert": {"de": " (pausiert)", "en": " (paused)"},
    "log_phase": {"de": "PHASE {anb}: {alt} -> {neu} ({stand})", "en": "PHASE {anb}: {alt} -> {neu} ({stand})"},
    "log_codex_kein_thread": {"de": "Codex-Terminal {handle}: kein Thread zugeordnet",
                              "en": "Codex terminal {handle}: no thread found"},
    "log_codex_bild": {"de": "Codex-Stopp: Bildschirm nicht lesbar: {fehler}",
                       "en": "Codex stop: screen not readable: {fehler}"},
    "log_codex_nichts": {"de": "Codex-Stopp {id}: nichts gesendet ({grund}) :: {ausschnitt}",
                         "en": "Codex stop {id}: nothing sent ({grund}) :: {ausschnitt}"},
    "log_tick_laeuft": {"de": "tick: vorheriger Durchlauf läuft noch – übersprungen",
                        "en": "tick: previous run still active – skipped"},
    "log_tickfehler": {"de": "TICK-FEHLER {typ}: {fehler} | {spur}", "en": "TICK ERROR {typ}: {fehler} | {spur}"},
    "log_hook_block": {"de": "HOOK Stop-Block (Sicherungsauftrag) in {sid}",
                       "en": "HOOK stop block (checkpoint request) in {sid}"},
    "log_hook_fehler": {"de": "HOOK-FEHLER {ev}: {typ}: {fehler}", "en": "HOOK ERROR {ev}: {typ}: {fehler}"},
    "log_meldung": {"de": "MELDUNG{modus} p{prio}: {text}", "en": "NOTIFY{modus} p{prio}: {text}"},
    "modus_dry": {"de": " (dry-run)", "en": " (dry-run)"},
    "modus_still": {"de": " (pausiert, still)", "en": " (paused, silent)"},
    "log_kein_topic": {"de": "ntfy: kein Topic im Schlüsselbund – Push übersprungen",
                       "en": "ntfy: no topic in the keychain – push skipped"},
    "log_ntfy_fehler": {"de": "ntfy-Fehler: {typ}", "en": "ntfy error: {typ}"},
    "log_banner_fehler": {"de": "Banner-Fehler", "en": "banner error"},
    "log_konfig_fehler": {"de": "KONFIG-FEHLER in {datei}: {fehler} – nutze Standardwerte",
                          "en": "CONFIG ERROR in {datei}: {fehler} – using defaults"},
    "log_pause": {"de": "Pause {wie}", "en": "Pause {wie}"},
    "log_pause_ende": {"de": "Pause beendet", "en": "Pause ended"},
    "orca_zeit": {"de": "Zeitüberschreitung bei orca {befehl}", "en": "timeout running orca {befehl}"},
    "orca_start": {"de": "orca nicht ausführbar: {fehler}", "en": "cannot run orca: {fehler}"},
    "orca_json": {"de": "keine JSON-Antwort von orca {befehl} (Exit {code})",
                  "en": "no JSON reply from orca {befehl} (exit {code})"},
    "orca_dry_senden": {"de": "DRY-RUN: würde senden an {handle}: {was}", "en": "DRY-RUN: would send to {handle}: {was}"},
    "orca_dry_erstellen": {"de": "DRY-RUN: würde Terminal erstellen in {wo}: {befehl}",
                           "en": "DRY-RUN: would create a terminal in {wo}: {befehl}"},
    "wach_dry": {"de": "würde caffeinate -i -s -t {sek} starten (bis {zeit})",
                 "en": "would start caffeinate -i -s -t {sek} (until {zeit})"},
    "wach_fehler": {"de": "caffeinate fehlgeschlagen: {fehler}", "en": "caffeinate failed: {fehler}"},
    "wach_start": {"de": "caffeinate -i -s bis {zeit} gestartet (pid {pid})",
                   "en": "caffeinate -i -s started until {zeit} (pid {pid})"},

    # ------------------------------------------------------------ Bildschirm-Einordnung (Gründe)
    "bs_leer": {"de": "kein Bildschirminhalt", "en": "empty screen"},
    "bs_menue": {"de": "Menü/Abfrage sichtbar ({m})", "en": "menu/prompt visible ({m})"},
    "bs_eingebaut": {"de": "eingebautes Warten sichtbar ({m})", "en": "built-in wait visible ({m})"},
    "bs_geld": {"de": "Kauf-/Kostenhinweis sichtbar ({m})", "en": "purchase/billing hint visible ({m})"},
    "bs_stale": {"de": "wartet auf Enter nach Schlaf", "en": "waiting for Enter after sleep"},
    "bs_arbeitet": {"de": "Agent arbeitet", "en": "agent is working"},
    "bs_codex_bereit": {"de": "Eingabezeile sichtbar", "en": "input line visible"},
    "bs_bereit": {"de": "leere Eingabezeile", "en": "empty input line"},
    "bs_belegt": {"de": "in der Eingabezeile steht schon Text", "en": "the input line already contains text"},
    "bs_keine": {"de": "keine Eingabezeile erkannt", "en": "no input line found"},

    # ------------------------------------------------------------ Bericht
    "bericht_titel": {"de": "# Limit-Wächter – Bericht {datum}", "en": "# Limit Watchdog – report {datum}"},
    "bericht_zeitraum": {"de": "Zeitraum: {von} bis {bis}", "en": "Period: {von} to {bis}"},
    "bericht_leer": {"de": "Keine Limit-Ereignisse.", "en": "No limit events."},
    "b_gestoppt": {"de": "Geordnet gestoppt", "en": "Stopped in an orderly way"},
    "b_limit": {"de": "Limit erreicht", "en": "Limit reached"},
    "b_fortgesetzt": {"de": "Fortgesetzt", "en": "Continued"},
    "b_blockiert": {"de": "Nicht fortgesetzt (Menü, Kaufhinweis oder unklar)",
                    "en": "Not continued (menu, billing option or unclear screen)"},
    "b_haengt": {"de": "Nach Fortsetzung an einer Abfrage hängen geblieben",
                 "en": "Stuck at a prompt after continuing"},
    "b_freigabe_blockiert": {"de": "Vom Auto-Modus blockiert", "en": "Denied by auto mode"},
    "b_wartet_auf_freigabe": {"de": "Wartete auf eine Freigabe", "en": "Waited for a permission prompt"},
    "b_reserve_gesperrt": {"de": "Eingebaute Fortsetzung wegen Wochenreserve gesperrt",
                           "en": "Built-in continuation blocked by the weekly reserve"},
    "b_ueberziehung": {"de": "Extra-Usage aktiv (prüfen!)", "en": "Extra usage active (check!)"},
    "b_eingebaut": {"de": "Claudes eingebaute Fortsetzung", "en": "Claude's built-in continuation"},
    "b_meldung": {"de": "Gesendete Meldungen", "en": "Notifications sent"},

    # ------------------------------------------------------------ Kommandozeile
    "cli_beschreibung": {"de": "Limit-Wächter für Claude Code und Codex in Orca",
                         "en": "Limit Watchdog for Claude Code and Codex in Orca"},
    "h_status": {"de": "Füllstand, Phasen, wartende Sitzungen", "en": "usage, phases, waiting sessions"},
    "h_alle": {"de": "auch aktive Sitzungen zeigen", "en": "also show active sessions"},
    "h_tick": {"de": "ein Durchlauf (macht der LaunchAgent jede Minute)",
               "en": "run once (the LaunchAgent does this every minute)"},
    "h_dry": {"de": "mit Kopie des Zustands, nichts senden", "en": "use a copy of the state, send nothing"},
    "h_simulate": {"de": "Probelauf ohne Verbrauch", "en": "dry run without using any quota"},
    "h_sitzung": {"de": "nur 'stop': scharf, aber nur für diese Claude-Session-ID",
                  "en": "'stop' only: live, but only for this Claude session ID"},
    "h_pause": {"de": "pausieren: pause [30m|2h|1d], beenden: pause aus",
                "en": "pause: pause [30m|2h|1d], end: pause off"},
    "h_weiter": {"de": "Pause beenden", "en": "end the pause"},
    "h_report": {"de": "Bericht der letzten Stunden", "en": "report for the last hours"},
    "h_ntfy_setup": {"de": "zufälliges Topic im Schlüsselbund anlegen", "en": "create a random topic in the keychain"},
    "h_ntfy_abo": {"de": "Topic in die Zwischenablage (zum Abonnieren in der ntfy-App)",
                   "en": "copy the topic to the clipboard (to subscribe in the ntfy app)"},
    "h_test_push": {"de": "Test-Push senden", "en": "send a test notification"},
    "st_kopf": {"de": "Limit-Wächter {version} · {zeit}", "en": "Limit Watchdog {version} · {zeit}"},
    "st_letzter": {"de": "letzter Tick vor {dauer}", "en": "last tick {dauer} ago"},
    "st_kein_tick": {"de": "noch kein Tick", "en": "no tick yet"},
    "st_pausiert_bis": {"de": "PAUSIERT bis {zeit}", "en": "PAUSED until {zeit}"},
    "st_pausiert": {"de": "PAUSIERT (bis pause aus)", "en": "PAUSED (until pause off)"},
    "st_aktiv": {"de": "aktiv", "en": "active"},
    "st_wachter": {"de": "Wächter: {pause} · {lauf} · LaunchAgent {agent}",
                   "en": "Watchdog: {pause} · {lauf} · LaunchAgent {agent}"},
    "st_geladen": {"de": "geladen", "en": "loaded"},
    "st_nicht_geladen": {"de": "NICHT geladen", "en": "NOT loaded"},
    "st_orca_weg": {"de": "Orca: NICHT erreichbar ({fehler})", "en": "Orca: NOT reachable ({fehler})"},
    "st_daten": {"de": "Daten vor {dauer} ({quelle})", "en": "data {dauer} old ({quelle})"},
    "st_keine_daten": {"de": "keine Daten", "en": "no data"},
    "st_reserve": {"de": " · Reserve erreicht", "en": " · reserve reached"},
    "st_zeile": {"de": "{name:7} 5h {f5:22} Woche {fw:22} Phase {phase:8} {alter}",
                 "en": "{name:7} 5h {f5:22} week {fw:22} phase {phase:8} {alter}"},
    "st_fenster": {"de": "{pct} (Reset {reset})", "en": "{pct} (resets {reset})"},
    "st_schwellen": {
        "de": "Schwellen: Warnung {w} %, Stopp {s} % (5h) · Woche {ww}/{ws} % · Reserve {r} % "
              "(ab {ab} % Woche keine Auto-Fortsetzung)",
        "en": "Thresholds: warn {w}%, stop {s}% (5h) · week {ww}/{ws}% · reserve {r}% "
              "(no auto-continue above {ab}% weekly use)",
    },
    "st_sitzungen": {"de": "Sitzungen (letzte 2 Tage, Orca): {c} Claude, {x} Codex",
                     "en": "Sessions (last 2 days, Orca): {c} Claude, {x} Codex"},
    "st_ab": {"de": " · Fortsetzung ab {zeit}", "en": " · continues from {zeit}"},
    "st_keine_wartet": {"de": "  (keine Sitzung wartet oder ist blockiert; alle anzeigen: status --alle)",
                        "en": "  (no session is waiting or blocked; show all: status --all)"},
    "ja": {"de": "ja", "en": "yes"},
    "nein": {"de": "nein", "en": "no"},
    "NEIN": {"de": "NEIN", "en": "NO"},
    "st_mac": {"de": "Mac: Netzteil {ac} · Schlaf aus: {schlaf} · zugeklappt wach: {deckel} · Amphetamine: {amph}",
               "en": "Mac: on power {ac} · sleep disabled: {schlaf} · awake with lid closed: {deckel} · "
                     "Amphetamine: {amph}"},
    "st_ntfy": {"de": "ntfy: Topic im Schlüsselbund {topic} · Wachhalten: {wach}",
                "en": "ntfy: topic in keychain {topic} · keep-awake: {wach}"},
    "st_topic_fehlt": {"de": "FEHLT (waechter.py ntfy-einrichten)", "en": "MISSING (waechter.py ntfy-setup)"},
    "st_caffeinate": {"de": "caffeinate bis {zeit}", "en": "caffeinate until {zeit}"},
    "st_aus": {"de": "aus", "en": "off"},
    "st_log": {"de": "Log: {pfad}", "en": "Log: {pfad}"},
    "phase_ok": {"de": "OK", "en": "OK"},
    "phase_warnung": {"de": "WARNUNG", "en": "WARNING"},
    "phase_stopp": {"de": "STOPP", "en": "STOP"},
    "phase_limit": {"de": "LIMIT", "en": "LIMIT"},
    "tick_dry": {"de": "Tick im Dry-Run (Kopie des Zustands, nichts gesendet)",
                 "en": "Tick in dry-run (copy of the state, nothing sent)"},
    "zyklus_fertig": {"de": "Zyklus fertig: alles mit Probedaten und Orca-Attrappe, nichts gesendet.",
                      "en": "Cycle finished: all with sample data and a fake Orca, nothing sent."},
    "nur_stop": {"de": "--sitzung gibt es nur für 'simulate stop'.", "en": "--session only works with 'simulate stop'."},
    "pause_ende": {"de": "Wächter wieder aktiv.", "en": "Watchdog active again."},
    "pause_dauer": {"de": "Dauer wie 30m, 2h oder 1d angeben (oder 'aus').",
                    "en": "Give a duration like 30m, 2h or 1d (or 'off')."},
    "pause_bis": {"de": "bis {zeit}", "en": "until {zeit}"},
    "pause_ohne_ende": {"de": "ohne Ende", "en": "without end"},
    "pause_bis_aus": {"de": "bis: waechter.py pause aus", "en": "until: waechter.py pause off"},
    "pause_ok": {"de": "Wächter pausiert {wie}. Keine Stopps, keine Fortsetzungen, keine Pushes; Claudes "
                       "eingebaute Fortsetzung läuft normal.",
                 "en": "Watchdog paused {wie}. No stops, no continuations, no notifications; Claude's built-in "
                       "auto-continue works as usual."},
    "ntfy_schon": {"de": "Topic ist schon im Schlüsselbund (Dienst {dienst}).",
                   "en": "The topic is already in the keychain (service {dienst})."},
    "ntfy_fehler": {"de": "Konnte das Topic nicht im Schlüsselbund speichern.",
                    "en": "Could not store the topic in the keychain."},
    "ntfy_neu": {"de": "Zufälliges ntfy-Topic erzeugt und im Schlüsselbund gespeichert (Dienst {dienst}).",
                 "en": "Created a random ntfy topic and stored it in the keychain (service {dienst})."},
    "ntfy_label": {"de": "Limit-Wächter ntfy-Topic", "en": "Limit Watchdog ntfy topic"},
    "ntfy_keins": {"de": "Kein Topic im Schlüsselbund. Erst: waechter.py ntfy-einrichten",
                   "en": "No topic in the keychain. First run: waechter.py ntfy-setup"},
    "ntfy_abo_1": {"de": "Das Topic liegt jetzt in der Zwischenablage (auch auf dem iPhone per Universal Clipboard).",
                   "en": "The topic is now on the clipboard (also on your iPhone via Universal Clipboard)."},
    "ntfy_abo_2": {"de": "ntfy-App → + → Topic einfügen → Server ntfy.sh lassen → Abonnieren. Danach: waechter.py test-push",
                   "en": "ntfy app → + → paste topic → keep server ntfy.sh → Subscribe. Then: waechter.py test-push"},
    "test_ok": {"de": "Test-Push gesendet (und macOS-Banner).", "en": "Test notification sent (and a macOS banner)."},

    # ------------------------------------------------------------ Sitzungszustände (Anzeige)
    "z_aktiv": {"de": "aktiv", "en": "active"},
    "z_sicherung": {"de": "sichert gerade", "en": "checkpointing"},
    "z_gestoppt": {"de": "gestoppt", "en": "stopped"},
    "z_limit": {"de": "am Limit", "en": "at limit"},
    "z_eingebaut_wartet": {"de": "Claude wartet selbst", "en": "Claude waiting (built-in)"},
    "z_eingebaut_fortgesetzt": {"de": "von Claude fortgesetzt", "en": "continued by Claude"},
    "z_stale": {"de": "wartet auf Enter", "en": "waiting for Enter"},
    "z_disabled": {"de": "Claude-Warten beendet", "en": "built-in wait ended"},
    "z_fortgesetzt": {"de": "fortgesetzt", "en": "continued"},
    "z_blockiert": {"de": "blockiert – bitte ansehen", "en": "blocked – please check"},
    "z_reserve": {"de": "Wochenreserve", "en": "weekly reserve"},
    "z_aufgegeben": {"de": "aufgegeben", "en": "gave up"},
    "z_beendet": {"de": "beendet", "en": "ended"},

    # ------------------------------------------------------------ Installer
    "inst_abbruch": {"de": "ABBRUCH: fremde Einträge hätten sich geändert – nichts geschrieben.",
                     "en": "ABORTED: entries of other tools would have changed – nothing written."},
    "inst_ok_eintragen": {"de": "eingetragen: {anzahl} Hookgruppen in {datei}",
                          "en": "installed: {anzahl} hook groups in {datei}"},
    "inst_ok_austragen": {"de": "ausgetragen: {anzahl} Hookgruppen verbleiben in {datei}",
                          "en": "removed: {anzahl} hook groups remain in {datei}"},

    # ------------------------------------------------------------ Simulation
    "sim_jetzt": {"de": "Simulation {fall} {anbieter} (echte Terminals nur gelesen, nichts gesendet)",
                  "en": "Simulation {fall} {anbieter} (real terminals only read, nothing sent)"},
    "sim_hooks": {"de": "  Claude-Hooks in dieser Phase: neue Agent/Workflow-Aufrufe -> deny; "
                        "Turn-Ende -> einmal Sicherungsauftrag (decision=block).",
                  "en": "  Claude hooks in this phase: new Agent/Workflow calls -> deny; "
                        "end of turn -> one checkpoint request (decision=block)."},
    "sim_gestoppt": {"de": "  (Sandbox: {anzahl} registrierte {anbieter}-Sitzung(en) als 'gestoppt' markiert)",
                     "en": "  (sandbox: marked {anzahl} registered {anbieter} session(s) as 'stopped')"},
    "sim_zeile": {"de": "  {a:6} Phase {phase:8} 5h {p5:5.1f} %  Woche {pw:5.1f} %",
                  "en": "  {a:6} phase {phase:8} 5h {p5:5.1f}%  week {pw:5.1f}%"},
    "sim_push": {"de": "  PUSH p{prio}: {text}", "en": "  PUSH p{prio}: {text}"},
    "sim_aktion": {"de": "  AKTION: {text}", "en": "  ACTION: {text}"},
    "sim_nichts": {"de": "  (keine Meldung, keine Aktion)", "en": "  (no notification, no action)"},
    "sim_s1": {"de": "1 Normalbetrieb", "en": "1 normal operation"},
    "sim_s2": {"de": "2 Warnschwelle", "en": "2 warning threshold"},
    "sim_s3": {"de": "3 Stopp-Schwelle", "en": "3 stop threshold"},
    "sim_s4": {"de": "4 Limit erreicht", "en": "4 limit reached"},
    "sim_s5": {"de": "5 Reset + 3 min", "en": "5 reset + 3 min"},
    "sim_s6": {"de": "6 Reset + 6 min", "en": "6 reset + 6 min"},
    "sim_s7": {"de": "7 Morgenbericht", "en": "7 morning report"},
    "sim_hook_deny": {"de": "  HOOK PreToolUse(Agent): {wert}", "en": "  HOOK PreToolUse(Agent): {wert}"},
    "sim_hook_post": {"de": "  HOOK PostToolUse: {wert}", "en": "  HOOK PostToolUse: {wert}"},
    "sim_hook_stop": {"de": "  HOOK Stop #1: {eins} | Stop #2 (stop_hook_active): {zwei}",
                      "en": "  HOOK Stop #1: {eins} | Stop #2 (stop_hook_active): {zwei}"},
    "sim_frei": {"de": "frei", "en": "allowed"},
    "sim_ende": {"de": "\n== Endzustand ==", "en": "\n== Final state =="},
    "sim_gesendet": {"de": "  An die Attrappe gesendet:", "en": "  Sent to the fake Orca:"},
    "sim_scharf": {"de": "Simulierte Stopp-Phase für Sitzung {sid} ist {minuten} min aktiv (nur diese Sitzung).",
                   "en": "Simulated stop phase for session {sid} is active for {minuten} min (this session only)."},
    "sim_scharf_ende": {"de": "Beenden: waechter.py simulate aus", "en": "End it with: waechter.py simulate off"},
    "sim_aus": {"de": "Simulation beendet.", "en": "Simulation ended."},
}
