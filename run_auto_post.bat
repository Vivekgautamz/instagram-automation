@echo off
cd /d "%~dp0"
echo ===================================================
echo   Instagram Automatic Batch Poster
echo ===================================================
"..\.venv\Scripts\python.exe" auto_post.py
pause
