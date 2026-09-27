"""v1.4 A: offizielle Nutzungsanzeige (Claude /api/oauth/usage, Codex /wham/usage), Quellenwahl, frühes Reset.

Nie echtes Netz, nie der echte Schlüsselbund: Opener und runner sind Attrappen, alles andere ist gesperrt.
"""

import contextlib
import io
import json
import os
import urllib.error
import urllib.request
from unittest import mock

from hilfe import TempHome, fixture, lies_fixture_json, nutzung as hilfe_nutzung

from lw import cli, melden, nutzung, phasen, quellen, register, sprache, tick, util
from lw.attrappe import OrcaAttrappe
from lw.kontext import Kontext

TOKEN = "fake-token-nicht-echt"
CODEX_TOKEN = "fake-codex-token-nicht-echt"
# So sieht der Schlüsselbund-Eintrag von Claude Code aus (nur Attrappe, kein echter Token).
SCHLUESSELBUND_ATTRAPPE = json.dumps({"claudeAiOauth": {
    "accessToken": TOKEN, "refreshToken": "fake-refresh-nicht-echt", "expiresAt": 1890000000000,
    "scopes": ["user:inference", "user:profile"], "subscriptionType": "max"}})


class _Antwort:
    def __init__(self, obj):
        self._roh = json.dumps(obj).encode()

    def read(self):
        return self._roh

    def close(self):
        pass


class _Runner:
    """Attrappe für subprocess.run (security find-generic-password)."""

    def __init__(self, stdout="", code=0):
        self.aufrufe = []
        self.stdout, self.code = stdout, code

    def __call__(self, args, **kw):
        self.aufrufe.append(args)
        return mock.Mock(returncode=self.code, stdout=self.stdout, stderr="")


class _Opener:
    """Attrappe für urlopen: gibt der Reihe nach Antworten zurück (dict) oder wirft (Exception)."""

    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.anfragen = []

    def __call__(self, req, timeout):
        self.anfragen.append(req)
        a = self.antworten.pop(0) if len(self.antworten) > 1 else self.antworten[0]
        if isinstance(a, BaseException):
            raise a
        return _Antwort(a)


def _http_fehler(code, retry=None):
    kopf = {"Retry-After": str(retry)} if retry is not None else {}
    return urllib.error.HTTPError("https://example.invalid", code, "x", kopf, io.BytesIO(b""))


def _verboten(*a, **kw):
    raise AssertionError("darf nicht aufgerufen werden")


class Basis(TempHome):
    def setUp(self):
        super().setUp()
        self.cred = SCHLUESSELBUND_ATTRAPPE
        self.k["daten"]["codex_auth"] = fixture("codex_auth.json")
        self.addCleanup(mock.patch.stopall)
        # Sicherheitsnetz: echtes Netz und echter Schlüsselbund sind in diesen Tests immer verboten
        mock.patch("lw.nutzung._http", side_effect=_verboten).start()
        mock.patch("urllib.request.urlopen", side_effect=_verboten).start()

    def online(self):
        os.environ["LIMIT_WAECHTER_OFFLINE"] = "0"

    def runner(self):
        return _Runner(self.cred)

    def ctx(self, orca=None):
        return Kontext(self.k, orca or OrcaAttrappe(), melden.Melder(self.k, dry_run=True), self.now, dry_run=True,
                       claude_agenten=[])


# ---------------------------------------------------------------- 1–4 Parser und Tokens

