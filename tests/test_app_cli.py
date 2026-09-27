"""v1.2: Schnittstelle für die Menüleisten-App (status --json, schwellen, app-texte, config.local.toml)."""

import contextlib
import io
import json
import os
import stat
import unittest.mock
import subprocess
import unittest

from hilfe import TempHome, lies_fixture_json

from lw import VERSION, cli, installer, konfig, register, sprache, util

APP_SCHLUESSEL = """app_titel app_version app_aktiv app_waechter_aus app_kein_tick app_letzter_tick app_orca_fehlt
app_fuenf app_woche app_reset app_keine_daten app_veraltet app_reserve_erreicht app_pause app_pausiert
app_pausiert_bis app_pause_30m app_pause_2h app_pause_offen app_pause_ende app_nacht app_nacht_alle app_nacht_aus
app_nacht_sitzung app_nacht_hinweis app_sitzungen app_keine_sitzungen app_fortsetzung_ab app_weiter_noetig
app_schwellen app_warnung app_stopp app_woche_warnung app_woche_stopp app_reserve app_speichern app_gespeichert
app_fehler app_bericht app_bericht_leer app_log_oeffnen app_aktualisieren app_beenden app_schliessen
app_python_fehlt app_min app_std""".split()


class CliBasis(TempHome):
    def setUp(self):
        super().setUp()
        self.konfig = os.path.join(self.home, "config.toml")
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write('[allgemein]\nsprache = "de"\n')
        os.environ["LIMIT_WAECHTER_CONFIG"] = self.konfig
        self.lokal = konfig.lokal_pfad(self.konfig)
        # Nie das echte ~/.claude lesen: Statusline-Zustand aus einer Temp-settings.json.
        self._alt_settings = os.environ.get("LIMIT_WAECHTER_CLAUDE_SETTINGS")
        self.settings = os.path.join(self.home, "claude-settings.json")
        os.environ["LIMIT_WAECHTER_CLAUDE_SETTINGS"] = self.settings

    def tearDown(self):
        if self._alt_settings is None:
            os.environ.pop("LIMIT_WAECHTER_CLAUDE_SETTINGS", None)
        else:
            os.environ["LIMIT_WAECHTER_CLAUDE_SETTINGS"] = self._alt_settings
        super().tearDown()

    def cli(self, *args):
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            code = cli.main(list(args))
        return code, puffer.getvalue()

    def sprache_setzen(self, wert):
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write(f'[allgemein]\nsprache = "{wert}"\n')


class StatusJsonTest(CliBasis):
    def test_alle_schluessel_des_fixtures(self):
        util.schreib_json(util.pfad("state", "zustand.json"), {"letzter_tick": self.now - 30})
        register.aktualisieren("claude", "11111111-2222", lambda d: d.update(cwd="/p/demo-app/", status="aktiv",
                                                                            zuletzt=self.now))
        register.aktualisieren("codex", "01a0da88-ad20", lambda d: d.update(worktree="/p/api", status="gestoppt",
                                                                           zuletzt=self.now,
                                                                           fortsetzen_ab=self.now + 60))
        register.aktualisieren("claude", "aaaaaaaa-bbbb", lambda d: d.update(status="beendet", zuletzt=self.now))
        code, out = self.cli("status", "--json")
        self.assertEqual(code, 0)
        d = json.loads(out)
        muster = lies_fixture_json(os.path.join("app", "status.json"))
        self.assertLessEqual(set(muster), set(d))
        for a in ("claude", "codex"):
            self.assertLessEqual(set(muster["phasen"][a]), set(d["phasen"][a]))
        s_keys = set().union(*(set(x) for x in muster["sitzungen"])) - {"fortsetzen_ab"}
        for x in d["sitzungen"]:
            self.assertLessEqual(s_keys - {"cwd"}, set(x))
        self.assertEqual(d["version"], VERSION)
        self.assertEqual(d["sprache"], "de")
        self.assertEqual(d["letzter_tick"], self.now - 30)
        self.assertEqual(d["jetzt"], self.now)
        self.assertIsNone(d["pause_bis"])
        self.assertTrue(d["nur_mit_nachtmodus"])
        self.assertEqual(d["bericht_uhrzeit"], "08:00")
        self.assertEqual(d["schwellen"], {"warnung": 80, "stopp": 92, "woche_warnung": 80, "woche_stopp": 92,
                                          "wochen_reserve": 20})
        nach_id = {x["id"]: x for x in d["sitzungen"]}
        self.assertEqual(nach_id["11111111-2222"]["projekt"], "demo-app")
        self.assertEqual(nach_id["01a0da88-ad20"]["projekt"], "api")
        self.assertIsNone(nach_id["aaaaaaaa-bbbb"]["projekt"])
        self.assertEqual(nach_id["01a0da88-ad20"]["status_text"], "gestoppt")

    def test_pause_bis(self):
        self.cli("pause", "30m")
        d = json.loads(self.cli("status", "--json")[1])
        self.assertTrue(d["pausiert"])
        self.assertEqual(d["pause_bis"], self.now + 1800)


