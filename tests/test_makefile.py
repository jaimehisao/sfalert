import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class MakefileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (ROOT / "Makefile").read_text()

    def test_expected_targets_exist(self) -> None:
        for target in ("help", "test", "ingest", "serve", "run", "docker", "clean"):
            self.assertRegex(
                self.text,
                re.compile(rf"^{re.escape(target)}:", re.M),
                msg=f"missing {target}",
            )

    def test_dry_run_test_invokes_unittest(self) -> None:
        out = subprocess.check_output(
            ["make", "-n", "test"],
            cwd=ROOT,
            text=True,
        )
        self.assertIn("unittest discover", out)
        self.assertIn("-s tests", out)

    def test_help_prints_targets(self) -> None:
        out = subprocess.check_output(["make", "help"], cwd=ROOT, text=True)
        self.assertIn("make test", out)
        self.assertIn("make serve", out)
        self.assertIn("make docker", out)
