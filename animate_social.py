import os
from pathlib import Path

# MoviePy v2 moved things around; this import works on v2
# and we keep a fallback for v1 environments.
try:
    from moviepy import AudioFileClip, ImageClip, CompositeVideoClip
except Exception:
    from moviepy.editor import AudioFileClip, ImageClip, CompositeVideoClip  # type: ignore

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
ASSETS_DIR = BASE_DIR / "assets"

SOCIAL_CARD = BASE_DIR / "social_card.jpg"
FALLBACK_COVER = ASSETS_DIR / "cover.png"

OUTPUT = BASE_DIR / "social_clip.mp4"

# 9:16 vertical
W, H = 1080, 1920

# X/TikTok friendly teaser length
TARGET_SECONDS = int(os.getenv("SOCIAL_TEASER_SECONDS", "58"))


def _latest_mp3() -> Path:
    files = sorted(AUDIO_DIR.glob("podcast_*.mp3"))
    if not files:
        raise FileNotFoundError(f"No podcast_*.mp3 found in {AUDIO_DIR}")
    return files[-1]


def _subclip_compat(audio, start: float, end: float):
    """
    MoviePy v1: subclip(start, end)
    MoviePy v2: subclipped(start, end)
    """
    if hasattr(audio, "subclip"):
        return audio.subclip(start, end)
    if hasattr(audio, "subclipped"):
        return audio.subclipped(start, end)
    raise AttributeError("AudioFileClip has neither subclip nor subclipped. Check moviepy version.")


def create_clip():
    print(">> 🎬 STARTING VIDEO RENDER...")

    mp3 = _latest_mp3()
    print(f"   Using audio: {mp3.name}")

    # Choose visual
    if SOCIAL_CARD.exists():
        img_path = SOCIAL_CARD
    elif FALLBACK_COVER.exists():
        img_path = FALLBACK_COVER
    else:
        raise FileNotFoundError("Missing social_card.jpg and assets/cover.png")

    audio = AudioFileClip(str(mp3))

    safe_duration = min(float(audio.duration), float(TARGET_SECONDS))
    audio_clip = _subclip_compat(audio, 0, safe_duration)

    # Base image clip
    img = ImageClip(str(img_path)).with_duration(safe_duration)

    # Fit/crop to 1080x1920 without relying on deprecated PIL constants
    # Approach: scale to cover, then center-crop.
    scale = max(W / img.w, H / img.h)
    img = img.resized(scale)
    x1 = int((img.w - W) / 2)
    y1 = int((img.h - H) / 2)
    img = img.cropped(x1=x1, y1=y1, width=W, height=H)

    # Subtle "Ken Burns" zoom-in for motion (2% over clip)
    def zoom(t):
        return 1.0 + 0.02 * (t / safe_duration)

    img = img.resized(zoom)

    video = CompositeVideoClip([img], size=(W, H)).with_audio(audio_clip)

    # Render
    video.write_videofile(
        str(OUTPUT),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        threads=4,
    )

    print(f"✅ social clip created: {OUTPUT}")


if __name__ == "__main__":
    create_clip()
