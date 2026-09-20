"""Read-only measurements of the final encoded master; no listening score."""
import json
import math
from pathlib import Path
import re
import subprocess


def parse_measurements(stderr):
    # loudnorm emits flat JSON among ordinary FFmpeg diagnostics.
    for block in reversed(re.findall(r"\{[^{}]*\}", stderr)):
        try:
            row = json.loads(block)
            if "input_i" not in row:
                continue
            values = {name: float(row[key]) for name, key in (
                ("integrated_lufs", "input_i"), ("true_peak_dbtp", "input_tp"),
                ("loudness_range_lu", "input_lra"))}
            if not all(math.isfinite(value) for value in values.values()):
                raise ValueError("non-finite loudness measurement")
            return values
        except json.JSONDecodeError:
            continue
    raise ValueError("loudness measurements unavailable")


def inspect_master(path):
    """Measure decoded delivery file, not the normalization filter's target."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
         "silencedetect=noise=-45dB:d=2.0,loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True, check=True, timeout=240,
    )
    measured = parse_measurements(result.stderr)
    gaps = []
    start = None
    for line in result.stderr.splitlines():
        opened = re.search(r"silence_start: ([0-9.]+)", line)
        closed = re.search(r"silence_end: ([0-9.]+).*silence_duration: ([0-9.]+)", line)
        if opened:
            start = float(opened[1])
        if closed:
            gaps.append({"start": start, "end": float(closed[1]), "seconds": float(closed[2])})
            start = None
    warnings = []
    if abs(measured["integrated_lufs"] + 16) > 1:
        warnings.append("Integrated loudness outside house target -16 +/-1 LUFS.")
    if measured["true_peak_dbtp"] > -1:
        warnings.append("Encoded true peak above -1 dBTP; check codec overshoot/headroom.")
    if gaps:
        warnings.append("Quiet spans of at least two seconds need contextual review; may be intentional.")
    return {
        "file": Path(path).name, "basis": "FFmpeg measurements of final encoded master",
        "listened": False, "blocking": False, "new_tts_calls": 0,
        "house_targets": {"integrated_lufs": -16, "normalizer_true_peak_dbtp": -1.5},
        "measurements": measured, "quiet_spans": gaps, "warnings": warnings,
        "listening_still_required": [
            "Speech intelligibility and consistent cast levels on phone and headphones",
            "Natural handoffs, pronunciation, humour and warmth",
            "Music entrances/exits, dry sponsor and audible story transitions",
            "Cold-open promise, mid-episode fatigue and satisfying closing payoff",
        ],
    }


def write_engineering_report(master_path, report_path):
    # A reporting failure must never discard or re-render a paid master.
    try:
        report = inspect_master(master_path)
    except Exception as exc:
        report = {"file": Path(master_path).name, "listened": False, "blocking": False,
                  "measurements": None, "warnings": ["Measurement unavailable: " + type(exc).__name__]}
    Path(report_path).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report