class ParserTest(Basis):
    def test_parse_claude(self):
        e = nutzung.parse_claude(lies_fixture_json("offiziell_claude.json"))
        self.assertEqual(e["quelle"], "offiziell")
        self.assertEqual(e["fuenf"]["pct"], 2.0)
        self.assertAlmostEqual(e["fuenf"]["reset"], 1790532000.27, places=2)
        self.assertEqual(e["fuenf"]["minuten"], 300)
        self.assertEqual(e["woche"]["pct"], 1.0)
        self.assertEqual(e["woche"]["minuten"], 10080)
        self.assertEqual([m["name"] for m in e["woche_modell"]], ["Fable"])
        self.assertEqual(e["woche_modell"][0]["pct"], 4.0)
        self.assertIsNone(nutzung.parse_claude({"unbekannt": 1}))
        self.assertIsNone(nutzung.parse_claude(None))

    def test_iso_zone(self):
        self.assertEqual(quellen.iso_zone_zu_epoch("2026-09-27T18:00:00Z"), 1790532000)
        self.assertEqual(quellen.iso_zone_zu_epoch("2026-09-27T20:00:00+02:00"), 1790532000)
        self.assertEqual(quellen.iso_zone_zu_epoch("2026-09-27T13:30:00-0430"), 1790532000)
        self.assertAlmostEqual(quellen.iso_zone_zu_epoch("2026-09-27T18:00:00.5+00:00"), 1790532000.5)
        self.assertIsNone(quellen.iso_zone_zu_epoch("morgen"))
        self.assertIsNone(quellen.iso_zone_zu_epoch(None))

    def test_parse_codex(self):
        e = nutzung.parse_codex(lies_fixture_json("offiziell_codex.json"))
        self.assertEqual(e["fuenf"], {"pct": 35.0, "reset": 1790528347.0, "minuten": 300})
        self.assertEqual(e["woche"]["minuten"], 10080)
        self.assertEqual(e["woche"]["reset"], 1790900000.0)
        self.assertFalse(e["erreicht"])
        self.assertIsNone(nutzung.parse_codex({"rate_limit": {}}))

    def test_claude_token(self):
        r = self.runner()
        token, fehler = nutzung.claude_token(self.k, r, self.now)
        self.assertEqual((token, fehler), (TOKEN, None))
        self.assertEqual(r.aufrufe[0][:4], ["/usr/bin/security", "find-generic-password", "-s",
                                           "Claude Code-credentials"])
        self.assertEqual(nutzung.claude_token(self.k, _Runner("", 44), self.now), (None, "kein_token"))
        self.assertEqual(nutzung.claude_token(self.k, _Runner("kein json"), self.now), (None, "kein_token"))

    def test_claude_token_abgelaufen_ohne_http(self):
        abgelaufen = json.dumps({"claudeAiOauth": {"accessToken": TOKEN, "expiresAt": (self.now - 60) * 1000}})
        self.assertEqual(nutzung.claude_token(self.k, _Runner(abgelaufen), self.now), (None, "abgelaufen"))
        opener = _Opener({})
        fehler = nutzung.abrufen(self.k, "claude", self.now, opener=opener, runner=_Runner(abgelaufen))
        self.assertEqual(fehler, "abgelaufen")
        self.assertEqual(opener.anfragen, [])

    def test_abgelaufen_nachts_push_nur_bei_wartender_sitzung(self):
        abgelaufen = json.dumps({"claudeAiOauth": {"accessToken": TOKEN, "expiresAt": (self.now - 60) * 1000}})
        nutzung.abrufen(self.k, "claude", self.now, opener=_Opener({}), runner=_Runner(abgelaufen))
        info = nutzung.info(self.k, self.now)
        ctx = self.ctx()
        tick._hinweis_offiziell_fehlt(ctx, info)
        self.assertEqual(ctx.melder.protokoll, [])          # niemand wartet: kein Push
        register.aktualisieren("claude", "0b1c2d3e-0000-4000-8000-00000000f0aa", lambda d: d.update(
            status="gestoppt", art="fuenf", reset=self.now + 3600, fortsetzen_ab=self.now + 3720,
            zuletzt=self.now))
        tick._hinweis_offiziell_fehlt(ctx, info)
        tick._hinweis_offiziell_fehlt(ctx, info)
        self.assertEqual(len(ctx.melder.protokoll), 1)      # einmal je Ausfall
        self.assertIn("hinterher", ctx.melder.protokoll[0]["text"])
        self.assertNotIn(TOKEN, ctx.melder.protokoll[0]["text"])

    def test_codex_token(self):
        self.assertEqual(nutzung.codex_token(self.k), (CODEX_TOKEN, "00000000-0000-4000-8000-000000000000"))
        datei = os.path.join(self.home, "auth.json")
        util.schreib_json(datei, {"OPENAI_API_KEY": "sk-x", "tokens": None})
        self.k["daten"]["codex_auth"] = datei
        self.assertEqual(nutzung.codex_token(self.k), (None, "kein_token"))
        self.k["daten"]["codex_auth"] = os.path.join(self.home, "fehlt.json")
        self.assertEqual(nutzung.codex_token(self.k), (None, "kein_token"))


