# social_publisher.py
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

BASE_DIR = Path(__file__).parent

def _safe_print(msg: str):
    print(msg, flush=True)

def _env_truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")

def _clamp_tweet(text: str, max_len: int = 280) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    # avoid cutting in middle of URL by truncating at last whitespace
    cut = t.rfind(" ", 0, max_len - 1)
    if cut < 80:
        cut = max_len - 1
    return (t[:cut].rstrip() + "…").strip()

def _split_blocks(text: str) -> List[str]:
    """
    Splits viral_caption.txt into tweet-sized blocks.
    Your main.py writes it as: tweet1 \n\n tweet2 \n\n hashtags
    """
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return []
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    return blocks

def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    return {}

def _pick_media() -> Optional[Path]:
    mp4 = BASE_DIR / "social_clip.mp4"
    jpg = BASE_DIR / "social_card.jpg"
    if mp4.exists() and mp4.stat().st_size > 100_000:
        return mp4
    if jpg.exists() and jpg.stat().st_size > 20_000:
        return jpg
    return None

def _wait_for_video_processing(api_v1, media_id: int, timeout_s: int = 180):
    start = time.time()
    while True:
        media = api_v1.get_media_upload_status(media_id)
        info = getattr(media, "processing_info", None) or {}
        state = info.get("state")
        if not state:
            return  # images often have no processing_info
        if state == "succeeded":
            return
        if state == "failed":
            raise RuntimeError(f"Video processing failed: {info}")
        check_after = int(info.get("check_after_secs") or 2)
        if time.time() - start > timeout_s:
            raise RuntimeError(f"Timed out waiting for video processing (media_id={media_id})")
        time.sleep(max(2, check_after))

def _upload_media(api_v1, media_path: Path) -> Optional[int]:
    if not media_path:
        return None
    try:
        if media_path.suffix.lower() == ".mp4":
            _safe_print(">> 📡 Uploading video to X (chunked)...")
            media = api_v1.media_upload(
                filename=str(media_path),
                chunked=True,
                media_category="tweet_video",
            )
            media_id = int(media.media_id)
            _wait_for_video_processing(api_v1, media_id)
            return media_id

        _safe_print(">> 📡 Uploading image to X...")
        media = api_v1.media_upload(filename=str(media_path))
        return int(media.media_id)

    except Exception as e:
        _safe_print(f"⚠️ social_publisher: media upload failed ({e}). Will post text-only.")
        return None

def _build_thread_texts(listen_url: str) -> List[str]:
    """
    Priority:
    1) marketing_pack.json -> tweet1/tweet2/hashtags
    2) viral_caption.txt blocks
    Ensures: Tweet 1 has NO listen link, Tweet 2 contains listen link, Tweet 3+ sponsor/resources if present.
    """
    marketing = _load_json(BASE_DIR / "marketing_pack.json")
    platform = _load_json(BASE_DIR / "platform_pack.json")

    # Prefer platform listen_url if present
    listen = (platform.get("listen_url") or listen_url or "").strip()

    # If marketing pack exists, use it
    if marketing:
        t1 = (marketing.get("tweet1") or "").strip()
        t2 = (marketing.get("tweet2") or "").strip()
        tags = (marketing.get("hashtags") or "").strip()

        # Keep tweet1 link-free for reach
        if listen and listen in t1:
            t1 = t1.replace(listen, "").strip()

        thread = []
        if t1:
            thread.append(_clamp_tweet(t1))
        if t2:
            thread.append(_clamp_tweet(t2))
        elif listen:
            thread.append(_clamp_tweet(f"👇 LISTEN & SOURCES:\n{listen}\n\n{tags}".strip()))
        if tags and all(tags not in x for x in thread[-1:]):
            # avoid duplicating if already in tweet2
            pass
        return [t for t in thread if t]

    # Fallback to viral_caption.txt
    caption_path = BASE_DIR / "viral_caption.txt"
    if caption_path.exists():
        blocks = _split_blocks(caption_path.read_text(encoding="utf-8"))
        blocks = [_clamp_tweet(b) for b in blocks if b.strip()]
        # If the listen link isn’t present, add a dedicated listen reply
        if listen and not any(listen in b for b in blocks):
            blocks.insert(1, _clamp_tweet(f"👇 LISTEN & SOURCES:\n{listen}"))
        return blocks[:6]  # keep threads tight

    # Absolute fallback
    if listen:
        return [
            _clamp_tweet("🚨 New episode is live. Sound on."),
            _clamp_tweet(f"👇 LISTEN & SOURCES:\n{listen}"),
        ]
    return [_clamp_tweet("🚨 New episode is live. Sound on.")]

def main() -> int:
    require = _env_truthy("REQUIRE_SOCIAL_PUBLISH", "false")

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

    # Use OAuth1 for media upload
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api_v1 = tweepy.API(auth)

    # Use v2 for tweet creation
    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
        wait_on_rate_limit=True,
    )

    platform = _load_json(BASE_DIR / "platform_pack.json")
    listen_url = (platform.get("listen_url") or os.getenv("LISTEN_URL", "") or "").strip()

    media_path = _pick_media()
    media_id = _upload_media(api_v1, media_path) if media_path else None

    thread_texts = _build_thread_texts(listen_url)
    if not thread_texts:
        _safe_print("⚠️ social_publisher: no content found to post.")
        return 1 if require else 0

    _safe_print(f">> 🧵 Posting X thread ({len(thread_texts)} tweets)...")

    # Tweet 1 with media (if present)
    first = thread_texts[0]
    resp1 = client.create_tweet(text=first, media_ids=[media_id] if media_id else None)
    first_id = resp1.data.get("id") if resp1 and resp1.data else None
    if not first_id:
        _safe_print("❌ social_publisher: failed to create first tweet.")
        return 1 if require else 0

    last_id = first_id

    # Replies (Tweet 2..n)
    for txt in thread_texts[1:]:
        resp = client.create_tweet(text=txt, in_reply_to_tweet_id=last_id)
        last_id = resp.data.get("id") if resp and resp.data else last_id
        time.sleep(1.2)  # light pacing to reduce flakiness

    _safe_print("✅ social_publisher: posted thread to X")

    # Log ids for debugging/analytics
    log = {
        "first_tweet_id": str(first_id),
        "last_tweet_id": str(last_id),
        "media": str(media_path.name) if media_path else "",
        "count": len(thread_texts),
        "timestamp_utc": int(time.time()),
    }
    (BASE_DIR / "x_publish_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")

    return 0

if __name__ == "__main__":
    sys.exit(main())
