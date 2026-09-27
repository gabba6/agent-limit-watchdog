import AppKit
import SwiftUI

// Farben je Phase/Stufe/Lage und das selbst gezeichnete Menüleistensymbol.

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

    /// Balkenfarbe nach Schwelle: grün < Warnung ≤ gelb < Stopp ≤ orange < 100 ≤ rot.
    static func fuellung(_ pct: Double, warnung: Int, stopp: Int) -> Color {
        if pct >= 100 { return .red }
        if pct >= Double(stopp) { return .orange }
        if pct >= Double(warnung) { return .yellow }
        return .green
    }

    /// Kontextstufe: ok = grün, warnung = orange, kritisch = rot.
    static func kontext(_ stufe: String) -> Color {
        switch stufe {
        case "kritisch": return .red
        case "warnung": return .orange
        default: return .green
        }
    }

    /// Gesamtstufe → Farbe und SF Symbol für das Statusbanner.
    static func stufe(_ s: String) -> (farbe: Color, symbol: String) {
        switch s {
        case "wartet": return (.blue, "clock.fill")
        case "warnung": return (.yellow, "exclamationmark.triangle.fill")
        case "stopp": return (.orange, "hand.raised.fill")
        case "limit": return (.red, "xmark.octagon.fill")
        case "pause": return (.gray, "pause.circle.fill")
        case "stoerung": return (.red, "bolt.horizontal.circle.fill")
        default: return (.green, "checkmark.circle.fill")
        }
    }

    /// Lage-Farbe aus status --json ("gruen", "blau", …).
    static func lage(_ name: String) -> Color {
        switch name {
        case "gruen": return .green
        case "gelb": return .yellow
        case "blau": return .blue
        case "orange": return .orange
        case "rot": return .red
        default: return .gray
        }
    }

    static func anbieter(_ a: String) -> Color { a == "codex" ? .teal : .orange }
}

enum MenueSymbol {
    /// Menüleistensymbol aus dem Status: Gesamtstufe bevorzugt, sonst höchste Phase.
    static func bild(status st: Status?, startFehler: Bool) -> NSImage {
        let h = st?.hoechsterFuenf ?? (pct: 0, phase: "ok")
        var phase = h.phase
        if let s = st?.gesamt?.stufe, ["ok", "warnung", "stopp", "limit"].contains(s) { phase = s }
        let stufe = st?.stufe
        return bild(pct: h.pct, phase: phase, nacht: st?.nacht != nil,
                    pause: stufe == "pause" || st?.pausiert == true,
                    stoerung: startFehler || stufe == "stoerung" || st?.launchagent == false)
    }

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
