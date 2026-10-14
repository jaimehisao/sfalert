import unittest

from sfalert.categories import categorize, category_meta


class CategorizeTest(unittest.TestCase):
    def test_violence_and_weapon_calls(self) -> None:
        self.assertEqual(categorize("ASSAULT / BATTERY")[0], "violence")
        self.assertEqual(categorize("FIGHT NO WEAPON")[0], "violence")
        self.assertEqual(categorize("PERSON W/GUN")[0], "violence")

    def test_stab_needle_does_not_match_established(self) -> None:
        # "STAB" matched inside "ESTABLISHED" / "STABILIZE".
        for desc in ("ESTABLISHED", "STABILIZE", "ESTABLISHING CONTACT"):
            self.assertNotEqual(categorize(desc)[0], "violence", desc)
        self.assertEqual(categorize("STABBING")[0], "violence")
        self.assertEqual(categorize("STABBED SUSPECT")[0], "violence")
        self.assertEqual(categorize("STAB WOUND")[0], "violence")

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
        self.assertEqual(categorize(None), ("other", True, 1))
        self.assertEqual(categorize(""), ("other", True, 1))

    def test_production_strings_land_in_expected_categories(self) -> None:
        # Needles validated against live DataSF call_type_final_desc values.
        expected = {
            "H&R INJURY ACCIDENT": "traffic",
            "H&R VEH ACCIDENT": "traffic",
            "INJURY VEH ACCIDENT": "traffic",
            "Psych escort": "welfare",
            "PSYCH EVAL / HOLD": "welfare",
            "416 for medication": "welfare",
            "416 for restraints": "welfare",
            "SENILE PERSON": "welfare",
            "VANDALISM": "quality",
            "GRAFFITI VANDALISM": "quality",
            "VANDALISM DV": "violence",
            "PROWLER": "suspicious",
            "PERSON BREAKING IN": "suspicious",
            "BOMB THREAT": "suspicious",
            "EXPLOSIVE FOUND": "suspicious",
            "SHOT SPOTTER": "violence",
            "KIDNAPPING": "violence",
            "STALKING": "violence",
            "SHOTS FIRED": "violence",
        }
        for desc, category in expected.items():
            self.assertEqual(categorize(desc)[0], category, desc)

    def test_misc_and_empty_descriptions_are_routine_noise(self) -> None:
        for desc in ("MISC", "MONEY COUNTS", ""):
            _, routine, weight = categorize(desc)
            self.assertTrue(routine, desc)
            self.assertEqual(weight, 1, desc)

    def test_category_meta_includes_traffic(self) -> None:
        ids = {row["id"] for row in category_meta()}
        self.assertIn("traffic", ids)
        self.assertIn("violence", ids)
