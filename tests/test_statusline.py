"""Statusline-Kette hooks/statusline.py als Unterprozess (wie Claude Code sie aufruft)."""

import json
import os
import re
import stat
import subprocess
import time
import unittest

from hilfe import PROJEKT, TempHome, fixture

from lw import quellen, util

SKRIPT = os.path.join(PROJEKT, "hooks", "statusline.py")
ANSI = re.compile(r"\033\[[0-9;]*m")


def ohne_farben(b):
    return ANSI.sub("", b.decode("utf-8"))


class StatuslineTest(TempHome):
    def setUp(self):
        super().setUp()
        with open(fixture("statusline_payload.json"), "rb") as f:
            self.payload = f.read()
        self.datei = os.path.join(self.home, "state", "statusline.json")

    def original(self, befehl, **mehr):
        eintrag = dict({"type": "command", "command": befehl}, **mehr) if befehl is not None else None
        util.schreib_json(util.pfad("state", "statusline-original.json"),
                          {"version": 1, "gesichert": self.now, "statusLine": eintrag})

    def ruf(self, eingabe=None, env_mehr=None):
        env = dict(os.environ)
        env.pop("COLUMNS", None)
        env.update(env_mehr or {})
        return subprocess.run(["/usr/bin/python3", SKRIPT], input=self.payload if eingabe is None else eingabe,
                              capture_output=True, env=env, timeout=20)

    def test_schreibt_datei_und_reicht_original_durch(self):
        self.original("cat >/dev/null; printf 'orca-zeile\\n'; printf 'warnung' >&2; exit 3", padding=0)
        r = self.ruf()
        self.assertEqual((r.returncode, r.stderr), (3, b"warnung"))
        zeilen = r.stdout.split(b"\n")
        self.assertEqual(zeilen[0], b"orca-zeile", "Original zuerst und unverändert")
        self.assertIn("ctx", ohne_farben(zeilen[1]), "danach die eigene Zeile")
        d = util.lies_json(self.datei)
        self.assertEqual(d["version"], 1)
        self.assertEqual(d["fuenf"], {"pct": 84.0, "reset": 1790451000})
        self.assertEqual(d["woche"], {"pct": 65.0, "reset": 1790470800})
        self.assertEqual(d["stand"], self.now)
        sl = quellen.claude_statusline(self.datei)
        self.assertEqual((sl["quelle"], sl["fuenf"]["pct"], sl["woche"]["minuten"]), ("statusline", 84.0, 10080))

    def test_original_bekommt_unveraenderte_bytes_und_umgebung(self):
        ziel = os.path.join(self.home, "kopie.bin")
        self.original(f"cat > '{ziel}'; printf '%s' \"$LW_PROBE\"")
        eingabe = self.payload + b"\n\xff"
        r = self.ruf(eingabe, {"LW_PROBE": "x y"})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"x y", b""))
        with open(ziel, "rb") as f:
            self.assertEqual(f.read(), eingabe)

    def test_ohne_original_eigene_zeile(self):
        util.schreib_json(util.pfad("state", "current.json"), {"statusline_anzeigen": False})
        r = self.ruf()
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertEqual(r.stdout.decode(), "5h 84% · week 65%\n")
        util.schreib_json(util.pfad("state", "current.json"), {"sprache": "de", "statusline_anzeigen": False})
        self.original(None)
        self.assertEqual(self.ruf().stdout.decode(), "5h 84% · Woche 65%\n")
        self.original("   ")
        self.assertEqual(self.ruf().returncode, 0)

    def test_kein_selbstaufruf(self):
        self.original(f"/usr/bin/python3 '{SKRIPT}' # limit-watchdog-statusline")
        r = self.ruf()
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertIn("84%", r.stdout.decode())

    def test_kaputtes_json_und_leere_eingabe(self):
        self.original("cat >/dev/null; echo ok")
        for eingabe in (b"kein json", b"", b"[1, 2]", b'{"rate_limits": {"five_hour": {"used_percentage": "x"}}}'):
            r = self.ruf(eingabe)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"ok\n", b""), eingabe)
        self.assertFalse(os.path.exists(self.datei))
        r = self.ruf(b"")
        self.assertEqual(r.returncode, 0)

    def test_ohne_rate_limits_nichts_geschrieben(self):
        daten = json.loads(self.payload)
        del daten["rate_limits"]
        r = self.ruf(json.dumps(daten).encode())
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertEqual(ohne_farben(r.stdout), "Opus 5.5 · ctx ░░░░░░░░░░ 2% 20k/1M\n", "Segmente ohne Daten fehlen")
        self.assertFalse(os.path.exists(self.datei))
        util.schreib_json(util.pfad("state", "current.json"), {"statusline_anzeigen": False})
        self.assertEqual(self.ruf(json.dumps(daten).encode()).stdout.decode(), "5h – · week –\n")

    def test_drosselung(self):
        self.ruf()
        self.assertEqual(util.lies_json(self.datei)["stand"], self.now)
        self.ruf(env_mehr={"LIMIT_WAECHTER_NOW": str(self.now + 10)})
        self.assertEqual(util.lies_json(self.datei)["stand"], self.now, "gleiche Werte innerhalb 20 s: nicht schreiben")
        daten = json.loads(self.payload)
        daten["rate_limits"]["five_hour"]["used_percentage"] = 85
        self.ruf(json.dumps(daten).encode(), {"LIMIT_WAECHTER_NOW": str(self.now + 12)})
        d = util.lies_json(self.datei)
        self.assertEqual((d["stand"], d["fuenf"]["pct"]), (self.now + 12, 85.0), "neue Werte sofort")
        self.ruf(json.dumps(daten).encode(), {"LIMIT_WAECHTER_NOW": str(self.now + 40)})
        self.assertEqual(util.lies_json(self.datei)["stand"], self.now + 40)

    def test_ohne_schreibrechte(self):
        self.original("cat >/dev/null; echo ok")
        state = os.path.join(self.home, "state")
        os.chmod(state, stat.S_IRUSR | stat.S_IXUSR)
        try:
            r = self.ruf()
        finally:
            os.chmod(state, 0o700)
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertTrue(r.stdout.startswith(b"ok\n"))
        self.assertIn("5h 84%", ohne_farben(r.stdout), "anzeigen geht auch ohne Schreibrechte")
        self.assertFalse(os.path.exists(self.datei))


