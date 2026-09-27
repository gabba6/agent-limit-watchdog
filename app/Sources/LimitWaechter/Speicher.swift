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
    /// Läuft gerade "wach an/aus" (Passwortdialog offen)?
    @Published var wachLaeuft = false
    /// Popover sichtbar? Dann wird bei Stopp/Limit/Warten öfter aktualisiert.
    var offen = false

    /// Vorschau mit Demo-Daten: Status aus dieser Datei, Befehle wirkungslos.
    let demoPfad: String?
    var demo: Bool { demoPfad != nil }

    private var taktAufgabe: Task<Void, Never>?
    /// Generationsnummer: nur die Antwort der zuletzt gestarteten Aktualisierung wird übernommen.
    private var generation = 0

    init(demo: String? = nil) {
        demoPfad = demo
        taktAufgabe = Task { [weak self] in
            await self?.texteLaden()
            while !Task.isCancelled {
                await self?.aktualisieren()
                let takt = self?.taktSekunden ?? 30
                try? await Task.sleep(nanoseconds: UInt64(takt) * 1_000_000_000)
            }
        }
    }

    /// 10 s, solange das Popover offen ist und etwas ansteht (Stopp, Limit, wartende Sitzungen), sonst 30 s.
    var taktSekunden: Int {
        guard offen, let st = status else { return 30 }
        return ["stopp", "limit", "wartet"].contains(st.stufe) ? 10 : 30
    }

    // MARK: Texte

    func t(_ schluessel: String, _ werte: [String: String] = [:]) -> String {
        var text = texte[schluessel] ?? schluessel
        for (k, v) in werte { text = text.replacingOccurrences(of: "{\(k)}", with: v) }
        return text
    }

    func texteLaden() async {
        let e = await Befehle.ausfuehren(["app-texte"])
        if let s = e.startFehler {
            if !demo { startFehler = s }
            return
        }
        if let d = e.ausgabe.data(using: .utf8), let at = try? JSONDecoder().decode(AppTexte.self, from: d) {
            texte = at.texte
            sprache = at.sprache
        }
    }

    // MARK: Status

    func aktualisieren() async {
        if let pfad = demoPfad {
            do {
                status = try JSONDecoder().decode(Status.self, from: Data(contentsOf: URL(fileURLWithPath: pfad)))
            } catch {
                meldung = t("app_fehler", ["fehler": error.localizedDescription])
            }
            return
        }
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
        if demo { return }
        let e = await Befehle.ausfuehren(argumente)
        if let s = e.startFehler { startFehler = s; return }
        if !e.ok { meldung = t("app_fehler", ["fehler": kurz(e)]) }
        await aktualisieren()
    }

    /// Wach-Modus von Hand an/aus. Den Passwortdialog zeigt waechter.py selbst; die App sieht kein Passwort.
    func wach(_ an: Bool) async {
        if demo || wachLaeuft { return }
        wachLaeuft = true
        defer { wachLaeuft = false }
        let e = await Befehle.ausfuehren(["wach", an ? "an" : "aus", "--json"], zeitlimit: Befehle.wachZeitlimit)
        if let s = e.startFehler { startFehler = s; return }
        let antwort = e.ausgabe.data(using: .utf8).flatMap { try? JSONDecoder().decode(WachAntwort.self, from: $0) }
        if antwort?.ok != true {
            let fehler = antwort?.fehler
            // Abbruch im Passwortdialog ist kein Fehler.
            if fehler != "abgebrochen" {
                meldung = t("app_wach_fehler", ["fehler": fehler.map { texte["app_wf_\($0)"] != nil ? t("app_wf_\($0)") : $0 } ?? kurz(e)])
            }
        } else {
            meldung = nil
        }
        await aktualisieren()
    }

    func schwellenSpeichern(_ s: Schwellen) async {
        if demo { return }
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
        if demo { bericht = t("app_bericht_leer"); return }
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

    // MARK: Zeit- und Zahlformate

    var gebietsschema: Locale { Locale(identifier: sprache == "en" ? "en_US" : "de_DE") }

    /// Bezugszeit: Zeitpunkt des Status (bei Demo-Daten deren "jetzt"), sonst die echte Uhr.
    var jetzt: Double { demo ? (status?.zeitpunkt ?? Date().timeIntervalSince1970) : Date().timeIntervalSince1970 }

    /// HH:mm heute, "morgen 03:00", sonst Wochentag mit Uhrzeit.
    func uhrzeit(_ ts: Double?) -> String {
        guard let ts = ts else { return "–" }
        let datum = Date(timeIntervalSince1970: ts)
        let bezug = Date(timeIntervalSince1970: jetzt)
        let kalender = Calendar.current
        let f = DateFormatter()
        f.locale = gebietsschema
        if kalender.isDate(datum, inSameDayAs: bezug) {
            f.dateFormat = "HH:mm"
        } else if let morgen = kalender.date(byAdding: .day, value: 1, to: bezug),
                  kalender.isDate(datum, inSameDayAs: morgen) {
            f.dateFormat = "HH:mm"
            return t("app_morgen", ["zeit": f.string(from: datum)])
        } else {
            f.setLocalizedDateFormatFromTemplate("EEE HH:mm")
        }
        return f.string(from: datum)
    }

    /// Kurz für die Kacheln: nur HH:mm, solange der Zeitpunkt weniger als 24 h entfernt ist.
    func kurzzeit(_ ts: Double?) -> String {
        guard let ts = ts else { return "–" }
        guard ts - jetzt < 86400 else { return uhrzeit(ts) }
        let f = DateFormatter()
        f.locale = gebietsschema
        f.dateFormat = "HH:mm"
        return f.string(from: Date(timeIntervalSince1970: ts))
    }

    func dauer(_ sekunden: Double) -> String {
        let min = max(0, Int(sekunden / 60))
        if min < 60 { return t("app_min", ["n": "\(min)"]) }
        return t("app_std", ["h": "\(min / 60)", "m": "\(min % 60)"])
    }

    /// "84 %" (de) bzw. "84%" (en).
    func prozent(_ wert: Double?) -> String {
        guard let w = wert else { return "–" }
        let n = Int(w.rounded())
        return sprache == "en" ? "\(n)%" : "\(n) %"
    }
}
