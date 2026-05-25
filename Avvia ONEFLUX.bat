@echo off
setlocal
cd /d "%~dp0"

set "TARGET_BRANCH=progetto"
set "ORIGINAL_BRANCH="
set "AUTO_STASHED=0"
set "CURRENT_BRANCH="
for /f %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "CURRENT_BRANCH=%%B"
set "ORIGINAL_BRANCH=%CURRENT_BRANCH%"

if not defined CURRENT_BRANCH (
	echo.
	echo ERRORE: Impossibile rilevare il branch Git corrente.
	echo Avvio bloccato: l'app deve partire sempre dal branch %TARGET_BRANCH%.
	echo.
	pause
	exit /b 1
)

if /I not "%CURRENT_BRANCH%"=="%TARGET_BRANCH%" (
	set "HAS_CHANGES="
	for /f %%S in ('git status --porcelain 2^>nul') do set "HAS_CHANGES=1"

	if defined HAS_CHANGES (
		echo.
		echo ATTENZIONE: Sei su branch %CURRENT_BRANCH% con modifiche locali non committate.
		echo Per avviare sempre e solo %TARGET_BRANCH% posso fare stash temporaneo automatico.
		choice /C SN /N /M "Procedo con stash temporaneo e avvio su %TARGET_BRANCH%? [S/N] "
		if errorlevel 2 (
			echo.
			echo Operazione annullata. Nessuna modifica applicata.
			echo.
			pause
			exit /b 1
		)

		git stash push -u -m "auto-avvio-oneflux" >nul 2>&1
		if errorlevel 1 (
			echo.
			echo ERRORE: stash automatico non riuscito. Avvio bloccato.
			echo.
			pause
			exit /b 1
		)
		set "AUTO_STASHED=1"
	)

	echo.
	echo Switch automatico branch: %CURRENT_BRANCH% ^> %TARGET_BRANCH%...
	git checkout %TARGET_BRANCH% >nul 2>&1
	if errorlevel 1 (
		git checkout -t origin/%TARGET_BRANCH% >nul 2>&1
	)

	if errorlevel 1 (
		echo.
		echo ERRORE: Impossibile fare checkout del branch %TARGET_BRANCH%.
		echo.
		pause
		exit /b 1
	)
)

set "CURRENT_BRANCH="
for /f %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "CURRENT_BRANCH=%%B"
if /I not "%CURRENT_BRANCH%"=="%TARGET_BRANCH%" (
	echo.
	echo ERRORE: Branch attivo non valido (%CURRENT_BRANCH%). Atteso: %TARGET_BRANCH%.
	echo Avvio bloccato.
	echo.
	pause
	exit /b 1
)

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "APP_FILE=%~dp0app.py"
set "APP_PORT=8502"

if not defined ADMIN_EMAILS (
	set "ADMIN_EMAILS=md@oneflux.it"
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

set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%APP_PORT% .*LISTENING"') do (
	if not defined PORT_PID set "PORT_PID=%%P"
)

if defined PORT_PID (
	echo.
	echo ATTENZIONE: La porta %APP_PORT% e' gia in uso.
	echo PID in ascolto: %PORT_PID%
	echo Apro comunque il browser locale.
	start "" "http://localhost:%APP_PORT%"
	echo.
	exit /b 0
)

echo.
echo ========================================
echo   AVVIO ONEFLUX
echo ========================================
echo.
echo Attendere l'avvio dell'applicazione...
echo.

echo Avvio su porta %APP_PORT%...
echo.

ping 127.0.0.1 -n 4 > nul
start "" "http://localhost:%APP_PORT%"

"%PYTHON_EXE%" -m streamlit run "%APP_FILE%" --server.port %APP_PORT%
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
	echo.
	echo ERRORE: Streamlit si e' chiuso con codice %APP_EXIT%.
)

if "%AUTO_STASHED%"=="1" (
	echo.
	echo Ripristino branch e modifiche locali precedenti...
	git checkout "%ORIGINAL_BRANCH%" >nul 2>&1
	if errorlevel 1 (
		echo ATTENZIONE: Non riesco a tornare automaticamente a %ORIGINAL_BRANCH%.
		echo Esegui manualmente: git checkout %ORIGINAL_BRANCH%
	) else (
		git stash pop >nul 2>&1
		if errorlevel 1 (
			echo ATTENZIONE: Ripristino stash automatico non completato.
			echo Verifica con: git stash list
		)
	)
)

if not "%APP_EXIT%"=="0" (
	echo.
	pause
)
