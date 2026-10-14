import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class WebUiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (ROOT / "web" / "index.html").read_text()
        self.css = (ROOT / "web" / "styles.css").read_text()
        self.js = (ROOT / "web" / "app.js").read_text()

    def test_map_library_is_vendored(self) -> None:
        # A local-first tool should not depend on a third-party CDN at runtime.
        self.assertIn('href="/vendor/leaflet.css"', self.html)
        self.assertIn('src="/vendor/leaflet.js"', self.html)
        self.assertIn('src="/vendor/leaflet-heat.js"', self.html)
        self.assertNotIn("unpkg.com", self.html)
        for asset in ("leaflet.js", "leaflet.css", "leaflet-heat.js"):
            self.assertTrue((ROOT / "web" / "vendor" / asset).is_file(), asset)

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
        self.assertIn('data-window="90d"', self.html)
        self.assertNotIn("citizen", self.html.lower())

    def test_overlay_chrome_not_page_header_layout(self) -> None:
        self.assertIn("position: absolute", self.css)
        self.assertIn("backdrop-filter", self.css)
        self.assertIn(".drawer", self.css)
        self.assertIn(".spark", self.css)

    def test_js_escapes_html_and_keeps_url_state(self) -> None:
        self.assertIn("function escapeHtml", self.js)
        self.assertIn("searchParams", self.js)
        # Search must be sent to the server, not filtered client-side.
        self.assertIn('p.set("q", state.q.trim())', self.js)
        self.assertNotIn("visibleIncidents", self.js)
        self.assertIn("renderDetail", self.js)
        # Polling must pause while the tab is hidden.
        self.assertIn("document.hidden", self.js)
        self.assertIn("visibilitychange", self.js)
        self.assertNotIn("citizen", self.js.lower())
