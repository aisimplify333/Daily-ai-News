import os
import random
import json
import numpy as np
import textwrap
import librosa
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import AudioFileClip, VideoClip, CompositeVideoClip, ImageClip, VideoFileClip

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
OUTPUT_DIR = BASE_DIR / "social_clips"
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR.mkdir(exist_ok=True)

# "Agency" Styles - Fallbacks if no video background is found
STYLES = {
    "TECH":   {"bg": (10, 15, 20),   "accent": (0, 255, 100),   "text": (255, 255, 255)}, 
    "SKEPTIC": {"bg": (20, 0, 0),     "accent": (255, 50, 50),   "text": (255, 255, 255)}, 
    "MONEY":  {"bg": (0, 20, 0),     "accent": (50, 200, 50),   "text": (255, 255, 255)}, 
    "DEFAULT": {"bg": (15, 15, 15),   "accent": (255, 200, 0),   "text": (255, 255, 255)}  
}

# --- 1. REAL AUDIO PHYSICS ENGINE ---
def analyze_audio(audio_path, fps=24):
    """Uses Librosa to extract real volume data for the waveform."""
    print(" 📊 ANALYZING AUDIO PHYSICS...")
    y, sr = librosa.load(audio_path, sr=None)
    
    # Get the volume envelope (Root Mean Square)
    hop_length = int(sr / fps)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    
    # Normalize data to be between 0 and 1
    rms = (rms - np.min(rms)) / (np.max(rms) - np.min(rms))
    return rms

# --- 2. THE RENDERER ---
def make_frame(t, duration, headline, style, audio_data, fps):
    W, H = 1080, 1920
    
    # A. Draw Background (Transparent if using video bg, Solid if not)
    # We return an RGBA image so we can overlay it on video
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0)) 
    draw = ImageDraw.Draw(img)
    
    # If no video background, fill with solid color
    if style.get("is_solid"):
        draw.rectangle([0, 0, W, H], fill=style["bg"])

    # B. REAL Waveform Animation
    # Get the current frame index
    frame_idx = int(t * fps)
    # Safety check for index
    current_vol = audio_data[frame_idx] if frame_idx < len(audio_data) else 0
    
    num_bars = 25
    bar_width = 30
    gap = 15
    total_width = (num_bars * bar_width) + ((num_bars - 1) * gap)
    start_x = (W - total_width) / 2
    
    # Draw bars that react to volume
    for i in range(num_bars):
        # Create a "wave" effect across the bars using sin, scaled by REAL volume
        wave_mod = np.sin(i * 0.5 + t * 5) * 0.5 + 0.5 
        bar_height = (current_vol * 600) * wave_mod + 20 # 20px min height
        
        x = start_x + i * (bar_width + gap)
        y_start = H - 350
        
        # Draw with Rounded look (simulated by drawing slightly larger circles at ends)
        draw.rectangle([x, y_start - bar_height, x + bar_width, y_start], fill=style["accent"])

    # C. Progress Bar (Top - High End Thin Line)
    prog_w = (t / duration) * W
    draw.rectangle([0, 0, prog_w, 15], fill=style["accent"])

    # D. "Agency" Typography
    # Headline
    font_head = get_font(95, bold=True)
    lines = textwrap.wrap(headline.upper(), width=14)
    y_text = 300 # Lowered slightly
    
    # Draw a dark "Scrim" (Gradient shadow) behind text for readability
    draw.rectangle([0, 0, W, 800], fill=(0,0,0, 100)) # Semi-transparent black

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_head)
        w_line = bbox[2] - bbox[0]
        x_text = (W - w_line) / 2
        
        # Hard Drop Shadow for "Pop"
        draw.text((x_text+6, y_text+6), line, font=font_head, fill=(0,0,0, 255))
        draw.text((x_text, y_text), line, font=font_head, fill=style["text"])
        y_text += 115

    # CTA Pill
    draw.rounded_rectangle([340, 1600, 740, 1720], radius=40, outline=style["text"], width=4)
    font_cta = get_font(50, bold=True)
    draw.text((435, 1635), "🔊 SOUND ON", font=font_cta, fill=style["text"])

    return np.array(img)

def get_font(size, bold=True):
    # Try to find a "Pro" font on the system
    options = ["Arialbd.ttf", "Impact.ttf", "VerdanaBold.ttf"] if bold else ["Arial.ttf"]
    for name in options:
        try: return ImageFont.truetype(name, size)
        except: continue
    return ImageFont.load_default()

def create_social_clip():
    print(" >> 🎬 STARTING AGENCY-GRADE RENDER...")
    
    # 1. Find Audio
    try:
        latest_audio = sorted(AUDIO_DIR.glob("*.mp3"), key=os.path.getmtime)[-1]
    except IndexError: return

    # 2. Get Metadata
    headline = "DAILY AI NEWS"
    try:
        with open("viral_caption.txt", "r") as f:
            for line in f.read().split("\n"):
                if "🎙️" in line or "🚀" in line:
                    headline = line.replace("🎙️", "").replace("🚀", "").replace("NEW EPISODE:", "").strip()
                    break
    except: pass

    # 3. Setup Layout & Physics
    audio_clip = AudioFileClip(str(latest_audio))
    duration = min(audio_clip.duration, 59)
    audio_clip = audio_clip.subclip(0, duration)
    
    # Run the Physics Engine
    audio_data = analyze_audio(str(latest_audio))

    # 4. Background Logic (Video vs Color)
    bg_video_path = ASSETS_DIR / "background.mp4"
    style = STYLES["DEFAULT"] # Default Color fallback
    
    if bg_video_path.exists():
        print("    🎥 USING MOTION BACKGROUND VIDEO")
        # Load video, loop it, resize to 9:16
        bg_clip = VideoFileClip(str(bg_video_path), audio=False)
        # Loop video if shorter than audio
        if bg_clip.duration < duration:
            bg_clip = bg_clip.loop(duration=duration)
        bg_clip = bg_clip.subclip(0, duration)
        # Resize to cover (Center Crop logic)
        bg_clip = bg_clip.resize(height=1920) 
        bg_clip = bg_clip.crop(x1=bg_clip.w/2 - 540, width=1080)
        style["is_solid"] = False # Tell renderer NOT to draw solid color
    else:
        print("    🎨 USING SOLID COLOR (Add 'background.mp4' to assets for Motion!)")
        # Create a dummy background clip of solid color
        bg_clip = VideoClip(lambda t: np.zeros((1920, 1080, 3), dtype='uint8'), duration=duration)
        style["is_solid"] = True

    # 5. Composite
    # Generate the Overlay (Text + Waveform)
    overlay_clip = VideoClip(lambda t: make_frame(t, duration, headline, style, audio_data, 24), duration=duration, ismask=False)
    
    # Layer: Background Video -> Cover Art (Optional) -> Overlay
    clips_to_stack = [bg_clip]
    
    if (ASSETS_DIR / "cover.png").exists():
        cover = ImageClip(str(ASSETS_DIR / "cover.png")).set_duration(duration)
        cover = cover.resize(width=600).set_position(("center", 750))
        clips_to_stack.append(cover)
        
    clips_to_stack.append(overlay_clip)
    
    final = CompositeVideoClip(clips_to_stack).set_audio(audio_clip)

    output_filename = OUTPUT_DIR / f"viral_{latest_audio.stem}.mp4"
    final.write_videofile(str(output_filename), fps=24, codec="libx264", audio_codec="aac")
    print(f"✅ AGENCY CLIP READY: {output_filename}")

if __name__ == "__main__":
    create_social_clip()
