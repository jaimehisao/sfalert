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

    def test_basemap_selector_is_configurable(self) -> None:
        self.assertIn('id="basemap"', self.html)
        # The tile layer must be data-driven from /api/meta, not hardcoded.
        self.assertNotIn("basemaps.cartocdn.com", self.js)
        self.assertIn("applyBasemap", self.js)
        self.assertIn("/api/meta", self.js)
        self.assertIn("basemap", self.js)

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

    def test_window_tabs_expose_selection_state(self) -> None:
        self.assertIn('role="tablist"', self.html)
        self.assertIn('role="tab"', self.html)
        self.assertIn('aria-selected', self.html)
        self.assertIn('aria-selected', self.js)

    def test_hour_bars_have_accessible_names(self) -> None:
        self.assertIn('aria-label', self.js)
        # Title and accessible name share the same "HH:00 · N calls" text.
        self.assertIn('00 · ${n} calls', self.js)

    def test_category_chips_expose_pressed_state(self) -> None:
        self.assertIn('aria-pressed', self.js)

    def test_feed_count_distinguishes_truncation(self) -> None:
        self.assertIn('of ${count} shown', self.js)

    def test_district_select_avoids_rebuild_churn(self) -> None:
        # Rebuilding the select every poll drops focus / closes the menu.
        self.assertIn('JSON.stringify(existing)', self.js)
        self.assertIn('document.activeElement === dist', self.js)

    def test_keyboard_focus_is_visible(self) -> None:
        self.assertIn(':focus-visible', self.css)
