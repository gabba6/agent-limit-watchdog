import Foundation

// Datenmodelle für "waechter.py status --json". Alles optional und tolerant,
// damit ältere oder unvollständige Ausgaben die App nicht zum Absturz bringen.

extension KeyedDecodingContainer {
    /// Liest einen Wert, falls vorhanden und vom richtigen Typ; sonst nil (nie ein Fehler).
    func weich<T: Decodable>(_ schluessel: Key) -> T? {
        (try? decodeIfPresent(T.self, forKey: schluessel)) ?? nil
    }

    /// Liste, in der kaputte Einträge einzeln verworfen werden.
    func weicheListe<T: Decodable>(_ schluessel: Key) -> [T]? {
        let roh: [Nachsichtig<T>]? = weich(schluessel)
        return roh?.compactMap { $0.wert }
    }
}

/// v1.4: Wochenlimit je Modell (nur Claude, offizielle Quelle).
struct WocheModell: Decodable, Hashable {
    var name: String?
    var pct: Double?
    var reset: Double?
}

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
    var quelle: String?
    var quelle_text: String?
    var woche_modell: [WocheModell]?

    enum CodingKeys: String, CodingKey {
        case anbieter, phase, art, pct, reset, pct5, reset5, pctw, resetw, reserve_erreicht, stand, alter,
             veraltet, hat_daten, quelle, quelle_text, woche_modell
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        anbieter = c.weich(.anbieter)
        phase = c.weich(.phase)
        art = c.weich(.art)
        pct = c.weich(.pct)
        reset = c.weich(.reset)
        pct5 = c.weich(.pct5)
        reset5 = c.weich(.reset5)
        pctw = c.weich(.pctw)
        resetw = c.weich(.resetw)
        reserve_erreicht = c.weich(.reserve_erreicht)
        stand = c.weich(.stand)
        alter = c.weich(.alter)
        veraltet = c.weich(.veraltet)
        hat_daten = c.weich(.hat_daten)
        quelle = c.weich(.quelle)
        quelle_text = c.weich(.quelle_text)
        woche_modell = c.weicheListe(.woche_modell)
    }

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

/// v1.4: letzte belegte Aktivität einer Sitzung (Transcript bzw. Codex-Protokoll).
struct Aktivitaet: Decodable {
    var letzte: Double?
    var quelle: String?
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
    // v1.4
    var lage: String?
    var lage_text: String?
    var lage_farbe: String?
    var aktivitaet: Aktivitaet?

    enum CodingKeys: String, CodingKey {
        case anbieter, id, cwd, projekt, status, status_text, zuletzt, wartet, automatisch, fortsetzen_ab,
             nacht_bis, ort, ort_text, faehigkeiten_text, lage, lage_text, lage_farbe, aktivitaet
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        anbieter = try c.decode(String.self, forKey: .anbieter)
        id = try c.decode(String.self, forKey: .id)
        cwd = c.weich(.cwd)
        projekt = c.weich(.projekt)
        status = c.weich(.status)
        status_text = c.weich(.status_text)
        zuletzt = c.weich(.zuletzt)
        wartet = c.weich(.wartet)
        automatisch = c.weich(.automatisch)
        fortsetzen_ab = c.weich(.fortsetzen_ab)
        nacht_bis = c.weich(.nacht_bis)
        ort = c.weich(.ort)
        ort_text = c.weich(.ort_text)
        faehigkeiten_text = c.weich(.faehigkeiten_text)
        lage = c.weich(.lage)
        lage_text = c.weich(.lage_text)
        lage_farbe = c.weich(.lage_farbe)
        aktivitaet = c.weich(.aktivitaet)
    }

    var imNachtmodus: Bool { nacht_bis != nil }
    var anzeigeName: String {
        if let p = projekt, !p.isEmpty { return p }
        if let c = cwd, !c.isEmpty { return (c as NSString).lastPathComponent }
        return String(id.prefix(8))
    }

    /// Lage aus status --json; für ältere Ausgaben aus dem Status abgeleitet.
    var lageName: String {
        if let l = lage, !l.isEmpty { return l }
        switch status ?? "" {
        case "wartet_auf_weiter": return "weiter_noetig"
        case "blockiert", "aufgegeben", "reserve": return "blockiert"
        case "sicherung": return "sichert"
        case "beendet": return "beendet"
        default: return wartet == true ? "wartet" : "ruht"
        }
    }

    var lageFarbe: String {
        if let f = lage_farbe, !f.isEmpty { return f }
        switch lageName {
        case "arbeitet": return "gruen"
        case "wartet", "pruefung": return "blau"
        case "weiter_noetig": return "orange"
        case "blockiert": return "rot"
        case "sichert": return "gelb"
        default: return "grau"
        }
    }

    /// Sortierung in der Liste: Handlungsbedarf zuerst.
    var lageRang: Int {
        ["blockiert": 0, "weiter_noetig": 1, "wartet": 2, "pruefung": 3, "sichert": 4, "arbeitet": 5, "ruht": 6][lageName] ?? 7
    }
}

