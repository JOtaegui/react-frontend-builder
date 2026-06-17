@echo off
REM ============================================================================
REM  EmailAnalyzer - Lanzador para Windows (incluye Windows on ARM / Mac M2)
REM  Doble clic para arrancar.
REM    - Instala Python (x64) automaticamente si no esta.
REM    - Instala Node.js automaticamente solo si hay que compilar el frontend.
REM    - NO instala Chrome. La app se abre en tu navegador por defecto.
REM ============================================================================
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "SERVER=%ROOT%server"
set "VENV=%SERVER%\venv"
set "PORT=8787"

REM Versiones para el modo de respaldo (si no hubiera winget):
set "PY_FALLBACK_VER=3.12.7"
set "NODE_FALLBACK_VER=20.18.0"

REM ── Detectar arquitectura (sirve para x64 y para ARM64) ────────────────────
REM  Regla: x64 corre en AMBAS (nativo en x64, emulado en ARM64); ARM64 NO corre
REM  en x64. Por eso Python se instala SIEMPRE x64 (asi pip encuentra todos los
REM  paquetes precompilados). Node se instala nativo de cada arquitectura.
set "IS_ARM=0"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "IS_ARM=1"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "IS_ARM=1"
if "%IS_ARM%"=="1" (
    echo [arch] Windows ARM64 detectado. Python sera x64 emulado; Node sera ARM64 nativo.
) else (
    echo [arch] Windows x64 detectado. Python y Node x64 nativos.
)

REM ── Liberar el puerto si quedo un proceso anterior ─────────────────────────
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

REM ── Carpeta de configuracion del usuario ───────────────────────────────────
set "CONFIG_DIR=%USERPROFILE%\.emailanalyzer"
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
set "ENV_FILE=%CONFIG_DIR%\.env"
if not exist "%ENV_FILE%" (
    > "%ENV_FILE%" echo # EmailAnalyzer - Configuracion personal
    >> "%ENV_FILE%" echo # Las credenciales OAuth ya vienen incluidas en server\.env
    >> "%ENV_FILE%" echo # Configura esto solo si quieres enviar bajas por tu propio SMTP:
    >> "%ENV_FILE%" echo # SMTP_USER=tu_correo@gmail.com
    >> "%ENV_FILE%" echo # SMTP_PASSWORD=xxxx xxxx xxxx xxxx
    >> "%ENV_FILE%" echo # BAJA_REPORT_DESTINATION=tu_correo@gmail.com
)

REM ── Variables de entorno ───────────────────────────────────────────────────
set "DOTENV_PATH=%ENV_FILE%"
set "DB_PATH=%CONFIG_DIR%\osint_chile.db"
set "STATIC_DIST_PATH=%ROOT%dist"
set "FRONTEND_URL=http://localhost:%PORT%"
set "GOOGLE_OAUTH_REDIRECT_URI=http://localhost:%PORT%/api/auth/gmail/callback"

REM ── Asegurar Python (lo instala si falta) ──────────────────────────────────
call :ensure_python
if errorlevel 1 ( endlocal & exit /b 1 )

REM ── Crear entorno virtual e instalar dependencias (solo la primera vez) ─────
if not exist "%VENV%\Scripts\python.exe" (
    echo ^>^>^> Primera vez: creando entorno virtual e instalando dependencias...
    echo     ^(esto puede tardar algunos minutos^)
    %PY% -m venv "%VENV%"
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV%\Scripts\python.exe" -m pip install -r "%SERVER%\requirements.txt"
)

REM ── Construir el frontend SOLO si no esta compilado ────────────────────────
if not exist "%ROOT%dist\index.html" (
    call :ensure_node
    if errorlevel 1 ( endlocal & exit /b 1 )
    echo ^>^>^> Construyendo interfaz...
    pushd "%ROOT%"
    call npm install
    call npm run build
    popd
)

REM ── Abrir el navegador por defecto a los 3 segundos ────────────────────────
start "" /b cmd /c "timeout /t 3 >nul & start http://localhost:%PORT%"

REM ── Arrancar el servidor ───────────────────────────────────────────────────
echo ^>^>^> Iniciando EmailAnalyzer en http://localhost:%PORT% ...
pushd "%SERVER%"
"%VENV%\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port %PORT% --log-level info
popd

endlocal
exit /b 0


REM ===========================================================================
REM  SUBRUTINAS
REM ===========================================================================

:ensure_python
REM Devuelve %PY% con el comando de Python. errorlevel 1 si hay que reabrir.
REM Usa "--version" (no "where") a proposito: asi ignora el stub falso de la
REM Microsoft Store (python.exe que solo dice "Python was not found").
py --version >nul 2>&1 && ( set "PY=py" & exit /b 0 )
python --version >nul 2>&1 && ( set "PY=python" & exit /b 0 )
echo.
echo ^>^>^> Python no encontrado. Instalando version x64 (compatible con ARM)...
where winget >nul 2>&1
if not errorlevel 1 (
    winget install -e --id Python.Python.3.12 --architecture x64 --scope user --silent --accept-source-agreements --accept-package-agreements
) else (
    call :download_python
)
call :refresh_path
py --version >nul 2>&1 && ( set "PY=py" & exit /b 0 )
python --version >nul 2>&1 && ( set "PY=python" & exit /b 0 )
echo.
echo *** Python se instalo, pero hay que reabrir la consola para usarlo. ***
echo     Cierra esta ventana y vuelve a hacer doble clic en start.bat
echo.
pause
exit /b 1

:download_python
set "PYEXE=%TEMP%\python-%PY_FALLBACK_VER%-amd64.exe"
echo     Descargando Python %PY_FALLBACK_VER% (x64)...
curl -L -o "%PYEXE%" "https://www.python.org/ftp/python/%PY_FALLBACK_VER%/python-%PY_FALLBACK_VER%-amd64.exe"
echo     Instalando Python (silencioso)...
"%PYEXE%" /quiet PrependPath=1 Include_launcher=1 InstallAllUsers=0
exit /b 0

:ensure_node
REM Solo se llama si hay que compilar el frontend. errorlevel 1 si hay que reabrir.
where npm >nul 2>&1 && exit /b 0
echo.
echo ^>^>^> Node.js no encontrado (necesario para compilar la interfaz). Instalando...
where winget >nul 2>&1
if not errorlevel 1 (
    winget install -e --id OpenJS.NodeJS.LTS --silent --accept-source-agreements --accept-package-agreements
) else (
    call :download_node
)
call :refresh_path
where npm >nul 2>&1 && exit /b 0
echo.
echo *** Node.js se instalo, pero hay que reabrir la consola para usarlo. ***
echo     Cierra esta ventana y vuelve a hacer doble clic en start.bat
echo.
pause
exit /b 1

:download_node
set "NODEMSI=%TEMP%\node-v%NODE_FALLBACK_VER%-x64.msi"
echo     Descargando Node.js %NODE_FALLBACK_VER%...
curl -L -o "%NODEMSI%" "https://nodejs.org/dist/v%NODE_FALLBACK_VER%/node-v%NODE_FALLBACK_VER%-x64.msi"
echo     Instalando Node.js (silencioso)...
msiexec /i "%NODEMSI%" /qn
exit /b 0

:refresh_path
REM Recarga el PATH desde el registro para detectar lo recien instalado
REM sin tener que reabrir la consola (best-effort).
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "PATH=%PATH%;%%B"
for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "PATH=%PATH%;%%B"
exit /b 0
