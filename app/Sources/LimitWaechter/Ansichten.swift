import AppKit
import SwiftUI

// Popover-Inhalt der Menüleisten-App (v1.4-Layout):
// Kopf · Statusbanner · Füllstand Claude/Codex · Sitzungen · Schnellschalter · Einstellungen · Fußzeile.

enum Mass {
    static let breite: CGFloat = 360
    static let abstand: CGFloat = 12
    static let eng: CGFloat = 8
    static let radius: CGFloat = 10
}

/// Einheitlicher Kartenhintergrund (Light/Dark über Systemfarben).
struct Karte: ViewModifier {
    var toenung: Color? = nil
    func body(content: Content) -> some View {
        content
            .padding(10)
            .background(RoundedRectangle(cornerRadius: Mass.radius, style: .continuous)
                .fill(toenung.map { AnyShapeStyle($0.opacity(0.14)) } ?? AnyShapeStyle(.quaternary.opacity(0.6))))
    }
}

extension View {
    func karte(_ toenung: Color? = nil) -> some View { modifier(Karte(toenung: toenung)) }
}

struct Hauptansicht: View {
    @EnvironmentObject var s: Speicher
    @Environment(\.openWindow) private var fensterOeffnen

    var body: some View {
        VStack(alignment: .leading, spacing: Mass.abstand) {
            if let pfad = s.startFehler {
                StartFehlerAnsicht(pfad: pfad)
            } else {
                Kopf()
                if let st = s.status {
                    StatusBanner(status: st)
                    HStack(alignment: .top, spacing: Mass.eng) {
                        FuellKarte(anbieter: "claude", name: "Claude", status: st)
                        FuellKarte(anbieter: "codex", name: "Codex", status: st)
                    }
                    .fixedSize(horizontal: false, vertical: true)  // beide Karten gleich hoch
                    SitzungenBereich(status: st)
                    SchnellSchalter(status: st)
                    EinstellungenBereich(status: st)
                } else {
                    HStack { Spacer(); ProgressView().controlSize(.small); Spacer() }
                }
                if let m = s.meldung {
                    Label(m, systemImage: "exclamationmark.circle").font(.caption).foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Divider()
            Fusszeile(berichtOeffnen: {
                fensterOeffnen(id: "bericht")
                NSApp.activate(ignoringOtherApps: true)
            })
        }
        .padding(14)
        .frame(width: Mass.breite)
        .animation(.default, value: s.status?.stufe)
        .task { await s.aktualisieren() }
        .onAppear { s.offen = true }
        .onDisappear { s.offen = false }
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

// MARK: Kopf und Statusbanner

struct Kopf: View {
    @EnvironmentObject var s: Speicher
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(s.t("app_titel")).font(.title3.bold())
            if let v = s.status?.version {
                Text(v).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if s.laedt {
                ProgressView().controlSize(.mini)
            } else {
                Button { Task { await s.aktualisieren() } } label: { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(.borderless)
                    .help(s.t("app_aktualisieren"))
            }
        }
    }
}

struct StatusBanner: View {
    @EnvironmentObject var s: Speicher
    let status: Status

    var body: some View {
        let stufe = status.stufe
        let (farbe, symbol) = Farben.stufe(stufe)
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 10) {
                Image(systemName: symbol).font(.title2).foregroundStyle(farbe)
                    .frame(width: 28)
                VStack(alignment: .leading, spacing: 2) {
                    Text(haupttext(stufe)).font(.headline).fixedSize(horizontal: false, vertical: true)
                    Text(zweitzeile).font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            ForEach(warnungen, id: \.self) { w in
                Label(w, systemImage: "exclamationmark.triangle").font(.caption2).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .karte(farbe)
    }

    /// Satz vom Wächter (v1.4); bei älteren Ausgaben aus den Einzelwerten gebildet.
    private func haupttext(_ stufe: String) -> String {
        if let t = status.gesamt?.text, !t.isEmpty { return t }
        switch stufe {
        case "stoerung": return s.t("app_waechter_aus")
        case "pause":
            if let b = status.pause_bis { return s.t("app_pausiert_bis", ["zeit": s.uhrzeit(b)]) }
            return s.t("app_pausiert")
        case "warnung", "stopp", "limit":
            guard let (a, p) = status.strengstePhase else { return s.t("phase_\(stufe)") }
            let name = a == "codex" ? "Codex" : "Claude"
            var text = "\(name): \(s.t("phase_\(stufe)"))"
            if let r = p.reset { text += " · " + s.t("app_reset", ["zeit": s.uhrzeit(r)]) }
            return text
        case "wartet":
            let n = status.aktuelleSitzungen.filter { ["wartet", "weiter_noetig"].contains($0.lageName) }.count
            return s.t("app_g_wartet", ["anzahl": "\(n)"])
        default: return s.t("app_aktiv")
        }
    }

    private var zweitzeile: String {
        if let d = status.gesamt?.detail, !d.isEmpty { return d }
        guard let tick = status.letzter_tick else { return s.t("app_kein_tick") }
        return s.t("app_letzter_tick", ["dauer": s.dauer(status.zeitpunkt - tick)])
    }

    private var warnungen: [String] {
        var w: [String] = []
        if status.orca_ok == false && status.orca_vorhanden != false { w.append(s.t("app_orca_fehlt")) }
        if status.statusline?.zustand == "zurueckgeschrieben" { w.append(s.t("app_statusline_fehlt")) }
        return w
    }
}

// MARK: Füllstand

/// Balken mit Markern an Warn- und Stoppschwelle.
struct FuellBalken: View {
    let wert: Double?
    let warnung: Int
    let stopp: Int
    var hoehe: CGFloat = 8

    var body: some View {
        GeometryReader { g in
            let w = g.size.width
            let anteil = min(max((wert ?? 0) / 100, 0), 1)
            ZStack(alignment: .leading) {
                Capsule().fill(.quaternary)
                if wert != nil {
                    Capsule().fill(Farben.fuellung(wert ?? 0, warnung: warnung, stopp: stopp))
                        .frame(width: max(anteil > 0 ? hoehe : 0, w * anteil))
                }
                ForEach([warnung, stopp], id: \.self) { m in
                    Rectangle().fill(.primary.opacity(0.35))
                        .frame(width: 1, height: hoehe + 4)
                        .offset(x: w * CGFloat(m) / 100 - 0.5)
                }
            }
        }
        .frame(height: hoehe + 4)
    }
}

struct FuellKarte: View {
    @EnvironmentObject var s: Speicher
    let anbieter: String
    let name: String
    let status: Status

    var body: some View {
        let p = status.phase(anbieter)
        let sw = status.schwellen ?? Schwellen()
        let hatDaten = p?.hatDaten ?? false
        let ph = p?.phaseName ?? "ok"
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Circle().fill(Farben.anbieter(anbieter)).frame(width: 8, height: 8)
                Text(name).font(.subheadline.bold())
                Spacer(minLength: 0)
                if ph != "ok" {
                    Text(s.t("phase_\(ph)")).font(.caption2.bold())
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(Capsule().fill(Farben.phase(ph).opacity(0.25)))
                }
            }
            // 5-Stunden-Fenster: große Zahl
            HStack(alignment: .firstTextBaseline) {
                Text(s.t("app_fuenf")).font(.caption).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Text(hatDaten ? s.prozent(p?.pct5) : "–")
                    .font(.system(size: 24, weight: .semibold, design: .rounded)).monospacedDigit()
            }
            FuellBalken(wert: hatDaten ? p?.pct5 : nil, warnung: sw.warnung, stopp: sw.stopp, hoehe: 7)
            Text(resetText(p?.reset5, hatDaten)).font(.caption2).foregroundStyle(.secondary)

            // Wochenfenster: kleiner
            HStack(alignment: .firstTextBaseline) {
                Text(s.t("app_woche")).font(.caption).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Text(hatDaten ? s.prozent(p?.pctw) : "–").font(.callout.weight(.semibold)).monospacedDigit()
            }
            .padding(.top, 2)
            FuellBalken(wert: hatDaten ? p?.pctw : nil, warnung: sw.woche_warnung, stopp: sw.woche_stopp, hoehe: 4)
            Text(resetText(p?.resetw, hatDaten)).font(.caption2).foregroundStyle(.secondary)

            ForEach(Array((p?.woche_modell ?? []).enumerated()), id: \.offset) { _, m in
                HStack {
                    Text(m.name ?? "–").lineLimit(1)
                    Spacer(minLength: 0)
                    Text(s.prozent(m.pct)).monospacedDigit()
                }
                .font(.caption2).foregroundStyle(.secondary)
            }
            if p?.reserve_erreicht == true {
                Text(s.t("app_reserve_erreicht")).font(.caption2).foregroundStyle(.orange)
            }
            Spacer(minLength: 0)
            Divider()
            quelleZeile(p, hatDaten)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .karte()
    }

    private func resetText(_ r: Double?, _ hatDaten: Bool) -> String {
        guard hatDaten, let r = r else { return " " }
        return s.t("app_reset", ["zeit": s.uhrzeit(r)])
    }

    /// Datenquelle und Alter; orange mit Symbol, wenn veraltet oder die offizielle Anzeige einen Fehler meldet.
    @ViewBuilder
    private func quelleZeile(_ p: Phase?, _ hatDaten: Bool) -> some View {
        let off = status.offiziell?[anbieter]
        let offFehler = off?.zustand == "fehler"
        let veraltet = p?.veraltet == true
        let problem = !hatDaten || veraltet || offFehler
        let quelle = p?.quelle_text ?? p?.quelle ?? s.t("app_keine_daten")
        let text = hatDaten && p?.alter != nil
            ? s.t("app_quelle_alter", ["quelle": quelle, "dauer": s.dauer(p?.alter ?? 0)])
            : (hatDaten ? quelle : s.t("app_keine_daten"))
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Image(systemName: problem ? "exclamationmark.triangle.fill"
                  : (p?.quelle == "offiziell" ? "checkmark.seal.fill" : "antenna.radiowaves.left.and.right"))
            Text(text).lineLimit(2).fixedSize(horizontal: false, vertical: true)
        }
        .font(.caption2)
        .foregroundStyle(problem ? AnyShapeStyle(.orange) : AnyShapeStyle(.secondary))
        .help(hilfe(p, off, veraltet))
    }

    private func hilfe(_ p: Phase?, _ off: OffiziellEintrag?, _ veraltet: Bool) -> String {
        var teile: [String] = []
        if veraltet { teile.append(s.t("app_veraltet", ["dauer": s.dauer(p?.alter ?? 0)])) }
        if let o = off {
            teile.append(s.t("app_offiziell_zeile", ["zustand": Speicher.offiziellText(s, o)]))
        }
        return teile.joined(separator: "\n")
    }
}

extension Speicher {
    /// Zustand der offiziellen Nutzungsanzeige als Text (Fehlercodes übersetzt).
    static func offiziellText(_ s: Speicher, _ o: OffiziellEintrag) -> String {
        switch o.zustand ?? "" {
        case "ok": return s.t("app_of_ok")
        case "aus": return s.t("app_of_aus")
        default:
            if let f = o.fehler, s.texte["app_of_\(f)"] != nil { return s.t("app_of_\(f)") }
            return s.t("app_of_fehler", ["fehler": o.fehler ?? "?"])
        }
    }
}

// MARK: Sitzungen

struct SitzungenBereich: View {
    @EnvironmentObject var s: Speicher
    let status: Status
    @State private var alle = false
    private let maxZeilen = 6

    var body: some View {
        let liste = status.aktuelleSitzungen
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(s.t("app_sitzungen")).font(.headline)
                Spacer()
                if !liste.isEmpty {
                    Text("\(liste.count)").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
            }
            if liste.isEmpty {
                Text(s.t("app_keine_sitzungen")).font(.caption).foregroundStyle(.secondary)
            } else {
                let sichtbar = alle ? liste : Array(liste.prefix(maxZeilen))
                VStack(spacing: 4) {
                    ForEach(sichtbar, id: \.schluessel) { SitzungZeile(sitzung: $0, status: status) }
                }
                if liste.count > maxZeilen {
                    Button(alle ? s.t("app_weniger") : s.t("app_weitere", ["n": "\(liste.count - maxZeilen)"])) {
                        alle.toggle()
                    }
                    .buttonStyle(.borderless).font(.caption)
                }
            }
        }
    }
}

struct LageChip: View {
    let text: String
    let farbe: Color
    var body: some View {
        Text(text)
            .font(.caption.weight(.medium))
            .lineLimit(1)
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(Capsule().fill(farbe.opacity(0.22)))
    }
}

struct SitzungZeile: View {
    @EnvironmentObject var s: Speicher
    let sitzung: Sitzung
    let status: Status

    private var offen: Bool { s.offeneSitzung == sitzung.schluessel }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            kopf
            if offen {
                Divider().padding(.top, 5)
                SitzungDetail(sitzung: sitzung, status: status)
            }
        }
        .padding(.vertical, 5).padding(.horizontal, 8)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
            .fill(.quaternary.opacity(offen ? 0.9 : 0.6)))
    }

