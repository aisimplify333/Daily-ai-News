import os
import json
import textwrap
from pathlib import Path
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


def _find_asset(*candidate_names: str) -> Path | None:
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


def _load_font(size: int, bold: bool = True):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejavuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _circle_avatar(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA")
    img = ImageOps.fit(img, (size, size), method=Image.LANCZOS, centering=(0.5, 0.5))
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask=mask)
    return out


def _safe_open(path: Path | None) -> Image.Image | None:
    if not path:
        return None
    try:
        return Image.open(path)
    except Exception:
        return None


def _first_nonempty_line(p: Path) -> str:
    if not p.exists():
        return ""
    txt = p.read_text(encoding="utf-8", errors="ignore").strip()
    for line in txt.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _teasers_from_meta(meta: dict, max_items: int = 2) -> list[str]:
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


def create_social_card():
    if not META_PATH.exists():
        raise FileNotFoundError("episode_metadata.json not found. Run main.py first.")

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

    # Optional subhook (more “agency-grade” than long bullets)
    subhook = (pack.get("card_subhook") or "").strip()

    # Clean and clamp
    hook = hook.replace("#", "").strip()
    if len(hook) > 120:
        hook = hook[:117].rstrip() + "..."

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
    bg = ImageOps.fit(bg, (W, H), method=Image.LANCZOS, centering=(0.5, 0.5))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=10))

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    canvas.paste(bg, (0, 0))

    # Dark overlay for contrast
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 150))
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)

    # Fonts
    headline_font = _load_font(76, bold=True)
    sub_font = _load_font(34, bold=False)
    body_font = _load_font(34, bold=False)
    brand_font = _load_font(32, bold=True)
    tiny_font = _load_font(28, bold=False)

    # Headline block
    wrap_width = 20
    lines = textwrap.wrap(hook.upper(), width=wrap_width)

    y = 140
    for line in lines[:4]:
        draw.text((72 + 3, y + 3), line, font=headline_font, fill=(0, 0, 0, 180))
        draw.text((72, y), line, font=headline_font, fill=(255, 255, 255, 255))
        y += 88

    # Subtitle/date
    if date:
        draw.text((72, y + 10), f"DAILY BRIEF • {date}", font=sub_font, fill=(220, 220, 220, 255))
        y += 60

    # Subhook (preferred) OR teaser bullets (fallback)
    if subhook:
        subhook = subhook.strip()
        if len(subhook) > 85:
            subhook = subhook[:82].rstrip() + "..."
        draw.text((72, y + 10), subhook.upper(), font=body_font, fill=(235, 235, 235, 255))
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

    draw.rounded_rectangle(
        (cta_x, cta_y, cta_x + cta_w, cta_y + cta_h),
        radius=radius,
        fill=(255, 255, 255, 235),
        outline=None
    )

    cta_text = "LISTEN ON SPOTIFY"
    tw = draw.textlength(cta_text, font=_load_font(40, True))
    draw.text(
        (cta_x + (cta_w - tw) / 2, cta_y + 24),
        cta_text,
        font=_load_font(40, True),
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
    draw.text((72, bar_y + 30), "THE AI EDGE", font=_load_font(44, True), fill=(255, 255, 255, 255))
    draw.text((72, bar_y + 80), "AI • MONEY • REGULATION", font=_load_font(28, False), fill=(210, 210, 210, 255))

    out = canvas.convert("RGB")
    out.save(OUT_PATH, quality=92)
    print(f"✅ social card generated: {OUT_PATH}")


if __name__ == "__main__":
    create_social_card()
