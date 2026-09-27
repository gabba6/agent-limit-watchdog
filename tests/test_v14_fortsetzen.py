"""v1.4 B: Fortsetzen verlässlich – Orcas "working" allein genügt nie, Belege aus Bildschirm und Protokoll,
Nachprüfung von "läuft bereits" (Regression 27.09.2026)."""

import calendar
import contextlib
import copy
import io
import json
import os
import shutil
import time
import unittest.mock

from hilfe import TempHome, bildschirm, fixture, nutzung

from lw import aktivitaet, bildschirm as bs, cli, fortsetzen, konfig, melden, register, simulation, tick, util
from lw.attrappe import OrcaAttrappe
from lw.kontext import Kontext

MAC_OK = {"netzteil": True, "wach_bei_deckel_zu": True, "schlaf_aus": True}
RESET = calendar.timegm((2026, 9, 27, 5, 30, 0, 0, 0, 0))     # 07:30 MESZ; Turn endete 06:07 MESZ
CODEX_ID = "01a0eeee-0000-7000-8000-00000000c014"
CODEX_ROLLOUT = f"rollout-2026-09-27T05-00-00-v14-{CODEX_ID}.jsonl"


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


class AktivitaetTest(TempHome):
    def test_turn_beendet_mit_hintergrund_task(self):
        b = aktivitaet.claude(fixture("transcript_turn_beendet_bg.jsonl"), RESET, RESET + 600)
        self.assertFalse(b["neu"])
        self.assertFalse(b["turn_offen"])
        self.assertEqual(b["letzte"], calendar.timegm((2026, 9, 27, 4, 7, 17, 0, 0, 0)) + 0.733)
        self.assertEqual(b["quelle"], "transcript")

    def test_neue_aktivitaet_nach_seit(self):
        b = aktivitaet.claude(fixture("transcript_arbeitet.jsonl"), RESET, RESET + 300)
        self.assertTrue(b["neu"])
        self.assertTrue(b["turn_offen"])

    def test_sidechain_und_meta_zaehlen_nicht(self):
        b = aktivitaet.claude(fixture("transcript_sidechain.jsonl"), RESET, RESET + 600)
        self.assertFalse(b["neu"])
        self.assertFalse(b["turn_offen"])

    def test_aktivitaet_vor_dem_reset_zaehlt_nicht(self):
        frueh = calendar.timegm((2026, 9, 27, 4, 0, 0, 0, 0, 0))
        self.assertTrue(aktivitaet.claude(fixture("transcript_turn_beendet_bg.jsonl"), frueh, RESET)["neu"])
        self.assertFalse(aktivitaet.claude(fixture("transcript_turn_beendet_bg.jsonl"), RESET, RESET)["neu"])

    def test_fehlende_datei(self):
        self.assertIsNone(aktivitaet.claude(os.path.join(self.home, "gibt-es-nicht.jsonl"), 0, RESET))
        self.assertIsNone(aktivitaet.claude(None, 0, RESET))

    def test_urteil(self):
        neu = {"neu": True, "letzte": RESET + 10, "turn_offen": False}
        alt = {"neu": False, "letzte": RESET - 3600, "turn_offen": False}
        self.assertEqual(aktivitaet.urteil("beschaeftigt", alt), "arbeitet")
        self.assertEqual(aktivitaet.urteil("bereit", neu), "schon_fortgesetzt")
        self.assertEqual(aktivitaet.urteil("bereit", alt), "bereit")
        self.assertEqual(aktivitaet.urteil("bereit", None), "bereit")
        self.assertEqual(aktivitaet.urteil("menue", neu), "bildschirm")
        offen = {"neu": False, "letzte": RESET - 60, "turn_offen": True}
        self.assertEqual(aktivitaet.urteil("bereit", offen, RESET + 60, 600), "arbeitet")
        self.assertEqual(aktivitaet.urteil("bereit", offen, RESET + 3600, 600), "bereit")


class BildschirmV14Test(TempHome):
    def test_neue_fixtures(self):
        self.assertEqual(bs.klassifiziere(bildschirm("claude_bereit_hintergrund_shell.txt"), "claude")[0], "bereit")
        self.assertEqual(bs.klassifiziere(bildschirm("claude_arbeitet_vordergrund_bash.txt"), "claude")[0],
                         "beschaeftigt")

    def test_ctrl_b_allein_ist_beschaeftigt(self):
        zeilen = ["⏺ Bash(make test)", "  ⎿  Running… (1m 2s)", "     (ctrl+b to run in background)", "─" * 40, "❯",
                  "─" * 40]
        self.assertEqual(bs.klassifiziere(zeilen, "claude")[0], "beschaeftigt")


