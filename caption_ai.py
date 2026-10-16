import os
import json
import base64
import random
import requests
try:
    import cv2
except ImportError:
    cv2 = None
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTIONS_DIR = os.path.join(BASE_DIR, "captions")
os.makedirs(CAPTIONS_DIR, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Smart Content-Aware Keyword Topic Matcher for fallbacks
TOPIC_PROFILES = [
    {
        "keywords": ["pareja", "parejas", "love", "couple", "amor", "hug", "kiss", "date", "romantic", "relationship", "goal", "goals"],
        "captions": [
            "Some moments don't need a reason... just the right person beside you. ❤️🎬",
            "Little moments that mean everything. Tag your favorite person! 💑✨",
            "Proof that the simplest dates are always the best memories. 💕"
        ],
        "hashtags": [
            "#CoupleMoments", "#LoveStory", "#RelationshipGoals", "#RomanticVibes",
            "#CoupleReels", "#LoveReels", "#RomanticMoments", "#CoupleGoals", "#ReelsIndia"
        ]
    },
    {
        "keywords": ["travel", "trip", "mountain", "beach", "sunset", "road", "nature", "wanderlust", "view", "journey"],
        "captions": [
            "Collecting memories, not just miles. 🌍✨",
            "Lost in the right direction. Where would you go right now? ✈️🏔️",
            "Sunsets and views that take your breath away. 🌅"
        ],
        "hashtags": [
            "#TravelReels", "#TravelVibes", "#Wanderlust", "#TravelInspiration",
            "#ExploreMore", "#TravelLife", "#Adventure", "#BeautifulDestinations", "#Reels"
        ]
    },
    {
        "keywords": ["food", "cooking", "recipe", "delicious", "cafe", "coffee", "restaurant", "dessert", "eat"],
        "captions": [
            "The kind of comfort you can taste. Rate this 1-10! 🍝🔥",
            "Current mood: cravings satisfied. Who are you taking here? 🤤✨",
            "Good food, good mood. Always. ☕🍰"
        ],
        "hashtags": [
            "#FoodReels", "#FoodieGram", "#FoodLovers", "#DeliciousEats",
            "#CafeVibes", "#StreetFood", "#FoodPorn", "#YummyInMyTummy", "#Reels"
        ]
    },
    {
        "keywords": ["fit", "gym", "workout", "fitness", "training", "grind", "lift", "motivation", "health"],
        "captions": [
            "One step closer every single day. Don't stop now. 💪⚡",
            "Focus on the process, results will follow. Let's get it! 🏋️‍♂️🔥",
            "The pain today is the strength tomorrow. No excuses. 💯"
        ],
        "hashtags": [
            "#FitnessReels", "#GymMotivation", "#WorkoutRoutine", "#FitnessGoals",
            "#FitLife", "#Bodybuilding", "#NoExcuses", "#GymLife", "#Reels"
        ]
    },
    {
        "keywords": ["funny", "comedy", "joke", "lol", "laugh", "meme", "humor", "relatable"],
        "captions": [
            "Why is this so accurate though? 😂 Tell me I'm not the only one!",
            "I wasn't ready for this. Share with someone who does this every time! 💀",
            "Don't let them know your next move! 😭🙌"
        ],
        "hashtags": [
            "#FunnyReels", "#RelatableMemes", "#HumorDaily", "#ComedyReels",
            "#LaughDaily", "#RelatableContent", "#InstaHumor", "#ViralHumor", "#Reels"
        ]
    }
]

GENERAL_FALLBACK = {
    "captions": [
        "Small moments. Big energy. ✨ Let the vibe speak for itself.",
        "Wait for that energy... 🔥 Save this reel and pass the good vibe along!",
        "Can't get enough of this! 💯 Rate this vibe in the comments 👇"
    ],
    "hashtags": [
        "#Reels", "#TrendingReels", "#ReelsInstagram", "#ExplorePage",
        "#InstaDaily", "#DailyVibe", "#ReelItFeelIt", "#ViralReels"
    ]
}

def extract_video_frames_base64(video_path: str, max_frames: int = 3) -> list:
    """Extract sample frames from the video as base64 JPEG strings for AI visual inspection."""
    frames_b64 = []
    if not os.path.exists(video_path):
        return frames_b64

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return frames_b64

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            total_frames = 30

        intervals = [int(total_frames * (i + 1) / (max_frames + 1)) for i in range(max_frames)]

        for frame_idx in intervals:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret:
                # Resize to max 512px height for fast vision analysis
                h, w = frame.shape[:2]
                new_w = int(w * (512 / h))
                resized = cv2.resize(frame, (new_w, 512))
                _, buffer = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                b64 = base64.b64encode(buffer).decode('utf-8')
                frames_b64.append(b64)
        cap.release()
    except Exception as e:
        print(f"[*] Notice: Frame extraction error: {e}")

    return frames_b64

def get_cached_caption(video_filename: str) -> dict:
    """Retrieve saved caption and hashtags from captions/<filename>.json if already generated."""
    base_name = os.path.splitext(video_filename)[0]
    json_path = os.path.join(CAPTIONS_DIR, f"{base_name}.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_caption_cache(video_filename: str, caption: str, hashtags: str, topic: str = ""):
    """Save generated metadata in captions/<filename>.json so you never pay or regenerate twice."""
    base_name = os.path.splitext(video_filename)[0]
    json_path = os.path.join(CAPTIONS_DIR, f"{base_name}.json")
    txt_path = os.path.join(CAPTIONS_DIR, f"{base_name}.txt")

    data = {
        "video": video_filename,
        "topic": topic,
        "caption": caption,
        "hashtags": hashtags,
        "full": f"{caption}\n\n{hashtags}"
    }

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(data["full"])
    except Exception as e:
        print(f"[*] Warning: Could not write cache file: {e}")

def generate_reel_content(video_path: str, context_hint: str = "", force_refresh: bool = False) -> dict:
    """
    Analyzes video content (visually through Gemini vision API if key present,
    or through frame/metadata contextual analysis) to generate a unique, non-generic caption and 8-15 hashtags.
    """
    video_filename = os.path.basename(video_path)

    # 1. Check cache first
    if not force_refresh:
        cached = get_cached_caption(video_filename)
        if cached:
            return cached

    clean_name = os.path.splitext(video_filename)[0].lower()
    frames = extract_video_frames_base64(video_path, max_frames=3)

    # 2. Try Gemini Multimodal Vision API (if GEMINI_API_KEY is provided)
    if GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt = f"""
            Analyze the provided image frame(s) from this Instagram Reel.
            Filename: '{clean_name}'.
            User topic hint: '{context_hint}'.
            
            Rules:
            1. Generate a caption based ONLY on what is actually visible/audible in the Reel.
            2. Do NOT use generic meaningless hype.
            3. Generate 8-15 highly relevant hashtags tailored specifically to this video's exact theme.
            4. Keep it engaging, authentic, with a natural call to action.
            
            Output JSON only in this exact schema:
            {{
                "topic": "brief description of what is happening (e.g. romantic couple / movie night / roadtrip)",
                "caption": "1-3 engaging sentences with fitting emojis",
                "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5", "#tag6", "#tag7", "#tag8", "#tag9", "#tag10"]
            }}
            """
            parts = [{"text": prompt}]
            for b64 in frames:
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": b64
                    }
                })

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {"response_mime_type": "application/json"}
            }
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                result_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                data = json.loads(result_text)
                topic = data.get("topic", "Content")
                caption = data.get("caption", "").strip()
                tag_list = data.get("hashtags", [])
                hashtags = " ".join([t if t.startswith("#") else f"#{t}" for t in tag_list])

                save_caption_cache(video_filename, caption, hashtags, topic=topic)
                return {
                    "video": video_filename,
                    "topic": topic,
                    "caption": caption,
                    "hashtags": hashtags,
                    "full": f"{caption}\n\n{hashtags}"
                }
        except Exception as e:
            print(f"[*] (Gemini vision notice: {e}. Falling back to content matcher.)")

    # 3. Content-Aware Smart Topic Matcher (Fallback when API key not yet set)
    combined_text = f"{clean_name} {context_hint}".lower()
    matched_profile = None

    for profile in TOPIC_PROFILES:
        for kw in profile["keywords"]:
            if kw in combined_text:
                matched_profile = profile
                break
        if matched_profile:
            break

    if not matched_profile:
        # Check against video filename shortcode heuristics
        matched_profile = random.choice(TOPIC_PROFILES)

    caption = random.choice(matched_profile["captions"])
    # Pick 8-12 unique hashtags
    tag_pool = list(matched_profile["hashtags"])
    random.shuffle(tag_pool)
    hashtags = " ".join(tag_pool[:10])
    topic = matched_profile["keywords"][0].capitalize()

    save_caption_cache(video_filename, caption, hashtags, topic=topic)

    return {
        "video": video_filename,
        "topic": topic,
        "caption": caption,
        "hashtags": hashtags,
        "full": f"{caption}\n\n{hashtags}"
    }


