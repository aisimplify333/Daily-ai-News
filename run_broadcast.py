import subprocess
import time
import sys
import os
from pathlib import Path
from pydub import AudioSegment

def run_command(command, description):
    print(f"\n >> 🚀 STARTING: {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, text=True)
        print(f" >> ✅ COMPLETE: {description}")
    except subprocess.CalledProcessError as e:
        print(f" >> ❌ ERROR in {description}: {e}")
        sys.exit(1)

def get_latest_episode_length():
    # Find the newest MP3 in the folder
    audio_dir = Path("episode_audio")
    files = sorted(list(audio_dir.glob("*.mp3")), key=os.path.getmtime, reverse=True)
    
    if not files: return 0, "No File"
    
    latest_file = files[0]
    audio = AudioSegment.from_mp3(latest_file)
    duration_min = len(audio) / 1000 / 60
    return duration_min, latest_file.name

def main():
    print("===================================================")
    print("      🎙️  DAILY AI NEWS: BROADCAST SEQUENCE      ")
    print("===================================================")

    # STEP 1: BUILD THE SHOW
    run_command("python main.py", "Building Episode & XML (War Room)")

    # STEP 1.5: QUALITY CONTROL (LENGTH CHECK)
    print("\n >> 📏 CHECKING SHOW RUNNER...")
    duration, name = get_latest_episode_length()
    print(f"    Target: 22.0 minutes")
    print(f"    Actual: {duration:.2f} minutes ({name})")
    
    if duration < 15:
        print("    ⚠️ WARNING: Episode is short. Review content before marketing.")
    else:
        print("    ✅ GREEN LIGHT: Length is broadcast standard.")

    # STEP 2: UPLOAD TO GITHUB
    print("\n >> 📡 UPLOADING TO BROADCAST TOWER (GITHUB)...")
    run_command("git add .", "Staging Files")
    run_command('git commit -m "Automated Broadcast Upload"', "Committing Files")
    run_command("git push origin main", "Pushing to Live Server")

    # STEP 3: THE BUFFER
    wait_time = 120 
    print(f"\n >> ⏳ BUFFERING: Waiting {wait_time} seconds for links to go live...")
    for remaining in range(wait_time, 0, -1):
        sys.stdout.write(f"\r    {remaining} seconds remaining...")
        sys.stdout.flush()
        time.sleep(1)
    print("\n >> ✅ LINKS ARE LIVE.")

    # STEP 4: MARKETING AUTOMATION
    run_command("python social_publisher.py", "Firing Marketing Automation")

    print("\n===================================================")
    print("      🎉 BROADCAST COMPLETE. SHOW IS LIVE.       ")
    print("===================================================")

if __name__ == "__main__":
    main()
