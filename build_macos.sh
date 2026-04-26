#!/usr/bin/env bash
# build_macos.sh — Builds EmailAnalyzer.app for macOS
#
# Usage:
#   chmod +x build_macos.sh
#   ./build_macos.sh
#
# Output: release/EmailAnalyzer.app
# Config: ~/.emailanalyzer/.env  (created on first run with a template)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVER="$ROOT/server"
VENV="$SERVER/venv"
PYTHON="$VENV/bin/python3"
PIP="$VENV/bin/pip"
RELEASE="$ROOT/release"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step()  { echo -e "${GREEN}>>> $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠  $*${NC}"; }
error() { echo -e "${RED}✗  $*${NC}"; exit 1; }

# ── Checks ────────────────────────────────────────────────────────────────────
[ -d "$VENV" ] || error "Server venv not found at $VENV. Run: cd server && python3 -m venv venv && venv/bin/pip install -r requirements.txt"
command -v node >/dev/null 2>&1 || error "Node.js not found. Install via brew: brew install node"

# ── 1. Build React frontend ───────────────────────────────────────────────────
step "Building React frontend…"
cd "$ROOT"
npm run build
[ -d "$ROOT/dist" ] || error "React build failed — dist/ not found"
step "React build complete ($(du -sh "$ROOT/dist" | cut -f1))"

# ── 2. Install PyInstaller ────────────────────────────────────────────────────
step "Installing PyInstaller in server venv…"
"$PIP" install pyinstaller --quiet --upgrade

# ── 3. Run PyInstaller ────────────────────────────────────────────────────────
step "Bundling Python app with PyInstaller…"
cd "$ROOT"
"$PYTHON" -m PyInstaller email_id.spec \
    --clean \
    --noconfirm \
    --distpath "$RELEASE"

APP="$RELEASE/EmailAnalyzer.app"
[ -d "$APP" ] || error "PyInstaller failed — EmailAnalyzer.app not found in release/"

# ── 4. Create ~/.emailanalyzer/.env template ──────────────────────────────────
CONFIG_DIR="$HOME/.emailanalyzer"
ENV_FILE="$CONFIG_DIR/.env"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$ENV_FILE" ]; then
    step "Creating config template at $ENV_FILE…"
    cat > "$ENV_FILE" << 'EOF'
# EmailAnalyzer Configuration
# Edit this file with your credentials, then relaunch the app.

# ── Gmail SMTP (para enviar informes de baja) ─────────────────────────────────
# 1. Activa "Verificación en dos pasos" en tu cuenta Google
# 2. Ve a: Cuenta Google → Seguridad → Contraseñas de aplicaciones
# 3. Crea una contraseña para "Correo" → copia las 16 letras
SMTP_USER=tu_correo@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx

# Dirección donde recibirás los informes de baja (puede ser la misma)
BAJA_REPORT_DESTINATION=tu_correo@gmail.com

# ── Gmail OAuth (para sincronizar tu bandeja) ─────────────────────────────────
# 1. Crea un proyecto en https://console.cloud.google.com
# 2. Activa la Gmail API
# 3. Crea credenciales OAuth → Aplicación de escritorio
# 4. En "URIs de redireccionamiento autorizados" agrega:
#    http://localhost:8787/api/auth/gmail/callback
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=

# ── Opcional ──────────────────────────────────────────────────────────────────
# HIBP_API_KEY=          # HaveIBeenPwned (filtraciones de datos)
# BRAVE_SEARCH_API_KEY=  # Búsqueda de emails públicos
EOF
    warn "Config template created at $ENV_FILE"
    warn "Edita el archivo con tus credenciales antes de usar la app."
else
    step "Config file already exists at $ENV_FILE (not overwritten)"
fi

# ── 5. Done ───────────────────────────────────────────────────────────────────
APP_SIZE=$(du -sh "$APP" | cut -f1)

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           EmailAnalyzer.app listo ✅                     ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  App:    $APP"
echo "  Tamaño: $APP_SIZE"
echo "  Config: $ENV_FILE"
echo ""
echo "  Para instalar: arrastra EmailAnalyzer.app a /Applications"
echo ""
echo "  Primero edita tu configuración:"
echo "    open $ENV_FILE"
echo ""
echo "  Luego abre la app (doble clic) o:"
echo "    open '$APP'"
echo ""
