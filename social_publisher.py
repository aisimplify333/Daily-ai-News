import os
import time
import tweepy

# --- CONFIGURATION ---
API_KEY = os.environ.get("TWITTER_API_KEY")
API_SECRET = os.environ.get("TWITTER_API_SECRET")
ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET")

VIDEO_FILE = "social_clip.mp4"
CAPTION_FILE = "viral_caption.txt"

def get_twitter_conn():
    """Connect to both v1.1 (Media) and v2 (Posting) APIs"""
    if not API_KEY:
        print(" !! NO TWITTER KEYS FOUND. Skipping.")
        return None, None
        
    # v1.1 Auth (For Media Uploads)
    auth = tweepy.OAuth1UserHandler(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET)
    api_v1 = tweepy.API(auth)
    
    # v2 Client (For Tweeting)
    client_v2 = tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_SECRET
    )
    return api_v1, client_v2

def post_thread():
    print(" >> 🐦 INITIALIZING BROADCAST ENGINE...")
    api_v1, client_v2 = get_twitter_conn()
    if not api_v1: return

    # 1. LOAD CONTENT
    if not os.path.exists(CAPTION_FILE):
        print(" !! CAPTION FILE MISSING.")
        return
        
    with open(CAPTION_FILE, "r") as f:
        full_text = f.read()
        
    # 2. PARSE THE THREAD
    # We split the caption file. 
    # Part 1: The Hook (Top lines)
    # Part 2: The Link (Bottom lines)
    lines = full_text.split('\n')
    hook_text = "\n".join(lines[:4]) # First 4 lines are the hook
    link_text = "\n".join(lines[4:]) # The rest is the link/tags

    # 3. UPLOAD VIDEO (Chunked Upload for stability)
    media_id = None
    if os.path.exists(VIDEO_FILE):
        print("    Uploading Video Asset...")
        try:
            media = api_v1.media_upload(VIDEO_FILE, chunked=True)
            # Wait for processing
            time.sleep(5) 
            media_id = media.media_id
            print("    Video Uploaded.")
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
        print("    Posting Link Reply...")
        time.sleep(2) # Breath
        client_v2.create_tweet(text=link_text[:280], in_reply_to_tweet_id=tweet_id)
        print("    ✅ TWEET 2 SENT (THREAD COMPLETE).")
        
    except Exception as e:
        print(f" !! BROADCAST FAILED: {e}")

if __name__ == "__main__":
    post_thread()