class FortsetzenBasis(TempHome):
    def setUp(self):
        super().setUp()
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = False
        self.setze_zeit(RESET + 180)
        self.transcript = os.path.join(self.home, "transcript.jsonl")
        shutil.copy(fixture("transcript_turn_beendet_bg.jsonl"), self.transcript)
        self.orca = OrcaAttrappe(
            terminals=[{"handle": "term_A", "agentIdentity": "claude", "tabId": "tA", "leafId": "lA",
                        "worktreePath": self.home}],
            agenten={"tA:lA": {"state": "working"}},
            bildschirme={"term_A": bildschirm("claude_bereit_hintergrund_shell.txt")})

    def lauf(self):
        melder = melden.Melder(self.k, dry_run=True)
        ctx = Kontext(self.k, self.orca, melder, self.now, dry_run=True, claude_agenten=[])
        return tick.ausfuehren(ctx, sim={"claude": nutzung(5, self.now + 5 * 3600, stand=self.now),
                                         "codex": nutzung(5, self.now + 5 * 3600, stand=self.now)}, mac_sim=MAC_OK)

    def sitzung_anlegen(self, sid="sess-A", status="gestoppt", **extra):
        def f(d):
            d.update({"cwd": self.home, "terminal": "term_A", "pane_key": "tA:lA", "transcript": self.transcript})
            register.warten_auf_reset(d, status, "claude-fuenf-v14", RESET, "fuenf", 120)
            d.update(extra)
        register.aktualisieren("claude", sid, f)

    def s(self, sid="sess-A"):
        return register.lesen("claude", sid)

    def prompts(self):
        return [g for g in self.orca.gesendet if g.get("text")]

    def anhaengen(self, ts, typ="assistant"):
        with open(self.transcript, "a") as f:
            f.write(json.dumps({"type": typ, "isSidechain": False, "timestamp": iso(ts),
                                "message": {"content": "..."}}) + "\n")

    def weiter(self, sekunden):
        self.setze_zeit(self.now + sekunden)
        return self.lauf()


