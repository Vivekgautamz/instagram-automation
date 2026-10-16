# ==============================================================================
# commands.ps1 - Professional Windows PowerShell Command Manager
# Project: Instagram Automation Bot
# Location: C:\vivek\poetghazipur61\for reel
# ==============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = "help",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

# Base project paths
$ProjectDir = $PSScriptRoot
$PythonExe  = [System.IO.Path]::GetFullPath((Join-Path $ProjectDir "..\.venv\Scripts\python.exe"))

# ------------------------------------------------------------------------------
# Helper Log Functions
# ------------------------------------------------------------------------------
function Log-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Log-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Log-Error {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor Red
}

function Check-Python {
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        Log-Error "Python executable not found at: $PythonExe"
        Log-Error "Please ensure the virtual environment (.venv) is present in the parent directory."
        exit 1
    }
}

function Check-Script {
    param([string]$FileName)
    $ScriptPath = Join-Path $ProjectDir $FileName
    if (-not (Test-Path -LiteralPath $ScriptPath)) {
        Log-Error "Required script '$FileName' not found at: $ScriptPath"
        exit 1
    }
    return $ScriptPath
}

# ------------------------------------------------------------------------------
# Help Menu
# ------------------------------------------------------------------------------
function Show-Help {
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host "  INSTAGRAM AUTOMATION COMMAND MANAGER  " -ForegroundColor Yellow
    Write-Host "  dashboard   Start the local Web Dashboard (UI at http://127.0.0.1:8501)" -ForegroundColor White
    Write-Host "  accounts    Show available Instagram accounts & active account" -ForegroundColor White
    Write-Host "  use         Switch active posting account (e.g. .\commands.ps1 use poetghazipur61)" -ForegroundColor White
    Write-Host "  add-account Login and save session for a new Instagram account" -ForegroundColor White
    Write-Host "  auto-post   Automatically post pending images + Reels to active account" -ForegroundColor White
    Write-Host "  download    Download Instagram Reel" -ForegroundColor White
    Write-Host "  bot         Run interactive Viral Reel Bot (download & post)" -ForegroundColor White
    Write-Host "  post-reel   Post Reel to Instagram (interactive)" -ForegroundColor White
    Write-Host "  post-image  Post image to Instagram (interactive)" -ForegroundColor White
    Write-Host "  setup       Install Reel dependencies" -ForegroundColor White
    Write-Host "  check       Check MoviePy and FFmpeg" -ForegroundColor White
    Write-Host "  list        List downloaded/ready Reels and images" -ForegroundColor White
    Write-Host "  folders     Create required folders" -ForegroundColor White
    Write-Host "  open        Open project folder" -ForegroundColor White
    Write-Host "  python      Open Python environment" -ForegroundColor White
    Write-Host "  help        Show this help" -ForegroundColor White

    Write-Host "----------------------------------------" -ForegroundColor Gray
    Write-Host "Examples:" -ForegroundColor DarkGray
    Write-Host "  .\commands.ps1 accounts" -ForegroundColor DarkGray
    Write-Host "  .\commands.ps1 use poetghazipur61" -ForegroundColor DarkGray
    Write-Host "  .\commands.ps1 add-account other_account" -ForegroundColor DarkGray
    Write-Host "  .\commands.ps1 auto-post" -ForegroundColor DarkGray
    Write-Host '  .\commands.ps1 download "https://www.instagram.com/reel/XXXXXXXX/"' -ForegroundColor DarkGray
    Write-Host "  .\commands.ps1 post-reel" -ForegroundColor DarkGray
    Write-Host "  .\commands.ps1 post-image" -ForegroundColor DarkGray
    Write-Host "========================================" -ForegroundColor Magenta
}

# ------------------------------------------------------------------------------
# Create Folders
# ------------------------------------------------------------------------------
function Ensure-Folders {
    $folders = @(
        "sessions",
        "downloads",
        "images\new",
        "images\posted",
        "reels\new",
        "reels\posted",
        "captions"
    )
    foreach ($f in $folders) {
        $p = Join-Path $ProjectDir $f
        if (-not (Test-Path -LiteralPath $p)) {
            New-Item -ItemType Directory -Path $p -Force | Out-Null
            Log-Success "Created folder: $f"
        }
    }
    Log-Success "All required folders are verified."
}

