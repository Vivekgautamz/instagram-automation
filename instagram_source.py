import re
from typing import List, Dict, Any
import yt_dlp

def extract_username_or_url(input_str: str) -> str:
    """Normalize input URL or username."""
    if not input_str:
        return ""
    input_str = str(input_str).strip()
    if not input_str.startswith("http"):
        # Username was entered
        username = input_str.lstrip("@").strip("/")
        return f"https://www.instagram.com/{username}/"
    return input_str

def extract_audio_details(
    m=None,
    entry: dict = None,
    is_video: bool = False,
    creator: str = "",
    post_type: str = "reel"
) -> Dict[str, Any]:
    """
    Extracts audio track metadata from Instagram Media object or yt-dlp entry.
    Always checks for audio on Photos, Carousels, and Reels.
    """
    track_name = ""
    artist_name = ""
    has_explicit_music = False

    # 1. Probe instagrapi Media object
    if m is not None:
        # Check clips_music_attribution_info
        music_attr = getattr(m, "clips_music_attribution_info", None)
        if music_attr:
            s_name = getattr(music_attr, "song_name", "") or ""
            a_name = getattr(music_attr, "artist_name", "") or ""
            if s_name:
                track_name = s_name
                artist_name = a_name
                has_explicit_music = True

        # Check clips_metadata
        if not track_name:
            clips_meta = getattr(m, "clips_metadata", None)
            if isinstance(clips_meta, dict):
                m_info = clips_meta.get("music_info") or {}
                if isinstance(m_info, dict) and m_info.get("music_asset_info"):
                    asset = m_info["music_asset_info"]
                    track_name = asset.get("title") or ""
                    artist_name = asset.get("display_artist") or ""
                    if track_name:
                        has_explicit_music = True
                if not track_name:
                    sound_info = clips_meta.get("original_sound_info") or {}
                    if isinstance(sound_info, dict):
                        track_name = sound_info.get("original_audio_title") or ""
                        ig_artist = sound_info.get("ig_artist") or {}
                        artist_name = ig_artist.get("username") or "" if isinstance(ig_artist, dict) else str(ig_artist)
                        if track_name:
                            has_explicit_music = True
            elif clips_meta:
                m_info = getattr(clips_meta, "music_info", None)
                if m_info and hasattr(m_info, "music_asset_info"):
                    asset = m_info.music_asset_info
                    track_name = getattr(asset, "title", "") or ""
                    artist_name = getattr(asset, "display_artist", "") or ""
                    if track_name:
                        has_explicit_music = True

        # Check music_metadata on m (common for carousels / photos with Instagram Music)
        if not track_name:
            music_meta = getattr(m, "music_metadata", None)
            if isinstance(music_meta, dict):
                m_info = music_meta.get("music_info") or {}
                if isinstance(m_info, dict) and m_info.get("music_asset_info"):
                    asset = m_info["music_asset_info"]
                    track_name = asset.get("title") or ""
                    artist_name = asset.get("display_artist") or ""
                    if track_name:
                        has_explicit_music = True

    # 2. Probe yt-dlp entry if instagrapi didn't find track
    if not track_name and entry:
        track_name = entry.get("track") or entry.get("music") or entry.get("soundtrack") or ""
        artist_name = entry.get("artist") or entry.get("channel") or ""
        if track_name:
            has_explicit_music = True

    # 3. Post-type specific categorization
    if post_type in ["image", "carousel"]:
        if has_explicit_music and track_name:
            return {
                "detected": True,
                "track_name": track_name,
                "artist_name": artist_name,
                "is_embedded": False,
                "audio_status": "Original audio detected",
                "status_label": "Original audio detected",
                "status_sub": "Available for repost",
                "post_type": post_type,
                "note": "Original audio track identified on source post (Instagram audio selection may be required for photos/carousels)"
            }
        else:
            return {
                "detected": False,
                "track_name": "",
                "artist_name": "",
                "is_embedded": False,
                "audio_status": "No audio detected",
                "status_label": "No audio detected",
                "status_sub": "",
                "post_type": post_type,
                "note": "No audio track associated with this source post"
            }

    # 4. Reel / Video post categorization
    m_has_audio = getattr(m, "has_audio", None) if m else None
    if m_has_audio is False:
        return {
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

    eff_track = track_name or "Original audio"
    eff_artist = artist_name or (f"@{creator}" if creator else "Original creator")
    return {
        "detected": True,
        "track_name": eff_track,
        "artist_name": eff_artist,
        "is_embedded": True,
        "audio_status": "Detected",
        "status_label": "Detected",
        "status_sub": "Audio stream present on source",
        "post_type": "reel",
        "note": "Audio detected on source Reel"
    }


def fetch_recent_reels(profile_or_reel_url: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch public metadata for reels or posts from the profile or single reel/post URL.
    Supports Instagram Reels (/reel/), Posts (/p/), Carousels, and Profile usernames.
    """
    normalized_url = extract_username_or_url(profile_or_reel_url)
    is_single_item = ("/p/" in normalized_url) or ("/reel/" in normalized_url)

    # 1. If it's a single post or reel, attempt high-fidelity instagrapi inspect first
    if is_single_item:
        try:
            from account_manager import get_instagram_client, get_active_account
            cl = get_instagram_client(get_active_account())
            if cl:
                pk = cl.media_pk_from_url(normalized_url)
                m = cl.media_info(pk)
                thumb = m.thumbnail_url
                if not thumb and getattr(m, "resources", None):
                    for r in m.resources:
                        if getattr(r, "thumbnail_url", None):
                            thumb = r.thumbnail_url
                            break

                creator = m.user.username if getattr(m, "user", None) and getattr(m.user, "username", None) else ""
                if not creator:
                    match = re.search(r"instagram\.com/([^/?#]+)", normalized_url)
                    if match and match.group(1) not in ["reel", "reels", "p", "explore"]:
                        creator = match.group(1)

                is_carousel = (m.media_type == 8) or bool(getattr(m, "resources", None) and len(m.resources) > 1)
                is_video = (m.media_type == 2)
                
                if is_carousel:
                    post_type = "carousel"
                elif is_video:
                    post_type = "reel"
                else:
                    post_type = "image"

                target_kind = "reel" if is_video else "p"
                canonical_url = f"https://www.instagram.com/{target_kind}/{m.code}/"

                raw_caption = m.caption_text or ""
                hashtags_list = re.findall(r"#[A-Za-z0-9_]+", raw_caption)
                original_hashtags = " ".join(hashtags_list)
                caption_only = re.sub(r"(?:\s*#[A-Za-z0-9_]+)+\s*$", "", raw_caption).strip()
                if not caption_only and raw_caption:
                    caption_only = raw_caption

                title = caption_only[:120].strip() if caption_only else f"Post by @{creator}"

                # Carousel slides preview
                items_preview = []
                if getattr(m, "resources", None):
                    for idx, res in enumerate(m.resources):
                        r_thumb = str(res.thumbnail_url) if getattr(res, "thumbnail_url", None) else ""
                        r_is_vid = (getattr(res, "media_type", None) == 2)
                        items_preview.append({
                            "index": idx + 1,
                            "type": "video" if r_is_vid else "image",
                            "thumbnail": r_thumb
                        })
                else:
                    items_preview = [{
                        "index": 1,
                        "type": "video" if is_video else "image",
                        "thumbnail": str(thumb or "")
                    }]

                audio_info = extract_audio_details(
                    m=m,
                    is_video=is_video,
                    creator=creator,
                    post_type=post_type
                )
                audio_status = audio_info.get("audio_status", "No audio detected")

                return [{
                    "id": str(m.code or pk),
                    "url": canonical_url,
                    "title": title,
                    "views": getattr(m, "view_count", 0) or 0,
                    "likes": getattr(m, "like_count", 0) or 0,
                    "thumbnail": thumb or "",
                    "creator": creator or "creator",
                    "media_type": m.media_type,
                    "is_video": is_video,
                    "post_type": post_type,
                    "item_count": len(items_preview),
                    "items_preview": items_preview,
                    "original_caption": caption_only,
                    "original_hashtags": original_hashtags,
                    "original_text": raw_caption,
                    "audio_status": audio_status,
                    "audio_info": audio_info
                }]
        except Exception as ig_err:
            print(f"[*] Note: instagrapi single post inspect fallback ({ig_err}). Trying yt-dlp...")

    # 2. For profiles or fallback, use yt-dlp
    if not is_single_item and not normalized_url.endswith("/reels/"):
        reels_url = normalized_url.rstrip("/") + "/reels/"
    else:
        reels_url = normalized_url

    ydl_opts = {
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'playlist_items': f"1-{limit}",
        'quiet': True,
        'no_warnings': True,
    }

    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(reels_url, download=False)
            
            entries = info.get('entries', []) if 'entries' in info else [info]
            for entry in entries:
                if not entry:
                    continue
                reel_id = entry.get('id') or "reel"
                url = f"https://www.instagram.com/reel/{reel_id}/"
                title = entry.get('title') or entry.get('description') or "No description"
                view_count = entry.get('view_count') or 0
                like_count = entry.get('like_count') or 0
                
                creator = entry.get('uploader') or entry.get('channel') or entry.get('creator') or entry.get('uploader_id') or ""
                if not creator:
                    m = re.search(r"instagram\.com/([^/?#]+)", profile_or_reel_url)
                    if m and m.group(1) not in ["reel", "reels", "p", "explore"]:
                        creator = m.group(1)

                a_info = extract_audio_details(entry=entry, is_video=True, creator=creator, post_type="reel")
                results.append({
                    "id": str(reel_id),
                    "url": url,
                    "title": title,
                    "views": view_count,
                    "likes": like_count,
                    "thumbnail": entry.get('thumbnail'),
                    "creator": creator,
                    "post_type": "reel",
                    "is_video": True,
                    "audio_status": a_info.get("audio_status", "Detected"),
                    "audio_info": a_info
                })

    except Exception as e:
        print(f"[!] Info: Direct flat extraction encountered ({e}). Falling back to single entry inspect.")
        # Single reel check
        try:
            with yt_dlp.YoutubeDL({'skip_download': True, 'quiet': True}) as ydl:
                info = ydl.extract_info(normalized_url, download=False)
                if info:
                    reel_id = info.get('id') or "single_reel"
                    web_url = info.get('webpage_url') or normalized_url
                    if not web_url.startswith("https://www.instagram.com/reel/") and not web_url.startswith("https://www.instagram.com/p/"):
                        web_url = f"https://www.instagram.com/reel/{reel_id}/"
                    creator = info.get('uploader') or info.get('channel') or info.get('creator') or info.get('uploader_id') or ""
                    a_info = extract_audio_details(entry=info, is_video=True, creator=creator, post_type="reel")
                    results.append({
                        "id": str(reel_id),
                        "url": web_url,
                        "title": info.get('title') or info.get('description') or "Reel",
                        "views": info.get('view_count') or 0,
                        "likes": info.get('like_count') or 0,
                        "thumbnail": info.get('thumbnail'),
                        "creator": creator,
                        "post_type": "reel",
                        "is_video": True,
                        "audio_status": a_info.get("audio_status", "Detected"),
                        "audio_info": a_info
                    })
        except Exception as err:
            print(f"[!] Extraction error: {err}")
            # If yt-dlp failed (e.g. "No video formats found"), try instagrapi as final fallback
            try:
                from account_manager import get_instagram_client, get_active_account
                cl = get_instagram_client(get_active_account())
                if cl:
                    pk = cl.media_pk_from_url(normalized_url)
                    m = cl.media_info(pk)
                    thumb = m.thumbnail_url or (m.resources[0].thumbnail_url if getattr(m, "resources", None) else "")
                    creator = m.user.username if getattr(m, "user", None) else "creator"
                    is_vid = (m.media_type == 2)
                    is_car = (m.media_type == 8)
                    pt = "carousel" if is_car else ("reel" if is_vid else "image")
                    a_info = extract_audio_details(m=m, is_video=is_vid, creator=creator, post_type=pt)
                    results.append({
                        "id": str(m.code or pk),
                        "url": f"https://www.instagram.com/p/{m.code}/",
                        "title": m.caption_text[:120] if m.caption_text else f"Post by @{creator}",
                        "views": getattr(m, "view_count", 0) or 0,
                        "likes": getattr(m, "like_count", 0) or 0,
                        "thumbnail": thumb or "",
                        "creator": creator,
                        "media_type": m.media_type,
                        "post_type": pt,
                        "is_video": is_vid,
                        "audio_status": a_info.get("audio_status", "No audio detected"),
                        "audio_info": a_info
                    })
            except Exception:
                pass

    # Sort candidates by views or likes descending
    results.sort(key=lambda x: (x.get('views') or 0, x.get('likes') or 0), reverse=True)
    return results
