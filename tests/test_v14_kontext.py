"""v1.4 (27.09.2026): nativ zuerst (N1/N3), sanfter Stopp im Tick (N2), Kontext-Tracking (N4), ruhende Sitzungen."""

import contextlib
import copy
import io
import json
import os
import shutil
import unittest.mock

from hilfe import TempHome, bildschirm, fixture, nutzung

from lw import cli, konfig, kontextfenster, melden, register, tick, util
from lw.attrappe import OrcaAttrappe
from lw.kontext import Kontext

MAC_OK = {"netzteil": True, "wach_bei_deckel_zu": True, "schlaf_aus": True}
CODEX_ID = "01a0beef-0000-7000-8000-00000000c0de"
ROLLOUT = "rollout-2026-09-26T07-00-00-01a0beef-0000-7000-8000-00000000c0de.jsonl"


class ParserTest(TempHome):
    def test_statusline_mit_current_usage(self):
        daten = {"session_id": "s", "model": {"id": "claude-opus-5-5[1m]", "display_name": "Opus"},
                 "context_window": {"context_window_size": 1000000, "used_percentage": 41,
                                    "current_usage": {"input_tokens": 2000, "cache_creation_input_tokens": 10000,
                                                      "cache_read_input_tokens": 400000, "output_tokens": 9999}}}
        e = kontextfenster.aus_statusline(daten, self.now)
        self.assertEqual((e["prozent"], e["tokens"], e["fenster"], e["modell"], e["quelle"]),
                         (41.2, 412000, 1000000, "Opus 5.5", "statusline"), "output_tokens zählen nicht")

    def test_statusline_nur_prozent_oder_nichts(self):
        e = kontextfenster.aus_statusline({"model": {"id": "claude-sonnet-5"},
                                           "context_window": {"used_percentage": 50}}, self.now)
        self.assertEqual((e["prozent"], e["tokens"], e["fenster"], e["modell"]), (50.0, 100000, 200000, "Sonnet 5"))
        self.assertIsNone(kontextfenster.aus_statusline({"context_window": {"current_usage": None,
                                                                            "used_percentage": None}}, self.now))
        self.assertIsNone(kontextfenster.aus_statusline({}, self.now))
        self.assertIsNone(kontextfenster.aus_statusline([1], self.now))
        e = kontextfenster.aus_statusline({"model": {"id": "claude-opus-5-5[1m]"},
                                           "context_window": {"used_percentage": 10}}, self.now)
        self.assertEqual(e["fenster"], 1000000, "[1m] in der Modellkennung")

    def test_fenster_und_modellnamen(self):
        self.assertEqual(kontextfenster.fenster_aus_modell("claude-opus-5-5"), 200000)
        self.assertEqual(kontextfenster.fenster_aus_modell("claude-opus-5-5", 150000), 150000)
        self.assertEqual(kontextfenster.fenster_aus_modell("Opus 5.5 (1M context)"), 200000)
        self.assertEqual(kontextfenster.fenster_aus_modell("Sonnet (1M)"), 1000000)
        self.assertEqual(kontextfenster.modell_name("claude-opus-4-20250514"), "Opus 4")
        self.assertEqual(kontextfenster.modell_name("gpt-5.5-codex"), "gpt-5.5-codex")
        self.assertEqual(kontextfenster.modell_name("claude-opus-5-5", "Opus 5.5"), "Opus 5.5")
        self.assertIsNone(kontextfenster.modell_name())

    def test_transcript(self):
        e = kontextfenster.aus_transcript(fixture("transcript_kontext.jsonl"))
        # letzter Haupteintrag (Sidechain und API-Fehler übersprungen): 20 + 2000 + 138000
        self.assertEqual((e["tokens"], e["fenster"], e["prozent"], e["modell"], e["quelle"]),
                         (140020, 200000, 70.0, "Opus 5.5", "transcript"))
        self.assertIsNotNone(e["stand"])
        self.assertIsNone(kontextfenster.aus_transcript(os.path.join(self.home, "fehlt.jsonl")))
        groß = os.path.join(self.home, "gross.jsonl")
        with open(groß, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"model": "claude-opus-5-5",
                                                                  "usage": {"input_tokens": 1,
                                                                            "cache_read_input_tokens": 450000}}}))
        self.assertEqual(kontextfenster.aus_transcript(groß)["fenster"], 1000000, "mehr als 200k -> 1M-Fenster")

    def test_transcript_nach_compact(self):
        tr = os.path.join(self.home, "t.jsonl")
        shutil.copy(fixture("transcript_kontext.jsonl"), tr)
        with open(tr, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "system", "subtype": "compact_boundary",
                                "timestamp": "2026-09-26T05:10:00.000Z"}) + "\n")
        e = kontextfenster.aus_transcript(tr)
        self.assertEqual((e["prozent"], e["tokens"], e["modell"]), (0.0, 0, "Opus 5.5"))

    def test_rollout(self):
        e = kontextfenster.aus_rollout(fixture(ROLLOUT))
        self.assertEqual((e["tokens"], e["fenster"], e["modell"], e["quelle"]),
                         (152000, 272000, "gpt-5.5-codex", "rollout"))
        self.assertAlmostEqual(e["prozent"], 55.9)
        self.assertIsNone(kontextfenster.aus_rollout(None))
        leer = os.path.join(self.home, "r.jsonl")
        with open(leer, "w", encoding="utf-8") as f:
            f.write('{"type": "event_msg", "payload": {"type": "token_count", "info": null}}\nkaputt\n')
        self.assertIsNone(kontextfenster.aus_rollout(leer))

    def test_tokens_text_und_stufe(self):
        self.assertEqual([kontextfenster.tokens_text(n) for n in (0, 999, 412000, 1000000, 1200000)],
                         ["0", "999", "412k", "1M", "1.2M"])
        self.assertEqual([kontextfenster.stufe(p) for p in (69.9, 70, 84.9, 85)],
                         ["ok", "warnung", "warnung", "kritisch"])

    def test_speichern_drosselt_und_merkt_kompaktierung(self):
        e = {"prozent": 60.0, "tokens": 120000, "fenster": 200000, "modell": "Opus 5.5", "quelle": "statusline"}
        kontextfenster.speichern("claude", "s1", e, self.now)
        kontextfenster.speichern("claude", "s1", e, self.now + 5)
        self.assertEqual(kontextfenster.lesen("claude", "s1")["stand"], self.now, "gleiche Zahlen: gedrosselt")
        kontextfenster.speichern("claude", "s1", dict(e, prozent=10.0, tokens=20000), self.now + 90)
        d = kontextfenster.lesen("claude", "s1")
        self.assertEqual((d["kompaktiert"], [p[1] for p in d["verlauf"]]), (self.now + 90, [60.0, 10.0]))


