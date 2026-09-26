# Bedienungsanleitung (Deutsch)

Stand: Version 1.2 (Menüleisten-App). Die englische Beschreibung steht in der [README](../README.md).

## Ganz einfach erklärt (hier anfangen)

### Die Idee

Der Wächter passt auf, dass deine Claude- und Codex-Sitzungen nicht mitten in der Arbeit vom Nutzungslimit
abgewürgt werden. Stell ihn dir wie einen Tankwart vor: Er warnt, bevor der Tank leer ist, lässt dich ordentlich
rechts ranfahren und fährt nach dem Nachtanken wieder los, aber **nur, wenn du das erlaubt hast**.

### Was er von selbst macht, ohne dass du etwas drückst

Er schaut jede Minute, wie voll dein Limit ist (5-Stunden-Fenster und Woche):

| Füllstand | Was passiert |
|---|---|
| unter 80 % | nichts |
| **80 %** | **Warnung**: Push aufs Handy und Banner am Mac, sonst nichts |
| **92 %** | **Geordneter Stopp**: Jede Sitzung macht ihren Schritt fertig, sichert den Stand (Übergabedatei, WIP-Commit ohne Push) und hält an. Neue Subagents/Workflows werden verweigert. |
| **Limit** | Die Sitzungen stehen schon, der Wächter wartet auf den Reset. |
| **Reset** | Jetzt entscheidet der Nachtmodus, ob es von selbst weitergeht (siehe unten). |

Warnung und Stopp laufen **immer, für alle Sitzungen**. Das musst du nie einschalten.

### Was der Nachtmodus macht

Der Nachtmodus beantwortet nur eine Frage: **Geht es nach dem Reset automatisch weiter?**

- **Ohne Nachtmodus (normal, tagsüber):** Nach dem Reset geht nichts von selbst weiter, auch Claudes eingebautes
  Weitermachen ist gesperrt. Du bekommst einen Push („… Sitzungen warten auf ‚weiter‘“), gehst in die Sitzung und
  tippst **„weiter“**. So wird dein frisches Limit nicht ohne dich verbraucht.
- **Mit Nachtmodus:** Nach dem Reset setzt der Wächter die Sitzungen selbst fort. Vorher liest er den Bildschirm:
  Menüs oder Kaufoptionen tippt er nie an, dann kommt nur ein Push. Er versucht es höchstens 2-mal pro Sitzung. Der
  Nachtmodus gilt **bis 08:00** und schaltet sich dann **von selbst ab**; um 8 Uhr kommt ein Morgenbericht.
- **Ausnahme Wochenreserve:** Ab 80 % Wochenverbrauch geht es auch im Nachtmodus nicht automatisch weiter, damit
  für den Rest der Woche etwas übrig bleibt.

### So benutzt du es im Alltag

- **Tagsüber:** nichts tun. Kommt ein Stopp, tippst du nach dem Reset in der Sitzung „weiter“.
- **Abends, wenn nachts etwas weiterlaufen soll:** Nachtmodus einschalten, und zwar entweder
  - in der Menüleiste aufs Ring-Symbol klicken → Schalter **Nachtmodus** (alle Sitzungen) oder den **Mond** neben
    einer Sitzung (nur diese),
  - in der Claude-Sitzung `#nacht` tippen (geht auch per Remote Control, kostet keine Nutzung),
  - oder `./waechter.py nacht an`.
  Den Mac am Netzteil lassen. Würde er nachts einschlafen, warnt dich der Wächter.
- **Morgens:** nichts ausschalten, das passiert um 8 Uhr allein. Kurz den Bericht ansehen.
- **Wenn er dich gerade stört:** Pause (in der App oder `./waechter.py pause 2h`). Dann greift er nirgends ein.

### Wo er wirkt und wo nicht

Der Wächter steuert **nur Sitzungen, die in einem Orca-Terminal laufen**. Nur dort kann er den Bildschirm lesen,
etwas eintippen und die Sitzung einer Session-ID zuordnen.

| Wo du arbeitest | Warnung/Anzeige | Geordneter Stopp | Fortsetzen nach dem Reset |
|---|---|---|---|
| **Claude Code im Orca-Terminal** | ✅ | ✅ | ✅ (mit Nachtmodus) |
| **Codex im Orca-Terminal** | ✅ | ✅ | ✅ (mit Nachtmodus) |
| Claude Code im normalen Terminal (Terminal.app, iTerm, VS Code …) | ✅ zählt mit | ❌ | ❌ vom Wächter nicht; Claudes eigenes Weitermachen bleibt dort ungebremst an |
| Codex im normalen Terminal | ✅ zählt mit | ❌ | ❌ Codex bleibt am Limit einfach stehen |
| Claude-Desktop-App, claude.ai, ChatGPT-/Codex-App | ✅ zählt mit | ❌ | ❌ |

