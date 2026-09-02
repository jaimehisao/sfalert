import unittest

from sfalert.categories import categorize, category_meta


class CategorizeTest(unittest.TestCase):
    def test_violence_and_weapon_calls(self) -> None:
        self.assertEqual(categorize("ASSAULT / BATTERY")[0], "violence")
        self.assertEqual(categorize("FIGHT NO WEAPON")[0], "violence")
        self.assertEqual(categorize("PERSON W/GUN")[0], "violence")

    def test_traffic_stops_are_hotspot_signal_not_routine(self) -> None:
        for desc in ("TRAFFIC STOP", "TRAF VIOLATION CITE", "TRAF VIOLATION TOW"):
            category, routine, weight = categorize(desc)
            self.assertEqual(category, "traffic", desc)
            self.assertFalse(routine, desc)
            self.assertGreaterEqual(weight, 3, desc)

    def test_passing_calls_are_routine_noise(self) -> None:
        category, routine, weight = categorize("PASSING CALL")
        self.assertTrue(routine)
        self.assertEqual(weight, 1)
        self.assertEqual(category, "other")

        _, meet_routine, _ = categorize("MEET W/CITY EMPLOYEE")
        self.assertTrue(meet_routine)

    def test_empty_description(self) -> None:
        self.assertEqual(categorize(None), ("other", False, 1))
        self.assertEqual(categorize(""), ("other", False, 1))

    def test_category_meta_includes_traffic(self) -> None:
        ids = {row["id"] for row in category_meta()}
        self.assertIn("traffic", ids)
        self.assertIn("violence", ids)
