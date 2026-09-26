import AppKit
import SwiftUI

// Popover-Inhalt der Menüleisten-App.

struct Hauptansicht: View {
    @EnvironmentObject var s: Speicher
    @Environment(\.openWindow) private var fensterOeffnen
    @State private var schwellenOffen = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let pfad = s.startFehler {
                StartFehlerAnsicht(pfad: pfad)
            } else {
                Kopf()
                if let st = s.status {
                    HStack(spacing: 10) {
                        AnbieterKarte(name: "Claude", phase: st.phase("claude"), jetzt: st.zeitpunkt)
                        AnbieterKarte(name: "Codex", phase: st.phase("codex"), jetzt: st.zeitpunkt)
                    }
                    Divider()
                    PauseBereich(status: st)
                    Divider()
                    NachtBereich(status: st)
                    Divider()
                    DisclosureGroup(isExpanded: $schwellenOffen) {
                        // Neu erzeugen, wenn sich die Schwellen von außen ändern (CLI, korrigierte Konfiguration).
                        SchwellenBereich(start: st.schwellen ?? Schwellen())
                            .id(st.schwellen ?? Schwellen())
                    } label: {
                        Label(s.t("app_schwellen"), systemImage: "slider.horizontal.3").font(.headline)
                    }
                } else {
                    HStack { Spacer(); ProgressView().controlSize(.small); Spacer() }
                }
                if let m = s.meldung {
                    Text(m).font(.caption).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true)
                }
            }
            Divider()
            Fusszeile(berichtOeffnen: {
                fensterOeffnen(id: "bericht")
                NSApp.activate(ignoringOtherApps: true)
            })
        }
        .padding(14)
        .frame(width: 340)
        .task { await s.aktualisieren() }
    }
}

struct StartFehlerAnsicht: View {
    @EnvironmentObject var s: Speicher
    let pfad: String
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Limit-Wächter", systemImage: "exclamationmark.triangle.fill").font(.headline)
            if s.texte["app_python_fehlt"] != nil {
                Text(s.t("app_python_fehlt", ["pfad": pfad])).font(.callout)
            } else {
            // Notlösung ohne geladene Texte: Python/waechter.py startet nicht.
            Text("Python or waechter.py could not be started: \(pfad)").font(.callout)
            Text("Python oder waechter.py konnte nicht gestartet werden: \(pfad)").font(.callout)
                .foregroundStyle(.secondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

struct Kopf: View {
    @EnvironmentObject var s: Speicher
    var body: some View {
        let st = s.status
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(s.t("app_titel")).font(.title3.bold())
                    Text(s.t("app_version", ["version": st?.version ?? "?"])).font(.caption).foregroundStyle(.secondary)
                }
                HStack(spacing: 5) {
                    Circle().fill(zustandFarbe(st)).frame(width: 7, height: 7)
                    Text(zustandText(st)).font(.caption)
                }
                Text(tickText(st)).font(.caption2).foregroundStyle(.secondary)
                if st?.orca_ok == false && st?.orca_vorhanden != false {
                    Text(s.t("app_orca_fehlt")).font(.caption2).foregroundStyle(.orange)
                }
                if st?.statusline?.zustand == "zurueckgeschrieben" {
                    Text(s.t("app_statusline_fehlt")).font(.caption2).foregroundStyle(.orange)
                }
            }
            Spacer()
            if st?.nacht != nil { MondAnimation().frame(width: 34, height: 34) }
        }
    }

    func zustandFarbe(_ st: Status?) -> Color {
        guard let st = st else { return .gray }
        if st.launchagent == false { return .red }
        if st.pausiert == true { return .orange }
        return .green
    }

    func zustandText(_ st: Status?) -> String {
        guard let st = st else { return "…" }
        if st.launchagent == false { return s.t("app_waechter_aus") }
        if st.pausiert == true {
            if let b = st.pause_bis { return s.t("app_pausiert_bis", ["zeit": s.uhrzeit(b)]) }
            return s.t("app_pausiert")
        }
        return s.t("app_aktiv")
    }

    func tickText(_ st: Status?) -> String {
        guard let tick = st?.letzter_tick else { return s.t("app_kein_tick") }
        return s.t("app_letzter_tick", ["dauer": s.dauer((st?.zeitpunkt ?? s.jetzt) - tick)])
    }
}

