from __future__ import annotations

import asyncio
import base64
import binascii
import email.utils
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Any, Iterable, Optional

import httpx
from config import EMAIL_EXTRACTION_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL
from core.consolidated_profile import build_consolidated_profile
from core.ip_classification import enrich_senders_with_header_ip_country, extract_header_ips
from core.personal_data.cross_validator import extract_contact_info
from core.personal_data import (
    address_fingerprint,
    extract_chilean_address_matches,
    extract_chilean_plate_matches,
    extract_chilean_phone_matches,
    extract_chilean_ruts,
    extract_name_candidates,
    find_address_near_target,
    select_primary_address,
    select_primary_name,
    select_primary_plate,
    select_primary_phone,
    select_primary_rut,
    street_core as _address_street_core,
)

from models.schemas import (
    AuthorizedEmailMessage,
    EmailHeaderKV,
    HeaderIpDetail,
    EmailIdentificationRequest,
    EmailIdentificationResponse,
    EmailIdentificationSummary,
    EmailSearchTargets,
    IdentifiedSender,
    SenderEvidence,
    SenderRiskAssessment,
    WhoisSummary,
)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
COMMON_MULTI_PART_SUFFIXES = {
    "co.uk",
    "org.uk",
    "gov.uk",
    "ac.uk",
    "com.au",
    "net.au",
    "org.au",
    "co.nz",
    "com.br",
}
COMMON_MAIL_SUBDOMAIN_PREFIXES = {
    "mail",
    "email",
    "mailer",
    "m",
    "mg",
    "news",
    "notify",
    "notifications",
    "n",
    "crm",
    "em",
    "links",
    "tracking",
    "click",
    "bounce",
    "transactional",
}
CHILEAN_GOVERNMENT_SUFFIXES = ("gob.cl", "gov.cl", "mil.cl")
KNOWN_SENDERS: dict[str, dict[str, Any]] = {
    "bancoestado.cl": {"company_name": "BancoEstado", "sender_type": "banco", "country": "Chile", "is_chilean": True},
    "bci.cl": {"company_name": "Banco BCI", "sender_type": "banco", "country": "Chile", "is_chilean": True},
    "santander.cl": {"company_name": "Santander Chile", "sender_type": "banco", "country": "Chile", "is_chilean": True},
    "falabella.com": {"company_name": "Falabella", "sender_type": "retail", "country": "Chile", "is_chilean": True},
    "linio.cl": {"company_name": "Linio Chile", "sender_type": "retail", "country": "Chile", "is_chilean": True},
    "mercadolibre.cl": {"company_name": "Mercado Libre Chile", "sender_type": "marketplace", "country": "Chile", "is_chilean": True},
    "mercadopago.cl": {"company_name": "Mercado Pago Chile", "sender_type": "fintech", "country": "Chile", "is_chilean": True},
    "copec.cl": {"company_name": "Copec", "sender_type": "retail", "country": "Chile", "is_chilean": True},
    "entel.cl": {"company_name": "Entel", "sender_type": "telecom", "country": "Chile", "is_chilean": True},
    "movistar.cl": {"company_name": "Movistar Chile", "sender_type": "telecom", "country": "Chile", "is_chilean": True},
    "wom.cl": {"company_name": "WOM Chile", "sender_type": "telecom", "country": "Chile", "is_chilean": True},
    "vtr.com": {"company_name": "VTR", "sender_type": "telecom", "country": "Chile", "is_chilean": True},
    "uchile.cl": {"company_name": "Universidad de Chile", "sender_type": "educacion", "country": "Chile", "is_chilean": True},
    "puc.cl": {"company_name": "Pontificia Universidad Catolica de Chile", "sender_type": "educacion", "country": "Chile", "is_chilean": True},
    "duoc.cl": {"company_name": "Duoc UC", "sender_type": "educacion", "country": "Chile", "is_chilean": True},
    "sii.cl": {"company_name": "Servicio de Impuestos Internos", "sender_type": "gobierno", "country": "Chile", "is_chilean": True},
    "mercadopublico.cl": {"company_name": "Mercado Publico", "sender_type": "gobierno", "country": "Chile", "is_chilean": True},
    "servel.cl": {"company_name": "SERVEL", "sender_type": "gobierno", "country": "Chile", "is_chilean": True},
    "gmail.com": {"company_name": "Google", "sender_type": "correo", "country": "Estados Unidos", "is_chilean": False},
    "google.com": {"company_name": "Google", "sender_type": "saas", "country": "Estados Unidos", "is_chilean": False},
    "apple.com": {"company_name": "Apple", "sender_type": "tecnologia", "country": "Estados Unidos", "is_chilean": False},
    "microsoft.com": {"company_name": "Microsoft", "sender_type": "saas", "country": "Estados Unidos", "is_chilean": False},
    "outlook.com": {"company_name": "Microsoft Outlook", "sender_type": "correo", "country": "Estados Unidos", "is_chilean": False},
    "amazon.com": {"company_name": "Amazon", "sender_type": "retail", "country": "Estados Unidos", "is_chilean": False},
    "aws.amazon.com": {"company_name": "Amazon Web Services", "sender_type": "saas", "country": "Estados Unidos", "is_chilean": False},
    "netflix.com": {"company_name": "Netflix", "sender_type": "streaming", "country": "Estados Unidos", "is_chilean": False},
    "spotify.com": {"company_name": "Spotify", "sender_type": "streaming", "country": "Suecia", "is_chilean": False},
    "linkedin.com": {"company_name": "LinkedIn", "sender_type": "empleo", "country": "Estados Unidos", "is_chilean": False},
    "meta.com": {"company_name": "Meta", "sender_type": "red_social", "country": "Estados Unidos", "is_chilean": False},
    "facebookmail.com": {"company_name": "Meta Facebook", "sender_type": "red_social", "country": "Estados Unidos", "is_chilean": False},
    "instagram.com": {"company_name": "Instagram", "sender_type": "red_social", "country": "Estados Unidos", "is_chilean": False},
    "x.com": {"company_name": "X", "sender_type": "red_social", "country": "Estados Unidos", "is_chilean": False},
    "paypal.com": {"company_name": "PayPal", "sender_type": "fintech", "country": "Estados Unidos", "is_chilean": False},
    "nubank.com.br": {"company_name": "Nubank", "sender_type": "fintech", "country": "Brasil", "is_chilean": False},
}
DATA_BROKER_KEYWORDS = (
    "peoplefinder",
    "peekyou",
    "spokeo",
    "whitepages",
    "beenverified",
    "radaris",
    "truthfinder",
    "intelius",
    "mylife",
    "rocketreach",
    "zoominfo",
    "apollo",
    "lusha",
    "seamless",
    "contactout",
    "hunter.io",
    "clearbit",
)
NEWSLETTER_HINTS = ("unsubscribe", "newsletter", "promotions", "offers", "marketing", "boletin")
SUSPICIOUS_KEYWORDS = ("noreply", "mailer", "bounce", "tracking", "click", "link")
SECTOR_KEYWORDS: list[tuple[str, str]] = [
    ("bank", "banco"),
    ("banco", "banco"),
    ("university", "educacion"),
    ("universidad", "educacion"),
    ("college", "educacion"),
    ("school", "educacion"),
    ("gov", "gobierno"),
    ("gob", "gobierno"),
    ("retail", "retail"),
    ("shop", "retail"),
    ("store", "retail"),
    ("pay", "fintech"),
    ("billing", "fintech"),
    ("saas", "saas"),
    ("cloud", "saas"),
    ("crm", "saas"),
    ("telecom", "telecom"),
    ("mobile", "telecom"),
    ("insurance", "seguros"),
    ("travel", "viajes"),
    ("air", "viajes"),
]
PERSONAL_DATA_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("nombre", ("estimado", "estimada", "hola ", "cliente", "usuario", "titular", "beneficiario", "nombre")),
    ("direccion", ("direccion", "despacho", "envio a", "domicilio", "calle", "comuna", "region", "sucursal")),
    ("patente", ("patente", "placa", "vehiculo", "automovil", "permiso de circulacion")),
    ("rut", ("rut", "run", "cedula", "documento de identidad")),
    ("telefono", ("telefono", "celular", "whatsapp", "llamanos", "llamanos al")),
    ("pedido", ("pedido", "orden", "compra", "seguimiento", "tracking")),
    ("pago", ("pago", "factura", "boleta", "cargo", "cobro", "cuota", "vencimiento")),
    ("cuenta", ("cuenta", "suscripcion", "perfil", "clave", "contrasena", "password", "inicio de sesion")),
]
MAX_PERSONAL_DATA_ANALYSIS_CHARS = 5000
MAX_WHOIS_DOMAINS = 80
MAX_LLM_SENDER_CANDIDATES = 8
LLM_ENRICH_CONCURRENCY = 4
_STYLE_SCRIPT_RE = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_CONTACT_ADDRESS_HINT_RE = re.compile(
    r"(?i)\b(direccion|domicilio|despacho|envio|entrega|calle|avenida|pasaje|camino|"
    r"av\.?|depto|departamento|comuna|region)\b"
)
_CONTACT_PHONE_HINT_RE = re.compile(
    r"(?i)(\+?56[\s().-]*(?:9|2)[\s().-]*\d{3,4}[\s().-]*\d{3,4}|\b(?:9|2)\d{8}\b|\b600[\s().-]*\d{3}[\s().-]*\d{4}\b)"
)
logger = logging.getLogger(__name__)


