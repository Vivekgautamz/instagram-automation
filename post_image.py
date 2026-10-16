import os
import sys
import shutil
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from instagrapi import Client

from account_manager import get_instagram_client, get_active_account

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))

# Image folders
IMAGES_DIR = os.path.join(BASE_DIR, "images")
NEW_IMAGES_DIR = os.path.join(IMAGES_DIR, "new")
POSTED_IMAGES_DIR = os.path.join(IMAGES_DIR, "posted")
LEGACY_POSTED_DIR = os.path.join(BASE_DIR, "posted_images")
DOWNLOADED_IMAGES_DIR = os.path.join(PARENT_DIR, "downloaded_images")

for d in [IMAGES_DIR, NEW_IMAGES_DIR, POSTED_IMAGES_DIR, LEGACY_POSTED_DIR]:
    os.makedirs(d, exist_ok=True)

DEFAULT_IMAGE_HASHTAGS = "#photo #photography #instagood #instagram #instadaily #photooftheday #explore #picoftheday"

def get_available_images():
    valid_exts = (".jpg", ".jpeg", ".png", ".webp")
    results = []

    # Check images/new/ first (recommended structure)
    if os.path.exists(NEW_IMAGES_DIR):
        for f in os.listdir(NEW_IMAGES_DIR):
            p = os.path.join(NEW_IMAGES_DIR, f)
            if os.path.isfile(p) and f.lower().endswith(valid_exts):
                results.append(p)

    # Check local images/ root folder (excluding subfolders)
    if os.path.exists(IMAGES_DIR):
        for f in os.listdir(IMAGES_DIR):
            p = os.path.join(IMAGES_DIR, f)
            if os.path.isfile(p) and f.lower().endswith(valid_exts):
                if p not in results:
                    results.append(p)

    # Also check parent downloaded_images folder
    if os.path.exists(DOWNLOADED_IMAGES_DIR):
        for f in os.listdir(DOWNLOADED_IMAGES_DIR):
            p = os.path.join(DOWNLOADED_IMAGES_DIR, f)
            if os.path.isfile(p) and f.lower().endswith(valid_exts):
                if p not in results:
                    results.append(p)

    return sorted(results)

def main():
    active_acc = get_active_account()
    print("=" * 55)
    print(f"      INSTAGRAM IMAGE PUBLISHER (@{active_acc})")
    print("=" * 55)

    cl = get_instagram_client(active_acc)
    if not cl:
        return

    images = get_available_images()
    if not images:
        print(f"\n[!] No images found in:")
        print(f"    - {NEW_IMAGES_DIR}")
        print(f"    - {IMAGES_DIR}")
        print(f"    - {DOWNLOADED_IMAGES_DIR}")
        print("\nPlease put your image (.jpg or .png) in 'images/new/' and run again.")
        return

    # Check if image was passed as command argument
    target_image = None
    if len(sys.argv) > 1:
        arg_path = " ".join(sys.argv[1:]).strip().strip('"').strip("'")
        if os.path.exists(arg_path):
            target_image = os.path.abspath(arg_path)

    if not target_image:
        print(f"\nFound {len(images)} image(s) available to post:\n")
        display_limit = min(len(images), 10)
        for i in range(display_limit):
            img_path = images[i]
            size_kb = os.path.getsize(img_path) / 1024
            print(f"[{i+1}] {os.path.basename(img_path)} ({size_kb:.1f} KB)")
        if len(images) > display_limit:
            print(f"... and {len(images) - display_limit} more.")

        choice = input("\nSelect Image number (or press Enter for [1]): ").strip()
        idx = int(choice) - 1 if choice.isdigit() else 0
        if 0 <= idx < len(images):
            target_image = images[idx]
        else:
            print("[!] Invalid choice.")
            return

    print(f"\nSelected image: {os.path.basename(target_image)}")

    caption_text = input("\nEnter caption (Press Enter for default caption):\n> ").strip()
    if not caption_text:
        caption_text = "Words from the heart. ✨"

    tags_input = input("Enter hashtags (Press Enter for default hashtags):\n> ").strip()
    if not tags_input:
        tags_input = DEFAULT_IMAGE_HASHTAGS

    full_caption = f"{caption_text}\n\n{tags_input}"

    print("\n" + "-" * 40)
    print("PROPOSED POST:")
    print("-" * 40)
    print(full_caption)
    print("-" * 40)

    fname = os.path.basename(target_image)
    
    # Check duplicate per account
    history_file = os.path.join(BASE_DIR, "posting_history.json")
    if os.path.exists(history_file):
        try:
            import json
            with open(history_file, "r", encoding="utf-8") as f:
                hist = json.load(f)
                posts = hist.get("posts", hist) if isinstance(hist, dict) else hist
                for p in posts:
                    if (p.get("filename") == fname or p.get("media_id") == fname) and p.get("account") == active_acc and p.get("status") in ["posted", "published"]:
                        print(f"\n[!] WARNING: '{fname}' has already been posted to @{active_acc} on {p.get('posted_at')}")
                        re_post = input("Do you still want to re-post to the same account? [Y/N]: ").strip().lower()
                        if re_post not in ['y', 'yes']:
                            print("Cancelled.")
                            return
                        break
        except Exception:
            pass

    confirm = input(f"\nPublish to @{active_acc}? [Y/N]: ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("Cancelled.")
        return

    print(f"\n[*] Uploading photo to Instagram (@{active_acc})...")
    try:
        media = cl.photo_upload(
            path=Path(target_image),
            caption=full_caption
        )
        post_url = f"https://www.instagram.com/p/{media.code}/"
        print(f"\n[OK] PHOTO PUBLISHED SUCCESSFULLY!")
        print(f"    Media PK: {media.pk}")
        print(f"    Code: {media.code}")
        print(f"    URL: {post_url}")

        # Archive copy to images/posted/ for backup, but keep original in images/new/
        dest = os.path.join(POSTED_IMAGES_DIR, fname)
        if not os.path.exists(dest):
            try:
                shutil.copy2(target_image, dest)
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
                "account": active_acc,
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

        print(f"[OK] Saved posting history for @{active_acc}. Shared media remains available.")
    except Exception as e:
        err_str = str(e)
        if "restrict" in err_str.lower() or "feedback_required" in err_str.lower():
            print(f"\n[!] ⚠️ INSTAGRAM ACTION RESTRICTED for @{active_acc}:")
            print(f"    Instagram responded: \"We restrict certain activity to protect our community.\"")
            print(f"    The session is valid, but Instagram is temporarily restricting publishing on this account.")
            print(f"    Recommended steps:")
            print(f"    1. Wait 24-48 hours for the restriction to lift naturally.")
            print(f"    2. Open the Instagram mobile app as @{active_acc} to check if manual posting works.")
            print(f"    3. Switch to another account (e.g. @poetghazipur61 or @psychology.yaarr) to continue posting.")
        else:
            print(f"\n[!] Upload error: {e}")

if __name__ == "__main__":
    main()

