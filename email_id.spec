# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for EmailAnalyzer — standalone macOS app.

What gets bundled:
  - All Python server code (launcher, main, config, db, core/*, models/*, modules/*)
  - The React production build (dist/)
  - Static data files (chile_ip_ranges.csv if it exists)

User data (DB, .env, logs) is stored in ~/.emailanalyzer/ at runtime.
"""

from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821 — injected by PyInstaller
SERVER = ROOT / "server"
DIST   = ROOT / "dist"     # React production build (must exist before building)

block_cipher = None

a = Analysis(
    [str(SERVER / "launcher.py")],
    pathex=[str(SERVER)],           # server/ is the root for imports
    binaries=[],
    datas=[
        # React frontend
        (str(DIST), "dist"),
        # OAuth credentials (shared, ships with the repo)
        *([(str(SERVER / ".env"), ".")] if (SERVER / ".env").exists() else []),
        # Optional static IP range CSV
        *([(str(SERVER / "chile_ip_ranges.csv"), ".")] if (SERVER / "chile_ip_ranges.csv").exists() else []),
    ],
    hiddenimports=[
        # uvicorn internals (not auto-detected)
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.protocols.websockets.wsproto_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        # starlette (FastAPI base)
        "starlette",
        "starlette.routing",
        "starlette.middleware",
        "starlette.middleware.cors",
        "starlette.staticfiles",
        "starlette.responses",
        # pydantic v2
        "pydantic",
        "pydantic.v1",
        "pydantic_core",
        # async / networking
        "anyio",
        "anyio._backends._asyncio",
        "anyio._backends._trio",
        "h11",
        "httpx",
        "httpcore",
        "aiosqlite",
        # email / SMTP (stdlib, but sometimes missed)
        "email",
        "email.mime",
        "email.mime.text",
        "email.mime.multipart",
        "smtplib",
        # html parsing
        "bs4",
        "lxml",
        "lxml.etree",
        # PDF (pypdf)
        "pypdf",
        # dotenv
        "dotenv",
        # app server modules
        "config",
        "main",
        "db",
        "core.email_identification",
        "core.email_sender",
        "core.gmail_oauth",
        "core.ip_classification",
        "core.orchestrator",
        "core.personal_data",
        "core.personal_data.address_extractor",
        "core.personal_data.name_extractor",
        "core.personal_data.phone_extractor",
        "core.personal_data.plate_extractor",
        "core.personal_data.rut_extractor",
        "core.personal_data.cross_validator",
        "models.schemas",
        "modules.base",
        "modules.diario_oficial",
        "modules.emails_publicos",
        "modules.empresas",
        "modules.hibp",
        "modules.instituciones_publicas",
        "modules.nryf",
        "modules.pjud",
        "modules.servel",
        "modules.sii",
        "utils.scraping",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude heavy scraping deps not needed for the email flow
    excludes=[
        "selenium",
        "undetected_chromedriver",
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EmailAnalyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=True,     # macOS: handle Finder open events
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="EmailAnalyzer",
)

app = BUNDLE(  # noqa: F821
    coll,
    name="EmailAnalyzer.app",
    icon=None,
    bundle_identifier="cl.titulo.emailanalyzer",
    info_plist={
        "CFBundleName":             "Email Analyzer",
        "CFBundleDisplayName":      "Email Analyzer",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion":          "1.0.0",
        "NSHighResolutionCapable":  True,
        "LSBackgroundOnly":         False,
        "NSRequiresAquaSystemAppearance": False,
    },
)