class ErmittelnTest(TempHome):
    def setUp(self):
        super().setUp()
        self.tr = os.path.join(self.home, "t.jsonl")
        shutil.copy(fixture("transcript_kontext.jsonl"), self.tr)
        os.utime(self.tr, (self.now - 3600, self.now - 3600))

    def test_claude_statusline_vor_transcript(self):
        x = {"anbieter": "claude", "id": "c1", "transcript": self.tr}
        kontextfenster.speichern("claude", "c1", {"prozent": 41.2, "tokens": 412000, "fenster": 1000000,
                                                  "modell": "Opus 5.5", "quelle": "statusline"}, self.now)
        kx = kontextfenster.ermitteln(x, self.k)
        self.assertEqual(kx, {"prozent": 41.2, "tokens": 412000, "fenster": 1000000, "modell": "Opus 5.5",
                              "stufe": "ok", "stand": self.now, "quelle": "statusline"})
        os.utime(self.tr, (self.now + 900, self.now + 900))     # Transcript viel neuer: Transcript gilt
        kx = kontextfenster.ermitteln(x, self.k)
        self.assertEqual((kx["quelle"], kx["tokens"], kx["fenster"]), ("transcript", 140020, 1000000),
                         "Fenster aus dem gespeicherten Stand übernommen")

    def test_claude_nur_transcript_und_stufe(self):
        kx = kontextfenster.ermitteln({"anbieter": "claude", "id": "c2", "transcript": self.tr}, self.k)
        self.assertEqual((kx["quelle"], kx["prozent"], kx["stufe"]), ("transcript", 70.0, "warnung"))
        self.assertIsNone(kontextfenster.ermitteln({"anbieter": "claude", "id": "c3"}, self.k))

    def test_codex_rollout(self):
        index = {CODEX_ID: fixture(ROLLOUT)}
        kx = kontextfenster.ermitteln({"anbieter": "codex", "id": CODEX_ID}, self.k, index)
        self.assertEqual((kx["quelle"], kx["tokens"], kx["fenster"], kx["stufe"]),
                         ("rollout", 152000, 272000, "ok"))
        self.assertIsNone(kontextfenster.ermitteln({"anbieter": "codex", "id": "x"}, self.k, {}))