@dataclass
class SenderAggregate:
    company_name: str
    primary_domain: str
    normalized_domain: str
    sender_type: str
    country: str
    is_chilean: bool
    confidence: float
    tld: str
    tags: set[str] = field(default_factory=set)
    personal_data_types: set[str] = field(default_factory=set)
    personal_names: set[str] = field(default_factory=set)
    personal_addresses: set[str] = field(default_factory=set)
    personal_address_display_by_fingerprint: dict[str, str] = field(default_factory=dict)
    personal_address_counts: dict[str, int] = field(default_factory=dict)
    personal_address_scores: dict[str, int] = field(default_factory=dict)
    personal_address_evidence: list[str] = field(default_factory=list)
    personal_ruts: set[str] = field(default_factory=set)
    personal_phones: set[str] = field(default_factory=set)
    # reincidencia (cuántos correos lo mencionan) y mejor score de contexto,
    # ambos indexados por el teléfono ya normalizado (+56 X XXXX XXXX)
    personal_phone_counts: dict[str, int] = field(default_factory=dict)
    personal_phone_scores: dict[str, int] = field(default_factory=dict)
    personal_phone_evidence: list[str] = field(default_factory=list)
    personal_plates: set[str] = field(default_factory=set)
    personal_plate_evidence: list[str] = field(default_factory=list)
    message_count: int = 0
    spam_count: int = 0
    trash_count: int = 0
    sample_subjects: list[str] = field(default_factory=list)
    sample_contents: list[str] = field(default_factory=list)
    attachment_filenames: set[str] = field(default_factory=set)
    from_addresses: set[str] = field(default_factory=set)
    reply_to_addresses: set[str] = field(default_factory=set)
    return_path_addresses: set[str] = field(default_factory=set)
    auth_domains: set[str] = field(default_factory=set)
    reply_to_domains: set[str] = field(default_factory=set)
    return_path_domains: set[str] = field(default_factory=set)
    header_ips: set[str] = field(default_factory=set)
    header_ip_countries: set[str] = field(default_factory=set)
    header_ip_chile_matches: set[str] = field(default_factory=set)
    header_ip_details: dict[str, dict[str, Any]] = field(default_factory=dict)
    subdomains: set[str] = field(default_factory=set)
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    risk_reasons: set[str] = field(default_factory=set)
    suspected_newsletter: bool = False
    suspected_data_broker: bool = False
    suspicious_infrastructure: bool = False
    aggressive_marketing: bool = False
    matched_target_types: set[str] = field(default_factory=set)
    target_matched_address_fps: set[str] = field(default_factory=set)
    whois: Optional[WhoisSummary] = None


async def identify_email_footprint(
    request: EmailIdentificationRequest,
) -> EmailIdentificationResponse:
    messages = list(request.messages)
    if request.provider == "gmail":
        if not request.gmail_access_token:
            raise ValueError("gmail_access_token es obligatorio cuando provider='gmail'")
        messages = await _fetch_gmail_messages(
            access_token=request.gmail_access_token,
            max_messages=request.max_messages,
        )
    elif not messages:
        raise ValueError("Debes enviar mensajes autorizados para provider='manual'")

    aggregates: dict[str, SenderAggregate] = {}
    all_domains: set[str] = set()
    suspicious_domains: set[str] = set()
    data_brokers: set[str] = set()
    spam_messages = 0
    trash_messages = 0
    spam_domains: set[str] = set()
    trash_domains: set[str] = set()

    for message in messages[: request.max_messages]:
        parsed = _parse_message(message, request.search_targets)
        if not parsed["from_domain"]:
            continue
        if parsed["is_spam"]:
            spam_messages += 1
            spam_domains.add(parsed["from_domain"])
        if parsed["is_trash"]:
            trash_messages += 1
            trash_domains.add(parsed["from_domain"])

        primary_domain = parsed["from_domain"]
        record = aggregates.get(primary_domain)
        if record is None:
            profile = _classify_sender(
                primary_domain=primary_domain,
                subdomains=parsed["subdomains"],
                subject=parsed["subject"],
                auth_domains=parsed["auth_domains"],
            )
            record = SenderAggregate(**profile)
            aggregates[primary_domain] = record

        _merge_message(record, parsed)
        all_domains.update(parsed["all_domains"])

        if record.suspicious_infrastructure:
            suspicious_domains.add(primary_domain)
        if record.suspected_data_broker:
            data_brokers.add(record.company_name)

    await _enrich_with_whois(aggregates)
    await enrich_senders_with_header_ip_country(aggregates)
    await _enrich_with_llm_personal_data(aggregates)

    senders = [
        _to_identified_sender(sender)
        for sender in sorted(aggregates.values(), key=lambda item: (-item.message_count, item.company_name.lower()))
    ]

    summary = EmailIdentificationSummary(
        total_messages_analyzed=len(messages[: request.max_messages]),
        spam_messages_analyzed=spam_messages,
        trash_messages_analyzed=trash_messages,
        unique_domains=len(all_domains),
        unique_companies=len({sender.company_name for sender in senders}),
        companies_with_user_data=_dedupe_preserve_order(sender.company_name for sender in senders),
        chilean_companies=_dedupe_preserve_order(sender.company_name for sender in senders if sender.is_chilean),
        international_companies=_dedupe_preserve_order(sender.company_name for sender in senders if not sender.is_chilean),
        risky_or_unnecessary_companies=_dedupe_preserve_order(sender.company_name for sender in senders if sender.risk.level != "low"),
        suspicious_domains=sorted(suspicious_domains),
        data_brokers=sorted(data_brokers),
        spam_domains=sorted(spam_domains),
        trash_domains=sorted(trash_domains),
    )

    return EmailIdentificationResponse(
        provider=request.provider,
        email_address=request.email_address,
        summary=summary,
        senders=senders,
        analyzed_domains=sorted(all_domains),
        consolidated_profile=build_consolidated_profile(senders, email_address=request.email_address),
    )