class FortsetzenV14Test(FortsetzenBasis):
    def test_regression_orca_working_aber_turn_beendet(self):
        """27.09.: Orca meldet working (nur Hintergrund-Shell), Bildschirm bereit, Turn vor dem Reset beendet."""
        self.sitzung_anlegen()
        erg = self.lauf()
        self.assertEqual(len(self.prompts()), 1)
        self.assertTrue(self.prompts()[0]["text"].startswith("Limit-Wächter: Das Nutzungslimit ist zurückgesetzt"))
        s = self.s()
        self.assertEqual(s["status"], "fortgesetzt")
        self.assertEqual(register.versuche(s, s["fenster_id"]), 1)
        self.assertFalse(s["geprueft"])
        with open(util.pfad("log", "waechter.log"), encoding="utf-8") as f:
            self.assertIn("Orca ignoriert", f.read())
        self.assertTrue(any("fortgesetzt" in m["text"] for m in erg["meldungen"]))

    def test_working_und_spinner_wird_nachgeprueft(self):
        self.orca.bildschirme["term_A"] = bildschirm("claude_arbeitet_vordergrund_bash.txt")
        self.sitzung_anlegen()
        self.lauf()
        self.assertEqual(self.orca.gesendet, [])
        s = self.s()
        self.assertEqual(s["status"], "fortgesetzt")
        self.assertTrue(s["laeuft_ungeprueft"])
        self.assertFalse(s["geprueft"])
        self.assertEqual(s["pruefen_ab"], self.now + 120)
        self.assertEqual(register.versuche(s, s["fenster_id"]), 0)
        # später: Spinner noch da -> tick prüft nach, verschiebt die nächste Prüfung, zählt nichts
        self.weiter(180)
        s = self.s()
        self.assertEqual(s["pruefen_ab"], self.now + 120)
        self.assertEqual(fortsetzen.nachpruefungen(s, s["fenster_id"]), 0)
        self.assertEqual(self.orca.gesendet, [])

    def test_nachpruefung_ohne_aktivitaet_zurueck_ins_warten(self):
        self.orca.bildschirme["term_A"] = bildschirm("claude_arbeitet_vordergrund_bash.txt")
        self.sitzung_anlegen()
        self.lauf()
        self.orca.bildschirme["term_A"] = bildschirm("claude_bereit_hintergrund_shell.txt")
        self.weiter(180)
        s = self.s()
        self.assertEqual(s["status"], "gestoppt")
        self.assertEqual(s["fortsetzen_ab"], self.now)
        self.assertNotIn("geprueft", s)
        self.assertEqual(fortsetzen.nachpruefungen(s, s["fenster_id"]), 1)
        self.assertEqual(self.orca.gesendet, [])
        self.weiter(60)
        self.assertEqual(len(self.prompts()), 1)
        self.assertEqual(self.s()["status"], "fortgesetzt")

    def test_nachpruefung_mit_aktivitaet(self):
        self.orca.bildschirme["term_A"] = bildschirm("claude_arbeitet_vordergrund_bash.txt")
        self.sitzung_anlegen()
        self.lauf()
        self.anhaengen(self.now + 30)
        self.orca.bildschirme["term_A"] = bildschirm("claude_bereit_hintergrund_shell.txt")
        self.weiter(180)
        s = self.s()
        self.assertEqual(s["status"], "fortgesetzt")
        self.assertTrue(s["geprueft"])
        self.assertFalse(s["laeuft_ungeprueft"])
        self.assertEqual(self.orca.gesendet, [])

    def test_max_nachpruefungen_blockiert(self):
        self.sitzung_anlegen(status="fortgesetzt", laeuft_ungeprueft=True, geprueft=False,
                             pruefen_ab=self.now - 1, beleg_seit=RESET,
                             nachpruefungen={"claude-fuenf-v14": 3})
        erg = self.lauf()
        self.assertEqual(self.s()["status"], "blockiert")
        self.assertEqual(self.orca.gesendet, [])
        self.assertTrue(any("nichts gesendet" in m["text"].lower() for m in erg["meldungen"]))

    def test_nach_echtem_senden_bis_aufgegeben(self):
        self.orca._agenten["tA:lA"] = {"state": "done"}
        self.sitzung_anlegen()
        self.lauf()                                   # Versuch 1
        self.assertEqual(len(self.prompts()), 1)
        self.weiter(180)                              # Prüfung: bereit, keine Aktivität -> zurück
        self.assertEqual(self.s()["status"], "gestoppt")
        self.weiter(60)                               # Versuch 2
        self.assertEqual(len(self.prompts()), 2)
        self.weiter(180)
        self.assertEqual(self.s()["status"], "gestoppt")
        erg = self.weiter(60)                         # max_pro_fenster erreicht
        self.assertEqual(self.s()["status"], "aufgegeben")
        self.assertEqual(len(self.prompts()), 2)
        self.assertTrue(any("aufgegeben" in m["text"].lower() or "2" in m["text"] for m in erg["meldungen"]))

    def test_nach_echtem_senden_mit_aktivitaet_geprueft(self):
        self.orca._agenten["tA:lA"] = {"state": "done"}
        self.sitzung_anlegen()
        self.lauf()
        self.anhaengen(self.now + 5, "user")          # unser Prompt kam an
        self.weiter(180)
        s = self.s()
        self.assertEqual((s["status"], s["geprueft"]), ("fortgesetzt", True))

    def test_working_und_limit_menue_blockiert(self):
        self.orca.bildschirme["term_A"] = bildschirm("claude_limit_menue.txt")
        self.sitzung_anlegen()
        self.lauf()
        self.assertEqual(self.orca.gesendet, [])
        self.assertEqual(self.s()["status"], "blockiert")

    def test_aktivitaet_nach_reset_schon_fortgesetzt(self):
        shutil.copy(fixture("transcript_arbeitet.jsonl"), self.transcript)
        self.orca.bildschirme["term_A"] = bildschirm("claude_bereit.txt")
        self.setze_zeit(RESET + 1800)
        self.sitzung_anlegen()
        self.lauf()
        self.assertEqual(self.orca.gesendet, [])
        s = self.s()
        self.assertEqual((s["status"], s["geprueft"]), ("fortgesetzt", True))

    def test_bildschirm_nicht_lesbar_bei_working(self):
        from lw.orca import OrcaFehler

        def kaputt(handle):
            raise OrcaFehler("weg")
        self.orca.bildschirm = kaputt
        self.sitzung_anlegen()
        self.lauf()
        s = self.s()
        self.assertEqual(s["status"], "fortgesetzt")
        self.assertTrue(s["laeuft_ungeprueft"])

    def test_belege_aus_altes_verhalten(self):
        self.k["fortsetzen"]["belege_pruefen"] = False
        self.sitzung_anlegen()
        self.lauf()
        self.assertEqual(self.orca.gesendet, [])
        self.assertEqual(self.s()["status"], "fortgesetzt")


