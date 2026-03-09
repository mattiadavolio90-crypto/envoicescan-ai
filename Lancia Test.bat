@echo off
cd /d "%~dp0"
code .
start "" cmd /c "cd /d "%~dp0" && .venv\Scripts\python.exe -m pytest tests/ -v && pause"