# ---------------------------------------------------------------- 5–9 Abruf, Fehler, Drosselung

class AbrufTest(Basis):
    def test_erfolg_ohne_token_in_dateien(self):
        opener = _Opener(lies_fixture_json("offiziell_claude.json"))
        self.assertIsNone(nutzung.abrufen(self.k, "claude", self.now, opener=opener, runner=self.runner()))
        req = opener.anfragen[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertEqual(req.get_header("Anthropic-beta"), "oauth-2025-04-20")
        self.assertTrue(req.get_header("User-agent").startswith("agent-limit-watchdog/"))
        self.assertEqual(req.full_url, "https://api.anthropic.com/api/oauth/usage")
        opener = _Opener(lies_fixture_json("offiziell_codex.json"))
        self.assertIsNone(nutzung.abrufen(self.k, "codex", self.now, opener=opener))
        self.assertEqual(opener.anfragen[0].get_header("Chatgpt-account-id"), "00000000-0000-4000-8000-000000000000")
        self.assertEqual(opener.anfragen[0].get_header("Authorization"), "Bearer " + CODEX_TOKEN)
        cache = nutzung.cache_lesen()
        self.assertEqual(cache["claude"]["stand"], self.now)
        self.assertIsNone(cache["claude"]["fehler"])
        self.assertEqual(cache["codex"]["daten"]["fuenf"]["pct"], 35.0)
        self.assertEqual(os.stat(util.pfad(*nutzung.CACHE)).st_mode & 0o777, 0o600)
        # Fehlerwechsel erzeugt Logzeilen; auch dann nie der Token
        nutzung.abrufen(self.k, "claude", self.now + 200, opener=_Opener(_http_fehler(401)), runner=self.runner())
        util.ereignis("probe")
        for teile in (nutzung.CACHE, ("log", "waechter.log"), ("log", "ereignisse.jsonl")):
            with open(util.pfad(*teile), encoding="utf-8") as f:
                inhalt = f.read()
            self.assertNotIn(TOKEN, inhalt)
            self.assertNotIn(CODEX_TOKEN, inhalt)
            self.assertNotIn("fake-refresh", inhalt)
        lesen = nutzung.lesen(self.k, self.now)
        self.assertEqual(lesen["claude"]["quelle"], "offiziell")
        self.assertEqual(lesen["claude"]["stand"], self.now)      # alter Erfolg bleibt nutzbar

    def test_401_und_rueckfall(self):
        self.online()
        with open(os.path.join(self.home, "auth-kaputt.json"), "w") as f:
            f.write("{}")
        self.k["daten"]["codex_auth"] = os.path.join(self.home, "auth-kaputt.json")
        opener = _Opener(_http_fehler(401))
        with mock.patch("lw.nutzung._http", opener), \
                mock.patch("lw.nutzung.claude_token", return_value=(TOKEN, None)):
            reset = self.now + 3600
            util.schreib_json(util.pfad("state", "statusline.json"),
                              {"version": 1, "stand": self.now - 30, "fuenf": {"pct": 55, "reset": reset}})
            d = tick.daten_sammeln(self.ctx())
        self.assertEqual(len(opener.anfragen), 1)                  # Codex ohne Token: kein HTTP
        c = nutzung.cache_lesen()
        self.assertEqual(c["claude"]["fehler"], "auth")
        self.assertEqual(c["claude"]["naechster"], self.now + 900)
        self.assertEqual(c["codex"]["fehler"], "kein_token")
        self.assertEqual(d["claude"]["quelle"], "statusline")
        self.assertEqual(d["offiziell"]["claude"], {"zustand": "fehler", "fehler": "auth", "stand": None})
        self.assertFalse(nutzung.faellig(self.k, c["claude"], True, self.now + 600))
        self.assertTrue(nutzung.faellig(self.k, c["claude"], True, self.now + 900))

    def test_429_backoff(self):
        erwartet = [300, 600, 1200, 2400, 3600, 3600]
        now = self.now
        for b in erwartet:
            nutzung.abrufen(self.k, "claude", now, opener=_Opener(_http_fehler(429)), runner=self.runner())
            c = nutzung.cache_lesen()["claude"]
            self.assertEqual((c["fehler"], c["backoff_s"], c["naechster"]), ("rate", b, now + b))
            self.assertFalse(nutzung.faellig(self.k, c, True, now + b - 1))
            now += b
        nutzung.abrufen(self.k, "claude", now, opener=_Opener(lies_fixture_json("offiziell_claude.json")),
                        runner=self.runner())
        self.assertEqual(nutzung.cache_lesen()["claude"]["backoff_s"], 0)
        nutzung.abrufen(self.k, "claude", now + 200, opener=_Opener(_http_fehler(429, retry=5000)),
                        runner=self.runner())
        c = nutzung.cache_lesen()["claude"]
        self.assertEqual((c["backoff_s"], c["naechster"]), (5000, now + 200 + 5000))

    def test_netz_und_format(self):
        nutzung.abrufen(self.k, "claude", self.now, opener=_Opener(OSError("timeout")), runner=self.runner())
        c = nutzung.cache_lesen()["claude"]
        self.assertEqual((c["fehler"], c["naechster"]), ("netz", self.now + 180))
        nutzung.abrufen(self.k, "claude", self.now + 200, opener=_Opener(_http_fehler(503)), runner=self.runner())
        self.assertEqual(nutzung.cache_lesen()["claude"]["fehler"], "netz")
        self.assertEqual(nutzung.cache_lesen()["claude"]["fehler_seit"], self.now)
        nutzung.abrufen(self.k, "claude", self.now + 400, opener=_Opener({"anders": True}), runner=self.runner())
        self.assertEqual(nutzung.cache_lesen()["claude"]["fehler"], "format")
        self.assertIsNone(nutzung.lesen(self.k, self.now)["claude"])

    def test_netzfehler_im_tick_rueckfall_auf_orca(self):
        self.online()
        reset = self.now + 3600
        konten = {"rateLimits": {"claude": {"session": {"usedPercent": 40, "resetsAt": int(reset * 1000),
                                                        "windowMinutes": 300}, "updatedAt": int(self.now * 1000)}}}
        with mock.patch("lw.nutzung._http", _Opener(urllib.error.URLError("weg"))), \
                mock.patch("lw.nutzung.claude_token", return_value=(TOKEN, None)):
            d = tick.daten_sammeln(self.ctx(OrcaAttrappe(konten=konten)))
        self.assertEqual(d["claude"]["quelle"], "orca")
        self.assertEqual(nutzung.cache_lesen()["claude"]["fehler"], "netz")

    def test_drosselung(self):
        zaehler = _Opener(lies_fixture_json("offiziell_claude.json"))
        r = self.runner()
        self.k["daten"]["codex_auth"] = os.path.join(self.home, "fehlt.json")
        self.online()
        nutzung.aktualisieren(self.k, {}, [], self.now, opener=zaehler, runner=r)
        self.assertEqual(len(zaehler.anfragen), 1)
        nutzung.aktualisieren(self.k, {}, [], self.now + 60, opener=zaehler, runner=r)
        self.assertEqual(len(zaehler.anfragen), 1)                 # im Intervall (3 min): kein Abruf
        nutzung.aktualisieren(self.k, {"claude": {"phase": "warnung"}}, [], self.now + 60, opener=zaehler, runner=r)
        self.assertEqual(len(zaehler.anfragen), 2)                 # eng: jede Minute
        s = {"anbieter": "claude", "status": "gestoppt", "fortsetzen_ab": self.now + 60 + 600}
        nutzung.aktualisieren(self.k, {}, [s], self.now + 120, opener=zaehler, runner=r)
        self.assertEqual(len(zaehler.anfragen), 3)                 # Fortsetzung in 10 min: eng
        nutzung.aktualisieren(self.k, {}, [], self.now + 180, opener=zaehler, runner=r)
        self.assertEqual(len(zaehler.anfragen), 3)
        nutzung.aktualisieren(self.k, {}, [], self.now + 120 + 180, opener=zaehler, runner=r)
        self.assertEqual(len(zaehler.anfragen), 4)
        self.assertTrue(nutzung.eng_noetig({}, [{"status": "fortgesetzt", "geprueft": False}], self.now))
        self.assertFalse(nutzung.eng_noetig({}, [{"status": "gestoppt", "fortsetzen_ab": self.now + 3600}],
                                            self.now))

    def test_abgeschaltet(self):
        self.online()
        self.k["daten"]["offiziell"] = False
        d = tick.daten_sammeln(self.ctx())          # _http ist verboten: würde scheitern
        self.assertEqual(d["offiziell"]["claude"]["zustand"], "aus")


# ---------------------------------------------------------------- 10 Quellenwahl

class QuellenwahlTest(Basis):
    def _q(self, quelle, stand, pct=50):
        return {"fuenf": {"pct": pct, "reset": self.now + 3600}, "woche": None, "stand": stand, "quelle": quelle}

    def test_offiziell_hat_vorrang(self):
        off = self._q("offiziell", self.now - 120)
        sl = self._q("statusline", self.now - 60)
        orca = self._q("orca", self.now - 5)
        self.assertIs(phasen.waehle_quelle(off, orca, sl, now=self.now, max_alter_s=600), off)
        alt = self._q("offiziell", self.now - 660)
        self.assertIs(phasen.waehle_quelle(alt, orca, sl, now=self.now, max_alter_s=600), orca)
        ohne = self._q("orca", None)
        self.assertIs(phasen.waehle_quelle(ohne, sl, now=self.now, max_alter_s=600), sl)
        self.assertIs(phasen.waehle_quelle(ohne, None, now=self.now, max_alter_s=600), ohne)
        # ohne now wie bisher: frischester
        self.assertIs(phasen.waehle_quelle(off, sl), sl)


# ---------------------------------------------------------------- 11–13 frühes Reset

class FruehesResetTest(Basis):
    def setUp(self):
        super().setUp()
        self.reset_alt = self.now + 3 * 3600
        self.sid = "0b1c2d3e-0000-4000-8000-00000000f001"
        register.aktualisieren("claude", self.sid, lambda d: d.update(
            status="gestoppt", art="fuenf", reset=self.reset_alt, fortsetzen_ab=self.reset_alt + 120,
            zuletzt=self.now, cwd="/tmp/projekt"))
        self.zustand = {"nutzung": {"claude": {"pct5": 99.0, "reset5": self.reset_alt, "pctw": 40.0,
                                               "resetw": self.now + 3 * 86400, "quelle": "offiziell"}}}

    def _daten(self, pct, reset, quelle="offiziell", stand=None):
        return {"claude": {"fuenf": {"pct": pct, "reset": reset, "minuten": 300},
                           "woche": {"pct": 40.0, "reset": self.now + 3 * 86400, "minuten": 10080},
                           "stand": self.now if stand is None else stand, "quelle": quelle}, "codex": None}

    def test_abfall_macht_faellig_push_einmal(self):
        ctx = self.ctx()
        geaendert = tick._nach_daten(ctx, self._daten(3.0, self.now + 5 * 3600), self.zustand, register.alle())
        self.assertTrue(geaendert)
        s = register.lesen("claude", self.sid)
        self.assertEqual((s["fortsetzen_ab"], s["reset"]), (self.now, self.now))
        self.assertEqual(s["status"], "gestoppt")
        self.assertEqual(len(ctx.melder.protokoll), 1)
        self.assertIn("vorzeitig", ctx.melder.protokoll[0]["text"])
        self.assertEqual(self.zustand["nutzung"]["claude"]["pct5"], 3.0)
        # nächster Tick: nichts Neues
        ctx2 = self.ctx()
        self.assertFalse(tick._nach_daten(ctx2, self._daten(4.0, self.now + 5 * 3600), self.zustand,
                                          register.alle()))
        self.assertEqual(ctx2.melder.protokoll, [])
        typen = [e["typ"] for e in util.lies_ereignisse()]
        self.assertEqual(typen.count("fruehes_reset"), 1)

    def test_orca_sprung_loest_nichts_aus(self):
        ctx = self.ctx()
        self.zustand["nutzung"]["claude"]["quelle"] = "orca"
        self.assertFalse(tick._nach_daten(ctx, self._daten(71.0, self.reset_alt, quelle="orca"), self.zustand,
                                          register.alle()))
        self.assertEqual(register.lesen("claude", self.sid)["fortsetzen_ab"], self.reset_alt + 120)
        self.assertEqual(ctx.melder.protokoll, [])
        # alte Statusline zählt auch nicht
        self.assertFalse(tick._nach_daten(ctx, self._daten(3.0, self.reset_alt, quelle="statusline",
                                                           stand=self.now - 900),
                                          {"nutzung": {"claude": dict(self.zustand["nutzung"]["claude"],
                                                                      pct5=99.0)}}, register.alle()))

    def test_kleiner_abfall_nichts(self):
        ctx = self.ctx()
        self.assertFalse(tick._nach_daten(ctx, self._daten(91.0, self.reset_alt), self.zustand, register.alle()))
        self.assertEqual(ctx.melder.protokoll, [])

    def test_reset_nach_vorn(self):
        ctx = self.ctx()
        nr = self.reset_alt - 2 * 3600
        self.assertTrue(tick._nach_daten(ctx, self._daten(98.0, nr), self.zustand, register.alle()))
        s = register.lesen("claude", self.sid)
        # Fenster noch nicht zurückgesetzt: neues Reset + Puffer, nicht sofort (keine Doppel-Fortsetzung)
        self.assertEqual((s["fortsetzen_ab"], s["reset"]), (nr + 120, nr))
        self.assertEqual(s["fenster_id"], phasen.fenster_id("claude", "fuenf", nr))
        self.assertEqual(ctx.melder.protokoll, [])

    def test_reset_nach_vorn_und_gefallen_sofort(self):
        ctx = self.ctx()
        self.assertTrue(tick._nach_daten(ctx, self._daten(3.0, self.reset_alt - 2 * 3600), self.zustand,
                                         register.alle()))
        self.assertEqual(register.lesen("claude", self.sid)["fortsetzen_ab"], self.now)

    def test_normales_reset_ist_kein_fruehes(self):
        self.zustand["nutzung"]["claude"]["reset5"] = self.now + 120
        ctx = self.ctx()
        self.assertFalse(tick._nach_daten(ctx, self._daten(0.0, self.now + 5 * 3600), self.zustand,
                                          register.alle()))

    def test_tick_pflegt_zustand(self):
        ctx = self.ctx()
        tick.ausfuehren(ctx, sim={"claude": hilfe_nutzung(30, self.now + 3600, stand=self.now)},
                        mac_sim={"netzteil": True, "wach_bei_deckel_zu": True})
        z = util.lies_json(util.pfad(*tick.ZUSTAND))
        self.assertEqual(z["nutzung"]["claude"]["pct5"], 30.0)


# ---------------------------------------------------------------- 14–16 status und offline

class StatusTest(Basis):
    def setUp(self):
        super().setUp()
        self.konfig = os.path.join(self.home, "config.toml")
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write('[allgemein]\nsprache = "de"\n')
        os.environ["LIMIT_WAECHTER_CONFIG"] = self.konfig

    def cli(self, *args):
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            code = cli.main(list(args))
        return code, puffer.getvalue()

    def test_status_json_ruft_nie_ab(self):
        self.online()
        nutzung.abrufen(self.k, "claude", self.now - 60, opener=_Opener(lies_fixture_json("offiziell_claude.json")),
                        runner=self.runner())
        mock.patch("lw.nutzung.claude_token", side_effect=_verboten).start()
        mock.patch("lw.nutzung.codex_token", side_effect=_verboten).start()
        mock.patch("lw.nutzung.abrufen", side_effect=_verboten).start()
        # Daten des Fixtures liegen in der Zukunft (27.09. 18:00 UTC) -> aktives Fenster
        code, out = self.cli("status", "--json")
        self.assertEqual(code, 0)
        d = json.loads(out)
        p = d["phasen"]["claude"]
        self.assertEqual(p["quelle"], "offiziell")
        self.assertEqual(p["quelle_text"], "offiziell")
        self.assertEqual(p["pct5"], 2.0)
        self.assertEqual([m["name"] for m in p["woche_modell"]], ["Fable"])
        self.assertEqual(d["phasen"]["codex"]["woche_modell"], [])
        # Codex: je nach Rechner Orca oder keine Daten (status liest ein installiertes Orca nur)
        self.assertEqual(d["phasen"]["codex"]["quelle_text"],
                         cli.quelle_text(d["phasen"]["codex"]["quelle"] if d["phasen"]["codex"]["hat_daten"]
                                         else None))
        self.assertEqual(cli.quelle_text(None), "keine Daten")
        self.assertEqual(cli.quelle_text("rollout"), "Codex-Protokoll")
        self.assertEqual(d["offiziell"]["claude"], {"zustand": "ok", "fehler": None, "stand": self.now - 60})
        self.assertEqual(d["offiziell"]["codex"]["zustand"], "fehler")
        self.assertEqual(set(d["gesamt"]), {"stufe", "text", "detail"})
        code, out = self.cli("status")
        self.assertIn("Claude-Quelle: offiziell (vor 60 s)", out)
        self.assertIn("offizielle Anzeige Codex: noch kein Abruf", out)

    def _ausgabe(self, **extra):
        a = {"launchagent": True, "letzter_tick": self.now - 30, "pausiert": False, "pause_bis": None,
             "orca_ok": True, "phasen": {"claude": {"phase": "ok", "pct": 10.0, "reset": self.now + 3600,
                                                    "art": "fuenf"},
                                         "codex": {"phase": "ok", "pct": 5.0, "reset": None, "art": "fuenf"}}}
        a.update(extra)
        return a

    def _gesamt(self, sitzungen=(), **extra):
        return cli.gesamt(self._ausgabe(**extra), self.k, self.now, list(sitzungen))

    def test_gesamt_stufen(self):
        for sp, erwartet in (("de", {"ok": "Alles gut", "stoerung": "Wächter läuft nicht", "pause": "Pausiert",
                                     "stopp": "Stopp – Reset", "limit": "Limit – Reset",
                                     "warnung": "Claude: Warnung – 85 %", "wartet": "1 Sitzung(en) warten"}),
                             ("en", {"ok": "All good", "stoerung": "Watchdog is not running", "pause": "Paused",
                                     "stopp": "Stop - resets", "limit": "Limit - resets",
                                     "warnung": "Claude: warning - 85%", "wartet": "1 session(s) waiting"})):
            with self.subTest(sprache=sp):
                sprache.setzen(sp)
                g = self._gesamt()
                self.assertEqual((g["stufe"], g["text"], g["detail"]), ("ok", erwartet["ok"], None))
                g = self._gesamt(launchagent=False)
                self.assertEqual((g["stufe"], g["text"]), ("stoerung", erwartet["stoerung"]))
                g = self._gesamt(letzter_tick=self.now - 600)
                self.assertEqual(g["stufe"], "stoerung")
                g = self._gesamt(pausiert=True, launchagent=True)
                self.assertEqual((g["stufe"], g["text"]), ("pause", erwartet["pause"]))
                g = self._gesamt(pausiert=True, pause_bis=self.now + 1800)
                self.assertIn(util.uhrzeit(self.now + 1800, self.now), g["text"])
                ph = self._ausgabe()["phasen"]
                ph["claude"] = {"phase": "warnung", "pct": 85.0, "reset": self.now + 3600, "art": "fuenf"}
                g = self._gesamt(phasen=ph)
                self.assertEqual(g["stufe"], "warnung")
                self.assertTrue(g["text"].startswith(erwartet["warnung"]), g["text"])
                ph["codex"] = {"phase": "stopp", "pct": 93.0, "reset": self.now + 1800, "art": "fuenf"}
                g = self._gesamt(phasen=ph)
                self.assertEqual(g["stufe"], "stopp")
                self.assertEqual(g["text"], erwartet["stopp"] + " " + util.uhrzeit(self.now + 1800, self.now))
                self.assertIn("Codex", g["detail"])
                ph["claude"] = {"phase": "limit", "pct": 100.0, "reset": self.now + 3600, "art": "fuenf"}
                g = self._gesamt(phasen=ph)
                self.assertEqual(g["stufe"], "limit")
                self.assertTrue(g["text"].startswith(erwartet["limit"]))
                s = {"anbieter": "claude", "id": "x", "status": "wartet_auf_weiter", "zuletzt": self.now}
                g = self._gesamt([s])
                self.assertEqual((g["stufe"], g["text"]), ("wartet", erwartet["wartet"]))
                g = self._gesamt([dict(s, zuletzt=self.now - 3 * 86400)])
                self.assertEqual(g["stufe"], "ok")
                g = self._gesamt([s], pausiert=True, launchagent=False)
                self.assertEqual(g["stufe"], "stoerung")
        sprache.setzen("de")

    def test_offline_nie_schluesselbund_oder_netz(self):
        mock.patch("lw.nutzung.claude_token", side_effect=_verboten).start()
        mock.patch("lw.nutzung.codex_token", side_effect=_verboten).start()
        self.assertTrue(util.offline())
        ctx = self.ctx()
        tick.ausfuehren(ctx, mac_sim={"netzteil": True, "wach_bei_deckel_zu": True})
        d = tick.daten_sammeln(ctx)
        self.assertIsNone(d["claude_quellen"]["offiziell"])
        self.assertFalse(os.path.exists(util.pfad(*nutzung.CACHE)))


class KonfigTest(Basis):
    def test_pruefung(self):
        from lw import konfig
        self.assertEqual(konfig.pruefen(self.k), [])
        for name, wert in (("offiziell_intervall_minuten", 0), ("offiziell_intervall_eng_minuten", 5),
                           ("offiziell_max_alter_minuten", 1), ("frueh_reset_abfall", 2),
                           ("offiziell_timeout_sekunden", 1.5),
                           ("claude_usage_url", "http://api.anthropic.com/api/oauth/usage"),
                           ("claude_usage_url", "https://api.anthropic.com.evil.example/x"),
                           ("codex_usage_url", "https://example.com/backend-api/wham/usage")):
            with self.subTest(name=name):
                k = dict(self.k, daten=dict(self.k["daten"], **{name: wert}))
                self.assertTrue(konfig.pruefen(k))
        from lw import konfig as kf
        standard = kf.laden(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                         "config.toml"), streng=True)
        self.assertTrue(standard["daten"]["offiziell"])
        self.assertEqual(standard["daten"]["offiziell_intervall_minuten"], 3)
        self.assertEqual(standard["daten"]["orca"], "/Applications/Orca.app/Contents/Resources/bin/orca")
        sprache.setzen("de")