    /// Kopfzeile: ein Klick klappt die Detailansicht auf bzw. zu (der Mond bleibt ein eigener Knopf).
    private var kopf: some View {
        HStack(spacing: Mass.eng) {
            Image(systemName: "chevron.right").font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
                .rotationEffect(.degrees(offen ? 90 : 0))
                .frame(width: 8)
            Circle().fill(Farben.anbieter(sitzung.anbieter)).frame(width: 8, height: 8)
                .help(sitzung.anbieter == "codex" ? "Codex" : "Claude")
            VStack(alignment: .leading, spacing: 1) {
                Text(sitzung.anzeigeName).font(.callout).lineLimit(1).truncationMode(.middle)
                HStack(spacing: 6) {
                    if let o = sitzung.ort_text, !o.isEmpty {
                        Text(o).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                    }
                    if let k = sitzung.kontext {
                        KontextMini(kontext: k, schwellen: status.kontext_schwellen ?? KontextSchwellen())
                    }
                }
            }
            .layoutPriority(1)
            Spacer(minLength: 4)
            LageChip(text: lageText, farbe: Farben.lage(sitzung.lageFarbe))
            Button {
                Task { await s.befehl(["nacht", sitzung.eigenerNachtmodus ? "aus" : "an", sitzung.id]) }
            } label: {
                Image(systemName: sitzung.imNachtmodus ? "moon.fill" : "moon")
                    .foregroundStyle(sitzung.eigenerNachtmodus ? Color.indigo
                                     : sitzung.nurGeerbterNachtmodus ? Color.indigo.opacity(0.35) : Color.secondary)
            }
            .buttonStyle(.borderless)
            // Geerbt von „Nacht für alle“: pro Sitzung nicht abschaltbar, deshalb blass und gesperrt
            .disabled(sitzung.nurGeerbterNachtmodus)
            .help(mondHilfe)
        }
        .contentShape(Rectangle())
        .onTapGesture {
            withAnimation(.easeInOut(duration: 0.15)) { s.offeneSitzung = offen ? nil : sitzung.schluessel }
        }
        .help(hilfe)
    }

