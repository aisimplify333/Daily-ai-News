"""A malformed correction must not hide other usable factual corrections."""
from unittest.mock import patch
import grounded_news_v1 as news


def test_mixed_recovery_retains_valid_corrections():
    first = {"pass": False, "unresolved": ["Invalid or ungrounded calculation record"],
             "critical_errors": []}
    recovered = {"pass": False, "unresolved": ["Another item could not be located"],
                 "critical_errors": [{"exact_line": "ALEX: Wrong.", "replacement_line": "ALEX: Correct."}]}
    with patch.object(news, "_grounded_text", return_value="{}"), \
         patch.object(news, "_recovery_search", return_value="{}"), \
         patch.object(news, "_fact_check_prompt", return_value="Check"), \
         patch.object(news, "_validate_fact_payload", side_effect=[first, recovered]):
        result = news.fact_check_script("ALEX: Wrong.", [], "2026-11-04")
    assert result is recovered
    assert result["pass"] is False
    assert result["unresolved"]
    corrected, count = news.apply_fact_replacements("ALEX: Wrong.", result)
    assert corrected == "ALEX: Correct."
    assert count == 1
