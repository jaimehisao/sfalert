import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class WebUiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (ROOT / "web" / "index.html").read_text()
        self.css = (ROOT / "web" / "styles.css").read_text()
        self.js = (ROOT / "web" / "app.js").read_text()

    def test_shell_has_map_search_and_feed(self) -> None:
        for needle in (
            'id="map"',
            'id="feed"',
            'id="q"',
            'id="windows"',
            'id="detail"',
            'id="hours"',
            "SFALERT",
        ):
            self.assertIn(needle, self.html)
        self.assertNotIn("citizen", self.html.lower())

    def test_overlay_chrome_not_page_header_layout(self) -> None:
        self.assertIn("position: absolute", self.css)
        self.assertIn("backdrop-filter", self.css)
        self.assertIn(".drawer", self.css)
        self.assertIn(".spark", self.css)

    def test_js_escapes_html_and_keeps_url_state(self) -> None:
        self.assertIn("function escapeHtml", self.js)
        self.assertIn("searchParams", self.js)
        self.assertIn("visibleIncidents", self.js)
        self.assertIn("renderDetail", self.js)
        self.assertNotIn("citizen", self.js.lower())