class CodexOrcaTest(TempHome):
    def setUp(self):
        super().setUp()
        self.setze_zeit(RESET + 180)
        tag = os.path.join(self.k["daten"]["codex_sessions"], time.strftime("%Y/%m/%d", time.localtime(self.now)))
        os.makedirs(tag, exist_ok=True)
        self.rollout = os.path.join(tag, CODEX_ROLLOUT)
        shutil.copy(fixture(CODEX_ROLLOUT), self.rollout)
        self.orca = OrcaAttrappe(
            terminals=[{"handle": "term_X", "agentIdentity": "codex", "tabId": "t2", "leafId": "l2",
                        "worktreePath": "/tmp/projekt"}],
            agenten={"t2:l2": {"state": "working"}},
            bildschirme={"term_X": bildschirm("codex_bereit.txt")})

        def f(d):
            d.update({"cwd": "/tmp/projekt", "terminal": "term_X", "pane_key": "t2:l2"})
            register.warten_auf_reset(d, "gestoppt", "codex-fuenf-v14", RESET, "fuenf", 120)
        register.aktualisieren("codex", CODEX_ID, f)

    def bearbeiten(self):
        ctx = Kontext(self.k, self.orca, melden.Melder(self.k, dry_run=True), self.now, dry_run=True,
                      claude_agenten=[])
        return fortsetzen.bearbeiten(ctx, register.lesen("codex", CODEX_ID), {"phase": "ok", "reserve_erreicht": False})

    def test_working_ohne_neue_aktivitaet_sendet(self):
        self.assertEqual(self.bearbeiten(), "fortgesetzt")
        self.assertEqual(len(self.orca.gesendet), 1)

    def test_rollout_laeuft_nachpruefen(self):
        with open(self.rollout, "a") as f:
            f.write(json.dumps({"timestamp": iso(RESET + 60), "type": "event_msg",
                                "payload": {"type": "task_started"}}) + "\n")
        self.orca.bildschirme["term_X"] = bildschirm("codex_arbeitet.txt")
        self.assertEqual(self.bearbeiten(), "laeuft")
        self.assertEqual(self.orca.gesendet, [])
        s = register.lesen("codex", CODEX_ID)
        self.assertTrue(s["laeuft_ungeprueft"])
        # Nachprüfung: rollout belegt Aktivität seit dem Reset
        self.setze_zeit(self.now + 180)
        ctx = Kontext(self.k, self.orca, melden.Melder(self.k, dry_run=True), self.now, dry_run=True)
        fortsetzen.pruefen(ctx, s)
        s = register.lesen("codex", CODEX_ID)
        self.assertTrue(s["geprueft"])

    def test_rollout_neu_und_bereit_schon_fortgesetzt(self):
        with open(self.rollout, "a") as f:
            f.write(json.dumps({"timestamp": iso(RESET + 30), "type": "event_msg",
                                "payload": {"type": "task_started"}}) + "\n")
            f.write(json.dumps({"timestamp": iso(RESET + 90), "type": "event_msg",
                                "payload": {"type": "task_complete"}}) + "\n")
        self.assertEqual(self.bearbeiten(), "laeuft")
        self.assertEqual(self.orca.gesendet, [])
        self.assertTrue(register.lesen("codex", CODEX_ID)["geprueft"])


