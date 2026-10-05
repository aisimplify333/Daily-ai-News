import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from specialty_audio import build_library as builder


class SpecialtyLibraryTests(unittest.TestCase):
    def test_low_balance_makes_no_generation_request(self):
        report = {'sounds': [], 'accounted_credits': 0}
        with tempfile.TemporaryDirectory() as folder, patch.object(builder, 'ROOT', Path(folder)), \
             patch.object(builder, 'get_account', return_value={'remaining': 10}), \
             patch.object(builder.urllib.request, 'urlopen') as request:
            with self.assertRaises(RuntimeError):
                builder.build_sounds('test-not-a-key', report)
            request.assert_not_called()

    def test_uncertain_attempt_is_not_retried(self):
        report = {'sounds': [{'name': 'conference', 'status': 'attempted'}], 'accounted_credits': 0}
        with tempfile.TemporaryDirectory() as folder, patch.object(builder, 'ROOT', Path(folder)), \
             patch.object(builder, 'get_account', return_value={'remaining': 340000}), \
             patch.object(builder.urllib.request, 'urlopen') as request:
            with self.assertRaises(RuntimeError):
                builder.build_sounds('test-not-a-key', report)
            request.assert_not_called()

    def test_existing_spend_counts_toward_budget(self):
        report = {'sounds': [], 'accounted_credits': 9500}
        with patch.object(builder, 'get_account', return_value={'remaining': 340000}), \
             patch.object(builder.urllib.request, 'urlopen') as request:
            with self.assertRaises(RuntimeError):
                builder.build_sounds('test-not-a-key', report)
            request.assert_not_called()
