"""A malformed correction must not hide other usable factual corrections."""
from unittest.mock import patch
import grounded_news_v1 as news


def test_mixed_recovery_retains_valid_corrections():
    first = {"pass": False, "unresolved": ["A reported factual error lacks a usable replacement"],
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


def test_schema_repair_cannot_erase_a_fact_or_invent_a_new_one():
    import json
    script = "ALEX: They paid ten billion dollars."
    err = {"claim_type": "factual_assertion", "factual_claim": "ten billion",
           "reason": "Wrong amount", "source_url": "https://example.org/filing",
           "evidence_quote": "five billion", "exact_line": script,
           "replacement_line": "ALEX: They paid five billion dollars."}
    for errors in ([], [err]):
        initial = {"pass": not errors, "critical_errors": errors, "calculations": [{}]}
        with patch.object(news, "_grounded_text", return_value=json.dumps(initial)), \
             patch.object(news, "_recovery_search", return_value=json.dumps({
                "calculations": [], "critical_errors": [{"invented": True}], "pass": True})):
            result = news.fact_check_script(script, [], "2026-11-10")
        assert result["pass"] == (not errors)
        assert len(result["critical_errors"]) == len(errors)
        assert not result["unresolved"]
