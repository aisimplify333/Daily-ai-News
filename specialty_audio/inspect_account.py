"""Read-only ElevenLabs preflight. No generation, account edits, or raw payload logs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.request


def get_json(path: str, key: str) -> dict:
    request = urllib.request.Request(
        "https://api.elevenlabs.io" + path,
        headers={"xi-api-key": key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Never expose provider response bodies, headers, or account identifiers.
        raise RuntimeError(f"ElevenLabs read-only preflight failed: HTTP {error.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise RuntimeError("ElevenLabs read-only preflight unavailable; no generation attempted") from None


def summarize(subscription: dict, voices: dict) -> dict:
    used, limit = subscription.get("character_count"), subscription.get("character_limit")
    remaining = max(0, limit - used) if type(used) is int and type(limit) is int else None
    return {
        "mode": "read_only_no_generation",
        "tier": subscription.get("tier"),
        "status": subscription.get("status"),
        "remaining_credits_from_reported_allowance": remaining,
        "next_character_count_reset_unix": subscription.get("next_character_count_reset_unix"),
        "note": "Reset timestamp is not proof of cancellation or renewal status. No billing changes made.",
        "voice_catalog_complete": not bool(voices.get("has_more")),
        "voices": [
            {"voice_id": voice.get("voice_id"), "name": voice.get("name"),
             "category": voice.get("category"),
             "labels": {k: v for k, v in (voice.get("labels") or {}).items()
                        if k in {"accent", "gender", "age", "use_case", "descriptive"}},
             "approved_for_production": False}
            for voice in voices.get("voices", [])
        ],
    }


def main() -> None:
    key = os.getenv("AI_EDGE_PODCAST_ELEVENLABS", "").strip()
    if not key:
        raise RuntimeError("Expected ElevenLabs secret is missing; no API calls made")
    subscription = get_json("/v1/user/subscription", key)
    voices = get_json("/v2/voices?page_size=100", key)
    report = summarize(subscription, voices)
    output = Path("specialty_account_report")
    output.mkdir(exist_ok=True)
    (output / "account_and_voices.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Read-only account check completed. Report saved as workflow artifact. No audio generated.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
