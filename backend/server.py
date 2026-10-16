"""
Instagram Automation Dashboard — Backend Server
Bridges the web frontend to existing Instagram automation scripts.
"""

import sys
import os
import json
import time
import shutil
import asyncio
import threading
import queue
import uuid
import glob
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# ── Project path setup ────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
sys.path.insert(0, PROJECT_DIR)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from account_manager import (
    get_instagram_client as _get_ig_client,
    get_active_account,
    set_active_account,
    list_accounts,
    verify_account_session,
    add_account,
    delete_account,
    login_account_direct,
    is_session_file_authenticated,
    create_account_session,
    verify_session,
    get_client_for_account,
    load_accounts_config,
    save_accounts_config,
    import_session_id,
    reconnect_account,
    import_session_json,
    get_pending_challenge,
    verify_otp_challenge,
    toggle_publishing,
    clean_username,
    get_session_path,
    BASE_DIR,
)

# ── Directories ───────────────────────────────────────────────────────────────
IMAGES_NEW = os.path.join(PROJECT_DIR, "images", "new")
IMAGES_POSTED = os.path.join(PROJECT_DIR, "images", "posted")
REELS_NEW = os.path.join(PROJECT_DIR, "reels", "new")
REELS_POSTED = os.path.join(PROJECT_DIR, "reels", "posted")
DOWNLOADS_DIR = os.path.join(PROJECT_DIR, "downloads")
HISTORY_FILE = os.path.join(PROJECT_DIR, "posting_history.json")
SETTINGS_FILE = os.path.join(PROJECT_DIR, "dashboard_settings.json")