class TickNativTest(TempHome):
    """N3: ohne Nachtmodus greift der Wächter nicht ins Fortsetzen ein; Claudes eingebautes hat Vorrang."""

    def setUp(self):
        super().setUp()
        self.reset = self.now - 60
        self.orca = OrcaAttrappe(
            terminals=[{"handle": "term_A", "agentIdentity": "claude", "tabId": "tA", "leafId": "lA",
                        "worktreePath": self.home}],
            agenten={"tA:lA": {"state": "done"}}, bildschirme={"term_A": bildschirm("claude_bereit.txt")})

    def lauf(self, claude=None):
        melder = melden.Melder(self.k, dry_run=True)
        ctx = Kontext(self.k, self.orca, melder, self.now, dry_run=True, claude_agenten=[])
        sim = {"claude": claude or nutzung(5, self.now + 5 * 3600, stand=self.now),
               "codex": nutzung(5, self.now + 5 * 3600, stand=self.now)}
        return tick.ausfuehren(ctx, sim=sim, mac_sim=MAC_OK)

    def anlegen(self, sid, status, anbieter="claude"):
        def f(d):
            d.update({"cwd": self.home, "terminal": "term_A", "pane_key": "tA:lA", "ort": "orca"})
            register.warten_auf_reset(d, status, f"{anbieter}-fuenf-1", self.reset, "fuenf", 120)
            d["fortsetzen_ab"] = self.reset
        register.aktualisieren(anbieter, sid, f)

    def test_claude_am_limit_ohne_nachtmodus_wartet_auf_eingebautes(self):
        self.anlegen("c-limit", "limit")
        self.anlegen("c-armed", "eingebaut_wartet")
        erg = self.lauf()
        for sid in ("c-limit", "c-armed"):
            self.assertEqual(register.lesen("claude", sid)["status"],
                             "limit" if sid == "c-limit" else "eingebaut_wartet", "kein Eingriff während der Karenz")
        self.assertEqual(self.orca.gesendet, [])
        self.assertFalse([m for m in erg["meldungen"] if "„weiter“" in m["text"]])
        # nach Reset + 3 × Karenz hat Claude offenbar nicht selbst fortgesetzt: nur Hinweis, nichts gesendet
        self.setze_zeit(self.reset + 3 * 5 * 60 + 1)
        erg = self.lauf()
        self.assertEqual(register.lesen("claude", "c-limit")["status"], "wartet_auf_weiter")
        self.assertEqual(self.orca.gesendet, [])

    def test_gestoppte_sitzung_und_codex_ohne_nachtmodus_wie_bisher(self):
        self.anlegen("c-stopp", "gestoppt")
        self.anlegen("x-limit", "limit", anbieter="codex")
        self.lauf()
        self.assertEqual(register.lesen("claude", "c-stopp")["status"], "wartet_auf_weiter")
        self.assertEqual(register.lesen("codex", "x-limit")["status"], "wartet_auf_weiter")

    def test_sanfter_stopp_push_und_current(self):
        erg = self.lauf(nutzung(93, self.now + 3600, stand=self.now))
        text = erg["meldungen"][0]["text"]
        self.assertIn("Stopp-Schwelle", text)
        self.assertIn("Claude selbst fort", text)
        cur = util.lies_json(util.pfad("state", "current.json"))
        self.assertEqual(cur["claude_stopp_art"], "sanft")
        self.assertEqual(cur["kontext"], {"warnung": 70, "kritisch": 85, "hinweis": False,
                                          "standard_fenster": 200000})
        self.assertTrue(cur["statusline_anzeigen"])
        self.assertEqual(cur["schwellen"]["stopp"], 92)

    def test_geordneter_stopp_push_bei_konfig(self):
        self.k["schwellen"]["claude_stopp_art"] = "geordnet"
        erg = self.lauf(nutzung(93, self.now + 3600, stand=self.now))
        self.assertIn("sichern und halten an", erg["meldungen"][0]["text"])


