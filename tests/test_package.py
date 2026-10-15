import tomllib
import unittest
from pathlib import Path

import sfalert

ROOT = Path(__file__).resolve().parent.parent


class PackageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    def test_version_is_set(self) -> None:
        self.assertRegex(sfalert.__version__, r"^\d+\.\d+")

    def test_pyproject_is_stdlib_only(self) -> None:
        self.assertEqual(self.pyproject["project"]["name"], "sfalert")
        self.assertGreaterEqual(self.pyproject["project"]["requires-python"], "3.11")
        self.assertNotIn("dependencies", self.pyproject["project"])

    def test_dev_extra_declares_coverage(self) -> None:
        dev = self.pyproject["project"]["optional-dependencies"]["dev"]
        self.assertTrue(any(dep.startswith("coverage") for dep in dev), dev)

    def test_console_script_entry_point(self) -> None:
        scripts = self.pyproject["project"]["scripts"]
        self.assertEqual(scripts["sfalert"], "sfalert.__main__:main")
        # The entry point must resolve to the real main().
        module_name, _, attr = scripts["sfalert"].partition(":")
        self.assertEqual(module_name, "sfalert.__main__")
        self.assertEqual(attr, "main")

    def test_version_is_dynamic_from_package(self) -> None:
        # Single source of truth: pyproject must not pin a version.
        self.assertIn("version", self.pyproject["project"]["dynamic"])
        self.assertEqual(
            self.pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"],
            "sfalert.__version__",
        )