    private var mondHilfe: String {
        if sitzung.nurGeerbterNachtmodus {
            return s.t("app_nacht_geerbt", ["zeit": s.uhrzeit(sitzung.nacht_global ?? sitzung.nacht_bis ?? 0)])
        }
        if let b = sitzung.nacht_eigen ?? sitzung.nacht_bis { return s.t("app_nacht_sitzung", ["zeit": s.uhrzeit(b)]) }
        return s.t("app_nacht")
    }

    /// Text vom Wächter (v1.4); für ältere Ausgaben aus dem Status gebildet.
    private var lageText: String {
        if let t = sitzung.lage_text, !t.isEmpty { return t }
        switch sitzung.lageName {
        case "wartet":
            if let ab = sitzung.fortsetzen_ab, sitzung.automatisch != false {
                return s.t("app_fortsetzung_ab", ["zeit": s.uhrzeit(ab)])
            }
            return s.t("app_weiter_noetig")
        case "weiter_noetig": return s.t("app_weiter_noetig")
        default: return sitzung.status_text ?? sitzung.status ?? "–"
        }
    }

    private var hilfe: String {
        ([sitzung.faehigkeiten_text, sitzung.status_text].compactMap { $0 }.filter { !$0.isEmpty }
            + [s.t(offen ? "app_kontext_zuklappen" : "app_kontext_details")])
            .joined(separator: " · ")
    }
}

