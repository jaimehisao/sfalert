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

    def test_runs_on_apps_runner(self) -> None:
        self.assertRegex(self.text, re.compile(r"^    runs-on: apps-runner\s*$", re.M))
        self.assertNotIn("ubuntu-latest", self.text)
        self.assertNotIn("self-hosted", self.text)

    def test_ci_invokes_make_test(self) -> None:
        self.assertIn("make test", self.text)

    def test_does_not_use_job_container(self) -> None:
        self.assertIsNone(re.search(r"^\s+container:", self.text, re.M))
