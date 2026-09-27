"""Tick mit Orca-Attrappe und Probedaten: Meldungen, Codex-Stopp, Fortsetzen, Schutzregeln."""

import os
import shutil
import time
import unittest

from hilfe import TempHome, bildschirm, fixture, nutzung

from lw import melden, register, simulation, tick, util
from lw.attrappe import OrcaAttrappe
from lw.kontext import Kontext

MAC_OK = {"netzteil": True, "wach_bei_deckel_zu": True, "schlaf_aus": True}


class TickTest(TempHome):
    def setUp(self):
        super().setUp()
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = False     # v1.0-Verhalten; Nachtmodus: test_nacht.py
        self.reset = self.now + 3600
        self.orca = OrcaAttrappe(
            terminals=[{"handle": "term_A", "agentIdentity": "claude", "tabId": "tA", "leafId": "lA",
                        "worktreePath": self.home},
                       {"handle": "term_S", "agentIdentity": None, "tabId": "tS", "leafId": "lS"}],
            agenten={"tA:lA": {"state": "done"}},
            bildschirme={"term_A": bildschirm("claude_bereit.txt")})

    def lauf(self, claude, codex=None, claude_agenten=None, mac=None):
        melder = melden.Melder(self.k, dry_run=True)
        ctx = Kontext(self.k, self.orca, melder, self.now, dry_run=True, claude_agenten=claude_agenten or [])
        sim = {"claude": claude, "codex": codex or nutzung(5, self.now + 7200, stand=self.now)}
        return tick.ausfuehren(ctx, sim=sim, mac_sim=mac or MAC_OK)

    def sitzung_anlegen(self, sid="sess-A", status="gestoppt", reset=None, **extra):
        reset = reset or self.reset

        def f(d):
            d.update({"cwd": self.home, "terminal": "term_A", "pane_key": "tA:lA"})
            register.warten_auf_reset(d, status, f"claude-fuenf-{int(round(reset / 600))}", reset, "fuenf", 120)
            d.update(extra)
        register.aktualisieren("claude", sid, f)

    def texte(self, erg):
        return [m["text"] for m in erg["meldungen"]]

    # ------------------------------------------------------------ Meldungen
    def test_meldungen_je_fenster_nur_einmal(self):
        erg = self.lauf(nutzung(82, self.reset, stand=self.now))
        self.assertEqual(len(erg["meldungen"]), 1)
        self.assertIn("Warnschwelle", erg["meldungen"][0]["text"])
        self.assertEqual(self.lauf(nutzung(83, self.reset, stand=self.now))["meldungen"], [])
        erg = self.lauf(nutzung(93, self.reset, stand=self.now))
        self.assertIn("Stopp-Schwelle", self.texte(erg)[0])
        self.assertEqual(erg["meldungen"][0]["prio"], 4)
        cur = util.lies_json(util.pfad("state", "current.json"))
        self.assertEqual(cur["claude"]["phase"], "stopp")

    def test_keine_projektinhalte_in_pushes(self):
        self.sitzung_anlegen(status="gestoppt")
        erg = self.lauf(nutzung(100, self.reset, stand=self.now))
        for t in self.texte(erg):
            self.assertNotIn(self.home, t)
            self.assertNotIn("sess-A", t)

    def test_reserve_meldung(self):
        erg = self.lauf(nutzung(10, self.reset, pw=85, stand=self.now))
        t = self.texte(erg)
        self.assertEqual(len(t), 1, t)
        self.assertIn("Wochenreserve", t[0])

    def test_pause_macht_nichts(self):
        util.schreib_json(util.pfad("state", "pause.json"), {"aktiv": True, "bis": None})
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 600)
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])
        self.assertTrue(erg["pausiert"])
        self.assertTrue(util.lies_json(util.pfad("state", "current.json"))["pausiert"])

    # ------------------------------------------------------------ Fortsetzen
    def test_fortsetzen_bereit(self):
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 180)
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(len(self.orca.gesendet), 1)
        self.assertTrue(self.orca.gesendet[0]["text"].startswith("Limit-Wächter: Das Nutzungslimit ist zurückgesetzt"))
        s = register.lesen("claude", "sess-A")
        self.assertEqual(s["status"], "fortgesetzt")
        self.assertEqual(register.versuche(s, s["fenster_id"]), 1)
        self.assertTrue(any("fortgesetzt" in t for t in self.texte(erg)))

    def test_nicht_vor_reset_plus_puffer(self):
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 60)      # Puffer 120 s noch nicht vorbei
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])

    def test_kaufmenue_nichts_senden(self):
        self.orca.bildschirme["term_A"] = bildschirm("claude_limit_menue.txt")
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 180)
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "blockiert")
        self.assertTrue(any("nichts gesendet" in t.lower() for t in self.texte(erg)))

    def test_arbeitet_schon(self):
        self.orca._agenten["tA:lA"] = {"state": "working"}
        # v1.4: Orcas "working" allein genügt nicht mehr; der Bildschirm muss es bestätigen
        self.orca.bildschirme["term_A"] = bildschirm("claude_arbeitet.txt")
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 180)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "fortgesetzt")

    def test_stale_nur_enter(self):
        self.orca.bildschirme["term_A"] = bildschirm("claude_stale.txt")
        self.sitzung_anlegen(status="stale", reset=self.now - 1800)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [{"handle": "term_A", "text": None, "enter": True}])

    def test_claude_limit_karenz_fuer_eingebaute_fortsetzung(self):
        self.sitzung_anlegen(status="limit", reset=self.now - 180)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [], "erst nach 5 min Karenz")
        self.setze_zeit(self.now + 180)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(len(self.orca.gesendet), 1)

    def test_eingebaut_wartet_erst_nach_langer_karenz(self):
        self.sitzung_anlegen(status="eingebaut_wartet", reset=self.now - 600)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [], "10 min nach Reset: Claudes eingebautes Warten hat Vorrang")
        self.setze_zeit(self.now + 360)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(len(self.orca.gesendet), 1, "nach Reset + 15 min übernimmt der Wächter")

    def test_geschuetzte_ordner_nicht_selbst_pruefen(self):
        from lw import fortsetzen
        self.assertTrue(fortsetzen.ordner_ok(os.path.expanduser("~/Documents/gibt-es/vielleicht")))
        self.assertTrue(fortsetzen.ordner_ok(os.path.expanduser("~/Library/CloudStorage/x")))
        self.assertFalse(fortsetzen.ordner_ok(os.path.join(self.home, "gibt-es-nicht")))
        self.assertFalse(fortsetzen.ordner_ok(None))

    def test_orca_modus_ueberlaesst_limit(self):
        self.k["fortsetzen"]["claude_limit_resume"] = "orca"
        self.sitzung_anlegen(status="limit", reset=self.now - 900)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])
        self.sitzung_anlegen(sid="sess-G", status="gestoppt", reset=self.now - 900)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(len(self.orca.gesendet), 1, "geordnet gestoppte Sitzungen setzt der Wächter weiter fort")

    def test_reserve_keine_fortsetzung(self):
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 180, reserve_bei_halt=True)
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "reserve")
        self.assertTrue(any("Wochenreserve" in t for t in self.texte(erg)))

    def test_hoechstens_zwei_versuche(self):
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 180)
        for _ in range(3):
            s = register.lesen("claude", "sess-A")
            register.aktualisieren("claude", "sess-A", lambda d: d.update(status="gestoppt"))
            self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(len(self.orca.gesendet), 2)
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "aufgegeben")
        del s

    def test_noch_im_limit_keine_fortsetzung(self):
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 180)
        self.lauf(nutzung(10, self.now + 5 * 3600, pw=100, resetw=self.now + 86400, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])

    def test_terminal_fehlt_neustart(self):
        self.orca._terminals = []
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 180, worktree_id="repo::" + self.home)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(len(self.orca.gesendet), 1)
        g = self.orca.gesendet[0]
        self.assertEqual(g["erstellen"], "id:repo::" + self.home)
        self.assertIn("--resume sess-A", g["befehl"])
        self.assertIn("--permission-mode auto", g["befehl"])
        self.assertTrue(g["befehl"].startswith("cd "))
        self.assertNotIn("dangerously", g["befehl"])

    def test_terminal_fehlt_aber_sitzung_laeuft_woanders(self):
        self.orca._terminals = []
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 180)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now),
                  claude_agenten=[{"sessionId": "sess-A", "pid": 1, "status": "idle"}])
        self.assertEqual(self.orca.gesendet, [])
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "blockiert")

    def test_nur_agent_terminals(self):
        # Sitzung verweist auf ein Terminal ohne agentIdentity -> wird nicht beschrieben
        self.orca._terminals = [{"handle": "term_S", "agentIdentity": None, "tabId": "tS", "leafId": "lS"}]
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 180)
        register.aktualisieren("claude", "sess-A", lambda d: d.update(terminal="term_S", pane_key="tS:lS"))
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now), claude_agenten=[])
        self.assertTrue(all(g.get("handle") != "term_S" for g in self.orca.gesendet))

    def test_pruefung_nach_fortsetzung_meldet_haenger(self):
        self.sitzung_anlegen(status="gestoppt", reset=self.now - 180)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.orca.bildschirme["term_A"] = bildschirm("claude_resume_dialog.txt")
        self.setze_zeit(self.now + 180)
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertTrue(any("wartet auf eine Eingabe" in t for t in self.texte(erg)))

    def test_orca_weg_meldet(self):
        self.orca._erreichbar = False
        self.sitzung_anlegen(status="gestoppt", reset=self.now + 600)
        melder = melden.Melder(self.k, dry_run=True)
        ctx = Kontext(self.k, self.orca, melder, self.now, dry_run=True, claude_agenten=[])
        erg = tick.ausfuehren(ctx, sim={"claude": nutzung(50, self.now + 600, stand=self.now), "orca_ok": False,
                                        "fehler": ["weg"]}, mac_sim=MAC_OK)
        self.assertTrue(any("Orca nicht erreichbar" in t for t in self.texte(erg)))

    # ------------------------------------------------------------ Codex
    def _codex_setup(self, limit=False):
        tag = os.path.join(self.k["daten"]["codex_sessions"], time.strftime("%Y/%m/%d", time.localtime(self.now)))
        os.makedirs(tag, exist_ok=True)
        name = "rollout-2026-09-20T17-25-00-01a0bf6b-ae1f-7de0-8b05-aa0baa8a6479.jsonl"
        ziel = os.path.join(tag, name)
        if limit:
            shutil.copy(fixture(name), ziel)
        else:
            with open(fixture(name)) as f:
                zeilen = f.read().splitlines()[:3]     # läuft noch, kein Limit
            with open(ziel, "w") as f:
                f.write("\n".join(zeilen) + "\n")
        shutil.copy(fixture("orca_last_status.json"), self.k["daten"]["orca_hook_status"])
        self.orca._terminals.append({"handle": "term_X", "agentIdentity": "codex", "tabId": "tab2", "leafId": "leaf2",
                                     "worktreePath": "/tmp/projekt"})
        self.orca._agenten["tab2:leaf2"] = {"state": "working"}
        self.orca.bildschirme["term_X"] = bildschirm("codex_arbeitet.txt")
        return ziel

    def test_codex_stopp_steuernachricht_einmal(self):
        self._codex_setup()
        self.lauf(nutzung(10, self.reset, stand=self.now), codex=nutzung(93, self.reset, stand=self.now))
        self.lauf(nutzung(10, self.reset, stand=self.now), codex=nutzung(94, self.reset, stand=self.now))
        an_x = [g for g in self.orca.gesendet if g.get("handle") == "term_X"]
        self.assertEqual(len(an_x), 1)
        self.assertIn("Codex-Nutzungslimit ist fast erreicht", an_x[0]["text"])
        s = register.lesen("codex", "01a0bf6b-ae1f-7de0-8b05-aa0baa8a6479")
        self.assertEqual(s["status"], "gestoppt")
        self.assertEqual(s["fortsetzen_ab"], self.reset + 120)

    def test_codex_stopp_text_je_nach_nachtmodus(self):
        from lw import nacht
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = True
        self._codex_setup()
        self.lauf(nutzung(10, self.reset, stand=self.now), codex=nutzung(93, self.reset, stand=self.now))
        an_x = [g for g in self.orca.gesendet if g.get("handle") == "term_X"]
        self.assertEqual(len(an_x), 1)
        self.assertIn("„weiter“", an_x[0]["text"])
        self.assertNotIn("automatisch fort", an_x[0]["text"])

    def test_codex_stopp_text_mit_nachtmodus(self):
        from lw import nacht
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = True
        nacht.alle_an(self.now)
        self._codex_setup()
        self.lauf(nutzung(10, self.reset, stand=self.now), codex=nutzung(93, self.reset, stand=self.now))
        an_x = [g for g in self.orca.gesendet if g.get("handle") == "term_X"]
        self.assertEqual(len(an_x), 1)
        self.assertIn("automatisch fort", an_x[0]["text"])

    def test_codex_stopp_nicht_bei_menue(self):
        self._codex_setup()
        self.orca.bildschirme["term_X"] = bildschirm("codex_menue.txt")
        self.lauf(nutzung(10, self.reset, stand=self.now), codex=nutzung(93, self.reset, stand=self.now))
        self.assertEqual([g for g in self.orca.gesendet if g.get("handle") == "term_X"], [])

    def test_codex_limit_aus_rollout_und_fortsetzen(self):
        self.setze_zeit(1789924214 - 600)        # 10 min vor dem Reset aus der Limitmeldung
        self._codex_setup(limit=True)
        self.orca._agenten["tab2:leaf2"] = {"state": "done"}
        self.orca.bildschirme["term_X"] = bildschirm("codex_limit.txt")
        erg = self.lauf(nutzung(10, self.now + 7200, stand=self.now), codex=None)
        s = register.lesen("codex", "01a0bf6b-ae1f-7de0-8b05-aa0baa8a6479")
        self.assertEqual((s["status"], s["reset"]), ("limit", 1789924214))
        self.assertEqual(erg["phasen"]["codex"]["phase"], "limit")
        self.setze_zeit(1789924214 + 150)
        self.lauf(nutzung(10, self.now + 7200, stand=self.now), codex=nutzung(0, self.now + 5 * 3600, stand=self.now))
        an_x = [g for g in self.orca.gesendet if g.get("handle") == "term_X"]
        self.assertEqual(len(an_x), 1)
        self.assertTrue(an_x[0]["text"].startswith("Limit-Wächter: Das Nutzungslimit ist zurückgesetzt"))

    def test_codex_credits_warnung(self):
        melder = melden.Melder(self.k, dry_run=True)
        for wert in (120.0, 120.0, 98.5):
            ctx = Kontext(self.k, self.orca, melder, self.now, dry_run=True, claude_agenten=[])
            tick.ausfuehren(ctx, sim={"claude": nutzung(5, self.reset, stand=self.now), "codex_credits": wert},
                            mac_sim=MAC_OK)
        t = [m["text"] for m in melder.protokoll]
        self.assertEqual(len([x for x in t if "Guthaben gesunken" in x]), 1)

    # ------------------------------------------------------------ Wach / Remote / Bericht
    def test_caffeinate_und_remote_hinweis_nachts(self):
        nacht = time.mktime((2026, 9, 26, 23, 0, 0, 0, 0, -1))
        self.setze_zeit(nacht)
        self.sitzung_anlegen(status="gestoppt", reset=nacht + 3600)
        erg = self.lauf(nutzung(50, nacht + 3600, stand=nacht), mac={"netzteil": True, "wach_bei_deckel_zu": False})
        self.assertTrue(any("caffeinate" in a for a in erg["aktionen"]))
        self.assertTrue(any("Remote-Modus" in t for t in self.texte(erg)))
        erg = self.lauf(nutzung(50, nacht + 3600, stand=nacht), mac={"netzteil": True, "wach_bei_deckel_zu": False})
        self.assertFalse(any("Remote-Modus" in t for t in self.texte(erg)), "nur einmal pro Nacht")

    def test_morgenbericht_einmal(self):
        abend = time.mktime((2026, 9, 26, 22, 0, 0, 0, 0, -1))
        self.setze_zeit(abend)
        self.lauf(nutzung(5, abend + 3600, stand=abend))
        util.ereignis("fortgesetzt", anbieter="claude", sitzung="x", cwd="/tmp/p", weg="Fortsetzungsprompt")
        morgen = time.mktime((2026, 9, 27, 8, 5, 0, 0, 0, -1))
        self.setze_zeit(morgen)
        erg = self.lauf(nutzung(5, morgen + 3600, stand=morgen))
        self.assertTrue(any(t.startswith("Morgenbericht") for t in self.texte(erg)))
        self.assertTrue(os.path.exists(util.pfad("berichte", "2026-09-27.md")))
        self.setze_zeit(morgen + 600)
        erg = self.lauf(nutzung(5, morgen + 3600, stand=morgen))
        self.assertFalse(any(t.startswith("Morgenbericht") for t in self.texte(erg)))


