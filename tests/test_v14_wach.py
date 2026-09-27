"""v1.4 C: Wach-Modus (wach an|aus|status, automatisches Wachhalten mit Amphetamine/caffeinate).

Kein Test ruft sysadminctl, osascript, pgrep, pmset oder Amphetamine wirklich auf: alle Systemaufrufe gehen an
eine Attrappe (wach.RUNNER), die die Argumentlisten protokolliert."""

import json
import os
import stat
import subprocess
import time
import unittest.mock as mock

from hilfe import TempHome
from test_app_cli import CliBasis

from lw import cli, konfig, melden, nacht, register, tick, util, wach
from lw.attrappe import OrcaAttrappe
from lw.kontext import Kontext

PASSWORT = "Geheim-PW-4711"


def zeit(tag, stunde, minute=0):
    return time.mktime((2026, 9, tag, stunde, minute, 0, 0, 0, -1))


class SystemAttrappe:
    """Spielt sysadminctl, osascript (Dialog, Banner, Amphetamine) und pgrep nach."""

    def __init__(self, sperre="300", dialog=PASSWORT, amph_laeuft=True, lage="inaktiv", verweigert=False,
                 sysadmin_ok=True):
        self.sperre = sperre
        self.dialog = dialog
        self.amph_laeuft = amph_laeuft
        self.lage = lage
        self.verweigert = verweigert
        self.sysadmin_ok = sysadmin_ok
        self.aufrufe = []

    def __call__(self, args, **kw):
        self.aufrufe.append(list(args))
        text = " ".join(args)

        def erg(rc=0, out="", err=""):
            return subprocess.CompletedProcess(args, rc, out, err)

        if args[0].endswith("sysadminctl"):
            if args[2] == "status":
                if self.sperre == "off":
                    return erg(err="2026-09-27 15:26:51.278 sysadminctl[1:2] screenLock is off")
                if self.sperre == "immediate":
                    return erg(err="2026-09-27 15:26:51.278 sysadminctl[1:2] screenLock delay is immediate")
                return erg(err=f"2026-09-27 sysadminctl[1:2] screenLock delay is {self.sperre} seconds")
            if not self.sysadmin_ok:
                return erg(1, err="Authentication failed")
            self.sperre = args[2]
            return erg()
        if args[0].endswith("pgrep"):
            return erg(0 if self.amph_laeuft else 1, "123\n" if self.amph_laeuft else "")
        if args[0].endswith("osascript"):
            if "display dialog" in text:
                return erg(1, err="User canceled. (-128)") if self.dialog is None else erg(out=self.dialog + "\n")
            if "display notification" in text:
                return erg()
            if 'application "Amphetamine"' in text:
                if self.verweigert:
                    return erg(1, err="execution error: Not authorized to send Apple events to Amphetamine. (-1743)")
                if "start new session" in text:
                    zeile = [a for a in args if "start new session" in a][0]
                    minuten = int(zeile.split("duration:")[1].split(",")[0])
                    self.lage = f"aktiv {minuten * 60}" if minuten else "aktiv 0"
                    return erg()
                if "end session" in text:
                    self.lage = "inaktiv"
                    return erg()
                if "session is active" in text:
                    return erg(out=self.lage + "\n")
                return erg()
        raise AssertionError(f"unerwarteter Systemaufruf: {args}")

    def mit(self, wort):
        return [a for a in self.aufrufe if any(wort in x for x in a)]

    def amph(self, wort):
        return [a for a in self.aufrufe if a[0].endswith("osascript") and 'tell application "Amphetamine"' in a
                and any(wort in x for x in a)]


