# -*- coding: utf-8 -*-
"""
The AI Edge v3.1 cost-safe production runner.

Paste this entire file as: run_broadcast.py

This fixes the expensive failure mode:
1. Cheap preflight runs before any LLM/TTS spend.
2. v3_1_runner generates only after preflight passes.
3. Feed sanitizer cleans stale public copy before final guard.
4. No-repeat guard remains as final public trust backstop.
5. A zero-cost delivery gate verifies title, SEO, subscriber CTA, RSS, and audio.\n6. Commit/push only happens after all gates pass.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import datetime
from pathlib import Path

from pydub import AudioSegment

MIN_MINUTES = float(os.getenv("MIN_MINUTES", os.getenv("MIN_EPISODE_MINUTES", "19")))
MAX_MINUTES = float(os.getenv("MAX_MINUTES", "26"))
BRANCH = os.getenv("GIT_BRANCH", "main")
RSS_BUFFER_SECONDS = int(os.getenv("RSS_BUFFER_SECONDS", "120"))
RUN_POST_PUSH_PUBLISHER = os.getenv("RUN_POST_PUSH_PUBLISHER", "false").strip().lower() in ("1", "true", "yes")
PUBLISH_SOCIAL_IN_MAIN = os.getenv("PUBLISH_SOCIAL", "false").strip().lower() in ("1", "true", "yes")


def run_command(command: str, description: str, allow_fail: bool = False) -> bool:
    print(f"\n>> STARTING: {description}...", flush=True)
    try:
        subprocess.run(command, shell=True, check=True, text=True)
        print(f">> ✅ COMPLETE: {description}", flush=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f">> ❌ ERROR in {description}: {e}", flush=True)
        if allow_fail:
            print(">> ⚠️ CONTINUING despite error...", flush=True)
            return False
        sys.exit(1)


def configure_git_identity() -> None:
    run_command('git config user.name "github-actions[bot]"', "Configuring git user.name", allow_fail=False)
    run_command(
        'git config user.email "41898282+github-actions[bot]@users.noreply.github.com"',
        "Configuring git user.email",
        allow_fail=False,
    )


def get_latest_mp3(audio_dir: str = "episode_audio") -> Path | None:
    audio_path = Path(audio_dir)
    expected = audio_path / f"podcast_{datetime.datetime.now(datetime.timezone.utc).date().isoformat()}.mp3"
    if expected.exists():
        return expected
    files = sorted(audio_path.glob("podcast_*.mp3"), key=lambda p: p.name, reverse=True)
    return files[0] if files else None


def get_mp3_duration_minutes(mp3_path: Path) -> float:
    audio = AudioSegment.from_mp3(mp3_path)
    return len(audio) / 1000.0 / 60.0


def check_episode_length_or_fail() -> tuple[Path, float]:
    print("\n>> CHECKING EPISODE LENGTH...", flush=True)
    latest = get_latest_mp3()
    if not latest:
        raise RuntimeError("No audio files found in episode_audio/.")

    duration_min = get_mp3_duration_minutes(latest)
    print(f">> File: {latest.name}", flush=True)
    print(f">> ⏱️ Duration: {duration_min:.2f} minutes", flush=True)

    if duration_min < MIN_MINUTES:
        raise RuntimeError(f"Episode too short ({duration_min:.2f} min < {MIN_MINUTES:.0f} min).")
    if duration_min > MAX_MINUTES:
        raise RuntimeError(f"Episode too long ({duration_min:.2f} min > {MAX_MINUTES:.0f} min).")

    print(f">> ✅ GREEN LIGHT: Episode inside {MIN_MINUTES:.0f}-{MAX_MINUTES:.0f} minute window.", flush=True)
    return latest, duration_min


def has_staged_changes() -> bool:
    result = subprocess.run("git diff --cached --quiet", shell=True)
    return result.returncode != 0


def maybe_run_post_push_publisher() -> None:
    if PUBLISH_SOCIAL_IN_MAIN:
        print("\n>> ℹ️ Skipping post-push publisher because PUBLISH_SOCIAL=true in main.", flush=True)
        return
    if not RUN_POST_PUSH_PUBLISHER:
        print("\n>> ℹ️ Post-push social publisher disabled.", flush=True)
        return
    if not Path("social_publisher.py").exists():
        print("\n>> ⚠️ social_publisher.py not found. Skipping.", flush=True)
        return
    run_command("python social_publisher.py", "Post-push Social Publisher", allow_fail=True)


def main() -> None:
    print("===================================================", flush=True)
    print("   THE AI EDGE — v3.1 COST-SAFE BROADCAST", flush=True)
    print("===================================================", flush=True)

    configure_git_identity()

    # 0) Cheap fail-fast checks. This protects the wallet.
    run_command("python preflight_guard_v3_1.py", "0. Cost-Safe Preflight Guard", allow_fail=False)

    # 1) Expensive generation only starts after preflight passes.
    run_command("python v3_1_runner.py", "1. V3.1 Studio Pipeline", allow_fail=False)

    # 1B) Clean public generated copy before final guard. This prevents stale legacy copy from wasting a completed episode.
    run_command("python feed_sanitize_v3_1.py", "1B. Public Feed Sanitizer", allow_fail=False)

    # 1C) Final public trust backstop. This should catch true repeats, not simple stale branding.
    run_command(
        "python no_repeat_guard_v3_1.py --feed feed.xml --report duplicate_guard_report.json --window 14",
        "1C. No-Repeat Public Trust Gate",
        allow_fail=False,
    )

    try:
        check_episode_length_or_fail()
    except Exception as e:
        print(f">> ❌ QUALITY GATE FAILED: {e}", flush=True)
        sys.exit(1)

    # Final package check is zero-cost. If it finds a metadata defect, the paid
    # master remains on disk and the next run reuses it instead of calling TTS.
    run_command(
        f"python production_delivery_gate.py --feed feed.xml "
        f"--min-minutes {MIN_MINUTES:g} --max-minutes {MAX_MINUTES:g}",
        "1D. Zero-Cost Spotify Delivery Gate",
        allow_fail=False,
    )

    print("\n>> UPLOADING TO GITHUB...", flush=True)
    run_command("git add .", "Staging Files", allow_fail=False)

    if not has_staged_changes():
        print(">> ℹ️ No changes staged. Skipping commit and push.", flush=True)
    else:
        run_command('git commit -m "The AI Edge v3.1: Cost-safe episode"', "Committing", allow_fail=False)
        run_command(f"git push origin {BRANCH}", "Pushing to Live", allow_fail=False)

    print(f"\n>> ⏳ BUFFERING {RSS_BUFFER_SECONDS}s for RSS propagation...", flush=True)
    time.sleep(RSS_BUFFER_SECONDS)

    maybe_run_post_push_publisher()

    print("\n===================================================", flush=True)
    print("   THE AI EDGE v3.1 COST-SAFE COMPLETE. LIVE.", flush=True)
    print("===================================================", flush=True)


if __name__ == "__main__":
    main()
