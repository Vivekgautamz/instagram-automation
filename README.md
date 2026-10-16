# Instagram Viral Reel & Image Automation Bot

A professional automation toolkit for downloading, generating AI captions, and publishing Reels and Photos to multiple Instagram accounts.

## Project Structure

```text
for reel/
│
├── commands.ps1            # Unified PowerShell Command Center
├── account_manager.py      # Multi-account session & login manager
├── auto_post.py            # Automatic batch poster for images & reels
├── post_reel_direct.py     # Content-aware Reel publisher
├── post_image.py           # Photo publisher
├── download.py             # Instagram Reel & post downloader
├── main.py                 # Interactive Viral Reel Bot
├── caption_ai.py           # Intelligent AI caption generator
│
├── sessions/               # Saved Instagram authenticated sessions
│   ├── active_account.txt  # Tracks the current active account
│   ├── poetghazipur61.json
│   └── <other_account>.json
│
├── images/
│   ├── new/                # Drop images here ready to post
│   └── posted/             # Successfully published images archive
│
└── reels/
    ├── new/                # Drop MP4 video Reels here ready to post
    └── posted/             # Successfully published Reels archive
```

---

## PowerShell Command Center (`commands.ps1`)

All operations can be managed via PowerShell:

### 1. Multi-Account Management

| Command | Description |
| :--- | :--- |
| `.\commands.ps1 accounts` | Show all saved Instagram accounts and which one is active |
| `.\commands.ps1 use <username>` | Switch the active posting account (e.g. `.\commands.ps1 use poetghazipur61`) |
| `.\commands.ps1 add-account <username>` | Log in and save session for a new account (supports 2FA) |

### 2. Posting & Publishing

| Command | Description |
| :--- | :--- |
| `.\commands.ps1 auto-post` | **Automatically posts all pending images & Reels to the active account** |
| `.\commands.ps1 post-reel` | Interactive Reel selector, previewer, and publisher |
| `.\commands.ps1 post-image` | Interactive photo selector and publisher |

### 3. Downloading & Exploring

| Command | Description |
| :--- | :--- |
| `.\commands.ps1 download "<reel_url>"` | Download a Reel by URL directly into `downloads/` |
| `.\commands.ps1 bot` | Launch the Viral Reel Bot discovery interface |
| `.\commands.ps1 list` | List all pending media in `reels/new/`, `images/new/`, and `downloads/` |

### 4. System & Utilities

| Command | Description |
| :--- | :--- |
| `.\commands.ps1 setup` | Install all video and posting dependencies |
| `.\commands.ps1 check` | Verify MoviePy and FFmpeg configuration |
| `.\commands.ps1 folders` | Create and verify all required directories |
| `.\commands.ps1 open` | Open the project in Windows Explorer |
| `.\commands.ps1 help` | View all available commands |

---

## How It Works

1. **No Passwords in Code**: Credentials are never hardcoded. When you run `.\commands.ps1 add-account <username>`, your terminal prompts for password and 2FA once, and creates an encrypted session file in `sessions/<username>.json`.
2. **Account Switching**: Running `.\commands.ps1 use <username>` updates `sessions/active_account.txt`. All scripts automatically direct uploads to that account.
3. **Automated Posting**: Put your photos into `images/new/` and MP4 reels into `reels/new/`. Run `.\commands.ps1 auto-post` to publish everything sequentially with rate-limit protection.

