import AppKit
import SwiftUI

// Vorschau für Screenshots (README): zeigt den Popover-Inhalt in einem normalen Fenster, ohne Menüleiste.
// Aufruf: LimitWaechter --vorschau  → gibt nach dem Laden die Fensternummer aus (für screencapture -l).
// Daten kommen wie sonst aus waechter.py (LIMIT_WAECHTER_PROJEKT kann auf eine Demo zeigen).

@MainActor
enum Vorschau {
    static var fenster: NSWindow?

    static func starten() -> Never {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let speicher = Speicher()
        let inhalt = Hauptansicht()
            .environmentObject(speicher)
            .background(Color(nsColor: .windowBackgroundColor))
        let host = NSHostingView(rootView: inhalt)
        let f = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 340, height: 600),
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
                print(f.windowNumber)
                fflush(stdout)
            }
        }
        app.run()
        exit(0)
    }
}
