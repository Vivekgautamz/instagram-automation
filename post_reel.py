import os
import sys
import shutil
from dotenv import load_dotenv

# Ensure emoji / unicode prints cleanly on Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from caption_ai import generate_reel_content, get_cached_caption, save_caption_cache
from instagram import publish_reel_container

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REELS_DIR = os.path.join(BASE_DIR, "reels")
NEW_REELS_DIR = os.path.join(REELS_DIR, "new")
POSTED_DIR = os.path.join(REELS_DIR, "posted")
CAPTIONS_DIR = os.path.join(BASE_DIR, "captions")

# Create standard directories
for d in [REELS_DIR, NEW_REELS_DIR, POSTED_DIR, CAPTIONS_DIR]:
    os.makedirs(d, exist_ok=True)

# Also check root reels/ for backward compatibility and move to reels/new/
for f in os.listdir(REELS_DIR):
    full_p = os.path.join(REELS_DIR, f)
    if os.path.isfile(full_p) and f.lower().endswith((".mp4", ".mov", ".m4v")):
        shutil.move(full_p, os.path.join(NEW_REELS_DIR, f))

def get_pending_reels():
    valid_exts = (".mp4", ".mov", ".m4v")
    files = [
        f for f in os.listdir(NEW_REELS_DIR)
        if os.path.isfile(os.path.join(NEW_REELS_DIR, f)) and f.lower().endswith(valid_exts)
    ]
    return sorted(files)

def process_single_reel(reel_filename: str, video_url_base: str, auto_confirm: bool = False):
    """Generates content for a single reel and optionally publishes it."""
    reel_path = os.path.join(NEW_REELS_DIR, reel_filename)
    if not os.path.exists(reel_path):
        print(f"[!] Reel not found: {reel_filename}")
        return False

    print(f"\nAnalyzing: {reel_filename}...")
    ai_meta = generate_reel_content(reel_path)

    print("\n" + "=" * 50)
    print(f"REEL: {reel_filename} (Topic: {ai_meta.get('topic', 'General')})")
    print("=" * 50)
    print("CAPTION:")
    print(ai_meta["caption"])
    print("\nHASHTAGS:")
    print(ai_meta["hashtags"])
    print("=" * 50)

    final_caption = ai_meta["full"]

    if not auto_confirm:
        user_input = input("\nPress ENTER to accept caption, or type 'edit' to change: ").strip().lower()
        if user_input == 'edit':
            custom_caption = input("\nEnter custom caption text:\n> ").strip()
            custom_tags = input("Enter custom hashtags (or press ENTER to keep):\n> ").strip()
            tags = custom_tags if custom_tags else ai_meta["hashtags"]
            final_caption = f"{custom_caption}\n\n{tags}"
            save_caption_cache(reel_filename, custom_caption, tags, topic="Custom")

        confirm = input(f"\nPublish '{reel_filename}' to your Instagram? [Y/N]: ").strip().lower()
        if confirm not in ['y', 'yes']:
            print(f"Skipping publish for '{reel_filename}'. Saved metadata to captions/.")
            return False

    # Check Meta credentials
    IG_USER_ID = os.getenv("IG_USER_ID", "").strip()
    FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN", "").strip()
    if not IG_USER_ID or not FB_ACCESS_TOKEN:
        print("\n[!] Error: Missing IG_USER_ID or FB_ACCESS_TOKEN in .env file.")
        return False

    if not video_url_base:
        print("\n[!] Error: PUBLIC_MEDIA_BASE_URL is not set.")
        return False

    video_url = f"{video_url_base}/{reel_filename}"
    print(f"\n[*] Uploading via Meta Graph API: {video_url}")
    res = publish_reel_container(video_url, final_caption)

    if res.get("success"):
        print(f"[✓] Published successfully! Post ID: {res.get('post_id')}")
        dest_path = os.path.join(POSTED_DIR, reel_filename)
        shutil.move(reel_path, dest_path)
        print(f"[✓] Moved '{reel_filename}' -> reels/posted/")
        return True
    else:
        print(f"[!] Publish failed: {res.get('error')}")
        return False

def main():
    print("=" * 50)
    print("       INSTAGRAM CONTENT-AWARE REEL BOT")
    print("=" * 50)

    reels = get_pending_reels()

    if not reels:
        print(f"\n[!] No video files found in:")
        print(f"    {NEW_REELS_DIR}")
        print("\nDrop your .mp4 files into 'reels/new/' and run this script again.")
        return

    print(f"\nFound {len(reels)} reel(s) ready in reels/new/:\n")
    for idx, r in enumerate(reels, 1):
        file_path = os.path.join(NEW_REELS_DIR, r)
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        cached_tag = " [✓ Cached]" if get_cached_caption(r) else ""
        print(f"[{idx}] {r} ({size_mb:.2f} MB){cached_tag}")

    print("\nOptions:")
    print("  - Type a number (e.g. 1) to publish that specific Reel")
    print("  - Type 'all' to batch analyze and publish all Reels")
    print("  - Type 'generate' to analyze all Reels without publishing yet")
    selection = input("\nSelect choice (or press Enter for [1]): ").strip().lower()

    # Determine Base URL
    base_url = os.getenv("PUBLIC_MEDIA_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        print("\n[!] Notice: PUBLIC_MEDIA_BASE_URL is not configured in .env.")
        print("    If publishing live, make sure your tunnel/URL is running.")

    if selection == "all":
        print(f"\n[*] Starting Batch Analysis for {len(reels)} Reels...")
        for i, r in enumerate(reels, 1):
            print(f"\n[{i}/{len(reels)}] {r}")
            reel_path = os.path.join(NEW_REELS_DIR, r)
            generate_reel_content(reel_path)
            print(f"✓ Caption & hashtags generated and cached in captions/{os.path.splitext(r)[0]}.json")

        print("\n" + "=" * 50)
        print("BATCH PREVIEW COMPLETE!")
        print("=" * 50)
        for r in reels:
            c = get_cached_caption(r)
            if c:
                print(f"\n--- {r} (Topic: {c.get('topic', 'General')}) ---")
                print(f"CAPTION: {c['caption']}")
                print(f"HASHTAGS: {c['hashtags']}")

        pub_all = input("\nPublish all analyzed Reels to Instagram now? [Y/N]: ").strip().lower()
        if pub_all in ['y', 'yes']:
            for r in reels:
                process_single_reel(r, base_url, auto_confirm=True)
        else:
            print("Publish skipped. All captions and hashtags remain saved in captions/.")

    elif selection == "generate":
        print(f"\n[*] Generating and saving metadata for all {len(reels)} Reels...")
        for i, r in enumerate(reels, 1):
            reel_path = os.path.join(NEW_REELS_DIR, r)
            generate_reel_content(reel_path)
            print(f"[{i}/{len(reels)}] ✓ {r} -> captions/{os.path.splitext(r)[0]}.json")
        print("\nAll done! Run 'python post_reel.py' anytime to review and publish.")

    else:
        # Single Reel Selection
        idx = int(selection) - 1 if selection.isdigit() else 0
        if 0 <= idx < len(reels):
            process_single_reel(reels[idx], base_url, auto_confirm=False)
        else:
            print("[!] Invalid selection.")

if __name__ == "__main__":
    main()
