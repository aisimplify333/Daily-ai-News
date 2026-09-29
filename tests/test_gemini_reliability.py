import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from gemini_cast_tts import GeminiTTSHTTPError
import hybrid_tts_router_v3_1 as router

class ReliabilityTests(unittest.TestCase):
    def test_daily_quota_stops_retry_and_redacts_details(self):
        response = Mock(status_code=429, headers={})
        response.json.return_value = {'error': {'message': 'secret project/account information', 'details': [
            {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [
                {'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]},
            {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '42s'}]}}
        error = GeminiTTSHTTPError(response)
        self.assertTrue(error.daily_exhausted)
        self.assertFalse(error.retryable)
        self.assertEqual(error.retry_after, 42)
        self.assertNotIn('secret', str(error))

    def test_transient_retry_after(self):
        response = Mock(status_code=429, headers={'Retry-After': '65'})
        response.json.return_value = {'error': {'details': []}}
        error = GeminiTTSHTTPError(response)
        self.assertTrue(error.retryable)
        self.assertEqual(error.retry_after, 65)

    def test_failed_gemini_never_calls_old_voice(self):
        with patch.dict(os.environ, {'ALEX_TTS_PROVIDER': 'gemini', 'GEMINI_REQUIRE_APPROVED_VOICE': 'true'}):
            with patch.object(router, '_gemini_tts_to_file', side_effect=RuntimeError('quota')):
                with patch.object(router, '_openai_tts_to_file') as old, patch.object(router, '_write_report'):
                    with self.assertRaisesRegex(RuntimeError, 'approved Gemini voice unavailable'):
                        router.route_text_to_file('A test sentence.', 'ALEX', Path('unused.mp3'))
                    old.assert_not_called()
