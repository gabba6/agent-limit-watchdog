import SwiftUI

// Kontextfüllstand je Sitzung (v1.4): Mini-Balken in der Sitzungszeile, aufklappbare Detailansicht
// und die einstellbaren Kontext-Schwellen. Fehlt "kontext" (älterer Wächter), wird nichts angezeigt.

/// Balken mit feinen Markierungen an Warn- und Kritisch-Schwelle; Farbe nach Stufe.
struct KontextBalken: View {
    let wert: Double?
    let stufe: String
    let schwellen: KontextSchwellen
    var hoehe: CGFloat = 8
    var marker = true

    var body: some View {
        GeometryReader { g in
            let w = g.size.width
            let anteil = min(max((wert ?? 0) / 100, 0), 1)
            ZStack(alignment: .leading) {
                Capsule().fill(.quaternary)
                if wert != nil {
                    Capsule().fill(Farben.kontext(stufe))
                        .frame(width: max(anteil > 0 ? hoehe : 0, w * anteil))
                }
                if marker {
                    ForEach([schwellen.warnung, schwellen.kritisch], id: \.self) { m in
                        Rectangle().fill(.primary.opacity(0.35))
                            .frame(width: 1, height: hoehe + 4)
                            .offset(x: w * CGFloat(m) / 100 - 0.5)
                    }
                }
            }
        }
        .frame(height: marker ? hoehe + 4 : hoehe)
    }
}

/// Kleiner Balken plus Prozent für die Sitzungszeile.
struct KontextMini: View {
    @EnvironmentObject var s: Speicher
    let kontext: Kontext
    let schwellen: KontextSchwellen

    var body: some View {
        if let w = kontext.wert {
            let stufe = kontext.stufeName(schwellen)
            HStack(spacing: 4) {
                KontextBalken(wert: w, stufe: stufe, schwellen: schwellen, hoehe: 4, marker: false)
                    .frame(width: 34)
                Text(s.prozent(w)).monospacedDigit()
                    .foregroundStyle(stufe == "ok" ? AnyShapeStyle(.secondary) : AnyShapeStyle(Farben.kontext(stufe)))
            }
            .font(.caption2)
            .help(s.t("app_kontext_titel") + ": " + s.t("app_kontext_tokens", [
                "tokens": s.tokens(kontext.tokens), "fenster": s.tokens(kontext.fenster), "prozent": s.prozent(w)]))
        }
    }
}

/// Aufgeklappte Detailansicht einer Sitzung (unter der Zeile).
struct SitzungDetail: View {
    @EnvironmentObject var s: Speicher
    let sitzung: Sitzung
    let status: Status

