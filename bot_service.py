r"""
bot_service.py — Shared Business Logic for Interactive Viral Reel Bot
Used by main.py (CLI: .\commands.ps1 bot) and FastAPI backend server.
"""

import os
import sys
import shutil
import re
from pathlib import Path
from typing import Dict, Any, Optional

from database import init_db, record_reel, mark_published, is_reel_processed
from instagram_source import fetch_recent_reels, extract_username_or_url
from downloader import download_reel, download_all_media
from caption_ai import generate_reel_content, save_caption_cache
from post_reel_direct import ensure_thumbnail
from account_manager import (
    get_instagram_client,
    get_active_account,
    clean_username,
    verify_account_session,
    update_account_status,
    load_accounts_config
)

# Instagram exception classes (imported lazily to avoid import errors if instagrapi not installed)
def _get_ig_exceptions():
    """Import instagrapi exception classes, returning None placeholders if unavailable."""
    try:
        from instagrapi.exceptions import (
            FeedbackRequired,
            ChallengeRequired,
            LoginRequired,
            BadPassword,
            ClipNotUpload,
            ClientError
        )
        return FeedbackRequired, ChallengeRequired, LoginRequired, BadPassword, ClipNotUpload, ClientError
    except ImportError:
        return Exception, Exception, Exception, Exception, Exception, Exception

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEW_REELS_DIR = os.path.join(BASE_DIR, "reels", "new")
POSTED_DIR = os.path.join(BASE_DIR, "reels", "posted")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
HISTORY_FILE = os.path.join(BASE_DIR, "posting_history.json")

NEW_IMAGES_DIR = os.path.join(BASE_DIR, "images", "new")
POSTED_IMAGES_DIR = os.path.join(BASE_DIR, "images", "posted")

for d in [NEW_REELS_DIR, POSTED_DIR, DOWNLOADS_DIR, NEW_IMAGES_DIR, POSTED_IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)


def format_count(count: Optional[int]) -> str:
    """Format numeric counts into readable strings (e.g. 7.5K, 1.2M, N/A)."""
    if not count or count <= 0:
        return "N/A"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def format_size(size_bytes: int) -> str:
    """Format bytes into readable size (B, KB, MB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def get_accounts_posted_for_source(source_id_or_url: str) -> list:
    """
    Returns list of account usernames that have already published this content.
    Allows distinguishing between accounts to prevent duplicate posts to the same account
    while permitting posting to another account.
    """
    posted_accounts = set()
    import sqlite3
    db_file = os.path.join(BASE_DIR, "reels_history.db")
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute(
                "SELECT account FROM processed_reels WHERE (reel_id = ? OR original_url = ?) AND published_status = 'published'",
                (source_id_or_url, source_id_or_url)
            )
            for row in cur.fetchall():
                if row[0]:
                    posted_accounts.add(clean_username(row[0]))
            conn.close()
        except Exception:
            pass

    if os.path.exists(HISTORY_FILE):
        try:
            import json
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            for entry in history:
                if entry.get("status") in ["published", "posted"] and entry.get("account"):
                    src_id = entry.get("source_post_id") or ""
                    src_url = entry.get("source_url") or ""
                    fn = entry.get("filename") or ""
                    if (source_id_or_url and (source_id_or_url == src_id or source_id_or_url in src_url or source_id_or_url in fn)):
                        posted_accounts.add(clean_username(entry.get("account")))
        except Exception:
            pass

    return sorted(list(posted_accounts))


def is_source_already_posted(source_id_or_url: str, account: str) -> bool:
    """
    Checks if this specific source post has already been posted to the given account.
    """
    target = clean_username(account).lower()
    posted_accs = [a.lower() for a in get_accounts_posted_for_source(source_id_or_url)]
    return target in posted_accs


def analyze_reel(url: str, limit: int = 5, account: str = "") -> Dict[str, Any]:
    """
    Search and analyze Instagram profile, Reel URL, or Post URL, returning candidate metadata.
    Detects Carousel vs Single Image vs Reel, extracts original caption and hashtags for Repost As-Is.
    """
    init_db()
    clean_url = extract_username_or_url(url.strip())
    reels = fetch_recent_reels(clean_url, limit=limit)

    if not reels:
        raise ValueError("No candidate content found or URL is inaccessible. Ensure post/profile is public.")

    target_acc = clean_username(account) if account else get_active_account()

    candidates = []
    for r in reels:
        creator = r.get("creator") or ""
        if not creator and "instagram.com/" in clean_url:
            m = re.search(r"instagram\.com/([^/?#]+)", clean_url)
            if m and m.group(1) not in ["reel", "reels", "p", "explore"]:
                creator = m.group(1)
        if not creator:
            creator = "creator"

        posted_accounts = get_accounts_posted_for_source(r["id"])
        is_processed = (target_acc.lower() in [a.lower() for a in posted_accounts]) or is_reel_processed(r["id"], account=target_acc)

        candidates.append({
            "id": r["id"],
            "url": r["url"],
            "title": r.get("title") or "Instagram Content",
            "creator": creator,
            "views": r.get("views") or 0,
            "views_formatted": format_count(r.get("views")),
            "likes": r.get("likes") or 0,
            "likes_formatted": format_count(r.get("likes")),
            "thumbnail": r.get("thumbnail") or "",
            "media_type": r.get("media_type", 2),
            "is_video": r.get("is_video", True),
            "post_type": r.get("post_type", "reel" if r.get("is_video", True) else "image"),
            "item_count": r.get("item_count", 1),
            "items_preview": r.get("items_preview", []),
            "original_caption": r.get("original_caption", ""),
            "original_hashtags": r.get("original_hashtags", ""),
            "original_text": r.get("original_text", ""),
            "audio_status": r.get("audio_status", "No audio detected"),
            "audio_info": r.get("audio_info", {}),
            "posted_accounts": posted_accounts,
            "is_processed": is_processed
        })

    top_candidate = candidates[0]
    return {
        "status": "candidate_found",
        "top_candidate": top_candidate,
        "candidates": candidates
    }


def download_candidate(candidate_url: str, custom_id: str = "", source_candidate: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Downloads ALL original media items for a Reel, Single Image, or Carousel.
    Preserves exact original media (visible watermarks/embedded text) without cropping.
    """
    dl_res = download_all_media(candidate_url, custom_id=custom_id, source_candidate=source_candidate)
    return dl_res


