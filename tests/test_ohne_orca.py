"""v1.3 ohne Orca: Orca optional, Claude-Quellen mischen, Codex außerhalb von Orca (codex queue), Fortsetzen per Push.

Nie ein echter Modellaufruf: subprocess.run ist überall gemockt, wo `codex queue` laufen könnte.
"""

import json
import os
import time
import unittest
from unittest import mock

from hilfe import TempHome, nutzung

from lw import melden, nacht, register, texte, tick, util
from lw.attrappe import OrcaAttrappe
from lw.kontext import Kontext
from lw.orca import Orca

MAC_OK = {"netzteil": True, "wach_bei_deckel_zu": True, "schlaf_aus": True}
TUI = "0b1c2d3e-0000-4000-8000-00000000a001"
DESK = "0b1c2d3e-0000-4000-8000-00000000a002"
EXEC = "0b1c2d3e-0000-4000-8000-00000000a003"
SUB = "0b1c2d3e-0000-4000-8000-00000000a004"


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


class _Ergebnis:
    def __init__(self, code=0):
        self.returncode = code
        self.stdout = ""
        self.stderr = ""


class OhneOrcaTest(TempHome):
    def setUp(self):
        super().setUp()
        self.k["wach"]["caffeinate"] = False
        self.assertFalse(self.k["fortsetzen"]["codex_queue"], "Standard: aus (im Echttest nicht belegt)")
        self.k["fortsetzen"]["codex_queue"] = True        # die meisten Tests prüfen den eingeschalteten Weg
        self.reset = self.now + 3600
        self.orca = OrcaAttrappe()
        self.run = mock.patch("lw.fortsetzen.subprocess.run", return_value=_Ergebnis(0)).start()
        self.addCleanup(mock.patch.stopall)

    # ------------------------------------------------------------ Helfer
    def rollout(self, tid, originator="codex-tui", source="cli", laeuft=True, cwd="/Users/alex/projekt"):
        tag = os.path.join(self.k["daten"]["codex_sessions"], time.strftime("%Y/%m/%d", time.localtime(self.now)))
        os.makedirs(tag, exist_ok=True)
        datei = os.path.join(tag, f"rollout-2026-09-26T07-00-00-{tid}.jsonl")
        zeilen = [{"timestamp": _iso(self.now - 1200), "type": "session_meta",
                   "payload": {"id": tid, "cwd": cwd, "originator": originator, "source": source}},
                  {"timestamp": _iso(self.now - 600), "type": "event_msg", "payload": {"type": "task_started"}}]
        if not laeuft:
            zeilen.append({"timestamp": _iso(self.now - 300), "type": "event_msg",
                           "payload": {"type": "task_complete", "last_agent_message": "fertig"}})
        with open(datei, "w") as f:
            f.write("\n".join(json.dumps(z) for z in zeilen) + "\n")
        os.utime(datei, (self.now, self.now))
        return datei

    def lauf(self, codex=None, claude=None, orca=None, sim_extra=None):
        melder = melden.Melder(self.k, dry_run=True)
        self.ctx = Kontext(self.k, orca or self.orca, melder, self.now, dry_run=False, claude_agenten=[])
        sim = {"claude": claude or nutzung(5, self.now + 7200, stand=self.now),
               "codex": codex or nutzung(5, self.now + 7200, stand=self.now)}
        sim.update(sim_extra or {})
        return tick.ausfuehren(self.ctx, sim=sim, mac_sim=MAC_OK)

    def stopp(self):
        return nutzung(93, self.reset, stand=self.now)

    def queue_aufrufe(self):
        return [c.args[0] for c in self.run.call_args_list if c.args and c.args[0][1:2] == ["queue"]]

    def wartend(self, anbieter, sid, ort, status="gestoppt", reset=None, **extra):
        reset = reset or self.now - 600

        def f(d):
            d.update({"cwd": "/Users/alex/projekt", "ort": ort})
            register.warten_auf_reset(d, status, f"{anbieter}-fuenf-{int(round(reset / 600))}", reset, "fuenf", 120)
            d.update(extra)
        register.aktualisieren(anbieter, sid, f)

    # ------------------------------------------------------------ Orca fehlt
    def test_orca_fehlt_keine_aufrufe_kein_fehler(self):
        orca = Orca(os.path.join(self.home, "gibt-es-nicht", "orca"))
        self.wartend("claude", "sess-O", "orca", reset=self.now + 600)
        with mock.patch("lw.orca.subprocess.run") as orca_run, mock.patch("lw.kontext.subprocess.run") as k_run:
            melder = melden.Melder(self.k, dry_run=True)
            ctx = Kontext(self.k, orca, melder, self.now, dry_run=True, claude_agenten=[])
            daten = tick.daten_sammeln(ctx)
            erg = tick.ausfuehren(ctx, mac_sim=MAC_OK)
        orca_run.assert_not_called()
        k_run.assert_not_called()
        self.assertFalse(daten["orca_vorhanden"])
        self.assertEqual(daten["fehler"], [])
        self.assertEqual(ctx.terminals(), [])
        self.assertEqual(ctx.agenten(), {})
        self.assertFalse(any("Orca nicht erreichbar" in m["text"] for m in erg["meldungen"]))
        self.assertIsNone(ctx.orca_fehler)
        self.assertFalse(util.lies_json(util.pfad("state", "current.json"))["nur_orca"])

    def test_orca_weg_nur_bei_orca_sitzung(self):
        self.orca._erreichbar = False
        self.wartend("claude", "sess-T", "terminal", reset=self.now + 600)
        erg = self.lauf(sim_extra={"orca_ok": False, "fehler": ["weg"]})
        self.assertFalse(any("Orca nicht erreichbar" in m["text"] for m in erg["meldungen"]))

    # ------------------------------------------------------------ Claude-Quellen
    def _konten(self, stand):
        ms = int(stand * 1000)
        return {"rateLimits": {"claude": {"session": {"usedPercent": 30, "resetsAt": int(self.reset * 1000),
                                                      "windowMinutes": 300}, "updatedAt": ms}}}

    def _statusline(self, stand, pct=60):
        util.schreib_json(util.pfad("state", "statusline.json"),
                          {"version": 1, "stand": stand, "fuenf": {"pct": pct, "reset": self.reset}, "woche": None})

    def test_statusline_frischer_als_orca(self):
        self._statusline(self.now - 10)
        ctx = Kontext(self.k, OrcaAttrappe(konten=self._konten(self.now - 120)), melden.Melder(self.k, dry_run=True),
                      self.now, dry_run=True)
        d = tick.daten_sammeln(ctx)
        self.assertEqual(d["claude"]["quelle"], "statusline")
        self.assertEqual(d["claude_quellen"], {"orca": self.now - 120, "statusline": self.now - 10, "offiziell": None})

    def test_orca_frischer_als_statusline(self):
        self._statusline(self.now - 300)
        ctx = Kontext(self.k, OrcaAttrappe(konten=self._konten(self.now - 20)), melden.Melder(self.k, dry_run=True),
                      self.now, dry_run=True)
        d = tick.daten_sammeln(ctx)
        self.assertEqual(d["claude"]["quelle"], "orca")
        self.assertTrue(d["orca_vorhanden"])

    # ------------------------------------------------------------ Codex außerhalb von Orca
    def test_codex_tui_registriert_und_stopp_per_queue_einmal(self):
        self.rollout(TUI)
        self.lauf(codex=self.stopp())
        self.lauf(codex=nutzung(94, self.reset, stand=self.now))
        s = register.lesen("codex", TUI)
        self.assertEqual(s["ort"], "terminal")
        self.assertNotIn("terminal", s)
        aufrufe = self.queue_aufrufe()
        self.assertEqual(len(aufrufe), 1)
        p = self.ctx.k["fortsetzen"]
        self.assertEqual(aufrufe[0][:5], [p["codex_befehl"], "queue", "--thread", TUI, "--message"])
        self.assertEqual(len(aufrufe[0]), 6)
        self.assertIn("Codex-Nutzungslimit ist fast erreicht", aufrufe[0][5])
        kw = self.run.call_args.kwargs
        self.assertEqual(kw.get("timeout"), 60)
        self.assertFalse(kw.get("shell", False))
        self.assertEqual((s["status"], s["fortsetzen_ab"]), ("gestoppt", self.reset + 120))
        self.assertEqual(self.orca.gesendet, [])

    def test_codex_desktop_ohne_stopp(self):
        self.rollout(DESK, originator="Codex Desktop", source="vscode")
        self.lauf(codex=self.stopp())
        self.assertEqual(register.lesen("codex", DESK)["ort"], "desktop")
        self.assertEqual(self.queue_aufrufe(), [])

    def test_codex_exec_und_subagent_ignoriert(self):
        self.rollout(EXEC, originator="codex_exec", source="exec")
        self.rollout(SUB, source={"subagent": {"parent": TUI}})
        self.lauf(codex=self.stopp())
        self.assertIsNone(register.lesen("codex", EXEC))
        self.assertIsNone(register.lesen("codex", SUB))
        self.assertEqual(self.queue_aufrufe(), [])

    def test_codex_queue_aus_kein_aufruf(self):
        self.k["fortsetzen"]["codex_queue"] = False
        self.rollout(TUI)
        self.lauf(codex=self.stopp())
        self.assertEqual(self.queue_aufrufe(), [])
        self.assertEqual(register.lesen("codex", TUI)["ort"], "terminal")

    def test_queue_fehler_nur_log(self):
        self.run.return_value = _Ergebnis(1)
        self.rollout(TUI)
        self.lauf(codex=self.stopp())
        self.lauf(codex=self.stopp())
        self.assertEqual(len(self.queue_aufrufe()), 1)
        self.assertEqual(register.lesen("codex", TUI)["status"], "aktiv")

    def test_dry_run_kein_queue(self):
        self.rollout(TUI)
        ctx = Kontext(self.k, self.orca, melden.Melder(self.k, dry_run=True), self.now, dry_run=True,
                      claude_agenten=[])
        tick.ausfuehren(ctx, sim={"claude": nutzung(5, self.now + 7200, stand=self.now), "codex": self.stopp()},
                        mac_sim=MAC_OK)
        self.run.assert_not_called()

    def test_nur_orca_wie_12(self):
        self.k["allgemein"]["nur_orca"] = True
        self.rollout(TUI)
        self.lauf(codex=self.stopp())
        self.assertIsNone(register.lesen("codex", TUI))
        self.assertEqual(self.queue_aufrufe(), [])
        self.assertTrue(util.lies_json(util.pfad("state", "current.json"))["nur_orca"])

    # ------------------------------------------------------------ Fortsetzen
    def test_codex_fortsetzen_ohne_nachtmodus_wartet(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = True
        self.wartend("codex", TUI, "terminal")
        self.lauf()
        self.assertEqual(self.queue_aufrufe(), [])
        self.assertEqual(register.lesen("codex", TUI)["status"], "wartet_auf_weiter")

    def test_codex_fortsetzen_per_queue_mit_nachtmodus(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = True
        nacht.alle_an(self.now)
        self.wartend("codex", TUI, "terminal")
        self.lauf()
        aufrufe = self.queue_aufrufe()
        self.assertEqual(len(aufrufe), 1)
        self.assertEqual(aufrufe[0][5], texte.fortsetzungsprompt())
        s = register.lesen("codex", TUI)
        self.assertEqual(s["status"], "fortgesetzt")
        self.assertEqual(self.orca.gesendet, [])

    def test_codex_fortsetzen_hoechstens_max_pro_fenster(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = False
        maxi = self.k["fortsetzen"]["max_pro_fenster"]
        self.wartend("codex", TUI, "terminal")
        fid = register.lesen("codex", TUI)["fenster_id"]
        register.aktualisieren("codex", TUI, lambda d: d["versuche"].update({fid: maxi}))
        self.lauf()
        self.assertEqual(self.queue_aufrufe(), [])
        self.assertEqual(register.lesen("codex", TUI)["status"], "aufgegeben")

    def test_codex_desktop_fortsetzen_nur_push(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = False
        self.wartend("codex", DESK, "desktop")
        erg = self.lauf()
        self.assertEqual(self.queue_aufrufe(), [])
        self.assertEqual(register.lesen("codex", DESK)["status"], "wartet_auf_weiter")
        self.assertTrue(any(f"codex resume {DESK}" in m["text"] for m in erg["meldungen"]))

    def test_claude_ausserhalb_nach_reset_push_mit_befehl(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = True
        nacht.alle_an(self.now)
        self.wartend("claude", "sess-T", "terminal")
        erg = self.lauf()
        self.assertEqual(register.lesen("claude", "sess-T")["status"], "wartet_auf_weiter")
        self.assertTrue(any("claude --resume sess-T" in m["text"] for m in erg["meldungen"]), erg["meldungen"])
        self.assertEqual(self.orca.gesendet, [])        # nie orca.erstellen / senden
        self.run.assert_not_called()

    def test_claude_ausserhalb_karenz_bleibt(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = False
        self.wartend("claude", "sess-T", "terminal", status="limit", reset=self.now - 60)
        self.lauf()
        self.assertEqual(register.lesen("claude", "sess-T")["status"], "limit")

    def test_codex_queue_nicht_wenn_thread_schon_laeuft(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = False
        self.wartend("codex", TUI, "terminal", status="limit")
        self.rollout(TUI, laeuft=True)                  # Nutzer hat selbst weitergetippt
        self.lauf()
        self.assertEqual(self.queue_aufrufe(), [])
        s = register.lesen("codex", TUI)
        self.assertEqual(s["status"], "fortgesetzt")
        self.assertEqual(s["versuche"].get(s["fenster_id"], 0), 0)

    def test_codex_orca_sitzung_ohne_terminal_bleibt_orca(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = False
        self.wartend("codex", TUI, "orca", terminal="term_alt", pane_key="alt:1")
        self.rollout(TUI, laeuft=False, cwd="/tmp")
        register.aktualisieren("codex", TUI, lambda d: d.update({"cwd": "/tmp"}))
        self.lauf()
        s = register.lesen("codex", TUI)
        self.assertEqual(s["ort"], "orca")
        self.assertEqual(self.queue_aufrufe(), [])
        self.assertTrue(any("erstellen" in g and f"codex resume {TUI}" in g["befehl"] for g in self.orca.gesendet),
                        self.orca.gesendet)

    def test_pruefung_ueber_rollout(self):
        self.k["fortsetzen"]["nur_mit_nachtmodus"] = False
        self.wartend("codex", TUI, "terminal")
        self.lauf()
        self.assertEqual(register.lesen("codex", TUI)["status"], "fortgesetzt")
        self.setze_zeit(self.now + 700)
        erg = self.lauf()
        self.assertTrue(register.lesen("codex", TUI)["geprueft"])
        self.assertTrue(any("nicht wiedergefunden" in m["text"] for m in erg["meldungen"]))


if __name__ == "__main__":
    unittest.main()
