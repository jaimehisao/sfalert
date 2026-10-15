import unittest
from unittest.mock import patch

from sfalert.basemaps import (
    BASEMAPS,
    DEFAULT_BASEMAP,
    ENV_VAR,
    basemap_meta,
    provider,
    resolve,
)


class BasemapRegistryTest(unittest.TestCase):
    def test_registry_is_consistent(self) -> None:
        self.assertIn(DEFAULT_BASEMAP, BASEMAPS)
        self.assertGreaterEqual(len(BASEMAPS), 3)
        for key, meta in BASEMAPS.items():
            self.assertTrue(meta.get("label"), key)
            url = meta.get("url")
            if url is not None:
                self.assertTrue(url.startswith("https://"), key)
        # Exactly one offline option, and it must declare no url.
        offline = [k for k, v in BASEMAPS.items() if not v.get("url")]
        self.assertEqual(offline, ["none"])

    def test_meta_exposes_everything_the_ui_needs(self) -> None:
        rows = basemap_meta()
        self.assertEqual({row["id"] for row in rows}, set(BASEMAPS))
        for row in rows:
            self.assertEqual(
                set(row), {"id", "label", "url", "subdomains", "attribution"}, row["id"]
            )

    def test_provider_returns_full_config(self) -> None:
        active = provider("esri-dark")
        self.assertIn("url", active)
        self.assertIn("attribution", active)
        # Esri tiles use {z}/{y}/{x} ordering; the others CARTO/OSM {z}/{x}/{y}.
        self.assertIn("{z}/{y}/{x}", str(active["url"]))

    def test_none_provider_has_no_url(self) -> None:
        self.assertIsNone(provider("none")["url"])


class ResolveTest(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_default_when_nothing_set(self) -> None:
        self.assertEqual(resolve(), DEFAULT_BASEMAP)

    @patch.dict("os.environ", {ENV_VAR: "esri-dark"})
    def test_env_var_sets_default(self) -> None:
        self.assertEqual(resolve(), "esri-dark")

    @patch.dict("os.environ", {ENV_VAR: "esri-dark"})
    def test_user_choice_beats_env(self) -> None:
        self.assertEqual(resolve("osm"), "osm")

    @patch.dict("os.environ", {ENV_VAR: "esri-dark"})
    def test_unknown_choice_falls_back_to_env(self) -> None:
        self.assertEqual(resolve("not-a-provider"), "esri-dark")

    @patch.dict("os.environ", {ENV_VAR: "bogus"})
    def test_unknown_env_falls_back_to_default(self) -> None:
        self.assertEqual(resolve(), DEFAULT_BASEMAP)

    def test_explicit_env_argument_is_honored(self) -> None:
        self.assertEqual(resolve(env="osm"), "osm")
        self.assertEqual(resolve("osm", env="esri-dark"), "osm")