class StatusLageTest(TempHome):
    def setUp(self):
        super().setUp()
        self.konfig = os.path.join(self.home, "config.toml")
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write('[allgemein]\nsprache = "de"\n[daten]\norca = "/gibt/es/nicht/orca"\n'
                    'codex_sessions = "' + os.path.join(self.home, "codex-sessions") + '"\n')
        os.environ["LIMIT_WAECHTER_CONFIG"] = self.konfig
        self.setze_zeit(RESET + 300)

    def status_json(self):
        puffer = io.StringIO()
        with unittest.mock.patch.object(cli, "_launchagent_geladen", return_value=True), \
                unittest.mock.patch.object(melden, "topic_vorhanden", return_value=True), \
                contextlib.redirect_stdout(puffer):
            self.assertEqual(cli.main(["status", "--json"]), 0)
        return {x["id"]: x for x in json.loads(puffer.getvalue())["sitzungen"]}

    def anlegen(self, sid, **felder):
        register.aktualisieren("claude", sid, lambda d: d.update(cwd="/p/demo", **felder))

    def test_lage_je_status(self):
        arbeitet = os.path.join(self.home, "t-arbeitet.jsonl")
        shutil.copy(fixture("transcript_arbeitet.jsonl"), arbeitet)
        ruht = os.path.join(self.home, "t-ruht.jsonl")
        shutil.copy(fixture("transcript_turn_beendet_bg.jsonl"), ruht)
        self.anlegen("s-arbeitet", status="aktiv", transcript=arbeitet)
        self.anlegen("s-ruht", status="aktiv", transcript=ruht)
        self.anlegen("s-ohne", status="eingebaut_fortgesetzt")
        self.anlegen("s-wartet", status="gestoppt", fortsetzen_ab=self.now + 600)
        self.anlegen("s-weiter", status="wartet_auf_weiter")
        self.anlegen("s-block", status="blockiert")
        self.anlegen("s-auf", status="aufgegeben")
        self.anlegen("s-res", status="reserve")
        self.anlegen("s-sich", status="sicherung")
        self.anlegen("s-pruef", status="fortgesetzt", geprueft=False)
        self.anlegen("s-fort", status="fortgesetzt", geprueft=True)
        self.anlegen("s-ende", status="beendet", transcript=arbeitet)
        x = self.status_json()
        erwartet = {"s-arbeitet": ("arbeitet", "gruen"), "s-ruht": ("ruht", "grau"), "s-ohne": ("ruht", "grau"),
                    "s-wartet": ("wartet", "blau"), "s-weiter": ("weiter_noetig", "orange"),
                    "s-block": ("blockiert", "rot"), "s-auf": ("blockiert", "rot"), "s-res": ("blockiert", "rot"),
                    "s-sich": ("sichert", "gelb"), "s-pruef": ("pruefung", "blau"), "s-fort": ("ruht", "grau"),
                    "s-ende": ("beendet", "grau")}
        for sid, (lage, farbe) in erwartet.items():
            with self.subTest(sid=sid):
                self.assertEqual((x[sid]["lage"], x[sid]["lage_farbe"]), (lage, farbe))
                self.assertTrue(x[sid]["lage_text"])
                self.assertIn("aktivitaet", x[sid])
        self.assertEqual(x["s-arbeitet"]["aktivitaet"]["quelle"], "transcript")
        self.assertEqual(x["s-arbeitet"]["aktivitaet"]["letzte"], RESET + 220)
        self.assertIsNone(x["s-ende"]["aktivitaet"]["letzte"])
        self.assertIsNone(x["s-ohne"]["aktivitaet"]["letzte"])
        self.assertEqual(x["s-weiter"]["lage_text"], "„weiter“ nötig")
        self.assertIn(util.uhrzeit(self.now + 600, self.now), x["s-wartet"]["lage_text"])
        # ohne Nachtmodus wird nicht automatisch fortgesetzt -> Hinweis auf „weiter“
        self.assertIn("„weiter“", x["s-wartet"]["lage_text"])


class KonfigV14Test(TempHome):
    def test_standard_und_pruefung(self):
        k = konfig.laden()
        self.assertTrue(k["fortsetzen"]["belege_pruefen"])
        self.assertEqual(k["fortsetzen"]["max_nachpruefungen"], 3)
        self.assertEqual(konfig.pruefen(k), [])
        falsch = copy.deepcopy(k)
        falsch["fortsetzen"]["aktiv_frist_minuten"] = 0
        falsch["fortsetzen"]["belege_pruefen"] = "ja"
        self.assertEqual(len(konfig.pruefen(falsch)), 2)

    def test_config_toml_block(self):
        k = konfig.laden(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.toml"),
                         streng=True)
        self.assertEqual(k["fortsetzen"]["aktiv_frist_minuten"], 10)
        self.assertEqual(k["fortsetzen"]["max_pro_fenster"], 2)


class ZyklusV14Test(TempHome):
    def test_zyklus_laeuft(self):
        erg = simulation.zyklus(ausgabe=False)
        ende = [e for e in erg if e["schritt"] == "endzustand"][0]["sitzungen"]
        self.assertEqual(ende["session-A"], "fortgesetzt")
        self.assertEqual(ende["01a0ffff-0000-7000-8000-00000000c0de"], "fortgesetzt")
