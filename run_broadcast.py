import subprocess
import time
import sys

def run_command(command, description):
    print(f"\n >> 🚀 STARTING: {description}...")
    try:
        # Run the command and wait for it to finish
        result = subprocess.run(command, shell=True, check=True, text=True)
        print(f" >> ✅ COMPLETE: {description}")
    except subprocess.CalledProcessError as e:
        print(f" >> ❌ ERROR in {description}: {e}")
        sys.exit(1) # Stop the entire process if one step fails

def main():
    print("===================================================")
    print("      🎙️  DAILY AI NEWS: BROADCAST SEQUENCE      ")
    print("===================================================")

    # STEP 1: BUILD THE SHOW (Run main.py)
    run_command("python main.py", "Building Episode & XML (War Room)")

    # STEP 2: UPLOAD TO GITHUB (The Broadcast Tower)
    print("\n >> 📡 UPLOADING TO BROADCAST TOWER (GITHUB)...")
    run_command("git add .", "Staging Files")
    run_command('git commit -m "Automated Broadcast Upload"', "Committing Files")
    run_command("git push origin main", "Pushing to Live Server")

    # STEP 3: THE BUFFER (Wait for GitHub/Spotify to catch up)
    # We wait 2 minutes to let GitHub Pages refresh the file so the link works
    wait_time = 120 
    print(f"\n >> ⏳ BUFFERING: Waiting {wait_time} seconds for links to go live...")
    for remaining in range(wait_time, 0, -1):
        sys.stdout.write(f"\r    {remaining} seconds remaining...")
        sys.stdout.flush()
        time.sleep(1)
    print("\n >> ✅ LINKS ARE LIVE.")

    # STEP 4: MARKETING AUTOMATION (Run social_publisher.py)
    run_command("python social_publisher.py", "Firing Marketing Automation")

    print("\n===================================================")
    print("      🎉 BROADCAST COMPLETE. SHOW IS LIVE.       ")
    print("===================================================")

if __name__ == "__main__":
    main()