    var body: some View {
        let sw = status.kontext_schwellen ?? KontextSchwellen()
        VStack(alignment: .leading, spacing: 8) {
            kontextBlock(sw)
            Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 10, verticalSpacing: 4) {
                if let m = sitzung.kontext?.modell, !m.isEmpty {
                    zeile("app_kontext_modell", m)
                }
                if let o = sitzung.ort_text ?? sitzung.ort, !o.isEmpty {
                    zeile("app_kontext_ort", o)
                }
                zeile("app_kontext_zustand", zustand)
                if let a = sitzung.aktivitaet?.letzte ?? sitzung.zuletzt {
                    zeile("app_kontext_aktivitaet", s.t("app_kontext_vor", ["dauer": s.dauer(s.jetzt - a)]))
                }
                if let e = sitzung.erstellt, e > 0 {
                    zeile("app_kontext_laufzeit", s.dauer(s.jetzt - e))
                }
                if let k = sitzung.kontext, k.wert != nil {
                    quelleZeile(k)
                }
                GridRow {
                    Text(s.t("app_kontext_nacht")).foregroundStyle(.secondary)
                    Toggle("", isOn: Binding(
                        get: { sitzung.imNachtmodus },
                        set: { an in Task { await s.befehl(["nacht", an ? "an" : "aus", sitzung.id]) } }))
                        .labelsHidden().toggleStyle(.switch).controlSize(.mini)
                        .disabled(sitzung.nurGeerbterNachtmodus)
                        .help(sitzung.nurGeerbterNachtmodus
                              ? s.t("app_nacht_geerbt", ["zeit": s.uhrzeit(sitzung.nacht_global ?? sitzung.nacht_bis ?? 0)])
                              : s.t("app_nacht"))
                }
            }
            .font(.caption)
        }
        .padding(.top, 6)
    }

    @ViewBuilder
    private func kontextBlock(_ sw: KontextSchwellen) -> some View {
        if let k = sitzung.kontext, let w = k.wert {
            let stufe = k.stufeName(sw)
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline) {
                    Text(s.t("app_kontext_titel")).font(.caption).foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                    if stufe != "ok" {
                        Text(stufeText(stufe)).font(.caption2.bold())
                            .padding(.horizontal, 5).padding(.vertical, 1)
                            .background(Capsule().fill(Farben.kontext(stufe).opacity(0.25)))
                    }
                }
                KontextBalken(wert: w, stufe: stufe, schwellen: sw, hoehe: 10)
                Text(k.tokens != nil && k.fenster != nil
                     ? s.t("app_kontext_tokens", ["tokens": s.tokens(k.tokens), "fenster": s.tokens(k.fenster),
                                                  "prozent": s.prozent(w)])
                     : s.prozent(w))
                    .font(.callout.weight(.semibold)).monospacedDigit()
            }
        } else {
            Text(s.t("app_kontext_keine")).font(.caption).foregroundStyle(.secondary)
        }
    }

    private func zeile(_ titel: String, _ wert: String) -> some View {
        GridRow {
            Text(s.t(titel)).foregroundStyle(.secondary)
            Text(wert).lineLimit(2).fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Quelle und Alter; älter als 10 min gedimmt.
    private func quelleZeile(_ k: Kontext) -> some View {
        let quelle = quelleText(k.quelle)
        let alter = k.stand.map { s.jetzt - $0 }
        let text = alter.map { s.t("app_kontext_quelle_alter", ["quelle": quelle, "dauer": s.dauer($0)]) } ?? quelle
        return GridRow {
            Text(s.t("app_kontext_quelle")).foregroundStyle(.secondary)
            Text(text).opacity((alter ?? 0) > 600 ? 0.5 : 1)
        }
    }

    private var zustand: String {
        if let t = sitzung.lage_text, !t.isEmpty { return t }
        return sitzung.status_text ?? sitzung.status ?? "–"
    }

    private func stufeText(_ stufe: String) -> String {
        switch stufe {
        case "kritisch": return s.t("app_kontext_stufe_kritisch")
        case "warnung": return s.t("app_kontext_stufe_warnung")
        default: return s.t("app_kontext_stufe_ok")
        }
    }

    private func quelleText(_ q: String?) -> String {
        switch q ?? "" {
        case "statusline": return s.t("app_kontext_quelle_statusline")
        case "transcript": return s.t("app_kontext_quelle_transcript")
        case "rollout": return s.t("app_kontext_quelle_rollout")
        default: return q ?? "–"
        }
    }
}

/// Einstellungen: Kontext-Warnung und -kritisch (Prozent).
struct KontextSchwellenBereich: View {
    @EnvironmentObject var s: Speicher
    @State var werte: KontextSchwellen

    init(start: KontextSchwellen) { _werte = State(initialValue: start) }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            stepper("app_kontext_warnung", $werte.warnung)
            stepper("app_kontext_kritisch", $werte.kritisch)
            HStack {
                Button(s.t("app_speichern")) { Task { await s.kontextSchwellenSpeichern(werte) } }
                    .controlSize(.small)
                    .disabled(werte.warnung >= werte.kritisch)
                if let m = s.kontextMeldung {
                    Text(m).font(.caption).foregroundStyle(s.kontextFehler ? .red : .green)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func stepper(_ k: String, _ b: Binding<Int>) -> some View {
        Stepper(value: b, in: 1...99) {
            HStack { Text(s.t(k)).font(.callout); Spacer(); Text("\(b.wrappedValue)").monospacedDigit() }
        }
    }
}