Was heißt „zählt mit“? Alles läuft über **dasselbe Konto-Limit**. Arbeitest du in der Desktop-App, steigt der
Füllstand genauso, und du bekommst auch die Warnung. Gestoppt und fortgesetzt werden aber **nur** die
Orca-Sitzungen. Auch `#nacht` wirkt nur in Orca; woanders geht der Text einfach als normale Nachricht ans Modell.

Zwei Folgen:

- **Füllstand nur mit laufendem Orca:** Die Prozentwerte liest der Wächter aus Orca. Ist Orca geschlossen, sieht er
  den Claude-Füllstand nicht und kann nicht rechtzeitig warnen.
- **Faustregel:** Alles, was nachts oder unbeaufsichtigt laufen soll, startest du in **Orca**.

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
| `./waechter.py schwellen` | aktuelle Schwellen anzeigen |
| `./waechter.py schwellen setzen stopp=90` | Schwellen ändern (siehe unten) |
| `./waechter.py report` | Bericht der letzten 24 Stunden (`--stunden 48` für mehr) |
| `./waechter.py simulate zyklus` | kompletter Probelauf mit Probedaten, nichts wird gesendet |
| `./waechter.py simulate stop` | zeigt, was jetzt bei 93 % passieren würde (echte Terminals werden nur gelesen) |
| `./waechter.py tick --dry-run` | ein Durchlauf mit deinen echten Daten auf einer Kopie, nichts wird gesendet |
| `./waechter.py ntfy-abo` | ntfy-Topic in die Zwischenablage (zum Abonnieren in der App) |
| `./waechter.py test-push` | Test-Benachrichtigung aufs Handy |
| `./install.sh` | installieren oder nach einem Update neu einrichten (mit Backup) |
| `./install.sh app` | Menüleisten-App installieren (siehe unten) |
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

Die fünf Schwellen gehen auch per Befehl, ohne die Datei selbst zu bearbeiten:
`./waechter.py schwellen setzen warnung=80 stopp=92 woche_warnung=80 woche_stopp=92 wochen_reserve=20`
(einzelne Werte reichen). Erlaubt sind ganze Zahlen von 1 bis 99, die Reserve von 0 bis 50, und die Warnung muss
unter dem Stopp liegen. Der Befehl schreibt nur die Zeilen unter `[schwellen]` in `config.local.toml`, alles andere
samt Kommentaren bleibt stehen. Bei einem Fehler ändert er nichts.

Änderungen wirken beim nächsten Durchlauf (höchstens eine Minute). Mit `./waechter.py status` siehst du die
aktiven Schwellen. Ist die Datei fehlerhaft, nimmt der Wächter die Standardwerte und schreibt das ins Log.

## Menüleisten-App (seit 1.2)

Eine kleine App in der Menüleiste zeigt dasselbe wie `status` auf einen Blick. Sie ist freiwillig; der Wächter
läuft auch ohne sie. Die App ruft nur `waechter.py` auf, sie tippt nie in Terminals und bedient nie Limit- oder
Kaufmenüs.

- **Voraussetzungen:** macOS 14 oder neuer und die Xcode Command Line Tools (`xcode-select --install`).
- **Installieren:** `./install.sh app`. Das Skript lässt die Tests laufen, baut die App, signiert sie ad hoc (kein
  kostenpflichtiges Entwicklerkonto nötig), kopiert sie nach `~/Applications/Limit-Waechter.app` (eine alte Version
  wandert vorher in die Backups) und richtet einen Autostart ein. Die App startet dann bei jeder Anmeldung und nach
  einem Absturz neu.
- **Anzeige:** Das Ring-Symbol in der Menüleiste färbt sich ab der Warnphase, zeigt einen Mond im Nachtmodus,
  Pausenstriche in der Pause und einen gestrichelten Ring, wenn der Wächter nicht läuft. Ein Klick öffnet je Anbieter
  eine Karte mit 5-Stunden- und Wochenverbrauch, Phase, Reset-Zeit und Countdown, dazu die aktuellen Sitzungen mit
  Zustand und Projektordner und den letzten Durchlauf.
- **Bedienen:** Pause für 30 Minuten, 2 Stunden oder bis auf Weiteres und wieder aufheben; Nachtmodus für alle oder
  per Mond-Schalter je Sitzung; die fünf Schwellen ändern und speichern (landet in `config.local.toml`); Bericht
  ansehen; Log öffnen; Beenden.
- **Sprache:** Die App übernimmt `sprache` aus der Konfiguration.
- **Rückbau:** `./uninstall.sh` entlädt auch den Autostart der App und verschiebt App und Autostart-Datei nach
  `~/.limit-waechter/backups/`. Gelöscht wird nichts.
- Nach `git pull` einfach erneut `./install.sh app` ausführen.

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
