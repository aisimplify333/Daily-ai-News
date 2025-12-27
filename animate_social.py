import os
import random
import json
import numpy as np
import textwrap
import librosa
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import AudioFileClip, VideoClip, CompositeVideoClip, ImageClip, VideoFileClip, concatenate_videoclips

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
OUTPUT_DIR = BASE_DIR / "social_clips"
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR.mkdir(exist_ok=True)

# THE 30-SECOND FORMULA
TOTAL_DURATION = 30
VIDEO_HOOK_DURATION = 8  # Length of your Veo clip
CTA_DURATION = 5         # Length of the "End Card"

# Styles for the Waveform Section
STYLE = {"bg": (15, 15, 20), "accent": (0, 255, 100), "text": (255, 255, 255)}

# --- 1. UTILS & PHYSICS ---
def get_font(size, bold=True):
    options = ["Arialbd.ttf", "Impact.ttf", "VerdanaBold.ttf"] if bold else ["Arial.ttf"]
    for name in options:
        try: return ImageFont.truetype(name, size)
        except: continue
    return ImageFont.load_default()

def analyze_audio(audio_path, fps=24):
    y, sr = librosa.load(audio_path, sr=None)
    hop_length = int(sr / fps)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    return (rms - np.min(rms)) / (np.max(rms) - np.min(rms))

# --- 2. WAVEFORM RENDERER (For the Middle Section) ---
def make_waveform_frame(t, duration, headline, audio_data, fps, offset_t):
    W, H = 1080, 1920
    img = Image.new('RGB', (W, H), color=STYLE["bg"])
    draw = ImageDraw.Draw(img)
    
    # Sync physics: We must look up the correct audio frame based on GLOBAL time
    frame_idx = int((t + offset_t) * fps)
    current_vol = audio_data[frame_idx] if frame_idx < len(audio_data) else 0.1

    # Draw Bars
    num_bars, bar_width, gap = 20, 35, 20
    start_x = (W - ((num_bars * bar_width) + ((num_bars - 1) * gap))) / 2
    for i in range(num_bars):
        wave_mod = np.sin(i * 0.5 + t * 5) * 0.5 + 0.5
        h_bar = (current_vol * 500) * wave_mod + 20
        x = start_x + i * (bar_width + gap)
        draw.rectangle([x, 1400 - h_bar, x + bar_width, 1400 + h_bar], fill=STYLE["accent"])

    # Draw Headline
    font = get_font(90)
    lines = textwrap.wrap(headline.upper(), width=14)
    y_text = 400
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x_text = (W - (bbox[2] - bbox[0])) / 2
        draw.text((x_text, y_text), line, font=font, fill=STYLE["text"])
        y_text += 110

    return np.array(img)

# --- 3. MAIN ASSEMBLY ENGINE ---
def create_hybrid_clip():
    print(" >> 🎬 ASSEMBLING 30s HYBRID TRAILER...")
    
    # A. Load Audio (The Master Track)
    try: latest_audio = sorted(AUDIO_DIR.glob("*.mp3"), key=os.path.getmtime)[-1]
    except: return print("No Audio Found.")
    
    audio_full = AudioFileClip(str(latest_audio))
    # Cut to exactly 30s (Trailer length)
    audio_30s = audio_full.subclip(0, TOTAL_DURATION)
    audio_data = analyze_audio(str(latest_audio)) # Physics data

    # B. Get Metadata
    headline = "DAILY AI NEWS"
    try:
        with open("viral_caption.txt") as f:
            for line in f.read().split("\n"):
                if "🎙️" in line: headline = line.replace("🎙️", "").replace("NEW EPISODE:", "").strip()
    except: pass

    # --- PART 1: THE VEO HOOK (0s - 8s) ---
    veo_path = ASSETS_DIR / "hook_video.mp4"
    if veo_path.exists():
        print("    Found Veo Video Hook...")
        clip_1 = VideoFileClip(str(veo_path)).resize(height=1920)
        # Center Crop to 1080x1920
        clip_1 = clip_1.crop(x1=clip_1.w/2 - 540, width=1080).subclip(0, VIDEO_HOOK_DURATION)
    else:
        print("    No Veo Video found. Generating fallback waveform...")
        # Fallback: Just use waveform if you didn't make a video today
        clip_1 = VideoClip(lambda t: make_waveform_frame(t, VIDEO_HOOK_DURATION, headline, audio_data, 24, 0), duration=VIDEO_HOOK_DURATION)

    # --- PART 2: THE WAVEFORM (8s - 25s) ---
    mid_duration = TOTAL_DURATION - VIDEO_HOOK_DURATION - CTA_DURATION
    clip_2 = VideoClip(lambda t: make_waveform_frame(t, mid_duration, headline, audio_data, 24, VIDEO_HOOK_DURATION), duration=mid_duration)

    # --- PART 3: THE CTA CARD (25s - 30s) ---
    # Uses your cover.png + "Link in Bio" text
    img = Image.new('RGB', (1080, 1920), color=(10, 10, 10))
    draw = ImageDraw.Draw(img)
    
    # Load Cover
    if (ASSETS_DIR / "cover.png").exists():
        cover = Image.open(ASSETS_DIR / "cover.png").resize((800, 800))
        img.paste(cover, (140, 400))
    
    # Draw CTA Text
    font_cta = get_font(100)
    draw.text((180, 1300), "FULL EPISODE", font=font_cta, fill="white")
    draw.rectangle([200, 1450, 880, 1600], fill=STYLE["accent"])
    draw.text((290, 1480), "LINK IN BIO", font=font_cta, fill="black")
    
    clip_3 = ImageClip(np.array(img)).set_duration(CTA_DURATION)

    # --- C. STITCH & EXPORT ---
    final_video = concatenate_videoclips([clip_1, clip_2, clip_3])
    final_video = final_video.set_audio(audio_30s)

    out_file = OUTPUT_DIR / f"hybrid_trailer_{latest_audio.stem}.mp4"
    final_video.write_videofile(str(out_file), fps=24, codec="libx264", audio_codec="aac")
    print(f"✅ TRAILER READY: {out_file}")

if __name__ == "__main__":
    create_hybrid_clip()