// MARK: Karten mit Doppelring

struct DoppelRing: View {
    let aussen: Double
    let innen: Double
    let farbeAussen: Color
    let farbeInnen: Color
    @Environment(\.accessibilityReduceMotion) private var wenigBewegung
    @State private var gezeigtAussen: Double = 0
    @State private var gezeigtInnen: Double = 0

    var body: some View {
        ZStack {
            Circle().stroke(farbeAussen.opacity(0.18), lineWidth: 9)
            Circle().trim(from: 0, to: gezeigtAussen / 100)
                .stroke(farbeAussen, style: StrokeStyle(lineWidth: 9, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Circle().stroke(farbeInnen.opacity(0.15), lineWidth: 6).padding(12)
            Circle().trim(from: 0, to: gezeigtInnen / 100)
                .stroke(farbeInnen.opacity(0.75), style: StrokeStyle(lineWidth: 6, lineCap: .round))
                .rotationEffect(.degrees(-90)).padding(12)
        }
        .onAppear { setzen() }
        .onChange(of: aussen) { setzen() }
        .onChange(of: innen) { setzen() }
    }

    private func setzen() {
        let a = min(max(aussen, 0), 100), i = min(max(innen, 0), 100)
        if wenigBewegung {
            gezeigtAussen = a; gezeigtInnen = i
        } else {
            withAnimation(.spring(response: 0.9, dampingFraction: 0.7)) { gezeigtAussen = a; gezeigtInnen = i }
        }
    }
}

struct AnbieterKarte: View {
    @EnvironmentObject var s: Speicher
    let name: String
    let phase: Phase?
    let jetzt: Double
    @Environment(\.accessibilityReduceMotion) private var wenigBewegung
    @State private var puls = false

    var body: some View {
        let p = phase
        let ph = p?.phaseName ?? "ok"
        let farbe = Farben.phase(ph)
        let hatDaten = p?.hatDaten ?? false
        let alarm = ph == "stopp" || ph == "limit"
        VStack(spacing: 6) {
            HStack {
                Text(name).font(.subheadline.bold())
                Spacer()
                Text(s.t("phase_\(ph)")).font(.caption2.bold())
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Capsule().fill(farbe.opacity(0.22)))
            }
            ZStack {
                DoppelRing(aussen: p?.pct5 ?? 0, innen: p?.pctw ?? 0,
                           farbeAussen: farbe, farbeInnen: .blue)
                VStack(spacing: 0) {
                    Text(hatDaten ? "\(Int((p?.pct5 ?? 0).rounded()))%" : "–")
                        .font(.system(.title3, design: .rounded).bold()).monospacedDigit()
                        .contentTransition(.numericText())
                    Text(hatDaten ? "\(Int((p?.pctw ?? 0).rounded()))%" : "")
                        .font(.caption2).foregroundStyle(.secondary).monospacedDigit()
                }
            }
            .frame(width: 96, height: 96)
            HStack(spacing: 8) {
                legende(.blue.opacity(0.75), s.t("app_woche"))
                legende(farbe, s.t("app_fuenf"))
            }
            // Kommt die Phase vom Wochenfenster, zählt der Wochen-Reset.
            let woche = p?.art == "woche"
            if hatDaten, let r = woche ? (p?.resetw ?? p?.reset) : p?.reset5 {
                Text((woche ? s.t("app_woche") + " · " : "") + s.t("app_reset", ["zeit": s.uhrzeit(r)]))
                    .font(.caption2)
                Text(s.dauer(r - s.jetzt)).font(.caption2).foregroundStyle(.secondary)
            }
            if !hatDaten {
                hinweis(s.t("app_keine_daten"), .secondary)
            } else if p?.veraltet == true {
                hinweis(s.t("app_veraltet", ["dauer": s.dauer(p?.alter ?? 0)]), .orange)
            }
            if p?.reserve_erreicht == true { hinweis(s.t("app_reserve_erreicht"), .orange) }
        }
        .padding(10)
        .frame(maxWidth: .infinity)
        .background(RoundedRectangle(cornerRadius: 12).fill(.background.secondary))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(farbe.opacity(alarm ? (puls ? 0.9 : 0.25) : 0), lineWidth: 2)
        )
        .onAppear { pulsStarten(alarm) }
        .onChange(of: alarm) { pulsStarten(alarm) }
    }

