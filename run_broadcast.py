import subprocess
import time
import sys
import os
from pathlib import Path
from pydub import AudioSegment

MIN_MINUTES = float(os.getenv("MIN_MINUTES", os.getenv("MIN_EPISODE_MINUTES", "22")))

BRANCH = os.getenv("GIT_BRANCH", "main")

def run_command(command, description, allow_fail=False):
    print(f"\n >> 🚀 STARTING: {description}...")
    try:
        subprocess.run(command, shell=True, check=True, text=True)
        print(f" >> ✅ COMPLETE: {description}")
        return True
    except subprocess.CalledProcessError as e:
        print(f" >> ❌ ERROR in {description}: {e}")
        if allow_fail:
            print("    ⚠️ CONTINUING despite error...")
            return False
        sys.exit(1)

def configure_git_identity():
    """
    GitHub Actions runners do not have an author identity by default.
    This prevents: 'fatal: empty ident name ... not allowed'
    """
    run_command('git config user.name "github-actions[bot]"', "Configuring git user.name", allow_fail=False)
    run_command('git config user.email "41898282+github-actions[bot]@users.noreply.github.com"', "Configuring git user.email", allow_fail=False)

def get_latest_mp3(audio_dir="episode_audio"):
    audio_dir = Path(audio_dir)
    files = sorted(list(audio_dir.glob("*.mp3")), key=os.path.getmtime, reverse=True)
    return files[0] if files else None

def get_mp3_duration_minutes(mp3_path: Path) -> float:
    audio = AudioSegment.from_mp3(mp3_path)
    return len(audio) / 1000.0 / 60.0

def check_episode_length_or_fail():
    print("\n >> 📏 CHECKING SHOW RUNNER...")
    latest = get_latest_mp3()
    if not latest:
        raise RuntimeError("No audio files found in episode_audio/.")

    duration_min = get_mp3_duration_minutes(latest)
    print(f"    📄 File: {latest.name}")
    print(f"    ⏱️  Duration: {duration_min:.2f} minutes")

    if duration_min < MIN_MINUTES:
        raise RuntimeError(f"Episode is too short ({duration_min:.2f} min < {MIN_MINUTES:.0f} min). Refusing to publish.")
    print(f"    ✅ GREEN LIGHT: Episode meets {MIN_MINUTES:.0f}+ min standard.")
    return latest, duration_min

def has_git_changes():
    # returns exit code 0 if changes exist, 1 if clean
    result = subprocess.run("git diff --cached --quiet", shell=True)
    return result.returncode != 0

def main():
    print("===================================================")
    print("      🎙️  DAILY AI NEWS: EMPIRE BROADCAST        ")
    print("===================================================")

    # 0) Configure git identity BEFORE any commits
    configure_git_identity()

    # 1) STUDIO (Audio & Script)
    run_command("python main.py", "1. Studio Recording", allow_fail=False)

    # Enforce quality gate: do not publish short episodes
    try:
        check_episode_length_or_fail()
    except Exception as e:
        print(f" >> ❌ QUALITY GATE FAILED: {e}")
        sys.exit(1)

    # 2) AGENCY (Visual Assets) - allow fail (marketing should not block audio publishing)
    run_command("python generate_social.py", "2. Generating Visuals (Card)", allow_fail=True)

    # NEW: Hook clip (8–15s). Uses episode_metadata.json + marketing_pack.json
    run_command("python animate_hook.py", "2b. Rendering Hook Clip (social_hook.mp4)", allow_fail=True)

    # Existing stylized clip
    run_command("python animate_social.py", "3. Rendering Video Clips (social_clip.mp4)", allow_fail=True)

    # 3) TOWER (Distribution)
    print("\n >> 📡 UPLOADING TO GITHUB...")
    run_command("git add .", "Staging Files", allow_fail=False)

    # If nothing changed, skip commit/push
    if not has_git_changes():
        print(" >> ℹ️  No changes staged. Skipping commit and push.")
    else:
        run_command('git commit -m "Empire Broadcast: New Episode"', "Committing", allow_fail=False)
        run_command(f"git push origin {BRANCH}", "Pushing to Live", allow_fail=False)

    # 4) BUFFER
    wait_time = int(os.getenv("RSS_BUFFER_SECONDS", "120"))
    print(f"\n >> ⏳ BUFFERING {wait_time}s for RSS propagation...")
    time.sleep(wait_time)

    # 5) LAUNCH (Marketing) - allow fail
    run_command("python social_publisher.py", "5. Firing Marketing Automation", allow_fail=True)

    print("\n===================================================")
    print("      🎉 EMPIRE BROADCAST COMPLETE. LIVE.         ")
    print("===================================================")

if __name__ == "__main__":
    main()
