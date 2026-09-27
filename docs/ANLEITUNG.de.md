# Bedienungsanleitung (Deutsch)

Stand: Version 1.4 (offizielle Füllstände, verlässliches Fortsetzen, Wach-Modus, neue App). Die englische Beschreibung steht in der [README](../README.md).

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
| **Limit** | Die Sitzungen stehen schon, der Wächter wartet auf den Reset und hält den Mac wach. |
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
  Den Mac am Netzteil lassen. Solange der Nachtmodus läuft, hält der Wächter den Mac von selbst wach (mit
  Amphetamine auch zugeklappt). Würde er trotzdem einschlafen, warnt dich der Wächter.
- **Morgens:** nichts ausschalten, das passiert um 8 Uhr allein. Kurz den Bericht ansehen.
- **Wenn er dich gerade stört:** Pause (in der App oder `./waechter.py pause 2h`). Dann greift er nirgends ein.

### Wo er wirkt und wo nicht

Seit 1.3 gilt der Wächter für **Orca, normale Terminals und Desktop-Apps, soweit belegt**. Orca ist freiwillig.
Den vollen Umfang gibt es aber nur in Orca: Nur dort liest er den Bildschirm und tippt selbst „weiter“.

**Außerhalb von Orca tippt er nie, liest nie einen Bildschirm und öffnet nie ein Fenster.** Er nutzt dort nur
offizielle Wege. Das heißt im normalen Terminal:

- Warnung und geordneter Stopp funktionieren bei Claude wie in Orca (über die Hooks, echt getestet).
- Nach dem Reset tippt niemand automatisch weiter. Mit Nachtmodus darf Claudes **eingebautes** Weitermachen am
  Limit laufen. Sonst bekommst du einen Push mit einem **Befehl zum Kopieren** (z. B. `claude --resume <ID>`).
- Skript-Aufrufe ohne Fenster (`claude -p`, Agent SDK) und Claude Code im Web lässt er außerhalb von Orca in Ruhe.

| Wo du arbeitest | Warnung | Geordneter Stopp | Fortsetzen nach dem Reset |
|---|---|---|---|
| **Claude Code im Orca-Terminal** | ✅ | ✅ | ✅ (mit Nachtmodus) |
| **Codex im Orca-Terminal** | ✅ | ✅ | ✅ (mit Nachtmodus) |
| Claude Code im normalen Terminal (Terminal.app, iTerm, VS Code …) | ✅ | ✅ | nur Claudes eingebautes Weitermachen am Limit (mit Nachtmodus), sonst Push mit Befehl |
| Codex im normalen Terminal | ✅ | ❌ | nur Push mit Befehl (`codex resume <ID>`); experimentell und ungetestet: `codex_queue = true` |
| Claude-Desktop-App | ✅ | vermutlich wie im Terminal (nicht bestätigt) | vermutlich wie im Terminal (nicht bestätigt) |
| Codex-App | ✅ nur Anzeige | ❌ | ❌ |
| claude.ai, chatgpt.com im Browser | ✅ zählt mit | ❌ | ❌ |

Was heißt „zählt mit“? Alles läuft über **dasselbe Konto-Limit**. Arbeitest du woanders, steigt der Füllstand
genauso, und du bekommst auch die Warnung. `./waechter.py status` und die App zeigen je Sitzung, wo sie läuft und
was der Wächter dort kann (z. B. „Terminal · warnt · stoppt · nur Push“).

**Faustregel:** Was nachts oder unbeaufsichtigt sicher weiterlaufen soll, startest du in **Orca**.

### Warum setzt er in Claude Desktop und der Codex-App nicht selbst fort?

Kurz: Weil es dort keinen sicheren Weg gibt, „weiter“ zu schreiben.

- **Kein offizieller Weg hinein.** Der Wächter tippt nur dort, wo er vorher den Bildschirm lesen kann (Orca). Die
  Desktop-Apps haben keine Schnittstelle, um eine Nachricht in ein laufendes Gespräch zu schicken. Es ginge nur
  mit simulierten Klicks oder Tastendrücken, und die könnten im Limit-Dialog genauso gut einen **Kauf-Knopf**
  treffen. Genau das macht der Wächter nie.
- **Claude kann es schon selbst.** In Claude Code (auch in der Desktop-App, soweit dort die Hooks laufen) gibt es
  Claudes eingebautes Weitermachen am Limit. Mit Nachtmodus lässt der Wächter es laufen, ohne Nachtmodus sperrt er
  es. Die Desktop-App macht also am harten Limit offiziell von selbst weiter.
- **Die Codex-App hat nichts Vergleichbares.** Sie hat eigene Technik ohne Hooks und ohne `codex queue`. Der
  Wächter kann dort nur anzeigen und warnen. Lange Codex-Aufgaben deshalb in einem Orca-Terminal starten.

