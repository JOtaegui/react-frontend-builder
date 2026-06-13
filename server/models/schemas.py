"""
Schemas — modelos Pydantic que mapean 1:1 con las interfaces TypeScript del frontend.
Si agregas un campo aquí, agrégalo también en el frontend (OSINTFuentes / OSINTResumen).
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel


# ── Fuentes individuales ────────────────────────────────────────────────────

class NRYFEntry(BaseModel):
    nombre: str
    rut: str
    sexo: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None


class ServelEntry(BaseModel):
    nombre: str
    rut: str
    circunscripcion: Optional[str] = None
    region: Optional[str] = None
    mesa: Optional[str] = None
    local: Optional[str] = None
    direccion_local: Optional[str] = None


class SIIEntry(BaseModel):
    nombre: Optional[str] = None
    actividad: Optional[str] = None
    contribuyente_iva: Optional[bool] = None
    inicio_actividades: Optional[str] = None


class EmpresaEntry(BaseModel):
    razon_social: str
    rut_empresa: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None


class PjudEntry(BaseModel):
    rol: str
    tribunal: str
    materia: Optional[str] = None
    estado: Optional[str] = None
    fecha: Optional[str] = None


class DiarioOficialEntry(BaseModel):
    titulo: str
    url: str
    descripcion: Optional[str] = None


class EmailEntry(BaseModel):
    email: str
    url: Optional[str] = None
    fuente: Optional[str] = None
    contexto: Optional[str] = None
    confidence: Optional[float] = None
    match_type: Optional[str] = None
    existence_status: Optional[str] = None
    institutional_domain: Optional[str] = None
    domain_category: Optional[str] = None


class InstitucionEntry(BaseModel):
    nombre: str
    confidence: Optional[float] = None
    source_type: Optional[str] = None
    fuente: Optional[str] = None
    url: Optional[str] = None
    contexto: Optional[str] = None


# ── HIBP ────────────────────────────────────────────────────────────────────

class BreachEntry(BaseModel):
    source: str
    data_types: list[str] = []
    breach_date: Optional[str] = None


class HibpResult(BaseModel):
    email: str
    breaches: list[BreachEntry] = []
    pwned: bool = False


# ── Identificación por correo ────────────────────────────────────────────────

class EmailHeaderKV(BaseModel):
    name: str
    value: str


class AuthorizedEmailMessage(BaseModel):
    provider_message_id: Optional[str] = None
    thread_id: Optional[str] = None
    received_at: Optional[str] = None
    label_ids: list[str] = []
    subject: Optional[str] = None
    snippet: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    attachment_filenames: list[str] = []
    headers: list[EmailHeaderKV] = []


class EmailSearchTargets(BaseModel):
    nombre: Optional[str] = None
    rut: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    patente: Optional[str] = None


class EmailIdentificationRequest(BaseModel):
    provider: Literal["manual", "gmail"] = "manual"
    email_address: Optional[str] = None
    gmail_access_token: Optional[str] = None
    max_messages: int = 200
    messages: list[AuthorizedEmailMessage] = []
    search_targets: Optional[EmailSearchTargets] = None


class SenderEvidence(BaseModel):
    message_count: int = 0
    spam_count: int = 0
    trash_count: int = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    sample_subjects: list[str] = []
    attachment_filenames: list[str] = []
    from_addresses: list[str] = []
    reply_to_addresses: list[str] = []
    return_path_addresses: list[str] = []
    auth_domains: list[str] = []
    header_ips: list[str] = []
    header_ip_countries: list[str] = []
    header_ip_chile_matches: list[str] = []
    header_ip_details: list["HeaderIpDetail"] = []
    subdomains: list[str] = []


class HeaderIpDetail(BaseModel):
    ip: str
    country: Optional[str] = None
    is_chilean: bool = False
    criterion: Literal["rango-cl-lacnic", "rango-cl-csv", "rdap", "sin-datos"] = "sin-datos"


class SenderRiskAssessment(BaseModel):
    level: Literal["low", "medium", "high"] = "low"
    reasons: list[str] = []
    suspected_newsletter: bool = False
    suspected_data_broker: bool = False
    suspicious_infrastructure: bool = False
    aggressive_marketing: bool = False


class WhoisSummary(BaseModel):
    registrar: Optional[str] = None
    registrant: Optional[str] = None
    country: Optional[str] = None
    source: Optional[str] = None


class IdentifiedSender(BaseModel):
    company_name: str
    normalized_domain: str
    primary_domain: str
    sender_type: str
    country: str
    is_chilean: bool = False
    confidence: float = 0.0
    personal_data_confidence: float = 0.0
    tld: Optional[str] = None
    personal_data_types: list[str] = []
    personal_names: list[str] = []
    primary_personal_name: Optional[str] = None
    personal_addresses: list[str] = []
    primary_personal_address: Optional[str] = None
    personal_address_evidence: list[str] = []
    personal_ruts: list[str] = []
    primary_personal_rut: Optional[str] = None
    personal_phones: list[str] = []
    primary_personal_phone: Optional[str] = None
    personal_phone_evidence: list[str] = []
    personal_plates: list[str] = []
    primary_personal_plate: Optional[str] = None
    personal_plate_evidence: list[str] = []
    subdomains: list[str] = []
    reply_to_domains: list[str] = []
    return_path_domains: list[str] = []
    auth_domains: list[str] = []
    tags: list[str] = []
    matched_targets: list[str] = []
    whois: Optional[WhoisSummary] = None
    evidence: SenderEvidence
    risk: SenderRiskAssessment


class BajaReportRequest(BaseModel):
    holder_email: str
    sender: IdentifiedSender
    access_token: Optional[str] = None   # Gmail OAuth token → usa Gmail API en lugar de SMTP
    sender_email: Optional[str] = None   # dirección Gmail del usuario autenticado


class EmailIdentificationSummary(BaseModel):
    total_messages_analyzed: int = 0
    spam_messages_analyzed: int = 0
    trash_messages_analyzed: int = 0
    unique_domains: int = 0
    unique_companies: int = 0
    companies_with_user_data: list[str] = []
    chilean_companies: list[str] = []
    international_companies: list[str] = []
    risky_or_unnecessary_companies: list[str] = []
    suspicious_domains: list[str] = []
    data_brokers: list[str] = []
    spam_domains: list[str] = []
    trash_domains: list[str] = []


class ConsolidatedCandidate(BaseModel):
    """Candidato alternativo en el cruce de datos entre remitentes."""
    value: str
    sources: int                            # dominios independientes que lo respaldan
    score: float                            # proporción del puntaje ponderado (0.0–1.0)
    supporting_companies: list[str] = []


class ConsolidatedDataPoint(BaseModel):
    value: str
    sources: int        # dominios independientes que respaldan el valor
    confidence: float   # 0.0–1.0 puntaje ponderado por confiabilidad de fuentes
    confidence_level: Literal["alta", "media", "baja"] = "baja"
    supporting_companies: list[str] = []    # empresas que confirman el valor
    last_seen: Optional[str] = None         # último correo donde se observó
    alternatives: list[ConsolidatedCandidate] = []


class ConsolidatedUserProfile(BaseModel):
    """Perfil del usuario inferido por cruce entre todos los remitentes."""
    name: Optional[ConsolidatedDataPoint] = None
    rut: Optional[ConsolidatedDataPoint] = None
    address: Optional[ConsolidatedDataPoint] = None
    phone: Optional[ConsolidatedDataPoint] = None
    plate: Optional[ConsolidatedDataPoint] = None


class EmailIdentificationResponse(BaseModel):
    provider: str
    email_address: Optional[str] = None
    summary: EmailIdentificationSummary
    senders: list[IdentifiedSender] = []
    analyzed_domains: list[str] = []
    baja_violations: list["BajaViolationFound"] = []
    consolidated_profile: Optional[ConsolidatedUserProfile] = None


# ── Contenedor de todas las fuentes ─────────────────────────────────────────

class OSINTFuentes(BaseModel):
    nryf_nombre: list[NRYFEntry] = []
    nryf_rut: Optional[NRYFEntry] = None
    servel: Optional[ServelEntry] = None
    sii: Optional[SIIEntry] = None
    empresas: list[EmpresaEntry] = []
    pjud: list[PjudEntry] = []
    diario_oficial: list[DiarioOficialEntry] = []
    emails_publicos: list[EmailEntry] = []
    instituciones_relacionadas: list[InstitucionEntry] = []
    hibp: list[HibpResult] = []          # nuevo — no rompe el frontend (lo ignorará)


# ── Resumen ──────────────────────────────────────────────────────────────────

class OSINTResumen(BaseModel):
    total_hallazgos: int = 0
    fuentes_con_datos: list[str] = []
    tiene_antecedentes_judiciales: bool = False
    tiene_actividad_empresarial: bool = False
    inscrito_servel: bool = False
    emails_encontrados: list[str] = []
    total_leaks: int = 0
    advertencia: Optional[str] = None


# ── Respuesta final ──────────────────────────────────────────────────────────

class OSINTResponse(BaseModel):
    query: str
    rut: Optional[str] = None
    search_id: Optional[str] = None
    fuentes: OSINTFuentes
    resumen: OSINTResumen


# ── Errores por módulo (para el log interno, no se expone al front) ──────────

class ModuleError(BaseModel):
    module: str
    error: str


# ── Baja automática ───────────────────────────────────────────────────────────

class BajaViolationFound(BaseModel):
    """Un correo recibido de un dominio con baja activa, posterior a la solicitud."""
    baja_id: str
    dominio: str
    empresa: str
    numero_solicitud: int
    message_id: str
    received_at: str
    subject: Optional[str] = None
    from_address: Optional[str] = None
    snippet: Optional[str] = None


class BajaRecord(BaseModel):
    """Estado completo de una solicitud de baja con su historial y violaciones."""
    id: str
    dominio: str
    empresa: str
    estado: str                     # SOLICITADA|CUMPLIDA|VENCIDA|REINCIDENTE|DENUNCIADA
    numero_solicitud: int
    fecha_solicitud: str
    fecha_limite: str
    fecha_acuse: Optional[str] = None
    destinatario: str
    holder_email: str
    baja_anterior_id: Optional[str] = None
    violations: list[BajaViolationFound] = []
    dias_restantes: Optional[int] = None
    dias_en_mora: Optional[int] = None


class SolicitarBajaRequest(BaseModel):
    sender: IdentifiedSender
    holder_email: str
    destinatario: str               # email de privacidad de la empresa
    access_token: Optional[str] = None
    sender_email: Optional[str] = None


class MarcarCumplidaRequest(BaseModel):
    evidencia_aportada: Optional[str] = None


class ReescalarRequest(BaseModel):
    access_token: Optional[str] = None
    destinatario: Optional[str] = None
    sender_email: Optional[str] = None
