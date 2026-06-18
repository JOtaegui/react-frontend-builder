# EmailAnalyzer — Instalación y uso (Linux y Windows)

Aplicación de análisis de exposición de datos personales (OSINT Chile).

- **Backend**: FastAPI (Python) que corre en `http://localhost:8787`.
- **Frontend**: React + Vite + TypeScript. Ya viene **compilado** en `dist/` y el
  **mismo backend lo sirve** en el puerto 8787 (no necesitas un servidor aparte).

> La forma recomendada es usar el **lanzador** de tu sistema operativo: clonas el
> repo y lo ejecutas — instala lo que falte, arranca el servidor y abre el navegador.

---

## Inicio rápido

### 🐧 Linux (Kali, Mint, Ubuntu, Debian y derivados)

```bash
# 1. (si no tienes git)   sudo apt-get install -y git
git clone https://github.com/JOtaegui/react-frontend-builder.git
cd react-frontend-builder
bash start-linux.sh
```

Eso es todo. El script:
- Instala **python3 / venv / pip** con `apt` si faltan (en Kali, como root, **no pide sudo**).
- Crea el entorno e instala dependencias (la **primera vez** tarda unos minutos).
- Abre la app en **Firefox** (`firefox` o `firefox-esr`) en `http://localhost:8787`.

Para **detener** la app: `Ctrl + C` en la terminal.

### 🪟 Windows (incluye Windows on ARM / Mac con Apple Silicon)

```bat
:: 1. Instala Git una vez:  https://git-scm.com/download/win
git clone https://github.com/JOtaegui/react-frontend-builder.git
cd react-frontend-builder
```

Luego **doble clic en `start.bat`** (o ejecútalo desde la consola). El script:
- Instala **Python (x64)** automáticamente con `winget` si falta — x64 funciona en
  Windows normal y en Windows ARM (emulado), y así `pip` encuentra todos los paquetes.
- Crea el entorno, instala dependencias y arranca el servidor.
- Abre la app en tu **navegador por defecto** en `http://localhost:8787`.

> Si la primera vez instala Python y te dice *"vuelve a ejecutar start.bat"*, ciérralo
> y haz doble clic otra vez (es solo para tomar el PATH nuevo).
>
> Si SmartScreen avisa *"Windows protegió tu PC"* → **"Más información" → "Ejecutar de todas formas"**.

Para **detener** la app: cierra la ventana negra (consola).

---

## Requisitos

| Programa | Linux | Windows |
|----------|-------|---------|
| **Git** | `sudo apt-get install git` | https://git-scm.com/download/win |
| **Python 3.10–3.12** | lo instala el script (`apt`) | lo instala el script (`winget`, **x64**) |
| **Node.js** | solo si falta `dist/` (lo instala el script) | solo si falta `dist/` (lo instala el script) |
| **Chrome/Chromium** | opcional* | opcional* |

\* Solo lo necesitan los módulos de *scraping en vivo* (Selenium). La **interfaz web
funciona en cualquier navegador** (Firefox en Linux, Edge en Windows). Como el repo
ya trae `dist/` compilado, **Node normalmente no hace falta**.

---

## Qué hace el lanzador (ambos sistemas)

1. Crea el entorno virtual de Python en `server/venv` e instala `server/requirements.txt`.
2. Compila el frontend **solo si falta `dist/`** (el repo ya lo incluye).
3. Define las variables de entorno necesarias (entre ellas `STATIC_DIST_PATH`, que le
   dice al backend que **también sirva el frontend**).
4. Abre el navegador y arranca `uvicorn` en el puerto **8787**.

---

## Opción manual (paso a paso)

Útil si el lanzador falla o quieres entender cada parte.

### Linux

```bash
# Backend
python3 -m venv server/venv
source server/venv/bin/activate
pip install --upgrade pip
pip install -r server/requirements.txt

# Frontend: SOLO si no existe dist/ (necesita Node.js)
# npm install && npm run build

# Arrancar (sirviendo el frontend)
export STATIC_DIST_PATH="$PWD/dist"
export DB_PATH="$HOME/.emailanalyzer/osint_chile.db"
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8787
```

