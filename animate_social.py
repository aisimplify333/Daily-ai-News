import os
import json
import math
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
OUTPUT_FILE = "social_surge.gif"
META_FILE = "episode_metadata.json"
WIDTH, HEIGHT = 1080, 1080

# --- COLORS ---
BG_COLOR = (10, 10, 15)       # Deep Circuit Blue/Black
CIRCUIT_DIM = (50, 50, 80)    # Unlit Path
CIRCUIT_LIT = (0, 255, 200)   # Cyan Electric Light
TEXT_COLOR = (255, 255, 255)

# --- THE "A" LOGO PATH (Normalized 0.0 to 1.0) ---
# We define the A as points. The Spark will travel strictly along these lines.
# 1. Left Leg up to Top. 2. Top to Right Leg. 3. Crossbar.
A_POINTS = [
    (0.2, 0.8),  # Start: Bottom Left
    (0.5, 0.2),  # Top Point
    (0.8, 0.8),  # End: Bottom Right
    (0.35, 0.5), # Crossbar Start (Teleport for effect)
    (0.65, 0.5)  # Crossbar End
]

def interpolate(p1, p2, t):
    """Linearly interpolate between p1 and p2 by factor t (0.0 to 1.0)"""
    x = p1[0] + (p2[0] - p1[0]) * t
    y = p1[1] + (p2[1] - p1[1]) * t
    return (x, y)

def draw_circuit_a(draw, width, height):
    """Draws the dark, unlit circuit tracks"""
    # Scale points to canvas
    pixels = [(p[0] * width, p[1] * height) for p in A_POINTS]
    
    # Draw Main Legs
    draw.line([pixels[0], pixels[1], pixels[2]], fill=CIRCUIT_DIM, width=15)
    # Draw Crossbar
    draw.line([pixels[3], pixels[4]], fill=CIRCUIT_DIM, width=15)

def draw_electricity(draw, frame_idx, total_frames, width, height):
    """Draws the moving light pulse along the path"""
    # Calculate progress (0.0 to 1.0)
    progress = frame_idx / total_frames
    
    # Scale points
    pixels = [(p[0] * width, p[1] * height) for p in A_POINTS]
    
    # PATH LOGIC: We map progress to the segments
    # 0.0-0.4: Left Leg (P0 -> P1)
    # 0.4-0.8: Right Leg (P1 -> P2)
    # 0.8-1.0: Crossbar (P3 -> P4)
    
    current_pos = None
    
    if progress < 0.4:
        # Segment 1
        t = progress / 0.4
        current_pos = interpolate(pixels[0], pixels[1], t)
    elif progress < 0.8:
        # Segment 2
        t = (progress - 0.4) / 0.4
        current_pos = interpolate(pixels[1], pixels[2], t)
    else:
        # Segment 3 (Crossbar)
        t = (progress - 0.8) / 0.2
        current_pos = interpolate(pixels[3], pixels[4], t)
        
    # Draw the Spark (Bright Ball)
    r = 20 # Spark radius
    x, y = current_pos
    
    # Glow effect (layered circles)
    draw.ellipse([x-r*2, y-r*2, x+r*2, y+r*2], fill=(0, 100, 100)) # Faint glow
    draw.ellipse([x-r, y-r, x+r, y+r], fill=CIRCUIT_LIT) # Hot core

def generate_visuals():
    print(" >> ⚡ GENERATING CIRCUIT ANIMATION...")
    
    # Load Episode Data
    try:
        with open(META_FILE) as f:
            data = json.load(f)
            title = data.get("title", "AI NEWS DAILY")
            hook = data.get("hook", "Listen Now")
    except:
        title = "AI SYSTEM ONLINE"
        hook = "Initializing..."

    # Font Setup
    try:
        font_large = ImageFont.truetype("arial.ttf", 90)
        font_small = ImageFont.truetype("arial.ttf", 50)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    frames = []
    total_frames = 30 # 30 Frames for a smooth flow loop
    
    for i in range(total_frames):
        # 1. Background
        img = Image.new('RGB', (WIDTH, HEIGHT), color=BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # 2. Draw Static Circuit
        draw_circuit_a(draw, WIDTH, HEIGHT)
        
        # 3. Draw Moving Electricity
        draw_electricity(draw, i, total_frames, WIDTH, HEIGHT)
        
        # 4. Text Overlay (Centered)
        # Title Breakdown
        lines = title.split()
        y_text = 200
        for line in lines: # Simple wrap
            draw.text((100, y_text), line.upper(), font=font_large, fill=TEXT_COLOR)
            y_text += 100
            
        # Hook Text at Bottom
        draw.text((100, 900), "LIVE NOW: " + hook[:30] + "...", font=font_small, fill=(200, 200, 200))

        frames.append(img)
        
    # Save GIF
    frames[0].save(
        OUTPUT_FILE,
        save_all=True,
        append_images=frames[1:],
        optimize=False,
        duration=50, # 50ms = Fast electricity
        loop=0
    )
    print(f"DONE: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_visuals()
