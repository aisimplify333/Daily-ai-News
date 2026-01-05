import os
import re
import json
import shutil
import subprocess
import datetime
from pathlib import Path
from typing import Dict, Any, Tuple

BASE_DIR = Path(__file__).parent

EPISODE_META_PATH = BASE_DIR / "episode_metadata.json"
MARKETING_PACK_PATH = BASE_DIR / "marketing_pack.json"

OUT_MP4 = BASE_DIR / "social_hook.mp4"

VIDEO_W = int(os.getenv("HOOK_W", "1080"))
VIDEO_H = int(os.getenv("HOOK_H", "1920"))
DURATION = float(os.getenv("HOOK_SECONDS", "11.0"))  # 8–15 seconds
FPS = int(os.getenv("HOOK_FPS", "30"))

# kinetic | reactions | (blank=auto)
HOOK_VARIANT = os.getenv("HOOK_VARIANT", "").strip().lower()

NUM_TOKEN_RE = re.compile(
    r"(\$?\d[\d,]*(\.\d+)?\s?(?:B|bn|billion|M|million|K|thousand)?|\d+(\.\d+)?%|\b\d{4}\b)",
    re.I,
)

def _safe_print(msg: str):
    print(msg, flush=True)

def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def _run(cmd) -> None:
    subprocess.run(cmd, check=True)

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _pick_date(meta: Dict[str, Any]) -> str:
    d = (meta.get("date") or "").strip()
    return d or datetime.date.today().isoformat()

def _pick_hook(meta: Dict[str, Any], pack: Dict[str, Any]) -> str:
    h = (pack.get("hook") or meta.get("marketing_pack", {}).get("hook") or "").strip()
    if h:
        return h[:64]
    t = (meta.get("title") or "NEW EPISODE LIVE").strip()
    return t[:64]

def _pick_top_story(meta: Dict[str, Any]) -> Tuple[str, str, str]:
    stories = meta.get("stories") if isinstance(meta.get("stories"), list) else []
    if not stories or not isinstance(stories[0], dict):
        return ("TODAY'S AI SHOCK", "", "")
    s0 = stories[0]
    headline = (s0.get("headline") or s0.get("title") or "TODAY'S AI SHOCK").strip()[:92]
    publisher = (s0.get("publisher") or "").strip()[:30]

    dp = s0.get("data_points") if isinstance(s0.get("data_points"), list) else []
    blob = " ".join([str(x) for x in dp if str(x).strip()])
    if not blob:
        blob = " ".join([headline, (s0.get("why_shocking") or "")])

    m = NUM_TOKEN_RE.search(blob)
    token = (m.group(1).strip() if m else "")
    return (headline, publisher, token[:16])

def _auto_variant(date_str: str) -> str:
    # alternate daily for variety
    try:
        day = int(date_str.split("-")[-1])
        return "kinetic" if day % 2 == 1 else "reactions"
    except Exception:
        return "kinetic"