    private func pulsStarten(_ an: Bool) {
        guard an, !wenigBewegung else { puls = an; return }
        withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true)) { puls = true }
    }

    private func legende(_ f: Color, _ t: String) -> some View {
        HStack(spacing: 3) { Circle().fill(f).frame(width: 6, height: 6); Text(t).font(.caption2) }
    }

    private func hinweis(_ t: String, _ f: Color) -> some View {
        Text(t).font(.caption2).foregroundStyle(f).multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: Mond mit funkelnden Sternen

struct MondAnimation: View {
    @Environment(\.accessibilityReduceMotion) private var wenigBewegung
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 20, paused: wenigBewegung)) { kontext in
            let t = kontext.date.timeIntervalSinceReferenceDate
            ZStack {
                Image(systemName: "moon.fill").font(.system(size: 18)).foregroundStyle(.indigo)
                ForEach(0..<3, id: \.self) { i in
                    let phase = wenigBewegung ? 1 : (sin(t * 2 + Double(i) * 2.1) + 1) / 2
                    Image(systemName: "sparkle").font(.system(size: 7))
                        .foregroundStyle(.yellow)
                        .opacity(0.3 + 0.7 * phase)
                        .scaleEffect(0.7 + 0.4 * phase)
                        .offset(x: [12, -12, 10][i], y: [-12, -8, 12][i])
                }
            }
        }
    }
}

// MARK: Pause

struct PauseBereich: View {
    @EnvironmentObject var s: Speicher
    let status: Status
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(s.t("app_pause"), systemImage: "pause.circle").font(.headline)
            HStack {
                knopf("app_pause_30m", ["pause", "30m"])
                knopf("app_pause_2h", ["pause", "2h"])
                knopf("app_pause_offen", ["pause"])
                if status.pausiert == true { knopf("app_pause_ende", ["pause", "aus"]) }
            }
        }
    }

    private func knopf(_ schluessel: String, _ args: [String]) -> some View {
        Button(s.t(schluessel)) { Task { await s.befehl(args) } }.controlSize(.small)
    }
}

// MARK: Nachtmodus

struct NachtBereich: View {
    @EnvironmentObject var s: Speicher
    let status: Status

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Toggle(isOn: Binding(
                get: { status.nacht != nil },
                set: { an in Task { await s.befehl(["nacht", an ? "an" : "aus"]) } })) {
                VStack(alignment: .leading, spacing: 1) {
                    Label(s.t("app_nacht"), systemImage: "moon.stars").font(.headline)
                    Text(status.nacht.map { s.t("app_nacht_alle", ["zeit": s.uhrzeit($0)]) } ?? s.t("app_nacht_aus"))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .toggleStyle(.switch)
            if status.nur_mit_nachtmodus == true {
                Text(s.t("app_nacht_hinweis")).font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(s.t("app_sitzungen")).font(.subheadline.bold()).padding(.top, 2)
            let liste = status.aktuelleSitzungen
            if liste.isEmpty {
                Text(s.t("app_keine_sitzungen")).font(.caption).foregroundStyle(.secondary)
            } else {
                ScrollView {
                    VStack(spacing: 4) { ForEach(liste) { SitzungZeile(sitzung: $0) } }
                }
                // Feste Höhe: eine ScrollView mit nur maxHeight fällt im Popover auf 0 zusammen.
                .frame(height: min(CGFloat(liste.count) * 40, 170))
            }
        }
    }
}

struct SitzungZeile: View {
    @EnvironmentObject var s: Speicher
    let sitzung: Sitzung

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: sitzung.anbieter == "codex" ? "chevron.left.forwardslash.chevron.right" : "sparkles")
                .foregroundStyle(sitzung.anbieter == "codex" ? Color.teal : Color.orange)
                .frame(width: 16)
            VStack(alignment: .leading, spacing: 1) {
                Text(sitzung.anzeigeName).font(.callout).lineLimit(1).truncationMode(.middle)
                Text(zeile2).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                if let z = zeile3 {
                    Text(z).font(.caption2).foregroundStyle(.tertiary).lineLimit(1).truncationMode(.tail)
                }
            }
            Spacer()
            Button {
                Task { await s.befehl(["nacht", sitzung.imNachtmodus ? "aus" : "an", sitzung.id]) }
            } label: {
                Image(systemName: sitzung.imNachtmodus ? "moon.fill" : "moon")
                    .foregroundStyle(sitzung.imNachtmodus ? Color.indigo : Color.secondary)
            }
            .buttonStyle(.borderless)
            .help(sitzung.nacht_bis.map { s.t("app_nacht_sitzung", ["zeit": s.uhrzeit($0)]) } ?? s.t("app_nacht"))
        }
        .padding(.vertical, 3).padding(.horizontal, 6)
        .background(RoundedRectangle(cornerRadius: 7).fill(.background.secondary))
    }

    var zeile2: String {
        var teile = [sitzung.status_text ?? sitzung.status ?? ""]
        if sitzung.wartet == true, let ab = sitzung.fortsetzen_ab, sitzung.automatisch != false {
            teile.append(s.t("app_fortsetzung_ab", ["zeit": s.uhrzeit(ab)]))
        } else if sitzung.status == "wartet_auf_weiter" || sitzung.wartet == true {
            teile.append(s.t("app_weiter_noetig"))
        }
        return teile.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    var zeile3: String? {
        let teile = [sitzung.ort_text, sitzung.faehigkeiten_text].compactMap { $0 }.filter { !$0.isEmpty }
        return teile.isEmpty ? nil : teile.joined(separator: " · ")
    }
}

