"""Statische Prüfungen der Shell-Skripte (keine Ausführung)."""
import os
import re
import shutil
import subprocess
import unittest

import hilfe  # noqa: F401  (setzt LIMIT_WAECHTER_HOME auf einen Temp-Ordner)

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZSH = shutil.which("zsh") or "/bin/zsh"


def lesen(name):
    with open(os.path.join(WURZEL, name), encoding="utf-8") as f:
        return f.read()


class TestSkripte(unittest.TestCase):
    def syntax(self, name):
        r = subprocess.run([ZSH, "-n", os.path.join(WURZEL, name)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless(os.path.exists(ZSH), "zsh fehlt")
    def test_syntax_install(self):
        self.syntax("install.sh")

    @unittest.skipUnless(os.path.exists(ZSH), "zsh fehlt")
    def test_syntax_uninstall(self):
        self.syntax("uninstall.sh")

    @unittest.skipUnless(os.path.exists(ZSH) and os.path.exists(os.path.join(WURZEL, "app", "build.sh")),
                         "app/build.sh fehlt")
    def test_syntax_build(self):
        self.syntax(os.path.join("app", "build.sh"))

    def test_install_app_modus(self):
        s = lesen("install.sh")
        self.assertIn('"$MODUS" == app', s)
        self.assertIn("[hooks|app]", s)
        self.assertIn("ditto", s)
        self.assertIn("Limit-Waechter.app.$TS", s)
        self.assertIn("$APP_LABEL.plist.$TS", s)
        self.assertNotIn("rm -rf", s)

    def test_uninstall_verschiebt_app(self):
        s = lesen("uninstall.sh")
        self.assertRegex(s, r'mv "\$APP" "\$LW/backups/Limit-Waechter\.app\.\$TS"')
        self.assertIn('"$LABEL.app"', s)
        self.assertNotIn("rm -rf", s)

    def test_kein_rm_auf_applications(self):
        for name in ("install.sh", "uninstall.sh"):
            for zeile in lesen(name).splitlines():
                if re.search(r"\brm\s", zeile):
                    self.assertNotIn("Applications", zeile, f"{name}: {zeile}")
                    self.assertNotIn("$APP", zeile, f"{name}: {zeile}")


if __name__ == "__main__":
    unittest.main()
