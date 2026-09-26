"""Statusline-Kette hooks/statusline.py als Unterprozess (wie Claude Code sie aufruft)."""

import json
import os
import stat
import subprocess
import unittest

from hilfe import PROJEKT, TempHome, fixture

from lw import quellen, util

SKRIPT = os.path.join(PROJEKT, "hooks", "statusline.py")


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
        env.update(env_mehr or {})
        return subprocess.run(["/usr/bin/python3", SKRIPT], input=self.payload if eingabe is None else eingabe,
                              capture_output=True, env=env, timeout=20)

    def test_schreibt_datei_und_reicht_original_durch(self):
        self.original("cat >/dev/null; printf 'orca-zeile\\n'; printf 'warnung' >&2; exit 3", padding=0)
        r = self.ruf()
        self.assertEqual((r.returncode, r.stdout, r.stderr), (3, b"orca-zeile\n", b"warnung"))
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
        r = self.ruf()
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertEqual(r.stdout.decode(), "5h 84% · week 65%\n")
        util.schreib_json(util.pfad("state", "current.json"), {"sprache": "de"})
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
        self.assertEqual(r.stdout.decode(), "5h – · week –\n")
        self.assertFalse(os.path.exists(self.datei))

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
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"ok\n", b""))
        self.assertFalse(os.path.exists(self.datei))


if __name__ == "__main__":
    unittest.main()
