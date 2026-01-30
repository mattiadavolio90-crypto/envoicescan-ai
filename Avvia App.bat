@echo off
cd /d "%~dp0"
echo.
echo ========================================
echo   AVVIO ANALISI FATTURE AI
echo ========================================
echo.
echo Attendere l'avvio dell'applicazione...
echo.
streamlit run app.py
pause
