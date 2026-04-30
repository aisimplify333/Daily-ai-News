#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rotate podcast show cover art monthly.

Purpose:
- Keep the public RSS artwork URL stable by updating /cover.png at repo root.
- Pull the monthly selected artwork from /assets.
- Optionally also update /assets/current_cover.png for internal reference.

Expected repo structure:
  assets/
    cover.png                 # current/default logo-only cover
    alex_master.png           # existing source asset
    jamie_master.png          # existing source asset
    rufus_master.png          # existing source asset
    cover_alex.png            # generated Alex-forward Spotify cover
    cover_jamie.png           # generated Jamie-forward Spotify cover
    cover_rufus.png           # optional Rufus-forward Spotify cover
  cover.png                   # public show cover referenced by RSS feed

Rotation pattern:
  Jan/Apr/Jul/Oct  = default cover
  Feb/May/Aug/Nov  = Alex-forward cover
  Mar/Jun/Sep/Dec  = Jamie-forward cover

You can change MONTH_TO_COVER below at any time.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"

# This is the stable public file your existing RSS/feed already appears to use.
PUBLIC_ROOT_COVER = ROOT / "cover.png"

# Optional internal active copy.
ASSETS_CURRENT_COVER = ASSETS_DIR / "current_cover.png"

MANIFEST_PATH = ASSETS_DIR / "cover_rotation_manifest.json"

# Month-based rotation. Edit filenames to match what you upload into /assets.
MONTH_TO_COVER = {
    1: "cover.png",
    2: "cover_alex.png",
    3: "cover_jamie.png",
    4: "cover.png",
    5: "cover_alex.png",
    6: "cover_jamie.png",
    7: "cover.png",
    8: "cover_alex.png",
    9: "cover_jamie.png",
    10: "cover.png",
    11: "cover_alex.png",
    12: "cover_jamie.png",
}

FALLBACK_COVER = "cover.png"

MIN_SIZE = 1400
MAX_SIZE = 3000
TARGET_SIZE = 2048


def _safe_print(msg: str) -> None:
    print(msg, flush=True)


def _validate_and_normalize_image(src: Path, dest: Path) -> None:
    """
    Spotify/Apple-safe cover handling:
    - square
    - RGB
    - PNG
    - minimum 1400x1400
    - maximum 3000x3000
    """
    with Image.open(src) as im:
        im = im.convert("RGB")

        w, h = im.size
        if w != h:
            # Center-crop to square rather than stretch.
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            im = im.crop((left, top, left + side, top + side))

        w, h = im.size
        if w < MIN_SIZE or h < MIN_SIZE or w > MAX_SIZE or h > MAX_SIZE:
            im = im.resize((TARGET_SIZE, TARGET_SIZE), Image.LANCZOS)

        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, format="PNG", optimize=True)


def main() -> None:
    # Allows manual override in GitHub Actions if needed:
    # COVER_ART_OVERRIDE=cover_jamie.png python scripts/rotate_cover_art.py
    override = os.getenv("COVER_ART_OVERRIDE", "").strip()

    today = _dt.datetime.now(_dt.timezone.utc).date()
    month = today.month

    selected_name = override or MONTH_TO_COVER.get(month, FALLBACK_COVER)
    selected = ASSETS_DIR / selected_name

    if not selected.exists():
        _safe_print(f"⚠️ Selected cover missing: assets/{selected_name}. Falling back to assets/{FALLBACK_COVER}.")
        selected_name = FALLBACK_COVER
        selected = ASSETS_DIR / selected_name

    if not selected.exists():
        raise FileNotFoundError(
            f"Missing fallback cover too: {selected}. "
            "Upload assets/cover.png or adjust MONTH_TO_COVER."
        )

    _validate_and_normalize_image(selected, PUBLIC_ROOT_COVER)
    _validate_and_normalize_image(selected, ASSETS_CURRENT_COVER)

    manifest = {
        "updated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "selected_cover": f"assets/{selected_name}",
        "public_cover": "cover.png",
        "assets_current_cover": "assets/current_cover.png",
        "month": month,
        "rotation_pattern": MONTH_TO_COVER,
        "note": "RSS should keep using a stable cover.png URL so Spotify refreshes the image without code changes.",
    }

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _safe_print(f"✅ Rotated podcast cover art to assets/{selected_name}")
    _safe_print(f"✅ Updated {PUBLIC_ROOT_COVER.relative_to(ROOT)}")
    _safe_print(f"✅ Updated {ASSETS_CURRENT_COVER.relative_to(ROOT)}")
    _safe_print(f"✅ Wrote {MANIFEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
