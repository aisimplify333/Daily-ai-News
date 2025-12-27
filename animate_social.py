import os
import json
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageChops

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
META_PATH = BASE_DIR / "episode_metadata.json"
OUTPUT_GIF = BASE_DIR / "social_surge.gif"

def create_energy_gif():
    print("--- STARTING VFX ENGINE (HIGH VOLTAGE MODE) ---")
    
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
            break
            
    if not img_path: 
        print(" >> [ERROR] No cover.png or logo.png found!")
        return

    base = Image.open(img_path).convert("RGBA").resize((1080, 1080))

    # 3. Setup Text
    try: font = ImageFont.truetype("arial.ttf", 80)
    except: font = ImageFont.load_default()
    
    frames = []
    # Create 10 frames for the loop (Fast, twitchy loop)
    for i in range(10):
        frame = base.copy()
        
        # A. ELECTRIC JITTER EFFECT
        # We split channels and offset them slightly to create "chromatic aberration" (glitch look)
        if i % 2 == 0: # Twitch every other frame
            r, g, b, a = frame.split()
            # Jitter the Red channel
            r = ImageChops.offset(r, random.randint(-5, 5), 0)
            # Jitter the Blue channel
            b = ImageChops.offset(b, random.randint(-5, 5), 0)
            frame = Image.merge("RGBA", (r, g, b, a))
            
            # Brightness Spike (The Spark)
            enhancer = ImageEnhance.Brightness(frame)
            frame = enhancer.enhance(1.4) # Flash bright
        
        draw = ImageDraw.Draw(frame)
        
        # B. Darken bottom for text
        draw.rectangle([(0, 800), (1080, 1080)], fill=(0,0,0, 220))
        
        # C. Draw Headline (White with slight shake)
        text_x = 50 + random.randint(-2, 2)
        draw.text((text_x, 850), headline, font=font, fill="white")
        
        # D. Draw "Listen Now" (Electric Cyan)
        # Randomly switch colors to look like a flickering neon sign
        cyan_electric = (0, 255, 255) if random.random() > 0.3 else (255, 255, 255)
        draw.text((50, 950), "▶ LISTEN ON SPOTIFY", font=font, fill=cyan_electric)
        
        # E. Draw "Sparks" (Random lines)
        if i % 3 == 0:
            # Draw a random jagged line near the 'A' (approx center)
            x1 = random.randint(400, 600)
            y1 = random.randint(300, 500)
            x2 = x1 + random.randint(-50, 50)
            y2 = y1 + random.randint(-50, 50)
            draw.line([(x1, y1), (x2, y2)], fill=(0, 255, 255), width=3)

        frames.append(frame)

    # 4. Save GIF
    frames[0].save(
        OUTPUT_GIF,
        save_all=True,
        append_images=frames[1:],
        duration=80, # 80ms = Fast, twitchy speed
        loop=0
    )
    print(f" >> [VFX SUCCESS] Electric GIF Saved: {OUTPUT_GIF}")

if __name__ == "__main__":
    create_energy_gif()
