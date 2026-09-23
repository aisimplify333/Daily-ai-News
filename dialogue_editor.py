"""One bounded dialogue revision; always retain the original on regression/error."""
import hashlib
import re
from pathlib import Path


def edit_dialogue(script, assessment, request, normalize, assess, runtime_distance, snapshot_dir=None, allow_runtime_repair=False):
    report = {"provider": "anthropic", "role": "dialogue_editor", "requested_calls": 1,
              "accepted": False, "listened": False,
              "input_sha256": hashlib.sha256(script.encode()).hexdigest()}
    report["input_words"] = assessment.get("metrics", {}).get("words", len(script.split()))
    report["input_runtime_distance"] = runtime_distance(assessment)
    try:
        if snapshot_dir is not None:
            Path(snapshot_dir, "dialogue_editor_original.txt").write_text(script, encoding="utf-8")
        response = request()
        if not response:
            report["reason"] = "empty_response_original_preserved"
            return script, assessment, report
        candidate = normalize(response)
        candidate_assessment = assess(candidate)
        report["candidate_words"] = candidate_assessment.get("metrics", {}).get("words", len(candidate.split()))
        report["candidate_runtime_distance"] = runtime_distance(candidate_assessment)
        report["candidate_failed"] = candidate_assessment.get("failed", [])
        if snapshot_dir is not None:
            Path(snapshot_dir, "dialogue_editor_candidate.txt").write_text(candidate, encoding="utf-8")
        report["candidate_sha256"] = hashlib.sha256(candidate.encode()).hexdigest()
        # These are regression checks, not semantic proof or an entertainment score.
        original_numbers = set(re.findall(r"\b\d[\d,.%]*", script))
        candidate_numbers = set(re.findall(r"\b\d[\d,.%]*", candidate))
        if candidate_numbers != original_numbers:
            reason = "numeric_receipts_changed"
        elif len(candidate.split()) > len(script.split()) * 1.03:
            reason = "unnecessary_expansion"
        elif not set(candidate_assessment.get("failed") or []).issubset(assessment.get("failed") or []):
            reason = "new_structural_failure"
        elif runtime_distance(candidate_assessment) > runtime_distance(assessment) and not (
            allow_runtime_repair
            and report["input_runtime_distance"] > 0
            and report["candidate_words"] >= report["input_words"] * 0.95
            and set(candidate_assessment.get("failed") or []).issubset({"runtime_word_band"})
        ):
            reason = "runtime_regression"
        elif len(candidate_assessment.get("soft_flags") or []) > len(assessment.get("soft_flags") or []):
            reason = "more_editorial_warnings"
        else:
            report.update(accepted=True, reason="revision_retained_runtime_repair_pending" if runtime_distance(candidate_assessment) > runtime_distance(assessment) else "revision_retained_no_detected_regression")
            return candidate, candidate_assessment, report
        report["reason"] = reason + "_original_preserved"
    except Exception as exc:
        report["reason"] = "editor_error_original_preserved"
        report["error_type"] = type(exc).__name__
    return script, assessment, report
