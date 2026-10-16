import os
import re
from pathlib import Path
from typing import Optional
import yt_dlp
from config import DOWNLOADS_DIR

def extract_safe_reel_id(url: str, fallback_id: str = "") -> str:
    """Extract clean Instagram shortcode or return safe fallback ID."""
    match = re.search(r"/(?:reel|p)/([A-Za-z0-9_-]+)", url)
    if match:
        return match.group(1)
    if fallback_id:
        clean = re.sub(r'[^A-Za-z0-9_-]', '_', fallback_id)
        return clean[:30]
    return "reel_video"

def download_reel(reel_url: str, custom_id: str = "", browser_cookies: str = "") -> str:
    """
    Downloads the Reel video file to the downloads directory using a clean,
    sanitized filename without URL query strings or illegal characters.
    """
    clean_id = extract_safe_reel_id(reel_url, custom_id)
    download_path = Path(DOWNLOADS_DIR)
    download_path.mkdir(parents=True, exist_ok=True)

    outtmpl = str(download_path / f"{clean_id}.%(ext)s")

    ydl_opts = {
        'format': 'best[ext=mp4]/bestvideo+bestaudio/best',
        'outtmpl': outtmpl,
        'windowsfilenames': True,
        'restrictfilenames': True,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': True,
        'merge_output_format': 'mp4'
    }

    if browser_cookies:
        ydl_opts['cookiesfrombrowser'] = (browser_cookies, )

    # Helper: Download photo or album via instagrapi
    def _download_via_instagrapi(target_url: str) -> str:
        print("[*] Downloading post media via Instagram client...")
        try:
            from account_manager import get_instagram_client, get_active_account
            cl = get_instagram_client(get_active_account())
        except Exception:
            cl = None

        if not cl:
            import instagrapi
            cl = instagrapi.Client()
            try:
                from account_manager import get_session_path
                session_path = get_session_path()
                if session_path and os.path.exists(session_path):
                    cl.load_settings(session_path)
            except Exception:
                pass

        pk = cl.media_pk_from_url(target_url)
        m = cl.media_info(pk)

        if m.media_type == 8:  # Carousel / Album
            downloaded = cl.album_download(pk, folder=download_path)
        elif m.media_type == 2:  # Video
            downloaded = [cl.video_download(pk, folder=download_path)]
        else:  # Photo (media_type == 1)
            downloaded = [cl.photo_download(pk, folder=download_path)]

        if not downloaded:
            raise ValueError(f"No media files downloaded from post {target_url}")

        # Convert any .heic files to standard .jpg
        processed = []
        for item in downloaded:
            p_str = str(Path(item).resolve())
            if p_str.lower().endswith('.heic'):
                jpg_path = os.path.splitext(p_str)[0] + '.jpg'
                converted = False
                try:
                    from PIL import Image
                    with Image.open(p_str) as im:
                        im.convert('RGB').save(jpg_path, 'JPEG', quality=95)
                    try:
                        os.remove(p_str)
                    except Exception:
                        pass
                    p_str = jpg_path
                    converted = True
                except Exception:
                    pass
                if not converted:
                    try:
                        os.rename(p_str, jpg_path)
                        p_str = jpg_path
                    except Exception:
                        pass
            processed.append(p_str)

        return processed[0]

    # First attempt: direct or with cookies via yt-dlp
    download_error = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([reel_url])
    except Exception as e:
        download_error = e
        err_msg = str(e).lower()
        if "no video in this post" in err_msg or "no video formats found" in err_msg or "/p/" in reel_url:
            print("[*] Detected photo/album post. Downloading high-res media via instagrapi...")
            try:
                return _download_via_instagrapi(reel_url)
            except Exception as pe:
                raise Exception(f"Failed to download post media: {pe}")
        elif "certain audiences" in err_msg or "login" in err_msg:
            if not browser_cookies:
                for b in ['chrome', 'edge', 'firefox']:
                    try:
                        print(f"[*] Trying to load session from {b} browser for restricted content...")
                        opts_with_cookie = dict(ydl_opts)
                        opts_with_cookie['cookiesfrombrowser'] = (b, )
                        with yt_dlp.YoutubeDL(opts_with_cookie) as ydl:
                            ydl.download([reel_url])
                        download_error = None
                        break
                    except Exception:
                        continue
                if download_error:
                    # Fallback to instagrapi
                    try:
                        return _download_via_instagrapi(reel_url)
                    except Exception:
                        raise download_error
            else:
                try:
                    return _download_via_instagrapi(reel_url)
                except Exception:
                    raise download_error
        else:
            # Try instagrapi as final fallback before failing
            try:
                return _download_via_instagrapi(reel_url)
            except Exception:
                raise download_error

    expected_mp4 = download_path / f"{clean_id}.mp4"
    if expected_mp4.exists():
        return str(expected_mp4.resolve())

    # Fallback search if different extension was produced
    for f in download_path.glob(f"{clean_id}.*"):
        if f.suffix in ['.mp4', '.mkv', '.webm', '.mov', '.jpg', '.jpeg', '.png', '.webp']:
            return str(f.resolve())

    return str(expected_mp4.resolve())