class OrteUndStatuslineTest(CliBasis):
    """v1.3: ort, faehigkeiten, orca_vorhanden, nur_orca, statusline in status --json und im Text."""

    def sitzungen_anlegen(self):
        register.aktualisieren("claude", "11111111-orca", lambda d: d.update(cwd="/p/a", status="gestoppt",
                                                                            zuletzt=self.now, ort="orca",
                                                                            terminal="term-1"))
        register.aktualisieren("claude", "22222222-term", lambda d: d.update(cwd="/p/b", status="gestoppt",
                                                                            zuletzt=self.now, ort="terminal"))
        register.aktualisieren("codex", "33333333-desk", lambda d: d.update(cwd="/p/c", status="wartet_auf_weiter",
                                                                           zuletzt=self.now, ort="desktop"))
        register.aktualisieren("claude", "44444444-alt", lambda d: d.update(cwd="/p/d", status="aktiv",
                                                                           zuletzt=self.now, pane_key="x:1"))

    def status_json(self, orca_da=False):
        with unittest.mock.patch.object(cli, "_orca_vorhanden", return_value=orca_da):
            return json.loads(self.cli("status", "--json")[1])

    def test_sitzungsfelder(self):
        self.sitzungen_anlegen()
        d = self.status_json()
        self.assertFalse(d["orca_vorhanden"])
        self.assertFalse(d["nur_orca"])
        n = {x["id"]: x for x in d["sitzungen"]}
        self.assertEqual([n[i]["ort"] for i in ("11111111-orca", "22222222-term", "33333333-desk", "44444444-alt")],
                         ["orca", "terminal", "desktop", "orca"])
        self.assertEqual(n["22222222-term"]["ort_text"], "Terminal")
        self.assertEqual(n["22222222-term"]["faehigkeiten"], {"warnen": "ja", "stoppen": "ja", "fortsetzen": "push"})
        self.assertEqual(n["22222222-term"]["faehigkeiten_text"], "warnt · stoppt · nur Push")
        self.assertEqual(n["33333333-desk"]["faehigkeiten"]["stoppen"], "nein")
        self.assertEqual(n["33333333-desk"]["faehigkeiten_text"], "warnt · stoppt nicht · nur Push")
        self.assertIn(n["11111111-orca"]["faehigkeiten"]["fortsetzen"], ("ja", "push"))

    def test_englisch(self):
        self.sprache_setzen("en")
        self.sitzungen_anlegen()
        n = {x["id"]: x for x in self.status_json()["sitzungen"]}
        self.assertEqual(n["33333333-desk"]["ort_text"], "Desktop")
        self.assertEqual(n["33333333-desk"]["faehigkeiten_text"], "warns · no stop · push only")

    def test_automatisch_nur_wo_der_waechter_fortsetzt(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = False
        orca = {"anbieter": "claude", "status": "gestoppt", "ort": "orca", "fortsetzen_ab": self.now + 60}
        term = dict(orca, ort="terminal")
        self.assertTrue(cli.automatisch(orca, self.k, self.now))
        self.assertFalse(cli.automatisch(term, self.k, self.now), "nach Wächter-Stopp setzt dort niemand fort")
        self.assertTrue(cli.automatisch(dict(term, status="limit"), self.k, self.now), "eingebaute Fortsetzung")
        self.assertFalse(cli.automatisch(orca, self.k, self.now, orca_ok=False))
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = True
        self.assertFalse(cli.automatisch(orca, self.k, self.now), "ohne Nachtmodus")
        self.assertTrue(cli.automatisch(dict(orca, nacht_bis=self.now + 3600), self.k, self.now))

    def test_faehigkeiten_text_kein_fortsetzen(self):
        self.assertEqual(cli.faehigkeiten_text({"warnen": "ja", "stoppen": "ja", "fortsetzen": "nein"}),
                         "warnt · stoppt · kein Fortsetzen")

    def test_statusline_zustaende(self):
        self.assertEqual(cli.statusline_info(), {"zustand": "aus", "stand": None})       # keine settings.json
        with open(self.settings, "w", encoding="utf-8") as f:
            f.write("{kaputt")
        self.assertEqual(cli.statusline_info()["zustand"], "aus")
        util.schreib_json(self.settings, {"statusLine": {"type": "command",
                                                         "command": "/usr/bin/python3 x " + installer.SL_MARKER}})
        self.assertEqual(cli.statusline_info(), {"zustand": "aktiv", "stand": None})
        util.schreib_json(util.pfad("state", "statusline.json"),
                          {"version": 1, "stand": self.now - 60, "fuenf": {"pct": 10, "reset": self.now + 99},
                           "woche": None})
        self.assertEqual(cli.statusline_info(), {"zustand": "aktiv", "stand": self.now - 60})
        self.assertEqual(self.status_json()["statusline"], {"zustand": "aktiv", "stand": self.now - 60})
        util.schreib_json(self.settings, {"statusLine": {"type": "command", "command": "anderes"}})
        util.schreib_json(util.pfad(*installer.SL_ORIGINAL), {"version": 1, "gesichert": self.now, "statusLine": None})
        self.assertEqual(cli.statusline_info(self.settings)["zustand"], "zurueckgeschrieben")

    def test_textausgabe(self):
        self.sitzungen_anlegen()
        with unittest.mock.patch.object(cli, "_orca_vorhanden", return_value=False):
            out = self.cli("status")[1]
        self.assertIn(sprache.TEXTE["st_orca_fehlt"]["de"], out)
        self.assertIn(sprache.TEXTE["st_sl_aus"]["de"], out)
        self.assertIn("Terminal", out)
        self.assertIn("Desktop", out)
        util.schreib_json(self.settings, {"statusLine": {"command": "x " + installer.SL_MARKER}})
        util.schreib_json(util.pfad("state", "statusline.json"),
                          {"version": 1, "stand": self.now - 120, "fuenf": {"pct": 10, "reset": None}})
        with unittest.mock.patch.object(cli, "_orca_vorhanden", return_value=True):
            out = self.cli("status")[1]
        self.assertNotIn(sprache.TEXTE["st_orca_fehlt"]["de"], out)
        self.assertIn("Statusline-Kette aktiv (zuletzt vor", out)


class AppSelbsttestTest(unittest.TestCase):
    APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "app", "build", "Limit-Waechter.app", "Contents", "MacOS", "LimitWaechter")

    def test_fixture_mit_orten(self):
        d = lies_fixture_json(os.path.join("app", "status.json"))
        self.assertEqual({x.get("ort") for x in d["sitzungen"]} - {None}, {"orca", "terminal", "desktop"})
        self.assertIn(d["statusline"]["zustand"], ("aktiv", "zurueckgeschrieben", "aus"))
        if not os.path.exists(self.APP):
            self.skipTest("App nicht gebaut (app/build.sh)")
        v = subprocess.run([self.APP, "--version"], capture_output=True, text=True, timeout=30).stdout.split()
        if not v or v[-1] != VERSION:
            # install.sh app testet vor dem Bauen: eine ältere Build darf das nicht blockieren
            self.skipTest("App-Build ist veraltet (app/build.sh)")
        r = subprocess.run([self.APP, "--selbsttest", os.path.join(os.path.dirname(self.APP), "..", "..", "..", "..",
                                                                    "..", "tests", "fixtures", "app", "status.json")],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("orte: orca,terminal,desktop", r.stdout)


class LokalSetzenTest(CliBasis):
    def test_legt_datei_an(self):
        konfig.lokal_setzen("schwellen", {"warnung": 70})
        with open(self.lokal, encoding="utf-8") as f:
            self.assertEqual(konfig.parse_toml(f.read()), {"schwellen": {"warnung": 70}})
        self.assertEqual(stat.S_IMODE(os.stat(self.lokal).st_mode), 0o600)

    def test_erhaelt_kommentare_ersetzt_und_ergaenzt(self):
        text = ('# persönlich\n[allgemein]\nname = "X"  # Name\n\n[schwellen]\n'
                'warnung = 75  # eigene\n# Kommentar im Abschnitt\n\n[bericht]\nuhrzeit = "07:00"\n')
        with open(self.lokal, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(self.lokal, 0o640)
        konfig.lokal_setzen("schwellen", {"warnung": 70, "stopp": 90})
        with open(self.lokal, encoding="utf-8") as f:
            neu = f.read()
        self.assertIn("# persönlich", neu)
        self.assertIn("# Kommentar im Abschnitt", neu)
        self.assertIn("warnung = 70  # eigene", neu)
        self.assertEqual(konfig.parse_toml(neu), {"allgemein": {"name": "X"}, "schwellen": {"warnung": 70, "stopp": 90},
                                                   "bericht": {"uhrzeit": "07:00"}})
        self.assertEqual(stat.S_IMODE(os.stat(self.lokal).st_mode), 0o640)

    def test_ergaenzt_abschnitt(self):
        with open(self.lokal, "w", encoding="utf-8") as f:
            f.write('[allgemein]\nname = "X"\n')
        konfig.lokal_setzen("schwellen", {"stopp": 95})
        with open(self.lokal, encoding="utf-8") as f:
            self.assertEqual(konfig.parse_toml(f.read()), {"allgemein": {"name": "X"}, "schwellen": {"stopp": 95}})


    def test_doppelter_schluessel(self):
        with open(self.lokal, "w", encoding="utf-8") as f:
            f.write("[schwellen]\nwarnung = 70\nwarnung = 71\n")
        konfig.lokal_setzen("schwellen", {"warnung": 75})
        with open(self.lokal, encoding="utf-8") as f:
            neu = f.read()
        self.assertNotIn("71", neu)
        self.assertEqual(konfig.parse_toml(neu)["schwellen"]["warnung"], 75)

    def test_neuer_schluessel_vor_kommentar_des_naechsten_abschnitts(self):
        with open(self.lokal, "w", encoding="utf-8") as f:
            f.write("[schwellen]\nwarnung = 70\n\n# zu nacht\n[nacht]\n")
        konfig.lokal_setzen("schwellen", {"stopp": 93})
        with open(self.lokal, encoding="utf-8") as f:
            zeilen = f.read().splitlines()
        self.assertLess(zeilen.index("stopp = 93"), zeilen.index("# zu nacht"))


class SchwellenTest(CliBasis):
    def test_anzeigen(self):
        code, out = self.cli("schwellen", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["schwellen"]["stopp"], 92)
        code, out = self.cli("schwellen")
        self.assertIn("wochen_reserve", out)

    def test_setzen_deutsch_und_englisch(self):
        code, out = self.cli("schwellen", "setzen", "warnung=70", "stopp=90", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out), {"ok": True, "schwellen": {"warnung": 70, "stopp": 90, "woche_warnung": 80,
                                                                     "woche_stopp": 92, "wochen_reserve": 20}})
        code, out = self.cli("thresholds", "set", "weekly_warn=75", "weekly_stop=90", "weekly_reserve=10",
                             "warn=60", "stop=85", "--json")
        self.assertEqual(code, 0, out)
        s = konfig.laden()["schwellen"]
        self.assertEqual((s["warnung"], s["stopp"], s["woche_warnung"], s["woche_stopp"], s["wochen_reserve"]),
                         (60, 85, 75, 90, 10))

    def test_aliase_in_englisch(self):
        self.sprache_setzen("en")
        code, out = self.cli("schwellen", "setzen", "stop=91", "--json")
        self.assertEqual(code, 0, out)
        code, out = self.cli("thresholds", "--json")
        self.assertEqual(json.loads(out)["schwellen"]["stopp"], 91)
        code, _ = self.cli("nacht", "an")
        self.assertEqual(code, 0)
        code, _ = self.cli("night", "off")
        self.assertEqual(code, 0)

    def test_ungueltig_datei_unveraendert(self):
        with open(self.lokal, "w", encoding="utf-8") as f:
            f.write("# bleibt\n[schwellen]\nwarnung = 70\n")
        with open(self.lokal, encoding="utf-8") as f:
            vorher = f.read()
        for werte in (["warnung=95"], ["warnung=0"], ["stopp=100"], ["stopp=viel"], ["wochen_reserve=51"],
                      ["unbekannt=5"], ["warnung"], [], ["woche_warnung=95", "woche_stopp=90"]):
            with self.subTest(werte=werte):
                code, out = self.cli("schwellen", "setzen", *werte, "--json")
                self.assertEqual(code, 2)
                d = json.loads(out)
                self.assertFalse(d["ok"])
                self.assertTrue(d["fehler"])
                with open(self.lokal, encoding="utf-8") as f:
                    self.assertEqual(f.read(), vorher)


class AppTexteTest(CliBasis):
    def test_de_und_en(self):
        for wert in ("de", "en"):
            with self.subTest(sprache=wert):
                self.sprache_setzen(wert)
                code, out = self.cli("app-texte" if wert == "de" else "app-texts")
                self.assertEqual(code, 0)
                d = json.loads(out)
                self.assertEqual(d["sprache"], wert)
                self.assertLessEqual(set(APP_SCHLUESSEL), set(d["texte"]))
                self.assertIn("phase_warnung", d["texte"])
                self.assertIn("z_gestoppt", d["texte"])
                self.assertEqual(d["texte"]["app_reset"], sprache.TEXTE["app_reset"][wert])
                self.assertIn("{zeit}", d["texte"]["app_reset"])

    def test_sprache_fuer_demo(self):
        self.sprache_setzen("en")
        code, out = self.cli("app-texte", "--sprache", "de")
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d["sprache"], "de")
        self.assertEqual(d["texte"]["app_reset"], sprache.TEXTE["app_reset"]["de"])

    def test_nicht_in_hilfe(self):
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer), self.assertRaises(SystemExit):
            cli.main(["--help"])
        self.assertNotIn("app-texte", puffer.getvalue())
        self.assertIn("schwellen", puffer.getvalue())


if __name__ == "__main__":
    unittest.main()
