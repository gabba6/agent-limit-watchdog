"""v1.4 D: App-Redesign – Texte, Demo-Fixture und (falls gebaut) Selbsttest der App."""

import glob
import os
import re
import subprocess
import unittest

from hilfe import PROJEKT, lies_fixture_json

from lw import VERSION, sprache

QUELLEN = os.path.join(PROJEKT, "app", "Sources", "LimitWaechter")

# Schlüssel, die die App dynamisch zusammensetzt ("app_of_\(fehler)", "app_amph_\(zustand)", "app_wf_\(fehler)").
DYNAMISCH = {
    "app_of_": ["ok", "aus", "auth", "rate", "netz", "format", "kein_token", "abgelaufen", "fehler"],
    "app_amph_": ["fehlt", "bereit", "verweigert", "ungeprueft"],
    "app_wf_": ["passwort", "system"],
}


def _swift():
    teile = []
    for datei in sorted(glob.glob(os.path.join(QUELLEN, "*.swift"))):
        with open(datei, encoding="utf-8") as f:
            teile.append(f.read())
    return "\n".join(teile)


class AppTexteTest(unittest.TestCase):
    def test_alle_statischen_schluessel_der_app_existieren(self):
        quelltext = _swift()
        genutzt = set(re.findall(r'"(app_[a-z0-9_]+)"', quelltext))
        self.assertTrue(genutzt)
        fehlend = sorted(n for n in genutzt if n not in sprache.TEXTE)
        self.assertEqual(fehlend, [])

    def test_dynamische_schluessel_existieren(self):
        for praefix, werte in DYNAMISCH.items():
            for w in werte:
                with self.subTest(schluessel=praefix + w):
                    self.assertIn(praefix + w, sprache.TEXTE)

    def test_phasen_schluessel_fuer_chips(self):
        for p in ("ok", "warnung", "stopp", "limit"):
            self.assertIn("phase_" + p, sprache.TEXTE)

    def test_app_ruft_nur_erlaubte_befehle(self):
        """Die App startet nur /usr/bin/python3 waechter.py – nie ein Terminal, nie claude/codex."""
        quelltext = _swift()
        self.assertEqual(quelltext.count("Process()"), 1)
        self.assertIn('static let python = "/usr/bin/python3"', quelltext)
        erlaubt = {"status", "app-texte", "pause", "nacht", "wach", "schwellen", "report"}
        erste = set(re.findall(r'(?:befehl|ausfuehren)\(\[\s*"([a-z-]+)"', quelltext))
        self.assertTrue(erste)
        self.assertLessEqual(erste, erlaubt)


class DemoFixtureTest(unittest.TestCase):
    def setUp(self):
        self.alt = lies_fixture_json(os.path.join("app", "status_v13.json"))
        self.neu = lies_fixture_json(os.path.join("app", "status.json"))

    def test_obermenge_des_alten_vertrags(self):
        self.assertLessEqual(set(self.alt), set(self.neu))
        for a in ("claude", "codex"):
            self.assertLessEqual(set(self.alt["phasen"][a]), set(self.neu["phasen"][a]))

    def test_neue_felder(self):
        n = self.neu
        self.assertEqual(set(n["gesamt"]), {"stufe", "text", "detail"})
        self.assertEqual(set(n["wach"]), {"an", "art", "modus", "bis", "sperre", "zugeklappt_ok", "netzteil",
                                          "amphetamine", "text"})
        for a in ("claude", "codex"):
            self.assertEqual(set(n["offiziell"][a]), {"zustand", "fehler", "stand"})
            self.assertIn("quelle_text", n["phasen"][a])
            self.assertIn("woche_modell", n["phasen"][a])
        self.assertEqual(n["phasen"]["claude"]["quelle"], "offiziell")
        self.assertEqual(n["phasen"]["claude"]["pct5"], 84.0)
        self.assertEqual(n["phasen"]["codex"]["pct5"], 35.0)
        lagen = set()
        for s in n["sitzungen"]:
            for f in ("lage", "lage_text", "lage_farbe", "aktivitaet"):
                self.assertIn(f, s)
            lagen.add(s["lage"])
        self.assertLessEqual({"arbeitet", "wartet", "weiter_noetig", "blockiert"}, lagen)


class AppSelbsttestV14Test(unittest.TestCase):
    """Nur wenn eine aktuelle App gebaut ist (app/build.sh oder LIMIT_WAECHTER_APP)."""

    def test_selbsttest_beide_fixtures(self):
        app = os.environ.get("LIMIT_WAECHTER_APP") or os.path.join(
            PROJEKT, "app", "build", "Limit-Waechter.app", "Contents", "MacOS", "LimitWaechter")
        if not os.path.exists(app):
            self.skipTest("App nicht gebaut (app/build.sh)")
        v = subprocess.run([app, "--version"], capture_output=True, text=True, timeout=30).stdout.split()
        if not v or v[-1] != VERSION:
            self.skipTest("App-Build passt nicht zur Version")
        fx = os.path.join(PROJEKT, "tests", "fixtures", "app")
        r = subprocess.run([app, "--selbsttest", os.path.join(fx, "status.json")],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gesamt=warnung", r.stdout)
        self.assertIn("quelle claude=offiziell codex=rollout", r.stdout)
        self.assertIn("wach=amphetamine/automatisch", r.stdout)
        self.assertIn("lagen=blockiert,weiter_noetig,wartet,arbeitet", r.stdout)
        r = subprocess.run([app, "--selbsttest", os.path.join(fx, "status_v13.json")],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gesamt=", r.stdout)
