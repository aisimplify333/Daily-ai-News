import os
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
META_PATH = BASE_DIR / "episode_metadata.json"
OUTPUT_GIF = BASE_DIR / "social_surge.gif"

def create_energy_gif():
    print("--- STARTING VFX ENGINE ---")
    
    # 1. Load Data
    if not META_PATH.exists(): headline = "DAILY AI NEWS"
    else:
        with open(META_PATH) as f: headline = json.load(f).get("title", "DAILY AI NEWS").upper()

    # 2. Load Image (Robust Finder)
    possible_covers = [
        BASE_DIR / "cover.png", BASE_DIR / "logo.png",
        ASSETS_DIR / "cover.png", ASSETS_DIR / "logo.png"
    ]
    img_path = None
    for p in possible_covers:
        if p.exists():
            img_path = p
            print(f" >> [VFX] Found Cover: {p.name}")
            break
            
    if not img_path: 
        print(" >> [ERROR] No cover.png or logo.png found!")
        return

    base = Image.open(img_path).convert("RGBA").resize((1080, 1080))

    # 3. Setup Text
    try: font = ImageFont.truetype("arial.ttf", 80)
    except: font = ImageFont.load_default()
    
    frames = []
    # Create 10 frames for the loop
    for i in range(10):
        # A. Create the "Surge" Effect (Brightness Pulse)
        factor = 1.0 + (0.3 * abs(i - 5) / 5) 
        
        frame = base.copy()
        enhancer = ImageEnhance.Brightness(frame)
        frame = enhancer.enhance(factor)
        
        draw = ImageDraw.Draw(frame)
        
        # B. Darken bottom for text
        draw.rectangle([(0, 800), (1080, 1080)], fill=(0,0,0, 200))
        
        # C. Draw Headline (White)
        draw.text((50, 850), headline, font=font, fill="white")
        
        # D. Draw "Listen Now" (Cyan Pulse)
        cyan_pulse = (0, 255, 255) if i % 2 == 0 else (200, 255, 255)
        draw.text((50, 950), "▶ LISTEN ON SPOTIFY", font=font, fill=cyan_pulse)
        
        frames.append(frame)

    # 4. Save GIF
    frames[0].save(
        OUTPUT_GIF,
        save_all=True,
        append_images=frames[1:],
        duration=100, # 100ms per frame
        loop=0
    )
    print(f" >> [VFX SUCCESS] GIF Saved: {OUTPUT_GIF}")

if __name__ == "__main__":
    create_energy_gif()
