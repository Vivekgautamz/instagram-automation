import os
from dotenv import load_dotenv

load_dotenv()

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

for path in [DOWNLOADS_DIR, PROCESSED_DIR, LOGS_DIR]:
    os.makedirs(path, exist_ok=True)

# Instagram Graph API settings (for official publishing)
# Requires an Instagram Professional (Creator or Business) Account linked to a Facebook Page
IG_USER_ID = os.getenv("IG_USER_ID", "")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN", "")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")

# OpenAI / Gemini API for intelligent caption & hashtag generation (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Local Public Media Server base URL (Instagram Graph API requires a publicly accessible video URL to publish)
PUBLIC_MEDIA_BASE_URL = os.getenv("PUBLIC_MEDIA_BASE_URL", "http://localhost:8000")
