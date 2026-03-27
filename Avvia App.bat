@echo off
cd /d "%~dp0"
echo.
echo ========================================
echo   AVVIO OH YEAH! Hub
echo ========================================
echo.
echo Attendere l'avvio dell'applicazione...
echo.

REM Attiva virtual environment
call .venv\Scripts\activate.bat

echo Avvio su porta 8502...
echo.
streamlit run app.py --server.port 8502
pause