class WachBasis(TempHome):
    def setUp(self):
        super().setUp()
        self.sys = SystemAttrappe()
        self.amph_app = os.path.join(self.home, "Amphetamine.app")
        os.makedirs(self.amph_app)
        self._patches = [mock.patch.object(wach, "RUNNER", self.sys),
                         mock.patch.object(wach, "AMPH_PFADE", (self.amph_app,))]
        for p in self._patches:
            p.start()
        self.k["wach"]["caffeinate"] = False
        self.melder = melden.Melder(self.k, dry_run=True)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        super().tearDown()

    def ohne_amphetamine(self):
        os.rmdir(self.amph_app)

    def probe_ok(self):
        d = util.lies_json(util.pfad(*wach.DATEI), {}) or {}
        d["probe"] = {"ergebnis": "ok", "zeit": self.now - 3600}
        util.schreib_json(util.pfad(*wach.DATEI), d)

    def ctx(self, dry_run=False):
        return Kontext(self.k, OrcaAttrappe(), self.melder, self.now, dry_run=dry_run, claude_agenten=[])

    def halten(self, dry_run=False, pausiert=False, mac=None):
        c = self.ctx(dry_run)
        tick._wach_halten(c, tick._Mac(mac or {"netzteil": True, "wach_bei_deckel_zu": False}), pausiert)
        return c

    def alle_dateien(self):
        inhalt = ""
        for ordner, _, dateien in os.walk(self.home):
            for d in dateien:
                try:
                    with open(os.path.join(ordner, d), encoding="utf-8", errors="replace") as f:
                        inhalt += f.read()
                except OSError:
                    pass
        return inhalt


# ---------------------------------------------------------------------------------------------- 1
class SperreParserTest(TempHome):
    def test_parser(self):
        self.assertEqual(wach.parse_sperre("2026 sysadminctl[1:2] screenLock delay is 300 seconds"), "300")
        self.assertEqual(wach.parse_sperre("x screenLock delay is immediate"), "immediate")
        self.assertEqual(wach.parse_sperre("x screenLock is immediate"), "immediate")
        self.assertEqual(wach.parse_sperre("x screenLock is off"), "off")
        self.assertIsNone(wach.parse_sperre("Unsinn"))
        self.assertIsNone(wach.parse_sperre(""))

    def test_offline_keine_systemaufrufe(self):
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("Systemaufruf")):
            self.assertIsNone(wach.sperre_status())
            self.assertFalse(wach.amphetamine_installiert())
            self.assertFalse(wach.amphetamine_laeuft())
            self.assertIsNone(wach.passwort_dialog())

    def test_konfig_pruefung(self):
        self.assertEqual(konfig.pruefen(self.k), [])
        for falsch in (-1, 90000, "300", 1.5):
            self.k["wach"]["sperre_standard"] = falsch
            self.assertTrue(any("sperre_standard" in f for f in konfig.pruefen(self.k)), falsch)


