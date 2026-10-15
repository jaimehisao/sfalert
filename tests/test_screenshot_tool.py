import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "screenshot.py"


class ScreenshotToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(TOOL.is_file(), "tools/screenshot.py is missing")
        self.source = TOOL.read_text()
        self.tree = ast.parse(self.source)

    def test_tool_is_valid_python(self) -> None:
        self.assertTrue(self.tree.body, "empty module")

    def test_swaps_carto_tiles_for_determinism(self) -> None:
        # CARTO answers anonymous tile bursts with an "API KEY REQUIRED"
        # watermark tile, which would make screenshots nondeterministic.
        self.assertIn("basemaps.cartocdn.com", self.source)
        self.assertIn("tile.openstreetmap.org", self.source)
        self.assertIn("--keep-tiles", self.source)

    def test_flags_mirror_the_ui_url_state(self) -> None:
        for flag in (
            "--window",
            "--category",
            "--district",
            "--search",
            "--open-only",
            "--noise",
            "--view",
            "--out",
        ):
            self.assertIn(f'"{flag}"', self.source, flag)
