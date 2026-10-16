@echo off
cd /d "%~dp0"
"..\.venv\Scripts\python.exe" post_reel_direct.py %*
pause