# ---------------------------------------------------------------------------------------------- 2–7
class ManuellTest(WachBasis):
    def test_abbruch_aendert_nichts(self):
        self.sys.dialog = None
        erg = wach.wach_an(self.k, self.now)
        self.assertEqual((erg["ok"], erg["fehler"]), (False, "abgebrochen"))
        self.assertEqual(self.sys.mit("sysadminctl"), [])
        self.assertEqual(self.sys.amph("Amphetamine"), [])
        self.assertFalse(os.path.exists(util.pfad(*wach.MODUS_DATEI)))

    def test_an_sperre_aus_passwort_nirgends(self):
        erg = wach.wach_an(self.k, self.now)
        self.assertTrue(erg["ok"])
        setzen = [a for a in self.sys.mit("sysadminctl") if "-password" in a]
        self.assertEqual(setzen, [["/usr/sbin/sysadminctl", "-screenLock", "off", "-password", PASSWORT]])
        datei = util.pfad(*wach.MODUS_DATEI)
        self.assertEqual(stat.S_IMODE(os.stat(datei).st_mode), 0o600)
        m = util.lies_json(datei)
        self.assertEqual((m["an"], m["sperre_vorher"], m["amph"]), (True, "300", True))
        start = self.sys.amph("start new session")
        self.assertEqual(len(start), 1)
        self.assertIn("duration:0, interval:0", " ".join(start[0]))
        self.assertIn("enable closed display mode", start[0])
        self.assertNotIn(PASSWORT, self.alle_dateien())
        self.assertNotIn(PASSWORT, json.dumps(erg))

    def test_falsches_passwort(self):
        self.sys.sysadmin_ok = False
        erg = wach.wach_an(self.k, self.now)
        self.assertEqual((erg["ok"], erg["fehler"]), (False, "passwort"))
        self.assertFalse(os.path.exists(util.pfad(*wach.MODUS_DATEI)))
        self.assertEqual(self.sys.amph("start new session"), [])
        self.assertNotIn(PASSWORT, self.alle_dateien() + erg["text"])

    def test_sperre_schon_aus_behaelt_wert(self):
        util.schreib_json(util.pfad(*wach.MODUS_DATEI), {"an": False, "sperre_vorher": "600"})
        self.sys.sperre = "off"
        wach.wach_an(self.k, self.now)
        self.assertEqual(util.lies_json(util.pfad(*wach.MODUS_DATEI))["sperre_vorher"], "600")

    def test_alte_zustandsdatei_einmal(self):
        alt = os.path.join(self.home, "alt", ".vorherige-sperre")
        os.makedirs(os.path.dirname(alt))
        with open(alt, "w") as f:
            f.write("600\n")
        vorher = os.stat(alt).st_mtime_ns
        self.k["wach"]["remote_alt_zustand"] = alt
        self.sys.sperre = "off"                    # remote.sh hatte die Sperre schon ausgeschaltet
        erg = wach.wach_an(self.k, self.now)
        self.assertIn("600", erg["text"])
        m = util.lies_json(util.pfad(*wach.MODUS_DATEI))
        self.assertEqual((m["sperre_vorher"], m["uebernommen"]), ("600", True))
        with open(alt) as f:
            self.assertEqual(f.read(), "600\n")
        self.assertEqual(os.stat(alt).st_mtime_ns, vorher)
        with open(alt, "w") as f:
            f.write("900\n")
        wach.wach_an(self.k, self.now)
        self.assertEqual(util.lies_json(util.pfad(*wach.MODUS_DATEI))["sperre_vorher"], "600")

    def test_aus_stellt_sperre_wieder_her(self):
        wach.wach_an(self.k, self.now)
        self.sys.aufrufe.clear()
        erg = wach.wach_aus(self.k, self.now + 60)
        self.assertTrue(erg["ok"])
        self.assertIn(["/usr/sbin/sysadminctl", "-screenLock", "300", "-password", PASSWORT], self.sys.aufrufe)
        ende = self.sys.amph("end session")
        self.assertEqual(len(ende), 1)
        self.assertIn("allow screen saver", ende[0])
        self.assertFalse(util.lies_json(util.pfad(*wach.MODUS_DATEI))["an"])
        self.assertNotIn(PASSWORT, self.alle_dateien())

    def test_aus_ohne_gesicherten_wert_nimmt_standard(self):
        self.k["wach"]["sperre_standard"] = 120
        self.sys.sperre = "off"
        wach.wach_aus(self.k, self.now)
        self.assertIn(["/usr/sbin/sysadminctl", "-screenLock", "120", "-password", PASSWORT], self.sys.aufrufe)

    def test_aus_laesst_fremde_amphetamine_sitzung(self):
        """wach aus ohne vorheriges wach an: Sperre wiederherstellen, fremde Sitzung des Nutzers nicht beenden."""
        self.sys.sperre = "off"
        self.sys.lage = "aktiv 0"
        erg = wach.wach_aus(self.k, self.now)
        self.assertTrue(erg["ok"])
        self.assertEqual(self.sys.amph("end session"), [])

    def test_aus_beendet_sitzung_des_alten_remote_skripts(self):
        alt = os.path.join(self.home, ".vorherige-sperre")
        with open(alt, "w") as f:
            f.write("immediate\n")
        self.k["wach"]["remote_alt_zustand"] = alt
        self.sys.sperre = "off"
        self.sys.lage = "aktiv 0"
        wach.wach_aus(self.k, self.now)
        self.assertIn(["/usr/sbin/sysadminctl", "-screenLock", "immediate", "-password", PASSWORT],
                      self.sys.aufrufe)
        self.assertEqual(len(self.sys.amph("end session")), 1)

    def test_an_aus_mit_sofortiger_sperre(self):
        self.sys.sperre = "immediate"
        wach.wach_an(self.k, self.now)
        self.assertEqual(util.lies_json(util.pfad(*wach.MODUS_DATEI))["sperre_vorher"], "immediate")
        wach.wach_aus(self.k, self.now + 60)
        self.assertIn(["/usr/sbin/sysadminctl", "-screenLock", "immediate", "-password", PASSWORT],
                      self.sys.aufrufe)
        self.assertEqual(self.sys.sperre, "immediate")

    def test_rueckbau(self):
        self.assertEqual(wach.rueckbau(self.now), ["–"])
        wach.wach_an(self.k, self.now)
        zeilen = wach.rueckbau(self.now)
        self.assertTrue(any("wach aus" in z and "Bildschirmsperre" in z for z in zeilen), zeilen)
        self.assertEqual(self.sys.sperre, "off")           # Rückbau ändert die Sperre nie (kein Passwort)

    def test_rueckbau_beendet_eigene_automatische_sitzung(self):
        util.schreib_json(util.pfad(*wach.DATEI), {"amph": {"eigen": True, "bis": self.now + 3600,
                                                            "gestartet": self.now, "zugeklappt": True}})
        self.sys.lage = "aktiv 3600"
        wach.rueckbau(self.now)
        self.assertEqual(len(self.sys.amph("end session")), 1)
        self.assertFalse(util.lies_json(util.pfad(*wach.DATEI))["amph"]["eigen"])
        # fremde (unbegrenzte) Sitzung bleibt
        util.schreib_json(util.pfad(*wach.DATEI), {"amph": {"eigen": True, "bis": self.now + 3600}})
        self.sys.lage = "aktiv 0"
        self.sys.aufrufe.clear()
        wach.rueckbau(self.now)
        self.assertEqual(self.sys.amph("end session"), [])

    def test_ohne_amphetamine(self):
        self.ohne_amphetamine()
        erg = wach.wach_an(self.k, self.now)
        self.assertTrue(erg["ok"])
        self.assertIn("Amphetamine ist nicht installiert", erg["text"])
        self.assertIn(["/usr/sbin/sysadminctl", "-screenLock", "off", "-password", PASSWORT], self.sys.aufrufe)
        self.assertEqual(self.sys.amph("Amphetamine"), [])
        b = wach.status_block(self.k, self.now, mac={"netzteil": True, "wach_bei_deckel_zu": False})
        self.assertEqual((b["modus"], b["art"], b["an"], b["amphetamine"]), ("manuell", "aus", False, "fehlt"))
        self.assertEqual(b["sperre"], "off")
        erg = wach.wach_aus(self.k, self.now)
        self.assertTrue(erg["ok"])
        self.assertEqual(self.sys.amph("Amphetamine"), [])


