"""Nachtmodus (v1.1): Dauer, CLI, Tick nur mit Nachtmodus fortsetzen, Push "warten auf weiter", Wachhalten."""

import contextlib
import io
import os
import subprocess
import time
import unittest
from unittest import mock

from hilfe import TempHome, bildschirm, nutzung

from lw import bericht, cli, melden, nacht, register, tick, util
from lw.attrappe import OrcaAttrappe
from lw.kontext import Kontext

MAC_OK = {"netzteil": True, "wach_bei_deckel_zu": True, "schlaf_aus": True}


def zeit(tag, h, m=0):
    return time.mktime((2026, 9, tag, h, m, 0, 0, 0, -1))


class EndeTest(TempHome):
    def test_abends_bis_naechsten_morgen(self):
        self.assertEqual(nacht.ende(zeit(26, 23)), zeit(27, 8))

    def test_nach_mitternacht_bis_heute_morgen(self):
        self.assertEqual(nacht.ende(zeit(27, 1, 30)), zeit(27, 8))

    def test_nach_acht_bis_morgen(self):
        self.assertEqual(nacht.ende(zeit(26, 8, 0)), zeit(27, 8))
        self.assertEqual(nacht.ende(zeit(26, 9), "07:30"), zeit(27, 7, 30))

    def test_sommerzeit_umstellung(self):
        """Abend vor der Umstellung auf Sommerzeit (Tag mit 23 h): Ende am nächsten Morgen, nicht übermorgen."""
        code = ("import time, sys; sys.path.insert(0, '..'); from lw import nacht; "
                "n = time.mktime((2026, 3, 28, 23, 30, 0, 0, 0, -1)); "
                "print(time.strftime('%Y-%m-%d %H:%M', time.localtime(nacht.ende(n))))")
        env = dict(os.environ, TZ="Europe/Berlin")
        r = subprocess.run(["/usr/bin/python3", "-c", code], capture_output=True, text=True, env=env,
                           cwd=os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(r.stdout.strip(), "2026-03-29 08:00", r.stderr)

    def test_ablauf_um_acht(self):
        nacht.sitzung_an("claude", "s1", zeit(26, 23))
        s = register.lesen("claude", "s1")
        self.assertTrue(nacht.aktiv(s, zeit(27, 7, 59)))
        self.assertFalse(nacht.aktiv(s, zeit(27, 8)))
        nacht.alle_an(zeit(26, 23))
        self.assertTrue(nacht.aktiv({}, zeit(27, 7)))
        self.assertFalse(nacht.aktiv({}, zeit(27, 8, 1)))


class CliTest(TempHome):
    def setUp(self):
        super().setUp()
        self.setze_zeit(zeit(26, 23))
        for sid, cwd in (("abcd1111-x", "/p/alpha"), ("abcd2222-y", "/p/beta"), ("ffff0000-z", "/p/beta")):
            register.aktualisieren("claude", sid, lambda d, cwd=cwd: d.update(cwd=cwd))

    def cli(self, *args):
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            code = cli.main(list(args))
        return code, puffer.getvalue()

    def test_an_alle_und_aus(self):
        code, out = self.cli("nacht", "an")
        self.assertEqual(code, 0)
        self.assertIn("all sessions", out)      # cli.main lädt die Konfiguration: Englisch
        self.assertEqual(nacht.global_bis(self.now), zeit(27, 8))
        self.cli("nacht", "an", "abcd1111")
        code, out = self.cli("night", "off")
        self.assertEqual(code, 0)
        self.assertIsNone(nacht.global_bis(self.now))
        self.assertIsNone(register.lesen("claude", "abcd1111-x")["nacht_bis"])

    def test_an_ziel_id_und_projekt(self):
        code, out = self.cli("nacht", "an", "abcd1111")
        self.assertEqual(code, 0)
        self.assertEqual(register.lesen("claude", "abcd1111-x")["nacht_bis"], zeit(27, 8))
        self.assertIsNone(nacht.global_bis(self.now))
        code, _ = self.cli("nacht", "on", "alpha")
        self.assertEqual(code, 0)
        code, _ = self.cli("nacht", "aus", "abcd1111")
        self.assertEqual(code, 0)
        self.assertIsNone(register.lesen("claude", "abcd1111-x")["nacht_bis"])

    def test_mehrdeutig_und_kein_treffer(self):
        code, out = self.cli("nacht", "an", "abcd")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", out)
        self.assertIn("abcd1111", out)
        self.assertIn("abcd2222", out)
        code, out = self.cli("nacht", "an", "beta")
        self.assertEqual(code, 2)
        code, out = self.cli("nacht", "an", "gibtsnicht")
        self.assertEqual(code, 2)
        self.assertIn("No session", out)
        self.assertIn("ffff0000", out)
        self.assertIsNone(register.lesen("claude", "abcd1111-x").get("nacht_bis"))

    def test_unbekannte_aktion(self):
        code, _ = self.cli("nacht", "xyz")
        self.assertEqual(code, 2)

    def test_aus_sitzung_bei_globalem_modus(self):
        self.cli("nacht", "an", "alle")
        code, out = self.cli("nacht", "aus", "abcd1111")
        self.assertEqual(code, 0)
        self.assertIn("still on", out)

    def test_an_hinweis_schon_wartend(self):
        register.aktualisieren("claude", "abcd1111-x", lambda d: d.update(status="wartet_auf_weiter"))
        code, out = self.cli("nacht", "an", "alle")
        self.assertIn("already wait", out)
        self.assertIn("abcd1111", out)
        code, out = self.cli("nacht", "an", "beta")
        self.assertNotIn("already wait", out)

    def test_status(self):
        self.cli("nacht", "an", "alpha")
        code, out = self.cli("nacht")
        self.assertEqual(code, 0)
        self.assertIn("abcd1111", out)
        self.assertNotIn("abcd2222", out)


class TickNachtTest(TempHome):
    def setUp(self):
        super().setUp()
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = True
        self.orca = OrcaAttrappe(
            terminals=[{"handle": "term_A", "agentIdentity": "claude", "tabId": "tA", "leafId": "lA",
                        "worktreePath": self.home},
                       {"handle": "term_B", "agentIdentity": "claude", "tabId": "tB", "leafId": "lB",
                        "worktreePath": self.home}],
            agenten={"tA:lA": {"state": "done"}, "tB:lB": {"state": "done"}},
            bildschirme={"term_A": bildschirm("claude_bereit.txt"), "term_B": bildschirm("claude_bereit.txt")})

    def lauf(self, claude, mac=None):
        melder = melden.Melder(self.k, dry_run=True)
        ctx = Kontext(self.k, self.orca, melder, self.now, dry_run=True, claude_agenten=[])
        sim = {"claude": claude, "codex": nutzung(5, self.now + 7200, stand=self.now)}
        return tick.ausfuehren(ctx, sim=sim, mac_sim=mac or MAC_OK)

    def anlegen(self, sid, reset, term="term_A", pane="tA:lA", status="gestoppt"):
        def f(d):
            d.update({"cwd": self.home, "terminal": term, "pane_key": pane})
            register.warten_auf_reset(d, status, f"claude-fuenf-{int(round(reset / 600))}", reset, "fuenf", 120)
        register.aktualisieren("claude", sid, f)

    def weiter_pushes(self, erg):
        return [m for m in erg["meldungen"] if "„weiter“" in m["text"]]

    def test_ohne_nachtmodus_nichts_gesendet_ein_push(self):
        self.anlegen("sess-A", self.now - 300)
        self.anlegen("sess-B", self.now - 300, "term_B", "tB:lB")
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "wartet_auf_weiter")
        p = self.weiter_pushes(erg)
        self.assertEqual(len(p), 1)
        self.assertIn("2 Sitzung(en)", p[0]["text"])
        self.assertTrue(register.lesen("claude", "sess-B")["weiter_gemeldet"])
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.weiter_pushes(erg), [])
        self.assertEqual(self.orca.gesendet, [])

    def test_push_wartet_auf_gleich_faellige(self):
        self.anlegen("sess-A", self.now - 300)
        self.anlegen("sess-B", self.now - 60, "term_B", "tB:lB")      # fortsetzen_ab in 60 s
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.weiter_pushes(erg), [])
        self.setze_zeit(self.now + 120)
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(len(self.weiter_pushes(erg)), 1)
        self.assertIn("2 Sitzung(en)", self.weiter_pushes(erg)[0]["text"])

    def test_mit_nachtmodus_fortgesetzt(self):
        self.anlegen("sess-A", self.now - 300)
        nacht.sitzung_an("claude", "sess-A", self.now)
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(len(self.orca.gesendet), 1)
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "fortgesetzt")
        self.assertEqual(self.weiter_pushes(erg), [])

    def test_nachtmodus_nach_reset_holt_nach(self):
        self.anlegen("sess-A", self.now - 300)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "wartet_auf_weiter")
        self.setze_zeit(self.now + 3600)                              # eine Stunde später: nacht an alle
        nacht.alle_an(self.now)
        self.lauf(nutzung(5, self.now + 4 * 3600, stand=self.now))
        self.assertEqual(len(self.orca.gesendet), 1)
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "fortgesetzt")

    def test_nachtmodus_holt_alte_sitzung_nicht_nach(self):
        self.anlegen("sess-A", self.now - 300)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.setze_zeit(self.now + 13 * 3600)                         # älter als max_stunden_voraus
        nacht.alle_an(self.now)
        self.lauf(nutzung(5, self.now + 4 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "wartet_auf_weiter")

    def test_globaler_nachtmodus(self):
        self.anlegen("sess-A", self.now - 300)
        nacht.alle_an(self.now)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "fortgesetzt")

    def test_nachtmodus_abgelaufen(self):
        self.anlegen("sess-A", self.now - 300)
        nacht.sitzung_an("claude", "sess-A", self.now - 86400)    # gestern an, heute 08:00 abgelaufen
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "wartet_auf_weiter")

    def test_schalter_aus_altes_verhalten(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = False
        self.anlegen("sess-A", self.now - 300)
        self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(len(self.orca.gesendet), 1)
        self.assertFalse(util.lies_json(util.pfad("state", "current.json"))["nur_nacht"])

    def test_kein_doppelter_reset_push(self):
        reset = self.now + 600
        self.anlegen("sess-A", reset)
        self.lauf(nutzung(100, reset, stand=self.now))
        self.setze_zeit(reset + 300)
        erg = self.lauf(nutzung(1, self.now + 5 * 3600, stand=self.now))
        texte = [m["text"] for m in erg["meldungen"]]
        self.assertEqual(len(self.weiter_pushes(erg)), 1, texte)
        self.assertFalse(any(t == "Claude: Limit zurückgesetzt." for t in texte), texte)

    def test_kein_doppelter_reset_push_wenn_hook_schon_gesetzt(self):
        reset = self.now + 600
        self.anlegen("sess-A", reset, status="limit")
        self.lauf(nutzung(100, reset, stand=self.now))
        register.aktualisieren("claude", "sess-A", lambda d: d.update(status="wartet_auf_weiter",
                                                                      weiter_gemeldet=False))
        self.setze_zeit(reset + 300)
        erg = self.lauf(nutzung(1, self.now + 5 * 3600, stand=self.now))
        texte = [m["text"] for m in erg["meldungen"]]
        self.assertEqual(len(self.weiter_pushes(erg)), 1, texte)
        self.assertFalse(any(t == "Claude: Limit zurückgesetzt." for t in texte), texte)

    def test_alte_gemeldete_sitzung_sperrt_reset_push_nicht(self):
        register.aktualisieren("claude", "alt", lambda d: d.update(status="wartet_auf_weiter", weiter_gemeldet=True,
                                                                  cwd=self.home))
        reset = self.now + 600
        self.lauf(nutzung(100, reset, stand=self.now))
        self.setze_zeit(reset + 300)
        erg = self.lauf(nutzung(1, self.now + 5 * 3600, stand=self.now))
        texte = [m["text"] for m in erg["meldungen"]]
        self.assertIn("Claude: Limit zurückgesetzt.", texte)

    def test_limit_push_zaehlt_nur_automatisch_fortgesetzte(self):
        reset = self.now + 600
        self.anlegen("sess-A", reset)
        self.anlegen("sess-B", reset, "term_B", "tB:lB")
        erg = self.lauf(nutzung(100, reset, stand=self.now), mac={"netzteil": False})
        limit = [m["text"] for m in erg["meldungen"] if "Limit" in m["text"]]
        self.assertTrue(limit)
        self.assertFalse(any("2 " in x or "Netzteil" in x for x in limit), limit)

    def test_reserve_ohne_nachtmodus_nicht_weiter(self):
        self.anlegen("sess-A", self.now - 300)
        register.aktualisieren("claude", "sess-A", lambda d: d.update(reserve_bei_halt=True))
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual(self.orca.gesendet, [])
        self.assertEqual(register.lesen("claude", "sess-A")["status"], "reserve")
        self.assertEqual(self.weiter_pushes(erg), [])

    def test_codex_wartet_auf_weiter_wird_aktiv(self):
        from lw import codex
        tid = "01a0bf6b-ae1f-7de0-8b05-aa0baa8a6479"
        register.aktualisieren("codex", tid, lambda d: d.update(status="wartet_auf_weiter", cwd=self.home))
        seit = register.lesen("codex", tid)["status_seit"]
        self.orca._terminals.append({"handle": "term_X", "agentIdentity": "codex", "tabId": "tX", "leafId": "lX",
                                     "worktreePath": self.home})
        melder = melden.Melder(self.k, dry_run=True)
        ctx = Kontext(self.k, self.orca, melder, self.now, dry_run=True, claude_agenten=[])
        phase = {"phase": "ok", "art": "fuenf", "pct": 5, "reset": self.now + 3600}
        for aktivitaet, erwartet in ((seit - 10, "wartet_auf_weiter"), (seit + 10, "aktiv")):
            info = {"cwd": self.home, "letzte_aktivitaet": aktivitaet, "laeuft": False, "limit": None}
            with mock.patch.object(codex.quellen, "orca_pane_sitzungen",
                                   return_value={"tX:lX": {"anbieter": "codex", "id": tid}}), \
                    mock.patch.object(codex, "id_index", return_value={tid: "datei"}), \
                    mock.patch.object(codex.quellen, "codex_thread", return_value=info):
                codex.verwalten(ctx, phase, [])
            self.assertEqual(register.lesen("codex", tid)["status"], erwartet)

    def test_kein_wachhalten_ohne_nachtmodus(self):
        abend = zeit(26, 23)
        self.setze_zeit(abend)
        self.anlegen("sess-A", abend + 3600)
        mac = {"netzteil": True, "wach_bei_deckel_zu": False}
        erg = self.lauf(nutzung(50, abend + 3600, stand=abend), mac=mac)
        self.assertFalse(any("caffeinate" in a for a in erg["aktionen"]))
        self.assertFalse(any("Remote-Modus" in m["text"] for m in erg["meldungen"]))
        nacht.sitzung_an("claude", "sess-A", abend)
        erg = self.lauf(nutzung(50, abend + 3600, stand=abend), mac=mac)
        self.assertTrue(any("caffeinate" in a for a in erg["aktionen"]))

    def test_nachtmodus_endet_vor_fortsetzung_kein_wachhalten(self):
        frueh = zeit(27, 7)
        self.setze_zeit(frueh)
        self.anlegen("sess-A", frueh + 2 * 3600)      # Reset 09:00, Nachtmodus endet 08:00
        nacht.sitzung_an("claude", "sess-A", frueh)
        erg = self.lauf(nutzung(50, frueh + 2 * 3600, stand=frueh))
        self.assertFalse(any("caffeinate" in a for a in erg["aktionen"]))

    def test_codex_ohne_nachtmodus_nichts_gesendet(self):
        tid = "01a0bf6b-ae1f-7de0-8b05-aa0baa8a6479"

        def f(d):
            d.update({"cwd": self.home, "terminal": "term_X", "pane_key": "tX:lX"})
            register.warten_auf_reset(d, "gestoppt", "codex-x", self.now - 300, "fuenf", 120)
        register.aktualisieren("codex", tid, f)
        self.orca._terminals.append({"handle": "term_X", "agentIdentity": "codex", "tabId": "tX", "leafId": "lX",
                                     "worktreePath": self.home})
        self.orca.bildschirme["term_X"] = bildschirm("codex_bereit.txt")
        erg = self.lauf(nutzung(5, self.now + 5 * 3600, stand=self.now))
        self.assertEqual([g for g in self.orca.gesendet if g.get("handle") == "term_X"], [])
        self.assertEqual(register.lesen("codex", tid)["status"], "wartet_auf_weiter")
        self.assertTrue(any(m["text"].startswith("Codex:") and "„weiter“" in m["text"] for m in erg["meldungen"]))


class BerichtTest(TempHome):
    def test_nachtmodus_nicht_relevant(self):
        util.ereignis("nachtmodus", anbieter="claude", weg="an")
        b = bericht.erstellen(self.now - 60, self.now + 60)
        self.assertEqual(b["relevant"], 0)
        util.ereignis("wartet_auf_weiter", anbieter="claude")
        b = bericht.erstellen(self.now - 60, self.now + 60)
        self.assertEqual(b["relevant"], 1)
        self.assertIn("weiter", b["text"])


if __name__ == "__main__":
    unittest.main()
