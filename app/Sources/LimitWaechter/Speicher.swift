import Foundation
import SwiftUI

// Zentraler Zustand der App: lädt Status und Texte, führt Befehle aus.

@MainActor
final class Speicher: ObservableObject {
    @Published var status: Status?
    @Published var texte: [String: String] = [:]
    @Published var sprache: String = "de"
    @Published var startFehler: String?
    @Published var meldung: String?
    @Published var bericht: String = ""
    @Published private(set) var laufend = 0
    var laedt: Bool { laufend > 0 }
    @Published var schwellenMeldung: String?
    @Published var schwellenFehler: Bool = false

    private var taktAufgabe: Task<Void, Never>?
    /// Generationsnummer: nur die Antwort der zuletzt gestarteten Aktualisierung wird übernommen.
    private var generation = 0

    init() {
        taktAufgabe = Task { [weak self] in
            await self?.texteLaden()
            while !Task.isCancelled {
                await self?.aktualisieren()
                try? await Task.sleep(nanoseconds: 30_000_000_000)
            }
        }
    }

    // MARK: Texte

    func t(_ schluessel: String, _ werte: [String: String] = [:]) -> String {
        var text = texte[schluessel] ?? schluessel
        for (k, v) in werte { text = text.replacingOccurrences(of: "{\(k)}", with: v) }
        return text
    }

    func texteLaden() async {
        let e = await Befehle.ausfuehren(["app-texte"])
        if let s = e.startFehler { startFehler = s; return }
        if let d = e.ausgabe.data(using: .utf8), let at = try? JSONDecoder().decode(AppTexte.self, from: d) {
            texte = at.texte
            sprache = at.sprache
        }
    }

    // MARK: Status

    func aktualisieren() async {
        generation += 1
        let g = generation
        laufend += 1
        defer { laufend -= 1 }
        let e = await Befehle.ausfuehren(["status", "--json"])
        guard g == generation else { return }
        if let s = e.startFehler { startFehler = s; return }
        guard e.ok, let d = e.ausgabe.data(using: .utf8) else {
            meldung = t("app_fehler", ["fehler": kurz(e)])
            return
        }
        do {
            let neu = try JSONDecoder().decode(Status.self, from: d)
            startFehler = nil
            meldung = nil
            if let sp = neu.sprache, sp != sprache || texte.isEmpty { await texteLaden() }
            guard g == generation else { return }
            status = neu
        } catch {
            meldung = t("app_fehler", ["fehler": error.localizedDescription])
        }
    }

    func befehl(_ argumente: [String]) async {
        let e = await Befehle.ausfuehren(argumente)
        if let s = e.startFehler { startFehler = s; return }
        if !e.ok { meldung = t("app_fehler", ["fehler": kurz(e)]) }
        await aktualisieren()
    }

    func schwellenSpeichern(_ s: Schwellen) async {
        let e = await Befehle.ausfuehren([
            "schwellen", "setzen",
            "warnung=\(s.warnung)", "stopp=\(s.stopp)", "woche_warnung=\(s.woche_warnung)",
            "woche_stopp=\(s.woche_stopp)", "wochen_reserve=\(s.wochen_reserve)", "--json"])
        if let fs = e.startFehler { startFehler = fs; return }
        if let d = e.ausgabe.data(using: .utf8), let a = try? JSONDecoder().decode(SchwellenAntwort.self, from: d) {
            if a.ok {
                schwellenFehler = false
                schwellenMeldung = t("app_gespeichert")
            } else {
                schwellenFehler = true
                schwellenMeldung = t("app_fehler", ["fehler": (a.fehler ?? []).joined(separator: "; ")])
            }
        } else {
            schwellenFehler = true
            schwellenMeldung = t("app_fehler", ["fehler": kurz(e)])
        }
        await aktualisieren()
    }

    func berichtLaden() async {
        bericht = ""
        let e = await Befehle.ausfuehren(["report"])
        if let s = e.startFehler { startFehler = s; return }
        let text = e.ausgabe.trimmingCharacters(in: .whitespacesAndNewlines)
        bericht = e.ok ? (text.isEmpty ? t("app_bericht_leer") : text) : t("app_fehler", ["fehler": kurz(e)])
    }

    private func kurz(_ e: Ergebnis) -> String {
        if e.zeitueberschreitung { return "timeout" }
        let f = e.fehler.trimmingCharacters(in: .whitespacesAndNewlines)
        let zeile = f.split(separator: "\n").last.map(String.init) ?? "exit \(e.code)"
        return String(zeile.prefix(200))
    }

    // MARK: Zeitformate

    var gebietsschema: Locale { Locale(identifier: sprache == "en" ? "en_US" : "de_DE") }

    /// HH:mm heute, "morgen 03:00", sonst Wochentag mit Uhrzeit.
    func uhrzeit(_ ts: Double?) -> String {
        guard let ts = ts else { return "–" }
        let datum = Date(timeIntervalSince1970: ts)
        let f = DateFormatter()
        f.locale = gebietsschema
        if Calendar.current.isDateInToday(datum) {
            f.dateFormat = "HH:mm"
        } else if Calendar.current.isDateInTomorrow(datum) {
            f.dateFormat = "HH:mm"
            return t("app_morgen", ["zeit": f.string(from: datum)])
        } else {
            f.setLocalizedDateFormatFromTemplate("EEE HH:mm")
        }
        return f.string(from: datum)
    }

    func dauer(_ sekunden: Double) -> String {
        let min = max(0, Int(sekunden / 60))
        if min < 60 { return t("app_min", ["n": "\(min)"]) }
        return t("app_std", ["h": "\(min / 60)", "m": "\(min % 60)"])
    }

    var jetzt: Double { Date().timeIntervalSince1970 }
}
