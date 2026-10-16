import sys
import re
from downloader import download_reel

def sanitize_url(raw_input: str) -> str:
    """Extract clean URL even if quotes or extra characters are passed."""
    raw_input = raw_input.strip().strip('"').strip("'")
    # Clean up tracking query params if any
    clean_url = raw_input.split("?")[0] if "instagram.com" in raw_input else raw_input
    return clean_url

def main():
    # Check if URL was passed as command line argument
    if len(sys.argv) > 1:
        raw_url = " ".join(sys.argv[1:])
    else:
        # Prompt interactively so PowerShell ampersands never cause a shell syntax error
        print("=" * 48)
        print("          INSTAGRAM QUICK REEL DOWNLOADER")
        print("=" * 48)
        raw_url = input("\nPaste Instagram Reel URL:\n> ").strip()

    if not raw_url:
        print("[!] No URL provided.")
        return

    clean_url = sanitize_url(raw_url)
    print(f"\n[*] Processing Reel: {clean_url}")
    print("[*] Downloading video...")

    try:
        saved_file = download_reel(clean_url)
        print("\n" + "=" * 48)
        print("[SUCCESS] DOWNLOAD COMPLETE!")
        print(f"File saved to: {saved_file}")
        print("=" * 48)
    except Exception as e:
        print(f"\n[!] Download error: {e}")


if __name__ == "__main__":
    main()
