import re
from typing import Tuple

DEFAULT_HASHTAGS = ["#reels", "#viral", "#trending", "#explore", "#reelsinstagram", "#instadaily", "#fyp"]

def clean_and_generate_caption(original_title_or_caption: str, credit_handle: str = "") -> Tuple[str, str]:
    """
    Cleans original captions, creates an engaging hook, appends proper attribution,
    and returns (caption, hashtags).
    """
    cleaned = re.sub(r'http\S+', '', original_title_or_caption)
    cleaned = re.sub(r'#\w+', '', cleaned).strip()

    # Fallback if empty
    if not cleaned:
        cleaned = "Wait till the end! 🔥 Thoughts on this?"

    if credit_handle:
        cleaned += f"\n\nCredit: @{credit_handle.lstrip('@')}"

    hashtags = " ".join(DEFAULT_HASHTAGS)
    return cleaned, hashtags
