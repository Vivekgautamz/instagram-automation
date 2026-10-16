@echo off
cd /d "%~dp0"
echo ===================================================
echo   Starting Instagram Automation Web Dashboard...
echo ===================================================
echo Opening browser at http://127.0.0.1:8501 ...
start http://127.0.0.1:8501
"..\.venv\Scripts\python.exe" backend\server.py
pause
