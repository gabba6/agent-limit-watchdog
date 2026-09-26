import AppKit
import SwiftUI

// Farben je Phase und das selbst gezeichnete Menüleistensymbol.

enum Farben {
    static func phase(_ p: String) -> Color {
        switch p {
        case "warnung": return .yellow
        case "stopp": return .orange
        case "limit": return .red
        default: return .green
        }
    }

    static func nsPhase(_ p: String) -> NSColor {
        switch p {
        case "warnung": return .systemYellow
        case "stopp": return .systemOrange
        case "limit": return .systemRed
        default: return .labelColor
        }
    }
}

enum MenueSymbol {
    /// Ring mit Füllung = höchster 5h-Wert; Mond bei Nachtmodus, Striche bei Pause.
    /// Störung (Wächter aus, Python/waechter.py fehlt): gestrichelter Ring.
    static func bild(pct: Double, phase: String, nacht: Bool, pause: Bool, stoerung: Bool = false) -> NSImage {
        let groesse = NSSize(width: 18, height: 18)
        let vorlage = phase == "ok"
        let farbe: NSColor = vorlage ? .black : Farben.nsPhase(phase)
        let bild = NSImage(size: groesse, flipped: false) { rect in
            let mitte = NSPoint(x: rect.midX, y: rect.midY)
            let radius: CGFloat = 6.5
            let hinten = NSBezierPath()
            hinten.appendArc(withCenter: mitte, radius: radius, startAngle: 0, endAngle: 360)
            hinten.lineWidth = 2.2
            if stoerung { hinten.setLineDash([2.0, 2.0], count: 2, phase: 0) }
            farbe.withAlphaComponent(stoerung ? 0.9 : 0.3).setStroke()
            hinten.stroke()
            let anteil = CGFloat(min(max(pct, 0), 100) / 100)
            if anteil > 0 {
                let bogen = NSBezierPath()
                bogen.appendArc(withCenter: mitte, radius: radius, startAngle: 90,
                                endAngle: 90 - 360 * anteil, clockwise: true)
                bogen.lineWidth = 2.2
                bogen.lineCapStyle = .round
                farbe.setStroke()
                bogen.stroke()
            }
            farbe.setFill()
            if pause {
                NSBezierPath(rect: NSRect(x: mitte.x - 2.3, y: mitte.y - 2.5, width: 1.6, height: 5)).fill()
                NSBezierPath(rect: NSRect(x: mitte.x + 0.7, y: mitte.y - 2.5, width: 1.6, height: 5)).fill()
            }
            if nacht {
                // Kleiner Mond oben rechts (Sichel über ausgeschnittenen Kreis).
                let m = NSRect(x: rect.maxX - 7, y: rect.maxY - 7, width: 7, height: 7)
                NSGraphicsContext.current?.saveGraphicsState()
                let sichel = NSBezierPath(ovalIn: m)
                sichel.appendOval(in: m.offsetBy(dx: 2.2, dy: 1.6))
                sichel.windingRule = .evenOdd
                sichel.addClip()
                NSBezierPath(ovalIn: m).fill()
                NSGraphicsContext.current?.restoreGraphicsState()
            }
            return true
        }
        bild.isTemplate = vorlage
        return bild
    }
}
