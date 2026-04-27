"""
address_extractor.py — Extractor robusto de direcciones chilenas v2.

Mejoras respecto a la versión anterior
---------------------------------------
1. Lista de comunas ampliada: cubre las 346 comunas de Chile agrupadas por región.
   Detectar el nombre de una comuna dentro de la ventana suma puntos de confirmación.

2. Regex de calle sin prefijo (BARE_STREET_PATTERN) más permisiva:
   - Acepta nombres de una sola palabra si son ≥ 5 caracteres (e.g., "Alemania 432").
   - Captura el fragmento de comuna/ciudad que sigue a la dirección como parte
     del candidato para mejorar la completitud.

3. Detección de estructura HTML/plain-text de emails:
   - `_extract_labeled_candidates` ahora escanea bloques de hasta 5 líneas después
     del label, no solo la siguiente.
   - Se reconocen labels en inglés frecuentes en sistemas de e-commerce
     (Shipping address, Deliver to, Ship to).

4. Hooks de verificación cruzada:
   - `extract_chilean_address_matches_with_context` acepta teléfonos y nombres
     para subir el score cuando coinciden en la ventana.

5. Normalización final mejorada:
   - Capitaliza correctamente incluyendo preposiciones chilenas.
   - Elimina trailing de teléfono, email, RUT y fecha con patrones más amplios.

6. API pública compatible con la versión anterior:
   - extract_chilean_addresses(content) → list[str]
   - extract_chilean_address_matches(content) → list[AddressMatch]
   - select_primary_address(values, counts, scores) → str | None
   - address_fingerprint(value) → str
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

# ---------------------------------------------------------------------------
# Importaciones opcionales
# ---------------------------------------------------------------------------
try:
    from .name_extractor import extract_name_candidates  # type: ignore
    from .rut_extractor import extract_chilean_ruts      # type: ignore
except ImportError:
    def extract_name_candidates(content: str) -> list[str]:  # type: ignore
        return []
    def extract_chilean_ruts(content: str) -> list[str]:  # type: ignore
        return []


# ---------------------------------------------------------------------------
# Comunas de Chile — lista completa (346 comunas)
# Fuente: INE / División Político-Administrativa de Chile
# ---------------------------------------------------------------------------

_COMUNAS_CHILE: frozenset[str] = frozenset({
    # Región Metropolitana
    "cerrillos", "cerro navia", "conchalí", "el bosque", "estacion central",
    "estación central", "huechuraba", "independencia", "la cisterna", "la florida",
    "la granja", "la pintana", "la reina", "las condes", "lo barnechea",
    "lo espejo", "lo prado", "macul", "maipu", "maipú", "miraflores",
    "nunoa", "nuñoa", "padre hurtado", "penaflor", "peñaflor",
    "peñalolen", "penalolen", "providencia", "pudahuel", "quilicura",
    "quinta normal", "recoleta", "renca", "san bernardo", "san joaquin",
    "san joaquín", "san miguel", "san ramon", "san ramón", "santiago",
    "vitacura", "buin", "calera de tango", "colina", "curacavi", "curacaví",
    "el monte", "isla de maipo", "isla de maipú", "lampa", "melipilla",
    "paine", "peñaflor", "pirque", "san jose de maipo", "san josé de maipo",
    "talagante", "tiltil", "til til",
    # V Región
    "algarrobo", "cabildo", "calera", "calle larga", "cartagena", "casablanca",
    "catemu", "con con", "concón", "el quisco", "el tabo", "hijuelas",
    "isla de pascua", "juan fernandez", "juan fernández", "la cruz", "la ligua",
    "llay llay", "llaillay", "limache", "los andes", "nogales", "olmue",
    "olmuée", "panquehue", "papudo", "petorca", "puchuncavi", "puchuncaví",
    "putaendo", "quillota", "quilpue", "quilpué", "quintero", "rinconada",
    "san antonio", "san esteban", "san felipe", "santa maria", "santa maría",
    "valparaiso", "valparaíso", "villa alemana", "vina del mar", "viña del mar",
    "zapallar",
    # VI Región
    "chimbarongo", "codegua", "coinco", "coltauco", "donihue", "graneros",
    "la estrella", "las cabras", "litueche", "lolol", "machali", "machalí",
    "malloa", "marchihue", "mostazal", "nancagua", "navidad", "olivar",
    "palmilla", "paredones", "peralillo", "peumo", "pichidegua", "pichilemu",
    "placilla", "pumanque", "quinta de tilcoco", "rancagua", "rengo",
    "requinoa", "san fernando", "san vicente", "santa cruz",
    # VII Región
    "cauquenes", "chanco", "colbun", "colbún", "constitution", "constitución",
    "curepto", "curico", "curicó", "empedrado", "hualane", "hualaňé",
    "licanten", "linares", "longavi", "longaví", "maule", "molina",
    "parral", "pelarco", "pelluhue", "pencahue", "rauco", "retiro",
    "romeral", "sagrada familia", "san clemente", "san javier",
    "san rafael", "teno", "vichuquen", "vichuquén", "villa alegre", "yerbas buenas",
    # VIII Región
    "arauco", "cabrero", "canete", "cañete", "chiguayante", "concepcion",
    "concepción", "contulmo", "coronel", "curanilahue", "florida",
    "hualpen", "hualpén", "hualqui", "laja", "lebu", "los alamos",
    "los álamos", "los angeles", "los ángeles", "lota", "mulchen",
    "mulchén", "nacimiento", "negrete", "penco", "quilaco", "quilleco",
    "san pedro de la paz", "san rosendo", "santa barbara", "santa bárbara",
    "santa juana", "talcahuano", "tirua", "tirao", "tome", "tomé",
    "tucapel", "yumbel",
    # IX Región
    "angol", "carahue", "cholchol", "collipulli", "cunco", "curacautin",
    "curacautín", "curarrehue", "ercilla", "freire", "galvarino",
    "gorbea", "lautaro", "loncoche", "lonquimay", "los sauces",
    "lumaco", "melipeuco", "nueva imperial", "padre las casas",
    "perquenco", "pitrufquen", "pitrufquén", "pucon", "pucón",
    "puren", "purén", "renaico", "saavedra", "temuco", "teodoro schmidt",
    "tolten", "toltén", "traiguen", "traiguén", "victoria", "vilcun",
    "vilcún", "villarrica",
    # XIV Región
    "futrono", "lago ranco", "lanco", "los lagos", "mafil", "mariquina",
    "paillaco", "panguipulli", "rio bueno", "río bueno", "valdivia",
    # X Región
    "ancud", "calbuco", "castro", "chaiten", "chaitén", "chiloe",
    "chiloé", "chonchi", "cochamo", "cochamó", "curaco de velez",
    "fresia", "frutillar", "hualaihue", "llanquihue", "los muermos",
    "maullin", "maullín", "osorno", "puerto montt", "puerto varas",
    "purranque", "puyehue", "queilen", "quellon", "quellón", "quemchi",
    "quinchao", "rio negro", "río negro", "san juan de la costa",
    "san pablo",
    # XI Región
    "aisen", "aysén", "chile chico", "coyhaique", "guaitecas",
    "lago verde", "o'higgins", "ohiggins", "rio ibáñez", "tortel",
    # XII Región
    "antartica", "antártica", "cabo de hornos", "laguna blanca",
    "natales", "porvenir", "primavera", "punta arenas", "rio verde",
    "san gregorio", "timaukel", "torres del paine",
    # I Región
    "alto hospicio", "camiña", "colchane", "huara", "iquique",
    "pica", "pozo almonte",
    # II Región
    "antofagasta", "calama", "mejillones", "maria elena", "ollagüe",
    "san pedro de atacama", "sierra gorda", "taltal", "tocopilla",
    # III Región
    "alto del carmen", "caldera", "chanaral", "chañaral", "copiapo",
    "copiapó", "diego de almagro", "freirina", "huasco", "tierra amarilla",
    "vallenar",
    # IV Región
    "andacollo", "canela", "combarbala", "combarbalá", "copiapo",
    "coquimbo", "illapel", "la higuera", "la serena", "los vilos",
    "monte patria", "ovalle", "paiguano", "punitaqui",
    "rio hurtado", "río hurtado", "salamanca", "vicuna", "vicuña",
    # XV Región
    "arica", "camarones", "general lagos", "putre",
})

# ---------------------------------------------------------------------------
# Keywords de contexto
# ---------------------------------------------------------------------------

ADDRESS_LABEL_KEYWORDS: tuple[str, ...] = (
    "direccion de despacho", "direccion de envio", "direccion de entrega",
    "direccion cliente", "direccion del cliente", "domicilio",
    "shipping address", "delivery address", "ship to", "deliver to",
    "enviar a", "envio a", "despacho a", "entrega en",
    "entregaremos en", "entregaremos tu tarjeta en",
    "tu direccion", "su direccion", "direccion de facturacion",
    "lugar de entrega", "direccion de envio", "tu domicilio",
    "su domicilio", "direccion registrada", "direccion de residencia",
)

ORDER_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "pedido", "orden", "compra", "despacho", "envio", "entrega",
    "tracking", "seguimiento", "tarjeta", "solicitud",
    # English equivalents (Uber, Amazon, etc.)
    "delivery", "delivered", "pickup", "order", "shipment", "shipped",
    "dispatch", "address", "ship to", "deliver to",
)

LOCATION_HINT_KEYWORDS: tuple[str, ...] = (
    "comuna", "region", "región", "rm", "metropolitana", "santiago", "chile",
)

_ID_TOKENS: frozenset[str] = frozenset({
    "folio", "boleta", "factura", "orden", "pedido", "tracking",
    "seguimiento", "otp", "clave", "codigo", "pin",
    "transaccion", "cupon", "descuento",
    "tarjeta", "cuenta", "debito", "credito", "ultimos", "primeros", "digitos",
})

_NON_ADDRESS_HINTS: tuple[str, ...] = (
    "terminos", "términos", "suscripcion", "suscripción",
    "privacidad", "promocion", "promoción", "membresia", "membresía",
    "uber one", "centro de ayuda", "politica", "política",
)

_NEGATIVE_CONTEXT: tuple[str, ...] = (
    "retiro en tienda", "retiro en sucursal", "retira en", "showroom",
)
_SPORT_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "roja", "seleccion", "selección", "mundial", "fifa", "conmebol",
    "partido", "clasificatorias", "campeonato", "torneo", "sub 20", "sub-20",
)
_SUB_CATEGORY_PATTERN = re.compile(r"\bsub[\s-]?\d{1,2}\b", re.IGNORECASE)
_PROMO_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "hasta", "aprovecha", "oferta", "ofertas", "descuento", "dcto", "cupon", "cupón",
    "promo", "promocion", "promoción", "relampago", "relámpago", "black", "week", "friday",
    "cyber", "navidad", "off", "cuotas", "sin interes", "sin interés", "envio gratis", "envío gratis",
    "por poco tiempo", "solo por", "adicional", "beneficio", "liquidacion", "liquidación",
)

# ---------------------------------------------------------------------------
# Patrones de exclusión
# ---------------------------------------------------------------------------

# Frases que indican inicio de prosa (no son parte de una dirección)
_PROSE_BREAK_RE = re.compile(
    r"(?i)\b(?:"
    r"si\s+no\s+pued|si\s+no\s+puede|si\s+no\s+asist|si\s+desea|si\s+tienes|si\s+necesitas|si\s+quieres|"
    r"para\s+m[aá]s|para\s+realizar|para\s+ver\s+|para\s+obtener|para\s+acceder|"
    r"haz\s+clic|visita\s+nuestra|por\s+favor\s|ante\s+cualquier|"
    r"en\s+caso\s+de|recuerda\s+que|puedes\s+contact|escr[ií]benos|"
    r"cualquier\s+duda|atentamente|saludos\s+cord|gracias\s+por|"
    r"te\s+informamos|le\s+informamos|no\s+olvides|te\s+esperamos\s+en"
    r")"
)
_SENTENCE_END_RE = re.compile(r"[.!?]\s+[A-ZÁÉÍÓÚÜÑ]")

_DATE_PATTERN = re.compile(
    r"(?i)\b\d{1,2}\s+de\s+"
    r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|setiembre|octubre|noviembre|diciembre)"
    r"(?:\s+de\s+\d{4})?\b"
)
_URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_RUT_PATTERN = re.compile(r"\b\d{7,8}-[\dkK]\b")
_LONG_NUMBER_PATTERN = re.compile(r"\b\d{10,}\b")

# ---------------------------------------------------------------------------
# Patrones de label
# ---------------------------------------------------------------------------

_INLINE_LABEL_RE = re.compile(
    r"(?i)"
    r"(?:direccion\s+de\s+(?:despacho|envio|entrega)|direccion\s+(?:del?\s+)?cliente|"
    r"domicilio|shipping\s+address|delivery\s+address|ship\s+to|deliver\s+to|"
    r"enviar\s+a|envio\s+a|despacho\s+a|entrega\s+en|"
    r"entregaremos(?:\s+tu\s+tarjeta)?\s+en|"
    r"tu\s+(?:direccion|domicilio)|su\s+(?:direccion|domicilio)|"
    r"lugar\s+de\s+entrega|direccion\s+registrada|"
    r"direccion\s+de\s+residencia)"
    r"\s*[:\-–]?\s*(.+)"
)

# ---------------------------------------------------------------------------
# Patrones de trailing
# ---------------------------------------------------------------------------

_TRAILING_RE = re.compile(
    r"(?i)(?:[,.\s]*)?"
    r"(?:titular|destinatario|cliente|run(?:\s*o\s*rut)?|rut|folio|pedido|orden|"
    r"tel(?:e(?:fono|fono))?(?:\s+de\s+contacto)?|teléfono(?:\s+de\s+contacto)?|"
    r"cel(?:ular)?|fono|movil|móvil|correo(?:\s+electronico)?|email|"
    r"comuna|region|región|comentarios|notas|fecha|hora)"
    r"\s*[:\-–].*$"
)

_TRAILING_PHONE_RE = re.compile(
    r"(?i)\s*[-/]\s*(?:\+?56\s*)?(?:9|2)\s*[\d\s()./-]{8,}$"
)

# ---------------------------------------------------------------------------
# Patrones de extracción de calle
# ---------------------------------------------------------------------------

PREFIX_STREET_PATTERN = re.compile(
    r"(?i)\b"
    r"(?P<prefix>av(?:da)?\.?|avenida|calle|pasaje|psje\.?|camino|ruta|autopista|boulevard|blvd\.?|"
    r"pje\.?|parcela|poblacion|población|villa|condominio|conjunto)"
    r"\s+"
    r"(?P<n>[A-Za-záéíóúüñÁÉÍÓÚÜÑ][A-Za-záéíóúüñÁÉÍÓÚÜÑ0-9.\- ]{1,80}?)"
    r"\s+"
    r"(?P<number>\d{1,5})"
    r"(?P<extra>"
    r"(?:\s*,?\s*(?:depto?\.?|departamento|dpto?\.?|oficina|of\.?|piso|local|block|bloque|casa|torre)\s*[A-Za-z0-9\-]+)?"
    r"(?:\s*[-,]\s*[A-Za-záéíóúüñÁÉÍÓÚÜÑ][A-Za-záéíóúüñÁÉÍÓÚÜÑ0-9()\- ]{1,40}){0,3}"
    r")"
    r"\b",
    re.UNICODE,
)

# Sin prefijo: más permisivo ahora (1 palabra ≥ 5 chars o 2 palabras ≥ 3 chars)
BARE_STREET_PATTERN = re.compile(
    r"(?<![/\\\w])"
    r"(?P<n>"
    r"(?:"
        # Opción A: 2+ palabras
        r"[A-ZÁÉÍÓÚÜÑ][A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,}"
        r"(?:\s+[A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,}){1,5}"
    r"|"
        # Opción B: 1 palabra ≥ 5 chars (ej. "Alemania 432", "Ñuble 1230")
        r"[A-ZÁÉÍÓÚÜÑ][A-Za-záéíóúüñÁÉÍÓÚÜÑ]{4,}"
    r")"
    r")"
    r"\s+"
    r"(?P<number>\d{1,5})"
    r"(?P<extra>"
    r"(?:\s*,?\s*(?:depto?\.?|departamento|dpto?\.?|oficina|of\.?|piso|local|block|bloque|casa|torre)\s*[A-Za-z0-9\-]+)?"
    r"(?:\s*[-,]\s*[A-Za-záéíóúüñÁÉÍÓÚÜÑ][A-Za-záéíóúüñÁÉÍÓÚÜÑ0-9()\- ]{1,40}){0,3}"
    r")"
    r"(?![/\\\w])",
    re.UNICODE,
)

MAX_CONTENT_LENGTH_FOR_FULL_BARE_SCAN = 3500
MAX_PATTERN_MATCHES = 120
MAX_BARE_MATCHES_FAST = 24

# ---------------------------------------------------------------------------
# Stopwords y tokens genéricos
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset({
    "en", "de", "del", "la", "el", "los", "las", "rm",
    "metropolitana", "santiago", "chile", "region", "región",
    "comuna", "a", "con", "y", "o", "por", "para", "al",
})

_GENERIC_TOKENS: frozenset[str] = frozenset({
    "pedido", "orden", "compra", "entrega", "entregas", "envio",
    "despacho", "tracking", "seguimiento", "solicitud", "transferencia",
    "auto", "chile", "solo", "numero", "nro",
    "hasta", "aprovecha", "oferta", "ofertas", "descuento", "dcto",
    "cupon", "promo", "promocion", "relampago", "black", "week", "friday",
    "cyber", "navidad", "off", "cuotas", "interes", "gratis", "adicional",
    "liquidacion", "beneficio", "flash", "exclusiva", "exclusivo",
    # Financial/banking terms that appear before numbers but are NOT addresses
    "debito", "credito", "ultimos", "primeros", "digitos", "visa", "mastercard",
    "meses", "cuota", "saldo", "monto", "cargo", "abono", "pago", "cobro",
    # E-commerce / shipping cost context
    "costo", "tarifa", "valor", "precio", "subtotal", "total", "free",
})

# ---------------------------------------------------------------------------
# Dataclass pública
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AddressMatch:
    address: str
    evidence: str
    score: int = field(default=0, compare=False)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def extract_chilean_addresses(content: str) -> list[str]:
    """Devuelve lista de direcciones encontradas en *content*."""
    return [m.address for m in extract_chilean_address_matches(content)]


def extract_chilean_address_matches(content: str) -> list[AddressMatch]:
    """Devuelve hasta 5 AddressMatch ordenados por score descendente."""
    return extract_chilean_address_matches_with_context(content)


def extract_chilean_address_matches_with_context(
    content: str,
    nearby_phones: list[str] | None = None,
    nearby_names: list[str] | None = None,
    boost_if_near_phone: int = 3,
    boost_if_near_name: int = 2,
) -> list[AddressMatch]:
    """
    Extrae direcciones y aplica verificación cruzada con contexto externo.

    Parámetros
    ----------
    nearby_phones : teléfonos ya extraídos; si aparecen en la ventana de la
                    dirección, se suma boost_if_near_phone al score.
    nearby_names  : nombres de persona extraídos del mismo email.
    boost_if_near_phone : puntos extra por co-ocurrencia con teléfono.
    boost_if_near_name  : puntos extra por co-ocurrencia con nombre.
    """
    if not content:
        return []

    nearby_phones = nearby_phones or []
    nearby_names = nearby_names or []
    normalized_content = _nt(content)
    content_is_long = len(content) > MAX_CONTENT_LENGTH_FOR_FULL_BARE_SCAN
    names = extract_name_candidates(content) if not content_is_long else []
    ruts = extract_chilean_ruts(content) if not content_is_long else []

    found: list[AddressMatch] = []
    seen: set[str] = set()

    # ── Fase 1: candidatos con label explícito ────────────────────────────
    for candidate, evidence in _extract_labeled_candidates(content):
        norm = _clean_address(candidate)
        if not norm or norm in seen:
            continue
        if not _looks_like_address(norm):
            continue
        score = _score_address(evidence, norm, names, ruts, explicit_label=True)
        score += _cross_validate(evidence, nearby_phones, nearby_names,
                                  boost_if_near_phone, boost_if_near_name)
        if score < 4:
            continue
        seen.add(norm)
        found.append(AddressMatch(address=norm, evidence=_snippet(evidence), score=score))

    # ── Fase 2: candidatos por regex de calle ────────────────────────────
    has_address_context_hint = (
        any(kw in normalized_content for kw in ADDRESS_LABEL_KEYWORDS)
        or any(kw in normalized_content for kw in ORDER_CONTEXT_KEYWORDS)
        or any(kw in normalized_content for kw in LOCATION_HINT_KEYWORDS)
    )
    patterns_to_scan: list[tuple[re.Pattern[str], int]] = [(PREFIX_STREET_PATTERN, MAX_PATTERN_MATCHES)]
    if not content_is_long or has_address_context_hint:
        bare_limit = MAX_PATTERN_MATCHES if not content_is_long else MAX_BARE_MATCHES_FAST
        patterns_to_scan.append((BARE_STREET_PATTERN, bare_limit))

    for pattern, max_matches in patterns_to_scan:
        for idx, m in enumerate(pattern.finditer(content)):
            if idx >= max_matches:
                break
            raw = _strip_trailing(m.group(0)).strip(" ,.;:–-")
            norm = _clean_address(raw)
            if not norm or norm in seen:
                continue
            if not _looks_like_address(norm):
                continue
            s = max(0, m.start() - 200)
            e = min(len(content), m.end() + 200)
            window = content[s:e]
            if _has_disqualifying_context(norm, window):
                continue
            # Intentar capturar la comuna que sigue al número
            norm = _append_commune(norm, content[m.end(): m.end() + 60])
            score = _score_address(window, norm, names, ruts, explicit_label=False)
            score += _cross_validate(window, nearby_phones, nearby_names,
                                      boost_if_near_phone, boost_if_near_name)
            if score < 4:
                continue
            seen.add(norm)
            found.append(AddressMatch(address=norm, evidence=_snippet(window), score=score))

    found.sort(key=lambda item: (-item.score, -len(item.address), item.address.lower()))
    return found[:5]


_STREET_PREFIX_STRIP_RE = re.compile(
    r"^(?:av(?:da)?\.?\s*|avenida\s+|calle\s+|pasaje\s+|psje\.?\s*|camino\s+|ruta\s+|autopista\s+)",
    re.IGNORECASE,
)
_TRAILING_STREET_NUMBER_RE = re.compile(r"\s+\d{1,5}\b.*$")


def _street_core(target: str) -> str:
    """
    Extrae solo el nombre de la calle, sin prefijo ni número.
    "Av. Los Aromos 456, Providencia" → "los aromos"
    """
    norm = _nt(target.strip())
    norm = _STREET_PREFIX_STRIP_RE.sub("", norm)
    norm = _TRAILING_STREET_NUMBER_RE.sub("", norm)
    return norm.strip(" ,.;:–-")


def _accent_flexible_pattern(text: str) -> str:
    """Convierte texto normalizado en regex que acepta letras con o sin tilde."""
    mapping = {
        "a": "[aáÁ]", "e": "[eéÉ]", "i": "[iíÍ]",
        "o": "[oóÓ]", "u": "[uúÚü]", "n": "[nñÑ]",
    }
    parts = []
    for ch in text:
        if ch in mapping:
            parts.append(mapping[ch])
        elif ch.isalpha():
            parts.append(f"[{ch.lower()}{ch.upper()}]")
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


def find_address_near_target(content: str, target: str) -> str | None:
    """
    Busca en *content* la dirección completa que corresponde al *target* dado.

    Estrategia (sin umbral de scoring):
    1. Extrae el nombre de calle desnudo (sin prefijo, sin número).
    2. Busca todas las ocurrencias de ese nombre en el contenido, tolerando
       diferencias de tilde/mayúscula.
    3. Para cada ocurrencia, aplica PREFIX_STREET_PATTERN y BARE_STREET_PATTERN
       en una ventana y devuelve el match más largo que incluya la calle.
    """
    if not content or not target:
        return None

    core = _street_core(target)
    if not core or len(core) < 3:
        return None

    street_re = re.compile(
        r"(?i)\b" + _accent_flexible_pattern(core) + r"\b",
        re.UNICODE,
    )

    best: tuple[str, int] | None = None  # (address, length)

    for m in street_re.finditer(content):
        s = max(0, m.start() - 60)
        e = min(len(content), m.end() + 150)
        window = content[s:e]

        for pattern in (PREFIX_STREET_PATTERN, BARE_STREET_PATTERN):
            for pm in pattern.finditer(window):
                raw = _strip_trailing(pm.group(0)).strip(" ,.;:–-")
                norm = _clean_address(raw)
                if not norm:
                    continue
                if core not in _nt(norm):
                    continue
                norm = _append_commune(norm, window[pm.end(): pm.end() + 80])
                if best is None or len(norm) > best[1]:
                    best = (norm, len(norm))

    return best[0] if best else None


def select_primary_address(
    values: list[str],
    counts: dict[str, int] | None = None,
    scores: dict[str, int] | None = None,
) -> str | None:
    """Elige la dirección más relevante de una lista."""
    if not values:
        return None

    unique = _dedupe(values)
    best = unique[0]
    best_rank = -1

    for value in unique:
        fp = address_fingerprint(value)
        count = counts.get(fp, counts.get(value, 0)) if counts else values.count(value)
        score = scores.get(fp, scores.get(value, 0)) if scores else 0
        completeness = 0
        nv = _nt(value)
        if re.search(r"\b(comuna|region|santiago|rm|metropolitana)\b", nv):
            completeness += 1
        if re.search(r"\b(depto|departamento|dpto|oficina|of|piso)\b", nv):
            completeness += 1
        # Bonus por nombre de comuna conocida
        if _find_commune_in_text(nv):
            completeness += 2
        rank = count * 7 + score * 2 + completeness
        if rank > best_rank or (rank == best_rank and len(value) > len(best)):
            best = value
            best_rank = rank

    return best


def address_fingerprint(value: str) -> str:
    """Genera una clave corta y estable para deduplicar direcciones similares."""
    normalized = re.sub(r"[^a-z0-9\s]", " ", _nt(value))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return value.lower().strip()

    tokens = normalized.split()
    num_idx = next(
        (i for i, t in enumerate(tokens) if t.isdigit() and 1 <= len(t) <= 5),
        None,
    )
    if num_idx is None:
        return normalized

    start = max(0, num_idx - 3)
    head = [t for t in tokens[start:num_idx] if t not in _STOPWORDS]
    if not head:
        head = tokens[max(0, num_idx - 2):num_idx]
    return " ".join(head + [tokens[num_idx]])


# ---------------------------------------------------------------------------
# Extracción de candidatos con label
# ---------------------------------------------------------------------------

def _extract_labeled_candidates(content: str) -> list[tuple[str, str]]:
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in content.splitlines() if ln.strip()]
    results: list[tuple[str, str]] = []

    for idx, line in enumerate(lines):
        # Caso A: label e información en la misma línea
        m = _INLINE_LABEL_RE.search(_nt(line))
        if m:
            raw_m = _INLINE_LABEL_RE.search(line)
            candidate = _strip_trailing(raw_m.group(1) if raw_m else line)
            candidate = _best_street_segment(candidate)
            evidence = line
            # Escanear hasta 5 líneas siguientes por continuación
            for j in range(1, 6):
                if idx + j >= len(lines):
                    break
                nxt = lines[idx + j]
                if _looks_like_address(nxt):
                    nxt_clean = _strip_trailing(nxt).strip(" ,.;:–-")
                    candidate = f"{candidate}, {nxt_clean}"
                    evidence = f"{evidence} {nxt}"
                    break
                if any(kw in _nt(nxt) for kw in ADDRESS_LABEL_KEYWORDS):
                    break  # nuevo label → parar
            results.append((candidate, evidence))
            continue

        # Caso B: label en una línea, dirección en las siguientes (hasta 5)
        if any(kw in _nt(line) for kw in ADDRESS_LABEL_KEYWORDS):
            for j in range(1, 6):
                if idx + j >= len(lines):
                    break
                nxt = lines[idx + j]
                if _looks_like_address(nxt):
                    results.append((nxt, f"{line} {nxt}"))
                    break
                if nxt.strip() == "":
                    break

    return results


# ---------------------------------------------------------------------------
# Validación de forma
# ---------------------------------------------------------------------------

def _looks_like_address(value: str) -> bool:
    nv = _nt(value)
    m_num = re.search(r"(?<!\d)\d{1,5}(?!\d)", nv)
    if not m_num:
        return False
    # Número 0 no es válido como número de calle
    if m_num.group(0) == "0":
        return False
    if _is_generic_phrase(nv):
        return False
    words = re.findall(r"[a-záéíóúüñ]{3,}", nv)
    meaningful = [w for w in words if w not in _STOPWORDS and w not in _GENERIC_TOKENS]
    if not meaningful:
        return False
    # Rechazar si el nombre de calle contiene tokens genéricos de e-commerce/finanzas
    before_num = nv[:m_num.start()].strip()
    words_before = re.findall(r"[a-záéíóúüñ]{3,}", before_num)
    if any(w in _GENERIC_TOKENS for w in words_before):
        return False
    if re.search(r"\b(av(?:da)?\.?|avenida|calle|pasaje|psje\.?|camino|ruta|"
                 r"pje\.?|parcela|poblacion|villa|condominio)\b", nv):
        return True
    if m_num:
        before = nv[:m_num.start()].strip()
        words_b = [w for w in re.findall(r"[a-záéíóúüñ]{2,}", before) if w not in _STOPWORDS]
        if len(words_b) >= 2:
            return True
        if len(words_b) == 1 and len(words_b[0]) >= 5:
            return True
    if _find_commune_in_text(nv):
        return True
    return False


def _is_generic_phrase(nv: str) -> bool:
    words = re.findall(r"[a-z0-9]+", nv)
    alpha = [w for w in words if not w.isdigit()]
    meaningful = [w for w in alpha if w not in _STOPWORDS]
    if not meaningful:
        return True
    if _looks_like_marketing_fragment(nv, nv):
        return True
    if all(w in _GENERIC_TOKENS for w in meaningful):
        return True
    if re.search(r"\bsolo\s+\d{1,5}\b", nv) and any(k in nv for k in ("entrega", "envio", "despacho")):
        return True
    # "últimos/primeros N" → credit card context, never an address
    if re.search(r"\b(?:ultimos|primeros|siguientes)\s+\d{1,2}\b", nv):
        return True
    # Financial sentence: contains debito/credito + number
    if re.search(r"\b(?:debito|credito|tarjeta|cuenta)\b", nv) and any(w in _GENERIC_TOKENS for w in meaningful):
        return True
    # Evita falsos positivos de contexto deportivo (ej. "roja sub 20")
    if _SUB_CATEGORY_PATTERN.search(nv) and any(k in nv for k in _SPORT_CONTEXT_KEYWORDS):
        return True
    if re.search(r"\broja\s+sub[\s-]?\d{1,2}\b", nv):
        return True
    return False


# ---------------------------------------------------------------------------
# Captura de comuna adyacente
# ---------------------------------------------------------------------------

def _append_commune(address: str, following: str) -> str:
    """
    Si el texto que sigue a la dirección contiene el nombre de una comuna
    conocida, lo agrega al candidato (p. ej. ", Las Condes").
    """
    commune = _find_commune_in_text(following)
    if commune:
        cap = commune.title()
        if cap.lower() not in _nt(address):
            return f"{address}, {cap}"
    return address


# ---------------------------------------------------------------------------
# Limpieza del candidato
# ---------------------------------------------------------------------------

def _truncate_at_prose(value: str) -> str:
    """Corta el string en el primer indicador de prosa (no dirección)."""
    m = _SENTENCE_END_RE.search(value)
    if m:
        value = value[:m.start()].strip(" ,.;:–-")
    m = _PROSE_BREAK_RE.search(value)
    if m:
        value = value[:m.start()].strip(" ,.;:–-")
    return value


def _clean_address(value: str) -> str | None:
    value = _strip_trailing(value)
    value = _TRAILING_PHONE_RE.sub("", value)
    value = _truncate_at_prose(value)
    value = re.sub(r"\s+", " ", value).strip(" ,.;:–-")

    if len(value) < 8 or len(value) > 160:
        return None

    nv = _nt(value)

    if any(h in nv for h in _NON_ADDRESS_HINTS):
        return None

    if _URL_PATTERN.search(value) or _EMAIL_PATTERN.search(value) or _RUT_PATTERN.search(value):
        return None

    if _LONG_NUMBER_PATTERN.search(value):
        return None

    if _DATE_PATTERN.search(nv):
        return None

    if len(nv.split()) > 14:
        return None

    return _capitalize_address(value)


def _capitalize_address(value: str) -> str:
    """Capitaliza la dirección respetando preposiciones y artículos."""
    _LOWER_WORDS = {"de", "del", "la", "el", "los", "las", "y", "en", "a", "al", "con"}
    words = value.split()
    result = []
    for i, word in enumerate(words):
        if i == 0 or word.lower() not in _LOWER_WORDS:
            result.append(word.capitalize())
        else:
            result.append(word.lower())
    return " ".join(result)


def _strip_trailing(value: str) -> str:
    return _TRAILING_RE.sub("", value).strip()


def _best_street_segment(value: str) -> str:
    for pattern in (PREFIX_STREET_PATTERN, BARE_STREET_PATTERN):
        m = pattern.search(value)
        if m:
            return m.group(0).strip(" ,.;:–-")
    return value


# ---------------------------------------------------------------------------
# Verificación cruzada
# ---------------------------------------------------------------------------

def _cross_validate(
    window: str,
    nearby_phones: list[str],
    nearby_names: list[str],
    boost_phone: int,
    boost_name: int,
) -> int:
    bonus = 0
    nw = _nt(window)

    for phone in nearby_phones:
        # Buscar los dígitos del teléfono (sin formato) en la ventana
        digits = re.sub(r"\D", "", phone)[-8:]
        if digits and digits in re.sub(r"\D", "", window):
            bonus += boost_phone
            break

    for name in nearby_names:
        parts = _nt(name).split()
        if any(len(p) >= 4 and p in nw for p in parts):
            bonus += boost_name
            break

    return bonus


# ---------------------------------------------------------------------------
# Scoring de contexto
# ---------------------------------------------------------------------------

def _score_address(
    window: str,
    address: str,
    names: list[str],
    ruts: list[str],
    explicit_label: bool,
) -> int:
    nw = _nt(window)
    na = _nt(address)

    if _looks_like_marketing_fragment(na, nw):
        return -6

    score = 0

    if explicit_label:
        score += 5

    for kw in ADDRESS_LABEL_KEYWORDS:
        if kw in nw:
            score += 4
            break

    for kw in ORDER_CONTEXT_KEYWORDS:
        if _kw(nw, kw):
            score += 2
            break

    for kw in LOCATION_HINT_KEYWORDS:
        if _kw(nw, kw):
            score += 2
            break

    # Bonus por nombre de comuna conocida en la ventana
    if _find_commune_in_text(nw) or _find_commune_in_text(na):
        score += 3

    for name in names:
        if _nt(name) in nw:
            score += 2
            break

    for rut in ruts:
        if rut.lower() in nw:
            score += 1
            break

    for kw in _NEGATIVE_CONTEXT:
        if kw in nw:
            score -= 4
            break

    return score


def _has_disqualifying_context(address: str, window: str) -> bool:
    nw = _nt(window)
    na = _nt(address)
    if _looks_like_marketing_fragment(na, nw):
        return True
    if _SUB_CATEGORY_PATTERN.search(nw) and any(k in nw for k in _SPORT_CONTEXT_KEYWORDS):
        return True
    m = re.search(r"(?<!\d)\d{1,5}(?!\d)", _nt(address))
    if m:
        number = m.group(0)
        before_num = nw[:nw.find(number)] if number in nw else ""
        last_words = re.findall(r"[a-z]+", before_num)[-4:]
        if any(w in _ID_TOKENS for w in last_words):
            return True
    for kw in _NEGATIVE_CONTEXT:
        if kw in nw:
            return True
    return False


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def _nt(value: str) -> str:
    return (
        value.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ü", "u")
        .replace("ñ", "n")
    )


def _kw(text: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in text
    return bool(re.search(rf"\b{re.escape(keyword)}\b", text))


def _snippet(window: str) -> str:
    return re.sub(r"\s+", " ", window).strip()[:260]


def _looks_like_marketing_fragment(address_text: str, window_text: str) -> bool:
    """
    Bloquea fragmentos promocionales con número que suelen parecer "dirección",
    por ejemplo: "Hasta 12", "Aprovecha 10", "Black Friday 50".
    """
    if _has_street_marker(address_text):
        return False
    if _find_commune_in_text(address_text):
        return False

    words = re.findall(r"[a-z0-9]+", address_text)
    promo_hits = 0
    for keyword in _PROMO_CONTEXT_KEYWORDS:
        if _kw(address_text, keyword) or _kw(window_text, keyword):
            promo_hits += 1

    if re.search(r"\b(?:hasta|desde|ahorra|aprovecha|solo)\s+\d{1,3}\b", address_text):
        return True
    if promo_hits >= 3:
        return True
    if len(words) <= 4 and promo_hits >= 2:
        return True
    if re.search(r"\b\d{1,3}\s*%\b", window_text) and len(words) <= 5 and promo_hits >= 1:
        return True
    return False


def _has_street_marker(text: str) -> bool:
    return bool(
        re.search(
            r"\b(av(?:da)?\.?|avenida|calle|pasaje|psje\.?|camino|ruta|"
            r"pje\.?|parcela|poblacion|villa|condominio|boulevard|blvd\.?|autopista)\b",
            text,
        )
    )


def _find_commune_in_text(text: str) -> str | None:
    cache = getattr(_find_commune_in_text, "_cache", None)
    if cache is None:
        normalized_to_display: dict[str, str] = {}
        for commune in sorted(_COMUNAS_CHILE, key=len, reverse=True):
            normalized = _nt(commune)
            normalized_to_display.setdefault(normalized, commune)
        options = sorted(normalized_to_display.keys(), key=len, reverse=True)
        if options:
            pattern = re.compile(
                rf"(?<![a-z0-9])({'|'.join(re.escape(item) for item in options)})(?![a-z0-9])"
            )
        else:
            pattern = re.compile(r"$^")
        cache = (pattern, normalized_to_display)
        setattr(_find_commune_in_text, "_cache", cache)

    pattern, normalized_to_display = cache
    match = pattern.search(_nt(text))
    if not match:
        return None
    return normalized_to_display.get(match.group(1))