class TickKontextTest(TempHome):
    def setUp(self):
        super().setUp()
        self.orca = OrcaAttrappe(terminals=[], agenten={})
        register.aktualisieren("claude", "c-kx", lambda d: d.update(cwd="/p/demo", status="aktiv"))

    def lauf(self):
        melder = melden.Melder(self.k, dry_run=True)
        ctx = Kontext(self.k, self.orca, melder, self.now, dry_run=True, claude_agenten=[])
        sim = {"claude": nutzung(5, self.now + 5 * 3600, stand=self.now),
               "codex": nutzung(5, self.now + 5 * 3600, stand=self.now)}
        erg = tick.ausfuehren(ctx, sim=sim, mac_sim=MAC_OK)
        return [m["text"] for m in erg["meldungen"] if "Kontext" in m["text"]]

    def stand(self, prozent):
        kontextfenster.speichern("claude", "c-kx", {"prozent": float(prozent), "tokens": prozent * 2000,
                                                    "fenster": 200000, "modell": "Opus 5.5",
                                                    "quelle": "statusline"}, self.now)

    def test_push_genau_einmal_je_stufe(self):
        self.stand(50)
        self.assertEqual(self.lauf(), [])
        self.stand(72)
        texte = self.lauf()
        self.assertEqual(len(texte), 1)
        self.assertIn("c-kx", texte[0])
        self.assertIn("72 %", texte[0])
        self.assertIn("144k / 200k", texte[0])
        self.assertNotIn("demo", texte[0], "kein Projektname im Push")
        self.setze_zeit(self.now + 60)
        self.stand(75)
        self.assertEqual(self.lauf(), [], "gleiche Stufe: kein zweiter Push")
        self.setze_zeit(self.now + 60)
        self.stand(90)
        texte = self.lauf()
        self.assertEqual(len(texte), 1)
        self.assertIn("kritisch", texte[0])
        self.assertEqual(self.lauf(), [])
        self.setze_zeit(self.now + 60)
        self.stand(10)                                 # kompaktiert
        self.assertEqual(self.lauf(), [])
        self.setze_zeit(self.now + 60)
        self.stand(71)
        self.assertEqual(len(self.lauf()), 1, "nach Kompaktierung darf die Warnung wiederkommen")

    def test_abschaltbar_und_alte_daten_still(self):
        self.k["kontext"]["melden"] = False
        self.stand(90)
        self.assertEqual(self.lauf(), [])
        self.k["kontext"]["melden"] = True
        self.setze_zeit(self.now + 2 * 3600)          # Stand älter als 1 h: kein Push
        self.assertEqual(self.lauf(), [])


