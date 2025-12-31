import subprocess
import time
import sys
import os
from pathlib import Path
from pydub import AudioSegment

def run_command(command, description):
    print(f"\n >> 🚀 STARTING: {description}...")
    try:
        # Run the command and wait for it to finish
        result = subprocess.run(command, shell=True, check=True, text=True)
        print(f" >> ✅ COMPLETE: {description}")
    except subprocess.CalledProcessError as e:
        print(f" >> ❌ ERROR in {description}: {e}")
        # Continue despite marketing errors to ensure audio publishes
        if "social" in description.lower() or "generate" in description.lower():
            print("    ⚠️ CONTINUING despite marketing error...")
        else:
            sys.exit(1)

def check_episode_length():
    print("\n >> 📏 CHECKING SHOW RUNNER...")
    audio_dir = Path("episode_audio")
    files = sorted(list(audio_dir.glob("*.mp3")), key=os.path.getmtime, reverse=True)
    
    if not files:
        print("    ⚠️ WARNING: No audio files found.")
        return

    latest_file = files[0]
    try:
        audio = AudioSegment.from_mp3(latest_file)
        duration_min = len(audio) / 1000 / 60
        print(f"    📄 File: {latest_file.name}")
        print(f"    ⏱️  Duration: {duration_min:.2f} minutes")
        
        if duration_min < 22.0:
            print("    ⚠️ WARNING: Episode is UNDER 22 MINUTES.")
        else:
            print("    ✅ GREEN LIGHT: Episode meets 22+ min standard.")
    except: pass

def main():
    print("===================================================")
    print("      🎙️  DAILY AI NEWS: EMPIRE BROADCAST        ")
    print("===================================================")

    # 1. STUDIO (Audio & Script)
    run_command("python main.py", "1. Studio Recording")
    check_episode_length()

    # 2. AGENCY (Visual Assets)
    run_command("python generate_social.py", "2. Generating Visuals")
    run_command("python animate_social.py", "3. Rendering Video Clips")

    # 3. TOWER (Distribution)
    print("\n >> 📡 UPLOADING TO GITHUB...")
    run_command("git add .", "Staging Files")
    run_command('git commit -m "Empire Broadcast: New Episode"', "Committing")
    run_command("git push origin main", "Pushing to Live")

    # 4. BUFFER
    wait_time = 120 
    print(f"\n >> ⏳ BUFFERING {wait_time}s for RSS propogation...")
    time.sleep(wait_time)

    # 5. LAUNCH (Marketing)
    run_command("python social_publisher.py", "5. Firing Marketing Automation")

    print("\n===================================================")
    print("      🎉 EMPIRE BROADCAST COMPLETE. LIVE.         ")
    print("===================================================")

if __name__ == "__main__":
    main()