for d in [IMAGES_NEW, IMAGES_POSTED, REELS_NEW, REELS_POSTED, DOWNLOADS_DIR]:
    os.makedirs(d, exist_ok=True)

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(title="Instagram Automation Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── WebSocket Manager ────────────────────────────────────────────────────────
class WSManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

ws_manager = WSManager()
log_queue: queue.Queue = queue.Queue()
event_loop = None

# ── Auto-post state ──────────────────────────────────────────────────────────
auto_post_state = {
    "running": False,
    "cancel": threading.Event(),
    "job_id": None,
    "progress": {},
    "thread": None,
}

# ── Helpers ───────────────────────────────────────────────────────────────────
# ── Media & Posting History Helpers ───────────────────────────────────────────
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm")
DEFAULT_IMAGE_HASHTAGS = "#photo #photography #instagood #instagram #instadaily #photooftheday #explore #picoftheday"


def scan_files(directory: str, extensions: tuple) -> list:
    """Scan a directory for files with given extensions, returning metadata."""
    results = []
    if not os.path.exists(directory):
        return results
    for fname in sorted(os.listdir(directory)):
        fpath = os.path.join(directory, fname)
        if os.path.isfile(fpath) and fname.lower().endswith(extensions):
            stat = os.stat(fpath)
            results.append({
                "filename": fname,
                "path": fpath,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return results


def load_history() -> list:
    """Load posting history from posting_history.json (supports both list or dict)."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "posts" in data:
                    return data["posts"]
                elif isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_history(history: list):
    """Save posting history to posting_history.json."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def add_history_entry(filename: str, media_type: str, account: str, url: str = "", caption: str = "", media_pk: str = ""):
    """Add a post record for (filename, account) to posting_history.json."""
    history = load_history()
    entry = {
        "media_id": filename,
        "filename": filename,
        "type": media_type,
        "account": account,
        "posted_at": datetime.now().isoformat(),
        "instagram_url": url,
        "caption": caption[:200] if caption else "",
        "media_pk": str(media_pk),
        "status": "posted",
    }
    # Check if duplicate entry already exists in history for same account
    existing = [h for h in history if (h.get("media_id") == filename or h.get("filename") == filename) and h.get("account") == account]
    if not existing:
        history.insert(0, entry)
        save_history(history)


def has_been_posted(filename: str, account: str) -> bool:
    """Check if the given media file has already been posted to the given account."""
    if not account or not filename:
        return False
    history = load_history()
    for h in history:
        fname = h.get("filename") or h.get("media_id")
        if fname == filename and h.get("account", "").lower() == account.lower():
            if h.get("status") in ["posted", "published"]:
                return True
    return False


def get_posted_accounts(filename: str) -> list:
    """Return a list of Instagram accounts that have successfully posted this media item."""
    if not filename:
        return []
    history = load_history()
    accounts = []
    for h in history:
        fname = h.get("filename") or h.get("media_id")
        if fname == filename and h.get("status") in ["posted", "published"]:
            acc = h.get("account")
            if acc and acc not in accounts:
                accounts.append(acc)
    return accounts


def find_media_file(filename: str) -> Optional[str]:
    """
    Search for physical media file across all library folders:
    1. images/new/ & reels/new/
    2. images/posted/ & reels/posted/
    3. downloads/
    If found in posted or downloads, copy it to new/ to keep it available.
    """
    clean_name = os.path.basename(filename)
    search_dirs = [
        IMAGES_NEW,
        REELS_NEW,
        IMAGES_POSTED,
        REELS_POSTED,
        DOWNLOADS_DIR,
    ]

    for d in search_dirs:
        candidate = os.path.join(d, clean_name)
        if os.path.isfile(candidate):
            ext = os.path.splitext(clean_name)[1].lower()
            target_new = IMAGES_NEW if ext in IMAGE_EXTS else REELS_NEW
            dest = os.path.join(target_new, clean_name)
            if not os.path.exists(dest):
                try:
                    shutil.copy2(candidate, dest)
                except Exception:
                    pass
            return candidate

    return None


def load_settings() -> dict:
    defaults = {
        "posting_delay": 30,
        "posting_order": "images_first",
        "auto_caption": True,
        "auto_hashtags": True,
        "duplicate_protection": True,
        "auto_archive": False,
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def emit_log(level: str, message: str, **extra):
    """Put a log message on the queue for WebSocket broadcast."""
    entry = {
        "type": "log",
        "level": level,
        "message": message,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        **extra,
    }
    log_queue.put(entry)


def emit_progress(current: int, total: int, filename: str, step: str, media_type: str):
    pct = int((current / total) * 100) if total > 0 else 0
    log_queue.put({
        "type": "progress",
        "current": current,
        "total": total,
        "percentage": pct,
        "filename": filename,
        "step": step,
        "media_type": media_type,
    })


# ── Background log broadcaster ───────────────────────────────────────────────
async def log_broadcaster():
    """Reads from log_queue and broadcasts to WebSocket clients."""
    while True:
        try:
            msg = log_queue.get_nowait()
            await ws_manager.broadcast(msg)
        except queue.Empty:
            pass
        await asyncio.sleep(0.1)


@app.on_event("startup")
async def startup():
    global event_loop
    event_loop = asyncio.get_event_loop()
    asyncio.create_task(log_broadcaster())


# ── Serve Frontend ────────────────────────────────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/style.css")
async def serve_style():
    return FileResponse(os.path.join(FRONTEND_DIR, "style.css"), media_type="text/css")


@app.get("/app.js")
async def serve_app_js():
    return FileResponse(os.path.join(FRONTEND_DIR, "app.js"), media_type="application/javascript")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/api/media/file/{media_type}/{subfolder}/{filename}")
async def serve_media_file(media_type: str, subfolder: str, filename: str):
    """Safely serve image/video files for frontend previews."""
    base = os.path.join(PROJECT_DIR, media_type, subfolder)
    fpath = os.path.join(base, filename)
    if not os.path.exists(fpath):
        fpath = find_media_file(filename)
    if not fpath or not os.path.exists(fpath):
        raise HTTPException(404, "File not found")
    return FileResponse(fpath)


# ── API: Account ──────────────────────────────────────────────────────────────
@app.get("/api/account")
async def api_account():
    active = get_active_account()
    accounts = list_accounts()
    return {"active": active, "accounts": [a["username"] for a in accounts]}


@app.get("/api/accounts")
async def api_accounts_list():
    """Return full detail for all registered accounts."""
    active = get_active_account()
    accounts = list_accounts()
    return {
        "active": active,
        "accounts": accounts
    }


@app.post("/api/account/switch")
async def api_switch_account(body: dict):
    username = (body.get("username") or "").strip().lstrip("@")
    if not username:
        raise HTTPException(400, "Username required")

    data = load_accounts_config()
    clean_u = clean_username(username).lower()
    accounts_map = {k.lower(): (k, v) for k, v in data.get("accounts", {}).items()}

    if clean_u not in accounts_map:
        raise HTTPException(404, f"Account @{username} is not registered in connected accounts.")

    orig_key, acc_info = accounts_map[clean_u]
    sess_file = acc_info.get("session_file")
    sess_path = os.path.normpath(os.path.join(BASE_DIR, sess_file)) if sess_file else get_session_path(orig_key)
    is_authenticated = is_session_file_authenticated(sess_path)
    current_status = acc_info.get("status", "connected" if is_authenticated else "session_expired")

    success = set_active_account(orig_key)
    if success:
        # Dynamically sync active Meta Graph API token and IG_USER_ID
        if acc_info.get("ig_user_id"):
            os.environ["IG_USER_ID"] = acc_info["ig_user_id"]
        if acc_info.get("meta_token"):
            os.environ["FB_ACCESS_TOKEN"] = acc_info["meta_token"]

        emit_log("info", f"Switched active Instagram account to @{orig_key}")
        return {
            "status": "ok",
            "active": orig_key,
            "is_authenticated": is_authenticated,
            "account_status": current_status,
            "warning": None if is_authenticated else f"Session for @{orig_key} is expired or requires reauthentication."
        }
    raise HTTPException(400, f"Could not switch to @{orig_key}")


@app.post("/api/account/verify")
async def api_account_verify(body: dict):
    """Verify that the session for a username is valid and live on Instagram."""
    username = (body.get("username") or "").strip().lstrip("@")
    session_file = (body.get("session_file") or "").strip() or None
    if not username:
        raise HTTPException(400, "Username required")
    result = verify_account_session(username, session_file)

    # Persist updated status in accounts.json
    try:
        data = load_accounts_config()
        clean_u = username.lower()
        if clean_u in data.get("accounts", {}):
            if result.get("status") == "publishing_restricted":
                data["accounts"][clean_u]["status"] = "publishing_restricted"
                save_accounts_config(data)
            elif result.get("valid"):
                data["accounts"][clean_u]["status"] = "connected"
                save_accounts_config(data)
            elif result.get("status") in ("session_mismatch", "session_expired", "not_authenticated"):
                data["accounts"][clean_u]["status"] = result.get("status")
                save_accounts_config(data)
    except Exception:
        pass

    return result


@app.post("/api/account/connect")
async def api_account_connect(body: dict):
    """
    Verify & Connect flow:
    Verifies actual authenticated username, registers in accounts.json (without passwords),
    and optionally sets as active.
    """
    username = (body.get("username") or "").strip().lstrip("@")
    display_name = (body.get("display_name") or "").strip()
    session_file = (body.get("session_file") or "").strip() or None
    set_active = bool(body.get("set_active", False))

    if not username:
        raise HTTPException(400, "Username required")

    # 1. Verify session/login status
    verify_res = verify_account_session(username, session_file)
    if not verify_res.get("valid"):
        return {
            "status": verify_res.get("status", "error"),
            "connected": False,
            "valid": False,
            "message": verify_res.get("message", "Session verification failed.")
        }

    # 2. Use the actual authenticated Instagram username
    actual_username = verify_res.get("actual_username") or username
    target_session = verify_res.get("session_file") or f"sessions/{actual_username}.json"

    # 3. Add to accounts.json (NEVER saves password)
    acc = add_account(
        username=actual_username,
        display_name=display_name or actual_username,
        session_file=target_session,
        set_active=set_active
    )
    emit_log("success", f"Account @{actual_username} connected successfully{' and set as active' if set_active else ''}")
    return {
        "status": "connected",
        "connected": True,
        "valid": True,
        "username": actual_username,
        "actual_username": actual_username,
        "display_name": acc.get("display_name", actual_username),
        "session_file": target_session,
        "is_active": acc.get("is_active", False),
        "user_id": verify_res.get("user_id"),
        "message": f"Successfully connected @{actual_username}!"
    }


@app.post("/api/account/login")
async def api_account_login(body: dict):
    """
    Authenticates with Instagram using password and optional 2FA code.
    Generates encrypted session, registers in accounts.json without storing password.
    """
    username = (body.get("username") or "").strip().lstrip("@")
    password = body.get("password") or ""
    verification_code = (body.get("verification_code") or "").strip() or None
    display_name = (body.get("display_name") or "").strip()
    set_active = bool(body.get("set_active", False))

    if not username:
        raise HTTPException(400, "Username required")
    if not password:
        raise HTTPException(400, "Password required")

    res = login_account_direct(
        username=username,
        password=password,
        verification_code=verification_code,
        display_name=display_name or None,
        set_active=set_active
    )
    if res.get("valid"):
        emit_log("success", f"Successfully logged in and connected @{res['actual_username']}")
    return res


@app.put("/api/accounts/{username}/session")
@app.post("/api/accounts/{username}/session")
@app.post("/api/accounts/{username}/session-id")
@app.post("/api/account/{username}/session")
async def api_account_import_session(username: str, body: dict):
    """
    Secure session ID import:
    Accepts session ID, validates against Instagram using an isolated Client,
    strictly confirms authenticated user matches the requested username,
    and stores solely to that account's session file (e.g. sessions/gautammmmm20.json).
    NEVER logs or exposes the session ID.
    """
    clean = username.strip().lstrip("@")
    sessionid = (body.get("sessionid") or body.get("session_id") or "").strip()
    if not clean:
        raise HTTPException(status_code=400, detail="Username required")
    if not sessionid:
        raise HTTPException(status_code=400, detail="Enter your session ID.")

    result = import_session_id(clean, sessionid)
    if not result.get("valid"):
        detail_msg = result.get("message") or "Session verification failed."
        raise HTTPException(status_code=400, detail=detail_msg)

    emit_log("success", f"Session ID verified and saved for @{clean}")
    return result


@app.post("/api/accounts/{username}/reconnect")
@app.post("/api/account/{username}/reconnect")
async def api_account_reconnect(username: str, body: dict):
    """
    Secure reauthentication flow:
    Supports password and 2FA verification challenge for an existing account.
    Verifies actual authenticated identity, saves to account-specific session file,
    and updates account status to connected.
    NEVER stores or logs credentials.
    """
    clean = username.strip().lstrip("@")
    password = body.get("password") or ""
    verification_code = (body.get("verification_code") or "").strip() or None

    if not clean:
        raise HTTPException(status_code=400, detail="Username required")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required to reconnect.")

    result = reconnect_account(clean, password, verification_code)
    if result.get("valid"):
        emit_log("success", f"Successfully reconnected @{result.get('actual_username', clean)}")
    return result


@app.get("/api/accounts/{username}/challenge-status")
async def api_account_challenge_status(username: str):
    """Returns active pending 2FA challenge status for the requested account."""
    clean = username.strip().lstrip("@")
    status = get_pending_challenge(clean)
    return {"status": "ok", "challenge": status}


@app.post("/api/accounts/verify-otp")
@app.post("/api/accounts/{username}/verify-otp")
async def api_account_verify_otp(body: dict, username: Optional[str] = None):
    """
    Verifies 6-digit OTP/2FA code against a pending login challenge.
    Never exposes passwords or OTP in logs.
    """
    clean = (username or body.get("username") or "").strip().lstrip("@")
    code = (body.get("verification_code") or body.get("code") or "").strip()
    password = body.get("password") or None

    if not clean:
        raise HTTPException(status_code=400, detail="Username required")
    if not code:
        raise HTTPException(status_code=400, detail="6-digit verification code required")

    result = verify_otp_challenge(clean, code, password)
    if not result.get("valid"):
        raise HTTPException(status_code=400, detail=result.get("message", "OTP verification failed"))

    emit_log("success", f"OTP verified and session created for @{result.get('actual_username', clean)}")
    return result


@app.post("/api/accounts/{username}/session-json")
@app.put("/api/accounts/{username}/session-json")
async def api_account_import_session_json(username: str, body: dict):
    """
    Imports raw session JSON dictionary/settings, verifies against Instagram,
    and saves to account session file.
    """
    clean = username.strip().lstrip("@")
    session_json = body.get("session_json") or body.get("settings") or body
    set_active = bool(body.get("set_active", False))

    if not clean:
        raise HTTPException(status_code=400, detail="Username required")

    result = import_session_json(clean, session_json, set_active=set_active)
    if not result.get("valid"):
        raise HTTPException(status_code=400, detail=result.get("message", "Session JSON invalid"))

    emit_log("success", f"Session JSON verified and saved for @{clean}")
    return result


@app.post("/api/accounts/{username}/toggle-publishing")
async def api_account_toggle_publishing(username: str, body: Optional[dict] = None):
    """Toggles or sets the publishing status (Enabled / Paused) for an account."""
    clean = username.strip().lstrip("@")
    enabled = body.get("enabled") if body else None
    result = toggle_publishing(clean, enabled)
    if result.get("status") != "ok":
        raise HTTPException(status_code=404, detail=result.get("message", "Account not found"))
    return result


@app.get("/api/meta-oauth-info")
async def api_meta_oauth_info():
    """Returns Meta developer configuration for Graph API integration."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJECT_DIR, ".env"), override=True)
    except Exception:
        pass

    data = load_accounts_config()
    active_user = get_active_account()
    acc_info = data.get("accounts", {}).get(active_user, {}) if active_user else {}

    token = acc_info.get("meta_token") or os.getenv("FB_ACCESS_TOKEN", "").strip()
    ig_user_id = acc_info.get("ig_user_id") or os.getenv("IG_USER_ID", "").strip()

    meta_accounts = []
    for uname, uinfo in data.get("accounts", {}).items():
        if uinfo.get("meta_token") and uinfo.get("ig_user_id"):
            tok = uinfo["meta_token"]
            meta_accounts.append({
                "username": uname,
                "display_name": uinfo.get("display_name", uname),
                "ig_user_id": uinfo.get("ig_user_id"),
                "token_preview": f"{tok[:12]}...{tok[-8:]}",
                "is_active": (uname == active_user)
            })

    return {
        "app_id": "1063180003141134",
        "has_token": bool(token),
        "active_account": active_user,
        "ig_user_id": ig_user_id,
        "token_preview": f"{token[:12]}...{token[-8:]}" if len(token) > 20 else "",
        "valid": bool(token and ig_user_id),
        "accounts": meta_accounts,
        "oauth_url": "https://www.facebook.com/v19.0/dialog/oauth?client_id=1063180003141134&redirect_uri=https://localhost:8501/auth/callback&scope=instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement"
    }


@app.post("/api/accounts/add")
@app.post("/api/account/add")
async def api_account_add(body: dict):
    """
    Dedicated Add Account flow:
    Creates a dedicated, fresh session context for the new account (never copies another session),
    checks whether it is already authenticated, and registers it in accounts.json.
    """
    username = (body.get("username") or "").strip().lstrip("@").lower()
    display_name = (body.get("display_name") or "").strip()
    set_active = bool(body.get("set_active", False))

    if not username:
        raise HTTPException(400, "Username required")

    # IMPORTANT: Fresh isolated Client and session path for this account
    client, session_file = create_account_session(username)
    rel_session = f"sessions/{username}.json"

    sess_exists = os.path.exists(session_file)
    is_auth = is_session_file_authenticated(session_file) if sess_exists else False

    status = "connected" if is_auth else "authentication_required"

    try:
        result = add_account(
            username=username,
            display_name=display_name or username,
            session_file=rel_session,
            status=status,
            set_active=set_active
        )
        emit_log("info" if not is_auth else "success", f"Account @{username} registered ({status})")
        return {
            "status": status,
            "username": username,
            "session_file": rel_session,
            "display_name": display_name or username,
            "is_active": result.get("is_active", False),
            "message": f"Account @{username} registered. Authentication required." if not is_auth else f"Account @{username} connected successfully."
        }
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/account/{username}")
async def api_account_delete(username: str):
    """Remove an account from accounts.json configuration without deleting session or Instagram account."""
    clean = username.strip().lstrip("@")
    if not clean:
        raise HTTPException(400, "Username required")
    ok = delete_account(clean)
    if ok:
        emit_log("info", f"Account @{clean} removed from dashboard configuration")
        return {"status": "ok", "removed": clean}
    raise HTTPException(404, f"Account @{clean} not found")


# ── API: Stats ────────────────────────────────────────────────────────────────
@app.get("/api/stats")
async def api_stats(account: str = None):
    target_user = account or get_active_account()
    images_new = scan_files(IMAGES_NEW, IMAGE_EXTS)
    reels_new = scan_files(REELS_NEW, VIDEO_EXTS)
    images_posted = scan_files(IMAGES_POSTED, IMAGE_EXTS)
    reels_posted = scan_files(REELS_POSTED, VIDEO_EXTS)
    history = load_history()
    failed = sum(1 for h in history if h.get("status") == "failed" and (not target_user or h.get("account") == target_user))
    
    # Active/target account specific stats
    account_posts = [h for h in history if h.get("account") == target_user and h.get("status") in ["posted", "published"]]
    
    # Ready (unposted to this account) counts
    images_ready = [img for img in images_new if not has_been_posted(img["filename"], target_user)]
    reels_ready = [reel for reel in reels_new if not has_been_posted(reel["filename"], target_user)]
    
    return {
        "images_waiting": len(images_ready),
        "reels_waiting": len(reels_ready),
        "images_posted": len([p for p in account_posts if p.get("type") == "image"]),
        "reels_posted": len([p for p in account_posts if p.get("type") == "reel"]),
        "total_images_in_library": len(images_new),
        "total_reels_in_library": len(reels_new),
        "failed": failed,
        "total_posted": len(account_posts),
        "active_account": target_user
    }


# ── API: Media Listing & Unified Queue ───────────────────────────────────────
@app.get("/api/queue")
async def api_get_queue():
    from bot_service import format_size
    active_user = get_active_account()

    def resolve_media_location(filename: str, media_type: str):
        if media_type == "image":
            possible_paths = [
                os.path.join(IMAGES_NEW, filename),
                os.path.join(IMAGES_POSTED, filename),
            ]
        else:
            possible_paths = [
                os.path.join(REELS_NEW, filename),
                os.path.join(REELS_POSTED, filename),
            ]
        
        found_abs = None
        for p in possible_paths:
            if os.path.exists(p):
                found_abs = p
                break
        
        if not found_abs:
            found_abs = find_media_file(filename)

        if found_abs:
            rel = os.path.relpath(found_abs, PROJECT_DIR).replace("\\", "/")
            return {
                "local_path": rel,
                "full_path": os.path.abspath(found_abs),
                "exists": True
            }
        else:
            default_rel = f"images/new/{filename}" if media_type == "image" else f"reels/new/{filename}"
            return {
                "local_path": default_rel,
                "full_path": os.path.abspath(os.path.join(PROJECT_DIR, default_rel)),
                "exists": False
            }

    images = []
    for f in scan_files(IMAGES_NEW, IMAGE_EXTS):
        posted_accs = get_posted_accounts(f["filename"])
        is_posted = has_been_posted(f["filename"], active_user)
        loc = resolve_media_location(f["filename"], "image")
        images.append({
            "id": f["filename"],
            "filename": f["filename"],
            "media_type": "image",
            "size": f["size"],
            "size_formatted": format_size(f["size"]),
            "modified": f["modified"],
            "preview_url": f"/api/media/file/images/new/{f['filename']}",
            "local_path": loc["local_path"],
            "full_path": loc["full_path"],
            "file_exists": loc["exists"],
            "posted_accounts": posted_accs,
            "is_posted_for_active": is_posted,
            "status": "posted" if is_posted else "ready",
            "status_label": f"✓ Posted to @{active_user}" if is_posted else f"Ready for @{active_user}"
        })

    reels = []
    for f in scan_files(REELS_NEW, VIDEO_EXTS):
        posted_accs = get_posted_accounts(f["filename"])
        is_posted = has_been_posted(f["filename"], active_user)
        loc = resolve_media_location(f["filename"], "reel")
        reels.append({
            "id": f["filename"],
            "filename": f["filename"],
            "media_type": "reel",
            "size": f["size"],
            "size_formatted": format_size(f["size"]),
            "modified": f["modified"],
            "preview_url": f"/api/media/file/reels/new/{f['filename']}",
            "local_path": loc["local_path"],
            "full_path": loc["full_path"],
            "file_exists": loc["exists"],
            "posted_accounts": posted_accs,
            "is_posted_for_active": is_posted,
            "status": "posted" if is_posted else "ready",
            "status_label": f"✓ Posted to @{active_user}" if is_posted else f"Ready for @{active_user}"
        })

    all_items = images + reels
    all_items.sort(key=lambda x: x["modified"], reverse=True)

    return {
        "images": images,
        "reels": reels,
        "items": all_items,
        "total": len(all_items),
        "active_account": active_user
    }


@app.get("/api/media/images")
async def api_images():
    return {"files": scan_files(IMAGES_NEW, IMAGE_EXTS)}


@app.get("/api/media/reels")
async def api_reels():
    return {"files": scan_files(REELS_NEW, VIDEO_EXTS)}


@app.get("/api/media/posted")
async def api_posted():
    history = load_history()
    return {"history": history[:200]}


# ── Duplicate Protection Helper ───────────────────────────────────────────────
def get_unique_filename(filename: str, media_type: str) -> str:
    """
    Checks if filename already exists in images/new or reels/new.
    Returns a unique filename if it already exists (e.g. photo_1.jpg).
    """
    clean_name = os.path.basename(filename)
    base_name, ext = os.path.splitext(clean_name)
    ext = ext.lower()

    folders = [IMAGES_NEW, REELS_NEW]
    candidate = f"{base_name}{ext}"
    counter = 1

    def exists_anywhere(name):
        for fld in folders:
            if os.path.exists(os.path.join(fld, name)):
                return True
        return False

    while exists_anywhere(candidate):
        candidate = f"{base_name}_{counter}{ext}"
        counter += 1

    return candidate


# ── API: Upload Files (Unified Multi-file Support) ───────────────────────────
@app.post("/api/upload")
async def api_upload_unified(file: UploadFile = File(...)):
    orig_filename = os.path.basename(file.filename)
    ext = os.path.splitext(orig_filename)[1].lower()

    if ext in IMAGE_EXTS:
        media_type = "image"
        target_dir = IMAGES_NEW
    elif ext in VIDEO_EXTS:
        media_type = "reel"
        target_dir = REELS_NEW
    else:
        raise HTTPException(
            400,
            f"Unsupported file extension '{ext}'. Allowed: {', '.join(IMAGE_EXTS + VIDEO_EXTS)}"
        )

    safe_filename = get_unique_filename(orig_filename, media_type)
    dest_path = os.path.join(target_dir, safe_filename)

    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    file_size = len(content)
    from bot_service import format_size
    size_str = format_size(file_size)

    emit_log("success", f"Uploaded {safe_filename} ({size_str}) -> {media_type}s/new/")

    return {
        "success": True,
        "filename": safe_filename,
        "original_filename": orig_filename,
        "media_type": media_type,
        "size": file_size,
        "size_formatted": size_str,
        "status": "ready"
    }


@app.post("/api/upload/image")
async def api_upload_image(file: UploadFile = File(...)):
    return await api_upload_unified(file)


@app.post("/api/upload/reel")
async def api_upload_reel(file: UploadFile = File(...)):
    return await api_upload_unified(file)


# ── API: Post Single Image/Reel from Queue ────────────────────────────────────
@app.post("/api/post/image")
async def api_post_image(body: dict):
    filename = body.get("media_id") or body.get("filename")
    caption = body.get("caption")
    hashtags = body.get("hashtags")
    if not filename:
        raise HTTPException(400, "media_id / filename required")

    fpath = find_media_file(filename)
    if not fpath or not os.path.exists(fpath):
        raise HTTPException(404, f"Media file not found: {filename}")

    active = get_active_account()
    if has_been_posted(filename, active):
        raise HTTPException(400, f"Image {filename} has already been posted to @{active}")

    def _post():
        emit_log("info", f"[*] Preparing to post image {filename} to @{active}...")
        cl = _get_ig_client(active, verify=True)
        if not cl:
            emit_log("error", f"[!] Authentication / Account mismatch for @{active}. Posting aborted.")
            return

        emit_log("info", f"[*] Generating caption & hashtags for {filename}...")
        cap = caption if caption else "Words from the heart. ✨"
        tags = hashtags if hashtags else DEFAULT_IMAGE_HASHTAGS
        full_caption = f"{cap}\n\n{tags}".strip()

        emit_log("info", f"[*] Uploading image {filename} to @{active}...")
        try:
            media = cl.photo_upload(path=Path(fpath), caption=full_caption)
            post_url = f"https://www.instagram.com/p/{media.code}/"
            emit_log("success", f"[✓] Published successfully: {post_url}")
            
            # Archive a copy in images/posted/ for records, but KEEP original in images/new/
            dest = os.path.join(IMAGES_POSTED, filename)
            if not os.path.exists(dest):
                try:
                    shutil.copy2(fpath, dest)
                except Exception:
                    pass

            add_history_entry(filename, "image", active, post_url, full_caption, media.pk)
        except Exception as e:
            err = str(e)
            if "restrict" in err.lower() or "feedback_required" in err.lower():
                emit_log("error", f"[⚠️] PUBLISHING RESTRICTED by Instagram for @{active}: {err}")
            else:
                emit_log("error", f"[!] Failed to post {filename}: {err}")

    threading.Thread(target=_post, daemon=True).start()
    return {"status": "started", "filename": filename, "account": active}


@app.post("/api/post/reel")
async def api_post_reel(body: dict):
    filename = body.get("media_id") or body.get("filename")
    caption = body.get("caption")
    hashtags = body.get("hashtags")
    if not filename:
        raise HTTPException(400, "media_id / filename required")

    fpath = find_media_file(filename)
    if not fpath or not os.path.exists(fpath):
        raise HTTPException(404, f"Media file not found: {filename}")

    active = get_active_account()
    if has_been_posted(filename, active):
        raise HTTPException(400, f"Reel {filename} has already been posted to @{active}")

    def _post():
        emit_log("info", f"[*] Preparing to post Reel {filename} to @{active}...")
        cl = _get_ig_client(active, verify=True)
        if not cl:
            emit_log("error", f"[!] Authentication / Account mismatch for @{active}. Posting aborted.")
            return

        emit_log("info", f"[*] Analyzing video content & generating AI caption for {filename}...")
        if not caption or not hashtags:
            try:
                from caption_ai import generate_reel_content
                ai_meta = generate_reel_content(fpath)
                cap = caption if caption else ai_meta.get("caption", "Words from the heart. ✨")
                tags = hashtags if hashtags else ai_meta.get("hashtags", DEFAULT_IMAGE_HASHTAGS)
            except Exception:
                cap = caption if caption else "🎬"
                tags = hashtags if hashtags else DEFAULT_IMAGE_HASHTAGS
        else:
            cap = caption
            tags = hashtags

        full_caption = f"{cap}\n\n{tags}".strip()
        emit_log("info", f"[*] Uploading Reel {filename} to @{active}...")
        try:
            from post_reel_direct import ensure_thumbnail
            thumb = ensure_thumbnail(fpath)
            kwargs = {"path": Path(fpath), "caption": full_caption}
            if thumb and os.path.exists(thumb):
                kwargs["thumbnail"] = Path(thumb)
            media = cl.clip_upload(**kwargs)
            post_url = f"https://www.instagram.com/reel/{media.code}/"
            emit_log("success", f"[✓] Published successfully: {post_url}")
            
            # Archive a copy in reels/posted/ for records, but KEEP original in reels/new/
            dest = os.path.join(REELS_POSTED, filename)
            if not os.path.exists(dest):
                try:
                    shutil.copy2(fpath, dest)
                except Exception:
                    pass
            if thumb and os.path.exists(thumb):
                thumb_dest = os.path.join(REELS_POSTED, os.path.basename(thumb))
                if not os.path.exists(thumb_dest):
                    try:
                        shutil.copy2(thumb, thumb_dest)
                    except Exception:
                        pass

            add_history_entry(filename, "reel", active, post_url, full_caption, media.pk)
            
            # Also update SQLite DB for reels
            try:
                import database
                reel_id = os.path.splitext(filename)[0]
                database.mark_published(reel_id, post_url, account=active)
            except Exception:
                pass
        except Exception as e:
            err = str(e)
            if "restrict" in err.lower() or "feedback_required" in err.lower():
                emit_log("error", f"[⚠️] PUBLISHING RESTRICTED by Instagram for @{active}: {err}")
            else:
                emit_log("error", f"[!] Failed to post {filename}: {err}")

    threading.Thread(target=_post, daemon=True).start()
    return {"status": "started", "filename": filename, "account": active}


# ── API: Download ─────────────────────────────────────────────────────────────
@app.post("/api/download")
async def api_download(body: dict):
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(400, "URL required")

    def _download():
        emit_log("info", f"Starting download: {url}")
        try:
            from downloader import download_reel
            local_file = download_reel(url)
            fname = os.path.basename(local_file)
            emit_log("success", f"Downloaded: {fname}")

            ext = os.path.splitext(fname)[1].lower()
            is_image = ext in IMAGE_EXTS
            dest_dir = IMAGES_NEW if is_image else REELS_NEW
            folder_desc = "images/new" if is_image else "reels/new"

            dest = os.path.join(dest_dir, fname)
            if os.path.abspath(local_file) != os.path.abspath(dest):
                shutil.copy2(local_file, dest)
            emit_log("info", f"Ready in {folder_desc}/{fname}")

            # If album/carousel, also copy any sibling files from downloads
            dl_dir = os.path.dirname(local_file)
            prefix = fname.split("_")[0]
            extra_count = 0
            for item in os.listdir(dl_dir):
                if item != fname and prefix and prefix in item:
                    item_path = os.path.join(dl_dir, item)
                    iext = os.path.splitext(item)[1].lower()
                    if iext in IMAGE_EXTS:
                        idest = os.path.join(IMAGES_NEW, item)
                        if not os.path.exists(idest):
                            shutil.copy2(item_path, idest)
                            extra_count += 1
            if extra_count > 0:
                emit_log("info", f"Saved {extra_count} additional carousel photo(s) to images/new/")
        except Exception as e:
            emit_log("error", f"Download failed: {e}")

    threading.Thread(target=_download, daemon=True).start()
    return {"status": "started"}


# ── API: Interactive Bot ──────────────────────────────────────────────────────
bot_jobs = {}

def add_bot_log(job: dict, message: str, level: str = "info"):
    entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "message": message,
        "level": level
    }
    job.setdefault("logs", []).append(entry)
    emit_log(level, message)


@app.post("/api/bot/analyze")
async def api_bot_analyze(body: dict):
    url = body.get("url", "").strip()
    account = body.get("account", "").strip()
    if not url:
        raise HTTPException(400, "Instagram Profile or Reel/Post URL is required")

    job_id = str(uuid.uuid4())[:8]
    auto_post = bool(body.get("auto_post", False))
    job = {
        "job_id": job_id,
        "url": url,
        "mode": body.get("mode", "repost_as_is"),
        "account": account or get_active_account(),
        "auto_post": auto_post,
        "status": "analyzing",
        "step": "url_received",
        "progress": 20,
        "message": "URL received",
        "error": None,
        "candidate": None,
        "download": None,
        "analysis": None,
        "publish": None,
        "logs": []
    }
    bot_jobs[job_id] = job
    add_bot_log(job, f"URL received ({'Automatic Auto-Post' if auto_post else 'Manual Review'} Mode)")

    def _run_analyze():
        try:
            add_bot_log(job, "Searching Instagram content...")
            job["step"] = "searching"
            job["progress"] = 35

            from bot_service import analyze_reel
            res = analyze_reel(url, limit=5, account=job["account"])
            candidate = res["top_candidate"]
            job["candidate"] = candidate
            type_label = candidate.get("post_type", "content").capitalize()
            item_info = f" ({candidate.get('item_count', 1)} items)" if candidate.get("post_type") == "carousel" else ""
            add_bot_log(job, f"{type_label} found{item_info}: {candidate['url']} (Likes: {candidate['likes_formatted']})", "success")

            from bot_service import is_source_already_posted
            reel_id = candidate.get("id") or ""
            target_acc = job["account"]

            if auto_post and reel_id and is_source_already_posted(reel_id, target_acc):
                err = f"Content was already published to @{target_acc}. Duplicate skipped."
                job["status"] = "failed"
                job["error"] = err
                add_bot_log(job, f"⚠️ Duplicate prevention: {err}", "warning")
                return

            job["status"] = "downloading"
            job["step"] = "downloading"
            job["progress"] = 65
            add_bot_log(job, f"{'Auto-mode' if auto_post else 'Manual-mode'}: Downloading original media (preserving order & audio)...")

            from bot_service import download_candidate, publish_bot_content
            dl_info = download_candidate(candidate["url"], custom_id=candidate["id"], source_candidate=candidate)
            job["download"] = dl_info

            count_str = f" ({dl_info.get('item_count', 1)} items in original order)" if dl_info.get("post_type") == "carousel" else ""
            add_bot_log(job, f"Downloaded{count_str}: {dl_info['filename']} ({dl_info.get('size_formatted', '')})", "success")

            # Preserve exact original caption & hashtags
            orig_cap = candidate.get("original_caption", "")
            orig_hash = candidate.get("original_hashtags", "")
            full_text = f"{orig_cap}\n\n{orig_hash}".strip() if (orig_cap and orig_hash) else (orig_cap or orig_hash)
            job["analysis"] = {
                "status": "as_is",
                "caption": orig_cap,
                "hashtags": orig_hash,
                "full": full_text,
                "is_repost_as_is": True
            }

            if not auto_post:
                # Manual mode: Media & metadata downloaded, ready for user review & edits
                job["status"] = "ready_to_publish"
                job["step"] = "ready_to_publish"
                job["progress"] = 75
                add_bot_log(job, "✓ Ready for review: media downloaded, caption and audio checked. Edit details or click Publish when ready.", "info")
                return

            # ── AUTOMATIC MODE: Proceed directly to publishing ──────────────
            job["status"] = "publishing"
            job["step"] = "publishing"
            job["progress"] = 85
            add_bot_log(job, f"Auto-mode: Publishing to @{target_acc}...")

            media_files = dl_info.get("media_files") or [dl_info["new_reel_path"]]
            post_type = dl_info.get("post_type", candidate.get("post_type", "reel"))

            pub_res = publish_bot_content(
                media_files=media_files,
                caption=orig_cap,
                hashtags=orig_hash,
                target_account=target_acc,
                post_type=post_type,
                mode="repost_as_is",
                reel_id=reel_id,
                original_url=candidate.get("url", ""),
                audio_status=dl_info.get("audio_status", candidate.get("audio_status", "")),
                force=False
            )
            job["status"] = "published"
            job["step"] = "published"
            job["progress"] = 100
            job["publish"] = pub_res
            add_bot_log(job, f"✓ {type_label.upper()} PUBLISHED SUCCESSFULLY: {pub_res.get('instagram_url')}", "success")

        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)
            add_bot_log(job, f"Process failed: {e}", "error")

    threading.Thread(target=_run_analyze, daemon=True).start()
    return {"status": "started", "job_id": job_id}


@app.get("/api/bot/status/{job_id}")
async def api_bot_status(job_id: str):
    job = bot_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job_id,
        "status": job["status"],
        "step": job["step"],
        "progress": job["progress"],
        "message": job["message"],
        "error": job["error"],
        "logs": job["logs"]
    }


@app.get("/api/bot/result/{job_id}")
async def api_bot_result(job_id: str):
    job = bot_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job_id,
        "candidate": job.get("candidate"),
        "download": job.get("download"),
        "analysis": job.get("analysis"),
        "publish": job.get("publish"),
        "status": job["status"],
        "step": job["step"],
        "error": job["error"],
        "logs": job["logs"],
        "mode": job.get("mode", "repost_as_is")
    }


@app.post("/api/bot/download/{job_id}")
async def api_bot_download(job_id: str, body: dict = None):
    job = bot_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    candidate = job.get("candidate")
    if not candidate:
        raise HTTPException(400, "No candidate available to download")

    mode = (body.get("mode") if body else None) or job.get("mode", "repost_as_is")
    job["mode"] = mode

    def _run_download_and_analyze():
        try:
            job["status"] = "downloading"
            job["step"] = "downloading"
            job["progress"] = 65
            post_type = candidate.get("post_type", "media")
            add_bot_log(job, f"Downloading original {post_type}: {candidate['url']} (Preserving watermarks/media as-is)...")

            from bot_service import download_candidate, analyze_video
            dl_info = download_candidate(candidate["url"], custom_id=candidate["id"], source_candidate=candidate)
            job["download"] = dl_info

            count_str = f" ({dl_info.get('item_count', 1)} items in original order)" if dl_info.get("post_type") == "carousel" else ""
            add_bot_log(job, f"Original media downloaded{count_str}: {dl_info['filename']} ({dl_info['size_formatted']})", "success")

            a_info = dl_info.get("audio_info", {})
            if a_info.get("detected"):
                track_str = f" — {a_info.get('track_name')}" if a_info.get('track_name') else ""
                add_bot_log(job, f"Audio Track: {dl_info.get('audio_status', 'Detected')}{track_str}", "info")
            else:
                add_bot_log(job, "Audio Track: No audio detected on source", "info")

            if mode == "repost_as_is":
                # In Repost As-Is mode: do NOT rewrite with AI. Directly copy original caption & hashtags.
                orig_cap = candidate.get("original_caption", "")
                orig_hash = candidate.get("original_hashtags", "")
                full_text = f"{orig_cap}\n\n{orig_hash}".strip() if (orig_cap and orig_hash) else (orig_cap or orig_hash)
                
                job["analysis"] = {
                    "status": "as_is",
                    "caption": orig_cap,
                    "hashtags": orig_hash,
                    "full": full_text,
                    "topic": "Original Content",
                    "visual_available": True,
                    "is_repost_as_is": True
                }
                job["step"] = "ready_to_publish"
                job["status"] = "ready_to_publish"
                job["progress"] = 100
                add_bot_log(job, "✓ Original caption and hashtags preserved as-is. Ready to repost!", "success")

            else:
                # In AI Generate mode: run AI analysis
                job["status"] = "analyzing_video"
                job["step"] = "analyzing_video"
                job["progress"] = 80
                add_bot_log(job, f"Analyzing media content for {dl_info['filename']}...")

                job["step"] = "generating_caption"
                job["progress"] = 90
                add_bot_log(job, "Generating AI caption & hashtags...")

                analysis = analyze_video(dl_info["new_reel_path"], context_hint=candidate.get("title", ""))
                job["analysis"] = analysis

                job["step"] = "ready_to_publish"
                job["status"] = "ready_to_publish"
                job["progress"] = 100
                add_bot_log(job, "Ready to publish content!", "success")

        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)
            add_bot_log(job, f"Download/Processing failed: {e}", "error")

    threading.Thread(target=_run_download_and_analyze, daemon=True).start()
    return {"status": "started", "job_id": job_id}


@app.post("/api/bot/publish/{job_id}")
async def api_bot_publish(job_id: str, body: dict = None):
    job = bot_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    dl_info = job.get("download")
    analysis = job.get("analysis")
    candidate = job.get("candidate")
    if not dl_info or not analysis:
        raise HTTPException(400, "Media or content not ready for publishing")

    caption = (body.get("caption") if body else "") or analysis.get("caption", "")
    hashtags = (body.get("hashtags") if body else "") or analysis.get("hashtags", "")
    mode = (body.get("mode") if body else None) or job.get("mode", "repost_as_is")
    force = bool(body.get("force", False)) if body else False

    target_account = (body.get("account") if body else "") or job.get("account") or get_active_account()

    job["status"] = "publishing"
    job["step"] = "publishing"
    add_bot_log(job, f"Verifying account @{target_account} session...")

    from bot_service import publish_bot_content, is_source_already_posted
    reel_id = candidate.get("id") if candidate else ""

    # Check duplicate repost prevention
    if not force and reel_id and is_source_already_posted(reel_id, target_account):
        err_msg = f"Content was already published to @{target_account}. Select another account or confirm repost."
        job["status"] = "duplicate_warning"
        job["error"] = err_msg
        add_bot_log(job, f"⚠️ Duplicate warning: {err_msg}", "warning")
        raise HTTPException(409, err_msg)

    try:
        media_files = dl_info.get("media_files") or [dl_info["new_reel_path"]]
        post_type = dl_info.get("post_type", candidate.get("post_type", "reel"))
        type_label = "Carousel" if post_type == "carousel" else ("Photo Post" if post_type == "image" else "Reel")
        
        add_bot_log(job, f"Uploading {type_label} ({len(media_files)} items) to @{target_account}...")
        
        res = publish_bot_content(
            media_files=media_files,
            caption=caption,
            hashtags=hashtags,
            target_account=target_account,
            post_type=post_type,
            mode=mode,
            reel_id=reel_id,
            original_url=candidate.get("url") if candidate else "",
            audio_status=dl_info.get("audio_status", candidate.get("audio_status", "")),
            force=force
        )
        job["status"] = "published"
        job["step"] = "published"
        job["publish"] = res
        add_bot_log(job, f"✓ {type_label.upper()} PUBLISHED SUCCESSFULLY: {res['instagram_url']}", "success")
        return res
    except PermissionError as pe:
        job["status"] = "failed"
        job["error"] = str(pe)
        err_msg = str(pe)
        if "AUTHENTICATION_REQUIRED" in err_msg or "login_required" in err_msg.lower() or "session expired" in err_msg.lower():
            job["status"] = "auth_required"
            job["step"] = "auth_required"
            add_bot_log(job, f"🔑 Authentication required for @{target_account}: {err_msg}", "error")
            raise HTTPException(401, err_msg)
        if "PUBLISHING RESTRICTED" in err_msg or "restrict" in err_msg.lower() or "feedback_required" in err_msg.lower():
            job["status"] = "publishing_restricted"
            job["step"] = "publishing_restricted"
            add_bot_log(job, f"⚠️ Publishing restricted by Instagram: {err_msg}", "error")
            raise HTTPException(403, f"PUBLISHING_RESTRICTED: {err_msg}")
        add_bot_log(job, f"❌ Account mismatch or permission error: {pe}", "error")
        raise HTTPException(403, str(pe))
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        err_msg = str(e)
        if "login_required" in err_msg.lower() or "upload_settings" in err_msg.lower():
            job["status"] = "auth_required"
            job["step"] = "auth_required"
            add_bot_log(job, f"🔑 Instagram session expired (HTTP 403: login_required) for @{target_account}. Please re-authenticate.", "error")
            raise HTTPException(401, f"AUTHENTICATION_REQUIRED: Instagram session expired during clip upload (HTTP 403: login_required). Please re-authenticate @{target_account}.")
        if "restrict" in err_msg.lower() or "feedback_required" in err_msg.lower():
            job["status"] = "publishing_restricted"
            job["step"] = "publishing_restricted"
            add_bot_log(job, f"⚠️ Publishing restricted by Instagram for @{target_account}: {err_msg}", "error")
            raise HTTPException(403, f"PUBLISHING_RESTRICTED: {err_msg}")
        add_bot_log(job, f"Publishing failed: {e}", "error")
        raise HTTPException(500, str(e))


# ── API: Auto-Post ────────────────────────────────────────────────────────────
@app.post("/api/auto-post/start")
async def api_auto_post_start(body: dict = None):
    if auto_post_state["running"]:
        return {"status": "already_running", "job_id": auto_post_state["job_id"]}

    if body is None:
        body = {}
    target_account = (body.get("account") if isinstance(body, dict) else None) or get_active_account()
    mode = (body.get("mode") if isinstance(body, dict) else "all") or "all"

    job_id = str(uuid.uuid4())[:8]
    auto_post_state["running"] = True
    auto_post_state["cancel"].clear()
    auto_post_state["job_id"] = job_id
    auto_post_state["account"] = target_account
    auto_post_state["mode"] = mode
    auto_post_state["progress"] = {
        "current": 0,
        "total": 0,
        "percentage": 0,
        "account": target_account,
        "mode": mode,
        "step": "initializing"
    }

    thread = threading.Thread(target=auto_post_worker, args=(job_id, target_account, mode), daemon=True)
    auto_post_state["thread"] = thread
    thread.start()
    return {"status": "started", "job_id": job_id, "account": target_account, "mode": mode}


@app.post("/api/auto-post/stop")
async def api_auto_post_stop():
    if auto_post_state["running"]:
        auto_post_state["cancel"].set()
        emit_log("warning", "Auto-post stop requested. Finishing current upload...")
        return {"status": "stopping"}
    return {"status": "not_running"}


@app.get("/api/auto-post/status")
async def api_auto_post_status():
    return {
        "running": auto_post_state["running"],
        "job_id": auto_post_state["job_id"],
        "account": auto_post_state.get("account"),
        "mode": auto_post_state.get("mode", "all"),
        "progress": auto_post_state["progress"],
    }


def auto_post_worker(job_id: str, target_account: str = None, mode: str = "all"):
    """Background thread: posts unposted images and/or reels to target_account according to mode."""
    settings = load_settings()
    delay = settings.get("posting_delay", 30)
    cancel = auto_post_state["cancel"]

    active = target_account or get_active_account()
    emit_log("info", f"Auto-post starting for @{active} (Mode: {mode}, Job: {job_id})")
    emit_log("info", f"Loading session for @{active}...")

    cl = _get_ig_client(active)
    if not cl:
        emit_log("error", f"Could not authenticate @{active}. Aborting.")
        auto_post_state["running"] = False
        log_queue.put({"type": "auto_post_done", "posted": 0, "failed": 0, "total": 0, "account": active})
        return

    # Scan directories based on chosen mode
    all_images = scan_files(IMAGES_NEW, IMAGE_EXTS) if mode in ("all", "images") else []
    all_reels = scan_files(REELS_NEW, VIDEO_EXTS) if mode in ("all", "reels") else []

    # Filter out media that has already been posted to target account
    pending_images = [img for img in all_images if not has_been_posted(img["filename"], active)]
    pending_reels = [r for r in all_reels if not has_been_posted(r["filename"], active)]

    total = len(pending_images) + len(pending_reels)
    done = 0
    failed = 0

    emit_log("info", f"Target Account: @{active} | Mode: {mode}")
    emit_log("info", f"Queue for @{active}: {len(pending_images)} images ready, {len(pending_reels)} reels ready ({total} total)")

    if total == 0:
        emit_log("warning", f"Nothing pending to post for @{active} (Mode: {mode}).")
        auto_post_state["running"] = False
        log_queue.put({"type": "auto_post_done", "posted": 0, "failed": 0, "total": 0, "account": active})
        return

    # ── Post Images ───────────────────────────────────────────────────────
    if pending_images and mode in ("all", "images"):
        for i, img in enumerate(pending_images):
            if cancel.is_set():
                emit_log("warning", "Auto-post cancelled by user.")
                break
            fname = img["filename"]
            fpath = img["path"]

            done += 1
            emit_progress(done, total, fname, "generating_caption", "image")
            emit_log("info", f"[{done}/{total}] Processing image: {fname} for @{active}")

            # AI caption & hashtags generation
            try:
                from caption_ai import generate_image_content
                ai_meta = generate_image_content(fpath)
                full_caption = ai_meta["full"]
            except Exception:
                full_caption = f"Words from the heart. ✨\n\n{DEFAULT_IMAGE_HASHTAGS}"

            emit_progress(done, total, fname, "posting", "image")
            emit_log("info", f"Uploading image: {fname} to @{active}")

            try:
                media = cl.photo_upload(path=Path(fpath), caption=full_caption)
                post_url = f"https://www.instagram.com/p/{media.code}/"
                emit_log("success", f"[✓] Published image to @{active}: {post_url}")

                # Archive copy in images/posted/, but keep original in images/new/ so other accounts can post it too
                dest = os.path.join(IMAGES_POSTED, fname)
                if not os.path.exists(dest):
                    try:
                        shutil.copy2(fpath, dest)
                    except Exception:
                        pass

                add_history_entry(fname, "image", active, post_url, full_caption, media.pk)
            except Exception as e:
                err = str(e)
                if "restrict" in err.lower() or "feedback_required" in err.lower():
                    emit_log("error", f"[⚠️] PUBLISHING RESTRICTED by Instagram for @{active}: {err}")
                    emit_log("warning", f"Stopping auto-post — Instagram has restricted @{active} activity. Wait 24–48 hours.")
                    auto_post_state['cancel'].set()
                else:
                    emit_log("error", f"Failed to post {fname} to @{active}: {err}")
                failed += 1

            if not cancel.is_set() and done < total:
                emit_log("info", f"Cooling down {delay}s...")
                for _ in range(delay):
                    if cancel.is_set():
                        break
                    time.sleep(1)

    # ── Post Reels ────────────────────────────────────────────────────────
    if pending_reels and mode in ("all", "reels"):
        for i, reel in enumerate(pending_reels):
            if cancel.is_set():
                emit_log("warning", "Auto-post cancelled by user.")
                break
            fname = reel["filename"]
            fpath = reel["path"]

            done += 1
            emit_progress(done, total, fname, "generating_caption", "reel")
            emit_log("info", f"[{done}/{total}] Processing reel: {fname} for @{active}")

            try:
                from caption_ai import generate_reel_content
                ai_meta = generate_reel_content(fpath)
                full_caption = ai_meta["full"]
            except Exception:
                full_caption = f"🎬\n\n{DEFAULT_IMAGE_HASHTAGS}"

            emit_progress(done, total, fname, "posting", "reel")
            emit_log("info", f"Uploading reel: {fname} to @{active}")

            try:
                from post_reel_direct import ensure_thumbnail
                thumb = ensure_thumbnail(fpath)
                kwargs = {"path": Path(fpath), "caption": full_caption}
                if thumb and os.path.exists(thumb):
                    kwargs["thumbnail"] = Path(thumb)
                media = cl.clip_upload(**kwargs)
                post_url = f"https://www.instagram.com/reel/{media.code}/"
                emit_log("success", f"[✓] Published reel to @{active}: {post_url}")

                # Archive copy in reels/posted/, but keep original in reels/new/ so other accounts can post it too
                dest = os.path.join(REELS_POSTED, fname)
                if not os.path.exists(dest):
                    try:
                        shutil.copy2(fpath, dest)
                    except Exception:
                        pass
                if thumb and os.path.exists(thumb):
                    thumb_dest = os.path.join(REELS_POSTED, os.path.basename(thumb))
                    if not os.path.exists(thumb_dest):
                        try:
                            shutil.copy2(thumb, thumb_dest)
                        except Exception:
                            pass

                add_history_entry(fname, "reel", active, post_url, full_caption, media.pk)

                # Update SQLite DB
                try:
                    import database
                    reel_id = os.path.splitext(fname)[0]
                    database.mark_published(reel_id, post_url, account=active)
                except Exception:
                    pass
            except Exception as e:
                err = str(e)
                if "login_required" in err.lower() or "upload_settings" in err.lower() or "session expired" in err.lower():
                    emit_log("error", f"[🔑] AUTHENTICATION REQUIRED: Instagram session expired for @{active} (HTTP 403: login_required). Stopping auto-post.")
                    auto_post_state['cancel'].set()
                elif "restrict" in err.lower() or "feedback_required" in err.lower():
                    emit_log("error", f"[⚠️] PUBLISHING RESTRICTED by Instagram for @{active}: {err}")
                    emit_log("warning", f"Stopping auto-post — Instagram has restricted @{active} activity. Wait 24–48 hours.")
                    auto_post_state['cancel'].set()
                else:
                    emit_log("error", f"Failed to post {fname} to @{active}: {err}")
                failed += 1

            if not cancel.is_set() and done < total:
                emit_log("info", f"Cooling down {delay}s...")
                for _ in range(delay):
                    if cancel.is_set():
                        break
                    time.sleep(1)

    auto_post_state["running"] = False
    auto_post_state["progress"] = {"current": done, "total": total,
                                    "percentage": 100 if not cancel.is_set() else (int(done / total * 100) if total > 0 else 0)}
    posted = done - failed
    emit_log("success", f"Auto-post complete for @{active}! Posted: {posted}, Failed: {failed}, Total: {total}")
    log_queue.put({"type": "auto_post_done", "posted": posted, "failed": failed, "total": total, "account": active})


# ── API: History & Logs ───────────────────────────────────────────────────────
@app.get("/api/history")
async def api_history():
    return {"history": load_history()[:200]}


@app.get("/api/settings")
async def api_get_settings():
    return load_settings()


@app.post("/api/settings")
async def api_save_settings(body: dict):
    current = load_settings()
    current.update(body)
    save_settings(current)
    return {"status": "ok"}


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/logs")
async def ws_logs(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  INSTAGRAM AUTOMATION DASHBOARD")
    print("=" * 55)
    port = int(os.environ.get("PORT", 8501))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    print(f"  Dashboard: http://{host}:{port}")
    print(f"  Account  : @{get_active_account()}")
    print("=" * 55)
    uvicorn.run(app, host=host, port=port, log_level="warning")