// MARK: Schnellschalter

/// Gleich breite Kachel: Symbol, Titel, Zustandszeile. An = gefüllt in der Akzentfarbe.
struct Kachel: View {
    let titel: String
    let symbol: String
    let zeile: String
    let an: Bool
    var halb: Bool = false
    let farbe: Color
    var laeuft: Bool = false
    let aktion: () -> Void

    var body: some View {
        Button(action: aktion) {
            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Image(systemName: symbol).font(.body.weight(.semibold))
                    Spacer(minLength: 0)
                    if laeuft { ProgressView().controlSize(.mini) }
                }
                Text(titel).font(.callout.weight(.semibold)).lineLimit(1)
                Text(zeile).font(.caption2).lineLimit(1).minimumScaleFactor(0.8)
                    .foregroundStyle(an ? AnyShapeStyle(.white.opacity(0.9)) : AnyShapeStyle(.secondary))
            }
            .foregroundStyle(an ? AnyShapeStyle(.white) : AnyShapeStyle(.primary))
            .padding(.horizontal, 9).padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: Mass.radius, style: .continuous)
                .fill(an ? AnyShapeStyle(farbe) : (halb ? AnyShapeStyle(farbe.opacity(0.22))
                                                       : AnyShapeStyle(.quaternary.opacity(0.6)))))
            .contentShape(RoundedRectangle(cornerRadius: Mass.radius))
        }
        .buttonStyle(.plain)
    }
}

