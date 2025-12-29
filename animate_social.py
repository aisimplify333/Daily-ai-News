import os
import requests # Needed to download the video
import replicate
import librosa
import numpy as np
from pathlib import Path
from moviepy.editor import (AudioFileClip, VideoClip, VideoFileClip, 
                            ImageClip, concatenate_videoclips, CompositeVideoClip)
from PIL import Image, ImageDraw

# --- 1. USER CONFIGURATION ---
# Load from GitHub Secrets (Safety First!)
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN") 
if REPLICATE_TOKEN:
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_TOKEN

# TIMING SETTINGS
HOOK_DURATION = 15  
TOTAL_DURATION = 35 

# FILE NAMES
ALEX_FILE  = "alex_master.png"
JAMIE_FILE = "jamie_master.png"
RUFUS_FILE = "rufus_master.png"
COVER_FILE = "cover.png"

# --- SYSTEM SETUP ---
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
ASSETS_DIR = BASE_DIR / "assets"

# Force output to root so git_add works easily
OUTPUT_FILE = BASE_DIR / "social_clip.mp4" 

AVATARS = {
    "ALEX": str(ASSETS_DIR / ALEX_FILE),
    "JAMIE": str(ASSETS_DIR / JAMIE_FILE),
    "RUFUS": str(ASSETS_DIR / RUFUS_FILE)
}
COVER_IMAGE = str(ASSETS_DIR / COVER_FILE)

# --- 2. THE ANIMATOR (CLOUD) ---
def generate_talking_head(audio_path, character="ALEX"):
    print(f" 🤖 ANIMATING {character} ({HOOK_DURATION}s)...")
    
    # Replicate SadTalker Model
    try:
        output_url = replicate.run(
            "cjwbw/sadtalker:3aa3dac937e567d196aa3e50402f8539da647250646c0780287a419830c2c10b",
            input={
                "source_image": open(AVATARS.get(character, AVATARS["ALEX"]), "rb"),
                "driven_audio": open(audio_path, "rb"),
                "enhancer": "gfpgan", 
                "still": True,
                "preprocess": "full"
            }
        )
        print(f" ✅ URL RECEIVED: {output_url}")
        
        # DOWNLOAD THE VIDEO (Fix for MoviePy)
        local_video_path = ASSETS_DIR / "temp_face.mp4"
        response = requests.get(output_url)
        with open(local_video_path, "wb") as f:
            f.write(response.content)
            
        return str(local_video_path)

    except Exception as e:
        print(f" !! ANIMATION FAILED: {e}")
        return None

# --- 3. THE WAVEFORM (BODY) ---
def make_waveform_frame(t, duration, audio_data, fps, offset_t):
    W, H = 1080, 1920
    # Dark Background
    img = Image.new('RGB', (W, H), color=(10, 10, 15))
    draw = ImageDraw.Draw(img)
    
    frame_idx = int((t + offset_t) * fps)
    if frame_idx >= len(audio_data): frame_idx = len(audio_data) - 1
    current_vol = audio_data[frame_idx]

    # Draw Waveform Bars (Spotify Style)
    center_y = 1400 
    for i in range(20):
        # Math to make them dance
        wave_mod = np.sin(i * 0.6 + t * 8) * 0.5 + 0.5
        h = (current_vol * 500) * wave_mod + 20
        x = 190 + i * 35
        # Draw Bar
        draw.rectangle([x, center_y - h, x + 30, center_y + h], fill=(30, 215, 96))
    
    return np.array(img)

# --- 4. MASTER ASSEMBLY ---
def create_hybrid_clip():
    print(" >> 🎬 STARTING PRODUCTION...")
    
    # 1. Get Latest Audio
    try: 
        latest_audio = sorted(AUDIO_DIR.glob("*.mp3"), key=os.path.getmtime)[-1]
        print(f"    Using Audio: {latest_audio.name}")
    except: 
        return print(" !! No Audio Found in episode_audio/!")
    
    full_audio = AudioFileClip(str(latest_audio))
    
    # 2. Slice Hook Audio (0 to 15s)
    hook_audio = full_audio.subclip(0, HOOK_DURATION)
    hook_audio_path = ASSETS_DIR / "temp_hook.mp3"
    hook_audio.write_audiofile(str(hook_audio_path), logger=None)

    # 3. Animate Hook (Alex)
    # Note: If your main.py saves who is speaking, pass that here. 
    # For now, defaulting to ALEX.
    face_video_path = generate_talking_head(hook_audio_path, "ALEX")
    
    if face_video_path:
        clip_hook = VideoFileClip(face_video_path).resize(height=1920)
        clip_hook = clip_hook.crop(x1=clip_hook.w/2 - 540, width=1080)
        clip_hook = clip_hook.subclip(0, HOOK_DURATION)
    else:
        # Fallback if Replicate fails
        print("    Using Static Image Fallback")
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
    
    # Overlay Cover Art
    cta_image = ImageClip(COVER_IMAGE).set_duration(body_duration).resize(width=900)
    cta_image = cta_image.set_position(("center", 400))
    
    final_body = CompositeVideoClip([clip_body, cta_image])

    # 5. Final Stitch
    final_video = concatenate_videoclips([clip_hook, final_body])
    final_video = final_video.set_audio(full_audio.subclip(0, TOTAL_DURATION))
    
    final_video.write_videofile(str(OUTPUT_FILE), fps=24)
    print(f"🎉 VIDEO SAVED: {OUTPUT_FILE}")

if __name__ == "__main__":
    create_hybrid_clip()
