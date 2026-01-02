# animate_social.py
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"

SOCIAL_CARD = BASE_DIR / "social_card.jpg"
OUT_MP4 = BASE_DIR / "social_clip.mp4"

CLIP_SECONDS = int(os.getenv("SOCIAL_CLIP_SECONDS", "30"))
FPS = int(os.getenv("SOCIAL_CLIP_FPS", "30"))

def _safe_print(msg: str):
    print(msg, flush=True)

def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def _run(cmd, fail_ok: bool = False) -> int:
    try:
        subprocess.run(cmd, check=True)
        return 0
    except subprocess.CalledProcessError as e:
        if fail_ok:
            return e.returncode
        raise

def _latest_podcast_mp3() -> Optional[Path]:
    files = sorted(AUDIO_DIR.glob("podcast_*.mp3"), key=lambda p: p.name, reverse=True)
    return files[0] if files else None

def create_clip():
    _safe_print(">> 🎬 STARTING VIDEO RENDER...")

    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found in PATH. Install it or use a runner image that includes it.")

    if not SOCIAL_CARD.exists():
        raise FileNotFoundError(f"Missing social card image: {SOCIAL_CARD}")

    audio_path = os.getenv("SOCIAL_AUDIO_FILE", "").strip()
    if audio_path:
        audio = Path(audio_path)
        if not audio.is_absolute():
            audio = (BASE_DIR / audio).resolve()
    else:
        audio = _latest_podcast_mp3()

    if audio and audio.exists():
        _safe_print(f"   Using audio: {audio.name}")
        audio_input = ["-i", str(audio)]
        audio_filter = f"afade=t=in:st=0:d=0.35,afade=t=out:st={max(0, CLIP_SECONDS-0.55)}:d=0.55"
        audio_codec = ["-c:a", "aac", "-b:a", "192k"]
    else:
        _safe_print("   No audio found. Rendering silent clip.")
        audio_input = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        audio_filter = "anull"
        audio_codec = ["-c:a", "aac", "-b:a", "192k"]

    # Fit/pad to vertical 1080x1920 without distortion + fades
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "format=yuv420p,"
        "fade=t=in:st=0:d=0.35,"
        f"fade=t=out:st={max(0, CLIP_SECONDS-0.55)}:d=0.55"
    )

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-loop", "1",
        "-i", str(SOCIAL_CARD),
        *audio_input,
        "-t", str(CLIP_SECONDS),
        "-r", str(FPS),
        "-vf", vf,
        "-af", audio_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        *audio_codec,
        "-movflags", "+faststart",
        str(OUT_MP4),
    ]

    _run(cmd)

    if not OUT_MP4.exists() or OUT_MP4.stat().st_size < 50_000:
        raise RuntimeError(f"Video render did not produce a valid mp4: {OUT_MP4}")

    _safe_print(f"✅ social clip generated: {OUT_MP4}")

if __name__ == "__main__":
    create_clip()