### Windows

```bat
:: Backend
python -m venv server\venv
server\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r server\requirements.txt

:: Frontend: SOLO si no existe dist\ (necesita Node.js)
:: npm install && npm run build

:: Arrancar (sirviendo el frontend)
set "STATIC_DIST_PATH=%cd%\dist"
set "DB_PATH=%USERPROFILE%\.emailanalyzer\osint_chile.db"
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8787
```

Luego abre **http://localhost:8787**.

> Sin `STATIC_DIST_PATH` el backend solo expone la API y la página no carga.

---

## Configuración opcional (`.env`)

La app **funciona sin configurar nada**. Algunas funciones extra requieren credenciales.
El lanzador crea un `.env` personal en:

- **Linux/Mac**: `~/.emailanalyzer/.env`
- **Windows**: `%USERPROFILE%\.emailanalyzer\.env`

| Variable | Función |
|----------|---------|
| `SMTP_USER`, `SMTP_PASSWORD` | Enviar informes de baja por tu Gmail (usa un **App Password**, no tu clave normal) |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | Conectar y analizar tu Gmail |
| `GEMINI_API_KEY` + `EMAIL_EXTRACTION_PROVIDER=gemini` | Enriquecer la detección con IA (si no, usa heurística local) |
| `HIBP_API_KEY`, `BRAVE_SEARCH_API_KEY` | APIs externas opcionales |

> **App Password** de Gmail: activa la verificación en 2 pasos en
> https://myaccount.google.com/security y genéralo en https://myaccount.google.com/apppasswords

---

## Exportar resultados a Excel

En la vista **Consolidada** (`/consolidado`), arriba a la derecha, el botón
**"Exportar a Excel"** descarga un `.xlsx` con todo: resumen, perfil consolidado,
empresas, datos personales, cabeceras (IPs), dominios, filtraciones y evidencia.
Se abre con Excel, **LibreOffice Calc** (preinstalado en Linux), Numbers o Google Sheets.

---

## Modo desarrollo (recarga en caliente)

Dos terminales:

**Frontend (Vite):**
```bash
npm install      # solo la primera vez
npm run dev      # abre http://localhost:5173
```

**Backend (con el venv activado):**
```bash
# Linux:   source server/venv/bin/activate
# Windows: server\venv\Scripts\activate
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8787 --reload
```

En este modo el frontend corre en `5173` y habla con el backend en `8787` (CORS ya
configurado). **No** definas `STATIC_DIST_PATH` en modo desarrollo.

---

## Solución de problemas

### Linux
| Síntoma | Solución |
|---------|----------|
| `The virtual environment was not created… ensurepip` | `sudo apt-get install -y python3-venv python3-pip` |
| Puerto 8787 ocupado | `fuser -k 8787/tcp` (o `kill` del proceso anterior) |
| No abre el navegador | Abre manualmente `http://localhost:8787` |
| `permission denied` al correr el script | Usa `bash start-linux.sh` (o `chmod +x start-linux.sh`) |
| Un módulo de scraping (Selenium) falla | Instala Chromium: `sudo apt-get install -y chromium` |

### Windows
| Síntoma | Solución |
|---------|----------|
| `'python' no se reconoce` | El stub falso de la Store; el script instala el Python real. Reintenta `start.bat`. |
| `winget` no existe | Instala Python a mano (x64) desde https://www.python.org/downloads/windows/ marcando **"Add Python to PATH"**. |
| SmartScreen bloquea `start.bat` | "Más información" → "Ejecutar de todas formas". |
| La página no carga | Asegúrate de que exista `dist\index.html` y de definir `STATIC_DIST_PATH`. |

---

## TL;DR

**Linux (Kali/Mint/Ubuntu):**
```bash
git clone https://github.com/JOtaegui/react-frontend-builder.git
cd react-frontend-builder
bash start-linux.sh
```

**Windows:**
```bat
git clone https://github.com/JOtaegui/react-frontend-builder.git
cd react-frontend-builder
:: doble clic en start.bat
```

Abrir: **http://localhost:8787**