// MARK: Schwellen

struct SchwellenBereich: View {
    @EnvironmentObject var s: Speicher
    @State var werte: Schwellen

    init(start: Schwellen) { _werte = State(initialValue: start) }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            stepper("app_warnung", $werte.warnung, 1...99)
            stepper("app_stopp", $werte.stopp, 1...99)
            stepper("app_woche_warnung", $werte.woche_warnung, 1...99)
            stepper("app_woche_stopp", $werte.woche_stopp, 1...99)
            stepper("app_reserve", $werte.wochen_reserve, 0...50)
            HStack {
                Button(s.t("app_speichern")) { Task { await s.schwellenSpeichern(werte) } }
                    .controlSize(.small).keyboardShortcut(.defaultAction)
                if let m = s.schwellenMeldung {
                    Text(m).font(.caption).foregroundStyle(s.schwellenFehler ? .red : .green)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(.top, 4)
    }

    private func stepper(_ k: String, _ b: Binding<Int>, _ r: ClosedRange<Int>) -> some View {
        Stepper(value: b, in: r) {
            HStack { Text(s.t(k)).font(.callout); Spacer(); Text("\(b.wrappedValue)").monospacedDigit() }
        }
    }
}

// MARK: Fußzeile und Bericht

struct Fusszeile: View {
    @EnvironmentObject var s: Speicher
    let berichtOeffnen: () -> Void
    var body: some View {
        HStack {
            Button(s.t("app_bericht"), systemImage: "doc.text") { berichtOeffnen() }
            Button(s.t("app_log_oeffnen"), systemImage: "list.bullet.rectangle") {
                NSWorkspace.shared.open(URL(fileURLWithPath: Befehle.logPfad))
            }
            Spacer()
            Button { Task { await s.aktualisieren() } } label: {
                Image(systemName: "arrow.clockwise").rotationEffect(.degrees(s.laedt ? 180 : 0))
            }
            .help(s.t("app_aktualisieren"))
            Button { NSApp.terminate(nil) } label: { Image(systemName: "power") }
                .help(s.t("app_beenden"))
        }
        .buttonStyle(.borderless)
        .labelStyle(.titleAndIcon)
        .font(.caption)
    }
}

struct BerichtFenster: View {
    @EnvironmentObject var s: Speicher
    @Environment(\.dismissWindow) private var schliessen
    var body: some View {
        VStack(spacing: 8) {
            ScrollView {
                Text(s.bericht.isEmpty ? "…" : s.bericht)
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
            }
            HStack {
                Button(s.t("app_aktualisieren")) { Task { await s.berichtLaden() } }
                Spacer()
                Button(s.t("app_schliessen")) { schliessen(id: "bericht") }.keyboardShortcut(.cancelAction)
            }
            .padding([.horizontal, .bottom])
        }
        .frame(minWidth: 520, minHeight: 380)
        .task { await s.berichtLaden() }
    }
}