### Woher kommen die Prozentwerte? (seit 1.4: die offiziellen)

Früher kamen die Werte von Orca. Die hängen manchmal hinterher oder springen (z. B. 99 % → 91 % → 100 % in wenigen
Minuten). Seit 1.4 fragt der Wächter zuerst **dieselbe Stelle ab, die auch Claude Desktop bzw. ChatGPT für ihre
Nutzungsanzeige benutzen**. Dann stimmen die Werte mit dem überein, was du dort siehst.

Ehrlich gesagt: Diese Abfrage ist **nicht offiziell dokumentiert**. Sie liest nur deinen Verbrauch (kein
Modellaufruf, kostet nichts, zählt nicht aufs Limit), nutzt dafür aber deine vorhandene Anmeldung:

- Claude: das Anmelde-Token von Claude Code aus dem macOS-Schlüsselbund; Codex: das Token aus `~/.codex/auth.json`.
- Das Token wird nur kurz gelesen, nur an genau diese zwei Adressen geschickt und **nie gespeichert, geloggt oder
  erneuert**.
- Abgefragt wird alle 3 Minuten, bei Warnung/Stopp/Limit jede Minute. Klappt es nicht (abgelaufene Anmeldung,
  „zu viele Abrufe“, kein Netz), nimmt der Wächter still die alten Quellen (Orca, Statusline, Codex-Protokoll).
- Abschalten: in `config.local.toml` unter `[daten]` `offiziell = false`.

`./waechter.py status` und die App zeigen je Anbieter, woher der Wert kommt und wie alt er ist (z. B. „Claude-Quelle:
offiziell (vor 40 s)“). Steht dort „Anmeldung abgelaufen“: einmal Claude Code öffnen, dann stimmt es wieder. Das
Claude-Token läuft nach ein paar Stunden ohne Claude-Code-Sitzung ab, und der Wächter erneuert es bewusst nicht.

**Frühes Reset:** Setzt Anthropic oder OpenAI ein Fenster vorzeitig zurück (kommt vor), sieht der Wächter das an
den offiziellen Werten und setzt wartende Sitzungen sofort fort, statt bis zur alten Reset-Zeit zu warten.

### Woher kommt der Füllstand ohne Orca? (Statusline-Kette)

Claude Code gibt den aktuellen Füllstand an die Statusline (die Zeile unten in Claude). `./install.sh`
**umhüllt** deine vorhandene Statusline: Zuerst merkt sich der Wächter die Prozentwerte, dann läuft deine
bisherige Statusline **unverändert** weiter. Das Original wird gesichert, `./uninstall.sh` stellt es wieder her.
Liefern Orca und die Statusline beide Werte, gewinnt der frischere. Ersetzt Orca oder ein anderes Tool die
Statusline später, zeigen `status` und die App einen Hinweis; dann einfach `./install.sh` erneut ausführen.
Die Statusline läuft nur, solange eine Claude-Sitzung offen ist.

## Was der Wächter macht, in drei Sätzen

Er schaut jede Minute, wie voll dein Claude- und Codex-Kontingent ist (5-Stunden-Fenster und Woche). Kurz vor dem
Limit sorgt er dafür, dass deine Agenten ihren Stand sichern und geordnet anhalten. Nach dem Reset setzt er
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
| `./waechter.py wach an` / `wach aus` / `wach` | Wach-Modus: Mac bleibt wach, Bildschirmsperre aus (fragt nach dem Passwort; siehe unten) |
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

## Verlässlich fortsetzen (seit 1.4)

Früher hat der Wächter Orca geglaubt, wenn Orca „arbeitet“ meldete. Das ging einmal schief: Eine Sitzung war längst
fertig, hatte aber noch einen Hintergrund-Task laufen. Orca sagte „arbeitet“, der Wächter setzte nicht fort, und die
Sitzung stand fünf Stunden herum, obwohl das Limit längst zurückgesetzt war.

Jetzt gilt: **Orcas „arbeitet“ allein reicht nicht.** Der Wächter braucht einen Beleg:

- auf dem Bildschirm echte Arbeit (Spinner, „esc to interrupt“). Eine bereite Eingabezeile mit einer Fußzeile
  für Hintergrund-Tasks zählt als **bereit**, nicht als „arbeitet“;
- oder im Protokoll der Sitzung (Claude-Transcript bzw. Codex-Protokoll) neue Einträge nach dem Reset, und der
  letzte Turn ist noch nicht beendet.

