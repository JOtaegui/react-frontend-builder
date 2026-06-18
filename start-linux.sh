#!/usr/bin/env bash
# ============================================================================
#  EmailAnalyzer — Lanzador para Linux Mint (y derivados Ubuntu/Debian)
#  Tras clonar el repo:   bash start-linux.sh
#    - Instala lo que falte (python3, venv, pip) con apt automáticamente.
#    - Crea el entorno, instala dependencias y arranca el servidor.
#    - Compila el frontend SOLO si falta (el repo ya trae dist/).
#    - Abre la app en FIREFOX. No hay que hacer nada más.
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$ROOT/server"
VENV="$SERVER/venv"
PORT=8787
URL="http://localhost:$PORT"

# En Kali (y contenedores) a veces se corre como root: ahí no se usa sudo.
SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

# ── Abrir el navegador: en Linux usamos Firefox ───────────────────────────────
open_browser() {
    if command -v firefox >/dev/null 2>&1; then
        firefox "$1" >/dev/null 2>&1 &
    elif command -v firefox-esr >/dev/null 2>&1; then
        firefox-esr "$1" >/dev/null 2>&1 &
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$1" >/dev/null 2>&1 &
    else
        echo "    Abre tu navegador en: $1"
    fi
}

# ── Liberar el puerto si quedó un proceso anterior ────────────────────────────
if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
elif command -v lsof >/dev/null 2>&1; then
    lsof -ti ":$PORT" | xargs -r kill -9 >/dev/null 2>&1 || true
fi
sleep 0.5

# ── Configuración personal del usuario (~/.emailanalyzer/.env) ────────────────
CONFIG_DIR="$HOME/.emailanalyzer"
ENV_FILE="$CONFIG_DIR/.env"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << 'EOF'
# EmailAnalyzer — Configuración personal
# Las credenciales OAuth ya vienen incluidas en el repositorio (server/.env).
# Solo configura esto si quieres enviar informes de baja por tu propio SMTP:
# SMTP_USER=tu_correo@gmail.com
# SMTP_PASSWORD=xxxx xxxx xxxx xxxx
# BAJA_REPORT_DESTINATION=tu_correo@gmail.com
EOF
fi

# ── Variables de entorno ──────────────────────────────────────────────────────
export DOTENV_PATH="$ENV_FILE"
export DB_PATH="$CONFIG_DIR/osint_chile.db"
export STATIC_DIST_PATH="$ROOT/dist"
export FRONTEND_URL="$URL"
export GOOGLE_OAUTH_REDIRECT_URI="$URL/api/auth/gmail/callback"

# ── Crear entorno virtual e instalar dependencias (solo la primera vez) ───────
if [ ! -x "$VENV/bin/python3" ]; then
    echo ">>> Primera vez: preparando Python y dependencias..."

    # Asegurar paquetes del sistema. En distros con apt (Mint/Ubuntu/Debian/Kali)
    # instalamos python3+venv+pip y TAMBIÉN los headers de compilación: si tu
    # versión de Python no tiene wheel de lxml (p. ej. 3.13), pip lo compila desde
    # fuente y necesita libxml2/libxslt-dev + un compilador.
    if command -v apt-get >/dev/null 2>&1; then
        echo ">>> Instalando paquetes del sistema (puede pedir tu contraseña de sudo)..."
        $SUDO apt-get update -y || true
        $SUDO apt-get install -y python3 python3-venv python3-pip \
            python3-dev build-essential libxml2-dev libxslt1-dev zlib1g-dev || true
    elif ! python3 -c "import ensurepip, venv" >/dev/null 2>&1; then
        echo "ERROR: falta python3-venv y no encontré apt-get."
        echo "       Instala python3, python3-venv, python3-pip y los headers de tu distro."
        exit 1
    fi

    echo ">>> Creando entorno virtual e instalando dependencias (tarda unos minutos)..."
    python3 -m venv "$VENV"
    "$VENV/bin/python3" -m pip install --upgrade pip
    "$VENV/bin/python3" -m pip install -r "$SERVER/requirements.txt"
fi

# ── Construir el frontend SOLO si no está compilado ───────────────────────────
if [ ! -f "$ROOT/dist/index.html" ]; then
    echo ">>> No existe dist/: construyendo interfaz..."
    if ! command -v npm >/dev/null 2>&1; then
        if command -v apt-get >/dev/null 2>&1; then
            echo ">>> Instalando Node.js/npm (puede pedir tu contraseña de sudo)..."
            $SUDO apt-get install -y nodejs npm
        else
            echo "ADVERTENCIA: no hay npm y no existe dist/. Instala Node.js y reintenta."
            exit 1
        fi
    fi
    ( cd "$ROOT" && npm install && npm run build )
fi

# ── Abrir Firefox a los 2 segundos ────────────────────────────────────────────
( sleep 2 && open_browser "$URL" ) &

# ── Arrancar el servidor ──────────────────────────────────────────────────────
echo ">>> Iniciando EmailAnalyzer en $URL ..."
cd "$SERVER"
"$VENV/bin/python3" -m uvicorn main:app \
    --host 127.0.0.1 \
    --port "$PORT" \
    --log-level info
