import os
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
# FIXED: Using PNG as requested
COVER_IMAGE_PATH = BASE_DIR / "cover.png" 
METADATA_PATH = BASE_DIR / "episode_metadata.json"
OUTPUT_PATH = BASE_DIR / "social_card.jpg"

def create_social_card():
    print("--- STARTING VISUAL ENGINE ---")

    # 1. LOAD DATA
    if not METADATA_PATH.exists():
        print(" >> [ERROR] No metadata found. Run main.py first.")
        return

    with open(METADATA_PATH, "r") as f:
        meta = json.load(f)
        headline = meta.get("title", "Daily AI News").upper()

    # 2. LOAD COVER IMAGE
    try:
        # Check root or assets for cover
        if COVER_IMAGE_PATH.exists():
            img = Image.open(COVER_IMAGE_PATH).convert("RGBA")
        elif (ASSETS_DIR / "cover.png").exists():
             img = Image.open(ASSETS_DIR / "cover.png").convert("RGBA")
        else:
            print(" >> [ERROR] cover.png not found.")
            return

        width, height = img.size

        # 3. DARKEN IMAGE (To make text pop)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 150)) 
        img = Image.alpha_composite(img, overlay)
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)

        # 4. DRAW TEXT 
        try:
            # Try to load a bold font if available, else default
            font = ImageFont.truetype("arial.ttf", size=int(height/10))
        except:
            font = ImageFont.load_default()
        
        # Wrap Text Logic
        lines = []
        words = headline.split()
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            if len(test_line) < 20:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word + " "
        lines.append(current_line)

        # Draw Lines Centered
        y_text = height / 3
        for line in lines:
            draw.text((width/10, y_text), line, font=font, fill="white")
            y_text += height / 8

        # 5. ADD BRANDING
        draw.text((width/20, height - height/10), "THE AI EDGE // DAILY", fill=(0, 255, 255)) 

        # 6. SAVE
        img.save(OUTPUT_PATH)
        print(f" >> [SUCCESS] Social Card Generated: {OUTPUT_PATH}")

    except Exception as e:
        print(f" >> [VISUAL FAIL] {e}")

if __name__ == "__main__":
    create_social_card()
