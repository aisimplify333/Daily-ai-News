# social_publisher.py
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

def _safe_print(msg: str):
    print(msg, flush=True)

def main():
    # If you want a hard gate, set REQUIRE_SOCIAL_PUBLISH=true
    require = os.getenv("REQUIRE_SOCIAL_PUBLISH", "false").strip().lower() in ("1", "true", "yes")

    try:
        import tweepy  # noqa: F401
    except Exception as e:
        _safe_print(f"⚠️ social_publisher: tweepy not installed ({e}). Skipping publish.")
        _safe_print("   Fix: add tweepy to requirements and install it in GitHub Actions.")
        return 1 if require else 0

    api_key = os.getenv("X_API_KEY", "").strip()
    api_secret = os.getenv("X_API_SECRET", "").strip()
    access_token = os.getenv("X_ACCESS_TOKEN", "").strip()
    access_secret = os.getenv("X_ACCESS_SECRET", "").strip()

    if not all([api_key, api_secret, access_token, access_secret]):
        _safe_print("⚠️ social_publisher: X credentials missing. Skipping publish.")
        _safe_print("   Expected env vars: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET")
        return 1 if require else 0

    import tweepy

    # Read caption text if present
    caption_path = BASE_DIR / "viral_caption.txt"
    text = caption_path.read_text(encoding="utf-8").strip() if caption_path.exists() else "New episode is live."

    # Optional media: prefer mp4 then jpg
    mp4 = BASE_DIR / "social_clip.mp4"
    jpg = BASE_DIR / "social_card.jpg"

    # OAuth1 is required for media upload in most setups
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api_v1 = tweepy.API(auth)

    media_id = None
    try:
        if mp4.exists() and mp4.stat().st_size > 100_000:
            _safe_print(">> 📡 Uploading video to X...")
            media = api_v1.media_upload(filename=str(mp4))
            media_id = media.media_id
        elif jpg.exists() and jpg.stat().st_size > 20_000:
            _safe_print(">> 📡 Uploading image to X...")
            media = api_v1.media_upload(filename=str(jpg))
            media_id = media.media_id
    except Exception as e:
        _safe_print(f"⚠️ social_publisher: media upload failed ({e}). Will attempt text-only tweet.")
        media_id = None

    # Post tweet
    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        if media_id is not None:
            client.create_tweet(text=text, media_ids=[media_id])
        else:
            client.create_tweet(text=text)
        _safe_print("✅ social_publisher: posted to X")
        return 0
    except Exception as e:
        _safe_print(f"❌ social_publisher: tweet failed ({e})")
        return 1 if require else 0

if __name__ == "__main__":
    sys.exit(main())
