import os
import sys
import time
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from account_manager import (
    get_instagram_client,
    get_active_account,
    set_active_account,
    list_accounts
)
from post_image import (
    get_available_images,
    POSTED_IMAGES_DIR,
    LEGACY_POSTED_DIR,
    DEFAULT_IMAGE_HASHTAGS
)
from post_reel_direct import (
    get_pending_reels,
    upload_single_reel,
    NEW_REELS_DIR
)
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def auto_post_all(account: str = None, mode: str = "all", delay_seconds: int = 5):
    """
    Automatically posts all pending images in images/new/ and reels in reels/new/
    to the active or designated Instagram account.
    """
    if account:
        set_active_account(account)

    active_user = get_active_account()

    print("=" * 65)
    print(f"       INSTAGRAM AUTOMATIC BATCH POSTER (@{active_user})")
    print(f"       Mode: {mode}")
    print("=" * 65)

    # 1. Fetch pending items
    images = get_available_images() if mode in ("all", "images") else []
    reels = get_pending_reels() if mode in ("all", "reels") else []

    total_items = len(images) + len(reels)
    print(f"[*] Queue Status:")
    print(f"    - Target Account : @{active_user}")
    print(f"    - Post Mode      : {mode}")
    print(f"    - Pending Images : {len(images)}")
    print(f"    - Pending Reels  : {len(reels)}")
    print(f"    - Safe Delay     : {delay_seconds}s between posts")
    print("-" * 65)

    if total_items == 0:
        print("[!] No pending content found to post.")
        print(f"    Drop photos into:  images/new/")
        print(f"    Drop videos into:  reels/new/")
        print("\nThen run this command again.")
        return

    # 2. Authenticate
    cl = get_instagram_client(active_user)
    if not cl:
        print(f"[!] Authentication failed for @{active_user}. Aborting auto-post.")
        return

    posted_count = 0
    failed_count = 0

    # 3. Post Images First
    if images:
        print(f"\n>>> PROCESSING {len(images)} IMAGE(S)...")
        for idx, img_path in enumerate(images, 1):
            fname = os.path.basename(img_path)
            
            # Check duplicate per account
            history_file = os.path.join(BASE_DIR, "posting_history.json")
            already_posted = False
            if os.path.exists(history_file):
                try:
                    import json
                    with open(history_file, "r", encoding="utf-8") as f:
                        hist = json.load(f)
                        posts = hist.get("posts", hist) if isinstance(hist, dict) else hist
                        for p in posts:
                            if (p.get("filename") == fname or p.get("media_id") == fname) and p.get("account") == active_user and p.get("status") in ["posted", "published"]:
                                already_posted = True
                                break
                except Exception:
                    pass

            if already_posted:
                print(f"\n[{idx}/{len(images)}] [-] Skipping image {fname}: Already posted to @{active_user}")
                continue

            print(f"\n[{idx}/{len(images)}] Posting image: {fname} to @{active_user}")
            
            caption_text = "Words from the heart. ✨"
            full_caption = f"{caption_text}\n\n{DEFAULT_IMAGE_HASHTAGS}"
            
            try:
                media = cl.photo_upload(
                    path=Path(img_path),
                    caption=full_caption
                )
                post_url = f"https://www.instagram.com/p/{media.code}/"
                print(f"[OK] Photo uploaded: {post_url}")
                
                # Archive copy to images/posted/ for backup, but keep original in images/new/
                dest = os.path.join(POSTED_IMAGES_DIR, fname)
                if not os.path.exists(dest):
                    try:
                        shutil.copy2(img_path, dest)
                    except Exception:
                        pass
                
                # Record in posting_history.json
                try:
                    import json
                    from datetime import datetime
                    hist_list = []
                    if os.path.exists(history_file):
                        with open(history_file, "r", encoding="utf-8") as f:
                            raw = json.load(f)
                            hist_list = raw.get("posts", raw) if isinstance(raw, dict) else raw
                    
                    entry = {
                        "media_id": fname,
                        "filename": fname,
                        "type": "image",
                        "account": active_user,
                        "posted_at": datetime.now().isoformat(),
                        "instagram_url": post_url,
                        "caption": full_caption[:200],
                        "media_pk": str(media.pk),
                        "status": "posted"
                    }
                    hist_list.insert(0, entry)
                    with open(history_file, "w", encoding="utf-8") as f:
                        json.dump(hist_list, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

                posted_count += 1
            except Exception as e:
                print(f"[!] Failed to post image {fname}: {e}")
                failed_count += 1

            if idx < len(images) or reels:
                print(f"[*] Cooling down for {delay_seconds}s to protect account health...")
                time.sleep(delay_seconds)

    # 4. Post Reels Next
    if reels:
        print(f"\n>>> PROCESSING {len(reels)} REEL(S)...")
        for idx, r_fname in enumerate(reels, 1):
            print(f"\n[{idx}/{len(reels)}] Preparing Reel: {r_fname}")
            try:
                success = upload_single_reel(cl, r_fname, auto_confirm=True)
                if success:
                    posted_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                print(f"[!] Failed to post Reel {r_fname}: {e}")
                failed_count += 1

            if idx < len(reels):
                print(f"[*] Cooling down for {delay_seconds}s to protect account health...")
                time.sleep(delay_seconds)

    print("\n" + "=" * 65)
    print("                 AUTO-POST RUN COMPLETE")
    print("=" * 65)
    print(f"  Target Account  : @{active_user}")
    print(f"  Successfully Posted : {posted_count}")
    print(f"  Failed / Skipped   : {failed_count}")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(description="Instagram Auto-Post for Images and Reels")
    parser.add_argument(
        "--account", "-a",
        type=str,
        default=None,
        help="Specify Instagram account username to post to"
    )
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["all", "images", "reels"],
        default="all",
        help="Content to post: all (Images + Reels), images (Images only), reels (Reels only)"
    )
    parser.add_argument(
        "--delay", "-d",
        type=int,
        default=5,
        help="Seconds delay between consecutive uploads (default: 5)"
    )
    args = parser.parse_args()
    auto_post_all(account=args.account, mode=args.mode, delay_seconds=args.delay)

if __name__ == "__main__":
    main()
