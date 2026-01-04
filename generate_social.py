import os
import json
import textwrap
from pathlib import Path
from typing import Optional, List

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"

META_PATH = BASE_DIR / "episode_metadata.json"
HOOK_PATH = BASE_DIR / "viral_caption.txt"
OUT_PATH = BASE_DIR / "social_card.jpg"

# Public “one link” (use your GitHub Pages redirect)
LISTEN_URL = os.getenv(
    "LISTEN_URL",
    "https://aisimplify333.github.io/Daily-ai-News/listen/"
)

# x (Twitter/X) | ig (Instagram/TikTok)
CTA_MODE = os.getenv("CTA_MODE", "x").strip().lower()

W, H = 1080, 1920


# ----------------------------
# Pillow compatibility helpers
# ----------------------------
def _resample_lanczos():
    # Pillow >= 9: Image.Resampling.LANCZOS
    # Older: Image.LANCZOS
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)


# ----------------------------
# Assets / fonts
# ----------------------------
def _find_asset(*candidate_names: str) -> Optional[Path]:
    """Find asset by exact name or case-insensitive match (Linux-safe)."""
    for name in candidate_names:
        p = ASSETS_DIR / name
        if p.exists():
            return p

    if not ASSETS_DIR.exists():
        return None

    lower_map = {p.name.lower(): p for p in ASSETS_DIR.glob("*") if p.is_file()}
    for name in candidate_names:
        p = lower_map.get(name.lower())
        if p:
            return p
    return None


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    # GitHub Actions (ubuntu-latest) typically has DejaVu available.
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _safe_open(path: Optional[Path]) -> Optional[Image.Image]:
    if not path:
        return None
    try:
        return Image.open(path)
    except Exception:
        return None


def _circle_avatar(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA")
    img = ImageOps.fit(img, (size, size), method=_resample_lanczos(), centering=(0.5, 0.5))
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask=mask)
    return out


# ----------------------------
# Text helpers
# ----------------------------
def _first_nonempty_line(p: Path) -> str:
    if not p.exists():
        return ""
    txt = p.read_text(encoding="utf-8", errors="ignore").strip()
    for line in txt.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _teasers_from_meta(meta: dict, max_items: int = 2) -> List[str]:
    stories = meta.get("stories", [])
    teasers = []
    if isinstance(stories, list):
        for s in stories:
            if not isinstance(s, dict):
                continue
            h = (s.get("headline") or "").strip()
            if h:
                teasers.append(h)
            if len(teasers) >= max_items:
                break
    return teasers


def _wrap_by_pixels(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    """
    Wrap text into lines such that each line fits within max_width pixels.
    """
    words = (text or "").split()
    if not words:
        return []
    lines = []
    cur = words[0]
    for w in words[1:]:
        candidate = cur + " " + w
        if draw.textlength(candidate, font=font) <= max_width:
            cur = candidate
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _draw_text_shadow(draw: ImageDraw.ImageDraw, xy, text, font, fill, shadow=(0, 0, 0, 180), offset=(3, 3)):
    x, y = xy
    ox, oy = offset
    draw.text((x + ox, y + oy), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius: int, fill):
    # Fallback if rounded_rectangle isn’t available.
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=None)
    else:
        draw.rectangle(box, fill=fill, outline=None)


