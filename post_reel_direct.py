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
from caption_ai import generate_reel_content, get_cached_caption, save_caption_cache
from account_manager import get_instagram_client, get_active_account

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REELS_DIR = os.path.join(BASE_DIR, "reels")
NEW_REELS_DIR = os.path.join(REELS_DIR, "new")
POSTED_DIR = os.path.join(REELS_DIR, "posted")
CAPTIONS_DIR = os.path.join(BASE_DIR, "captions")

for d in [REELS_DIR, NEW_REELS_DIR, POSTED_DIR, CAPTIONS_DIR]:
    os.makedirs(d, exist_ok=True)

def get_pending_reels():
    valid_exts = (".mp4", ".mov", ".m4v")
    files = [
        f for f in os.listdir(NEW_REELS_DIR)
        if os.path.isfile(os.path.join(NEW_REELS_DIR, f)) and f.lower().endswith(valid_exts)
    ]
    return sorted(files)

def ensure_thumbnail(video_path: str) -> str:
    """Ensures a JPG thumbnail exists for the video to guarantee upload success."""
    base_name = os.path.splitext(video_path)[0]
    thumb_path = f"{base_name}.jpg"
    if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
        return thumb_path

    # Try imageio_ffmpeg binary or local ffmpeg.exe
    ffmpeg_exe = None
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    local_ffmpeg = os.path.abspath(os.path.join(BASE_DIR, "..", "ffmpeg.exe"))
    if not ffmpeg_exe and os.path.exists(local_ffmpeg):
        ffmpeg_exe = local_ffmpeg

    if ffmpeg_exe:
        import subprocess
        cmd = [
            ffmpeg_exe, "-y", "-ss", "00:00:01",
            "-i", video_path, "-vframes", "1",
            "-q:v", "2", thumb_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(thumb_path):
                return thumb_path
        except Exception as e:
            print(f"[*] Thumbnail extraction notice: {e}")
    return None

def upload_single_reel(cl: Client, reel_filename: str, auto_confirm: bool = False):
    reel_path = os.path.join(NEW_REELS_DIR, reel_filename)
    if not os.path.exists(reel_path):
        print(f"[!] Video not found: {reel_filename}")
        return False

    active_acc = get_active_account()

    # Check duplicate per account
    history_file = os.path.join(BASE_DIR, "posting_history.json")
    if os.path.exists(history_file):
        try:
            import json
            with open(history_file, "r", encoding="utf-8") as f:
                hist = json.load(f)
                posts = hist.get("posts", hist) if isinstance(hist, dict) else hist
                for p in posts:
                    if (p.get("filename") == reel_filename or p.get("media_id") == reel_filename) and p.get("account") == active_acc and p.get("status") in ["posted", "published"]:
                        print(f"\n[!] WARNING: '{reel_filename}' has already been posted to @{active_acc} on {p.get('posted_at')}")
                        if not auto_confirm:
                            re_post = input("Do you still want to re-post to the same account? [Y/N]: ").strip().lower()
                            if re_post not in ['y', 'yes']:
                                print("Cancelled.")
                                return False
                        else:
                            print("Skipping duplicate Reel.")
                            return False
                        break
        except Exception:
            pass

    print(f"\n[*] Generating content-aware caption for: {reel_filename}...")
    ai_meta = generate_reel_content(reel_path)

    print("\n" + "=" * 55)
    print(f"REEL: {reel_filename}  (Topic: {ai_meta.get('topic', 'General')})")
    print("=" * 55)
    print("CAPTION:")
    print(ai_meta["caption"])
    print("\nHASHTAGS:")
    print(ai_meta["hashtags"])
    print("=" * 55)

    final_caption = ai_meta["full"]

    if not auto_confirm:
        user_input = input("\nPress ENTER to accept caption, or type 'edit' to change: ").strip().lower()
        if user_input == 'edit':
            custom_caption = input("\nEnter custom caption text:\n> ").strip()
            custom_tags = input("Enter custom hashtags (or press ENTER to keep):\n> ").strip()
            tags = custom_tags if custom_tags else ai_meta["hashtags"]
            final_caption = f"{custom_caption}\n\n{tags}"
            save_caption_cache(reel_filename, custom_caption, tags, topic="Custom")

        confirm = input(f"\nPublish '{reel_filename}' to @{active_acc} now? [Y/N]: ").strip().lower()
        if confirm not in ['y', 'yes']:
            print(f"Skipping publish for '{reel_filename}'. Caption saved in captions/.")
            return False

    print(f"\n[*] Preparing thumbnail & uploading Reel directly to @{active_acc}...")
    thumb_path = ensure_thumbnail(reel_path)
    try:
        upload_kwargs = {
            "path": Path(reel_path),
            "caption": final_caption
        }
        if thumb_path and os.path.exists(thumb_path):
            upload_kwargs["thumbnail"] = Path(thumb_path)

        media = cl.clip_upload(**upload_kwargs)
        post_url = f"https://www.instagram.com/reel/{media.code}/"
        print(f"\n[✓] REEL PUBLISHED SUCCESSFULLY!")
        print(f"    Media PK: {media.pk}")
        print(f"    Code: {media.code}")
        print(f"    Instagram URL: {post_url}")

        # Archive copy to reels/posted/, but keep master in reels/new/
        dest_path = os.path.join(POSTED_DIR, reel_filename)
        if not os.path.exists(dest_path):
            try:
                shutil.copy2(reel_path, dest_path)
            except Exception:
                pass
        if thumb_path and os.path.exists(thumb_path):
            thumb_dest = os.path.join(POSTED_DIR, os.path.basename(thumb_path))
            if not os.path.exists(thumb_dest):
                try:
                    shutil.copy2(thumb_path, thumb_dest)
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
                "media_id": reel_filename,
                "filename": reel_filename,
                "type": "reel",
                "account": active_acc,
                "posted_at": datetime.now().isoformat(),
                "instagram_url": post_url,
                "caption": final_caption[:200],
                "media_pk": str(media.pk),
                "status": "posted"
            }
            hist_list.insert(0, entry)
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(hist_list, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # Update SQLite DB
        try:
            import database
            reel_id = os.path.splitext(reel_filename)[0]
            database.mark_published(reel_id, post_url, account=active_acc)
        except Exception:
            pass

        print(f"[✓] Saved posting history for @{active_acc}. Shared Reel remains available.")
        return True
    except Exception as e:
        err = str(e)
        if "login_required" in err.lower() or "upload_settings" in err.lower():
            print(f"\n[!] AUTHENTICATION ERROR: Instagram session for @{active_acc} has expired (HTTP 403: login_required).")
            print(f"    Please re-authenticate your account: python account_manager.py login {active_acc}")
        else:
            print(f"\n[!] Upload error: {e}")
        return False


def main():
    args = [a.lower() for a in sys.argv[1:]]
    auto_accept = any(a in ("--accept", "--yes", "-y", "--auto", "accept") for a in args)

    active_acc = get_active_account()
    print("=" * 55)
    print(f"   INSTAGRAM REEL DIRECT PUBLISHER (@{active_acc})")
    print("=" * 55)

    cl = get_instagram_client(active_acc)
    if not cl:
        return

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

    target_idx = None
    for i, a in enumerate(args):
        if a in ("--reel", "-r", "--file", "-f") and i + 1 < len(args):
            val = args[i + 1]
            if val.isdigit():
                target_idx = int(val) - 1
            else:
                for idx_cand, r_name in enumerate(reels):
                    if val.lower() in r_name.lower():
                        target_idx = idx_cand
                        break

    if auto_accept:
        if target_idx is None:
            # Pick first unposted reel for active account
            history_file = os.path.join(BASE_DIR, "posting_history.json")
            posted_files = set()
            if os.path.exists(history_file):
                try:
                    import json
                    with open(history_file, "r", encoding="utf-8") as f:
                        hist = json.load(f)
                        posts = hist.get("posts", hist) if isinstance(hist, dict) else hist
                        for p in posts:
                            if p.get("account") == active_acc and p.get("status") in ["posted", "published"]:
                                posted_files.add(p.get("filename"))
                except Exception:
                    pass
            for idx_cand, r_name in enumerate(reels):
                if r_name not in posted_files:
                    target_idx = idx_cand
                    break
            if target_idx is None:
                target_idx = 0

        chosen = reels[target_idx]
        print(f"\n[✓] Auto-accept flag active. Selected Reel [{target_idx + 1}] '{chosen}' & confirming publish...")
        upload_single_reel(cl, chosen, auto_confirm=True)
    else:
        choice_str = input("\nSelect Reel number (or press Enter for [1]): ").strip()
        idx = int(choice_str) - 1 if choice_str.isdigit() else 0

        if 0 <= idx < len(reels):
            upload_single_reel(cl, reels[idx])
        else:
            print("[!] Invalid selection.")

if __name__ == "__main__":
    main()
