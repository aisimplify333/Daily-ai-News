#!/usr/bin/env python3
"""Generate a low-cost Grok TTS audition for Jamie without publishing anything."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.getenv("XAI_API_BASE", "https://api.x.ai/v1").rstrip("/")
DEFAULT_VOICES = ("eve", "sirius", "iris", "ursa", "celeste")
JAMIE_COPY = (
    "ALEX: So the company says this is safer, faster, and definitely not a power grab. "
    "JAMIE: [chuckle] Oh, definitely. Because companies always put that in the press release "
    "right before they hand users more control. [pause] Look, the model is impressive. "
    "But if a worker gets blamed when it fails, then the efficiency belongs to management "
    "and the risk belongs to her. <emphasis>That is not innovation. That is cost transfer "
    "with better branding.</emphasis> RUFUS: Rather direct. JAMIE: [laugh] You say that like "
    "the boys were going to notice the human being without me."
)


def _request(path: str, api_key: str, payload: dict | None = None) -> bytes:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        method="GET" if payload is None else "POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "the-ai-edge-grok-audition/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="voice_audition")
    parser.add_argument(
        "--voices",
        default=os.getenv("GROK_JAMIE_VOICES", ",".join(DEFAULT_VOICES)),
        help="Comma-separated Grok voice IDs.",
    )
    args = parser.parse_args()

    api_key = os.getenv("XAI_API_KEY", "").strip()
    if not api_key:
        print("XAI_API_KEY is missing; audition cannot run.", file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    voices = tuple(dict.fromkeys(v.strip().lower() for v in args.voices.split(",") if v.strip()))
    if not voices:
        print("No voice candidates were provided.", file=sys.stderr)
        return 2

    catalog = {}
    try:
        raw_catalog = _request("/tts/voices", api_key)
        catalog_payload = json.loads(raw_catalog.decode("utf-8"))
        catalog_items = catalog_payload.get("voices", []) if isinstance(catalog_payload, dict) else []
        catalog = {
            str(item.get("voice_id", "")).lower(): item
            for item in catalog_items
            if isinstance(item, dict) and item.get("voice_id")
        }
        (out_dir / "grok_voice_catalog.json").write_text(
            json.dumps(catalog_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"Voice catalog lookup failed; continuing with configured IDs: {exc}")

    results = []
    for voice_id in voices:
        output_path = out_dir / f"jamie_grok_{voice_id}.mp3"
        payload = {
            "text": JAMIE_COPY,
            "voice_id": voice_id,
            "language": "en",
            "speed": 1.0,
            "text_normalization": True,
            "output_format": {
                "codec": "mp3",
                "sample_rate": 44100,
                "bit_rate": 192000,
            },
        }
        record = {
            "voice_id": voice_id,
            "catalog": catalog.get(voice_id, {}),
            "characters": len(JAMIE_COPY),
            "estimated_cost_usd": round(len(JAMIE_COPY) * 15.0 / 1_000_000, 6),
            "output": str(output_path),
        }
        try:
            audio = _request("/tts", api_key, payload)
            if len(audio) < 1_000:
                raise RuntimeError(f"audio response was only {len(audio)} bytes")
            output_path.write_bytes(audio)
            record.update({"status": "ok", "bytes": len(audio)})
            print(f"OK {voice_id}: {len(audio):,} bytes")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            record.update({"status": "error", "error": f"HTTP {exc.code}: {detail}"})
            print(f"FAIL {voice_id}: HTTP {exc.code}", file=sys.stderr)
        except Exception as exc:
            record.update({"status": "error", "error": str(exc)[:500]})
            print(f"FAIL {voice_id}: {exc}", file=sys.stderr)
        results.append(record)

    manifest = {
        "purpose": "Jamie Grok TTS blind audition; no episode was published",
        "persona": (
            "Highly intelligent, opinionated female co-host; warm but competitive, "
            "human-stakes focused, with restrained sarcastic laughter and chuckles."
        ),
        "speech_tags_tested": ["[chuckle]", "[pause]", "<emphasis>", "[laugh]"],
        "candidates": results,
        "total_estimated_cost_usd": round(
            sum(float(r["estimated_cost_usd"]) for r in results), 6
        ),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    successes = sum(1 for result in results if result.get("status") == "ok")
    print(f"Generated {successes}/{len(results)} voice samples.")
    return 0 if successes else 1


if __name__ == "__main__":
    raise SystemExit(main())