struct SchnellSchalter: View {
    @EnvironmentObject var s: Speicher
    let status: Status

    var body: some View {
        HStack(spacing: Mass.eng) {
            nacht
            wach
            pause
        }
    }

    private var nacht: some View {
        let an = status.nacht != nil
        return Kachel(titel: s.t("app_nacht_kachel"), symbol: an ? "moon.stars.fill" : "moon.stars",
                      zeile: an ? s.t("app_an_bis", ["zeit": s.kurzzeit(status.nacht)]) : s.t("app_aus"),
                      an: an, farbe: .indigo) {
            Task { await s.befehl(["nacht", an ? "aus" : "an"]) }
        }
        .help(an ? s.t("app_nacht_alle", ["zeit": s.uhrzeit(status.nacht)]) : s.t("app_nacht_hinweis"))
    }

    @ViewBuilder
    private var wach: some View {
        let w = status.wach
        let modus = w?.modusName ?? "aus"
        let zeile: String = {
            guard let w = w else { return "–" }
            if s.wachLaeuft { return s.t("app_wach_dialog") }
            switch modus {
            case "manuell": return s.t("app_wach_manuell")
            case "automatisch":
                return w.bis.map { s.t("app_wach_auto_bis", ["zeit": s.kurzzeit($0)]) } ?? s.t("app_wach_auto")
            default: return s.t("app_aus")
            }
        }()
        Kachel(titel: s.t("app_wach_kachel"), symbol: modus == "aus" ? "sun.max" : "sun.max.fill", zeile: zeile,
               an: modus == "manuell", halb: modus == "automatisch", farbe: .orange, laeuft: s.wachLaeuft) {
            Task { await s.wach(modus != "manuell") }
        }
        .disabled(w == nil || s.wachLaeuft)
        .help(modus == "manuell" ? s.t("app_wach_aus_hilfe") : s.t("app_wach_an_hilfe"))
    }

    private var pause: some View {
        let an = status.pausiert == true
        let zeile = an ? (status.pause_bis.map { s.t("app_bis", ["zeit": s.kurzzeit($0)]) } ?? s.t("app_pause_offen"))
                       : s.t("app_aus")
        return Kachel(titel: s.t("app_pause_kachel"), symbol: an ? "pause.circle.fill" : "pause.circle",
                      zeile: zeile, an: an, farbe: .gray) {
            var eintraege: [(String, () -> Void)] = [
                (s.t("app_pause_30m"), { Task { await s.befehl(["pause", "30m"]) } }),
                (s.t("app_pause_2h"), { Task { await s.befehl(["pause", "2h"]) } }),
                (s.t("app_pause_bis_fortsetzen"), { Task { await s.befehl(["pause"]) } }),
            ]
            if an { eintraege.append((s.t("app_pause_ende"), { Task { await s.befehl(["pause", "aus"]) } })) }
            KontextMenue.zeigen(eintraege)
        }
    }
}

/// Kleines Auswahlmenü an der Mausposition (die Kachel bleibt ein normaler Knopf).
@MainActor
enum KontextMenue {
    final class Aktion: NSObject {
        let block: () -> Void
        init(_ block: @escaping () -> Void) { self.block = block }
        @objc func los() { block() }
    }

    static func zeigen(_ eintraege: [(String, () -> Void)]) {
        let menue = NSMenu()
        for (titel, block) in eintraege {
            let aktion = Aktion(block)
            let punkt = NSMenuItem(title: titel, action: #selector(Aktion.los), keyEquivalent: "")
            punkt.target = aktion
            punkt.representedObject = aktion  // hält die Aktion am Leben
            menue.addItem(punkt)
        }
        menue.popUp(positioning: nil, at: NSEvent.mouseLocation, in: nil)
    }
}

// MARK: Einstellungen und Hinweise

struct EinstellungenBereich: View {
    @EnvironmentObject var s: Speicher
    let status: Status
    @State private var offen = Vorschau.einstellungenOffen