class StatusKontextTest(TempHome):
    def setUp(self):
        super().setUp()
        self.konfig = os.path.join(self.home, "config.toml")
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write('[allgemein]\nsprache = "de"\n[kontext]\nwarnung = 60\nkritisch = 80\n')
        os.environ["LIMIT_WAECHTER_CONFIG"] = self.konfig
        util.schreib_json(util.pfad("state", "zustand.json"), {"letzter_tick": self.now - 30})

    def status(self):
        puffer = io.StringIO()
        with unittest.mock.patch.object(cli, "_launchagent_geladen", return_value=True), \
                unittest.mock.patch.object(melden, "topic_vorhanden", return_value=True), \
                contextlib.redirect_stdout(puffer):
            self.assertEqual(cli.main(["status", "--json"]), 0)
        return json.loads(puffer.getvalue())

    def test_kontext_je_sitzung_und_schwellen(self):
        register.aktualisieren("claude", "c-kx", lambda d: d.update(cwd="/p/demo", status="aktiv"))
        register.aktualisieren("claude", "c-leer", lambda d: d.update(cwd="/p/leer", status="aktiv"))
        kontextfenster.speichern("claude", "c-kx", {"prozent": 64.0, "tokens": 640000, "fenster": 1000000,
                                                    "modell": "Opus 5.5", "quelle": "statusline"}, self.now)
        d = self.status()
        self.assertEqual(d["kontext_schwellen"], {"warnung": 60, "kritisch": 80})
        s = {x["id"]: x for x in d["sitzungen"]}
        self.assertEqual(s["c-kx"]["kontext"], {"prozent": 64.0, "tokens": 640000, "fenster": 1000000,
                                                "modell": "Opus 5.5", "stufe": "warnung", "stand": self.now,
                                                "quelle": "statusline"})
        self.assertIsNone(s["c-leer"]["kontext"])

    def test_ruhende_sitzungen_nur_zwoelf_stunden(self):
        register.aktualisieren("claude", "c-neu", lambda d: d.update(cwd="/p/a", status="aktiv"))
        register.aktualisieren("claude", "c-alt", lambda d: d.update(cwd="/p/b", status="aktiv"))
        register.aktualisieren("claude", "c-wartet", lambda d: d.update(cwd="/p/c", status="gestoppt",
                                                                         fortsetzen_ab=self.now + 60))
        for sid in ("c-alt", "c-wartet"):
            datei = register._datei("claude", sid)
            d = util.lies_json(datei)
            d["zuletzt"] = self.now - 13 * 3600
            util.schreib_json(datei, d)
        ids = {x["id"] for x in self.status()["sitzungen"]}
        self.assertEqual(ids, {"c-neu", "c-wartet"}, "ruht und älter als 12 h: ausgeblendet; wartend bleibt")
        with open(self.konfig, "a", encoding="utf-8") as f:
            f.write("[anzeige]\nruht_stunden = 24\n")
        self.assertIn("c-alt", {x["id"] for x in self.status()["sitzungen"]})

    def test_claude_am_limit_setzt_selbst_fort(self):
        register.aktualisieren("claude", "c-lim", lambda d: d.update(
            cwd="/p/x", status="limit", ort="terminal", fortsetzen_ab=self.now + 600, reset=self.now + 480))
        s = {x["id"]: x for x in self.status()["sitzungen"]}["c-lim"]
        self.assertTrue(s["automatisch"], "ohne Nachtmodus: Claude setzt selbst fort")
        self.assertIn("selbst fort", s["lage_text"])
        self.assertNotIn("„weiter“", s["lage_text"])


class KonfigTest(TempHome):
    def test_neue_schluessel_und_pruefung(self):
        k = konfig.laden()
        self.assertEqual(k["schwellen"]["claude_stopp_art"], "sanft")
        self.assertEqual((k["kontext"]["warnung"], k["kontext"]["kritisch"], k["kontext"]["hinweis_an_sitzung"]),
                         (70, 85, False))
        self.assertTrue(k["statusline"]["anzeigen"])
        self.assertEqual(k["anzeige"]["ruht_stunden"], 12)
        self.assertEqual(konfig.pruefen(k), [])
        for abschnitt, schluessel, wert in (("schwellen", "claude_stopp_art", "hart"), ("kontext", "warnung", 90),
                                            ("kontext", "kritisch", 100), ("kontext", "standard_fenster", 10),
                                            ("kontext", "hinweis_an_sitzung", "ja"), ("statusline", "anzeigen", 1),
                                            ("anzeige", "ruht_stunden", -1)):
            with self.subTest(schluessel=schluessel):
                falsch = copy.deepcopy(k)
                falsch[abschnitt][schluessel] = wert
                self.assertTrue(konfig.pruefen(falsch))

    def test_config_toml_enthaelt_neue_schluessel(self):
        k = konfig.laden(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.toml"),
                         streng=True)
        self.assertEqual((k["schwellen"]["claude_stopp_art"], k["kontext"]["warnung"], k["kontext"]["kritisch"],
                          k["statusline"]["anzeigen"], k["anzeige"]["ruht_stunden"]), ("sanft", 70, 85, True, 12))


if __name__ == "__main__":
    unittest.main()
