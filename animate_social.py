import os
import random
import replicate
import librosa
import numpy as np
from pathlib import Path
from moviepy.editor import (AudioFileClip, VideoClip, VideoFileClip, 
                            ImageClip, concatenate_videoclips, CompositeVideoClip)
from PIL import Image, ImageDraw, ImageFont

# --- 1. USER CONFIGURATION ---
# PASTE YOUR REPLICATE KEY HERE:
os.environ["REPLICATE_API_TOKEN"] = "r8_YOUR_REPLICATE_KEY_HERE"

# TIMING SETTINGS (Updated per your request)
HOOK_DURATION = 15  # Face speaks for 15 seconds
TOTAL_DURATION = 35 # Total clip is 35 seconds (leaves 20s for CTA)

# FILE NAMES (Must match assets folder exactly)
ALEX_FILE  = "alex_master.png"
JAMIE_FILE = "jamie_master.png"
RUFUS_FILE = "rufus_master.png"
COVER_FILE = "cover.png"

# --- SYSTEM SETUP ---
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
OUTPUT_DIR = BASE_DIR / "social_clips"
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR.mkdir(exist_ok=True)

AVATARS = {
    "ALEX": str(ASSETS_DIR / ALEX_FILE),
    "JAMIE": str(ASSETS_DIR / JAMIE_FILE),
    "RUFUS": str(ASSETS_DIR / RUFUS_FILE)
}
COVER_IMAGE = str(ASSETS_DIR / COVER_FILE)

# --- 2. THE ANIMATOR (CLOUD) ---
def generate_talking_head(audio_path, character="ALEX"):
    print(f" 🤖 ANIMATING {character} ({HOOK_DURATION}s)...")
    cache_path = ASSETS_DIR / f"daily_hook_{character}.mp4"
    
    # Check cache to save money/time
    if cache_path.exists():
        print("    Found cached hook video. Using that.")
        return str(cache_path)

    try:
        output = replicate.run(
            "cjwbw/sadtalker:a519a502c816f7344755a5c276f753232c44414f6b28394a5c9f535359b34360",
            input={
                "source_image": open(AVATARS.get(character, AVATARS["ALEX"]), "rb"),
                "driven_audio": open(audio_path, "rb"),
                "enhancer": "gfpgan", 
                "still": True,
                "preprocess": "full"
            }
        )
        print(f" ✅ VIDEO RECEIVED: {output}")
        return output 
    except Exception as e:
        print(f" !! ANIMATION FAILED: {e}")
        return None

# --- 3. THE WAVEFORM (BODY) ---
def make_waveform_frame(t, duration, audio_data, fps, offset_t):
    W, H = 1080, 1920
    # Create dark background
    img = Image.new('RGB', (W, H), color=(10, 10, 15))
    draw = ImageDraw.Draw(img)
    
    frame_idx = int((t + offset_t) * fps)
    if frame_idx >= len(audio_data): frame_idx = len(audio_data) - 1
    current_vol = audio_data[frame_idx]

    # Draw "Listen on Spotify" Text
    # (Simplified text drawing for reliability)
    # Ideally, you'd use a font file, but default logic works for testing
    
    # Draw Waveform Bars
    center_y = 1400 
    for i in range(20):
        wave_mod = np.sin(i * 0.6 + t * 8) * 0.5 + 0.5
        h = (current_vol * 500) * wave_mod + 20
        x = 190 + i * 35
        # Spotify Green Color
        draw.rectangle([x, center_y - h, x + 30, center_y + h], fill=(30, 215, 96))
    
    return np.array(img)

# --- 4. MASTER ASSEMBLY ---
def create_hybrid_clip():
    print(" >> 🎬 STARTING 15s/20s SPLIT PRODUCTION...")
    
    # 1. Get Audio
    try: latest_audio = sorted(AUDIO_DIR.glob("*.mp3"), key=os.path.getmtime)[-1]
    except: return print(" !! No Audio Found!")
    
    full_audio = AudioFileClip(str(latest_audio))
    
    # 2. Slice Hook Audio (0 to 15s)
    hook_audio = full_audio.subclip(0, HOOK_DURATION)
    hook_audio_path = ASSETS_DIR / "temp_hook.mp3"
    hook_audio.write_audiofile(str(hook_audio_path), logger=None)

    # 3. Animate Hook (Alex)
    hook_video_url = generate_talking_head(hook_audio_path, "ALEX")
    
    if hook_video_url:
        clip_hook = VideoFileClip(hook_video_url).resize(height=1920)
        clip_hook = clip_hook.crop(x1=clip_hook.w/2 - 540, width=1080)
        clip_hook = clip_hook.subclip(0, HOOK_DURATION)
    else:
        clip_hook = ImageClip(AVATARS["ALEX"]).set_duration(HOOK_DURATION)

    # 4. Create Body/CTA (15s to 35s)
    body_duration = TOTAL_DURATION - HOOK_DURATION
    
    # Prepare Waveform Data
    y, sr = librosa.load(str(latest_audio), sr=None)
    rms = librosa.feature.rms(y=y, hop_length=int(sr/24))
    rms = (rms[0] - np.min(rms)) / (np.max(rms) - np.min(rms))
    
    # Create Background (Waveform)
    clip_body = VideoClip(
        lambda t: make_waveform_frame(t, body_duration, rms, 24, HOOK_DURATION), 
        duration=body_duration
    )
    
    # Overlay Cover Art in Center for CTA
    cta_image = ImageClip(COVER_IMAGE).set_duration(body_duration).resize(width=900)
    cta_image = cta_image.set_position(("center", 400)) # Positioned near top-middle
    
    final_body = CompositeVideoClip([clip_body, cta_image])

    # 5. Final Stitch
    final_video = concatenate_videoclips([clip_hook, final_body])
    final_video = final_video.set_audio(full_audio.subclip(0, TOTAL_DURATION))
    
    out_file = OUTPUT_DIR / f"social_{latest_audio.stem}_final.mp4"
    final_video.write_videofile(str(out_file), fps=24)
    print(f"🎉 VIDEO SAVED: {out_file}")

if __name__ == "__main__":
    create_hybrid_clip()