# ----------------------------
# Main
# ----------------------------
def create_social_card():
    if not META_PATH.exists():
        raise FileNotFoundError("episode_metadata.json not found. Run mani.py first.")

    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    date = (meta.get("date") or "").strip()

    # Prefer structured “marketing pack” hook over raw viral_caption.txt lines.
    pack = meta.get("marketing_pack") if isinstance(meta.get("marketing_pack"), dict) else {}
    hook = (
        (meta.get("card_headline") or "").strip()
        or (pack.get("hook") or "").strip()
        or _first_nonempty_line(HOOK_PATH)
        or (meta.get("title") or "THE AI EDGE").strip()
    )

    subhook = (pack.get("card_subhook") or "").strip()

    # Clean and clamp
    hook = hook.replace("#", "").strip()
    if len(hook) > 140:
        hook = hook[:137].rstrip() + "..."

    teasers = _teasers_from_meta(meta, max_items=2)

    # Assets (case-insensitive safe)
    cover_path = _find_asset("cover.png", "cover.jpg", "cover.jpeg")
    alex_path = _find_asset("alex_master.png")
    jamie_path = _find_asset("jamie_master.png", "Jamie_master.png")
    rufus_path = _find_asset("rufus_master.png")

    # Background
    bg_src = _safe_open(cover_path)
    if bg_src is None:
        bg_src = Image.new("RGBA", (W, H), (10, 10, 10, 255))

    bg = bg_src.convert("RGBA")
    bg = ImageOps.fit(bg, (W, H), method=_resample_lanczos(), centering=(0.5, 0.5))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=10))

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    canvas.paste(bg, (0, 0))

    # Dark overlay for contrast
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 150))
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)

    # Fonts
    headline_font_size = 76
    headline_font = _load_font(headline_font_size, bold=True)
    sub_font = _load_font(34, bold=False)
    body_font = _load_font(34, bold=False)
    brand_font = _load_font(32, bold=True)
    tiny_font = _load_font(28, bold=False)

    # Headline block (wrap by pixel width; auto-shrink if needed)
    max_text_width = W - 144  # 72px padding on both sides
    max_lines = 4

    hook_upper = hook.upper()
    lines = _wrap_by_pixels(draw, hook_upper, headline_font, max_text_width)

    # If too many lines, reduce font until it fits (down to 56)
    while len(lines) > max_lines and headline_font_size > 56:
        headline_font_size -= 4
        headline_font = _load_font(headline_font_size, bold=True)
        lines = _wrap_by_pixels(draw, hook_upper, headline_font, max_text_width)

    # If still too long, hard clamp to 4 lines
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        # add ellipsis to last line if it looks truncated
        if not lines[-1].endswith("..."):
            lines[-1] = (lines[-1][: max(0, len(lines[-1]) - 4)].rstrip() + "...")

    y = 140
    line_step = int(headline_font_size * 1.15)

    for line in lines:
        _draw_text_shadow(draw, (72, y), line, font=headline_font, fill=(255, 255, 255, 255))
        y += line_step

    # Subtitle/date
    if date:
        draw.text((72, y + 10), f"DAILY BRIEF • {date}", font=sub_font, fill=(220, 220, 220, 255))
        y += 60

    # Subhook (preferred) OR teaser bullets (fallback)
    if subhook:
        subhook_clean = subhook.strip()
        if len(subhook_clean) > 85:
            subhook_clean = subhook_clean[:82].rstrip() + "..."
        draw.text((72, y + 10), subhook_clean.upper(), font=body_font, fill=(235, 235, 235, 255))
        y += 58
    elif teasers:
        y_tease = y + 10
        for t in teasers[:2]:
            t = t.strip()
            if len(t) > 70:
                t = t[:67].rstrip() + "..."
            bullet = f"• {t}"
            draw.text((72, y_tease), bullet, font=body_font, fill=(235, 235, 235, 255))
            y_tease += 48

    # CTA button above cast bar
    bar_h = 380
    bar_y = H - bar_h

    cta_w, cta_h = W - 144, 96
    cta_x, cta_y = 72, bar_y - 160
    radius = 24

    _rounded_rect(
        draw,
        (cta_x, cta_y, cta_x + cta_w, cta_y + cta_h),
        radius=radius,
        fill=(255, 255, 255, 235),
    )

    cta_font = _load_font(40, True)
    cta_text = "LISTEN ON SPOTIFY"
    tw = draw.textlength(cta_text, font=cta_font)
    draw.text(
        (cta_x + (cta_w - tw) / 2, cta_y + 24),
        cta_text,
        font=cta_font,
        fill=(0, 0, 0, 255),
    )

    # Platform-accurate link cue
    cta_hint = "LINK IN REPLY" if CTA_MODE == "x" else "LINK IN BIO"
    draw.text(
        (72, cta_y + 110),
        f"{cta_hint} • {LISTEN_URL.replace('https://', '').replace('http://', '')}",
        font=tiny_font,
        fill=(210, 210, 210, 255),
    )

    # Bottom cast bar
    bar = Image.new("RGBA", (W, bar_h), (0, 0, 0, 170))
    canvas.paste(bar, (0, bar_y), bar)

    # Load avatars
    alex_img = _safe_open(alex_path)
    jamie_img = _safe_open(jamie_path)
    rufus_img = _safe_open(rufus_path)

    avatar_size = 160
    x_positions = [200, 540, 880]
    labels = ["ALEX", "JAMIE", "RUFUS"]
    imgs = [alex_img, jamie_img, rufus_img]

    for x, label, im in zip(x_positions, labels, imgs):
        if im is None:
            im = Image.new("RGBA", (avatar_size, avatar_size), (80, 80, 80, 255))
        av = _circle_avatar(im, avatar_size)
        canvas.paste(av, (x - avatar_size // 2, bar_y + 110), av)

        tw = draw.textlength(label, font=brand_font)
        draw.text((x - tw / 2, bar_y + 290), label, font=brand_font, fill=(255, 255, 255, 255))

    # Brand mark
    brand_title_font = _load_font(44, True)
    brand_sub_font = _load_font(28, False)

    draw.text((72, bar_y + 30), "THE AI EDGE", font=brand_title_font, fill=(255, 255, 255, 255))
    draw.text((72, bar_y + 80), "AI • MONEY • REGULATION", font=brand_sub_font, fill=(210, 210, 210, 255))

    out = canvas.convert("RGB")
    out.save(OUT_PATH, quality=92)
    print(f"✅ social card generated: {OUT_PATH}")


if __name__ == "__main__":
    create_social_card()
