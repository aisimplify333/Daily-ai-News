import os
import sys
import json
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).parent

def _safe_print(msg: str):
    print(msg, flush=True)

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _load_sponsors(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict) and isinstance(data.get("sponsors"), list):
            return [x for x in data["sponsors"] if isinstance(x, dict)]
    except Exception:
        pass
    return []

def _clamp(text: str, max_len: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return (t[: max_len - 1].rstrip() + "…").strip()

def _pick_today_sponsor(sponsors: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not sponsors:
        return None
    # deterministic rotation by day-of-year
    day = int(datetime.datetime.utcnow().strftime("%j"))
    return sponsors[day % len(sponsors)]

def _build_sponsor_tweet(s: Dict[str, Any]) -> str:
    name = (s.get("name") or "Sponsor").strip()
    tagline = (s.get("tagline") or "").strip()
    cta = (s.get("cta") or "").strip()
    url = (s.get("url") or s.get("link") or "").strip()

    parts = [f"SPONSOR: {name}"]
    if tagline:
        parts.append(tagline)
    if cta:
        parts.append(cta)
    if url:
        parts.append(url)

    return _clamp("\n".join(parts), 280)

def _get_x_creds() -> Tuple[str, str, str, str]:
    api_key = os.getenv("X_API_KEY", "").strip()
    api_secret = os.getenv("X_API_SECRET", "").strip()
    access_token = os.getenv("X_ACCESS_TOKEN", "").strip()
    access_secret = os.getenv("X_ACCESS_SECRET", "").strip()
    return api_key, api_secret, access_token, access_secret

def _pick_media() -> Optional[Path]:
    # Tweet 1: hook clip first; then fallback
    for p in [BASE_DIR / "social_hook.mp4", BASE_DIR / "social_clip.mp4", BASE_DIR / "social_card.jpg"]:
        if p.exists():
            try:
                if p.suffix.lower() == ".mp4" and p.stat().st_size > 100_000:
                    return p
                if p.suffix.lower() == ".jpg" and p.stat().st_size > 20_000:
                    return p
            except Exception:
                continue
    return None

def main():
    # Hard gate if set
    require = os.getenv("REQUIRE_SOCIAL_PUBLISH", "false").strip().lower() in ("1", "true", "yes")

    try:
        import tweepy  # noqa
    except Exception as e:
        _safe_print(f"⚠️ social_publisher: tweepy not installed ({e}). Skipping publish.")
        _safe_print("   Fix: add tweepy to requirements.txt and install it in GitHub Actions.")
        return 1 if require else 0

    api_key, api_secret, access_token, access_secret = _get_x_creds()
    if not all([api_key, api_secret, access_token, access_secret]):
        _safe_print("⚠️ social_publisher: X credentials missing. Skipping publish.")
        _safe_print("   Expected env vars: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET")
        return 1 if require else 0

    import tweepy

    # Inputs produced by your pipeline
    marketing_pack = _load_json(BASE_DIR / "marketing_pack.json")
    episode_meta = _load_json(BASE_DIR / "episode_metadata.json")
    sponsors = _load_sponsors(BASE_DIR / "sponsors.json")

    hashtags = (marketing_pack.get("hashtags") or "").strip()
    listen_url = (episode_meta.get("listen_url") or os.getenv("LISTEN_URL", "")).strip()

    # Tweet 1: media + hook. NO LINK.
    tweet1 = (marketing_pack.get("tweet1") or marketing_pack.get("hook") or "NEW EPISODE LIVE").strip()
    tweet1 = tweet1.replace(listen_url, "").strip() if listen_url else tweet1
    tweet1 = _clamp(tweet1, 275)

    # Tweet 2: listen link + hashtags (CTR measured here)
    if marketing_pack.get("tweet2"):
        tweet2 = str(marketing_pack.get("tweet2")).strip()
    else:
        tweet2 = f"Listen now: {listen_url}".strip()

    # Ensure listen link is present in tweet 2
    if listen_url and listen_url not in tweet2:
        tweet2 = f"{tweet2}\n{listen_url}".strip()

    if hashtags and hashtags not in tweet2:
        tweet2 = f"{tweet2}\n\n{hashtags}".strip()

    tweet2 = _clamp(tweet2, 280)

    # Tweet 3: sponsor CTA (clean sponsor preview + measurable CTR)
    sponsor = _pick_today_sponsor(sponsors)
    tweet3 = _build_sponsor_tweet(sponsor) if sponsor else _clamp("SPONSOR SLOT AVAILABLE — reply or DM to book.", 280)

    media_path = _pick_media()

    # OAuth1 for media upload
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api_v1 = tweepy.API(auth)

    media_id = None
    if media_path:
        try:
            if media_path.suffix.lower() == ".mp4":
                _safe_print(f">> 📡 Uploading video to X: {media_path.name}")
                media = api_v1.media_upload(
                    filename=str(media_path),
                    chunked=True,
                    media_category="tweet_video",
                )
            else:
                _safe_print(f">> 📡 Uploading image to X: {media_path.name}")
                media = api_v1.media_upload(filename=str(media_path))

            media_id = getattr(media, "media_id", None)
        except Exception as e:
            _safe_print(f"⚠️ social_publisher: media upload failed ({e}). Will attempt text-only.")
            media_id = None

    # Post thread via v2
    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )

        _safe_print(">> 🧵 Posting X thread (1: hook media, 2: listen, 3: sponsor)...")

        # Tweet 1
        if media_id is not None:
            r1 = client.create_tweet(text=tweet1, media_ids=[media_id])
        else:
            r1 = client.create_tweet(text=tweet1)
        t1_id = r1.data.get("id")

        # Tweet 2 (reply)
        r2 = client.create_tweet(text=tweet2, in_reply_to_tweet_id=t1_id)
        t2_id = r2.data.get("id")

        # Tweet 3 (reply)
        client.create_tweet(text=tweet3, in_reply_to_tweet_id=t2_id)

        _safe_print("✅ social_publisher: posted X thread")
        return 0

    except Exception as e:
        _safe_print(f"❌ social_publisher: thread failed ({e})")
        return 1 if require else 0

if __name__ == "__main__":
    sys.exit(main())
