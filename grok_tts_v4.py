# -*- coding: utf-8 -*-
"""Grok TTS adapter for Jamie: Ursa primary, Celeste fallback.

This module is intentionally small and provider-specific. The production router owns
speaker selection and OpenAI fallback; this adapter owns Grok retries, voice fallback,
expressive tags, caching, and per-call cost telemetry.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / ".tts_cache" / "grok"
API_BASE = os.getenv("XAI_API_BASE", "https://api.x.ai/v1").rstrip("/")
COST_PER_MILLION_CHARS = 15.0


def _api_key() -> str:
    return (
        os.getenv("XAI_API_KEY", "")
        or os.getenv("GROK_XAI_API_KEY", "")
        or os.getenv("GROK_API_KEY", "")
    ).strip()


def _clean_text(text: str) -> str:
    value = re.sub(r"^\s*JAMIE\s*:\s*", "", text or "", flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _expressive_text(text: str, mood: str) -> str:
    """Add restrained Grok-native direction without turning Jamie into a cartoon."""
    clean = _clean_text(text)
    mood = (mood or "neutral").strip().lower()
    if not clean:
        return clean

    # Grok TTS understands these tags natively. Use at most one expression per line.
    if mood == "amused":
        return f"[chuckle] {clean}"
    if mood == "concern":
        return f"[breath] {clean}"
    if mood in {"pushback", "interruption"} and not clean.lower().startswith(("wait", "hold on")):
        return f"Wait. [pause] {clean}"
    if mood == "concession":
        return f"[pause] {clean}"
    return clean


def _cache_key(text: str, voice: str, mood: str) -> str:
    raw = json.dumps(
        {"text": text, "voice": voice, "mood": mood, "version": "grok-jamie-v1"},
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _valid_mp3(data: bytes) -> bool:
    return len(data) > 1_000 and (
        data.startswith(b"ID3")
        or data[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}
    )


def _render_once(text: str, voice: str, out_path: Path) -> int:
    key = _api_key()
    if not key:
        raise RuntimeError("XAI_API_KEY/GROK_XAI_API_KEY is missing")

    response = requests.post(
        f"{API_BASE}/tts",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "the-ai-edge-production/1.0",
        },
        json={
            "text": text,
            "voice_id": voice,
            "language": "en",
            "speed": float(os.getenv("GROK_TTS_SPEED_JAMIE", "1.0")),
            "text_normalization": True,
            "output_format": {
                "codec": "mp3",
                "sample_rate": 44100,
                "bit_rate": 192000,
            },
        },
        timeout=(10, int(os.getenv("GROK_TTS_TIMEOUT_SECONDS", "90"))),
    )
    if not response.ok:
        detail = response.text[:400].replace("\n", " ")
        raise RuntimeError(f"Grok TTS HTTP {response.status_code}: {detail}")
    audio = response.content
    if not _valid_mp3(audio):
        raise RuntimeError(f"Grok TTS returned invalid/tiny audio ({len(audio)} bytes)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    partial = out_path.with_suffix(out_path.suffix + ".part")
    partial.write_bytes(audio)
    partial.replace(out_path)
    return len(audio)


def render_jamie(
    text: str,
    mood: str,
    out_path: Path,
    *,
    primary_only: bool = False,
) -> Dict[str, Any]:
    """Render Jamie using Ursa, then Celeste. Raises only when all allowed voices fail."""
    clean = _clean_text(text)
    if not clean:
        raise RuntimeError("Cannot render an empty Jamie line")

    expressive = _expressive_text(clean, mood)
    primary = os.getenv("GROK_TTS_VOICE_JAMIE", "ursa").strip().lower()
    fallback = os.getenv("GROK_TTS_VOICE_JAMIE_FALLBACK", "celeste").strip().lower()
    voices = [primary]
    if not primary_only and fallback and fallback != primary:
        voices.append(fallback)

    retries = max(1, int(os.getenv("GROK_TTS_MAX_RETRIES", "2")))
    use_cache = os.getenv("GROK_TTS_CACHE", "true").strip().lower() in {"1", "true", "yes"}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    errors = []

    for voice_index, voice in enumerate(voices):
        cache_file = CACHE_DIR / f"{_cache_key(expressive, voice, mood)}.mp3"
        if use_cache and cache_file.exists() and cache_file.stat().st_size > 1_000:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cache_file, out_path)
            return {
                "provider": "grok",
                "voice": voice,
                "primary_voice": voice_index == 0,
                "cache": True,
                "characters": len(expressive),
                "bytes": out_path.stat().st_size,
                "estimated_cost_usd": 0.0,
                "mood": mood,
            }

        for attempt in range(1, retries + 1):
            try:
                size = _render_once(expressive, voice, out_path)
                if use_cache:
                    shutil.copyfile(out_path, cache_file)
                return {
                    "provider": "grok",
                    "voice": voice,
                    "primary_voice": voice_index == 0,
                    "cache": False,
                    "characters": len(expressive),
                    "bytes": size,
                    "estimated_cost_usd": round(
                        len(expressive) * COST_PER_MILLION_CHARS / 1_000_000, 6
                    ),
                    "mood": mood,
                    "attempt": attempt,
                }
            except Exception as exc:
                errors.append(f"{voice} attempt {attempt}: {exc}")
                if attempt < retries:
                    time.sleep(min(4.0, 1.25 * attempt))

    raise RuntimeError("Grok Jamie failed across Ursa/Celeste: " + " | ".join(errors)[-1200:])


def smoke_test(out_path: Path) -> Dict[str, Any]:
    line = (
        "Okay, quick voice check. [chuckle] If the boys are going to call risk "
        "an efficiency gain, somebody in this room has to read the fine print."
    )
    # Prove Ursa specifically; Celeste is the production fallback, not a fake primary pass.
    return render_jamie(line, "amused", Path(out_path), primary_only=True)
