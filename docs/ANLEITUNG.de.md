# Bedienungsanleitung (Deutsch)

Stand: Version 1.1 (Nachtmodus). Die englische Beschreibung steht in der [README](../README.md).

## Was der Wächter macht, in drei Sätzen

Er schaut jede Minute, wie voll dein Claude- und Codex-Kontingent ist (5-Stunden-Fenster und Woche). Kurz vor dem
Limit sorgt er dafür, dass deine Agenten in Orca ihren Stand sichern und geordnet anhalten. Nach dem Reset setzt er
die Sitzungen im **Nachtmodus** automatisch fort; alle anderen warten auf dein „weiter“, und du bekommst einen Push.
Geld gibt er nie aus.

## Wo gebe ich die Befehle ein?

Im **Terminal** (auch ein normales Orca-Terminal) im Ordner des Wächters:

```sh
cd ~/pfad/zu/agent-limit-watchdog      # dort, wohin du das Repo geklont hast
./waechter.py status
```

Tipp: Mit `alias lw="~/pfad/zu/agent-limit-watchdog/waechter.py"` in der `~/.zshrc` reicht danach überall `lw status`.

## Die wichtigsten Befehle

| Befehl | Was er tut |
|---|---|
| `./waechter.py status` | Füllstand Claude/Codex, aktuelle Phase, wartende oder blockierte Sitzungen, Mac-Zustand |
| `./waechter.py status --alle` | wie oben, aber mit allen Sitzungen |
| `./waechter.py nacht an` | Nachtmodus für alle Sitzungen bis 08:00 (siehe unten) |
| `./waechter.py nacht an <ID-Anfang oder Projektordner>` | Nachtmodus nur für diese Sitzung |
| `./waechter.py nacht aus` / `./waechter.py nacht` | Nachtmodus aus / anzeigen, was gerade gilt |
| `./waechter.py pause` | **Wächter aus** bis auf Weiteres: keine Stopps, keine Fortsetzungen, keine Pushes |
| `./waechter.py pause 2h` | Pause für 2 Stunden (auch `30m`, `1d`), danach automatisch wieder an |
| `./waechter.py pause aus` | **Wächter wieder an** (gleich: `./waechter.py weiter`) |
| `./waechter.py report` | Bericht der letzten 24 Stunden (`--stunden 48` für mehr) |
| `./waechter.py simulate zyklus` | kompletter Probelauf mit Probedaten, nichts wird gesendet |
| `./waechter.py simulate stop` | zeigt, was jetzt bei 93 % passieren würde (echte Terminals werden nur gelesen) |
| `./waechter.py tick --dry-run` | ein Durchlauf mit deinen echten Daten auf einer Kopie, nichts wird gesendet |
| `./waechter.py ntfy-abo` | ntfy-Topic in die Zwischenablage (zum Abonnieren in der App) |
| `./waechter.py test-push` | Test-Benachrichtigung aufs Handy |
| `./install.sh` | installieren oder nach einem Update neu einrichten (mit Backup) |
| `./uninstall.sh` | **ganz ausschalten**: Autostart und Hooks entfernen (mit Backup, löscht nichts) |

**Ein/Aus kurz:** vorübergehend `pause` / `pause aus`; dauerhaft `./uninstall.sh` / `./install.sh`.
In der Pause sperrt der Wächter nichts; Claudes eigenes Auto-Continue am Limit läuft dann normal.

## Nachtmodus (seit 1.1)

Der geordnete Stopp läuft immer für alle Sitzungen. **Automatisch fortgesetzt** wird nach dem Reset aber nur, wer im
Nachtmodus ist. Alle anderen Sitzungen warten auf „weiter“ – auch Claudes eingebautes Auto-Continue wird für sie
gesperrt –, und du bekommst je Anbieter einen Push „… Sitzung(en) warten auf „weiter““.

- **Einschalten:** `./waechter.py nacht an` (alle, auch später gestartete) oder `nacht an <Sitzung>`. In einer
  Claude-Sitzung einfach `#nacht` tippen (`#nacht alle`, `#nacht aus`). Der Hook fängt das ab, es geht nicht ans
  Modell und kostet nichts; klappt auch per Remote Control vom Handy. Codex-Sitzungen nur per Befehl.
- **Dauer:** bis zur Berichtszeit (`[bericht] uhrzeit`, Standard 08:00), dann schaltet er sich selbst ab.
- **Auch nachträglich:** Sitzungen, die seit weniger als 12 Stunden auf „weiter“ warten, setzt der Wächter
  nach dem Einschalten innerhalb einer Minute fort (mit der üblichen Bildschirmprüfung).
