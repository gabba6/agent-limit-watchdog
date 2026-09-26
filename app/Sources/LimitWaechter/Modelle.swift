import Foundation

// Datenmodelle für "waechter.py status --json". Alles optional und tolerant,
// damit ältere oder unvollständige Ausgaben die App nicht zum Absturz bringen.

struct Phase: Decodable {
    var anbieter: String?
    var phase: String?
    var art: String?
    var pct: Double?
    var reset: Double?
    var pct5: Double?
    var reset5: Double?
    var pctw: Double?
    var resetw: Double?
    var reserve_erreicht: Bool?
    var stand: Double?
    var alter: Double?
    var veraltet: Bool?
    var hat_daten: Bool?

    var phaseName: String { phase ?? "ok" }
    var hatDaten: Bool { hat_daten ?? (pct5 != nil) }
}

struct Schwellen: Codable, Hashable {
    var warnung: Int = 80
    var stopp: Int = 92
    var woche_warnung: Int = 80
    var woche_stopp: Int = 92
    var wochen_reserve: Int = 20
}

struct Sitzung: Decodable, Identifiable {
    var anbieter: String
    var id: String
    var cwd: String?
    var projekt: String?
    var status: String?
    var status_text: String?
    var zuletzt: Double?
    var wartet: Bool?
    var automatisch: Bool?
    var fortsetzen_ab: Double?
    var nacht_bis: Double?
    var ort: String?
    var ort_text: String?
    var faehigkeiten_text: String?

    var imNachtmodus: Bool { nacht_bis != nil }
    var anzeigeName: String {
        if let p = projekt, !p.isEmpty { return p }
        if let c = cwd, !c.isEmpty { return (c as NSString).lastPathComponent }
        return String(id.prefix(8))
    }
}

struct Status: Decodable {
    var version: String?
    var jetzt: Double?
    var sprache: String?
    var phasen: [String: Phase]?
    var pausiert: Bool?
    var pause_bis: Double?
    var letzter_tick: Double?
    var launchagent: Bool?
    var orca_ok: Bool?
    var nacht: Double?
    var nur_mit_nachtmodus: Bool?
    var bericht_uhrzeit: String?
    var schwellen: Schwellen?
    var sitzungen: [Sitzung]?
    var orca_vorhanden: Bool?
    var nur_orca: Bool?
    var statusline: StatuslineInfo?

    enum CodingKeys: String, CodingKey {
        case version, jetzt, sprache, phasen, pausiert, pause_bis, letzter_tick, launchagent, orca_ok,
             nacht, nur_mit_nachtmodus, bericht_uhrzeit, schwellen, sitzungen,
             orca_vorhanden, nur_orca, statusline
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try? c.decodeIfPresent(String.self, forKey: .version)
        jetzt = try? c.decodeIfPresent(Double.self, forKey: .jetzt)
        sprache = try? c.decodeIfPresent(String.self, forKey: .sprache)
        // Verlustarm: ein kaputter Eintrag lässt nicht den ganzen Status scheitern.
        phasen = try c.decodeIfPresent([String: Nachsichtig<Phase>].self, forKey: .phasen)?
            .compactMapValues { $0.wert }
        pausiert = try? c.decodeIfPresent(Bool.self, forKey: .pausiert)
        pause_bis = try? c.decodeIfPresent(Double.self, forKey: .pause_bis)
        letzter_tick = try? c.decodeIfPresent(Double.self, forKey: .letzter_tick)
        launchagent = try? c.decodeIfPresent(Bool.self, forKey: .launchagent)
        orca_ok = try? c.decodeIfPresent(Bool.self, forKey: .orca_ok)
        nacht = try? c.decodeIfPresent(Double.self, forKey: .nacht)
        nur_mit_nachtmodus = try? c.decodeIfPresent(Bool.self, forKey: .nur_mit_nachtmodus)
        bericht_uhrzeit = try? c.decodeIfPresent(String.self, forKey: .bericht_uhrzeit)
        schwellen = try? c.decodeIfPresent(Schwellen.self, forKey: .schwellen)
        sitzungen = (try? c.decodeIfPresent([Nachsichtig<Sitzung>].self, forKey: .sitzungen))??
            .compactMap { $0.wert }
        orca_vorhanden = try? c.decodeIfPresent(Bool.self, forKey: .orca_vorhanden)
        nur_orca = try? c.decodeIfPresent(Bool.self, forKey: .nur_orca)
        statusline = (try? c.decodeIfPresent(Nachsichtig<StatuslineInfo>.self, forKey: .statusline))??.wert
    }

    func phase(_ anbieter: String) -> Phase? { phasen?[anbieter] }

    var zeitpunkt: Double { jetzt ?? Date().timeIntervalSince1970 }

    /// Aktuelle Sitzungen: nicht beendet und in den letzten 2 Tagen aktiv.
    var aktuelleSitzungen: [Sitzung] {
        let grenze = zeitpunkt - 2 * 86400
        return (sitzungen ?? []).filter { ($0.status ?? "") != "beendet" && ($0.zuletzt ?? 0) >= grenze }
    }

    /// Höchster 5h-Wert über Claude/Codex (für das Menüleistensymbol).
    var hoechsterFuenf: (pct: Double, phase: String) {
        var best: (Double, String) = (0, "ok")
        let rang = ["ok": 0, "warnung": 1, "stopp": 2, "limit": 3]
        for a in ["claude", "codex"] {
            guard let p = phase(a) else { continue }
            let wert = p.pct5 ?? 0
            if wert > best.0 { best.0 = wert }
            if (rang[p.phaseName] ?? 0) > (rang[best.1] ?? 0) { best.1 = p.phaseName }
        }
        return best
    }
}

/// v1.3: Zustand der Statusline-Kette (Claude-Füllstand ohne Orca).
struct StatuslineInfo: Decodable {
    var zustand: String?
    var stand: Double?
}

struct SchwellenAntwort: Decodable {
    var ok: Bool
    var schwellen: Schwellen?
    var fehler: [String]?
}

struct AppTexte: Decodable {
    var sprache: String
    var texte: [String: String]
}

/// Dekodiert einen Wert oder schluckt den Fehler (nil).
struct Nachsichtig<T: Decodable>: Decodable {
    var wert: T?
    init(from decoder: Decoder) throws { wert = try? T(from: decoder) }
}