# ---------------------------------------------------------------------------------------------- 8–13, 15
class AutomatischTest(WachBasis):
    def setUp(self):
        super().setUp()
        self.setze_zeit(zeit(26, 23))

    def test_nachtmodus_startet_eigene_sitzung(self):
        self.probe_ok()
        nacht.alle_an(self.now, "08:00")
        c = self.halten()
        start = self.sys.amph("start new session")
        self.assertEqual(len(start), 1)
        self.assertIn("duration:540, interval:minutes", " ".join(start[0]))
        self.assertIn("enable closed display mode", start[0])
        amph = util.lies_json(util.pfad(*wach.DATEI))["amph"]
        self.assertEqual((amph["eigen"], amph["bis"]), (True, zeit(27, 8)))
        self.assertTrue(any("Amphetamine-Sitzung bis" in a for a in c.aktionen))
        # nächster Tick: eigene Sitzung reicht, keine AppleScript-Abfrage
        self.sys.aufrufe.clear()
        self.setze_zeit(self.now + 60)
        self.halten()
        self.assertEqual(self.sys.amph("Amphetamine"), [])
        b = wach.status_block(self.k, self.now, mac={"netzteil": True, "wach_bei_deckel_zu": False})
        self.assertEqual((b["an"], b["art"], b["modus"], b["bis"], b["zugeklappt_ok"]),
                         (True, "amphetamine", "automatisch", zeit(27, 8), True))
        self.assertIn("zugeklappt ok", b["text"])

    def test_nachtmodus_haelt_mit_caffeinate_wach(self):
        self.k["wach"]["caffeinate"] = True
        nacht.alle_an(self.now, "08:00")
        c = self.halten(dry_run=True)
        self.assertTrue(any("caffeinate" in a for a in c.aktionen))
        self.k["wach"]["bei_nachtmodus"] = False
        c = self.halten(dry_run=True)
        self.assertFalse(any("caffeinate" in a for a in c.aktionen))

    def test_ohne_probe_kein_applescript(self):
        nacht.alle_an(self.now, "08:00")
        self.halten()
        self.assertEqual(self.sys.amph("Amphetamine"), [])

    def test_fremde_sitzung_wird_nie_angefasst(self):
        self.probe_ok()
        self.sys.lage = "aktiv 0"                  # unbegrenzte Sitzung von Hand
        nacht.alle_an(self.now, "08:00")
        self.halten()
        self.assertEqual(self.sys.amph("start new session"), [])
        nacht.alle_aus(self.now)
        self.halten()
        self.assertEqual(self.sys.amph("end session"), [])

    def test_bedarf_weg_beendet_nur_eigene(self):
        self.probe_ok()
        nacht.alle_an(self.now, "08:00")
        self.halten()
        nacht.alle_aus(self.now)
        self.setze_zeit(self.now + 120)
        c = self.halten()
        ende = self.sys.amph("end session")
        self.assertEqual(len(ende), 1)
        self.assertNotIn("allow screen saver", ende[0])
        self.assertFalse(util.lies_json(util.pfad(*wach.DATEI))["amph"]["eigen"])
        self.assertTrue(any("beendet" in a for a in c.aktionen))

    def test_eigene_von_hand_ersetzt_wird_nicht_beendet(self):
        self.probe_ok()
        nacht.alle_an(self.now, "08:00")
        self.halten()
        self.sys.lage = "aktiv 0"                  # Nutzer hat eine eigene unbegrenzte Sitzung gestartet
        nacht.alle_aus(self.now)
        self.halten()
        self.assertEqual(self.sys.amph("end session"), [])

    def test_pausiert(self):
        self.probe_ok()
        nacht.alle_an(self.now, "08:00")
        self.halten(pausiert=True)
        self.assertEqual(self.sys.amph("start new session"), [])
        self.halten()
        self.assertEqual(len(self.sys.amph("start new session")), 1)
        self.halten(pausiert=True)
        self.assertEqual(len(self.sys.amph("end session")), 1)

    def test_manueller_modus_keine_automatik(self):
        self.probe_ok()
        wach.wach_an(self.k, self.now)
        self.sys.aufrufe.clear()
        nacht.alle_an(self.now, "08:00")
        self.halten()
        self.assertEqual(self.sys.amph("Amphetamine"), [])

    def test_manueller_modus_ohne_amph_sitzung_startet_automatik(self):
        """wach an konnte Amphetamine nicht starten: die automatische Sitzung (zugeklappt) springt ein."""
        self.probe_ok()
        wach.wach_an(self.k, self.now)
        m = util.lies_json(util.pfad(*wach.MODUS_DATEI))
        m["amph"] = False
        util.schreib_json(util.pfad(*wach.MODUS_DATEI), m)
        self.sys.lage = "inaktiv"
        self.sys.aufrufe.clear()
        nacht.alle_an(self.now, "08:00")
        self.halten()
        self.assertEqual(len(self.sys.amph("start new session")), 1)

    def test_manueller_modus_amphetamine_beendet(self):
        self.probe_ok()
        wach.wach_an(self.k, self.now)
        self.sys.amph_laeuft = False
        self.assertFalse(wach._manuell_haelt())
        self.sys.amph_laeuft = True
        self.assertTrue(wach.haelt_zugeklappt(self.k, self.now))

    def test_probe_nur_tagsueber_und_einmal(self):
        self.halten()                              # 23 Uhr
        self.assertEqual(self.sys.mit("pgrep") + self.sys.amph("Amphetamine"), [])
        self.setze_zeit(zeit(27, 10))
        self.halten()
        self.assertEqual(len(self.sys.amph("session is active")), 1)
        self.assertEqual(util.lies_json(util.pfad(*wach.DATEI))["probe"]["ergebnis"], "ok")
        self.setze_zeit(zeit(27, 11))
        self.halten()
        self.assertEqual(len(self.sys.amph("session is active")), 1)
        self.assertEqual(wach.status_block(self.k, self.now, mac={})["amphetamine"], "bereit")

    def test_probe_ohne_laufende_app(self):
        self.sys.amph_laeuft = False
        self.setze_zeit(zeit(27, 10))
        self.halten()
        self.assertEqual(self.sys.amph("Amphetamine"), [])
        self.assertEqual(wach.status_block(self.k, self.now, mac={})["amphetamine"], "ungeprueft")

    def test_probe_verweigert(self):
        self.sys.verweigert = True
        self.k["wach"]["caffeinate"] = True
        self.setze_zeit(zeit(27, 10))
        self.halten()
        self.halten()
        pushes = [m for m in self.melder.protokoll if "Automation" in m["text"]]
        self.assertEqual(len(pushes), 1)
        self.assertEqual(wach.status_block(self.k, self.now, mac={})["amphetamine"], "verweigert")
        self.sys.aufrufe.clear()
        self.setze_zeit(zeit(27, 23))
        nacht.alle_an(self.now, "08:00")
        with mock.patch.object(wach, "sicherstellen", return_value="caffeinate gestartet") as caf:
            c = self.halten()
        caf.assert_called_once()
        self.assertEqual(self.sys.amph("Amphetamine"), [])
        self.assertIn("caffeinate gestartet", c.aktionen)

    def test_dry_run_ruft_nichts_auf(self):
        self.probe_ok()
        nacht.alle_an(self.now, "08:00")
        c = self.halten(dry_run=True)
        self.assertEqual(self.sys.aufrufe, [])
        self.assertTrue(any("würde eine Amphetamine-Sitzung" in a for a in c.aktionen))

    def _wartende_sitzung(self):
        register.aktualisieren("claude", "sess-w", lambda d: d.update(
            status="gestoppt", fortsetzen_ab=self.now + 3600, reset=self.now + 3600, cwd=self.home,
            terminal="term_A", pane_key="t:A", zuletzt=self.now))
        nacht.sitzung_an("claude", "sess-w", self.now)

    def test_nacht_hinweis_nennt_eigenen_befehl(self):
        self.ohne_amphetamine()
        self._wartende_sitzung()
        self.halten(mac={"netzteil": True, "wach_bei_deckel_zu": False})
        texte = [m["text"] for m in self.melder.protokoll]
        self.assertTrue(any("waechter.py wach an" in x for x in texte), texte)

    def test_kein_nacht_hinweis_bei_eigener_zugeklappt_sitzung(self):
        self.probe_ok()
        self._wartende_sitzung()
        self.halten(mac={"netzteil": True, "wach_bei_deckel_zu": False})
        self.assertEqual(len(self.sys.amph("start new session")), 1)
        self.assertFalse(any("wach an" in m["text"] for m in self.melder.protokoll))

    def test_fremder_befehl_bleibt(self):
        self.ohne_amphetamine()
        skript = os.path.join(self.home, "wach.sh")
        with open(skript, "w") as f:
            f.write("#!/bin/sh\n")
        self.k["wach"]["remote_modus_befehl"] = skript + " on"
        self._wartende_sitzung()
        self.halten(mac={"netzteil": True, "wach_bei_deckel_zu": False})
        self.assertTrue(any(skript + " on" in m["text"] for m in self.melder.protokoll))

    def test_geloeschtes_altes_skript_zeigt_eigenen_befehl(self):
        self.ohne_amphetamine()
        self.k["wach"]["remote_modus_befehl"] = os.path.join(self.home, "weg", "remote.sh") + " an"
        self._wartende_sitzung()
        self.halten(mac={"netzteil": True, "wach_bei_deckel_zu": False})
        texte = [m["text"] for m in self.melder.protokoll]
        self.assertTrue(any("wach an" in x for x in texte), texte)
        self.assertFalse(any("remote.sh" in x for x in texte))

    def test_alte_zustandsdatei_neben_remote_skript(self):
        ordner = os.path.join(self.home, "Remote-Modus")
        os.makedirs(ordner)
        with open(os.path.join(ordner, ".vorherige-sperre"), "w") as f:
            f.write("600\n")
        self.k["wach"]["remote_modus_befehl"] = os.path.join(ordner, "remote.sh") + " an"
        self.assertEqual(wach.alt_zustand_datei(self.k), os.path.join(ordner, ".vorherige-sperre"))
        self.sys.sperre = "off"
        wach.wach_aus(self.k, self.now)
        self.assertIn(["/usr/sbin/sysadminctl", "-screenLock", "600", "-password", PASSWORT], self.sys.aufrufe)


