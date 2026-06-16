@echo off
REM ============================================================================
REM  EmailAnalyzer - Lanzador para Windows
REM  Doble clic para arrancar. Crea el entorno, compila y abre el navegador.
REM ============================================================================
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "SERVER=%ROOT%server"
set "VENV=%SERVER%\venv"
set "PORT=8787"

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

REM ── Detectar Python ────────────────────────────────────────────────────────
where py >nul 2>&1
if %errorlevel%==0 ( set "PY=py" ) else ( set "PY=python" )
%PY% --version >nul 2>&1
if not %errorlevel%==0 (
    echo ERROR: No se encontro Python. Instalalo desde https://www.python.org/downloads/
    echo        Marca "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

REM ── Crear entorno virtual e instalar dependencias (solo la primera vez) ─────
if not exist "%VENV%\Scripts\python.exe" (
    echo ^>^>^> Primera vez: creando entorno virtual e instalando dependencias...
    echo     ^(esto puede tardar algunos minutos^)
    %PY% -m venv "%VENV%"
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV%\Scripts\python.exe" -m pip install -r "%SERVER%\requirements.txt"
)

REM ── Construir el frontend si no esta compilado ─────────────────────────────
if not exist "%ROOT%dist\index.html" (
    where npm >nul 2>&1
    if !errorlevel!==0 (
        echo ^>^>^> Construyendo interfaz...
        pushd "%ROOT%"
        call npm install
        call npm run build
        popd
    ) else (
        echo ADVERTENCIA: no se encontro npm y no existe la carpeta dist.
        echo              Instala Node.js ^(https://nodejs.org^) y vuelve a ejecutar,
        echo              o pide el repositorio con la carpeta dist ya incluida.
    )
)

REM ── Abrir el navegador a los 3 segundos ────────────────────────────────────
start "" /b cmd /c "timeout /t 3 >nul & start http://localhost:%PORT%"

REM ── Arrancar el servidor ───────────────────────────────────────────────────
echo ^>^>^> Iniciando EmailAnalyzer en http://localhost:%PORT% ...
pushd "%SERVER%"
"%VENV%\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port %PORT% --log-level info
popd
