import time
import requests
from config import IG_USER_ID, FB_ACCESS_TOKEN, GRAPH_API_VERSION

def publish_reel_to_instagram(video_url: str, caption: str) -> dict:
    """
    Publishes a Reel to your Instagram account using the Official Instagram Graph API.
    
    Requirements:
    1. IG_USER_ID (Instagram Business / Creator Account ID)
    2. FB_ACCESS_TOKEN (Access token with instagram_content_publish permission)
    3. video_url (Publicly accessible URL to the video file)
    """
    if not IG_USER_ID or not FB_ACCESS_TOKEN:
        return {
            "success": False,
            "error": "Missing IG_USER_ID or FB_ACCESS_TOKEN in .env. Please configure your Meta Graph API credentials."
        }

    base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{IG_USER_ID}"

    # Step 1: Create media container for REELS
    container_endpoint = f"{base_url}/media"
    container_params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": FB_ACCESS_TOKEN
    }

    print("[*] Creating Instagram Reels media container...")
    res = requests.post(container_endpoint, data=container_params)
    res_data = res.json()

    if "id" not in res_data:
        return {"success": False, "error": f"Failed to create media container: {res_data}"}

    creation_id = res_data["id"]
    print(f"[*] Container created with ID: {creation_id}. Waiting for processing...")

    # Step 2: Poll status of the container until FINISHED
    status_endpoint = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{creation_id}"
    status_params = {
        "fields": "status_code",
        "access_token": FB_ACCESS_TOKEN
    }

    max_retries = 30
    for _ in range(max_retries):
        time.sleep(4)
        status_res = requests.get(status_endpoint, params=status_params).json()
        code = status_res.get("status_code")
        print(f"[*] Processing status: {code}")
        if code == "FINISHED":
            break
        elif code in ["ERROR", "EXPIRED"]:
            return {"success": False, "error": f"Container processing ended with status: {code}"}
    else:
        return {"success": False, "error": "Timeout waiting for video processing on Instagram."}

    # Step 3: Publish container
    publish_endpoint = f"{base_url}/media_publish"
    publish_params = {
        "creation_id": creation_id,
        "access_token": FB_ACCESS_TOKEN
    }

    print("[*] Publishing reel to Instagram...")
    pub_res = requests.post(publish_endpoint, data=publish_params).json()

    if "id" in pub_res:
        return {"success": True, "media_id": pub_res["id"]}
    else:
        return {"success": False, "error": f"Publish failed: {pub_res}"}