# ---------------------------------------------------------------------------------------------- 14, 16
class WachCliTest(CliBasis):
    SCHLUESSEL = {"an", "art", "modus", "bis", "sperre", "zugeklappt_ok", "netzteil", "amphetamine", "text"}

    def test_status_json_offline_ohne_systemaufrufe(self):
        aufrufe = []

        def run(args, *a, **kw):
            aufrufe.append(list(args))
            return subprocess.CompletedProcess(args, 1, "", "")

        with mock.patch("subprocess.run", side_effect=run), \
                mock.patch.object(wach.subprocess, "Popen", side_effect=AssertionError("Popen")):
            code, out = self.cli("status", "--json")
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(set(d["wach"]), self.SCHLUESSEL)
        self.assertEqual((d["wach"]["art"], d["wach"]["sperre"], d["wach"]["netzteil"]), ("aus", None, None))
        verboten = ("sysadminctl", "osascript", "pgrep", "pmset", "ioreg")
        self.assertFalse([a for a in aufrufe if any(v in a[0] for v in verboten)], aufrufe)
        code, out = self.cli("status")
        self.assertIn("Wach-Modus aus", out)

    def test_englische_befehle_und_json(self):
        self.sprache_setzen("en")
        attrappe = SystemAttrappe()
        app = os.path.join(self.home, "Amphetamine.app")
        os.makedirs(app)
        with mock.patch.object(wach, "RUNNER", attrappe), mock.patch.object(wach, "AMPH_PFADE", (app,)):
            code, out = self.cli("awake", "on", "--json")
            self.assertEqual(code, 0)
            d = json.loads(out)
            self.assertEqual((d["ok"], d["fehler"], d["wach"]["modus"], d["wach"]["art"]),
                             (True, None, "manuell", "amphetamine"))
            self.assertIn("Awake mode ON", d["text"])
            self.assertNotIn(PASSWORT, out)
            code, out = self.cli("awake", "status")
            self.assertEqual(code, 0)
            self.assertIn("screen lock: off", out)
            code, out = self.cli("awake", "off", "--json")
            self.assertEqual((code, json.loads(out)["wach"]["modus"]), (0, "aus"))
            attrappe.dialog = None
            code, out = self.cli("awake", "on", "--json")
            self.assertEqual((code, json.loads(out)["fehler"]), (1, "abgebrochen"))
            code, out = self.cli("awake", "maybe")
            self.assertEqual(code, 2)
        with open(util.pfad("log", "waechter.log"), encoding="utf-8") as f:
            self.assertNotIn(PASSWORT, f.read())

    def test_deutsche_befehle(self):
        attrappe = SystemAttrappe(dialog=None)
        with mock.patch.object(wach, "RUNNER", attrappe), mock.patch.object(wach, "AMPH_PFADE", ()):
            code, out = self.cli("wach", "an")
            self.assertEqual(code, 1)
            self.assertIn("Abgebrochen", out)
            code, out = self.cli("wach", "--json")
            self.assertEqual((code, json.loads(out)["wach"]["amphetamine"]), (0, "fehlt"))
