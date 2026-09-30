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


def edit_story_scenes(script, assessment, request_scene, normalize, assess, runtime_distance):
    """Bounded local revisions: a failed scene never discards successful other scenes."""
    report = {'provider':'anthropic', 'role':'scene_dialogue_editor', 'requested_calls':0,
              'accepted':False, 'listened':False, 'scenes':[]}
    for segment in (2, 3, 4):
        pattern = rf'(^###\s*SEGMENT\s*{segment}\b[^\n]*\n)(.*?)(?=^###\s*SEGMENT\s*{segment+1}\b)'
        match = re.search(pattern, script, re.M | re.S | re.I)
        if not match:
            continue
        original = match[2]
        row = {'segment':segment, 'accepted':False}
        report['requested_calls'] += 1
        try:
            revised = request_scene(segment, original).strip()
            if not revised or re.search(r'^###\s*SEGMENT', revised, re.M | re.I):
                row['reason'] = 'empty_or_structural_response'
            elif set(re.findall(r'\b\d[\d,.%]*', revised)) != set(re.findall(r'\b\d[\d,.%]*', original)):
                row['reason'] = 'numeric_receipts_changed'
            elif not .98 <= len(revised.split()) / max(1, len(original.split())) <= 1.12:
                row['reason'] = 'scene_word_budget_regression'
            else:
                candidate = normalize(script[:match.start(2)] + revised + '\n\n' + script[match.end(2):])
                measured = assess(candidate)
                new_failures = set(measured.get('failed') or []) - set(assessment.get('failed') or [])
                if new_failures - {'runtime_word_band'} or runtime_distance(measured) > runtime_distance(assessment):
                    row['reason'] = 'episode_structure_or_runtime_regression'
                else:
                    script, assessment = candidate, measured
                    row.update(accepted=True, reason='scene_revision_retained')
                    report['accepted'] = True
        except Exception as exc:
            row['reason'] = 'scene_error_' + type(exc).__name__
        report['scenes'].append(row)
    report['reason'] = 'scene_revisions_retained' if report['accepted'] else 'original_scenes_preserved'
    return script, assessment, report
