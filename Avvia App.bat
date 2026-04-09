@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "APP_FILE=%~dp0app.py"
set "APP_PORT=8502"

if not defined ADMIN_EMAILS (
	set "ADMIN_EMAILS=mattiadavolio90@gmail.com"
)

if not exist "%PYTHON_EXE%" (
	echo.
	echo ERRORE: Virtual environment non trovato in .venv\Scripts\python.exe
	echo Crea prima l'ambiente con:
	echo   python -m venv .venv
	echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
	echo.
	pause
	exit /b 1
)

if not exist "%APP_FILE%" (
	echo.
	echo ERRORE: File app.py non trovato nella cartella corrente.
	echo.
	pause
	exit /b 1
)

echo.
echo ========================================
echo   AVVIO OH YEAH! Hub
echo ========================================
echo.
echo Attendere l'avvio dell'applicazione...
echo.

echo Avvio su porta %APP_PORT%...
echo.

"%PYTHON_EXE%" -m streamlit run "%APP_FILE%" --server.port %APP_PORT%
pause
