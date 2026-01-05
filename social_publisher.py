# social_publisher.py
import os
import sys
import traceback
from pathlib import Path
from typing import Optional, Tuple

BASE_DIR = Path(__file__).parent

MAX_TWEET_CHARS = int(os.getenv("X_MAX_TWEET_CHARS", "280"))
DEBUG = os.getenv("X_DEBUG", "false").strip().lower() in ("1", "true", "yes")


def _safe_print(msg: str):
    print(msg, flush=True)


def _debug(msg: str):
    if DEBUG:
        _safe_print(f"   [debug] {msg}")


def _trim_to_limit(text: str, limit: int = 280) -> str:
    """
    Hard trim by character count. (X uses weighted counts for links, but hard-trimming
    prevents accidental overflows in automation.)
    """
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    # Keep a little space for ellipsis
    return (t[: max(0, limit - 1)].rstrip() + "…")[:limit]


def _load_caption_text() -> str:
    caption_path = BASE_DIR / "viral_caption.txt"
    if caption_path.exists():
        t = caption_path.read_text(encoding="utf-8", errors="ignore").strip()
        if t:
            return t
    return "New episode is live."


def _pick_media() -> Tuple[Optional[Path], str]:
    """
    Prefer mp4, fall back to jpg.
    Returns (path, kind) where kind is 'video' | 'image' | 'none'
    """
    mp4 = BASE_DIR / "social_clip.mp4"
    jpg = BASE_DIR / "social_card.jpg"

    if mp4.exists() and mp4.is_file():
        try:
            size = mp4.stat().st_size
            _debug(f"Found social_clip.mp4 size={size} bytes")
            # Basic sanity gate; adjust as you like.
            if size > 100_000:
                return mp4, "video"
        except Exception:
            pass

    if jpg.exists() and jpg.is_file():
        try:
            size = jpg.stat().st_size
            _debug(f"Found social_card.jpg size={size} bytes")
            if size > 20_000:
                return jpg, "image"
        except Exception:
            pass

    return None, "none"


def main() -> int:
    # If you want a hard gate, set REQUIRE_SOCIAL_PUBLISH=true
    require = os.getenv("REQUIRE_SOCIAL_PUBLISH", "false").strip().lower() in ("1", "true", "yes")

    try:
        import tweepy  # noqa: F401
    except Exception as e:
        _safe_print(f"⚠️ social_publisher: tweepy not installed ({e}). Skipping publish.")
        _safe_print("   Fix: add tweepy to requirements.txt and install it in GitHub Actions.")
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

    text_raw = _load_caption_text()
    text = _trim_to_limit(text_raw, MAX_TWEET_CHARS)

    media_path, media_kind = _pick_media()

    # OAuth1 is typically required for media upload (v1.1 upload endpoints).
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api_v1 = tweepy.API(auth, wait_on_rate_limit=True)

    media_id: Optional[str] = None

    # Upload media (optional)
    if media_path and media_kind != "none":
        try:
            if media_kind == "video":
                _safe_print(">> 📡 Uploading video to X (chunked)...")
                # Tweepy routes videos through chunked upload; wait_for_async_finalize can be passed through.
                # (See Tweepy API.media_upload / chunked_upload docs.) :contentReference[oaicite:2]{index=2}
                media = api_v1.media_upload(
                    filename=str(media_path),
                    chunked=True,
                    media_category="tweet_video",
                    wait_for_async_finalize=True,
                )
            else:
                _safe_print(">> 📡 Uploading image to X...")
                media = api_v1.media_upload(
                    filename=str(media_path),
                    chunked=False,
                    media_category="tweet_image",
                )

            media_id = getattr(media, "media_id_string", None) or str(getattr(media, "media_id", "")).strip() or None
            _debug(f"Uploaded media_id={media_id}")

            # Optional: add alt text for images/GIFs (supported for images/GIFs). :contentReference[oaicite:3]{index=3}
            if media_kind == "image" and media_id:
                alt = os.getenv("X_MEDIA_ALT_TEXT", "").strip()
                if alt:
                    try:
                        api_v1.create_media_metadata(media_id=media_id, alt_text=_trim_to_limit(alt, 1000))
                        _debug("Alt text applied.")
                    except Exception as e:
                        _safe_print(f"⚠️ social_publisher: alt text failed ({e}). Continuing.")

        except Exception as e:
            _safe_print(f"⚠️ social_publisher: media upload failed ({e}). Will attempt text-only tweet.")
            if DEBUG:
                _safe_print(traceback.format_exc())
            media_id = None

    # Post tweet (v2)
    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )

        if media_id:
            client.create_tweet(text=text, media_ids=[media_id])
        else:
            client.create_tweet(text=text)

        _safe_print("✅ social_publisher: posted to X")
        return 0

    except Exception as e:
        _safe_print(f"❌ social_publisher: tweet failed ({e})")
        if DEBUG:
            _safe_print(traceback.format_exc())
        return 1 if require else 0


if __name__ == "__main__":
    sys.exit(main())
