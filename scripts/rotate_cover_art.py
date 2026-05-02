#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rotate podcast show cover art monthly.

This script updates the public root cover.png used by the podcast RSS feed.
It selects the active monthly cover from /assets and copies it to /cover.png.

Expected repo structure:
  assets/cover.png
  assets/cover_alex.png
  assets/cover_jamie.png
  assets/cover_rufus.png
  assets/cover_trio_master.png
  scripts/rotate_cover_art.py
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"

PUBLIC_ROOT_COVER = ROOT / "cover.png"
ASSETS_CURRENT_COVER = ASSETS_DIR / "current_cover.png"
MANIFEST_PATH = ASSETS_DIR / "cover_rotation_manifest.json"

# Monthly rotation:
# Jan = standard/logo
# Feb = Alex
# Mar = Jamie
# Apr = Rufus
# May = Trio
# Jun = standard/logo
# Jul = Alex
# Aug = Jamie
# Sep = Rufus
# Oct = Trio
# Nov = standard/logo
# Dec = Alex
MONTH_TO_COVER = {
    1: "cover.png",
    2: "cover_alex.png",
    3: "cover_jamie.png",
    4: "cover_rufus.png",
    5: "cover_trio_master.png",
    6: "cover.png",
    7: "cover_alex.png",
    8: "cover_jamie.png",
    9: "cover_rufus.png",
    10: "cover_trio_master.png",
    11: "cover.png",
    12: "cover_alex.png",
}

FALLBACK_COVER = "cover.png"

MIN_SIZE = 1400
MAX_SIZE = 3000
TARGET_SIZE = 2048


def _safe_print(message: str) -> None:
    print(message, flush=True)


def _validate_and_normalize_image(src: Path, dest: Path) -> None:
    """
    Normalize to podcast-platform-safe artwork:
    - square
    - RGB
    - PNG
    - 1400x1400 minimum
    - 3000x3000 maximum
    """
    with Image.open(src) as image:
        image = image.convert("RGB")

        width, height = image.size
        if width != height:
            side = min(width, height)
            left = (width - side) // 2
            top = (height - side) // 2
            image = image.crop((left, top, left + side, top + side))

        width, height = image.size
        if width < MIN_SIZE or height < MIN_SIZE or width > MAX_SIZE or height > MAX_SIZE:
            image = image.resize((TARGET_SIZE, TARGET_SIZE), Image.LANCZOS)

        dest.parent.mkdir(parents=True, exist_ok=True)
        image.save(dest, format="PNG", optimize=True)


def main() -> None:
    # Optional manual override from GitHub Actions:
    # COVER_ART_OVERRIDE=cover_trio_master.png
    override = os.getenv("COVER_ART_OVERRIDE", "").strip()

    today = _dt.datetime.now(_dt.timezone.utc).date()
    month = today.month

    selected_name = override or MONTH_TO_COVER.get(month, FALLBACK_COVER)
    selected_path = ASSETS_DIR / selected_name

    if not selected_path.exists():
        _safe_print(
            f"⚠️ Selected cover missing: assets/{selected_name}. "
            f"Falling back to assets/{FALLBACK_COVER}."
        )
        selected_name = FALLBACK_COVER
        selected_path = ASSETS_DIR / selected_name

    if not selected_path.exists():
        raise FileNotFoundError(
            f"Missing fallback cover too: {selected_path}. "
            "Upload assets/cover.png or adjust MONTH_TO_COVER."
        )

    _validate_and_normalize_image(selected_path, PUBLIC_ROOT_COVER)
    _validate_and_normalize_image(selected_path, ASSETS_CURRENT_COVER)

    manifest = {
        "updated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "selected_cover": f"assets/{selected_name}",
        "public_cover": "cover.png",
        "assets_current_cover": "assets/current_cover.png",
        "month": month,
        "rotation_pattern": MONTH_TO_COVER,
        "note": "RSS should keep using a stable cover.png URL so Spotify can refresh the image without feed-code changes.",
    }

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _safe_print(f"✅ Rotated podcast cover art to assets/{selected_name}")
    _safe_print(f"✅ Updated {PUBLIC_ROOT_COVER.relative_to(ROOT)}")
    _safe_print(f"✅ Updated {ASSETS_CURRENT_COVER.relative_to(ROOT)}")
    _safe_print(f"✅ Wrote {MANIFEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
