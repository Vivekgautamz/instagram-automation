import os
import sys
import json
import shutil
import getpass
from pathlib import Path
from typing import Optional, List, Dict, Union
import time

# In-memory storage for pending 2FA challenges (expires in 5 minutes)
PENDING_2FA_CHALLENGES: Dict[str, dict] = {}

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
ACTIVE_FILE = os.path.join(SESSIONS_DIR, "active_account.txt")
ACCOUNTS_FILE = os.path.join(BASE_DIR, "accounts.json")
LEGACY_SESSION = os.path.abspath(os.path.join(BASE_DIR, "..", "session.json"))

def _init_sessions():
    """Initializes sessions directory and imports legacy session if present."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    
    # If no session files exist in sessions/ but legacy session.json exists, copy it
    existing_sessions = [f for f in os.listdir(SESSIONS_DIR) if f.lower().endswith(".json")]
    if not existing_sessions and os.path.exists(LEGACY_SESSION):
        target = os.path.join(SESSIONS_DIR, "poetghazipur61.json")
        try:
            shutil.copy2(LEGACY_SESSION, target)
            if not os.path.exists(ACTIVE_FILE):
                with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
                    f.write("poetghazipur61\n")
        except Exception as e:
            print(f"[*] Notice: Could not migrate legacy session: {e}")

_init_sessions()

def clean_username(username: str) -> str:
    """Normalizes an Instagram username (stripping @, whitespace, .json)."""
    u = (username or "").strip()
    if u.startswith("@"):
        u = u[1:]
    if u.lower().endswith(".json"):
        u = u[:-5]
    return u.strip()

def load_accounts_config() -> dict:
    """
    Loads accounts configuration from accounts.json.
    Auto-discovers and syncs any sessions/*.json found in the sessions directory.
    """
    _init_sessions()
    data = {"accounts": {}, "active_account": "poetghazipur61"}
    
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
                    if "accounts" not in data or not isinstance(data["accounts"], dict):
                        data["accounts"] = {}
        except Exception as e:
            print(f"[*] Notice: Could not read accounts.json: {e}")

    # Synchronize with sessions/ folder
    active_user = get_active_account()
    if os.path.exists(SESSIONS_DIR):
        for fname in sorted(os.listdir(SESSIONS_DIR)):
            if fname.lower().endswith(".json"):
                uname = clean_username(fname[:-5])
                rel_session = f"sessions/{fname}"
                sess_path = os.path.join(SESSIONS_DIR, fname)
                is_auth = is_session_file_authenticated(sess_path)
                default_status = "connected" if is_auth else "not_authenticated"

                if uname not in data["accounts"]:
                    data["accounts"][uname] = {
                        "username": uname,
                        "display_name": uname,
                        "session_file": rel_session,
                        "status": default_status
                    }
                else:
                    if not data["accounts"][uname].get("session_file"):
                        data["accounts"][uname]["session_file"] = rel_session
                    if not data["accounts"][uname].get("display_name"):
                        data["accounts"][uname]["display_name"] = uname
                    if not data["accounts"][uname].get("status"):
                        data["accounts"][uname]["status"] = default_status

    if not data["accounts"]:
        data["accounts"] = {
            "poetghazipur61": {
                "username": "poetghazipur61",
                "display_name": "Poet Ghazipur Official",
                "session_file": "sessions/poetghazipur61.json",
                "status": "connected",
                "publishing_enabled": True,
                "ig_user_id": os.getenv("IG_USER_ID", "17841476541733844"),
                "meta_token": os.getenv("FB_ACCESS_TOKEN", "")
            },
            "forevermoments.web": {
                "username": "forevermoments.web",
                "display_name": "Forever Moments",
                "session_file": "sessions/forevermoments.web.json",
                "status": "connected",
                "publishing_enabled": True,
                "ig_user_id": os.getenv("FOREVERMOMENTS_IG_USER_ID", "17841431242353329"),
                "meta_token": os.getenv("FOREVERMOMENTS_FB_ACCESS_TOKEN", "")
            }
        }
        data["active_account"] = "poetghazipur61"

    if "active_account" not in data or not data["active_account"]:
        data["active_account"] = active_user or "poetghazipur61"

    return data

def save_accounts_config(data: dict):
    """Saves accounts configuration to accounts.json."""
    try:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Error saving accounts.json: {e}")

def update_account_status(username: str, status: str):
    """Saves and updates status for a specific Instagram account in accounts.json."""
    try:
        clean_u = clean_username(username).lower()
        data = load_accounts_config()
        if clean_u in data.get("accounts", {}):
            data["accounts"][clean_u]["status"] = status
            save_accounts_config(data)
    except Exception as e:
        print(f"[*] Notice: Could not update status for @{username}: {e}")

def list_accounts() -> List[Dict[str, any]]:
    """Returns a list of all saved Instagram accounts and indicates active status."""
    data = load_accounts_config()
    active_user = get_active_account()
    accounts = []
    
    for uname, acc in data.get("accounts", {}).items():
        sess_file = acc.get("session_file", f"sessions/{uname}.json")
        sess_path = os.path.normpath(os.path.join(BASE_DIR, sess_file)) if not os.path.isabs(sess_file) else sess_file
        sess_exists = os.path.exists(sess_path)
        is_auth = is_session_file_authenticated(sess_path)
        
        stored_status = (acc.get("status") or "").lower()
        if not is_auth:
            status = "session_expired" if sess_exists else "No Session File"
            is_auth = False
        elif stored_status == "publishing_restricted":
            status = "publishing_restricted"
        elif stored_status in ("session_expired", "expired"):
            status = "session_expired"
            is_auth = False
        elif stored_status == "session_mismatch":
            status = "session_mismatch"
            is_auth = False
        elif stored_status == "authentication_required":
            status = "Authentication Required"
            is_auth = False
        elif stored_status == "connected":
            status = "Connected"
        else:
            status = "Connected" if is_auth else ("Not Authenticated" if sess_exists else "No Session File")
        
        acc_auth_type = acc.get("auth_type", "Instagram Login")
        pub_enabled = acc.get("publishing_enabled", True)
        has_pending_2fa = uname.lower() in PENDING_2FA_CHALLENGES and (time.time() - PENDING_2FA_CHALLENGES[uname.lower()].get("created_at", 0) <= 300)
        
        accounts.append({
            "username": uname,
            "display_name": acc.get("display_name") or uname,
            "session_file": sess_file.replace("\\", "/"),
            "session_path": sess_path,
            "session_exists": sess_exists,
            "is_authenticated": is_auth,
            "status": status,
            "is_active": (uname.lower() == active_user.lower()),
            "auth_type": acc_auth_type,
            "publishing_enabled": pub_enabled,
            "two_factor": is_auth,
            "token_status": "Valid" if is_auth else ("Expired" if status == "session_expired" else "Invalid"),
            "challenge_pending": has_pending_2fa
        })
    
    # Sort with active first, then alphabetical
    accounts.sort(key=lambda x: (not x["is_active"], x["username"]))
    return accounts

def get_active_account() -> str:
    """Returns the currently active Instagram account name."""
    if os.path.exists(ACTIVE_FILE):
        try:
            with open(ACTIVE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return clean_username(content)
        except Exception:
            pass

    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict) and d.get("active_account"):
                    return clean_username(d["active_account"])
        except Exception:
            pass

    # Fallback to the first session found in sessions/
    if os.path.exists(SESSIONS_DIR):
        files = [f for f in os.listdir(SESSIONS_DIR) if f.lower().endswith(".json")]
        if files:
            return clean_username(files[0][:-5])

    return "poetghazipur61"

def set_active_account(username: str) -> bool:
    """Switches the active Instagram account."""
    uname = clean_username(username)
    session_file = os.path.join(SESSIONS_DIR, f"{uname}.json")
    
    # Check if session exists in sessions/
    if not os.path.exists(session_file):
        # Check if legacy session matches
        if os.path.exists(LEGACY_SESSION) and uname.lower() == "poetghazipur61":
            shutil.copy2(LEGACY_SESSION, session_file)
        else:
            # Check if defined in accounts.json
            data = load_accounts_config()
            acc = data.get("accounts", {}).get(uname)
            if not acc:
                print(f"[!] Account not found for: @{uname}")
                return False
            # Create a placeholder session file if missing so client scripts don't fail
            try:
                with open(session_file, "w", encoding="utf-8") as sf:
                    json.dump({}, sf)
            except Exception:
                pass

    with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
        f.write(f"{uname}\n")
        
    data = load_accounts_config()
    data["active_account"] = uname
    save_accounts_config(data)
    
    print(f"[OK] Active Instagram account set to: @{uname}")
    return True

def get_session_path(username: Optional[str] = None) -> str:
    """Returns the full path to the session JSON file for the given or active account."""
    _init_sessions()
    uname = clean_username(username) if username else get_active_account()
    
    data = load_accounts_config()
    acc = data.get("accounts", {}).get(uname)
    if acc and acc.get("session_file"):
        custom = os.path.normpath(os.path.join(BASE_DIR, acc["session_file"]))
        if os.path.exists(custom):
            return custom

    target_path = os.path.join(SESSIONS_DIR, f"{uname}.json")
    if os.path.exists(target_path):
        return target_path
    if os.path.exists(LEGACY_SESSION) and uname.lower() == "poetghazipur61":
        return LEGACY_SESSION
    return target_path

def is_session_file_authenticated(sess_path: str) -> bool:
    """Fast check whether a session file on disk contains real credentials or is just an empty placeholder."""
    if not os.path.exists(sess_path):
        return False
    try:
        with open(sess_path, "r", encoding="utf-8") as f:
            d = json.load(f)
            if not isinstance(d, dict):
                return False
            # Check for instagrapi auth headers or cookies
            auth_data = d.get("authorization_data") or d.get("authorization") or {}
            cookies = d.get("cookies", {}) or {}
            has_sessionid = bool(
                cookies.get("sessionid") or 
                (isinstance(auth_data, dict) and auth_data.get("sessionid")) or 
                d.get("sessionid")
            )
            has_user_id = bool(
                d.get("user_id") or 
                cookies.get("ds_user_id") or 
                (isinstance(auth_data, dict) and auth_data.get("ds_user_id"))
            )
            return bool(has_sessionid or (bool(auth_data) and has_user_id))
    except Exception:
        return False

def create_account_session(username: str):
    """
    Creates a dedicated, fresh session context for the specified Instagram account.
    Returns (fresh_client, session_file_path).
    Never loads another account's session.
    """
    uname = clean_username(username).lower()
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    session_file = os.path.join(SESSIONS_DIR, f"{uname}.json")
    
    from instagrapi import Client
    # IMPORTANT: Fresh Client for every new Instagram account.
    cl = Client()
    # Do not load another account's session here.
    return cl, session_file

def verify_session(client, expected_username: str) -> bool:
    """
    Verifies that the authenticated client actually belongs to expected_username
    and has a live, valid session.
    Raises PermissionError if session has expired or requires authentication.
    Raises RuntimeError if there is a session mismatch.
    """
    from instagrapi.exceptions import (
        FeedbackRequired,
        LoginRequired,
        BadPassword,
        ChallengeRequired
    )
    
    expected_username = clean_username(expected_username).lower()
    actual_username = None
    try:
        account = client.account_info()
        actual_username = account.username.lower()
    except (LoginRequired, BadPassword) as e:
        update_account_status(expected_username, "session_expired")
        raise PermissionError(
            f"AUTHENTICATION_REQUIRED: Instagram session for @{expected_username} has expired (HTTP 403: login_required). "
            f"Please re-authenticate your account."
        )
    except ChallengeRequired as e:
        update_account_status(expected_username, "challenge_required")
        raise PermissionError(
            f"CHALLENGE_REQUIRED: Instagram security checkpoint required for @{expected_username}. "
            f"Please open Instagram app or web to resolve it."
        )
    except FeedbackRequired:
        # If Instagram restricted account_info with "We restrict certain activity",
        # resolve username from user_id if possible
        if client.user_id:
            try:
                actual_username = (client.username_from_user_id(client.user_id) or "").lower()
            except Exception:
                actual_username = expected_username
        else:
            actual_username = expected_username
    except Exception as e:
        err_str = str(e).lower()
        if "login_required" in err_str or "unauthorized" in err_str or "403" in err_str:
            update_account_status(expected_username, "session_expired")
            raise PermissionError(
                f"AUTHENTICATION_REQUIRED: Instagram session for @{expected_username} is invalid or expired ({e}). "
                f"Please re-authenticate."
            )
        if client.user_id:
            try:
                actual_username = (client.username_from_user_id(client.user_id) or "").lower()
            except Exception as ce:
                raise RuntimeError(f"Could not verify session user identity: {ce}")
        else:
            raise RuntimeError("No user ID associated with this session.")

    if actual_username != expected_username:
        update_account_status(expected_username, "session_mismatch")
        raise RuntimeError(
            f"Session mismatch: expected @{expected_username}, authenticated as @{actual_username}"
        )
    return True

def get_client_for_account(account, verify: bool = True):
    """
    Dedicated client loader for an account.
    Loads its specific session file and strictly verifies the authenticated username.
    """
    from instagrapi import Client

    if isinstance(account, dict):
        uname = clean_username(account.get("username", "")).lower()
        sess_file = account.get("session_file")
    else:
        uname = clean_username(str(account)).lower()
        sess_file = None

    if not uname:
        uname = get_active_account().lower()

    if sess_file:
        sess_path = os.path.normpath(os.path.join(BASE_DIR, sess_file)) if not os.path.isabs(sess_file) else sess_file
    else:
        sess_path = get_session_path(uname)

    if not os.path.exists(sess_path):
        raise FileNotFoundError(f"Session file not found for @{uname} at: {sess_path}")

    # IMPORTANT: Fresh client per account
    client = Client()
    client.load_settings(sess_path)

    if verify:
        verify_session(client, uname)

    return client

def verify_account_session(username: str, session_file: Optional[str] = None) -> dict:
    """
    Verifies that the session file for a username exists, contains valid credentials,
    and performs a live check with Instagram to determine the ACTUAL authenticated username.
    """
    from instagrapi import Client
    from instagrapi.exceptions import (
        LoginRequired,
        BadPassword,
        ChallengeRequired,
        FeedbackRequired
    )

    uname = clean_username(username)
    if not uname:
        return {"valid": False, "username": "", "status": "error", "message": "Username is required."}

    if session_file:
        sess_path = os.path.normpath(os.path.join(BASE_DIR, session_file)) if not os.path.isabs(session_file) else session_file
    else:
        sess_path = get_session_path(uname)

    rel_session = os.path.relpath(sess_path, BASE_DIR).replace("\\", "/")

    if not os.path.exists(sess_path):
        return {
            "valid": False,
            "username": uname,
            "actual_username": None,
            "session_file": rel_session,
            "status": "missing_session",
            "message": f"Session file not found at '{os.path.basename(sess_path)}'. Please authenticate to generate it."
        }

    # Verify if file has actual credential data
    if not is_session_file_authenticated(sess_path):
        return {
            "valid": False,
            "username": uname,
            "actual_username": None,
            "session_file": rel_session,
            "status": "not_authenticated",
            "message": f"Session file at '{os.path.basename(sess_path)}' contains no active login credentials."
        }

    try:
        cl = Client()
        cl.load_settings(sess_path)
    except Exception as e:
        return {
            "valid": False,
            "username": uname,
            "actual_username": None,
            "session_file": rel_session,
            "status": "invalid_session",
            "message": f"Session file exists but could not be parsed: {e}"
        }

    if not cl.user_id:
        return {
            "valid": False,
            "username": uname,
            "actual_username": None,
            "session_file": rel_session,
            "status": "not_authenticated",
            "message": "Session contains no authenticated user ID."
        }

    # ── Live Instagram verification ───────────────────────────────────────────
    actual_username = None
    try:
        info = cl.account_info()
        actual_username = info.username
    except (LoginRequired, BadPassword) as e:
        return {
            "valid": False,
            "username": uname,
            "actual_username": None,
            "session_file": rel_session,
            "status": "session_expired",
            "message": f"Instagram session has expired or been revoked: {e}"
        }
    except ChallengeRequired:
        return {
            "valid": False,
            "username": uname,
            "actual_username": None,
            "session_file": rel_session,
            "status": "challenge_required",
            "message": "Instagram security challenge required (SMS/email checkpoint). Resolve it in the Instagram app."
        }
    except FeedbackRequired as e:
        # Session is valid, but Instagram is restricting actions for this account
        err_str = str(e)
        return {
            "valid": True,  # Session itself is valid — this is an Instagram-side restriction
            "username": uname,
            "actual_username": uname,
            "username_matched": True,
            "session_file": rel_session,
            "status": "publishing_restricted",
            "user_id": str(cl.user_id) if cl.user_id else None,
            "message": f"⚠️ INSTAGRAM ACTION RESTRICTED: Instagram is temporarily restricting activity for @{uname}. "
                       f"The session is valid but Instagram is blocking posts/actions. Wait 24-48 hours. Details: {err_str}"
        }
    except Exception:
        # Fallback to resolving username from user_id if account_info is temporarily rate-limited
        try:
            actual_username = cl.username_from_user_id(cl.user_id)
        except Exception:
            actual_username = uname

    if not actual_username:
        actual_username = uname

    matches = (actual_username.lower() == uname.lower())
    if not matches:
        return {
            "valid": False,
            "username": uname,
            "actual_username": actual_username,
            "username_matched": False,
            "session_file": rel_session,
            "status": "session_mismatch",
            "message": f"❌ SESSION MISMATCH: Selected @{uname}, but authenticated as @{actual_username}. Publishing disabled."
        }
    
    return {
        "valid": True,
        "username": uname,
        "actual_username": actual_username,
        "username_matched": True,
        "session_file": rel_session,
        "status": "Connected",
        "user_id": str(cl.user_id) if cl.user_id else None,
        "message": f"Session verified successfully for @{actual_username} (Status: Connected)"
    }


def login_account_direct(
    username: str,
    password: str,
    verification_code: Optional[str] = None,
    display_name: Optional[str] = None,
    set_active: bool = False
) -> dict:
    """
    Directly logs into Instagram and saves the session in sessions/<actual_username>.json.
    NEVER writes passwords to accounts.json or to disk.
    """
    from instagrapi import Client
    from instagrapi.exceptions import (
        TwoFactorRequired,
        BadPassword,
        ChallengeRequired,
        FeedbackRequired
    )

    uname = clean_username(username)
    if not uname:
        return {"valid": False, "status": "error", "message": "Instagram username is required."}
    if not password:
        return {"valid": False, "status": "error", "message": "Password is required."}

    cl = Client()
    _init_sessions()

    try:
        if verification_code:
            cl.login(uname, password, verification_code=str(verification_code).strip())
        else:
            cl.login(uname, password)
    except TwoFactorRequired:
        PENDING_2FA_CHALLENGES[uname.lower()] = {
            "password": password,
            "created_at": time.time(),
            "display_name": display_name,
            "set_active": set_active
        }
        return {
            "valid": False,
            "status": "two_factor_required",
            "username": uname,
            "challenge_pending": True,
            "message": "Two-Factor Authentication (2FA) is enabled for this account. Enter the 6-digit code in the OTP / 2FA Code tab."
        }
    except BadPassword:
        return {
            "valid": False,
            "status": "bad_password",
            "username": uname,
            "message": "Incorrect Instagram password. Please check your credentials."
        }
    except ChallengeRequired:
        return {
            "valid": False,
            "status": "challenge_required",
            "username": uname,
            "message": "Instagram challenge required (SMS/email verification). Please open Instagram app or web browser to confirm."
        }
    except FeedbackRequired as e:
        return {
            "valid": False,
            "status": "feedback_required",
            "username": uname,
            "message": f"Instagram action blocked or rate limited: {e}"
        }
    except Exception as e:
        return {
            "valid": False,
            "status": "error",
            "username": uname,
            "message": f"Instagram login failed: {e}"
        }

    # Verify actual username from authenticated Client
    actual_username = uname
    try:
        info = cl.account_info()
        actual_username = info.username
    except Exception:
        if cl.user_id:
            try:
                actual_username = cl.username_from_user_id(cl.user_id) or uname
            except Exception:
                actual_username = uname

    session_filename = f"sessions/{actual_username}.json"
    session_filepath = os.path.join(SESSIONS_DIR, f"{actual_username}.json")

    try:
        cl.dump_settings(session_filepath)
    except Exception as e:
        return {
            "valid": False,
            "status": "error",
            "username": actual_username,
            "message": f"Logged in but error saving session: {e}"
        }

    # Clear any pending challenge for this account
    PENDING_2FA_CHALLENGES.pop(actual_username.lower(), None)
    PENDING_2FA_CHALLENGES.pop(uname.lower(), None)

    # Add to accounts.json (WITHOUT password)
    acc_result = add_account(
        username=actual_username,
        display_name=display_name or actual_username,
        session_file=session_filename,
        set_active=set_active
    )

    return {
        "valid": True,
        "status": "Connected",
        "username": actual_username,
        "actual_username": actual_username,
        "display_name": acc_result.get("display_name", actual_username),
        "session_file": session_filename,
        "is_active": acc_result.get("is_active", False),
        "user_id": str(cl.user_id) if cl.user_id else None,
        "message": f"Successfully authenticated and connected @{actual_username}!"
    }

def add_account(
    username: str,
    display_name: Optional[str] = None,
    session_file: Optional[str] = None,
    status: Optional[str] = None,
    set_active: bool = False
) -> dict:
    """
    Adds a new Instagram account configuration to accounts.json and ensures
    the session file path structure is prepared without storing any passwords.
    """
    uname = clean_username(username)
    if not uname:
        raise ValueError("Valid Instagram username is required.")

    if not session_file:
        session_file = f"sessions/{uname}.json"
    
    sess_path = os.path.normpath(os.path.join(BASE_DIR, session_file)) if not os.path.isabs(session_file) else session_file
    os.makedirs(os.path.dirname(sess_path), exist_ok=True)
    
    disp_name = (display_name or "").strip() or uname
    
    data = load_accounts_config()
    acc_status = status or ("connected" if is_session_file_authenticated(sess_path) else "not_authenticated")
    data["accounts"][uname] = {
        "username": uname,
        "display_name": disp_name,
        "session_file": session_file.replace("\\", "/"),
        "status": acc_status
    }

    if set_active or len(data["accounts"]) == 1:
        data["active_account"] = uname
        with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
            f.write(f"{uname}\n")

    save_accounts_config(data)
    
    return {
        "username": uname,
        "display_name": disp_name,
        "session_file": session_file.replace("\\", "/"),
        "status": acc_status,
        "is_active": (data["active_account"].lower() == uname.lower())
    }

def delete_account(username: str) -> bool:
    """Removes an account from accounts.json."""
    uname = clean_username(username)
    data = load_accounts_config()
    if uname in data.get("accounts", {}):
        del data["accounts"][uname]
        if data.get("active_account", "").lower() == uname.lower():
            remaining = list(data.get("accounts", {}).keys())
            data["active_account"] = remaining[0] if remaining else "poetghazipur61"
            with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
                f.write(f"{data['active_account']}\n")
        save_accounts_config(data)
        return True
    return False

def get_instagram_client(username: Optional[str] = None, verify: bool = True):
    """
    Initializes and returns an authenticated instagrapi Client for the requested
    or active Instagram account using dedicated per-account session loading.
    """
    _init_sessions()
    uname = clean_username(username) if username else get_active_account()
    session_path = get_session_path(uname)

    if not os.path.exists(session_path):
        print(f"[!] Session file not found for @{uname} at:")
        print(f"    {session_path}")
        print(f"Please log in first using: .\\commands.ps1 add-account {uname}")
        return None

    print(f"[*] Loading Instagram session: {os.path.relpath(session_path, BASE_DIR)}")
    try:
        cl = get_client_for_account(uname, verify=verify)
        print(f"[OK] Logged in as: @{uname}")
        return cl
    except PermissionError as pe:
        print(f"\n[ERROR] AUTHENTICATION REQUIRED for @{uname}: {pe}")
        raise
    except RuntimeError as re:
        print(f"\n[ERROR] ACCOUNT MISMATCH: {re}")
        raise
    except Exception as e:
        print(f"[*] Session notice for @{uname}: {e}")
        err_msg = str(e).lower()
        if "login_required" in err_msg or "expired" in err_msg:
            update_account_status(uname, "session_expired")
            raise PermissionError(f"AUTHENTICATION_REQUIRED: Session expired for @{uname} ({e})")
        if verify:
            raise
        from instagrapi import Client
        cl = Client()
        try:
            cl.load_settings(session_path)
            return cl
        except Exception:
            return None


def login_new_account(username: str, password: Optional[str] = None):
    """
    Interactively logs into an Instagram account and saves the session
    in sessions/<username>.json.
    """
    from instagrapi import Client
    from instagrapi.exceptions import (
        TwoFactorRequired,
        BadPassword,
        ChallengeRequired,
        FeedbackRequired
    )

    uname = clean_username(username)
    print("=" * 60)
    print(f"  INSTAGRAM LOGIN - ADD ACCOUNT: @{uname}")
    print("=" * 60)
    print("Your password is NOT stored in any script or code.")
    print("It is used once to authenticate and generate an encrypted session.json.")
    print("=" * 60)

    if not password:
        password = getpass.getpass(f"Enter Instagram password for @{uname}: ")
        if not password:
            print("[!] Password cannot be empty.")
            return False

    cl = Client()
    session_file = os.path.join(SESSIONS_DIR, f"{uname}.json")

    print(f"\n[*] Authenticating with Instagram as @{uname}...")
    try:
        cl.login(uname, password)
    except TwoFactorRequired:
        print("\n[!] Two-Factor Authentication (2FA) is enabled for this account.")
        code = input("Enter the 6-digit 2FA verification code (from SMS/Auth App): ").strip()
        try:
            cl.login(uname, password, verification_code=code)
        except Exception as e:
            print(f"[!] 2FA verification failed: {e}")
            return False
    except BadPassword:
        print("[!] Login failed: Incorrect password.")
        return False
    except ChallengeRequired:
        print("[!] Instagram challenge required (Email/SMS verification).")
        print("Please resolve the checkpoint in your Instagram mobile app or browser first.")
        return False
    except FeedbackRequired as e:
        print(f"[!] Instagram rate limit/action blocked: {e}")
        return False
    except Exception as e:
        print(f"[!] Login error: {e}")
        return False

    try:
        cl.dump_settings(session_file)
        print(f"\n[OK] Successfully authenticated and saved session to:")
        print(f"    {session_file}")
        
        # Add to accounts.json and make active
        add_account(uname, uname, f"sessions/{uname}.json", set_active=True)
        return True
    except Exception as e:
        print(f"[!] Error saving session settings: {e}")
        return False

def import_session_id(username: str, sessionid: str) -> dict:
    """
    Securely validates an Instagram session ID cookie for a specific account,
    ensures the authenticated identity matches the requested username,
    and persists the session directly to sessions/<username>.json.
    Never logs or exposes the session ID value.
    """
    from instagrapi import Client
    from instagrapi.exceptions import (
        LoginRequired,
        BadPassword,
        ChallengeRequired,
        FeedbackRequired
    )

    clean_u = clean_username(username).lower()
    if not clean_u:
        return {"valid": False, "status": "error", "message": "Username is required."}

    clean_sid = (sessionid or "").strip()
    if clean_sid.lower().startswith("sessionid="):
        clean_sid = clean_sid[10:].strip()
    clean_sid = clean_sid.strip("\"'; ")

    if not clean_sid:
        return {"valid": False, "status": "error", "message": "Enter your session ID."}

    # Isolated client specifically for this import attempt
    cl = Client()
    _init_sessions()

    try:
        cl.login_by_sessionid(clean_sid)
    except AssertionError:
        return {
            "valid": False,
            "status": "invalid_format",
            "username": clean_u,
            "message": "Invalid session ID format. Please copy the complete sessionid cookie (typically starting with your numeric Instagram user ID, e.g. 54321%3A...)."
        }
    except (LoginRequired, BadPassword) as e:
        return {
            "valid": False,
            "status": "session_expired",
            "username": clean_u,
            "message": "Instagram rejected this session ID (session expired or revoked: login_required). Please use Reconnect Instagram with credentials/2FA or obtain a fresh active session cookie."
        }
    except ChallengeRequired:
        return {
            "valid": False,
            "status": "challenge_required",
            "username": clean_u,
            "message": "Instagram security challenge required (SMS/email checkpoint). Please open Instagram in your browser or app to resolve it."
        }
    except FeedbackRequired as e:
        return {
            "valid": False,
            "status": "feedback_required",
            "username": clean_u,
            "message": f"Instagram action restricted: {e}"
        }
    except Exception as e:
        err_msg = str(e)
        if "login_required" in err_msg.lower():
            return {
                "valid": False,
                "status": "session_expired",
                "username": clean_u,
                "message": "Session ID is expired or revoked by Instagram (login_required). Please use Reconnect Instagram."
            }
        return {
            "valid": False,
            "status": "verification_failed",
            "username": clean_u,
            "message": f"Session verification failed: {err_msg}"
        }

    # Verify actual user identity
    actual_username = None
    try:
        info = cl.account_info()
        actual_username = (info.username or "").lower()
    except Exception:
        if cl.user_id:
            try:
                actual_username = (cl.username_from_user_id(cl.user_id) or "").lower()
            except Exception:
                actual_username = (getattr(cl, "username", "") or "").lower()
        else:
            actual_username = (getattr(cl, "username", "") or "").lower()

    if not actual_username or actual_username != clean_u:
        return {
            "valid": False,
            "status": "session_mismatch",
            "username": clean_u,
            "actual_username": actual_username or "unknown",
            "message": f"Session mismatch: The imported session ID belongs to @{actual_username or 'unknown'}, not @{clean_u}. Session was NOT saved to protect account isolation."
        }

    # Save to sessions/<clean_u>.json
    target_session_file = os.path.join(SESSIONS_DIR, f"{clean_u}.json")
    rel_session = f"sessions/{clean_u}.json"

    try:
        cl.dump_settings(target_session_file)
    except Exception as e:
        return {
            "valid": False,
            "status": "save_error",
            "username": clean_u,
            "message": f"Verified session with Instagram, but failed to save session file: {e}"
        }

    # Update accounts.json
    try:
        data = load_accounts_config()
        if clean_u not in data.get("accounts", {}):
            data["accounts"][clean_u] = {
                "username": clean_u,
                "display_name": clean_u,
                "session_file": rel_session,
                "status": "connected"
            }
        else:
            data["accounts"][clean_u]["status"] = "connected"
            data["accounts"][clean_u]["session_file"] = rel_session
        save_accounts_config(data)
    except Exception as e:
        print(f"[!] Warning: accounts.json update failed: {e}")

    return {
        "valid": True,
        "status": "connected",
        "username": clean_u,
        "actual_username": actual_username,
        "session_file": rel_session,
        "user_id": str(cl.user_id) if cl.user_id else None,
        "message": f"Session verified and saved successfully for @{clean_u}!"
    }


def reconnect_account(
    username: str,
    password: str,
    verification_code: Optional[str] = None
) -> dict:
    """
    Securely re-authenticates an existing account using username, password,
    and optional 2FA code. Updates the account's session file and status.
    Never stores or logs the password.
    """
    clean_u = clean_username(username).lower()
    if not clean_u:
        return {"valid": False, "status": "error", "message": "Username is required."}

    data = load_accounts_config()
    disp_name = clean_u
    if clean_u in data.get("accounts", {}):
        disp_name = data["accounts"][clean_u].get("display_name", clean_u)

    active_user = get_active_account().lower()
    is_active = (clean_u == active_user)

    res = login_account_direct(
        username=clean_u,
        password=password,
        verification_code=verification_code,
        display_name=disp_name,
        set_active=is_active
    )
    return res


def get_pending_challenge(username: str) -> Optional[dict]:
    """Checks if there is an active pending 2FA login challenge for this account (expires in 5 minutes)."""
    clean_u = clean_username(username).lower()
    challenge = PENDING_2FA_CHALLENGES.get(clean_u)
    if not challenge:
        return None
    elapsed = time.time() - challenge.get("created_at", 0)
    if elapsed > 300:
        PENDING_2FA_CHALLENGES.pop(clean_u, None)
        return None
    expires_in = max(0, int(300 - elapsed))
    return {
        "username": clean_u,
        "created_at": challenge.get("created_at"),
        "expires_in": expires_in,
        "pending": True
    }


def verify_otp_challenge(username: str, verification_code: str, password: Optional[str] = None) -> dict:
    """
    Submits a 6-digit OTP / 2FA code for a pending challenge and creates an isolated session.
    Never exposes passwords or OTP in logs.
    """
    clean_u = clean_username(username).lower()
    code = (verification_code or "").strip()
    if not clean_u:
        return {"valid": False, "status": "error", "message": "Username is required."}
    if not code:
        return {"valid": False, "status": "error", "message": "6-digit verification code is required."}

    challenge = PENDING_2FA_CHALLENGES.get(clean_u)
    effective_pwd = password or (challenge.get("password") if challenge else None)

    if not effective_pwd:
        return {
            "valid": False,
            "status": "challenge_expired",
            "message": f"No active login challenge found for @{clean_u}. Please initiate login in the 'Password + 2FA' tab first."
        }

    # Verify expiration (5 minutes)
    if challenge and (time.time() - challenge.get("created_at", 0) > 300):
        PENDING_2FA_CHALLENGES.pop(clean_u, None)
        return {
            "valid": False,
            "status": "challenge_expired",
            "message": "The login challenge has expired (security codes expire within 5 minutes). Please start login again."
        }

    set_active = challenge.get("set_active", False) if challenge else False
    display_name = challenge.get("display_name", clean_u) if challenge else clean_u

    res = login_account_direct(
        username=clean_u,
        password=effective_pwd,
        verification_code=code,
        display_name=display_name,
        set_active=set_active
    )

    if res.get("valid"):
        PENDING_2FA_CHALLENGES.pop(clean_u, None)
        try:
            data = load_accounts_config()
            if clean_u in data.get("accounts", {}):
                data["accounts"][clean_u]["auth_type"] = "Password + 2FA (OTP)"
                save_accounts_config(data)
        except Exception:
            pass

    return res


def import_session_json(username: str, json_content: Union[str, dict], set_active: bool = False) -> dict:
    """
    Securely loads session settings from a JSON dictionary/string,
    verifies user identity with Instagram, and writes to sessions/<username>.json.
    """
    from instagrapi import Client
    clean_u = clean_username(username).lower()
    if not clean_u:
        return {"valid": False, "status": "error", "message": "Username is required."}

    if isinstance(json_content, str):
        try:
            settings_dict = json.loads(json_content)
        except Exception as e:
            return {"valid": False, "status": "invalid_json", "message": f"Invalid JSON format: {e}"}
    elif isinstance(json_content, dict):
        settings_dict = json_content
    else:
        return {"valid": False, "status": "invalid_json", "message": "Session JSON must be a valid dictionary or JSON string."}

    cl = Client()
    _init_sessions()

    try:
        cl.set_settings(settings_dict)
    except Exception as e:
        return {"valid": False, "status": "invalid_session", "message": f"Failed to apply session settings: {e}"}

    # Verify identity with Instagram
    actual_username = None
    try:
        info = cl.account_info()
        actual_username = (info.username or "").lower()
    except Exception:
        if cl.user_id:
            try:
                actual_username = (cl.username_from_user_id(cl.user_id) or "").lower()
            except Exception:
                actual_username = (getattr(cl, "username", "") or "").lower()
        else:
            actual_username = (getattr(cl, "username", "") or "").lower()

    if not actual_username or actual_username != clean_u:
        return {
            "valid": False,
            "status": "session_mismatch",
            "username": clean_u,
            "actual_username": actual_username or "unknown",
            "message": f"Session mismatch: The imported JSON belongs to @{actual_username or 'unknown'}, not @{clean_u}."
        }

    target_session_file = os.path.join(SESSIONS_DIR, f"{clean_u}.json")
    rel_session = f"sessions/{clean_u}.json"

    try:
        cl.dump_settings(target_session_file)
    except Exception as e:
        return {"valid": False, "status": "save_error", "message": f"Failed to save session settings: {e}"}

    try:
        data = load_accounts_config()
        if clean_u not in data.get("accounts", {}):
            data["accounts"][clean_u] = {
                "username": clean_u,
                "display_name": clean_u,
                "session_file": rel_session,
                "status": "connected",
                "auth_type": "Session JSON"
            }
        else:
            data["accounts"][clean_u]["status"] = "connected"
            data["accounts"][clean_u]["session_file"] = rel_session
            data["accounts"][clean_u]["auth_type"] = "Session JSON"
        if set_active:
            data["active_account"] = clean_u
            with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
                f.write(f"{clean_u}\n")
        save_accounts_config(data)
    except Exception as e:
        print(f"[!] accounts.json update notice: {e}")

    return {
        "valid": True,
        "status": "connected",
        "username": clean_u,
        "actual_username": actual_username,
        "session_file": rel_session,
        "auth_type": "Session JSON",
        "message": f"Session JSON loaded and verified successfully for @{clean_u}!"
    }


def toggle_publishing(username: str, enabled: Optional[bool] = None) -> dict:
    """Toggles or sets the publishing status for an account (Enabled / Paused)."""
    clean_u = clean_username(username).lower()
    data = load_accounts_config()
    if clean_u in data.get("accounts", {}):
        curr = data["accounts"][clean_u].get("publishing_enabled", True)
        new_val = (not curr) if enabled is None else bool(enabled)
        data["accounts"][clean_u]["publishing_enabled"] = new_val
        save_accounts_config(data)
        return {"status": "ok", "username": clean_u, "publishing_enabled": new_val}
    return {"status": "error", "message": f"Account @{clean_u} not found"}


def print_accounts():
    """Prints a styled list of all available Instagram accounts."""
    accounts = list_accounts()
    active_user = get_active_account()
    
    print("=" * 55)
    print("           AVAILABLE INSTAGRAM ACCOUNTS")
    print("=" * 55)
    
    if not accounts:
        print("  No saved accounts found in sessions/ folder.")
        print(f"  Legacy session: {'Found' if os.path.exists(LEGACY_SESSION) else 'Not found'}")
        print("\nTo add an account, run: .\\commands.ps1 add-account <username>")
    else:
        for idx, acc in enumerate(accounts, 1):
            status = "Connected" if acc.get("session_exists") else "No Session"
            if acc["is_active"]:
                print(f"  [{idx}] 🟢 @{acc['username']:<20} ({acc.get('display_name', '')}) [{status}] [ACTIVE]")
            else:
                print(f"  [{idx}] ⚪ @{acc['username']:<20} ({acc.get('display_name', '')}) [{status}]")
    
    print("-" * 55)
    print(f"Currently active account: @{active_user}")
    print("=" * 55)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_accounts()
        sys.exit(0)

    action = sys.argv[1].lower().strip()

    if action in ["list", "accounts", "show"]:
        print_accounts()
    elif action in ["get", "active", "current"]:
        print(get_active_account())
    elif action in ["use", "switch", "set", "select"]:
        if len(sys.argv) < 3:
            print("Usage: python account_manager.py use <username>")
            sys.exit(1)
        target = sys.argv[2]
        success = set_active_account(target)
        sys.exit(0 if success else 1)
    elif action in ["login", "add", "add-account"]:
        if len(sys.argv) < 3:
            uname = input("Enter Instagram username to add: ").strip()
        else:
            uname = sys.argv[2]
        pwd = sys.argv[3] if len(sys.argv) > 3 else None
        success = login_new_account(uname, pwd)
        sys.exit(0 if success else 1)
    else:
        print(f"[!] Unknown action: {action}")
        print("Usage: python account_manager.py [list | use <username> | login <username> | active]")
        sys.exit(1)
