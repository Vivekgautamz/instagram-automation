import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

IG_USER_ID = os.getenv("IG_USER_ID", "")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN", "")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")

def publish_reel_container(video_url: str, caption: str) -> dict:
    """
    Handles Instagram Reels API container creation, status polling, and publishing.
    """
    if not IG_USER_ID or not FB_ACCESS_TOKEN:
        return {
            "success": False,
            "error": "Missing IG_USER_ID or FB_ACCESS_TOKEN in .env file."
        }

    base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{IG_USER_ID}"

    # 1. Initialize Container
    print("\n[*] Initializing media upload container on Instagram...")
    container_payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": FB_ACCESS_TOKEN
    }
    try:
        res = requests.post(f"{base_url}/media", data=container_payload, timeout=20)
        data = res.json()
    except Exception as e:
        return {"success": False, "error": f"Request error: {e}"}

    if "id" not in data:
        return {"success": False, "error": f"Failed to initiate container: {data}"}

    container_id = data["id"]
    print(f"[*] Container created (ID: {container_id}). Uploading & processing on Instagram servers...")

    # 2. Status Polling
    status_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{container_id}"
    for attempt in range(40):
        time.sleep(5)
        try:
            status_res = requests.get(
                status_url,
                params={"fields": "status_code", "access_token": FB_ACCESS_TOKEN},
                timeout=15
            ).json()
            code = status_res.get("status_code")
            print(f"[*] Instagram processing status: {code} (check {attempt + 1})")
            if code == "FINISHED":
                break
            elif code in ["ERROR", "EXPIRED"]:
                return {"success": False, "error": f"Processing failed on Instagram: {status_res}"}
        except Exception as e:
            print(f"[*] Retry check due to network glitch: {e}")
    else:
        return {"success": False, "error": "Timeout waiting for Instagram to process the video."}

    # 3. Publish Container
    print("[*] Publishing reel live to your Instagram profile...")
    try:
        publish_res = requests.post(
            f"{base_url}/media_publish",
            data={"creation_id": container_id, "access_token": FB_ACCESS_TOKEN},
            timeout=20
        ).json()
        if "id" in publish_res:
            return {"success": True, "post_id": publish_res["id"]}
        else:
            return {"success": False, "error": f"Publish failed: {publish_res}"}
    except Exception as e:
        return {"success": False, "error": f"Publish request error: {e}"}
