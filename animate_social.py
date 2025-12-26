import os
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
COVER_PATH = BASE_DIR / "cover.png" # <--- FIXED: Look for PNG
META_PATH = BASE_DIR / "episode_metadata.json"
OUTPUT_GIF = BASE_DIR / "social_surge.gif"

def create_energy_gif():
    print("--- STARTING VFX ENGINE ---")
    
    # 1. Load Data
    if not META_PATH.exists(): headline = "DAILY AI NEWS"
    else:
        with open(META_PATH) as f: headline = json.load(f).get("title", "DAILY AI NEWS").upper()

    # 2. Load Image (Smart Find)
    try:
        # Check Root first, then Assets
        if COVER_PATH.exists(): 
            img_path = COVER_PATH
        elif (ASSETS_DIR / "cover.png").exists(): 
            img_path = ASSETS_DIR / "cover.png"
        else: 
            print(" >> [ERROR] cover.png NOT FOUND")
            return

        base = Image.open(img_path).convert("RGBA").resize((1080, 1080))
    except Exception as e: 
        print(f" >> [ERROR] {e}")
        return

    # 3. Setup Text
    try: font = ImageFont.truetype("arial.ttf", 80)
    except: font = ImageFont.load_default()
    
    frames = []
    # Create 10 frames for the loop
    for i in range(10):
        # A. Create the "Surge" Effect (Brightness Pulse)
        # We simulate energy by boosting brightness rhythmically
        factor = 1.0 + (0.3 * abs(i - 5) / 5) # Oscillates between 1.0 and 1.3
        
        frame = base.copy()
        enhancer = ImageEnhance.Brightness(frame)
        frame = enhancer.enhance(factor)
        
        draw = ImageDraw.Draw(frame)
        
        # B. Darken bottom for text
        draw.rectangle([(0, 800), (1080, 1080)], fill=(0,0,0, 200))
        
        # C. Draw Headline (White)
        draw.text((50, 850), headline, font=font, fill="white")
        
        # D. Draw "Listen Now" (Cyan Pulse)
        # The text color changes slightly with the loop
        cyan_pulse = (0, 255, 255) if i % 2 == 0 else (200, 255, 255)
        draw.text((50, 950), "▶ LISTEN ON SPOTIFY", font=font, fill=cyan_pulse)
        
        frames.append(frame)

    # 4. Save GIF
    frames[0].save(
        OUTPUT_GIF,
        save_all=True,
        append_images=frames[1:],
        duration=100, # 100ms per frame = fast surge
        loop=0
    )
    print(f" >> [VFX SUCCESS] GIF Saved: {OUTPUT_GIF}")

if __name__ == "__main__":
    create_energy_gif()