- **Englisch:** `night on|off [session|all]`, `#night`.
- **Altes Verhalten** (alles automatisch fortsetzen): in `config.local.toml` unter `[fortsetzen]`
  `nur_mit_nachtmodus = false`.

## Schwellen und Verhalten einstellen

Eigene Werte gehören in die Datei **`config.local.toml`** im Ordner des Wächters. Sie wird nie hochgeladen und
überschreibt die Standardwerte aus `config.toml`. Beispiel:

```toml
[allgemein]
sprache = "de"             # deutsche Pushes und Ausgaben
name = "Alex"              # erscheint in den Hinweisen, die Claude bekommt

[schwellen]
warnung = 80               # ab so viel % des 5h-Fensters: Warnung aufs Handy
stopp = 92                 # ab so viel %: geordneter Stopp (sichern, anhalten)
woche_warnung = 80         # dasselbe fürs Wochenfenster
woche_stopp = 92
wochen_reserve = 20        # ab 100 - 20 = 80 % Wochenverbrauch: keine automatische Fortsetzung mehr

[fortsetzen]
aktiv = true               # false = nach dem Reset nie automatisch fortsetzen (Stopp läuft trotzdem)
nur_mit_nachtmodus = true  # nur Sitzungen im Nachtmodus fortsetzen; false = alles (Verhalten von 1.0)
puffer_minuten = 2         # so lange nach dem Reset warten
max_pro_fenster = 2        # höchstens so viele automatische Fortsetzungen je Sitzung und Fenster

[bericht]
uhrzeit = "08:00"          # Morgenbericht; hier endet auch der Nachtmodus
```

Änderungen wirken beim nächsten Durchlauf (höchstens eine Minute). Mit `./waechter.py status` siehst du die
aktiven Schwellen. Ist die Datei fehlerhaft, nimmt der Wächter die Standardwerte und schreibt das ins Log.

## Was passiert wann?

| Phase | Wann | Was passiert |
|---|---|---|
| OK | unter 80 % | nichts |
| Warnung | ab 80 % | Push und Banner |
| Stopp | ab 92 % | Claude: keine neuen Subagents/Workflows; am Ende des Turns genau ein Sicherungsauftrag (Status-/Übergabedatei, WIP-Commit ohne Push, laufende Workflows mit Run-ID notieren), dann hält die Sitzung an. Codex bekommt eine kurze Nachricht mit derselben Bitte. |
| Limit | 100 % | Sitzungen werden mit Reset-Zeit gemerkt, der Mac bleibt wach |
| Reset | Reset + 2 min | Sitzungen im Nachtmodus: Wächter liest den Bildschirm und setzt fort, außer dort steht ein Menü, eine Kaufoption oder etwas Unklares. Alle anderen warten auf „weiter“ (ein Push). |

Von Hand fortsetzen: in der Sitzung einfach „weiter“ schreiben. Claude liest dann die eigene Sicherung.

## Pushes aufs Handy

- **Warnschwelle / Stopp-Schwelle / Limit erreicht:** zur Info, du musst nichts tun.
- **„Fortsetzung angehalten – … Nichts gesendet“:** Am Bildschirm stand ein Menü oder ein Kaufhinweis. Bitte selbst
  ansehen; der Wächter tippt dort bewusst nichts.
- **„Limit zurückgesetzt – … Sitzung(en) warten auf „weiter““:** Diese Sitzungen waren nicht im Nachtmodus. Schreib
  dort „weiter“, wenn du weitermachen willst.
- **„Wochenreserve erreicht“:** Ab jetzt keine automatische Fortsetzung mehr bis zum Wochen-Reset.
- **„Mac: … Remote-Modus aus“ (nachts):** Der Mac würde zugeklappt schlafen oder hängt am Akku. Dann klappt die
  Fortsetzung nicht.
- **„Guthaben gesunken“ / „Extra-Usage aktiv“:** Bitte prüfen, der Wächter selbst gibt nie Geld aus.

## Für welche Apps gilt das?

Nur für **Claude Code CLI** und **Codex CLI** in **Orca-Terminals**. Nicht gesteuert werden Claude Desktop,
claude.ai im Browser, die ChatGPT-/Codex-App, Codex in VS Code sowie Claude im normalen Terminal.app oder iTerm.
Deren Verbrauch zählt aber mit in den Prozentwerten.

## Wenn etwas komisch ist

1. `./waechter.py status`: Läuft der LaunchAgent, und wann war der letzte Tick?
2. Log ansehen: `tail -50 ~/.limit-waechter/log/waechter.log`. Dort steht auch jeder Bildschirm, den der Wächter vor
   dem Senden gelesen hat.
3. Sofort alles anhalten: `./waechter.py pause`.
4. Zurückbauen: `./uninstall.sh` (Backups liegen in `~/.limit-waechter/backups/`).