class TokenSchutzTest(Basis):
    def test_url_erlaubt(self):
        self.assertTrue(nutzung.url_erlaubt("claude", "https://api.anthropic.com/api/oauth/usage"))
        self.assertTrue(nutzung.url_erlaubt("codex", "https://chatgpt.com/backend-api/wham/usage"))
        for url in ("http://api.anthropic.com/api/oauth/usage", "https://api.anthropic.com:8443/x",
                    "https://user:pw@api.anthropic.com/x", "https://chatgpt.com/x", "", "kaputt://"):
            with self.subTest(url=url):
                self.assertFalse(nutzung.url_erlaubt("claude", url))

    def test_falsche_url_ohne_token_und_netz(self):
        self.k["daten"]["claude_usage_url"] = "http://example.com/usage"
        runner = self.runner()
        opener = _Opener({})
        self.assertEqual(nutzung.abrufen(self.k, "claude", self.now, opener=opener, runner=runner), "url")
        self.assertEqual((runner.aufrufe, opener.anfragen), ([], []))

    def test_weiterleitung_wird_nicht_verfolgt(self):
        handler = nutzung._KeineWeiterleitung()
        req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage",
                                     headers={"Authorization": "Bearer " + TOKEN})
        self.assertIsNone(handler.redirect_request(req, None, 302, "Found", {}, "http://evil.example/"))
        self.assertTrue(any(isinstance(h, nutzung._KeineWeiterleitung) for h in nutzung._OPENER.handlers))
        self.assertFalse(any(type(h) is urllib.request.HTTPRedirectHandler for h in nutzung._OPENER.handlers))
