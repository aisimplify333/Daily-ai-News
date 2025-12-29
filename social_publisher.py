import os
import time
import tweepy
from pathlib import Path

# --- SETUP PATHS (Cloud Safety) ---
BASE_DIR = Path(__file__).parent
VIDEO_PATH = BASE_DIR / "social_clip.mp4"
CAPTION_PATH = BASE_DIR / "viral_caption.txt"

def get_twitter_conn():
    """Connect to both v1.1 (Media) and v2 (Posting) APIs"""
    consumer_key = os.getenv("TWITTER_API_KEY")
    consumer_secret = os.getenv("TWITTER_API_SECRET")
    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_token_secret = os.getenv("TWITTER_ACCESS_SECRET")

    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        print("❌ ERROR: Missing Twitter API Keys in Environment Variables.")
        return None, None
        
    # v1.1 Auth (For Media Uploads)
    auth = tweepy.OAuth1UserHandler(consumer_key, consumer_secret, access_token, access_token_secret)
    api_v1 = tweepy.API(auth)
    
    # v2 Client (For Tweeting)
    client_v2 = tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret
    )
    return api_v1, client_v2

def post_thread():
    print(" >> 🐦 INITIALIZING BROADCAST ENGINE...")
    api_v1, client_v2 = get_twitter_conn()
    if not api_v1: return

    # 1. LOAD CONTENT
    if not CAPTION_PATH.exists():
        print("⚠️ CAPTION FILE MISSING. Using fallback.")
        full_text = "Here is today's AI Update! 🤖\n\nListen to the full episode."
    else:
        with open(CAPTION_PATH, "r", encoding="utf-8") as f:
            full_text = f.read()
        
    # 2. PARSE THE THREAD
    # Split text into Hook (Tweet 1) and Link/Tags (Tweet 2)
    lines = full_text.split('\n')
    
    # Safety: If caption is short, put everything in Tweet 1
    if len(lines) > 4:
        hook_text = "\n".join(lines[:4]) 
        link_text = "\n".join(lines[4:])
    else:
        hook_text = full_text
        link_text = ""

    # 3. UPLOAD VIDEO
    media_id = None
    if VIDEO_PATH.exists():
        print(f"    Uploading Video ({VIDEO_PATH.name})...")
        try:
            # chunked=True AND media_category="tweet_video" are required for MP4s
            media = api_v1.media_upload(
                filename=str(VIDEO_PATH), 
                chunked=True, 
                media_category="tweet_video"
            )
            
            # Simple wait for processing
            print("    ⏳ Twitter processing video...")
            time.sleep(8) 
            
            media_id = media.media_id
            print(f"    ✅ Video Uploaded. Media ID: {media_id}")
        except Exception as e:
            print(f" !! VIDEO UPLOAD FAILED: {e}")
    else:
        print(" !! VIDEO FILE MISSING. Posting Text Only.")

    # 4. POST TWEET 1 (THE HOOK + VIDEO)
    print("    Posting Hook...")
    try:
        if media_id:
            t1 = client_v2.create_tweet(text=hook_text[:280], media_ids=[media_id])
        else:
            t1 = client_v2.create_tweet(text=hook_text[:280])
            
        tweet_id = t1.data['id']
        print(f"    ✅ TWEET 1 SENT (ID: {tweet_id})")
        
        # 5. POST TWEET 2 (THE LINK - REPLY)
        # Only post if there is actually text left
        if link_text.strip():
            print("    Posting Link Reply...")
            time.sleep(2) 
            client_v2.create_tweet(text=link_text[:280], in_reply_to_tweet_id=tweet_id)
            print("    ✅ TWEET 2 SENT (THREAD COMPLETE).")
        else:
            print("    ℹ️ No link text found. Thread complete.")
        
    except Exception as e:
        print(f" !! BROADCAST FAILED: {e}")

if __name__ == "__main__":
    post_thread()