async def _fetch_gmail_messages(access_token: str, max_messages: int) -> list[AuthorizedEmailMessage]:
    """
    Estrategia de dos fases optimizada para máxima detección de datos personales:

    Fase 1 — Metadata rápida (sin cuerpo):
      Descarga headers (From, Subject, Date…) para todos los mensajes.
      Identifica todos los remitentes únicos. ~5-10× más rápido que format=full.

    Fase 2 — Body completo por remitente:
      Para CADA remitente único, descarga hasta FULL_PER_SENDER mensajes
      con cuerpo completo. Esto maximiza la detección de RUT, nombre,
      dirección, teléfono y patente en correos transaccionales.
      Sin límite de remitentes — todos se cubren.
    """
    FULL_PER_SENDER = 5     # mensajes con body por cada remitente único
    SEM_META        = 30    # concurrencia fase 1
    SEM_FULL        = 20    # concurrencia fase 2

    import re as _re
    from collections import defaultdict

    api_headers = {"Authorization": f"Bearer {access_token}"}
    timeout_meta = httpx.Timeout(12.0, connect=6.0)
    timeout_full = httpx.Timeout(20.0, connect=8.0)

    # ── Fase 1: metadata para todos los mensajes ──────────────────────────────
    async with httpx.AsyncClient(timeout=timeout_meta, headers=api_headers) as client:
        message_refs: list[dict[str, Any]] = []
        next_page_token: str | None = None

        while len(message_refs) < max_messages:
            listing = await client.get(
                f"{GMAIL_API_BASE}/messages",
                params={
                    "maxResults": min(max_messages - len(message_refs), 500),
                    "includeSpamTrash": "true",
                    **({"pageToken": next_page_token} if next_page_token else {}),
                },
            )
            listing.raise_for_status()
            data = listing.json()
            message_refs.extend(data.get("messages", []) or [])
            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

        selected_refs = message_refs[:max_messages]
        sem_meta = asyncio.Semaphore(SEM_META)

        async def fetch_meta(ref: dict[str, Any]) -> tuple[str, AuthorizedEmailMessage | None]:
            msg_id = ref.get("id", "")
            if not msg_id:
                return msg_id, None
            async with sem_meta:
                try:
                    # metadataHeaders debe pasarse como lista para que httpx
                    # los serialice como repeated params (?metadataHeaders=From&metadataHeaders=To…)
                    r = await client.get(
                        f"{GMAIL_API_BASE}/messages/{msg_id}",
                        params=[
                            ("format",          "metadata"),
                            ("metadataHeaders", "From"),
                            ("metadataHeaders", "To"),
                            ("metadataHeaders", "Subject"),
                            ("metadataHeaders", "Date"),
                            ("metadataHeaders", "Reply-To"),
                            ("metadataHeaders", "Return-Path"),
                        ],
                    )
                    r.raise_for_status()
                    return msg_id, _gmail_to_authorized_message(r.json())
                except Exception:
                    return msg_id, None

        meta_results = await asyncio.gather(*(fetch_meta(ref) for ref in selected_refs))

    # Índice id → (mensaje_meta, posición_en_lista)
    meta_by_id: dict[str, AuthorizedEmailMessage] = {}
    order: list[str] = []
    for msg_id, msg in meta_results:
        order.append(msg_id)
        if msg is not None:
            meta_by_id[msg_id] = msg

    # ── Agrupar IDs por dominio raíz del remitente ────────────────────────────
    domain_to_ids: dict[str, list[str]] = defaultdict(list)
    for msg_id, msg in meta_by_id.items():
        from_hdr = next(
            (h.value for h in msg.headers if h.name.lower() == "from"),
            "",
        )
        m = _re.search(r"@([\w.-]+)", from_hdr)
        if not m:
            continue
        parts = m.group(1).lower().split(".")
        domain = ".".join(parts[-2:]) if len(parts) >= 2 else parts[0]
        domain_to_ids[domain].append(msg_id)

    # ── Fase 2: body completo — FULL_PER_SENDER mensajes por cada remitente ──
    # Todos los remitentes cubiertos. Priorizamos los que tienen subjects con
    # palabras transaccionales (pedido, boleta, cuenta, rut…) porque es donde
    # más probablemente aparecen datos personales como RUT, dirección, teléfono.
    TRANSACTIONAL_HINTS = {
        "pedido", "orden", "boleta", "factura", "compra", "confirmacion",
        "despacho", "envio", "entrega", "cuenta", "saldo", "transferencia",
        "rut", "direccion", "domicilio", "clave", "bienvenido", "registro",
        "pago", "cobro", "cuota", "vencimiento", "estado de cuenta",
    }

    def _sender_priority(ids: list[str]) -> int:
        """Retorna 0 si algún subject tiene hint transaccional, 1 si no."""
        for mid in ids[:3]:
            msg = meta_by_id.get(mid)
            if not msg:
                continue
            subj = (msg.subject or "").lower()
            if any(h in subj for h in TRANSACTIONAL_HINTS):
                return 0
        return 1

    sorted_domains = sorted(
        domain_to_ids.items(),
        key=lambda kv: (_sender_priority(kv[1]), -len(kv[1])),
    )

    full_ids: list[str] = []
    for _domain, ids in sorted_domains:
        full_ids.extend(ids[:FULL_PER_SENDER])

    full_by_id: dict[str, AuthorizedEmailMessage] = {}
    if full_ids:
        async with httpx.AsyncClient(timeout=timeout_full, headers=api_headers) as client:
            sem_full = asyncio.Semaphore(SEM_FULL)

            async def fetch_full(msg_id: str) -> tuple[str, AuthorizedEmailMessage | None]:
                async with sem_full:
                    try:
                        r = await client.get(
                            f"{GMAIL_API_BASE}/messages/{msg_id}",
                            params={"format": "full"},
                        )
                        r.raise_for_status()
                        return msg_id, _gmail_to_authorized_message(r.json())
                    except Exception:
                        return msg_id, None

            full_results = await asyncio.gather(*(fetch_full(mid) for mid in full_ids))

        for msg_id, msg in full_results:
            if msg is not None:
                full_by_id[msg_id] = msg

    # ── Combinar: usar version full si existe, si no usar metadata ────────────
    messages_final: list[AuthorizedEmailMessage] = []
    for msg_id in order:
        msg = full_by_id.get(msg_id) or meta_by_id.get(msg_id)
        if msg is not None:
            messages_final.append(msg)

    return messages_final


async def _enrich_with_whois(aggregates: dict[str, SenderAggregate]) -> None:
    if not aggregates:
        return

    timeout = httpx.Timeout(8.0, connect=4.0)
    prioritized_domains = [
        domain
        for domain, _ in sorted(
            aggregates.items(),
            key=lambda item: (-item[1].message_count, item[0]),
        )
    ][:MAX_WHOIS_DOMAINS]

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_fetch_whois_summary(client, domain) for domain in prioritized_domains],
            return_exceptions=True,
        )

    for domain, result in zip(prioritized_domains, results):
        if isinstance(result, Exception):
            continue
        aggregates[domain].whois = result


