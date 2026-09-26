import unittest

from hilfe import TempHome, bildschirm, nutzung

from lw import bildschirm as bs
from lw import phasen


class PhasenTest(TempHome):
    def ph(self, daten, hinweise=None):
        return phasen.berechne("claude", daten, hinweise or [], self.k, self.now)

    def test_schwellen(self):
        r = self.now + 3600
        self.assertEqual(self.ph(nutzung(79.9, r))["phase"], "ok")
        self.assertEqual(self.ph(nutzung(80, r))["phase"], "warnung")
        self.assertEqual(self.ph(nutzung(92, r))["phase"], "stopp")
        p = self.ph(nutzung(100, r))
        self.assertEqual((p["phase"], p["art"], p["reset"]), ("limit", "fuenf", r))

    def test_woche_und_reserve(self):
        r = self.now + 3600
        p = self.ph(nutzung(10, r, pw=85))
        self.assertEqual((p["phase"], p["art"]), ("warnung", "woche"))
        self.assertTrue(p["reserve_erreicht"])
        self.assertFalse(self.ph(nutzung(10, r, pw=79))["reserve_erreicht"])
        p = self.ph(nutzung(50, r, pw=93))
        self.assertEqual((p["phase"], p["art"]), ("stopp", "woche"))

    def test_hoechste_stufe_gewinnt(self):
        r = self.now + 3600
        p = self.ph(nutzung(93, r, pw=85))
        self.assertEqual((p["phase"], p["art"]), ("stopp", "fuenf"))

    def test_abgelaufenes_fenster_ist_reset(self):
        p = self.ph(nutzung(100, self.now - 1, pw=40, resetw=self.now + 86400))
        self.assertEqual((p["phase"], p["pct5"]), ("ok", 0.0))

    def test_limit_hinweis_aus_register(self):
        r = self.now + 1800
        p = self.ph(nutzung(88, r), [{"art": "fuenf", "reset": r}])
        self.assertEqual(p["phase"], "limit")
        self.assertEqual(self.ph(nutzung(88, r), [{"art": "fuenf", "reset": self.now - 5}])["phase"], "warnung")

    def test_keine_daten(self):
        p = self.ph(None)
        self.assertEqual(p["phase"], "ok")
        self.assertFalse(p["hat_daten"])
        self.assertTrue(p["veraltet"])

    def test_fenster_id_stabil_bei_sekundenabweichung(self):
        a = phasen.fenster_id("codex", "woche", 1790935478)
        b = phasen.fenster_id("codex", "woche", 1790935477)
        self.assertEqual(a, b)

    def test_quelle_waehlen(self):
        alt = dict(nutzung(10, self.now + 10), stand=self.now - 900)
        neu = dict(nutzung(20, self.now + 10), stand=self.now - 60)
        self.assertIs(phasen.waehle_quelle(alt, neu), neu)
        self.assertIs(phasen.waehle_quelle(None, alt), alt)
        self.assertIsNone(phasen.waehle_quelle(None, {"fuenf": None, "woche": None}))


class BildschirmTest(unittest.TestCase):
    FAELLE = [
        ("claude_bereit.txt", "claude", "bereit"),
        ("claude_verlauf_mit_credits.txt", "claude", "bereit"),
        ("claude_arbeitet.txt", "claude", "beschaeftigt"),
        ("claude_limit_menue.txt", "claude", "menue"),
        ("claude_countdown.txt", "claude", "menue"),
        ("claude_stale.txt", "claude", "stale"),
        ("claude_eingabe_belegt.txt", "claude", "eingabe_belegt"),
        ("claude_upgrade_hinweis.txt", "claude", "geld"),
        ("claude_resume_dialog.txt", "claude", "menue"),
        ("codex_bereit.txt", "codex", "bereit"),
        ("codex_limit.txt", "codex", "bereit"),
        ("codex_arbeitet.txt", "codex", "beschaeftigt"),
        ("codex_menue.txt", "codex", "menue"),
        ("leer.txt", "claude", "unbekannt"),
        # aus echten Terminals (26.09.2026, Claude 2.1.283)
        ("claude_arbeitet_2_1_283.txt", "claude", "beschaeftigt"),
        ("claude_workflow_ansicht.txt", "claude", "menue"),
        ("claude_deutsch_kaufen.txt", "claude", "bereit"),
    ]

    def test_faelle(self):
        for datei, anbieter, erwartet in self.FAELLE:
            with self.subTest(datei=datei):
                art, grund = bs.klassifiziere(bildschirm(datei), anbieter)
                self.assertEqual(art, erwartet, f"{datei}: {grund}")

    def test_kaufwort_unten_blockiert(self):
        zeilen = bildschirm("claude_bereit.txt")
        zeilen.insert(-3, "  Add funds to continue with extra usage")
        self.assertIn(bs.klassifiziere(zeilen, "claude")[0], ("geld", "menue"))

    def test_nur_prompt_ohne_linien(self):
        self.assertEqual(bs.klassifiziere(["irgendwas", "❯ "], "claude")[0], "bereit")
        self.assertEqual(bs.klassifiziere(["kein prompt hier"], "claude")[0], "unbekannt")


if __name__ == "__main__":
    unittest.main()