def _ff_escape(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\\", "\\\\")
    s = s.replace(":", "\\:")
    s = s.replace("'", "\\'")
    s = s.replace("%", "\\%")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _find_font() -> str:
    candidates = [
        os.getenv("FONT_FILE", "").strip(),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return ""

def _render(cmd_common_prefix, vf: str) -> None:
    # Add silent audio track for platform compatibility
    cmd = [
        *cmd_common_prefix,
        "-vf", vf,
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-shortest",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        "-crf", "26",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(OUT_MP4),
    ]
    _run(cmd)

def _render_kinetic(hook: str, headline: str, publisher: str, num_token: str, date_str: str) -> None:
    font = _find_font()
    font_arg = f":fontfile={_ff_escape(font)}" if font else ""

    hook = hook.upper()
    num_token = (num_token or "BREAKING").upper()

    hook_e = _ff_escape(hook)
    headline_e = _ff_escape(headline)
    pub_e = _ff_escape(publisher)
    num_e = _ff_escape(num_token)
    date_e = _ff_escape(date_str)

    alpha = f"if(lt(t,0.6),t/0.6, if(lt(t,{DURATION-0.6}), 1, ({DURATION}-t)/0.6))"

    filters = []
    filters.append(f"drawtext=text='THE AI EDGE'{font_arg}:fontsize=42:fontcolor=white:x=60:y=60:alpha='{alpha}'")
    filters.append(f"drawtext=text='{date_e}'{font_arg}:fontsize=38:fontcolor=white:x=w-260:y=70:alpha='{alpha}'")

    filters.append(f"drawtext=text='{hook_e}'{font_arg}:fontsize=78:fontcolor=white:x=(w-text_w)/2:y=150:alpha='{alpha}'")
    filters.append(f"drawtext=text='{num_e}'{font_arg}:fontsize=220:fontcolor=white:x=(w-text_w)/2:y=(h/2-280):alpha='{alpha}'")

    if pub_e:
        filters.append(f"drawtext=text='Source\\: {pub_e}'{font_arg}:fontsize=44:fontcolor=white:x=(w-text_w)/2:y=(h/2+10):alpha='{alpha}'")

    filters.append(f"drawtext=text='{headline_e}'{font_arg}:fontsize=58:fontcolor=white:x=(w-text_w)/2:y=(h/2+90):alpha='{alpha}'")
    filters.append(f"drawtext=text='SOUND ON'{font_arg}:fontsize=60:fontcolor=red:x=(w-text_w)/2:y=h-220:alpha='{alpha}'")

    vf = ",".join(filters)

    cmd_common = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=black:s={VIDEO_W}x{VIDEO_H}:d={DURATION}:r={FPS}",
    ]
    _safe_print(">> Rendering social_hook.mp4 (kinetic)...")
    _render(cmd_common, vf)

def _render_reactions(hook: str, headline: str, publisher: str, num_token: str, date_str: str) -> None:
    font = _find_font()
    font_arg = f":fontfile={_ff_escape(font)}" if font else ""

    hook = hook.upper()
    num_token = (num_token or "BREAKING").upper()

    hook_e = _ff_escape(hook)
    headline_e = _ff_escape(headline)
    pub_e = _ff_escape(publisher)
    num_e = _ff_escape(num_token)
    date_e = _ff_escape(date_str)

    alpha = f"if(lt(t,0.6),t/0.6, if(lt(t,{DURATION-0.6}), 1, ({DURATION}-t)/0.6))"

    vf = [
        f"drawtext=text='THE AI EDGE'{font_arg}:fontsize=42:fontcolor=white:x=60:y=60:alpha='{alpha}'",
        f"drawtext=text='{date_e}'{font_arg}:fontsize=38:fontcolor=white:x=w-260:y=70:alpha='{alpha}'",
        f"drawtext=text='{hook_e}'{font_arg}:fontsize=70:fontcolor=white:x=(w-text_w)/2:y=140:alpha='{alpha}'",
        f"drawtext=text='{num_e}'{font_arg}:fontsize=170:fontcolor=white:x=(w-text_w)/2:y=330:alpha='{alpha}'",
        f"drawtext=text='{headline_e}'{font_arg}:fontsize=54:fontcolor=white:x=(w-text_w)/2:y=540:alpha='{alpha}'",
    ]

    tile_y = 860
    tile_h = 220
    pad = 60
    tile_w = int((VIDEO_W - pad * 2 - 40 * 2) / 3)

    # ALEX
    x1 = pad
    vf += [
        f"drawbox=x={x1}:y={tile_y}:w={tile_w}:h={tile_h}:color=white@0.08:t=fill",
        f"drawtext=text='ALEX\\: NO WAY'{font_arg}:fontsize=46:fontcolor=white:x={x1+30}:y={tile_y+75}:alpha='{alpha}'",
        f"drawtext=text='REACTION\\: SHOCK'{font_arg}:fontsize=40:fontcolor=white:x={x1+30}:y={tile_y+140}:alpha='{alpha}'",
    ]

    # JAMIE
    x2 = pad + tile_w + 40
    vf += [
        f"drawbox=x={x2}:y={tile_y}:w={tile_w}:h={tile_h}:color=white@0.08:t=fill",
        f"drawtext=text='JAMIE\\: WHO GETS HIT?'{font_arg}:fontsize=46:fontcolor=white:x={x2+30}:y={tile_y+75}:alpha='{alpha}'",
        f"drawtext=text='REACTION\\: WORRIED'{font_arg}:fontsize=40:fontcolor=white:x={x2+30}:y={tile_y+140}:alpha='{alpha}'",
    ]

    # RUFUS
    x3 = pad + (tile_w + 40) * 2
    vf += [
        f"drawbox=x={x3}:y={tile_y}:w={tile_w}:h={tile_h}:color=white@0.08:t=fill",
        f"drawtext=text='RUFUS\\: FOLLOW THE MONEY'{font_arg}:fontsize=46:fontcolor=white:x={x3+30}:y={tile_y+75}:alpha='{alpha}'",
        f"drawtext=text='REACTION\\: COLD'{font_arg}:fontsize=40:fontcolor=white:x={x3+30}:y={tile_y+140}:alpha='{alpha}'",
    ]

    if pub_e:
        vf.append(f"drawtext=text='Source\\: {pub_e}'{font_arg}:fontsize=44:fontcolor=white:x=(w-text_w)/2:y=h-260:alpha='{alpha}'")
    vf.append(f"drawtext=text='SOUND ON'{font_arg}:fontsize=60:fontcolor=red:x=(w-text_w)/2:y=h-210:alpha='{alpha}'")

    cmd_common = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=black:s={VIDEO_W}x{VIDEO_H}:d={DURATION}:r={FPS}",
    ]
    _safe_print(">> Rendering social_hook.mp4 (reactions)...")
    _render(cmd_common, ",".join(vf))

def main():
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found; required to render social_hook.mp4")

    meta = _load_json(EPISODE_META_PATH)
    pack = _load_json(MARKETING_PACK_PATH)

    date_str = _pick_date(meta)
    hook = _pick_hook(meta, pack)
    headline, publisher, num_token = _pick_top_story(meta)

    variant = HOOK_VARIANT or _auto_variant(date_str)
    if variant not in ("kinetic", "reactions"):
        variant = "kinetic"

    _safe_print(f">> Hook variant: {variant}")
    _safe_print(f">> Hook: {hook}")
    _safe_print(f">> Top: {headline} | {publisher} | {num_token or 'NO_NUM'}")

    if variant == "reactions":
        _render_reactions(hook, headline, publisher, num_token, date_str)
    else:
        _render_kinetic(hook, headline, publisher, num_token, date_str)

    _safe_print(f"✅ Hook video ready: {OUT_MP4}")

if __name__ == "__main__":
    main()
