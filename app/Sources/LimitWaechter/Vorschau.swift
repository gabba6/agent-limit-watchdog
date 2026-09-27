import AppKit
import SwiftUI

// Vorschau für Screenshots (README): zeigt den Popover-Inhalt in einem normalen Fenster, ohne Menüleiste.
// Aufruf: LimitWaechter --vorschau [--demo <status.json>] [--hell|--dunkel] [--bild <datei.png>]
//   --demo   Status aus der Datei statt aus waechter.py; alle Befehle sind wirkungslos.
//   --einstellungen  Einstellungen aufgeklappt.
//   --bild   rendert das Fenster nach dem Laden als PNG (ohne Bildschirmaufnahme-Recht) und beendet sich.
// Ohne --bild wird die Fensternummer ausgegeben (für screencapture -o -l <nummer>).

@MainActor
enum Vorschau {
    static var fenster: NSWindow?
    /// --einstellungen: Einstellungen aufgeklappt zeigen (Screenshot der Hinweise).
    static var einstellungenOffen = false

    static func starten(demo: String?, bild: String?, erscheinung: String?) -> Never {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        if erscheinung == "dunkel" { app.appearance = NSAppearance(named: .darkAqua) }
        if erscheinung == "hell" { app.appearance = NSAppearance(named: .aqua) }
        let speicher = Speicher(demo: demo)
        let inhalt = Hauptansicht()
            .environmentObject(speicher)
            .background(Color(nsColor: .windowBackgroundColor))
        let host = NSHostingView(rootView: inhalt)
        host.safeAreaRegions = []  // keinen Platz für die (unsichtbare) Titelleiste reservieren
        let f = NSWindow(contentRect: NSRect(x: 80, y: 80, width: Mass.breite, height: 600),
                         styleMask: [.titled, .fullSizeContentView], backing: .buffered, defer: false)
        f.titlebarAppearsTransparent = true
        f.titleVisibility = .hidden
        f.contentView = host
        f.orderFrontRegardless()
        fenster = f
        // Warten, bis Texte und Status geladen sind, dann auf die passende Größe bringen.
        DispatchQueue.main.asyncAfter(deadline: .now() + 4) {
            f.setContentSize(host.fittingSize)
            // Aktiv, damit Schalter nicht im grauen Inaktiv-Stil erscheinen.
            app.activate(ignoringOtherApps: true)
            f.makeKeyAndOrderFront(nil)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                if let ziel = bild {
                    exit(speichern(host, ziel) ? 0 : 1)
                }
                print(f.windowNumber)
                fflush(stdout)
            }
        }
        app.run()
        exit(0)
    }

    /// Rendert die Ansicht als PNG (doppelte Auflösung, wenn der Bildschirm es hat).
    static func speichern(_ ansicht: NSView, _ ziel: String) -> Bool {
        let rahmen = ansicht.bounds
        guard let rep = ansicht.bitmapImageRepForCachingDisplay(in: rahmen) else { return false }
        ansicht.cacheDisplay(in: rahmen, to: rep)
        guard let daten = rep.representation(using: .png, properties: [:]) else { return false }
        do {
            try daten.write(to: URL(fileURLWithPath: ziel))
            print(ziel)
            fflush(stdout)
            return true
        } catch {
            FileHandle.standardError.write("vorschau: \(error)\n".data(using: .utf8)!)
            return false
        }
    }
}