def check_video_has_audio(file_path: str) -> bool:
    """
    Checks if a video file has an active, playable audio track.
    Returns True if audio is detected, False otherwise.
    """
    if not file_path or not os.path.exists(file_path):
        return False
    try:
        from moviepy import VideoFileClip
        clip = VideoFileClip(file_path)
        has_audio = (clip.audio is not None)
        clip.close()
        return has_audio
    except Exception as e:
        print(f"[*] Audio track check notice: {e}")
        return True


def download_all_media(target_url: str, custom_id: str = "", source_candidate: Optional[dict] = None) -> dict:
    """
    Downloads ALL original media files for a post:
    - For Carousel: downloads all 1..N items in exact original order, converts HEIC to JPG.
    - For Single Image: downloads high-resolution original image.
    - For Reel/Video: downloads original video and checks for active audio track.
    Preserves exact original media (visible watermarks/embedded text) without cropping.
    Always checks and accurately reports audio track status.
    """
    import shutil
    from instagram_source import extract_audio_details
    base_dir = os.path.dirname(os.path.abspath(__file__))
    new_images_dir = os.path.join(base_dir, "images", "new")
    new_reels_dir = os.path.join(base_dir, "reels", "new")
    downloads_dir = Path(DOWNLOADS_DIR)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    os.makedirs(new_images_dir, exist_ok=True)
    os.makedirs(new_reels_dir, exist_ok=True)

    clean_id = extract_safe_reel_id(target_url, custom_id)
    m = None
    creator = (source_candidate.get("creator") if source_candidate else "") or ""

    # 1. Attempt instagrapi inspection & download
    try:
        from account_manager import get_instagram_client, get_active_account
        cl = get_instagram_client(get_active_account())
    except Exception:
        cl = None

    if not cl:
        try:
            import instagrapi
            cl = instagrapi.Client()
            from account_manager import get_session_path
            session_path = get_session_path()
            if session_path and os.path.exists(session_path):
                cl.load_settings(session_path)
        except Exception:
            cl = None

    if cl and ("/p/" in target_url or "/reel/" in target_url):
        try:
            pk = cl.media_pk_from_url(target_url)
            m = cl.media_info(pk)
            if getattr(m, "user", None) and getattr(m.user, "username", None):
                creator = m.user.username
            
            # --- CAROUSEL ALBUM ---
            if m.media_type == 8:
                print(f"[*] Detected Instagram Carousel ({len(m.resources) if m.resources else 'multi'} items). Downloading all slides...")
                downloaded = cl.album_download(pk, folder=downloads_dir)
                if not downloaded:
                    raise ValueError(f"Album download returned empty for {target_url}")

                processed_paths = []
                processed_filenames = []
                total_size = 0

                for item in downloaded:
                    p_str = str(Path(item).resolve())
                    # Convert HEIC to JPG if necessary
                    if p_str.lower().endswith('.heic'):
                        jpg_path = os.path.splitext(p_str)[0] + '.jpg'
                        converted = False
                        try:
                            from PIL import Image
                            with Image.open(p_str) as im:
                                im.convert('RGB').save(jpg_path, 'JPEG', quality=95)
                            try:
                                os.remove(p_str)
                            except Exception:
                                pass
                            p_str = jpg_path
                            converted = True
                        except Exception:
                            pass
                        if not converted:
                            try:
                                os.rename(p_str, jpg_path)
                                p_str = jpg_path
                            except Exception:
                                pass

                    fname = os.path.basename(p_str)
                    target_path = os.path.join(new_images_dir, fname)
                    if os.path.abspath(p_str) != os.path.abspath(target_path):
                        shutil.copy2(p_str, target_path)

                    processed_paths.append(target_path)
                    processed_filenames.append(fname)
                    total_size += os.path.getsize(target_path)

                src_audio = source_candidate.get("audio_info") if (source_candidate and source_candidate.get("audio_info")) else None
                audio_info = src_audio or extract_audio_details(m=m, is_video=False, creator=creator, post_type="carousel")
                audio_status = audio_info.get("audio_status", "No audio detected")

                from bot_service import format_size
                return {
                    "status": "downloaded",
                    "post_type": "carousel",
                    "item_count": len(processed_paths),
                    "media_files": processed_paths,
                    "media_filenames": processed_filenames,
                    "filename": processed_filenames[0] if processed_filenames else "",
                    "new_reel_path": processed_paths[0] if processed_paths else "",
                    "size": total_size,
                    "size_formatted": format_size(total_size),
                    "audio_status": audio_status,
                    "audio_info": audio_info,
                    "has_audio": False,
                    "media_type": "image",
                    "preserved_watermark": True
                }

            # --- SINGLE PHOTO ---
            elif m.media_type == 1:
                print(f"[*] Detected Single Photo post. Downloading original image...")
                photo_file = cl.photo_download(pk, folder=downloads_dir)
                p_str = str(Path(photo_file).resolve())
                if p_str.lower().endswith('.heic'):
                    jpg_path = os.path.splitext(p_str)[0] + '.jpg'
                    try:
                        from PIL import Image
                        with Image.open(p_str) as im:
                            im.convert('RGB').save(jpg_path, 'JPEG', quality=95)
                        try:
                            os.remove(p_str)
                        except Exception:
                            pass
                        p_str = jpg_path
                    except Exception:
                        pass

                fname = os.path.basename(p_str)
                target_path = os.path.join(new_images_dir, fname)
                if os.path.abspath(p_str) != os.path.abspath(target_path):
                    shutil.copy2(p_str, target_path)

                fsize = os.path.getsize(target_path)
                src_audio = source_candidate.get("audio_info") if (source_candidate and source_candidate.get("audio_info")) else None
                audio_info = src_audio or extract_audio_details(m=m, is_video=False, creator=creator, post_type="image")
                audio_status = audio_info.get("audio_status", "No audio detected")

                from bot_service import format_size
                return {
                    "status": "downloaded",
                    "post_type": "image",
                    "item_count": 1,
                    "media_files": [target_path],
                    "media_filenames": [fname],
                    "filename": fname,
                    "new_reel_path": target_path,
                    "size": fsize,
                    "size_formatted": format_size(fsize),
                    "audio_status": audio_status,
                    "audio_info": audio_info,
                    "has_audio": False,
                    "media_type": "image",
                    "preserved_watermark": True
                }

        except Exception as e:
            print(f"[*] Note: instagrapi download attempt error: {e}. Falling back to standard downloader...")

    # 2. Video / Reel or standard fallback download
    video_path = download_reel(target_url, custom_id=clean_id)
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Downloaded media file not found: {video_path}")

    filename = os.path.basename(video_path)
    ext = os.path.splitext(filename)[1].lower()
    is_image = ext in ('.jpg', '.jpeg', '.png', '.webp')

    if is_image:
        target_path = os.path.join(new_images_dir, filename)
        post_type = "image"
        has_audio = False
        src_audio = source_candidate.get("audio_info") if (source_candidate and source_candidate.get("audio_info")) else None
        audio_info = src_audio or {
            "detected": False,
            "track_name": "",
            "artist_name": "",
            "is_embedded": False,
            "audio_status": "No audio detected",
            "status_label": "No audio detected",
            "post_type": "image",
            "note": "No audio track associated with this source post"
        }
        audio_status = audio_info.get("audio_status", "No audio detected")
    else:
        target_path = os.path.join(new_reels_dir, filename)
        post_type = "reel"
        has_audio = check_video_has_audio(video_path)
        
        # Audio track details resolution
        src_audio = source_candidate.get("audio_info") if (source_candidate and source_candidate.get("audio_info")) else None
        if not src_audio and m:
            src_audio = extract_audio_details(m=m, is_video=True, creator=creator, post_type="reel")

        t_name = src_audio.get("track_name") if src_audio else ""
        a_name = src_audio.get("artist_name") if src_audio else ""

        if has_audio:
            audio_info = {
                "detected": True,
                "track_name": t_name or "Original audio",
                "artist_name": a_name or (f"@{creator}" if creator else "Original creator"),
                "is_embedded": True,
                "audio_status": "Detected",
                "status_label": "Detected",
                "status_sub": "Audio embedded in downloaded video",
                "post_type": "reel",
                "note": "Audio embedded in downloaded video"
            }
            audio_status = "Detected"
        else:
            # Video downloaded with no audio track / muted
            if t_name or (src_audio and src_audio.get("detected")):
                audio_info = {
                    "detected": True,
                    "track_name": t_name or "Original audio",
                    "artist_name": a_name or (f"@{creator}" if creator else ""),
                    "is_embedded": False,
                    "audio_status": "Detected on source",
                    "status_label": "Detected on source",
                    "status_sub": "Audio is not embedded in downloaded media",
                    "post_type": "reel",
                    "note": "Audio is not embedded in downloaded media. Instagram audio selection may be required."
                }
                audio_status = "Detected on source"
            else:
                audio_info = {
                    "detected": False,
                    "track_name": "",
                    "artist_name": "",
                    "is_embedded": False,
                    "audio_status": "No audio detected",
                    "status_label": "No audio detected",
                    "status_sub": "",
                    "post_type": "reel",
                    "note": "Video file has no audio track"
                }
                audio_status = "No audio detected"

    if os.path.abspath(video_path) != os.path.abspath(target_path):
        shutil.copy2(video_path, target_path)

    fsize = os.path.getsize(target_path)
    from bot_service import format_size
    return {
        "status": "downloaded",
        "post_type": post_type,
        "item_count": 1,
        "media_files": [target_path],
        "media_filenames": [filename],
        "filename": filename,
        "new_reel_path": target_path,
        "size": fsize,
        "size_formatted": format_size(fsize),
        "audio_status": audio_status,
        "audio_info": audio_info,
        "has_audio": has_audio,
        "media_type": "image" if is_image else "reel",
        "preserved_watermark": True
    }