/// v1.4: Gesamtzustand in einem Satz (vom Wächter formuliert).
struct Gesamt: Decodable {
    var stufe: String?
    var text: String?
    var detail: String?
}

/// v1.4: Zustand der offiziellen Nutzungsanzeige je Anbieter.
struct OffiziellEintrag: Decodable {
    var zustand: String?
    var fehler: String?
    var stand: Double?
}

/// v1.4: Wach-Modus (Mac wach halten).
struct WachInfo: Decodable {
    var an: Bool?
    var art: String?
    var modus: String?
    var bis: Double?
    var sperre: String?
    var zugeklappt_ok: Bool?
    var netzteil: Bool?
    var amphetamine: String?
    var text: String?

    var modusName: String { modus ?? ((an ?? false) ? "automatisch" : "aus") }
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
    // v1.4
    var gesamt: Gesamt?
    var offiziell: [String: OffiziellEintrag]?
    var wach: WachInfo?

    enum CodingKeys: String, CodingKey {
        case version, jetzt, sprache, phasen, pausiert, pause_bis, letzter_tick, launchagent, orca_ok,
             nacht, nur_mit_nachtmodus, bericht_uhrzeit, schwellen, sitzungen,
             orca_vorhanden, nur_orca, statusline, gesamt, offiziell, wach
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = c.weich(.version)
        jetzt = c.weich(.jetzt)
        sprache = c.weich(.sprache)
        // Verlustarm: ein kaputter Eintrag lässt nicht den ganzen Status scheitern.
        phasen = try c.decodeIfPresent([String: Nachsichtig<Phase>].self, forKey: .phasen)?
            .compactMapValues { $0.wert }
        pausiert = c.weich(.pausiert)
        pause_bis = c.weich(.pause_bis)
        letzter_tick = c.weich(.letzter_tick)
        launchagent = c.weich(.launchagent)
        orca_ok = c.weich(.orca_ok)
        nacht = c.weich(.nacht)
        nur_mit_nachtmodus = c.weich(.nur_mit_nachtmodus)
        bericht_uhrzeit = c.weich(.bericht_uhrzeit)
        schwellen = c.weich(.schwellen)
        sitzungen = c.weicheListe(.sitzungen)
        orca_vorhanden = c.weich(.orca_vorhanden)
        nur_orca = c.weich(.nur_orca)
        statusline = (c.weich(.statusline) as Nachsichtig<StatuslineInfo>?)?.wert
        gesamt = (c.weich(.gesamt) as Nachsichtig<Gesamt>?)?.wert
        offiziell = (c.weich(.offiziell) as [String: Nachsichtig<OffiziellEintrag>]?)?.compactMapValues { $0.wert }
        wach = (c.weich(.wach) as Nachsichtig<WachInfo>?)?.wert
    }

    func phase(_ anbieter: String) -> Phase? { phasen?[anbieter] }

    var zeitpunkt: Double { jetzt ?? Date().timeIntervalSince1970 }

    /// Aktuelle Sitzungen: nicht beendet und in den letzten 2 Tagen aktiv, Handlungsbedarf zuerst.
    var aktuelleSitzungen: [Sitzung] {
        let grenze = zeitpunkt - 2 * 86400
        return (sitzungen ?? [])
            .filter { ($0.status ?? "") != "beendet" && $0.lageName != "beendet" && ($0.zuletzt ?? 0) >= grenze }
            .enumerated()
            .sorted { ($0.element.lageRang, $0.offset) < ($1.element.lageRang, $1.offset) }
            .map { $0.element }
    }

    /// Strengste Phase über Claude/Codex.
    var strengstePhase: (anbieter: String, phase: Phase)? {
        let rang = ["ok": 0, "warnung": 1, "stopp": 2, "limit": 3]
        var best: (String, Phase)?
        for a in ["claude", "codex"] {
            guard let p = phase(a) else { continue }
            if best == nil || (rang[p.phaseName] ?? 0) > (rang[best!.1.phaseName] ?? 0) { best = (a, p) }
        }
        return best.map { (anbieter: $0.0, phase: $0.1) }
    }

    /// Gesamtstufe: vom Wächter (v1.4), sonst aus den Einzelwerten abgeleitet.
    var stufe: String {
        if let s = gesamt?.stufe, !s.isEmpty { return s }
        if launchagent == false { return "stoerung" }
        if pausiert == true { return "pause" }
        if let p = strengstePhase?.phase.phaseName, p != "ok" { return p }
        if aktuelleSitzungen.contains(where: { ["wartet", "weiter_noetig"].contains($0.lageName) }) { return "wartet" }
        return "ok"
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

/// v1.4: Antwort von "wach an|aus --json".
struct WachAntwort: Decodable {
    var ok: Bool?
    var fehler: String?
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
