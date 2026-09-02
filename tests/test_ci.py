import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


class GithubActionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text()

    def test_workflow_file_exists(self) -> None:
        self.assertTrue(WORKFLOW.is_file())

    def test_runs_on_ubuntu_latest(self) -> None:
        self.assertRegex(self.text, re.compile(r"^    runs-on: ubuntu-latest\s*$", re.M))
        self.assertNotIn("apps-runner", self.text)
        self.assertNotIn("self-hosted", self.text)

    def test_pins_python(self) -> None:
        self.assertIn("actions/setup-python", self.text)
        self.assertIn('python-version: "3.12"', self.text)

    def test_ci_invokes_make_test(self) -> None:
        self.assertIn("make test", self.text)
