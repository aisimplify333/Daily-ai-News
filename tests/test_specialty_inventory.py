import unittest
from unittest.mock import patch
from specialty_audio.inspect_account import summarize, main


class InventoryTests(unittest.TestCase):
    def test_only_allowlisted_fields_and_no_automatic_voice_approval(self):
        report = summarize(
            {"character_count": 100, "character_limit": 260100, "email": "private"},
            {"voices": [{"voice_id": "test", "name": "Test", "samples": ["private"],
                         "labels": {"accent": "british", "private": "private"}}]},
        )
        self.assertEqual(report["remaining_credits_from_reported_allowance"], 260000)
        self.assertNotIn("private", str(report))
        self.assertFalse(report["voices"][0]["approved_for_production"])

    def test_unknown_balance_not_assumed_available(self):
        self.assertIsNone(summarize({}, {})["remaining_credits_from_reported_allowance"])
        self.assertFalse(summarize({}, {"has_more": True})["voice_catalog_complete"])

    @patch.dict("os.environ", {}, clear=True)
    @patch("specialty_audio.inspect_account.get_json")
    def test_missing_secret_makes_no_calls(self, get):
        with self.assertRaises(RuntimeError):
            main()
        get.assert_not_called()
