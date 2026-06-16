#!/usr/bin/env bash
# EmailAnalyzer.command
# Doble clic en Finder para arrancar. Abre el servidor y el browser.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$ROOT/server"
VENV="$SERVER/venv"
PORT=8787

# Matar cualquier proceso anterior en el mismo puerto
lsof -ti ":$PORT" | xargs kill -9 2>/dev/null || true
sleep 0.5

# ── Cargar .env del usuario ───────────────────────────────────────────────────
CONFIG_DIR="$HOME/.emailanalyzer"
ENV_FILE="$CONFIG_DIR/.env"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << 'EOF'
# EmailAnalyzer — Configuración personal
# Las credenciales OAuth ya vienen incluidas en el repositorio (server/.env).
# Solo necesitas configurar esto si quieres enviar informes de baja por SMTP
# en lugar de usar tu Gmail conectado.

# Opcional: SMTP propio (no necesario si conectas Gmail en la app)
# SMTP_USER=tu_correo@gmail.com
# SMTP_PASSWORD=xxxx xxxx xxxx xxxx
# BAJA_REPORT_DESTINATION=tu_correo@gmail.com
EOF
    echo ""
    echo "⚙  Primera vez: edita tu configuración en:"
    echo "   $ENV_FILE"
    echo ""
fi

# ── Exportar variables de entorno ─────────────────────────────────────────────
export DOTENV_PATH="$ENV_FILE"
export DB_PATH="$CONFIG_DIR/osint_chile.db"
export STATIC_DIST_PATH="$ROOT/dist"
export FRONTEND_URL="http://localhost:$PORT"
export GOOGLE_OAUTH_REDIRECT_URI="http://localhost:$PORT/api/auth/gmail/callback"

# ── Crear entorno virtual e instalar dependencias (solo la primera vez) ───────
if [ ! -x "$VENV/bin/python3" ]; then
    echo ">>> Primera vez: creando entorno virtual e instalando dependencias..."
    echo "    (esto puede tardar algunos minutos)"
    python3 -m venv "$VENV"
    "$VENV/bin/python3" -m pip install --upgrade pip
    "$VENV/bin/python3" -m pip install -r "$SERVER/requirements.txt"
fi

# ── Construir frontend si no existe o hay cambios en src/ ────────────────────
NEEDS_BUILD=false
if [ ! -d "$ROOT/dist" ]; then
    NEEDS_BUILD=true
elif [ -d "$ROOT/src" ] && [ "$(find "$ROOT/src" -newer "$ROOT/dist/index.html" -name '*.tsx' -o -name '*.ts' 2>/dev/null | head -1)" != "" ]; then
    NEEDS_BUILD=true
fi

if [ "$NEEDS_BUILD" = "true" ]; then
    echo ">>> Construyendo frontend..."
    cd "$ROOT"
    npm run build
fi

# ── Arrancar el servidor ──────────────────────────────────────────────────────
echo ">>> Iniciando EmailAnalyzer en http://localhost:$PORT ..."
cd "$SERVER"

# Abrir browser después de 2 segundos
(sleep 2 && open "http://localhost:$PORT") &

"$VENV/bin/python3" -m uvicorn main:app \
    --host 127.0.0.1 \
    --port "$PORT" \
    --log-level info