Hat er eine Sitzung als „läuft bereits“ übersprungen, **prüft er ein paar Minuten später nach**. Ist seit dem Reset
nichts passiert, kommt sie zurück in die Warteschlange und er versucht es erneut (höchstens 2 Fortsetzungen je
Fenster wie bisher; nach 3 erfolglosen Nachprüfungen: blockiert und Push). Ausschalten ginge mit
`[fortsetzen] belege_pruefen = false`, ist aber nicht zu empfehlen.

## Wach-Modus (seit 1.4)

Damit eine Fortsetzung um 7:30 Uhr klappt, darf der Mac nicht schlafen und am besten nicht gesperrt sein. Der
Wach-Modus ersetzt eigene „wach bleiben“-Skripte und hat zwei Teile:

- **Automatisch, ohne Passwort:** Solange eine Fortsetzung ansteht oder der Nachtmodus läuft, hält der Wächter den
  Mac wach. Ist [Amphetamine](https://apps.apple.com/app/amphetamine/id937984704) installiert (kostenlos), startet er
  eine **eigene, befristete** Amphetamine-Sitzung, die den Mac **auch zugeklappt** wach hält. Sonst nutzt er
  `caffeinate` (wirkt nur am Netzteil). Er beendet nur Sitzungen, die er selbst gestartet hat. Beim ersten Mal fragt
  macOS, ob der Wächter Amphetamine steuern darf (Systemeinstellungen › Datenschutz & Sicherheit › Automation).
- **Von Hand:** `./waechter.py wach an`. Es kommt ein Passwort-Fenster von macOS, danach ist die
  **Bildschirmsperre aus** und Amphetamine hält den Mac unbegrenzt wach (auch zugeklappt, kein Bildschirmschoner).
  `./waechter.py wach aus` beendet das und stellt die vorherige Sperrzeit wieder her. `./waechter.py wach` zeigt
  den Zustand. Englisch: `awake on|off|status`. Geht auch über die Kachel **Wach** in der App.

Das Passwort wird nur im Fenster abgefragt und **nie gespeichert oder geloggt**. (Technisch geht es kurz als
Argument an `sysadminctl`, weil das außerhalb eines Terminals der einzige Weg ist; es ist dann für einen Moment in
der Prozessliste deines eigenen Macs sichtbar.) Hattest du vorher ein eigenes Skript mit einer gesicherten Sperrzeit
(Datei `.vorherige-sperre`), übernimmt der Wächter diesen Wert einmal, wenn `[wach] remote_modus_befehl` auf das
Skript zeigt oder `[wach] remote_alt_zustand` auf die Datei. Das alte Skript brauchst du danach nicht mehr.

Ohne Amphetamine klappt alles außer „zugeklappt wach“: Die Sperre geht aus, am Netzteil hält `caffeinate` den Mac
wach, zugeklappt schläft er. `./uninstall.sh` beendet die eigene Amphetamine-Sitzung und warnt, falls der
Wach-Modus noch an ist (dann zuerst `wach aus`).

## Schwellen und Verhalten einstellen

Eigene Werte gehören in die Datei **`config.local.toml`** im Ordner des Wächters. Sie wird nie hochgeladen und
überschreibt die Standardwerte aus `config.toml`. Beispiel:

```toml
[allgemein]
sprache = "de"             # deutsche Pushes und Ausgaben
name = "Alex"              # erscheint in den Hinweisen, die Claude bekommt

nur_orca = false           # true = nur Sitzungen in Orca-Terminals überwachen (Verhalten bis 1.2)

[schwellen]
warnung = 80               # ab so viel % des 5h-Fensters: Warnung aufs Handy
stopp = 92                 # ab so viel %: geordneter Stopp (sichern, anhalten)
woche_warnung = 80         # dasselbe fürs Wochenfenster
woche_stopp = 92
wochen_reserve = 20        # ab 100 - 20 = 80 % Wochenverbrauch: keine automatische Fortsetzung mehr

[fortsetzen]
aktiv = true               # false = nach dem Reset nie automatisch fortsetzen (Stopp läuft trotzdem)
nur_mit_nachtmodus = true  # nur Sitzungen im Nachtmodus fortsetzen; false = alles (Verhalten von 1.0)
codex_queue = false        # experimentell, ungetestet: Codex im normalen Terminal per `codex queue` stoppen/fortsetzen
puffer_minuten = 2         # so lange nach dem Reset warten
max_pro_fenster = 2        # höchstens so viele automatische Fortsetzungen je Sitzung und Fenster

[daten]
offiziell = true           # offizielle Füllstände abfragen (siehe oben); false = nur Orca/Statusline/Codex-Protokoll

[wach]
amphetamine = true         # Amphetamine nutzen, falls installiert
bei_nachtmodus = true      # Mac wach halten, solange der Nachtmodus läuft

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

## Menüleisten-App (seit 1.2, neu gestaltet in 1.4)

Eine kleine App in der Menüleiste zeigt dasselbe wie `status` auf einen Blick. Sie ist freiwillig; der Wächter
läuft auch ohne sie. Die App ruft nur `waechter.py` auf, sie tippt nie in Terminals und bedient nie Limit- oder
Kaufmenüs.

- **Voraussetzungen:** macOS 14 oder neuer und die Xcode Command Line Tools (`xcode-select --install`).
- **Installieren:** `./install.sh app`. Das Skript lässt die Tests laufen, baut die App, signiert sie ad hoc (kein
  kostenpflichtiges Entwicklerkonto nötig), kopiert sie nach `~/Applications/Limit-Waechter.app` (eine alte Version
  wandert vorher in die Backups) und richtet einen Autostart ein. Die App startet dann bei jeder Anmeldung und nach
  einem Absturz neu.
- **Anzeige:** Das Ring-Symbol in der Menüleiste färbt sich ab der Warnphase, zeigt einen Mond im Nachtmodus,
  Pausenstriche in der Pause und einen gestrichelten Ring, wenn der Wächter nicht läuft. Ein Klick öffnet das
  Fenster, von oben nach unten:
  1. **Ein Satz zum Gesamtzustand**, z. B. „Alles gut“, „Stopp – Reset 17:50“ oder „2 Sitzung(en) warten“.
  2. **Je eine Karte für Claude und Codex:** 5-Stunden-Wert groß, Woche darunter, Balken mit Markierungen für
     Warnung und Stopp, Reset-Uhrzeit und woher der Wert kommt (z. B. „offiziell · vor 1 min“).
  3. **Sitzungen kompakt:** Projekt, Ort und ein farbiger Zustand („arbeitet“, „wartet bis 07:32“, „„weiter“
     nötig“, „blockiert“ …); der Mond schaltet den Nachtmodus je Sitzung.
  4. **Schnellschalter:** **Nacht** (alle Sitzungen), **Wach** (Wach-Modus, das Passwort-Fenster kommt von macOS)
     und **Pause**.
  5. **Einstellungen** (eingeklappt): Schwellen, Hinweise, Bericht, Log.
- **Bedienen:** Pause für 30 Minuten, 2 Stunden oder bis du fortsetzt; Nachtmodus für alle oder je Sitzung;
  Wach-Modus an/aus; die fünf Schwellen ändern und speichern (landet in `config.local.toml`); Bericht ansehen; Log
  öffnen; Beenden.
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
| Limit | 100 % | Sitzungen werden mit Reset-Zeit gemerkt, der Mac bleibt wach (Wach-Modus automatisch) |
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
  Fortsetzung nicht. Abhilfe: Netzteil anschließen und `./waechter.py wach an` (steht auch im Push).
- **„Limit wurde vorzeitig zurückgesetzt“:** Der Anbieter hat früher zurückgesetzt; wartende Sitzungen im
  Nachtmodus laufen jetzt weiter.
- **„offizielle Werte nicht verfügbar, Anmeldung abgelaufen“:** Einmal Claude Code (bzw. Codex) öffnen. Bis dahin
  nimmt der Wächter die Orca-Werte, die hinterherhängen können.
- **„Der Limit-Wächter darf Amphetamine nicht steuern“:** In den Systemeinstellungen unter Automation erlauben.
- **„Guthaben gesunken“ / „Extra-Usage aktiv“:** Bitte prüfen, der Wächter selbst gibt nie Geld aus.

## Für welche Apps gilt das?

Für **Claude Code** und **Codex CLI** in Orca und in normalen Terminals, mit den Einschränkungen aus der Tabelle
[Wo er wirkt und wo nicht](#wo-er-wirkt-und-wo-nicht). Die Claude-Desktop-App vermutlich wie ein Terminal (nicht
bestätigt), die Codex-App nur mit Anzeige und Warnung. Der Verbrauch aller Apps zählt in den Prozentwerten mit.

## Wenn etwas komisch ist

1. `./waechter.py status`: Läuft der LaunchAgent, und wann war der letzte Tick? Woher kommen die Werte
   (offiziell, Orca, Statusline)? Weichen sie von Claude Desktop ab, steht unter „offizielle Anzeige“ meist der
   Grund.
2. Log ansehen: `tail -50 ~/.limit-waechter/log/waechter.log`. Dort steht auch jeder Bildschirm, den der Wächter vor
   dem Senden gelesen hat.
3. Sofort alles anhalten: `./waechter.py pause`.
4. Zurückbauen: `./uninstall.sh` (Backups liegen in `~/.limit-waechter/backups/`).
