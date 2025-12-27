import os
import json
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
# UPDATED: New import style for v2.0+
from moviepy import AudioFileClip, VideoClip

# --- CONFIGURATION ---
AUDIO_DIR = "episode_audio"
OUTPUT_FILE = "social_clip.mp4"
META_FILE = "episode_metadata.json"
WIDTH, HEIGHT = 1080, 1920  # 9:16 Vertical Video

# --- PRO PALETTE ---
BG_COLOR = (5, 5, 10)           # Almost Black (Cinematic)
CIRCUIT_DIM = (30, 30, 50)      # Subtle Structure
CIRCUIT_LIT = (0, 255, 200)     # Neon Cyan (Energy)
TEXT_WHITE = (255, 255, 255)
TEXT_GRAY = (150, 150, 150)
ACCENT_RED = (255, 50, 50)      # "Recording" Red
PROGRESS_BAR = (255, 200, 0)    # Yellow Retention Bar

# --- CIRCUIT PATH (The "A" Logo) ---
A_POINTS = [
    (0.2, 0.7), (0.5, 0.3), (0.8, 0.7), # Legs
    (0.35, 0.5), (0.65, 0.5)            # Crossbar
]

def get_best_font(size):
    """Finds a bold font on Linux/Mac/Windows to avoid the 'Default' look."""
    font_names = [
        "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arialbd.ttf", 
        "Impact.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except: continue
    return ImageFont.load_default()

def interpolate(p1, p2, t):
    x = p1[0] + (p2[0] - p1[0]) * t
    y = p1[1] + (p2[1] - p1[1]) * t
    return (x, y)

def make_frame(t, duration, title, hook):
    # 1. SETUP CANVAS
    img = Image.new('RGB', (WIDTH, HEIGHT), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 2. DRAW STATIC CIRCUIT (Background Texture)
    pixels = [(p[0] * WIDTH, p[1] * HEIGHT) for p in A_POINTS]
    draw.line([pixels[0], pixels[1], pixels[2]], fill=CIRCUIT_DIM, width=25)
    draw.line([pixels[3], pixels[4]], fill=CIRCUIT_DIM, width=25)
    
    # 3. DRAW MOVING ENERGY PULSE
    loop_duration = 2.5 
    loop_t = (t % loop_duration) / loop_duration
    
    current_pos = pixels[0]
    if loop_t < 0.4:
        current_pos = interpolate(pixels[0], pixels[1], loop_t/0.4)
    elif loop_t < 0.8:
        current_pos = interpolate(pixels[1], pixels[2], (loop_t-0.4)/0.4)
    else:
        current_pos = interpolate(pixels[3], pixels[4], (loop_t-0.8)/0.2)
        
    x, y = current_pos
    draw.ellipse([x-60, y-60, x+60, y+60], fill=(0, 50, 50))
    draw.ellipse([x-30, y-30, x+30, y+30], fill=CIRCUIT_LIT)
    
    # 4. TYPOGRAPHY (The "Pro" Layout)
    font_header = get_best_font(60)
    font_headline = get_best_font(110) 
    font_sub = get_best_font(50)

    draw.rectangle([80, 150, 500, 230], fill=(20, 20, 30), outline=TEXT_GRAY, width=2)
    draw.text((100, 160), "🎙️ AI EDGE DAILY", font=font_header, fill=TEXT_WHITE)
    
    words = title.upper().split()
    y_text = 400
    line = ""
    for word in words:
        test_line = line + word + " "
        w = draw.textlength(test_line, font=font_headline)
        if w < WIDTH - 160: 
            line = test_line
        else:
            w_final = draw.textlength(line, font=font_headline)
            x_centered = (WIDTH - w_final) / 2
            draw.text((x_centered, y_text), line, font=font_headline, fill=TEXT_WHITE)
            y_text += 130
            line = word + " "
    w_final = draw.textlength(line, font=font_headline)
    x_centered = (WIDTH - w_final) / 2
    draw.text((x_centered, y_text), line, font=font_headline, fill=TEXT_WHITE)

    # 5. RETENTION FEATURES
    if (t * 2) % 2 > 1:
        draw.rectangle([WIDTH/2 - 150, 1600, WIDTH/2 + 150, 1680], fill=ACCENT_RED)
        draw.text((WIDTH/2 - 110, 1615), "🔊 SOUND ON", font=font_sub, fill=TEXT_WHITE)
    else:
         draw.rectangle([WIDTH/2 - 150, 1600, WIDTH/2 + 150, 1680], outline=ACCENT_RED, width=3)
         draw.text((WIDTH/2 - 110, 1615), "🔊 SOUND ON", font=font_sub, fill=ACCENT_RED)

    bar_width = (t / duration) * WIDTH
    draw.rectangle([0, HEIGHT-30, bar_width, HEIGHT], fill=PROGRESS_BAR)
    
    return np.array(img)

def generate_video():
    print(" >> 🎬 GENERATING PRO SOCIAL CLIP...")
    
    today = os.popen('date +%Y-%m-%d').read().strip()
    audio_path = f"{AUDIO_DIR}/podcast_{today}.mp3"
    
    if not os.path.exists(audio_path):
        files = [f for f in os.listdir(AUDIO_DIR) if f.endswith('.mp3')]
        if files: audio_path = os.path.join(AUDIO_DIR, files[0])
        else: 
            print(" !! AUDIO MISSING.")
            return

    try:
        with open(META_FILE) as f:
            data = json.load(f)
            title = data.get("title", "BREAKING AI NEWS")
            hook = data.get("hook", "Listen to the full episode now.")
    except:
        title = "AI NEWS DAILY"
        hook = "Listen Now"

    # UPDATED: API changes for MoviePy 2.0
    audio_clip = AudioFileClip(audio_path)
    duration = min(audio_clip.duration, 25) 
    audio_clip = audio_clip.subclipped(0, duration) # renamed from subclip()
    
    video = VideoClip(lambda t: make_frame(t, duration, title, hook), duration=duration)
    video = video.with_audio(audio_clip) # renamed from set_audio()
    
    # Export remains mostly the same
    video.write_videofile(OUTPUT_FILE, fps=24, codec="libx264", audio_codec="aac")
    print(f"DONE: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_video()