class TerminalZeileTest(TempHome):
    """v1.4 N5: sichtbare eigene Zeile unter der Original-Statusline."""

    def setUp(self):
        super().setUp()
        with open(fixture("statusline_payload.json"), encoding="utf-8") as f:
            self.daten = json.load(f)
        self.daten["context_window"] = {"context_window_size": 1000000, "used_percentage": 41,
                                        "current_usage": {"input_tokens": 2000, "cache_creation_input_tokens": 10000,
                                                          "cache_read_input_tokens": 400000, "output_tokens": 900}}
        self.daten["rate_limits"]["five_hour"]["used_percentage"] = 63
        self.daten["rate_limits"]["seven_day"]["used_percentage"] = 38
        self.uhr = time.strftime("%H:%M", time.localtime(1790451000))

    def ruf(self, spalten=None, daten=None, roh=None):
        env = dict(os.environ)
        env.pop("COLUMNS", None)
        if spalten:
            env["COLUMNS"] = str(spalten)
        eingabe = roh if roh is not None else json.dumps(daten or self.daten).encode()
        r = subprocess.run(["/usr/bin/python3", SKRIPT], input=eingabe, capture_output=True, env=env, timeout=20)
        self.assertEqual(r.stderr, b"")
        return r

    def test_zielzeile_mit_farben(self):
        r = self.ruf()
        self.assertEqual(ohne_farben(r.stdout),
                         f"Opus 5.5 · ctx ████░░░░░░ 41% 412k/1M · 5h 63% ↻{self.uhr} · wk 38%\n")
        self.assertIn("\033[32m41%", r.stdout.decode(), "Kontext unter der Warnschwelle grün")
        self.assertIn("\033[2m", r.stdout.decode(), "Trenner gedimmt")

    def test_farben_nach_schwellen_und_nachtmodus(self):
        util.schreib_json(util.pfad("state", "current.json"), {
            "sprache": "de", "kontext": {"warnung": 30, "kritisch": 40},
            "schwellen": {"warnung": 50, "stopp": 60, "woche_warnung": 30, "woche_stopp": 90}})
        util.schreib_json(util.pfad("state", "nacht.json"), {"alle_bis": self.now + 3600})
        r = self.ruf()
        text = r.stdout.decode()
        self.assertIn("\033[31m41%", text, "Kontext kritisch rot")
        self.assertIn("\033[31m63%", text, "5h über Stopp rot")
        self.assertIn("\033[33m38%", text, "Woche über Warnung gelb")
        self.assertIn("Wo 38%", ohne_farben(r.stdout))
        self.assertTrue(ohne_farben(r.stdout).rstrip().endswith("☾"))

    def test_schmale_terminals(self):
        erwartet = {
            90: f"Opus 5.5 · ctx ████░░░░░░ 41% · 5h 63% ↻{self.uhr} · wk 38%",
            70: f"Opus 5.5 · ctx ██░░░ 41% · 5h 63% ↻{self.uhr} · wk 38%",
            50: "Opus 5.5 · ctx ██░░░ 41% · 5h 63%",
            30: "ctx 41% · 5h 63%",
        }
        for spalten, zeile in erwartet.items():
            with self.subTest(spalten=spalten):
                ausgabe = ohne_farben(self.ruf(spalten).stdout).rstrip("\n")
                self.assertEqual(ausgabe, zeile)
                self.assertLessEqual(len(ausgabe), spalten)

    def test_speichert_kontext_ohne_inhalte(self):
        self.ruf()
        from lw import kontextfenster
        d = kontextfenster.lesen("claude", self.daten["session_id"])
        self.assertEqual((d["prozent"], d["tokens"], d["fenster"], d["modell"], d["quelle"]),
                         (41.2, 412000, 1000000, "Opus 5.5", "statusline"))
        self.assertNotIn("transcript_path", json.dumps(d))
        self.assertNotIn("cwd", d)

    def test_ohne_zahlen_nichts_ueberschrieben_nach_compact_null(self):
        self.ruf()
        leer = dict(self.daten, context_window={"context_window_size": 1000000, "current_usage": None,
                                                "used_percentage": None})
        r = self.ruf(daten=leer)
        from lw import kontextfenster
        self.assertEqual(kontextfenster.lesen("claude", self.daten["session_id"])["prozent"], 41.2)
        self.assertIn("41%", ohne_farben(r.stdout), "letzter bekannter Stand")
        tr = os.path.join(self.home, "t.jsonl")
        with open(tr, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-09-26T05:00:00Z",
                                "message": {"model": "claude-opus-5-5", "usage": {"input_tokens": 5}}}) + "\n")
            f.write(json.dumps({"type": "system", "subtype": "compact_boundary",
                                "timestamp": "2026-09-26T05:10:00Z"}) + "\n")
        leer["transcript_path"] = tr
        self.ruf(daten=leer)
        self.assertEqual(kontextfenster.lesen("claude", self.daten["session_id"])["prozent"], 0.0, "/compact = 0")

    def test_fehler_im_eigenen_teil_nur_original(self):
        util.schreib_json(util.pfad("state", "statusline-original.json"),
                          {"statusLine": {"type": "command", "command": "cat >/dev/null; printf 'orca\\n'"}})
        util.schreib_json(util.pfad("state", "current.json"), {"schwellen": "kaputt", "kontext": ["kaputt"]})
        r = self.ruf()
        self.assertEqual((r.returncode, r.stdout), (0, b"orca\n"))
        util.schreib_json(util.pfad("state", "current.json"), {"statusline_anzeigen": False})
        self.assertEqual(self.ruf().stdout, b"orca\n", "abgeschaltet: nur Original")
        util.schreib_json(util.pfad("state", "current.json"), {})
        self.assertEqual(self.ruf(roh=b"kein json").stdout, b"orca\n")

    def test_original_ohne_zeilenende_und_schnell(self):
        util.schreib_json(util.pfad("state", "statusline-original.json"),
                          {"statusLine": {"type": "command", "command": "cat >/dev/null; printf 'orca'"}})
        start = time.time()
        r = self.ruf()
        dauer = time.time() - start
        zeilen = r.stdout.decode().split("\n")
        self.assertEqual(zeilen[0], "orca")
        self.assertIn("ctx", ohne_farben(zeilen[1].encode()))
        self.assertLess(dauer, 1.0)


if __name__ == "__main__":
    unittest.main()