# ------------------------------------------------------------------------------
# Command Routing
# ------------------------------------------------------------------------------
switch ($Command.ToLower()) {
    "help" {
        Show-Help
        exit 0
    }

    "folders" {
        Log-Info "Verifying project directory structure..."
        Ensure-Folders
        exit 0
    }

    "open" {
        Log-Info "Opening project folder in File Explorer..."
        Start-Process explorer.exe -ArgumentList $ProjectDir
        Log-Success "Explorer opened."
        exit 0
    }

    "list" {
        Log-Info "Checking Reels and Images directories..."
        $newReelsDir = Join-Path $ProjectDir "reels\new"
        $newImagesDir = Join-Path $ProjectDir "images\new"
        $dlDir  = Join-Path $ProjectDir "downloads"

        Write-Host ""
        Write-Host "--- Ready in reels\new ---" -ForegroundColor Yellow
        if (Test-Path -LiteralPath $newReelsDir) {
            $newFiles = Get-ChildItem -LiteralPath $newReelsDir -File -Filter *.mp4 -ErrorAction SilentlyContinue
            if ($newFiles.Count -gt 0) {
                foreach ($file in $newFiles) {
                    $mb = [math]::Round($file.Length / 1MB, 2)
                    Write-Host "  - $($file.Name) ($mb MB)" -ForegroundColor Cyan
                }
            } else {
                Write-Host "  (No .mp4 files found in reels\new)" -ForegroundColor DarkGray
            }
        }

        Write-Host ""
        Write-Host "--- Ready in images\new ---" -ForegroundColor Yellow
        if (Test-Path -LiteralPath $newImagesDir) {
            $imgFiles = Get-ChildItem -LiteralPath $newImagesDir -File -ErrorAction SilentlyContinue | Where-Object {
                $_.Extension -match "\.(jpg|jpeg|png|webp)$"
            }
            if ($imgFiles.Count -gt 0) {
                foreach ($file in $imgFiles) {
                    $kb = [math]::Round($file.Length / 1KB, 1)
                    Write-Host "  - $($file.Name) ($kb KB)" -ForegroundColor Cyan
                }
            } else {
                Write-Host "  (No images found in images\new)" -ForegroundColor DarkGray
            }
        }

        Write-Host ""
        Write-Host "--- Downloaded in downloads\ ---" -ForegroundColor Yellow
        if (Test-Path -LiteralPath $dlDir) {
            $dlFiles = Get-ChildItem -LiteralPath $dlDir -File -Filter *.mp4 -ErrorAction SilentlyContinue
            if ($dlFiles.Count -gt 0) {
                foreach ($file in $dlFiles) {
                    $mb = [math]::Round($file.Length / 1MB, 2)
                    Write-Host "  - $($file.Name) ($mb MB)" -ForegroundColor Cyan
                }
            } else {
                Write-Host "  (No .mp4 files found in downloads)" -ForegroundColor DarkGray
            }
        }
        Write-Host ""
        exit 0
    }

    "setup" {
        Check-Python
        Log-Info "Installing video dependencies in virtual environment..."
        & $PythonExe -m pip install "instagrapi[video]"
        if ($LASTEXITCODE -ne 0) {
            Log-Error "Failed to install instagrapi[video]."
            exit $LASTEXITCODE
        }

        Log-Info "Installing MoviePy 2.2.1 and imageio-ffmpeg..."
        & $PythonExe -m pip install --no-deps "moviepy==2.2.1" imageio-ffmpeg
        if ($LASTEXITCODE -ne 0) {
            Log-Error "Failed to install MoviePy."
            exit $LASTEXITCODE
        }

        Log-Success "Setup completed successfully."
        exit 0
    }

    "check" {
        Check-Python
        Log-Info "Checking MoviePy and FFmpeg availability..."
        & $PythonExe -c "import moviepy; print('MoviePy version:', moviepy.__version__)"
        if ($LASTEXITCODE -ne 0) {
            Log-Error "MoviePy check failed."
            exit $LASTEXITCODE
        }

        & $PythonExe -c "import imageio_ffmpeg; print('FFmpeg executable:', imageio_ffmpeg.get_ffmpeg_exe())"
        if ($LASTEXITCODE -ne 0) {
            Log-Error "imageio_ffmpeg check failed."
            exit $LASTEXITCODE
        }

        Log-Success "All core video processing libraries are working."
        exit 0
    }

    "download" {
        Check-Python
        $script = Check-Script "download.py"
        
        $urlArg = ""
        if ($Arguments -and $Arguments.Count -gt 0) {
            $urlArg = ($Arguments -join " ").Trim().Trim('"').Trim("'")
        }

        if (-not [string]::IsNullOrWhiteSpace($urlArg)) {
            Log-Info "Starting download for Reel: $urlArg"
            & $PythonExe $script $urlArg
        } else {
            Log-Info "Starting interactive Reel downloader..."
            & $PythonExe $script
        }

        if ($LASTEXITCODE -ne 0) {
            Log-Error "Download operation failed with exit code $LASTEXITCODE."
            exit $LASTEXITCODE
        }
        exit 0
    }

    "accounts" {
        Check-Python
        $script = Check-Script "account_manager.py"
        & $PythonExe $script list
        exit $LASTEXITCODE
    }

    "use" {
        Check-Python
        $script = Check-Script "account_manager.py"
        if ($Arguments -and $Arguments.Count -gt 0) {
            $targetUser = $Arguments[0].Trim().Trim("@")
            & $PythonExe $script use $targetUser
        } else {
            Log-Error "Please specify the username to use. Example: .\commands.ps1 use poetghazipur61"
            & $PythonExe $script list
            exit 1
        }
        exit $LASTEXITCODE
    }

    "account" {
        Check-Python
        $script = Check-Script "account_manager.py"
        if ($Arguments -and $Arguments.Count -gt 0) {
            $targetUser = $Arguments[0].Trim().Trim("@")
            & $PythonExe $script use $targetUser
        } else {
            & $PythonExe $script list
        }
        exit $LASTEXITCODE
    }

    "add-account" {
        Check-Python
        $script = Check-Script "account_manager.py"
        if ($Arguments -and $Arguments.Count -gt 0) {
            & $PythonExe $script login @Arguments
        } else {
            & $PythonExe $script login
        }
        exit $LASTEXITCODE
    }

    "login" {
        Check-Python
        $script = Check-Script "account_manager.py"
        if ($Arguments -and $Arguments.Count -gt 0) {
            & $PythonExe $script login @Arguments
        } else {
            & $PythonExe $script login
        }
        exit $LASTEXITCODE
    }

    "auto-post" {
        Check-Python
        $script = Check-Script "auto_post.py"
        Log-Info "Launching Automatic Instagram Content Poster..."
        if ($Arguments -and $Arguments.Count -gt 0) {
            & $PythonExe $script @Arguments
        } else {
            & $PythonExe $script
        }
        if ($LASTEXITCODE -ne 0) {
            Log-Error "Auto-post workflow exited with code $LASTEXITCODE."
            exit $LASTEXITCODE
        }
        exit 0
    }

    "bot" {
        Check-Python
        $script = Check-Script "main.py"
        Log-Info "Launching Viral Reel Bot (main.py)..."
        & $PythonExe $script
        if ($LASTEXITCODE -ne 0) {
            Log-Error "Bot workflow exited with code $LASTEXITCODE."
            exit $LASTEXITCODE
        }
        exit 0
    }

    "post-reel" {
        Check-Python
        $script = Check-Script "post_reel_direct.py"
        Log-Info "Launching Instagram Reel publisher..."
        & $PythonExe $script
        if ($LASTEXITCODE -ne 0) {
            Log-Error "Post Reel workflow exited with code $LASTEXITCODE."
            exit $LASTEXITCODE
        }
        exit 0
    }


    "post-image" {
        Check-Python
        $localScript = Join-Path $ProjectDir "post_image.py"
        $parentScript = [System.IO.Path]::GetFullPath((Join-Path $ProjectDir "..\instagram.py"))
        
        if (Test-Path -LiteralPath $localScript) {
            Log-Info "Launching local image publisher ($localScript)..."
            & $PythonExe $localScript
        } elseif (Test-Path -LiteralPath $parentScript) {
            Log-Info "Launching parent image publisher ($parentScript)..."
            & $PythonExe $parentScript
        } else {
            Log-Error "No post_image.py or instagram.py script found."
            exit 1
        }

        if ($LASTEXITCODE -ne 0) {
            Log-Error "Post image workflow exited with code $LASTEXITCODE."
            exit $LASTEXITCODE
        }
        exit 0
    }

    "dashboard" {
        Check-Python
        $serverScript = Join-Path $ProjectDir "backend\server.py"
        if (-not (Test-Path -LiteralPath $serverScript)) {
            Log-Error "Backend server script not found at: $serverScript"
            exit 1
        }
        Log-Info "Starting Instagram Web Dashboard at http://127.0.0.1:8501 ..."
        Start-Process "http://127.0.0.1:8501"
        & $PythonExe $serverScript
        exit 0
    }

    "web" {
        & $PSCommandPath "dashboard"
        exit 0
    }

    "python" {
        Check-Python
        Log-Info "Starting project Python interactive shell..."
        if ($Arguments -and $Arguments.Count -gt 0) {
            & $PythonExe @Arguments
        } else {
            & $PythonExe
        }
        exit 0
    }

    default {
        Log-Error "Unknown command '$Command'."
        Write-Host ""
        Show-Help
        exit 1
    }
}