class ZyklusTest(TempHome):
    def test_kompletter_zyklus(self):
        erg = simulation.zyklus(ausgabe=False)
        titel = {e["schritt"]: e for e in erg}
        self.assertEqual(titel["s3"]["phasen"]["claude"]["phase"], "stopp")
        h = titel["hooks"]["hooks"]
        self.assertEqual(h["deny"]["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(h["block"]["decision"], "block")
        self.assertIsNone(h["frei"])
        ende = titel["endzustand"]
        self.assertEqual(ende["sitzungen"]["session-A"], "fortgesetzt")
        self.assertEqual(ende["sitzungen"]["session-B"], "blockiert")
        self.assertEqual(ende["sitzungen"]["01a0ffff-0000-7000-8000-00000000c0de"], "fortgesetzt")
        gesendet = [g.get("handle") for g in ende["gesendet"]]
        self.assertNotIn("term_B", gesendet, "Kaufmenü: nie etwas senden")
        self.assertNotIn("term_Z", gesendet, "nur Agent-Terminals")
        # C ohne Nachtmodus: nichts gesendet, wartet auf "weiter", genau ein Push dazu
        self.assertEqual(ende["sitzungen"]["session-C"], "wartet_auf_weiter")
        self.assertNotIn("term_C", gesendet)
        weiter = [m for e in erg if "meldungen" in e for m in e["meldungen"] if "„weiter“" in m["text"] or '"continue"' in m["text"]]
        self.assertEqual(len(weiter), 1)
        self.assertEqual(titel["nacht"]["hook"]["decision"], "block")


class MelderTest(TempHome):
    def test_dry_run_sendet_nichts(self):
        import urllib.request
        original = urllib.request.urlopen
        aufrufe = []
        urllib.request.urlopen = lambda *a, **kw: aufrufe.append(a)
        try:
            m = melden.Melder(self.k, dry_run=True)
            self.assertTrue(m.senden("x", schluessel="k1"))
            self.assertFalse(m.senden("x", schluessel="k1"))
        finally:
            urllib.request.urlopen = original
        self.assertEqual(aufrufe, [])


if __name__ == "__main__":
    unittest.main()
