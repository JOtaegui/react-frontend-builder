"""
_data.py — Datos estáticos de clasificación de dominios.

Para agregar una empresa nueva:  añade una entrada a KNOWN_COMPANIES.
Para ignorar un dominio nuevo:   añade a IGNORE_DOMAINS.
No hay lógica aquí — solo tablas de lookup.

Campos de KNOWN_COMPANIES:
  company   : nombre visible
  type      : categoría (ver TYPE_LABELS en el frontend)
  is_chilean: bool
  risk      : "high" | "medium" | "low"
  data_types: lista de tipos de datos que SIEMPRE retiene (sin importar actividad)
              (complementa la inferencia por actividad de _classifier.py)
"""
from __future__ import annotations

# ── Empresas conocidas ────────────────────────────────────────────────────────
KNOWN_COMPANIES: dict[str, dict] = {
    # ── Retail / E-commerce ──────────────────────────────────────────────────
    "falabella.com":       {"company": "Falabella",         "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "ripley.cl":           {"company": "Ripley",             "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "paris.cl":            {"company": "Paris / Cencosud",   "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "lider.cl":            {"company": "Lider / Walmart",    "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "walmart.cl":          {"company": "Walmart Chile",      "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "jumbo.cl":            {"company": "Jumbo / Cencosud",   "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "hites.com":           {"company": "Hites",              "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "corona.cl":           {"company": "Corona",             "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "tricot.cl":           {"company": "Tricot",             "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "abcdin.cl":           {"company": "ABC Din",            "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "lacuracao.cl":        {"company": "La Curacao",         "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "sodimac.com":         {"company": "Sodimac",            "type": "retail",       "is_chilean": True,  "risk": "medium", "data_types": []},
    "easy.cl":             {"company": "Easy",               "type": "retail",       "is_chilean": True,  "risk": "low",    "data_types": []},
    "pcfactory.cl":        {"company": "PC Factory",         "type": "retail",       "is_chilean": True,  "risk": "low",    "data_types": []},
    "mercadolibre.cl":     {"company": "MercadoLibre",       "type": "marketplace",  "is_chilean": False, "risk": "medium", "data_types": []},
    "amazon.com":          {"company": "Amazon",             "type": "marketplace",  "is_chilean": False, "risk": "medium", "data_types": []},
    # ── Banca / Finanzas ─────────────────────────────────────────────────────
    "bancoestado.cl":      {"company": "BancoEstado",        "type": "banca",        "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos financieros", "historial de transacciones"]},
    "santander.cl":        {"company": "Santander",          "type": "banca",        "is_chilean": False, "risk": "high",   "data_types": ["RUT", "datos financieros", "historial de transacciones"]},
    "bci.cl":              {"company": "BCI",                "type": "banca",        "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos financieros", "historial de transacciones"]},
    "bancochile.cl":       {"company": "Banco de Chile",     "type": "banca",        "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos financieros", "historial de transacciones"]},
    "scotiabank.cl":       {"company": "Scotiabank",         "type": "banca",        "is_chilean": False, "risk": "high",   "data_types": ["RUT", "datos financieros", "historial de transacciones"]},
    "itau.cl":             {"company": "Itaú",               "type": "banca",        "is_chilean": False, "risk": "high",   "data_types": ["RUT", "datos financieros", "historial de transacciones"]},
    "coopeuch.cl":         {"company": "Coopeuch",           "type": "banca",        "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos financieros"]},
    "cmrfalabella.cl":     {"company": "CMR Falabella",      "type": "fintech",      "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos financieros"]},
    # ── Salud / ISAPRE ───────────────────────────────────────────────────────
    "fonasa.cl":           {"company": "FONASA",             "type": "salud",        "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos de salud"]},
    "isaprebancochile.cl": {"company": "Isapre BancoChile",  "type": "salud",        "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos de salud"]},
    "cruzblanca.cl":       {"company": "Cruz Blanca",        "type": "salud",        "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos de salud"]},
    "colmena.cl":          {"company": "Colmena",            "type": "salud",        "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos de salud"]},
    "consalud.cl":         {"company": "Consalud",           "type": "salud",        "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos de salud"]},
    "banmedica.cl":        {"company": "Banmédica",          "type": "salud",        "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos de salud"]},
    # ── Telecomunicaciones ───────────────────────────────────────────────────
    "entel.cl":            {"company": "Entel",              "type": "telecomunicaciones", "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "dirección", "historial de llamadas"]},
    "movistar.cl":         {"company": "Movistar",           "type": "telecomunicaciones", "is_chilean": False, "risk": "high",   "data_types": ["RUT", "dirección", "historial de llamadas"]},
    "claro.cl":            {"company": "Claro",              "type": "telecomunicaciones", "is_chilean": False, "risk": "high",   "data_types": ["RUT", "dirección", "historial de llamadas"]},
    "wom.cl":              {"company": "WOM",                "type": "telecomunicaciones", "is_chilean": True,  "risk": "medium", "data_types": ["RUT", "dirección"]},
    "gtd.cl":              {"company": "GTD",                "type": "telecomunicaciones", "is_chilean": True,  "risk": "medium", "data_types": ["RUT", "dirección"]},
    "vtr.net":             {"company": "VTR",                "type": "telecomunicaciones", "is_chilean": False, "risk": "high",   "data_types": ["RUT", "dirección"]},
    # ── Data Brokers / Directorios ───────────────────────────────────────────
    "nombrerutyfirma.cl":  {"company": "NombreRutYFirma",    "type": "data_broker",  "is_chilean": True,  "risk": "high",   "data_types": ["nombre", "RUT", "dirección", "teléfono"]},
    "truecaller.com":      {"company": "Truecaller",         "type": "data_broker",  "is_chilean": False, "risk": "high",   "data_types": ["nombre", "teléfono"]},
    "whitepages.com":      {"company": "Whitepages",         "type": "data_broker",  "is_chilean": False, "risk": "high",   "data_types": ["nombre", "dirección", "teléfono"]},
    "spokeo.com":          {"company": "Spokeo",             "type": "data_broker",  "is_chilean": False, "risk": "high",   "data_types": ["nombre", "dirección", "teléfono"]},
    "pipl.com":            {"company": "Pipl",               "type": "data_broker",  "is_chilean": False, "risk": "high",   "data_types": ["nombre", "dirección", "email"]},
    "equifax.cl":          {"company": "Equifax Chile",      "type": "data_broker",  "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "historial crediticio"]},
    "transunion.cl":       {"company": "TransUnion",         "type": "data_broker",  "is_chilean": False, "risk": "high",   "data_types": ["RUT", "historial crediticio"]},
    # ── Gobierno ─────────────────────────────────────────────────────────────
    "servel.cl":           {"company": "SERVEL",             "type": "gobierno",     "is_chilean": True,  "risk": "low",    "data_types": []},
    "sii.cl":              {"company": "SII",                "type": "gobierno",     "is_chilean": True,  "risk": "low",    "data_types": ["RUT"]},
    "registrocivil.cl":    {"company": "Registro Civil",     "type": "gobierno",     "is_chilean": True,  "risk": "low",    "data_types": ["RUT"]},
    "chileatiende.gob.cl": {"company": "ChileAtiende",       "type": "gobierno",     "is_chilean": True,  "risk": "low",    "data_types": []},
    "previred.com":        {"company": "Previred",           "type": "gobierno",     "is_chilean": True,  "risk": "medium", "data_types": ["RUT", "datos laborales"]},
    # ── Delivery / Transporte ────────────────────────────────────────────────
    "pedidosya.cl":        {"company": "PedidosYa",          "type": "delivery",     "is_chilean": False, "risk": "medium", "data_types": ["dirección"]},
    "rappi.com":           {"company": "Rappi",              "type": "delivery",     "is_chilean": False, "risk": "medium", "data_types": ["dirección"]},
    "ubereats.com":        {"company": "Uber Eats",          "type": "delivery",     "is_chilean": False, "risk": "medium", "data_types": ["dirección"]},
    "uber.com":            {"company": "Uber",               "type": "transporte",   "is_chilean": False, "risk": "medium", "data_types": ["ubicación GPS"]},
    "cabify.com":          {"company": "Cabify",             "type": "transporte",   "is_chilean": False, "risk": "medium", "data_types": ["ubicación GPS"]},
    # ── Redes sociales / Big Tech ─────────────────────────────────────────────
    "facebook.com":        {"company": "Facebook / Meta",    "type": "social",       "is_chilean": False, "risk": "high",   "data_types": ["perfil", "comportamiento"]},
    "instagram.com":       {"company": "Instagram / Meta",   "type": "social",       "is_chilean": False, "risk": "high",   "data_types": ["perfil", "comportamiento"]},
    "twitter.com":         {"company": "Twitter / X",        "type": "social",       "is_chilean": False, "risk": "medium", "data_types": []},
    "x.com":               {"company": "X (Twitter)",        "type": "social",       "is_chilean": False, "risk": "medium", "data_types": []},
    "linkedin.com":        {"company": "LinkedIn",           "type": "social",       "is_chilean": False, "risk": "medium", "data_types": ["perfil profesional"]},
    "tiktok.com":          {"company": "TikTok",             "type": "social",       "is_chilean": False, "risk": "high",   "data_types": ["comportamiento", "biométrico"]},
    "apple.com":           {"company": "Apple",              "type": "tech",         "is_chilean": False, "risk": "medium", "data_types": []},
    "microsoft.com":       {"company": "Microsoft",          "type": "tech",         "is_chilean": False, "risk": "medium", "data_types": []},
    # ── AFP / Previsión ──────────────────────────────────────────────────────
    "afphabitat.cl":       {"company": "AFP Habitat",        "type": "afp",          "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos financieros", "historial laboral"]},
    "afpmodelo.cl":        {"company": "AFP Modelo",         "type": "afp",          "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos financieros", "historial laboral"]},
    "afpcuprum.cl":        {"company": "AFP Cuprum",         "type": "afp",          "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos financieros", "historial laboral"]},
    "afpplanvital.cl":     {"company": "AFP PlanVital",      "type": "afp",          "is_chilean": True,  "risk": "high",   "data_types": ["RUT", "datos financieros", "historial laboral"]},
    "svs.cl":              {"company": "CMF / SVS",          "type": "regulador",    "is_chilean": True,  "risk": "low",    "data_types": []},
    # ── Educación ────────────────────────────────────────────────────────────
    "uchile.cl":           {"company": "U. de Chile",        "type": "educacion",    "is_chilean": True,  "risk": "low",    "data_types": []},
    "puc.cl":              {"company": "UC",                 "type": "educacion",    "is_chilean": True,  "risk": "low",    "data_types": []},
    "usach.cl":            {"company": "USACH",              "type": "educacion",    "is_chilean": True,  "risk": "low",    "data_types": []},
    "demre.cl":            {"company": "DEMRE",              "type": "educacion",    "is_chilean": True,  "risk": "medium", "data_types": ["RUT"]},
}

# ── Dominios que no aportan información personal — se ignoran ─────────────────
# Para agregar uno nuevo: añade el string aquí. Nada más.
IGNORE_DOMAINS: frozenset[str] = frozenset({
    # Motores de búsqueda
    "google.com", "google.cl", "bing.com", "yahoo.com", "duckduckgo.com",
    # Infraestructura Google
    "googleapis.com", "gstatic.com", "accounts.google.com",
    "chrome.google.com", "chromewebstore.google.com",
    # Video
    "youtube.com", "youtu.be", "vimeo.com",
    # Código / Dev
    "github.com", "githubusercontent.com", "gitlab.com",
    "stackoverflow.com", "stackexchange.com",
    # CDNs / infraestructura
    "cloudflare.com", "akamaized.net", "fastly.net", "cdn.net",
    "jsdelivr.net", "unpkg.com", "jquery.com",
    # Conocimiento
    "wikipedia.org", "wikimedia.org",
    # Observabilidad / telemetría
    "newrelic.com", "datadog.com", "sentry.io", "segment.com",
    # Localhost
    "localhost", "127.0.0.1", "0.0.0.0",
})
