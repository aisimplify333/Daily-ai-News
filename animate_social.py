import os
import random
import replicate
import requests
from pathlib import Path
from moviepy.editor import AudioFileClip, ImageClip, TextClip, CompositeVideoClip
from moviepy.video.fx.resize import resize

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
OUTPUT_FILE = BASE_DIR / "social_clip.mp4"
COVER_IMAGE = BASE_DIR / "cover.jpg"

# Replicate Model ID (SadTalker - Latest Working Version)
MODEL_ID = "cjwbw/sadtalker:3aa3dac937e567d196aa3e50402f8539da647250646c0780287a419830c2c10b"

def get_latest_episode():
    # Find the latest file starting with "podcast_"
    files = sorted(AUDIO_DIR.glob("podcast_*.mp3"))
    if not files:
        raise FileNotFoundError("No podcast episode found in episode_audio/")
    return files[-1]

def create_talking_head(audio_path, image_path):
    print(" 🤖 ANIMATING ALEX (via Replicate)...")
    try:
        # 1. Upload audio to tmp host (Replicate needs a URL)
        # For simplicity in this script, we will skip the upload complexity 
        # and default to the static image fallback if Replicate is not fully configured with a public URL.
        # However, if you have the API key, we try:
        if not os.environ.get("REPLICATE_API_TOKEN"):
            raise Exception("No Replicate Token found.")

        # Note: In a real production env, you'd upload 'audio_path' to an S3 bucket here.
        # Since we are local/runner, we will use the Static Fallback to save credits/complexity for now.
        raise Exception("Skipping Replicate for stability (using Static Image).")

    except Exception as e:
        print(f" !! ANIMATION FALLBACK: {e}")
        return None

def create_hybrid_clip():
    print(" >> 🎬 STARTING PRODUCTION...")
    
    # 1. Assets
    latest_episode = get_latest_episode()
    print(f"    Using Audio: {latest_episode.name}")
    
    # Load Audio
    full_audio = AudioFileClip(str(latest_episode))
    
    # --- CRITICAL FIX: DURATION CLAMP ---
    # We strip 0.15s to prevent the "IndexError" at the very end of the file
    safe_duration = full_audio.duration - 0.15
    if safe_duration < 1: safe_duration = full_audio.duration # Handle tiny clips
    
    # Trim audio to safe length
    audio_clip = full_audio.subclip(0, safe_duration)
    
    # 2. Visuals (Static Cover)
    # We use the static image which is safer than the API for now
    if not COVER_IMAGE.exists():
        # Create a dummy image if missing (red background)
        from moviepy.video.VideoClip import ColorClip
        video_clip = ColorClip(size=(1080, 1080), color=(200, 0, 0), duration=safe_duration)
    else:
        video_clip = ImageClip(str(COVER_IMAGE)).set_duration(safe_duration)
        video_clip = video_clip.resize(width=1080) # Ensure it's square/social ready

    # 3. Text Overlay (Waveform simulation or Title)
    # Simple Title Overlay
    try:
        txt_clip = TextClip("THE AI EDGE", fontsize=70, color='white', font='Arial-Bold')
        txt_clip = txt_clip.set_position('center').set_duration(safe_duration)
        final_video = CompositeVideoClip([video_clip, txt_clip])
    except:
        # Fallback if ImageMagick is missing
        final_video = video_clip

    # 4. Attach Audio
    final_video = final_video.set_audio(audio_clip)

    # 5. Export
    print(f"    Rendering to {OUTPUT_FILE} ({safe_duration:.1f}s)...")
    final_video.write_videofile(
        str(OUTPUT_FILE), 
        fps=24, 
        codec="libx264", 
        audio_codec="aac",
        ffmpeg_params=["-pix_fmt", "yuv420p"] # Ensures compatibility with all players
    )
    print(" ✅ SOCIAL CLIP COMPLETE.")

if __name__ == "__main__":
    create_hybrid_clip()
