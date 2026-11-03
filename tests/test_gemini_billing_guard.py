import os
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import writer_room_v3_1 as writer

def client_error(message):
    def generate_content(**kwargs):
        raise RuntimeError(message)
    return {"gemini_client": SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))}

def test_depleted_prepaid_cast_stops_before_cross_provider_spend():
    with patch.dict(os.environ, {"ALEX_TTS_PROVIDER": "gemini"}):
        with pytest.raises(RuntimeError, match="approved cast unavailable"):
            writer._gemini_text(client_error("402 RESOURCE_EXHAUSTED: Your prepayment credits are depleted."), "test", "test")

def test_transient_quota_keeps_existing_fallback():
    with patch.dict(os.environ, {"ALEX_TTS_PROVIDER": "gemini"}):
        assert writer._gemini_text(client_error("429 RESOURCE_EXHAUSTED: retry later"), "test", "test") == ""