def analyze_video(video_path: str, context_hint: str = "") -> Dict[str, Any]:
    """
    Analyze downloaded media content (video or image) and generate AI caption and hashtags.
    Gracefully catches visual analysis errors without crashing.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Media file not found for analysis: {video_path}")

    filename = os.path.basename(video_path)
    ext = os.path.splitext(filename)[1].lower()
    is_image = ext in ('.jpg', '.jpeg', '.png', '.webp')
    visual_available = True
    ai_meta = None

    try:
        if is_image:
            from caption_ai import generate_image_content
            ai_meta = generate_image_content(video_path, context_hint=context_hint)
        else:
            ai_meta = generate_reel_content(video_path, context_hint=context_hint)
    except Exception as e:
        visual_available = False
        print(f"[!] Warning: Visual analysis unavailable ({e}). Continuing with metadata fallback.")

    if not ai_meta or not isinstance(ai_meta, dict):
        caption = "Words from the heart. ✨"
        hashtags = "#ExploreMore #Trending #Instagram #DailyVibe" if is_image else "#Reels #ExploreMore #ViralReels #Trending #InstagramReels"
        topic = "Content"
        full = f"{caption}\n\n{hashtags}"
    else:
        caption = ai_meta.get("caption", "Words from the heart. ✨")
        hashtags = ai_meta.get("hashtags", "#ExploreMore #Trending")
        topic = ai_meta.get("topic", "Content")
        full = ai_meta.get("full", f"{caption}\n\n{hashtags}")

    return {
        "status": "analyzed",
        "video": filename,
        "media_type": "image" if is_image else "reel",
        "caption": caption,
        "hashtags": hashtags,
        "topic": topic,
        "full": full,
        "visual_available": visual_available
    }


def publish_bot_content(
    media_files: Any,
    caption: str,
    hashtags: str,
    target_account: str,
    post_type: str = "",
    mode: str = "repost_as_is",
    reel_id: str = "",
    original_url: str = "",
    audio_status: str = "",
    force: bool = False,
    video_path: str = ""
) -> Dict[str, Any]:
    """
    Publishes content to Instagram:
    - Carousel: uploads Image 1..N in exact original order as ONE album post.
    - Single Image: photo_upload.
    - Reel/Video: clip_upload with thumbnail.
    Checks duplicate prevention per account to prevent accidental duplicate reposts to the same account.
    """
    # Normalize media_files input
    if isinstance(media_files, str):
        file_list = [media_files]
    elif isinstance(media_files, (list, tuple)):
        file_list = list(media_files)
    elif video_path:
        file_list = [video_path]
    else:
        raise ValueError("No media files specified for publishing.")

    # Validate file existence
    valid_files = []
    for fp in file_list:
        if os.path.exists(fp):
            valid_files.append(os.path.abspath(fp))
        else:
            # Check in images/new or reels/new
            alt1 = os.path.join(NEW_IMAGES_DIR, os.path.basename(fp))
            alt2 = os.path.join(NEW_REELS_DIR, os.path.basename(fp))
            if os.path.exists(alt1):
                valid_files.append(alt1)
            elif os.path.exists(alt2):
                valid_files.append(alt2)
            else:
                raise FileNotFoundError(f"Media file not found: {fp}")

    target = clean_username(target_account)

    # 1. Pre-flight check: Verify publishing enabled on target account
    accounts_cfg = load_accounts_config()
    target_cfg = accounts_cfg.get("accounts", {}).get(target.lower(), {})
    if target_cfg and target_cfg.get("publishing_enabled") is False:
        raise PermissionError(
            f"PUBLISHING DISABLED: Publishing is paused for @{target}. "
            f"Enable it in Settings → Instagram Accounts to publish."
        )

    # 2. Pre-flight check: Verify live Instagram session authentication
    auth_check = verify_account_session(target)
    if not auth_check.get("valid"):
        status = auth_check.get("status")
        msg = auth_check.get("message", "Session invalid")
        update_account_status(target, status)
        if status == "session_expired" or "login_required" in msg.lower():
            raise PermissionError(
                f"AUTHENTICATION_REQUIRED: Instagram session for @{target} has expired (HTTP 403: login_required). "
                f"Please re-authenticate your account in Settings → Instagram Accounts."
            )
        elif status == "publishing_restricted":
            raise PermissionError(
                f"⚠️ PUBLISHING RESTRICTED: Instagram has temporarily restricted posting activity for @{target}. Details: {msg}"
            )
        elif status == "challenge_required":
            raise PermissionError(
                f"⚠️ CHALLENGE REQUIRED: Instagram checkpoint required for @{target}. Please open Instagram app or web to resolve."
            )
        elif status == "session_mismatch":
            raise PermissionError(
                f"ACCOUNT MISMATCH: Selected account (@{target}) does not match authenticated session ({msg})."
            )
        else:
            raise PermissionError(
                f"AUTHENTICATION_REQUIRED: Account @{target} is not authenticated ({msg}). Please connect or log in."
            )

    cl = get_instagram_client(target, verify=True)
    if not cl:
        raise PermissionError(
            f"AUTHENTICATION_REQUIRED: Could not establish authenticated Instagram client for @{target}. Please re-authenticate."
        )

    # Duplicate repost check
    if not force and reel_id:
        if is_source_already_posted(reel_id, target):
            raise ValueError(
                f"Content '{reel_id}' was already published to @{target}. Choose another authorized account or confirm repost."
            )

    # Determine post type
    if not post_type:
        if len(valid_files) > 1:
            post_type = "carousel"
        else:
            ext = os.path.splitext(valid_files[0])[1].lower()
            post_type = "image" if ext in ('.jpg', '.jpeg', '.png', '.webp') else "reel"

    cap_clean = (caption or "").strip()
    hash_clean = (hashtags or "").strip()
    if cap_clean and hash_clean:
        full_caption = f"{cap_clean}\n\n{hash_clean}"
    elif cap_clean:
        full_caption = cap_clean
    else:
        full_caption = hash_clean

    print(f"[*] Publishing {post_type.upper()} ({len(valid_files)} items) to @{target} in '{mode}' mode...")

    FeedbackRequired, ChallengeRequired, LoginRequired, BadPassword, ClipNotUpload, ClientError = _get_ig_exceptions()

    # Upload according to post type — with per-exception handling
    try:
        if post_type == "carousel":
            paths = [Path(p) for p in valid_files]
            media = cl.album_upload(paths=paths, caption=full_caption)
            ig_url = f"https://www.instagram.com/p/{media.code}/"
            dest_dir = POSTED_IMAGES_DIR
            primary_name = os.path.basename(valid_files[0])

        elif post_type == "image":
            media = cl.photo_upload(path=Path(valid_files[0]), caption=full_caption)
            ig_url = f"https://www.instagram.com/p/{media.code}/"
            dest_dir = POSTED_IMAGES_DIR
            primary_name = os.path.basename(valid_files[0])

        else:  # Reel / Video
            primary_file = valid_files[0]
            thumb_path = ensure_thumbnail(primary_file)
            upload_kwargs = {
                "path": Path(primary_file),
                "caption": full_caption
            }
            if thumb_path and os.path.exists(thumb_path):
                upload_kwargs["thumbnail"] = Path(thumb_path)
            media = cl.clip_upload(**upload_kwargs)
            ig_url = f"https://www.instagram.com/reel/{media.code}/"
            dest_dir = POSTED_DIR
            primary_name = os.path.basename(primary_file)

    except FeedbackRequired as e:
        err_str = str(e)
        if "restrict" in err_str.lower() or "feedback_required" in err_str.lower():
            update_account_status(target, "publishing_restricted")
            raise PermissionError(
                f"⚠️ PUBLISHING RESTRICTED: Instagram has temporarily restricted posting activity for @{target}. "
                f"This is an Instagram-side restriction — wait 24–48 hours and try again. Details: {err_str}"
            )
        raise PermissionError(
            f"⚠️ Instagram blocked this action for @{target}: {err_str}. "
            f"This may be a rate-limit or action block. Try again later."
        )
    except ChallengeRequired as e:
        update_account_status(target, "challenge_required")
        raise PermissionError(
            f"⚠️ Instagram security challenge required for @{target}. "
            f"Open the Instagram app or website to confirm your identity, then try again. Details: {e}"
        )
    except (LoginRequired, BadPassword) as e:
        update_account_status(target, "session_expired")
        raise PermissionError(
            f"AUTHENTICATION_REQUIRED: Instagram session has expired for @{target} (HTTP 403: login_required). "
            f"Please re-authenticate via Settings → Instagram Accounts → Reconnect. Details: {e}"
        )
    except ClipNotUpload as e:
        err_str = str(e)
        if "login_required" in err_str.lower() or "403" in err_str:
            update_account_status(target, "session_expired")
            raise PermissionError(
                f"AUTHENTICATION_REQUIRED: Clip upload failed for @{target} because Instagram session has expired (HTTP 403: login_required). "
                f"Please re-authenticate your account in Settings → Instagram Accounts."
            )
        if "restrict" in err_str.lower() or "feedback_required" in err_str.lower():
            update_account_status(target, "publishing_restricted")
            raise PermissionError(
                f"⚠️ PUBLISHING RESTRICTED: Instagram restricted clip upload for @{target}: {err_str}"
            )
        raise RuntimeError(f"Clip upload failed during publishing: {err_str}")
    except ClientError as e:
        err_str = str(e)
        if "login_required" in err_str.lower() or "403" in err_str:
            update_account_status(target, "session_expired")
            raise PermissionError(
                f"AUTHENTICATION_REQUIRED: Instagram session has expired for @{target} (HTTP 403: login_required). "
                f"Please re-authenticate via Settings → Instagram Accounts → Reconnect."
            )
        raise

    # Copy files to posted archive directory
    for vf in valid_files:
        try:
            shutil.copy2(vf, os.path.join(dest_dir, os.path.basename(vf)))
        except Exception:
            pass

    # Record in SQLite database
    if reel_id:
        record_reel(
            reel_id=reel_id,
            original_url=original_url or ig_url,
            views=0,
            likes=0,
            caption=full_caption,
            local_filepath=valid_files[0],
            status="published",
            account=target
        )
        mark_published(reel_id, account=target)

    # Record in JSON posting history with full metadata
    import json
    from datetime import datetime
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    history.insert(0, {
        "source_url": original_url or ig_url,
        "source_post_id": reel_id,
        "media_files": [os.path.basename(p) for p in valid_files],
        "filename": primary_name,
        "type": post_type,
        "item_count": len(valid_files),
        "account": target,
        "mode": mode,
        "posted_at": datetime.now().isoformat(),
        "instagram_url": ig_url,
        "caption": full_caption[:300],
        "hashtags": hash_clean[:200],
        "audio_status": audio_status or ("Detected" if post_type == "reel" else "No audio detected"),
        "media_pk": str(media.pk),
        "status": "published",
    })

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    return {
        "status": "published",
        "account": target,
        "instagram_url": ig_url,
        "code": media.code,
        "media_pk": str(media.pk),
        "media_type": post_type,
        "post_type": post_type,
        "item_count": len(valid_files),
        "filename": primary_name,
        "media_files": [os.path.basename(p) for p in valid_files],
        "mode": mode
    }


# Backwards compatibility alias
publish_bot_reel = publish_bot_content