    var body: some View {
        DisclosureGroup(isExpanded: $offen) {
            VStack(alignment: .leading, spacing: Mass.abstand) {
                VStack(alignment: .leading, spacing: 4) {
                    Label(s.t("app_schwellen"), systemImage: "slider.horizontal.3").font(.subheadline.bold())
                    // Neu erzeugen, wenn sich die Schwellen von außen ändern (CLI, korrigierte Konfiguration).
                    SchwellenBereich(start: status.schwellen ?? Schwellen())
                        .id(status.schwellen ?? Schwellen())
                }
                // Nur mit einem Wächter, der Kontext-Schwellen kennt (sonst schlägt "schwellen setzen" fehl).
                if let ks = status.kontext_schwellen {
                    VStack(alignment: .leading, spacing: 4) {
                        Label(s.t("app_kontext_schwellen"), systemImage: "text.alignleft").font(.subheadline.bold())
                        KontextSchwellenBereich(start: ks).id(ks)
                    }
                }
                VStack(alignment: .leading, spacing: 4) {
                    Label(s.t("app_hinweise"), systemImage: "info.circle").font(.subheadline.bold())
                    ForEach(Array(hinweise.enumerated()), id: \.offset) { _, h in
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Image(systemName: h.symbol).foregroundStyle(h.farbe).frame(width: 14)
                            Text(h.text).fixedSize(horizontal: false, vertical: true)
                        }
                        .font(.caption)
                    }
                }
            }
            .padding(.top, 6)
        } label: {
            Label(s.t("app_einstellungen"), systemImage: "gearshape").font(.headline)
        }
    }

    private struct Hinweis { var symbol: String; var text: String; var farbe: Color = .secondary }

    private var hinweise: [Hinweis] {
        var h: [Hinweis] = []
        if status.nur_mit_nachtmodus == true {
            h.append(Hinweis(symbol: "moon.stars", text: s.t("app_nacht_hinweis")))
        }
        if status.statusline?.zustand == "zurueckgeschrieben" {
            h.append(Hinweis(symbol: "exclamationmark.triangle", text: s.t("app_statusline_fehlt"), farbe: .orange))
        }
        if status.orca_ok == false && status.orca_vorhanden != false {
            h.append(Hinweis(symbol: "exclamationmark.triangle", text: s.t("app_orca_fehlt"), farbe: .orange))
        }
        for (a, name) in [("claude", "Claude"), ("codex", "Codex")] {
            if let o = status.offiziell?[a] {
                h.append(Hinweis(symbol: o.zustand == "fehler" ? "exclamationmark.triangle" : "checkmark.seal",
                                 text: "\(name): " + s.t("app_offiziell_zeile", ["zustand": Speicher.offiziellText(s, o)]),
                                 farbe: o.zustand == "fehler" ? .orange : .secondary))
            }
        }
        if let w = status.wach {
            if let t = w.text, !t.isEmpty { h.append(Hinweis(symbol: "sun.max", text: t)) }
            if let sp = w.sperre {
                let wert: String
                switch sp {
                case "off": wert = s.t("app_sperre_aus")
                case "immediate": wert = s.t("app_sperre_sofort")
                default: wert = Double(sp).map { s.t("app_sperre_nach", ["dauer": s.dauer($0)]) } ?? sp
                }
                h.append(Hinweis(symbol: "lock", text: s.t("app_sperre", ["wert": wert])))
            }
            if let n = w.netzteil {
                h.append(Hinweis(symbol: n ? "powerplug.fill" : "battery.50",
                                 text: s.t("app_netzteil", ["wert": s.t(n ? "app_ja" : "app_nein")])))
            }
            if let z = w.zugeklappt_ok {
                h.append(Hinweis(symbol: "laptopcomputer", text: s.t("app_zugeklappt", ["wert": s.t(z ? "app_ja" : "app_nein")]),
                                 farbe: z ? .secondary : .orange))
            }
            if let am = w.amphetamine {
                h.append(Hinweis(symbol: "pills", text: s.t("app_amphetamine", ["wert": s.t("app_amph_\(am)")]),
                                 farbe: am == "verweigert" ? .orange : .secondary))
            }
        }
        return h
    }
}

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
        HStack(spacing: Mass.abstand) {
            Button(s.t("app_bericht"), systemImage: "doc.text") { berichtOeffnen() }
            Button(s.t("app_log_oeffnen"), systemImage: "list.bullet.rectangle") {
                NSWorkspace.shared.open(URL(fileURLWithPath: Befehle.logPfad))
            }
            Spacer()
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
