import Foundation

// Ruft waechter.py auf: immer /usr/bin/python3 mit Argumentliste, nie über eine Shell.

struct Ergebnis {
    var code: Int32
    var ausgabe: String
    var fehler: String
    var zeitueberschreitung: Bool = false
    var startFehler: String? = nil
    var ok: Bool { code == 0 && startFehler == nil && !zeitueberschreitung }
}

enum Befehle {
    static let python = "/usr/bin/python3"
    static let standardZeitlimit: TimeInterval = 20
    // größer als Passwortdialog (lw/wach.py: schließt nach 110 s, Timeout 120 s) plus sysadminctl/Amphetamine
    static let wachZeitlimit: TimeInterval = 180

    static var projektPfad: String? {
        if let env = ProcessInfo.processInfo.environment["LIMIT_WAECHTER_PROJEKT"], !env.isEmpty { return env }
        return Bundle.main.object(forInfoDictionaryKey: "LWProjekt") as? String
    }

    static var skriptPfad: String? {
        guard let p = projektPfad else { return nil }
        return (p as NSString).appendingPathComponent("waechter.py")
    }

    static var logPfad: String {
        let home: String
        if let env = ProcessInfo.processInfo.environment["LIMIT_WAECHTER_HOME"], !env.isEmpty {
            home = env
        } else {
            home = (NSHomeDirectory() as NSString).appendingPathComponent(".limit-waechter")
        }
        return (home as NSString).appendingPathComponent("log/waechter.log")
    }

    /// Führt waechter.py im Hintergrund aus (Standard-Timeout 20 s; "wach an/aus" wartet auf den Passwortdialog).
    static func ausfuehren(_ argumente: [String], zeitlimit: TimeInterval = standardZeitlimit) async -> Ergebnis {
        guard let skript = skriptPfad, FileManager.default.fileExists(atPath: skript) else {
            return Ergebnis(code: -1, ausgabe: "", fehler: "", startFehler: skriptPfad ?? "waechter.py")
        }
        return await withCheckedContinuation { (fortsetzung: CheckedContinuation<Ergebnis, Never>) in
            DispatchQueue.global(qos: .userInitiated).async {
                fortsetzung.resume(returning: synchron([skript] + argumente, zeitlimit: zeitlimit))
            }
        }
    }

    private static func synchron(_ argumente: [String], zeitlimit: TimeInterval) -> Ergebnis {
        let prozess = Process()
        prozess.executableURL = URL(fileURLWithPath: python)
        prozess.arguments = argumente
        var umgebung = ProcessInfo.processInfo.environment
        umgebung["PYTHONIOENCODING"] = "utf-8"
        prozess.environment = umgebung
        let aus = Pipe(), err = Pipe()
        prozess.standardOutput = aus
        prozess.standardError = err
        prozess.standardInput = FileHandle.nullDevice
        do { try prozess.run() } catch {
            return Ergebnis(code: -1, ausgabe: "", fehler: "", startFehler: python)
        }
        // Beide Pipes parallel leeren, damit nichts blockiert. Puffer mit Lock gegen Datenrennen.
        let puffer = Puffer()
        let gruppe = DispatchGroup()
        gruppe.enter()
        DispatchQueue.global().async {
            puffer.setzen(aus: aus.fileHandleForReading.readDataToEndOfFile()); gruppe.leave()
        }
        gruppe.enter()
        DispatchQueue.global().async {
            puffer.setzen(err: err.fileHandleForReading.readDataToEndOfFile()); gruppe.leave()
        }
        if gruppe.wait(timeout: .now() + zeitlimit) == .timedOut {
            prozess.terminate()
            if gruppe.wait(timeout: .now() + 2) == .timedOut {
                if prozess.isRunning { kill(prozess.processIdentifier, SIGKILL) }
                // Enkelprozesse können die Pipes offen halten: Leseenden schließen, Ausgabe verwerfen.
                if gruppe.wait(timeout: .now() + 1) == .timedOut {
                    try? aus.fileHandleForReading.close()
                    try? err.fileHandleForReading.close()
                }
            }
            // Nach SIGKILL kehrt waitUntilExit sicher zurück; Wartezeit trotzdem begrenzen.
            let ende = Date().addingTimeInterval(2)
            while prozess.isRunning && Date() < ende { usleep(50_000) }
            return Ergebnis(code: -1, ausgabe: "", fehler: "", zeitueberschreitung: true)
        }
        prozess.waitUntilExit()
        let (ausDaten, errDaten) = puffer.lesen()
        return Ergebnis(code: prozess.terminationStatus,
                        ausgabe: String(decoding: ausDaten, as: UTF8.self),
                        fehler: String(decoding: errDaten, as: UTF8.self))
    }
}

/// Threadsicherer Puffer für die Ausgabe der Leser-Threads.
private final class Puffer: @unchecked Sendable {
    private let lock = NSLock()
    private var aus = Data(), err = Data()
    func setzen(aus d: Data) { lock.lock(); aus = d; lock.unlock() }
    func setzen(err d: Data) { lock.lock(); err = d; lock.unlock() }
    func lesen() -> (Data, Data) { lock.lock(); defer { lock.unlock() }; return (aus, err) }
}
