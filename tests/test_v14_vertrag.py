"""v1.4: Vertrag zwischen status --json / wach --json und der Menüleisten-App (nach dem Zusammenführen A–D)."""

import contextlib
import io
import json
import os
import unittest.mock

from hilfe import TempHome, lies_fixture_json

from lw import VERSION, cli, melden, nacht, register, util

STUFEN = {"ok", "wartet", "warnung", "stopp", "limit", "pause", "stoerung"}
LAGEN = {"arbeitet", "ruht", "sichert", "wartet", "pruefung", "weiter_noetig", "blockiert", "beendet"}
FARBEN = {"gruen", "grau", "gelb", "blau", "orange", "rot"}
QUELLEN = {"offiziell", "orca", "statusline", "rollout", None}
WACH = {"an", "art", "modus", "bis", "sperre", "zugeklappt_ok", "netzteil", "amphetamine", "text"}
KONTEXT = {"prozent", "tokens", "fenster", "modell", "stufe", "stand", "quelle"}
KONTEXT_STUFEN = {"ok", "warnung", "kritisch"}
KONTEXT_QUELLEN = {"statusline", "transcript", "rollout"}


class VertragTest(TempHome):
    def setUp(self):
        super().setUp()
        self.konfig = os.path.join(self.home, "config.toml")
        self.sprache("de")
        os.environ["LIMIT_WAECHTER_CONFIG"] = self.konfig
        self._alt_settings = os.environ.get("LIMIT_WAECHTER_CLAUDE_SETTINGS")
        os.environ["LIMIT_WAECHTER_CLAUDE_SETTINGS"] = os.path.join(self.home, "claude-settings.json")
        util.schreib_json(util.pfad("state", "zustand.json"), {"letzter_tick": self.now - 30})
        register.aktualisieren("claude", "11111111-2222", lambda d: d.update(cwd="/p/demo", status="aktiv",
                                                                            zuletzt=self.now))
        register.aktualisieren("codex", "01a0da88-ad20", lambda d: d.update(worktree="/p/api", status="gestoppt",
                                                                           zuletzt=self.now,
                                                                           fortsetzen_ab=self.now + 600))
        register.aktualisieren("claude", "33333333-4444", lambda d: d.update(cwd="/p/web", status="blockiert",
                                                                            zuletzt=self.now))

    def tearDown(self):
        if self._alt_settings is None:
            os.environ.pop("LIMIT_WAECHTER_CLAUDE_SETTINGS", None)
        else:
            os.environ["LIMIT_WAECHTER_CLAUDE_SETTINGS"] = self._alt_settings
        super().tearDown()

    def sprache(self, wert):
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write(f'[allgemein]\nsprache = "{wert}"\n')

    def cli(self, *args):
        puffer = io.StringIO()
        with unittest.mock.patch.object(cli, "_launchagent_geladen", return_value=True), \
                unittest.mock.patch.object(melden, "topic_vorhanden", return_value=True), \
                contextlib.redirect_stdout(puffer):
            code = cli.main(list(args))
        return code, puffer.getvalue()

    def pruefe_status(self, d):
        self.assertEqual(d["version"], VERSION)
        self.assertEqual(set(d["gesamt"]), {"stufe", "text", "detail"})
        self.assertIn(d["gesamt"]["stufe"], STUFEN)
        self.assertTrue(d["gesamt"]["text"])
        for a in ("claude", "codex"):
            self.assertEqual(set(d["offiziell"][a]), {"zustand", "fehler", "stand"})
            self.assertIn(d["offiziell"][a]["zustand"], ("ok", "aus", "fehler"))
            ph = d["phasen"][a]
            self.assertIn(ph.get("quelle"), QUELLEN)
            self.assertTrue(ph["quelle_text"])
            self.assertIsInstance(ph["woche_modell"], list)
        self.assertEqual(set(d["wach"]), WACH)
        self.assertIn(d["wach"]["art"], ("amphetamine", "caffeinate", "aus"))
        self.assertIn(d["wach"]["modus"], ("manuell", "automatisch", "aus"))
        self.assertIn(d["wach"]["amphetamine"], ("fehlt", "bereit", "verweigert", "ungeprueft"))
        self.assertTrue(d["sitzungen"])
        for s in d["sitzungen"]:
            self.assertIn(s["lage"], LAGEN)
            self.assertIn(s["lage_farbe"], FARBEN)
            self.assertTrue(s["lage_text"])
            self.assertEqual(set(s["aktivitaet"]), {"letzte", "quelle"})
            # Nachtmodus getrennt: wirksam = max(eigen, für alle) (App zeigt geerbten Modus anders)
            self.assertLessEqual({"nacht_bis", "nacht_eigen", "nacht_global"}, set(s))
            wirksam = [w for w in (s["nacht_eigen"], s["nacht_global"]) if w]
            self.assertEqual(s["nacht_bis"], max(wirksam) if wirksam else None)
            # v1.4 N4: Kontext je Sitzung (verbindlicher Vertrag für die App)
            self.assertIn("kontext", s)
            kx = s["kontext"]
            if kx is not None:
                self.assertEqual(set(kx), KONTEXT)
                self.assertIn(kx["stufe"], KONTEXT_STUFEN)
                self.assertIn(kx["quelle"], KONTEXT_QUELLEN)
                self.assertIsInstance(kx["prozent"], (int, float))
                self.assertIsInstance(kx["tokens"], int)
                self.assertIsInstance(kx["fenster"], int)
                self.assertGreater(kx["fenster"], 0)
                self.assertTrue(kx["modell"] is None or isinstance(kx["modell"], str))
                self.assertIsInstance(kx["stand"], (int, float))
        self.assertEqual(set(d["kontext_schwellen"]), {"warnung", "kritisch"})
        self.assertLess(d["kontext_schwellen"]["warnung"], d["kontext_schwellen"]["kritisch"])

    def test_status_json_de_und_en(self):
        for wert in ("de", "en"):
            with self.subTest(sprache=wert):
                self.sprache(wert)
                code, out = self.cli("status", "--json")
                self.assertEqual(code, 0)
                d = json.loads(out)
                self.pruefe_status(d)
                lagen = {s["id"]: s["lage"] for s in d["sitzungen"]}
                self.assertEqual(lagen["01a0da88-ad20"], "wartet")
                self.assertEqual(lagen["33333333-4444"], "blockiert")

    def test_nacht_eigen_und_fuer_alle_getrennt(self):
        nacht.alle_an(self.now, "08:00")
        nacht.sitzung_an("claude", "33333333-4444", self.now, "09:00")
        code, out = self.cli("status", "--json")
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.pruefe_status(d)
        s = {x["id"]: x for x in d["sitzungen"]}
        geerbt, eigen = s["11111111-2222"], s["33333333-4444"]
        self.assertIsNone(geerbt["nacht_eigen"])
        self.assertIsNotNone(geerbt["nacht_global"])
        self.assertEqual(geerbt["nacht_bis"], geerbt["nacht_global"])
        self.assertIsNotNone(eigen["nacht_eigen"])

    def test_app_fixture_erfuellt_vertrag(self):
        for name in ("status.json", "status_en.json"):
            with self.subTest(fixture=name):
                d = lies_fixture_json(os.path.join("app", name))
                self.assertEqual(d["version"], VERSION)
                self.pruefe_status(d)
                self.assertTrue(any(s["kontext"] for s in d["sitzungen"]))
                self.assertTrue(any(s["kontext"] is None for s in d["sitzungen"]))
        en = lies_fixture_json(os.path.join("app", "status_en.json"))
        self.assertEqual(en["sprache"], "en")
        self.assertNotRegex(json.dumps(en, ensure_ascii=False), "[äöüÄÖÜß]", "englische Demo ohne deutsche Texte")
        self.assertEqual({s["kontext"]["stufe"] for s in en["sitzungen"] if s["kontext"]}, KONTEXT_STUFEN)

    def test_wach_json_fuer_die_app(self):
        code, out = self.cli("wach", "status", "--json")
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertLessEqual({"ok", "fehler", "wach"}, set(d))
        self.assertTrue(d["ok"])
        self.assertIsNone(d["fehler"])
        self.assertEqual(set(d["wach"]), WACH)
