import AppKit
import Foundation
import SwiftUI

// Einstieg: --version und --selbsttest laufen ohne GUI.

let argumente = CommandLine.arguments

func versionText() -> String {
    (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? "dev"
}

if argumente.contains("--version") {
    print("LimitWaechter \(versionText())")
    exit(0)
}

if let i = argumente.firstIndex(of: "--selbsttest") {
    guard i + 1 < argumente.count else {
        FileHandle.standardError.write("usage: LimitWaechter --selbsttest <status.json>\n".data(using: .utf8)!)
        exit(1)
    }
    do {
        let daten = try Data(contentsOf: URL(fileURLWithPath: argumente[i + 1]))
        let st = try JSONDecoder().decode(Status.self, from: daten)
        guard st.phasen != nil else { throw NSError(domain: "LimitWaechter", code: 1) }
        print("version: \(st.version ?? "?")  sprache: \(st.sprache ?? "?")")
        for a in ["claude", "codex"] {
            let p = st.phase(a)
            let p5 = p?.pct5.map { "\(Int($0.rounded()))%" } ?? "-"
            let pw = p?.pctw.map { "\(Int($0.rounded()))%" } ?? "-"
            print("\(a): phase=\(p?.phaseName ?? "-") 5h=\(p5) woche=\(pw)")
        }
        print("sitzungen: \(st.sitzungen?.count ?? 0) (aktuell \(st.aktuelleSitzungen.count))")
        let orte = (st.sitzungen ?? []).map { $0.ort ?? "-" }.joined(separator: ",")
        print("orca: \(st.orca_vorhanden.map { $0 ? "ja" : "nein" } ?? "-")  statusline: \(st.statusline?.zustand ?? "-")  orte: \(orte)")
        print("nachtmodus: \(st.nacht != nil ? "an" : "aus")  pausiert: \(st.pausiert == true)")
        // v1.4: Gesamtzustand, Datenquellen, Wach-Modus, Lagen der Sitzungen
        print("gesamt=\(st.stufe)")
        print("quelle claude=\(st.phase("claude")?.quelle ?? "-") codex=\(st.phase("codex")?.quelle ?? "-")")
        print("wach=\(st.wach?.art ?? "-")/\(st.wach?.modus ?? "-")")
        print("lagen=\(st.aktuelleSitzungen.map { $0.lageName }.joined(separator: ","))")
        if let sw = st.schwellen {
            print("schwellen: \(sw.warnung)/\(sw.stopp) woche \(sw.woche_warnung)/\(sw.woche_stopp) reserve \(sw.wochen_reserve)")
        }
        exit(0)
    } catch {
        FileHandle.standardError.write("selbsttest: \(error)\n".data(using: .utf8)!)
        exit(1)
    }
}

func wertNach(_ option: String) -> String? {
    guard let i = argumente.firstIndex(of: option), i + 1 < argumente.count else { return nil }
    return argumente[i + 1]
}

if argumente.contains("--vorschau") {
    let erscheinung = argumente.contains("--dunkel") ? "dunkel" : (argumente.contains("--hell") ? "hell" : nil)
    let demo = wertNach("--demo").map { URL(fileURLWithPath: $0).standardizedFileURL.path }
    let bild = wertNach("--bild").map { URL(fileURLWithPath: $0).standardizedFileURL.path }
    MainActor.assumeIsolated {
        Vorschau.einstellungenOffen = argumente.contains("--einstellungen")
        Vorschau.starten(demo: demo, bild: bild, erscheinung: erscheinung)
    }
}

struct LimitWaechterApp: App {
    @StateObject private var speicher = Speicher()

    var body: some Scene {
        MenuBarExtra {
            Hauptansicht().environmentObject(speicher)
        } label: {
            Image(nsImage: MenueSymbol.bild(status: speicher.status, startFehler: speicher.startFehler != nil))
        }
        .menuBarExtraStyle(.window)

        Window(speicher.t("app_bericht"), id: "bericht") {
            BerichtFenster().environmentObject(speicher)
        }
        .windowResizability(.contentSize)
    }
}

LimitWaechterApp.main()
