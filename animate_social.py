import os
import json
from pathlib import Path

# MoviePy v2 imports (with a compatibility fallback)
try:
    from moviepy import AudioFileClip, ImageClip
except Exception:
    from moviepy.editor import AudioFileClip, ImageClip  # older moviepy

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
META_PATH = BASE_DIR / "episode_metadata.json"

CARD_PATH = BASE_DIR / "social_card.jpg"
OUT_MAIN = BASE_DIR / "social_clip.mp4"

CLIPS_DIR = BASE_DIR / "social_clips"
CLIPS_DIR.mkdir(exist_ok=True)

W, H = 1080, 1920
CLIP_SECONDS = int(os.getenv("SOCIAL_CLIP_SECONDS", "58"))
FPS = int(os.getenv("SOCIAL_FPS", "30"))

def _latest_audio_path() -> Path:
    if META_PATH.exists():
        try:
            meta = json.loads(META_PATH.read_text(encoding="utf-8"))
            fn = meta.get("audio_file")
            if fn:
                p = AUDIO_DIR / fn
                if p.exists():
                    return p
        except Exception:
            pass

    # Fallback: latest by filename
    candidates = sorted(AUDIO_DIR.glob("podcast_*.mp3"), reverse=True)
    if candidates:
        return candidates[0]
    raise FileNotFoundError("No podcast_*.mp3 found in episode_audio/")

def _next_clip_name() -> Path:
    existing = sorted(CLIPS_DIR.glob("clip_*.mp4"))
    if not existing:
        return CLIPS_DIR / "clip_01.mp4"
    last = existing[-1].stem  # clip_05
    try:
        n = int(last.split("_")[1])
    except Exception:
        n = len(existing)
    return CLIPS_DIR / f"clip_{n+1:02d}.mp4"

def _subclip(audio, start, end):
    if hasattr(audio, "subclipped"):
        return audio.subclipped(start, end)
    return audio.subclip(start, end)

def _with_duration(clip, d):
    if hasattr(clip, "with_duration"):
        return clip.with_duration(d)
    return clip.set_duration(d)

def _with_audio(clip, audio):
    if hasattr(clip, "with_audio"):
        return clip.with_audio(audio)
    return clip.set_audio(audio)

def _resized(clip, **kwargs):
    if hasattr(clip, "resized"):
        return clip.resized(**kwargs)
    return clip.resize(**kwargs)

def create_clip():
    audio_path = _latest_audio_path()
    print(">> 🎬 STARTING VIDEO RENDER...")
    print(f"   Using audio: {audio_path.name}")

    audio = AudioFileClip(str(audio_path))
    safe_duration = min(float(CLIP_SECONDS), float(getattr(audio, "duration", CLIP_SECONDS) or CLIP_SECONDS))
    audio_clip = _subclip(audio, 0, safe_duration)

    if not CARD_PATH.exists():
        raise FileNotFoundError("social_card.jpg not found. Run generate_social.py first.")

    base = ImageClip(str(CARD_PATH))
    base = _with_duration(base, safe_duration)

    # Ensure correct size (your card is already 1080x1920, but keep this safe)
    base = _resized(base, height=H)

    final = _with_audio(base, audio_clip)

    # Write outputs
    clip_out = _next_clip_name()

    final.write_videofile(
        str(OUT_MAIN),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="medium",
        ffmpeg_params=["-movflags", "+faststart"],
        verbose=False,
        logger=None,
    )

    # Also keep an archive copy
    try:
        import shutil
        shutil.copyfile(OUT_MAIN, clip_out)
    except Exception:
        pass

    print(f"✅ social clip generated: {OUT_MAIN}")
    print(f"✅ archived clip: {clip_out.name}")

if __name__ == "__main__":
    create_clip()