async def _enrich_with_llm_personal_data(aggregates: dict[str, SenderAggregate]) -> None:
    if EMAIL_EXTRACTION_PROVIDER != "gemini" or not GEMINI_API_KEY:
        return

    candidates = [
        item
        for item in sorted(aggregates.values(), key=lambda sender: (-sender.message_count, sender.company_name.lower()))
        if item.sample_contents
    ][:MAX_LLM_SENDER_CANDIDATES]
    if not candidates:
        return

    timeout = httpx.Timeout(8.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        semaphore = asyncio.Semaphore(LLM_ENRICH_CONCURRENCY)

        async def run_one(sender: SenderAggregate) -> list[str]:
            async with semaphore:
                return await _extract_personal_data_with_gemini(client, sender)

        results = await asyncio.gather(
            *[run_one(sender) for sender in candidates],
            return_exceptions=True,
        )

    for sender, result in zip(candidates, results):
        if isinstance(result, Exception) or not result:
            continue
        sender.personal_data_types.update(result)


async def _extract_personal_data_with_gemini(
    client: httpx.AsyncClient,
    sender: SenderAggregate,
) -> list[str]:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    schema = {
        "type": "object",
        "properties": {
            "personal_data_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "nombre",
                        "direccion",
                        "patente",
                        "rut",
                        "telefono",
                        "pedido",
                        "pago",
                        "cuenta",
                    ],
                },
            },
        },
        "required": ["personal_data_types"],
        "propertyOrdering": ["personal_data_types"],
    }
    joined_content = "\n\n".join(sender.sample_contents[:3])[:12000]
    prompt = (
        "Analiza el texto de emails y devuelve solo tipos de datos personales de la persona analizada "
        "que aparezcan mencionados de forma razonable. No incluyas datos de la empresa. No inventes. "
        "Tipos permitidos: nombre, direccion, patente, rut, telefono, pedido, pago, cuenta.\n\n"
        f"Empresa: {sender.company_name}\n"
        f"Dominio: {sender.primary_domain}\n"
        "Texto de ejemplo:\n"
        f"{joined_content}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
        },
    }

    try:
        response = await client.post(
            endpoint,
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        candidates = body.get("candidates") or []
        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        text = parts[0].get("text", "") if parts else ""
        data = json.loads(text) if text else {}
        values = data.get("personal_data_types") or []
        allowed = {"nombre", "direccion", "patente", "rut", "telefono", "pedido", "pago", "cuenta"}
        return [item for item in values if item in allowed]
    except Exception:
        return []


async def _fetch_whois_summary(
    client: httpx.AsyncClient,
    domain: str,
) -> Optional[WhoisSummary]:
    try:
        response = await client.get(f"https://rdap.org/domain/{domain}")
        response.raise_for_status()
    except Exception:
        return None

    payload = response.json()
    registrar = None
    registrant = None
    country = None

    entities = payload.get("entities") or []
    for entity in entities:
        roles = set(entity.get("roles") or [])
        if "registrar" in roles and not registrar:
            registrar = _extract_vcard_value(entity.get("vcardArray"), "fn")
        if ("registrant" in roles or "administrative" in roles) and not registrant:
            registrant = _extract_vcard_value(entity.get("vcardArray"), "fn")
            country = country or _extract_vcard_value(entity.get("vcardArray"), "country-name")

    return WhoisSummary(
        registrar=registrar,
        registrant=registrant,
        country=country,
        source="rdap.org",
    )


def _gmail_to_authorized_message(payload: dict[str, Any]) -> AuthorizedEmailMessage:
    headers = [
        EmailHeaderKV(name=item.get("name", ""), value=item.get("value", ""))
        for item in payload.get("payload", {}).get("headers", [])
    ]
    subject = _header_lookup(headers, "Subject")
    snippet = payload.get("snippet")
    body_text, body_html = _extract_gmail_bodies(payload.get("payload", {}))
    attachment_filenames = _extract_gmail_attachment_filenames(payload.get("payload", {}))
    received_at = _gmail_internal_date_to_iso(payload.get("internalDate"))
    return AuthorizedEmailMessage(
        provider_message_id=payload.get("id"),
        thread_id=payload.get("threadId"),
        received_at=received_at,
        label_ids=payload.get("labelIds", []) or [],
        subject=subject,
        snippet=snippet,
        body_text=body_text,
        body_html=body_html,
        attachment_filenames=attachment_filenames,
        headers=headers,
    )


def _extract_gmail_bodies(payload: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    text_parts: list[str] = []
    html_parts: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data and mime_type in {"text/plain", "text/html"}:
            decoded = _decode_base64url(data)
            if decoded is not None:
                if mime_type == "text/plain":
                    text_parts.append(decoded)
                else:
                    html_parts.append(decoded)
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    return (
        "\n".join(part.strip() for part in text_parts if part.strip()) or None,
        "\n".join(part.strip() for part in html_parts if part.strip()) or None,
    )


def _extract_gmail_attachment_filenames(payload: dict[str, Any]) -> list[str]:
    filenames: list[str] = []
    seen: set[str] = set()

    def walk(part: dict[str, Any]) -> None:
        filename = (part.get("filename") or "").strip()
        body = part.get("body", {}) or {}
        has_attachment = bool(filename and body.get("attachmentId"))
        if has_attachment and filename not in seen:
            seen.add(filename)
            filenames.append(filename)
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    return filenames[:10]


def _decode_base64url(value: str) -> Optional[str]:
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(value + padding)
        return raw.decode("utf-8", errors="ignore")
    except (ValueError, binascii.Error):
        return None


def _gmail_internal_date_to_iso(value: Any) -> Optional[str]:
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def _trim_content_for_personal_data(value: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    if len(compact) <= max_chars:
        return compact
    if max_chars < 200:
        return compact[:max_chars]
    head = int(max_chars * 0.6)
    tail = max_chars - head - 29
    if tail < 0:
        tail = 0
    return f"{compact[:head]} [contenido truncado] {compact[-tail:]}" if tail else compact[:max_chars]


def _should_run_cross_validator(content: str) -> bool:
    if not content:
        return False
    has_address_hint = bool(_CONTACT_ADDRESS_HINT_RE.search(content))
    has_phone_hint = bool(_CONTACT_PHONE_HINT_RE.search(content))
    return has_address_hint and has_phone_hint


def _normalize_free_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    ascii_folded = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", ascii_folded.lower())).strip()


def _normalize_phone_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _extract_phone_variants(value: str) -> set[str]:
    digits = _normalize_phone_digits(value)
    if not digits:
        return set()

    variants: set[str] = set()

    def push(candidate: str) -> None:
        compact = candidate.strip()
        if len(compact) >= 8 and compact.isdigit():
            variants.add(compact)

    queue = [digits]
    visited: set[str] = set()
    while queue:
        candidate = queue.pop()
        if candidate in visited:
            continue
        visited.add(candidate)
        if candidate.startswith("0056"):
            queue.append(candidate[4:])
        if candidate.startswith("056"):
            queue.append(candidate[3:])
        if candidate.startswith("56"):
            queue.append(candidate[2:])
        if candidate.startswith("0"):
            queue.append(candidate[1:])
        push(candidate)
        if len(candidate) >= 9:
            push(candidate[-9:])
        if len(candidate) >= 8:
            push(candidate[-8:])

    return variants


def _normalize_phone(value: str) -> Optional[str]:
    for candidate in sorted(_extract_phone_variants(value), key=lambda item: (abs(len(item) - 9), item)):
        if len(candidate) == 9 and candidate[0] in {"9", "2"}:
            return f"+56 {candidate[0]} {candidate[1:5]} {candidate[5:9]}"
    return None


def _compute_rut_dv(body: str) -> str:
    factors = [2, 3, 4, 5, 6, 7]
    total = 0
    for index, digit in enumerate(reversed(body)):
        total += int(digit) * factors[index % len(factors)]
    remainder = 11 - (total % 11)
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)


def _format_rut(body: str, dv: str) -> str:
    reversed_body = body[::-1]
    groups = [reversed_body[i:i + 3][::-1] for i in range(0, len(reversed_body), 3)][::-1]
    return f"{'.'.join(groups)}-{dv}"


def _normalize_rut(value: str) -> Optional[str]:
    compact = re.sub(r"[^0-9kK]", "", value or "").upper()
    if len(compact) < 8 or len(compact) > 9:
        return None
    body, dv = compact[:-1], compact[-1]
    if not body.isdigit() or _compute_rut_dv(body) != dv:
        return None
    return _format_rut(body, dv)


def _normalize_plate(value: str) -> Optional[str]:
    compact = re.sub(r"[^A-Za-z0-9]", "", value or "").upper()
    if re.fullmatch(r"[A-Z]{4}\d{2}", compact):
        return compact
    if re.fullmatch(r"[A-Z]{2}\d{4}", compact):
        return compact
    return None


def _contains_normalized(text: str, target: str) -> bool:
    text_norm = _normalize_free_text(text)
    target_norm = _normalize_free_text(target)
    return bool(text_norm and target_norm and target_norm in text_norm)


def _contains_phone_digits(text: str, target: str) -> bool:
    text_digits = _normalize_phone_digits(text)
    if not text_digits:
        return False
    for variant in _extract_phone_variants(target):
        if variant in text_digits:
            return True
    return False


def _contains_plate(text: str, target: str) -> bool:
    target_plate = _normalize_plate(target)
    if not target_plate:
        return False
    compact_text = re.sub(r"[^A-Za-z0-9]", "", text or "").upper()
    return target_plate in compact_text


def _names_related(value: str, target: str) -> bool:
    value_tokens = [token for token in _normalize_free_text(value).split(" ") if token]
    target_tokens = [token for token in _normalize_free_text(target).split(" ") if token]
    if not value_tokens or not target_tokens:
        return False
    shared = set(value_tokens) & set(target_tokens)
    min_required = max(1, min(2, min(len(value_tokens), len(target_tokens))))
    return len(shared) >= min_required


def _address_related(value: str, target: str) -> bool:
    value_fp = address_fingerprint(value)
    target_fp = address_fingerprint(target)
    if value_fp and target_fp and value_fp == target_fp:
        return True

    value_norm = _normalize_free_text(value)
    target_norm = _normalize_free_text(target)
    if not value_norm or not target_norm:
        return False
    if value_norm in target_norm or target_norm in value_norm:
        return True

    value_tokens = {token for token in value_norm.split(" ") if len(token) >= 3}
    target_tokens = {token for token in target_norm.split(" ") if len(token) >= 3}
    shared_tokens = value_tokens & target_tokens
    if len(shared_tokens) >= 2:
        value_number = re.search(r"\b\d{1,5}\b", value_norm)
        target_number = re.search(r"\b\d{1,5}\b", target_norm)
        if value_number and target_number:
            return value_number.group(0) == target_number.group(0)
        return True
    return False


def _phone_related(value: str, target: str) -> bool:
    value_variants = _extract_phone_variants(value)
    target_variants = _extract_phone_variants(target)
    if not value_variants or not target_variants:
        return False
    return bool(value_variants & target_variants)


def _rut_related(value: str, target: str) -> bool:
    value_norm = _normalize_rut(value)
    target_norm = _normalize_rut(target)
    return bool(value_norm and target_norm and value_norm == target_norm)


def _plate_related(value: str, target: str) -> bool:
    value_norm = _normalize_plate(value)
    target_norm = _normalize_plate(target)
    return bool(value_norm and target_norm and value_norm == target_norm)


def _parse_message(message: AuthorizedEmailMessage, search_targets: Optional[EmailSearchTargets] = None) -> dict[str, Any]:
    headers_by_name = _group_headers_by_name(message.headers)
    headers = {name: values[-1] for name, values in headers_by_name.items() if values}
    from_raw = headers.get("from", "")
    reply_to_raw = headers.get("reply-to", "")
    return_path_raw = headers.get("return-path", "")

    from_addresses = _extract_addresses(from_raw)
    reply_to_addresses = _extract_addresses(reply_to_raw)
    return_path_addresses = _extract_addresses(return_path_raw)

    raw_from_domains = _extract_domains(from_addresses)
    raw_reply_to_domains = _extract_domains(reply_to_addresses)
    raw_return_path_domains = _extract_domains(return_path_addresses)

    from_domains = [domain for domain in (_normalize_domain(item) for item in raw_from_domains) if domain]
    reply_to_domains = [domain for domain in (_normalize_domain(item) for item in raw_reply_to_domains) if domain]
    return_path_domains = [domain for domain in (_normalize_domain(item) for item in raw_return_path_domains) if domain]
    auth_domains = _extract_auth_domains(headers)
    header_ips = extract_header_ips(headers_by_name)
    attachment_filenames = [name.strip() for name in (message.attachment_filenames or []) if name and name.strip()]

    primary_domain = next((domain for domain in from_domains if domain), None)
    subject = (message.subject or headers.get("subject") or "").strip()
    attachment_text = " ".join(f"Adjunto {filename}" for filename in attachment_filenames)
    content = " ".join(filter(None, [subject, message.snippet, message.body_text, _strip_html(message.body_html or ""), attachment_text]))
    analysis_content = _trim_content_for_personal_data(content, max_chars=MAX_PERSONAL_DATA_ANALYSIS_CHARS)
    content_lower = analysis_content.lower()
    all_domains = {domain for domain in from_domains + reply_to_domains + return_path_domains + auth_domains if domain}
    label_ids = [label.upper() for label in (message.label_ids or [])]

    if header_ips:
        logger.debug(
            "[email-ip-debug-raw] message_id=%s | from_domain=%s | header_ips=%s",
            message.provider_message_id or "desconocido",
            primary_domain or "desconocido",
            ", ".join(header_ips),
        )
    else:
        logger.debug(
            "[email-ip-debug-raw] message_id=%s | from_domain=%s | sin IP publica detectable",
            message.provider_message_id or "desconocido",
            primary_domain or "desconocido",
        )

    name_candidates = extract_name_candidates(analysis_content)
    contact_info = None
    should_run_cross_validator = _should_run_cross_validator(analysis_content)
    if should_run_cross_validator:
        try:
            contact_info = extract_contact_info(analysis_content, name_hints=name_candidates, min_confidence=0.35)
            logger.debug(
                "[cross-validator] message_id=%s | address=%s | phone=%s | confidence=%.2f",
                message.provider_message_id or "desconocido",
                (contact_info.address if contact_info and contact_info.address else "none"),
                (contact_info.phone if contact_info and contact_info.phone else "none"),
                (contact_info.confidence if contact_info else 0.0),
            )
        except Exception as exc:
            logger.debug("[cross-validator] fallo en message_id=%s: %s", message.provider_message_id or "desconocido", exc)
    else:
        logger.debug(
            "[cross-validator] message_id=%s | omitido por falta de señales combinadas (direccion+telefono)",
            message.provider_message_id or "desconocido",
        )

    address_matches = extract_chilean_address_matches(analysis_content)
    phone_matches = extract_chilean_phone_matches(analysis_content)
    plate_matches = extract_chilean_plate_matches(analysis_content)
    personal_data_types = _detect_personal_data_types(content_lower)
    personal_addresses = [match.address for match in address_matches]
    personal_address_scores = {match.address: match.score for match in address_matches}
    personal_address_evidence = [match.evidence for match in address_matches]
    personal_phones = [match.phone for match in phone_matches]
    personal_phone_scores = {match.phone: match.score for match in phone_matches}
    personal_phone_evidence = [match.evidence for match in phone_matches]
    personal_ruts = extract_chilean_ruts(analysis_content)
    personal_plates = [match.plate for match in plate_matches]
    personal_plate_evidence = [match.evidence for match in plate_matches]

    if contact_info:
        if contact_info.address and contact_info.address not in personal_addresses:
            personal_addresses.insert(0, contact_info.address)
            personal_address_scores[contact_info.address] = max(personal_address_scores.get(contact_info.address, 0), 5)
        if contact_info.phone and contact_info.phone not in personal_phones:
            personal_phones.insert(0, contact_info.phone)
        if contact_info.phone:
            personal_phone_scores[contact_info.phone] = max(personal_phone_scores.get(contact_info.phone, 0), 5)

        details = contact_info.details if isinstance(contact_info.details, dict) else {}
        cv_address_candidates = details.get("address_candidates", []) if isinstance(details, dict) else []
        cv_phone_candidates = details.get("phone_candidates", []) if isinstance(details, dict) else []
        should_merge_cv_address_candidates = bool(contact_info.address and contact_info.confidence >= 0.35)

        if contact_info.address:
            summary = f"[cross-validator] Direccion validada con confianza {contact_info.confidence:.2f}"
            if summary not in personal_address_evidence:
                personal_address_evidence.insert(0, summary)
        if contact_info.phone:
            summary = f"[cross-validator] Telefono validado con confianza {contact_info.confidence:.2f}"
            if summary not in personal_phone_evidence:
                personal_phone_evidence.insert(0, summary)

        for candidate in cv_address_candidates:
            if not should_merge_cv_address_candidates:
                break
            if not isinstance(candidate, dict):
                continue
            addr = str(candidate.get("address") or "").strip()
            if not addr:
                continue
            if not _is_structured_address_candidate(addr):
                continue
            score = candidate.get("score")
            if not isinstance(score, (int, float)) or int(score) < 8:
                continue
            if addr not in personal_addresses:
                personal_addresses.append(addr)
            personal_address_scores[addr] = max(int(score), personal_address_scores.get(addr, 0))
            evidence = str(candidate.get("evidence") or "").strip()
            if evidence and evidence not in personal_address_evidence and len(personal_address_evidence) < 8:
                personal_address_evidence.append(evidence)

        for candidate in cv_phone_candidates:
            if not isinstance(candidate, dict):
                continue
            phone = str(candidate.get("phone") or "").strip()
            if phone and phone not in personal_phones:
                personal_phones.append(phone)
            if phone:
                score = candidate.get("score")
                if isinstance(score, (int, float)):
                    personal_phone_scores[phone] = max(int(score), personal_phone_scores.get(phone, 0))
            evidence = str(candidate.get("evidence") or "").strip()
            if evidence and evidence not in personal_phone_evidence and len(personal_phone_evidence) < 8:
                personal_phone_evidence.append(evidence)

    # ── Objetivos opcionales para búsqueda de mayor precisión ────────────────
    matched_target_types: set[str] = set()
    target_address_fps: set[str] = set()

    if search_targets is not None:
        target_nombre    = (search_targets.nombre    or "").strip()
        target_rut       = (search_targets.rut       or "").strip()
        target_direccion = (search_targets.direccion or "").strip()
        target_telefono  = (search_targets.telefono  or "").strip()
        target_patente   = (search_targets.patente   or "").strip()

        # ── Nombre ────────────────────────────────────────────────────────────
        if target_nombre:
            matched_names = [v for v in name_candidates if _names_related(v, target_nombre)]
            # Buscar también en contenido completo (no truncado)
            if matched_names or _contains_normalized(content, target_nombre):
                name_candidates = _dedupe_preserve_order([target_nombre, *matched_names, *name_candidates])
                if "nombre" not in personal_data_types:
                    personal_data_types.append("nombre")
                matched_target_types.add("nombre")

        # ── Dirección ─────────────────────────────────────────────────────────
        if target_direccion:
            # 1) Buscar en direcciones ya extraídas (match flexible)
            matched_addresses = [v for v in personal_addresses if _address_related(v, target_direccion)]

            # 2) Siempre intentar extracción directa por nombre de calle.
            #    No gateamos en content_has_street para evitar fallos por edge cases
            #    (contenido codificado, caracteres especiales, etc.).
            if not matched_addresses:
                recovered = find_address_near_target(content, target_direccion)
                if recovered:
                    matched_addresses = [recovered]

            # 3) Si la dirección completa no se pudo extraer, verificar si la
            #    calle al menos aparece en el contenido
            street_core = _address_street_core(target_direccion)
            found_street_only = (
                not matched_addresses
                and bool(street_core and street_core in _normalize_free_text(content))
            )

            if matched_addresses or found_street_only:
                best_target = matched_addresses[0] if matched_addresses else target_direccion
                personal_addresses = _dedupe_preserve_order([best_target, *matched_addresses, *personal_addresses])
                personal_address_scores[best_target] = max(personal_address_scores.get(best_target, 0), 12)
                ev_msg = (
                    "[target] Direccion objetivo encontrada en el correo"
                    if matched_addresses else
                    "[target] Calle del objetivo mencionada en el correo"
                )
                if ev_msg not in personal_address_evidence:
                    personal_address_evidence.insert(0, ev_msg)
                if "direccion" not in personal_data_types:
                    personal_data_types.append("direccion")
                matched_target_types.add("direccion")
                target_address_fps.add(address_fingerprint(best_target))

        # ── RUT ───────────────────────────────────────────────────────────────
        if target_rut:
            matched_ruts = [v for v in personal_ruts if _rut_related(v, target_rut)]
            target_rut_norm = _normalize_rut(target_rut)
            # Buscar en contenido completo también
            rut_in_full = extract_chilean_ruts(content)
            content_has_rut = any(_rut_related(v, target_rut) for v in rut_in_full)
            if matched_ruts or content_has_rut:
                rut_to_add = target_rut_norm or target_rut
                personal_ruts = _dedupe_preserve_order([rut_to_add, *matched_ruts, *personal_ruts])
                if "rut" not in personal_data_types:
                    personal_data_types.append("rut")
                matched_target_types.add("rut")

        # ── Teléfono ──────────────────────────────────────────────────────────
        if target_telefono:
            matched_phones = [v for v in personal_phones if _phone_related(v, target_telefono)]
            # Buscar en contenido completo
            has_phone_in_full = _contains_phone_digits(content, target_telefono)
            if matched_phones or has_phone_in_full:
                phone_to_add = _normalize_phone(target_telefono) or target_telefono
                personal_phones = _dedupe_preserve_order([phone_to_add, *matched_phones, *personal_phones])
                # el teléfono objetivo confirmado es la señal más fuerte posible
                personal_phone_scores[phone_to_add] = max(personal_phone_scores.get(phone_to_add, 0), 12)
                ev_phone = "[target] Telefono objetivo encontrado en el correo"
                if ev_phone not in personal_phone_evidence:
                    personal_phone_evidence.insert(0, ev_phone)
                if "telefono" not in personal_data_types:
                    personal_data_types.append("telefono")
                matched_target_types.add("telefono")

        # ── Patente ───────────────────────────────────────────────────────────
        if target_patente:
            matched_plates = [v for v in personal_plates if _plate_related(v, target_patente)]
            target_plate_norm = _normalize_plate(target_patente)
            has_plate_in_full = _contains_plate(content, target_patente)
            if matched_plates or has_plate_in_full:
                plate_to_add = target_plate_norm or target_patente
                personal_plates = _dedupe_preserve_order([plate_to_add, *matched_plates, *personal_plates])
                ev_plate = "[target] Patente objetivo encontrada en el correo"
                if ev_plate not in personal_plate_evidence:
                    personal_plate_evidence.insert(0, ev_plate)
                if "patente" not in personal_data_types:
                    personal_data_types.append("patente")
                matched_target_types.add("patente")

    return {
        "from_addresses": from_addresses,
        "reply_to_addresses": reply_to_addresses,
        "return_path_addresses": return_path_addresses,
        "from_domain": primary_domain,
        "reply_to_domains": reply_to_domains,
        "return_path_domains": return_path_domains,
        "auth_domains": auth_domains,
        "header_ips": header_ips,
        "attachment_filenames": attachment_filenames,
        "subject": subject,
        "content_excerpt": content[:4000],
        "received_at": message.received_at,
        "is_spam": "SPAM" in label_ids,
        "is_trash": "TRASH" in label_ids,
        "subdomains": {
            subdomain
            for domain in raw_from_domains + raw_reply_to_domains + raw_return_path_domains
            for subdomain in [_extract_subdomain(domain)]
            if subdomain
        },
        "all_domains": all_domains,
        "personal_data_types": personal_data_types,
        "personal_names": name_candidates,
        "personal_addresses": personal_addresses,
        "personal_address_fingerprints": {address: address_fingerprint(address) for address in personal_addresses},
        "personal_address_scores": personal_address_scores,
        "personal_address_evidence": personal_address_evidence,
        "personal_ruts": personal_ruts,
        "personal_phones": personal_phones,
        "personal_phone_scores": personal_phone_scores,
        "personal_phone_evidence": personal_phone_evidence,
        "personal_plates": personal_plates,
        "personal_plate_evidence": personal_plate_evidence,
        "newsletter": any(hint in content_lower for hint in NEWSLETTER_HINTS),
        "marketing": any(word in content_lower for word in ("descuento", "oferta", "promo", "sale", "cyber", "black friday")),
        "matched_target_types": matched_target_types,
        "target_address_fps": target_address_fps,
    }


def _merge_message(record: SenderAggregate, parsed: dict[str, Any]) -> None:
    record.message_count += 1
    if parsed["is_spam"]:
        record.spam_count += 1
        record.tags.add("spam")
        record.risk_reasons.add("Aparece en carpeta spam")
    if parsed["is_trash"]:
        record.trash_count += 1
        record.tags.add("trash")
        record.risk_reasons.add("Aparece en papelera")
    record.from_addresses.update(parsed["from_addresses"])
    record.reply_to_addresses.update(parsed["reply_to_addresses"])
    record.return_path_addresses.update(parsed["return_path_addresses"])
    record.reply_to_domains.update(parsed["reply_to_domains"])
    record.return_path_domains.update(parsed["return_path_domains"])
    record.auth_domains.update(parsed["auth_domains"])
    record.header_ips.update(parsed["header_ips"])
    record.attachment_filenames.update(parsed["attachment_filenames"])
    record.subdomains.update(parsed["subdomains"])
    record.personal_data_types.update(parsed["personal_data_types"])
    record.personal_names.update(parsed["personal_names"])
    for address in parsed["personal_addresses"]:
        fingerprint = parsed["personal_address_fingerprints"].get(address) or address_fingerprint(address)
        record.personal_address_counts[fingerprint] = record.personal_address_counts.get(fingerprint, 0) + 1
        previous_display = record.personal_address_display_by_fingerprint.get(fingerprint)
        record.personal_address_display_by_fingerprint[fingerprint] = _choose_better_address_display(previous_display, address)
        record.personal_addresses.add(record.personal_address_display_by_fingerprint[fingerprint])
    for address, score in parsed["personal_address_scores"].items():
        fingerprint = parsed["personal_address_fingerprints"].get(address) or address_fingerprint(address)
        record.personal_address_scores[fingerprint] = max(score, record.personal_address_scores.get(fingerprint, 0))
    for evidence in parsed["personal_address_evidence"]:
        if evidence not in record.personal_address_evidence and len(record.personal_address_evidence) < 5:
            record.personal_address_evidence.append(evidence)
    record.personal_ruts.update(parsed["personal_ruts"])
    record.personal_phones.update(parsed["personal_phones"])
    # reincidencia: cada correo que menciona un teléfono suma una aparición;
    # el score de contexto se queda con el máximo observado para ese número
    for phone in parsed["personal_phones"]:
        record.personal_phone_counts[phone] = record.personal_phone_counts.get(phone, 0) + 1
    for phone, score in parsed.get("personal_phone_scores", {}).items():
        record.personal_phone_scores[phone] = max(int(score), record.personal_phone_scores.get(phone, 0))
    for evidence in parsed["personal_phone_evidence"]:
        if evidence not in record.personal_phone_evidence and len(record.personal_phone_evidence) < 5:
            record.personal_phone_evidence.append(evidence)
    record.personal_plates.update(parsed["personal_plates"])
    for evidence in parsed["personal_plate_evidence"]:
        if evidence not in record.personal_plate_evidence and len(record.personal_plate_evidence) < 5:
            record.personal_plate_evidence.append(evidence)

    subject = parsed["subject"]
    if subject and subject not in record.sample_subjects and len(record.sample_subjects) < 5:
        record.sample_subjects.append(subject)
    content_excerpt = parsed["content_excerpt"]
    if content_excerpt and content_excerpt not in record.sample_contents and len(record.sample_contents) < 3:
        record.sample_contents.append(content_excerpt)
    if record.personal_names:
        record.personal_data_types.add("nombre")
    if record.personal_addresses:
        record.personal_data_types.add("direccion")
    if record.personal_ruts:
        record.personal_data_types.add("rut")
    if record.personal_phones:
        record.personal_data_types.add("telefono")
    if record.personal_plates:
        record.personal_data_types.add("patente")

    record.first_seen = _min_date(record.first_seen, parsed["received_at"])
    record.last_seen = _max_date(record.last_seen, parsed["received_at"])

    if parsed["newsletter"]:
        record.suspected_newsletter = True
        record.risk_reasons.add("Patron de newsletter o marketing detectado")
        record.tags.add("newsletter")
    if parsed["marketing"]:
        record.aggressive_marketing = True
        record.risk_reasons.add("Contenido promocional recurrente")
        record.tags.add("marketing")

    record.matched_target_types.update(parsed.get("matched_target_types", set()))
    record.target_matched_address_fps.update(parsed.get("target_address_fps", set()))

    mismatched_domains = {
        domain for domain in parsed["reply_to_domains"] + parsed["return_path_domains"] + parsed["auth_domains"]
        if domain and domain != record.primary_domain
    }
    if mismatched_domains:
        record.suspicious_infrastructure = True
        record.risk_reasons.add("Infraestructura de envio usa dominios distintos al remitente visible")

    if record.message_count >= 8 and (record.suspected_newsletter or record.aggressive_marketing):
        record.risk_reasons.add("Alta frecuencia de correos para un posible servicio no esencial")

    if record.spam_count >= 2:
        record.risk_reasons.add("Multiples correos terminaron en spam")
    if record.trash_count >= 2:
        record.risk_reasons.add("Multiples correos terminaron en papelera")


def _classify_sender(
    primary_domain: str,
    subdomains: Iterable[str],
    subject: str,
    auth_domains: Iterable[str],
) -> dict[str, Any]:
    known = KNOWN_SENDERS.get(primary_domain)
    if known is None:
        known = next((config for domain, config in KNOWN_SENDERS.items() if primary_domain.endswith(f".{domain}")), None)

    sender_type = known["sender_type"] if known else _guess_sender_type(primary_domain, subject)
    country = known["country"] if known else _guess_country(primary_domain)
    is_chilean = known["is_chilean"] if known else _is_probably_chilean(primary_domain)
    company_name = known["company_name"] if known else _guess_company_name(primary_domain)
    confidence = 0.95 if known else (0.8 if is_chilean else 0.65)
    tags: set[str] = set()
    if known:
        tags.add("known-sender")

    if primary_domain.endswith(".cl"):
        is_chilean = True
        country = "Chile"
        tags.add("tld-cl")
        confidence = max(confidence, 0.9)

    if any(primary_domain.endswith(suffix) for suffix in CHILEAN_GOVERNMENT_SUFFIXES):
        sender_type = "gobierno"
        is_chilean = True
        country = "Chile"
        tags.add("gobierno")
        confidence = max(confidence, 0.9)

    lowered = primary_domain.lower()
    suspected_data_broker = any(keyword in lowered for keyword in DATA_BROKER_KEYWORDS)
    if suspected_data_broker:
        tags.add("data-broker")

    if any(word in lowered for word in SUSPICIOUS_KEYWORDS) or any(sub in COMMON_MAIL_SUBDOMAIN_PREFIXES for sub in subdomains):
        tags.add("delivery")

    if any(domain != primary_domain for domain in auth_domains):
        tags.add("third-party-mailer")

    return {
        "company_name": company_name,
        "primary_domain": primary_domain,
        "normalized_domain": primary_domain,
        "sender_type": sender_type,
        "country": country,
        "is_chilean": is_chilean,
        "confidence": confidence,
        "tld": _extract_tld(primary_domain),
        "tags": tags,
        "suspected_data_broker": suspected_data_broker,
    }


def _to_identified_sender(sender: SenderAggregate) -> IdentifiedSender:
    level = "low"
    if sender.suspicious_infrastructure or sender.suspected_data_broker:
        level = "high"
    elif sender.suspected_newsletter or sender.aggressive_marketing or sender.message_count >= 8 or sender.spam_count > 0 or sender.trash_count > 0:
        level = "medium"

    if sender.message_count >= 15 and level == "medium":
        sender.risk_reasons.add("Frecuencia muy alta de correos")

    if sender.personal_address_display_by_fingerprint:
        ordered_fingerprints = sorted(
            sender.personal_address_display_by_fingerprint.keys(),
            key=lambda fingerprint: (
                # Target-matched addresses always come first
                0 if fingerprint in sender.target_matched_address_fps else 1,
                -(sender.personal_address_counts.get(fingerprint, 0)),
                -(sender.personal_address_scores.get(fingerprint, 0)),
                -_address_display_rank(sender.personal_address_display_by_fingerprint[fingerprint]),
                sender.personal_address_display_by_fingerprint[fingerprint].lower(),
            ),
        )
        ordered_addresses = [sender.personal_address_display_by_fingerprint[fingerprint] for fingerprint in ordered_fingerprints]
        address_counts_by_value = {
            sender.personal_address_display_by_fingerprint[fingerprint]: sender.personal_address_counts.get(fingerprint, 0)
            for fingerprint in ordered_fingerprints
        }
        address_scores_by_value = {
            sender.personal_address_display_by_fingerprint[fingerprint]: sender.personal_address_scores.get(fingerprint, 0)
            for fingerprint in ordered_fingerprints
        }
        # If we have a target-matched address, it's always the primary
        if sender.target_matched_address_fps:
            primary_address = ordered_addresses[0]
        else:
            primary_address = select_primary_address(ordered_addresses, address_counts_by_value, address_scores_by_value)
    else:
        ordered_addresses = sorted(sender.personal_addresses)
        primary_address = select_primary_address(ordered_addresses)

    return IdentifiedSender(
        company_name=sender.company_name,
        normalized_domain=sender.normalized_domain,
        primary_domain=sender.primary_domain,
        sender_type=sender.sender_type,
        country=sender.country,
        is_chilean=sender.is_chilean,
        confidence=round(sender.confidence, 2),
        personal_data_confidence=round(_personal_data_confidence(sender), 2),
        tld=sender.tld,
        personal_data_types=sorted(sender.personal_data_types),
        personal_names=sorted(sender.personal_names),
        primary_personal_name=select_primary_name(sorted(sender.personal_names)),
        personal_addresses=ordered_addresses,
        primary_personal_address=primary_address,
        personal_address_evidence=sender.personal_address_evidence,
        personal_ruts=sorted(sender.personal_ruts),
        primary_personal_rut=select_primary_rut(sorted(sender.personal_ruts)),
        personal_phones=sorted(sender.personal_phones),
        primary_personal_phone=select_primary_phone(
            sorted(sender.personal_phones),
            counts=sender.personal_phone_counts,
            scores=sender.personal_phone_scores,
        ),
        personal_phone_evidence=sender.personal_phone_evidence,
        personal_plates=sorted(sender.personal_plates),
        primary_personal_plate=select_primary_plate(sorted(sender.personal_plates)),
        personal_plate_evidence=sender.personal_plate_evidence,
        subdomains=sorted(sender.subdomains),
        reply_to_domains=sorted(sender.reply_to_domains),
        return_path_domains=sorted(sender.return_path_domains),
        auth_domains=sorted(sender.auth_domains),
        tags=sorted(sender.tags),
        matched_targets=sorted(sender.matched_target_types),
        whois=sender.whois,
        evidence=SenderEvidence(
            message_count=sender.message_count,
            spam_count=sender.spam_count,
            trash_count=sender.trash_count,
            first_seen=sender.first_seen,
            last_seen=sender.last_seen,
            sample_subjects=sender.sample_subjects,
            attachment_filenames=sorted(sender.attachment_filenames),
            from_addresses=sorted(sender.from_addresses),
            reply_to_addresses=sorted(sender.reply_to_addresses),
            return_path_addresses=sorted(sender.return_path_addresses),
            auth_domains=sorted(sender.auth_domains),
            header_ips=sorted(sender.header_ips),
            header_ip_countries=sorted(sender.header_ip_countries),
            header_ip_chile_matches=sorted(sender.header_ip_chile_matches),
            header_ip_details=[
                HeaderIpDetail(
                    ip=item["ip"],
                    country=item.get("country"),
                    is_chilean=bool(item.get("is_chilean")),
                    criterion=item.get("criterion", "sin-datos"),
                )
                for item in sorted(sender.header_ip_details.values(), key=lambda detail: detail.get("ip", ""))
                if item.get("ip")
            ],
            subdomains=sorted(sender.subdomains),
        ),
        risk=SenderRiskAssessment(
            level=level, 
            reasons=sorted(sender.risk_reasons),
            suspected_newsletter=sender.suspected_newsletter,
            suspected_data_broker=sender.suspected_data_broker,
            suspicious_infrastructure=sender.suspicious_infrastructure,
            aggressive_marketing=sender.aggressive_marketing,
        ),
    )


def _extract_addresses(raw: str) -> list[str]:
    if not raw:
        return []
    addresses = [addr for _, addr in email.utils.getaddresses([raw]) if addr]
    if addresses:
        return sorted(set(addresses))
    fallback = re.findall(r"[\w.+-]+@[\w.-]+\.\w+", raw)
    return sorted(set(fallback))


def _extract_domains(addresses: Iterable[str]) -> list[str]:
    domains: list[str] = []
    for address in addresses:
        if "@" not in address:
            continue
        domain = address.rsplit("@", 1)[-1].strip(" >").lower()
        if domain:
            domains.append(domain)
    return domains


def _extract_auth_domains(headers: dict[str, str]) -> list[str]:
    values = " ".join(filter(None, [headers.get("authentication-results"), headers.get("received-spf"), headers.get("dkim-signature")]))
    domains = set()
    for match in re.findall(r"(?:header\.d|d|smtp\.mailfrom|envelope-from|from)=([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", values):
        normalized = _normalize_domain(match)
        if normalized:
            domains.add(normalized)
    return sorted(domains)


def _group_headers_by_name(headers: Iterable[EmailHeaderKV]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in headers:
        key = item.name.lower().strip()
        value = item.value.strip()
        if not key or not value:
            continue
        grouped.setdefault(key, []).append(value)
    return grouped


def _normalize_domain(domain: str) -> Optional[str]:
    domain = domain.strip().lower().strip(".")
    if not domain or "." not in domain:
        return None
    labels = [label for label in domain.split(".") if label]
    if len(labels) < 2:
        return None
    last_two = ".".join(labels[-2:])
    last_three = ".".join(labels[-3:]) if len(labels) >= 3 else None
    if last_three and last_two in COMMON_MULTI_PART_SUFFIXES:
        return last_three
    if len(labels) >= 3 and labels[-1] == "cl":
        return ".".join(labels[-2:])
    if len(labels) >= 3 and last_two in {"co.uk", "com.au", "co.nz", "com.br"}:
        return last_three
    return last_two


def _extract_subdomain(domain: str) -> Optional[str]:
    labels = domain.split(".")
    if len(labels) <= 2:
        return None
    return ".".join(labels[:-2])


def _extract_tld(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) >= 2:
        return f".{parts[-1]}"
    return ""


def _guess_company_name(domain: str) -> str:
    root = domain.split(".")[0]
    humanized = re.sub(r"[-_]+", " ", root)
    return humanized.title()


def _guess_sender_type(domain: str, subject: str) -> str:
    lowered = f"{domain} {subject}".lower()
    for keyword, sector in SECTOR_KEYWORDS:
        if keyword in lowered:
            return sector
    if domain.endswith(".edu") or domain.endswith(".edu.cl"):
        return "educacion"
    if domain.endswith(".gov") or domain.endswith(".gob.cl") or domain.endswith(".gov.cl"):
        return "gobierno"
    return "servicio_digital"


def _guess_country(domain: str) -> str:
    if _is_probably_chilean(domain):
        return "Chile"
    if domain.endswith(".br"):
        return "Brasil"
    if domain.endswith(".ar"):
        return "Argentina"
    if domain.endswith(".mx"):
        return "Mexico"
    if domain.endswith(".es"):
        return "Espana"
    return "Internacional"


def _is_probably_chilean(domain: str) -> bool:
    return domain.endswith(".cl") or any(domain.endswith(suffix) for suffix in CHILEAN_GOVERNMENT_SUFFIXES)


def _strip_html(value: str) -> str:
    if not value:
        return ""
    cleaned = _STYLE_SCRIPT_RE.sub(" ", value)
    cleaned = _COMMENT_RE.sub(" ", cleaned)
    no_tags = re.sub(r"<[^>]+>", " ", cleaned)
    return re.sub(r"\s+", " ", unescape(no_tags)).strip()


def _header_lookup(headers: list[EmailHeaderKV], name: str) -> Optional[str]:
    lowered = name.lower()
    for header in headers:
        if header.name.lower() == lowered:
            return header.value
    return None


def _min_date(current: Optional[str], candidate: Optional[str]) -> Optional[str]:
    if not candidate:
        return current
    if not current:
        return candidate
    return candidate if candidate < current else current


def _max_date(current: Optional[str], candidate: Optional[str]) -> Optional[str]:
    if not candidate:
        return current
    if not current:
        return candidate
    return candidate if candidate > current else current


def _extract_vcard_value(vcard_array: Any, field_name: str) -> Optional[str]:
    if not isinstance(vcard_array, list) or len(vcard_array) < 2:
        return None
    entries = vcard_array[1]
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, list) or len(entry) < 4:
            continue
        if str(entry[0]).lower() == field_name.lower():
            value = entry[3]
            if isinstance(value, str):
                return value.strip() or None
    return None


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _is_structured_address_candidate(value: str) -> bool:
    normalized = value.lower()
    if not re.search(r"(?<!\d)\d{1,5}(?!\d)", normalized):
        return False
    if len(value.split()) < 2:
        return False
    if re.search(r"\b(hasta|aprovecha|oferta|descuento|dcto|cuotas?|black|friday|cyber|promo)\b", normalized):
        return False
    return True


def _choose_better_address_display(current: Optional[str], candidate: str) -> str:
    if not current:
        return candidate
    current_rank = _address_display_rank(current)
    candidate_rank = _address_display_rank(candidate)
    if candidate_rank > current_rank:
        return candidate
    if candidate_rank == current_rank and len(candidate) > len(current):
        return candidate
    return current


def _address_display_rank(value: str) -> int:
    normalized = value.lower()
    rank = 0
    if re.search(r"\b(comuna|region|santiago|rm|metropolitana)\b", normalized):
        rank += 2
    if re.search(r"\b(depto|departamento|dpto|oficina|of)\b", normalized):
        rank += 1
    if re.search(r"\d{1,5}", normalized):
        rank += 1
    rank += min(len(value) // 20, 2)
    return rank


def _detect_personal_data_types(content_lower: str) -> list[str]:
    found: list[str] = []
    for label, patterns in PERSONAL_DATA_PATTERNS:
        if any(pattern in content_lower for pattern in patterns):
            found.append(label)
    return found


def _personal_data_confidence(sender: SenderAggregate) -> float:
    score = 0.0
    if sender.personal_names:
        score += 0.3
    if sender.personal_addresses:
        score += 0.28
    if sender.personal_ruts:
        score += 0.45
    if sender.personal_phones:
        score += 0.25
    if sender.personal_plates:
        score += 0.35
    if sender.message_count >= 2 and (sender.personal_names or sender.personal_addresses or sender.personal_ruts or sender.personal_phones or sender.personal_plates):
        score += 0.05
    return min(score, 0.99)
