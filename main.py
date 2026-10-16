import sys
import os
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from account_manager import get_active_account
from bot_service import (
    analyze_reel,
    download_candidate,
    analyze_video,
    publish_bot_reel,
    format_count
)
from caption_ai import save_caption_cache
from database import record_reel, mark_published, is_reel_processed

def main():
    active_user = get_active_account()
    print("=" * 50)
    print("         INSTAGRAM VIRAL REEL BOT")
    print("=" * 50)
    print(f"[*] Active account: @{active_user}")
    print("=" * 50)

    profile_url = input("\nEnter Instagram profile or Reel URL:\n> ").strip()
    if not profile_url:
        print("[!] No URL provided. Exiting.")
        return

    print("\nSearching and analyzing Reels...")
    try:
        data = analyze_reel(profile_url, limit=5)
    except Exception as e:
        print(f"[!] Analysis error: {e}")
        return

    candidates = data["candidates"]
    top_reel = data["top_candidate"]

    print(f"\nFound {len(candidates)} candidate(s):\n")
    for idx, r in enumerate(candidates, 1):
        processed_tag = " [PROCESSED]" if r.get("is_processed") else ""
        title_snippet = (r["title"][:40] + "...") if len(r["title"]) > 40 else r["title"]
        print(f"[{idx}] Views: {r['views_formatted'] : <7} | Likes: {r['likes_formatted'] : <7} | Title: {title_snippet}{processed_tag}")

    print(f"\nTop Candidate: {top_reel['url']} ({top_reel['likes_formatted']} likes)")

    choice = input("\nDownload this Reel? [Y/N]: ").strip().lower()
    if choice not in ['y', 'yes']:
        print("Cancelled.")
        return

    print("\n[*] Downloading media...")
    try:
        dl_info = download_candidate(top_reel["url"], custom_id=top_reel["id"])
        print(f"[✓] Saved locally to: {dl_info['local_file']} ({dl_info['size_formatted']})")
    except Exception as e:
        print(f"[!] Download failed: {e}")
        return

    video_path = dl_info["new_reel_path"]
    reel_filename = dl_info["filename"]

    # Content-Aware Caption & Hashtag Generation
    print("\n[*] Analyzing video content & generating AI caption + hashtags...")
    analysis = analyze_video(video_path)
    caption_text = analysis["caption"]
    hashtags = analysis["hashtags"]

    print("\n" + "-" * 45)
    print("PROPOSED CAPTION:")
    print("-" * 45)
    print(caption_text)
    print("\nHASHTAGS:")
    print(hashtags)
    print("-" * 45)

    user_caption_choice = input("\nPress ENTER to accept this caption, or type 'edit' to change:\n> ").strip().lower()
    if user_caption_choice == 'edit':
        custom_body = input("\nEnter custom caption text:\n> ").strip()
        custom_tags = input("Enter custom hashtags (or press Enter to keep AI tags):\n> ").strip()
        caption_text = custom_body if custom_body else caption_text
        hashtags = custom_tags if custom_tags else hashtags
        save_caption_cache(reel_filename, caption_text, hashtags, topic="Custom")

    # Record in history
    record_reel(
        reel_id=top_reel["id"],
        original_url=top_reel["url"],
        views=top_reel.get("views") or 0,
        likes=top_reel.get("likes") or 0,
        caption=f"{caption_text}\n\n{hashtags}",
        local_filepath=dl_info["local_file"],
        status="downloaded"
    )

    publish_choice = input(f"\nPost this Reel to your Instagram (@{active_user})? [Y/N]: ").strip().lower()
    if publish_choice in ['y', 'yes']:
        print(f"\n[*] Loading session for @{active_user} & verifying account...")
        try:
            res = publish_bot_reel(
                video_path=video_path,
                caption=caption_text,
                hashtags=hashtags,
                target_account=active_user,
                reel_id=top_reel["id"],
                original_url=top_reel["url"]
            )
            print(f"\n[✓] REEL PUBLISHED SUCCESSFULLY!")
            print(f"    Posted to   : @{res['account']}")
            print(f"    Media PK    : {res['media_pk']}")
            print(f"    Code        : {res['code']}")
            print(f"    Instagram URL: {res['instagram_url']}")
            print(f"[✓] Moved '{reel_filename}' -> reels/posted/")
        except Exception as e:
            print(f"[!] Publishing error: {e}")
    else:
        print("[*] Skipped publishing. Video saved in downloads/ and reels/new/ for later.")

if __name__ == "__main__":
    main()