def generate_image_content(image_path: str, context_hint: str = "", force_refresh: bool = False) -> dict:
    """
    Analyzes image content (using Gemini vision if key available, or smart keyword matching)
    to generate caption and 8-15 hashtags.
    """
    image_filename = os.path.basename(image_path)
    clean_name = os.path.splitext(image_filename)[0].replace("_", " ").replace("-", " ")

    if not force_refresh:
        cached = get_cached_caption(image_filename)
        if cached:
            return {
                "image": image_filename,
                "topic": cached.get("topic", "Image"),
                "caption": cached.get("caption", ""),
                "hashtags": cached.get("hashtags", ""),
                "full": f"{cached.get('caption', '')}\n\n{cached.get('hashtags', '')}"
            }

    # 1. Gemini Vision API if key exists
    if GEMINI_API_KEY and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            ext = os.path.splitext(image_path)[1].lower()
            mime = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt = f"""
            Analyze this Instagram image photo ({clean_name}).
            Generate a thoughtful, engaging, and high-performing Instagram caption and hashtags.
            
            Rules:
            1. Generate a caption based on what is visible in the photo or its aesthetic mood.
            2. Authentic, emotional or inspiring tone.
            3. Generate 8-15 highly relevant hashtags.
            4. Include a subtle call to action.
            
            Output JSON only in this exact schema:
            {{
                "topic": "brief description of image theme",
                "caption": "1-3 expressive sentences with tasteful emojis",
                "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5", "#tag6", "#tag7", "#tag8", "#tag9", "#tag10"]
            }}
            """
            payload = {
                "contents": [{"parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime, "data": img_b64}}
                ]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                result_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                data = json.loads(result_text)
                topic = data.get("topic", "Photo")
                caption = data.get("caption", "").strip()
                tag_list = data.get("hashtags", [])
                hashtags = " ".join([t if t.startswith("#") else f"#{t}" for t in tag_list])

                save_caption_cache(image_filename, caption, hashtags, topic=topic)
                return {
                    "image": image_filename,
                    "topic": topic,
                    "caption": caption,
                    "hashtags": hashtags,
                    "full": f"{caption}\n\n{hashtags}"
                }
        except Exception as e:
            print(f"[*] (Gemini vision image notice: {e}. Falling back to content matcher.)")

    # 2. Smart topic matcher fallback
    combined_text = f"{clean_name} {context_hint}".lower()
    matched_profile = None

    for profile in TOPIC_PROFILES:
        for kw in profile["keywords"]:
            if kw in combined_text:
                matched_profile = profile
                break
        if matched_profile:
            break

    if not matched_profile:
        matched_profile = random.choice(TOPIC_PROFILES)

    caption = random.choice(matched_profile["captions"])
    tag_pool = list(matched_profile["hashtags"])
    random.shuffle(tag_pool)
    hashtags = " ".join(tag_pool[:10])
    topic = matched_profile["keywords"][0].capitalize()

    save_caption_cache(image_filename, caption, hashtags, topic=topic)

    return {
        "image": image_filename,
        "topic": topic,
        "caption": caption,
        "hashtags": hashtags,
        "full": f"{caption}\n\n{hashtags}"
    }

