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
        print("nachtmodus: \(st.nacht != nil ? "an" : "aus")  pausiert: \(st.pausiert == true)")
        if let sw = st.schwellen {
            print("schwellen: \(sw.warnung)/\(sw.stopp) woche \(sw.woche_warnung)/\(sw.woche_stopp) reserve \(sw.wochen_reserve)")
        }
        exit(0)
    } catch {
        FileHandle.standardError.write("selbsttest: \(error)\n".data(using: .utf8)!)
        exit(1)
    }
}

struct LimitWaechterApp: App {
    @StateObject private var speicher = Speicher()

    var body: some Scene {
        MenuBarExtra {
            Hauptansicht().environmentObject(speicher)
        } label: {
            let st = speicher.status
            let h = st?.hoechsterFuenf ?? (pct: 0, phase: "ok")
            Image(nsImage: MenueSymbol.bild(pct: h.pct, phase: h.phase,
                                            nacht: st?.nacht != nil, pause: st?.pausiert == true,
                                            stoerung: speicher.startFehler != nil || st?.launchagent == false))
        }
        .menuBarExtraStyle(.window)

        Window(speicher.t("app_bericht"), id: "bericht") {
            BerichtFenster().environmentObject(speicher)
        }
        .windowResizability(.contentSize)
    }
}

LimitWaechterApp.main()
