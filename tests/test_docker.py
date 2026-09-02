import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class DockerfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (ROOT / "Dockerfile").read_text()
        self.ignore = (ROOT / ".dockerignore").read_text()

    def test_uses_python_312_slim(self) -> None:
        self.assertRegex(self.text, r"^FROM python:3\.12-slim", re.M)

    def test_copies_app_and_web_only(self) -> None:
        self.assertIn("COPY sfalert ./sfalert", self.text)
        self.assertIn("COPY web ./web", self.text)
        self.assertNotIn("COPY tests", self.text)
        self.assertNotIn("COPY data", self.text)

    def test_runs_as_non_root_and_listens_publicly(self) -> None:
        self.assertRegex(self.text, re.compile(r"^USER sfalert\s*$", re.M))
        self.assertIn("EXPOSE 8765", self.text)
        self.assertIn("--host", self.text)
        self.assertIn("0.0.0.0", self.text)
        self.assertIn("--no-browser", self.text)

    def test_dockerignore_keeps_image_small(self) -> None:
        for name in (".git", "data", "tests", ".github"):
            self.assertIn(name, self.ignore)
