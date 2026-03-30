#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from growth_engine import record_episode_feedback

BASE_DIR = Path(__file__).parent
META_PATH = BASE_DIR / "episode_metadata.json"
DEFAULT_METRICS_PATH = BASE_DIR / "episode_metrics.json"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    metrics_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_METRICS_PATH
    if not META_PATH.exists():
        print("feedback_worker.py: episode_metadata.json not found", flush=True)
        return 1
    if not metrics_path.exists():
        print(f"feedback_worker.py: metrics file not found: {metrics_path}", flush=True)
        return 1

    episode_meta = _read_json(META_PATH)
    metrics = _read_json(metrics_path)
    row = record_episode_feedback(episode_meta, metrics)
    print(json.dumps(row, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
