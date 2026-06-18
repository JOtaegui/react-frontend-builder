import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertTriangle, Building2, Car, CheckCircle2, Chrome, CreditCard, Download, Globe,
  KeyRound, LayoutDashboard, Loader2, LogIn, Mail, MapPin, Phone,
  ShieldAlert, ShieldCheck, ShieldOff, ShoppingCart, User,
} from "lucide-react";
import { exportConsolidatedToExcel, type ExportProfile } from "@/lib/exportConsolidated";

// ── LocalStorage Keys ─────────────────────────────────────────────────────────

const LS_EMAIL_RESULT   = "email_footprint_result";
const LS_BROWSER_RESULT = "browser_history_result";
const LS_EMAIL_HOLDER   = "email_footprint_holder";
const LS_HIBP_CACHE     = "consolidated_hibp_result";

// ── Breach types ──────────────────────────────────────────────────────────────

interface BreachCacheEntry {
  hasBreached: boolean;
  hibpBreach: boolean;
  clBreach: boolean;
  breachNames: string[];
}

type BreachCache = Map<string, BreachCacheEntry>;

// ── Types ─────────────────────────────────────────────────────────────────────

interface EmailSender {
  company_name: string;
  primary_domain: string;
  sender_type: string;
  country: string;
  is_chilean: boolean;
  confidence: number;
  personal_data_confidence: number;
  personal_data_types: string[];
  personal_names: string[];
  personal_addresses: string[];
  personal_ruts: string[];
  personal_phones: string[];
  personal_plates: string[];
  evidence: {
    message_count: number;
    spam_count: number;
    sample_subjects: string[];
    attachment_filenames: string[];
    from_addresses: string[];
    reply_to_addresses: string[];
    return_path_addresses: string[];
    header_ips?: string[];
    header_ip_chile_matches?: string[];
  };
  risk: { level: "low" | "medium" | "high" };
}

interface ConsolidatedCandidateRef {
  value: string;
}
interface ConsolidatedDataPoint {
  value: string;
  alternatives?: ConsolidatedCandidateRef[];
}
interface ConsolidatedUserProfile {
  name?: ConsolidatedDataPoint | null;
  rut?: ConsolidatedDataPoint | null;
  address?: ConsolidatedDataPoint | null;
  phone?: ConsolidatedDataPoint | null;
  plate?: ConsolidatedDataPoint | null;
}

interface EmailIdentificationResponse {
  email_address?: string | null;
  consolidated_profile?: ConsolidatedUserProfile | null;
  senders: EmailSender[];
}

interface ConfirmedDatum {
  tipo: string;
  tipo_key: string;
  valores: string[];
  evidencia: string;
}

interface BrowserCompany {
  domain: string;
  primary_domain: string;
  company_name: string;
  sender_type: string;
  country: string;
  is_chilean: boolean;
  visit_count: number;
  last_visit_iso: string | null;
  login_detected: boolean;
  signup_detected: boolean;
  checkout_detected: boolean;
  risk_level: "high" | "medium" | "low";
  confirmed_data: ConfirmedDatum[];
  autofill_hints: ConfirmedDatum[];
  probable_data_types: string[];
  known: boolean;
}

interface BrowserHistoryResponse {
  companies: BrowserCompany[];
}

interface ConsolidatedCompany {
  key: string;
  company_name: string;
  primary_domain: string;
  sources: Array<"email" | "browser">;
  personal_names: string[];
  personal_ruts: string[];
  personal_addresses: string[];
  personal_phones: string[];
  personal_plates: string[];
  confirmed_data: ConfirmedDatum[];
  autofill_hints: ConfirmedDatum[];
  probable_data_types: string[];
  personal_data_types: string[];
  risk_level: "low" | "medium" | "high";
  sender_type: string;
  is_chilean: boolean;
  country: string;
  confidence: number;
  personal_data_confidence: number;
  email_message_count: number;
  email_spam_count: number;
  email_header_ips: string[];
  email_header_ip_chile_matches: string[];
  email_from_addresses: string[];
  email_reply_to_addresses: string[];
  email_return_path_addresses: string[];
  email_sample_subjects: string[];
  email_attachment_filenames: string[];
  browser_visit_count: number;
  browser_login_detected: boolean;
  browser_signup_detected: boolean;
  browser_checkout_detected: boolean;
  browser_last_visit: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function normalizeDomainKey(domain: string): string {
  return domain.toLowerCase().replace(/^www\./, "").replace(/^mail\./, "").replace(/^m\./, "").trim();
}

function riskScore(level: "low" | "medium" | "high"): number {
  if (level === "high") return 30;
  if (level === "medium") return 15;
  return 5;
}

interface BreachStatus { inCl: boolean; inHibp: boolean; }

// Sensibilidad por tipo de dato: cuánto agrava la exposición que la empresa lo
// posea (un RUT o una dirección pesan más que solo el nombre).
const DATA_SENSITIVITY: Record<string, number> = {
  rut: 25, direccion: 20, telefono: 15, patente: 12, email: 10, nombre: 6,
};

// Puntaje de riesgo por empresa. Prioriza, en orden de peso:
//   1. Exposición por filtración conocida (incidente chileno o HIBP).
//   2. Sensibilidad de los datos que la empresa efectivamente posee.
//   3. Certeza de la relación (doble fuente + login/compra).
//   4. Clasificación de riesgo del backend.
//   5. Volumen de interacción (solo desempate).
function companyScore(
  c: ConsolidatedCompany,
  breach: BreachStatus,
  profile?: ConsolidatedUserProfile | null,
): number {
  // 1) Filtración: la señal más fuerte de exposición real. El incidente chileno
  //    pesa más por ser local, reciente y accionable bajo la Ley 21.719.
  const breachScore = (breach.inCl ? 80 : 0) + (breach.inHibp ? 50 : 0);

  // 2) Sensibilidad de los datos, contrastados contra el resumen para no contar
  //    falsos positivos.
  const present = new Set<string>();
  if (filterByProfile(c.personal_names, profile?.name, matchesName).length) present.add("nombre");
  if (filterByProfile(c.personal_ruts, profile?.rut, matchesRut).length) present.add("rut");
  if (filterByProfile(c.personal_addresses, profile?.address, matchesAddress).length) present.add("direccion");
  if (filterByProfile(c.personal_phones, profile?.phone, matchesPhone).length) present.add("telefono");
  if (filterByProfile(c.personal_plates, profile?.plate, matchesPlate).length) present.add("patente");
  for (const d of c.confirmed_data) {
    if (filterAutofillValues(d.tipo_key, d.valores, profile).length) present.add(d.tipo_key);
  }
  let dataScore = 0;
  present.forEach(t => { dataScore += DATA_SENSITIVITY[t] ?? 5; });

  // 3) Certeza de la relación con la empresa.
  const bothSources = c.sources.length === 2 ? 30 : 0;
  const activity = (c.browser_login_detected || c.browser_checkout_detected) ? 20 : 0;

  // 4) Clasificación de riesgo del backend.
  const risk = riskScore(c.risk_level);

  // 5) Volumen (desempate, peso acotado).
  const volume = Math.min((c.email_message_count + c.browser_visit_count) / 20, 10);

  return breachScore + dataScore + bothSources + activity + risk + volume;
}

function riskVariant(level: string): "destructive" | "default" | "secondary" {
  if (level === "high") return "destructive";
  if (level === "medium") return "default";
  return "secondary";
}

function riskIcon(level: string) {
  if (level === "high") return <ShieldOff className="h-4 w-4 text-destructive" />;
  if (level === "medium") return <ShieldAlert className="h-4 w-4 text-amber-500" />;
  return <ShieldCheck className="h-4 w-4 text-emerald-500" />;
}

const RISK_LABEL: Record<string, string> = { high: "Alto", medium: "Medio", low: "Bajo" };

const TYPE_LABEL: Record<string, string> = {
  retail: "Retail", banca: "Banca", fintech: "Fintech", salud: "Salud",
  telecomunicaciones: "Telecomunicaciones", data_broker: "Data Broker",
  gobierno: "Gobierno", delivery: "Delivery", transporte: "Transporte",
  social: "Red Social", tech: "Tecnología", afp: "AFP",
  educacion: "Educación", marketplace: "Marketplace", desconocido: "Desconocido",
};

function summarize(values: string[], fallback: string, limit = 8): string {
  const cleaned = values.filter((v, i, arr) => Boolean(v) && arr.indexOf(v) === i);
  return cleaned.length === 0 ? fallback : cleaned.slice(0, limit).join(", ");
}

// ── Normalización de datos personales para display ─────────────────────────

function normalizeRut(raw: string): string {
  // Acepta: 12345678-9 · 12.345.678-9 · 12345678K · 123456789
  const s = raw.trim().toUpperCase();
  const clean = s.replace(/\./g, "");          // quitar puntos
  if (clean.includes("-")) return clean;        // ya formateado
  if (clean.length >= 7) {                      // intentar agregar dígito verificador
    return clean.slice(0, -1) + "-" + clean.slice(-1);
  }
  return clean;
}

function normalizeName(raw: string): string {
  const s = raw.trim();
  // Si está en mayúsculas, convertir a Title Case
  if (s === s.toUpperCase() && s.length > 2) {
    return s.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
  }
  return s;
}

function normalizePhone(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  // +56 9 XXXX XXXX (11 dígitos con código país)
  if (digits.startsWith("56") && digits.length === 11) {
    return `+56 ${digits[2]} ${digits.slice(3, 7)} ${digits.slice(7)}`;
  }
  // 9 XXXX XXXX (9 dígitos celular chileno)
  if (digits.startsWith("9") && digits.length === 9) {
    return `${digits[0]} ${digits.slice(1, 5)} ${digits.slice(5)}`;
  }
  // Teléfono fijo 2-XXXX-XXXX (8 dígitos)
  if (digits.length === 8) {
    return `${digits.slice(0, 4)}-${digits.slice(4)}`;
  }
  return raw.trim();
}

function normalizePlate(raw: string): string {
  // ABCD-12 · ABCD12 · AB-1234 · AB1234
  const s = raw.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
  // Patente nueva: 4 letras + 2 números → LLLL-NN
  if (/^[A-Z]{4}\d{2}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4)}`;
  // Patente antigua: 2 letras + 4 números → LL-NNNN
  if (/^[A-Z]{2}\d{4}$/.test(s)) return `${s.slice(0, 2)}-${s.slice(2)}`;
  return s;
}

function dedup(arr: string[]): string[] {
  const seen = new Set<string>();
  return arr.filter(v => {
    const k = v.trim().toLowerCase();
    if (!k || seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

// ── Validadores de certeza (filtran falsos positivos) ─────────────────────

// Prefijos de vía chilenos (calle, avenida, pasaje, etc.)
const ADDRESS_STREET_RE = /\b(calle|av\.?|avda\.?|avenida|pasaje|psje\.?|camino|ruta|autopista|villa|poblaci[oó]n|pob\.?|condominio|cdo\.?|parcela|lote|sector|los\s|las\s|el\s|la\s|san\s|santa\s|don\s|do[nñ]a\s|parque\s|pedro|pablo|jos[eé]|mar[ií]a)\b/i;
// Palabras que indican que NO es una dirección
const ADDRESS_NOISE_RE  = /^(su\s|tu\s|el\s?(monto|total|valor|precio|costo)|código|pedido|orden|n[°º]|#\s?\d|ref\.?\s|ticket|seguimiento|confirmaci[oó]n|estimado|enviado|despacho|direcci[oó]n\s?de\s?(env[ií]o|despacho))/i;

function isLikelyAddress(raw: string): boolean {
  const s = raw.trim();
  if (s.length < 8 || s.length > 300) return false;                 // muy corto o enorme
  if (!/\d/.test(s)) return false;                                  // sin número de calle
  const letters = (s.match(/[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]/g) ?? []).length;
  if (letters < 5) return false;                                    // casi sin texto
  if (/^\$|^CLP\s*\d|^USD\s*\d/i.test(s)) return false;           // precio
  if (ADDRESS_NOISE_RE.test(s)) return false;                       // falsos positivos típicos
  // Necesita al menos: prefijo de vía O coma (ciudad) O número seguido de texto
  const hasStreetPrefix = ADDRESS_STREET_RE.test(s);
  const hasComma        = s.includes(",");
  const hasInlineNum    = /[a-zA-ZáéíóúñÑ]\s+\d{1,5}\b/.test(s) || /\b\d{1,5}\s+[a-zA-ZáéíóúñÑ]/.test(s);
  return hasStreetPrefix || hasComma || hasInlineNum;
}

// RUT: 7-8 dígitos + guión + dígito o K
function isLikelyRut(raw: string): boolean {
  const s = raw.trim().toUpperCase().replace(/\./g, "");
  // Con o sin guión: 7-8 dígitos seguidos de (- opcional) + (dígito o K)
  return /^\d{7,8}-?[0-9K]$/.test(s);
}

// Teléfono chileno: celular (9 dígitos), con código país (11), fijo (8)
function isLikelyPhone(raw: string): boolean {
  const digits = raw.replace(/\D/g, "");
  return digits.length === 8 || digits.length === 9 ||
    (digits.length === 11 && digits.startsWith("56")) ||
    (digits.length === 12 && digits.startsWith("569"));
}

// Palabras que descalifican un nombre de persona
const NAME_DISQUALIFY_RE = /\b(estimado|estimada|querido|querida|apreciado|apreciada|se[ñn]or|se[ñn]ora|cliente|usuario|usuaria|equipo|departamento|empresa|sociedad|s\.?a\.?|spa|ltda?\.?|e\.?i\.?r\.?l\.?|inc\.?|corp\.?|llc|s\.?a\.?c\.?|despacho|env[ií]o|compra|pedido|orden|transacci[oó]n|cuenta|servicio|soporte|atenci[oó]n|asesor|ejecutivo)\b/i;

// Nombre: al menos 2 palabras de 2+ chars, sin dígitos dominantes, sin palabras de saludo/empresa
function isLikelyPersonName(raw: string): boolean {
  const s = raw.trim();
  if (s.length < 5 || s.length > 120) return false;
  if (/\d{4,}/.test(s)) return false;                              // parece código con números
  if (NAME_DISQUALIFY_RE.test(s)) return false;                    // saludo, empresa, término genérico
  if (/[,;@#$%&*()\[\]{}]/.test(s)) return false;                 // caracteres raros en un nombre
  const words = s.split(/\s+/).filter(w => /^[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]{2,}$/.test(w));
  return words.length >= 2 && words.length <= 6;                   // 2-6 palabras (nombre + apellidos)
}

// Patente chilena: exactamente los patrones válidos
function isLikelyPlate(raw: string): boolean {
  const s = raw.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
  return /^[A-Z]{4}\d{2}$/.test(s) || /^[A-Z]{2}\d{4}$/.test(s);
}

interface ConfirmedField {
  key: string;
  label: string;
  icon: React.ReactNode;
  values: string[];           // valores normalizados
  colorBg: string;
  colorText: string;
  colorBorder: string;
}

// ── Filtrado contra el resumen final (perfil consolidado) ──────────────────
// El resumen final cruza datos entre todas las empresas y valida; es nuestra
// verdad de referencia. La vista por empresa, en cambio, muestra extracciones
// crudas que arrastran falsos positivos: texto de marketing tomado como nombre
// o dirección, y datos de autocompletado de prueba (RUTs/teléfonos falsos).
// Por eso, para cada tipo donde el resumen tiene un valor aceptado, solo se
// muestran los valores de la empresa compatibles con ese valor o sus
// alternativas. Donde el resumen no opina (campo nulo), no se filtra.

function acceptedValues(point?: ConsolidatedDataPoint | null): string[] {
  if (!point) return [];
  return [point.value, ...(point.alternatives ?? []).map(a => a.value)].filter(Boolean);
}
const _stripAcc = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "");
function _nameTokens(s: string): string[] {
  return _stripAcc(s.toLowerCase()).replace(/[^a-z\s]/g, " ").split(/\s+/).filter(Boolean);
}
// Un token calza con otro si es igual o si es una inicial ("j" calza con "juan").
function _tokenMatches(a: string, b: string): boolean {
  if (a === b) return true;
  if (a.length === 1) return b.startsWith(a);
  if (b.length === 1) return a.startsWith(b);
  return false;
}
function matchesName(candidate: string, accepted: string[]): boolean {
  const ct = _nameTokens(candidate);
  if (ct.length === 0) return false;
  return accepted.some(acc => {
    const at = _nameTokens(acc);
    if (at.length === 0) return false;
    // Todos los tokens del más corto deben tener correspondencia en el más
    // largo (igualdad o inicial). Así "Juan Otaegui", "J. Otaegui" y
    // "Juan I. Otaegui" calzan con "Juan Ignacio Otaegui", pero "Juan Ignacio
    // Aprovecha" no, porque "aprovecha" no corresponde a ningún token real.
    const [small, big] = ct.length <= at.length ? [ct, at] : [at, ct];
    return small.every(t => big.some(u => _tokenMatches(t, u)));
  });
}
function _addrNorm(s: string): string {
  return _stripAcc(s.toLowerCase()).replace(/[^a-z0-9]+/g, " ").trim();
}
function matchesAddress(candidate: string, accepted: string[]): boolean {
  const c = _addrNorm(candidate);
  if (c.length < 4) return false;
  return accepted.some(acc => {
    const a = _addrNorm(acc);
    return a.length >= 4 && (c.includes(a) || a.includes(c));
  });
}
function _rutKey(s: string): string { return s.toUpperCase().replace(/[^0-9K]/g, ""); }
function matchesRut(candidate: string, accepted: string[]): boolean {
  const c = _rutKey(candidate);
  return c.length >= 7 && accepted.some(acc => _rutKey(acc) === c);
}
function _phoneKey(s: string): string { return s.replace(/\D/g, "").slice(-8); }
function matchesPhone(candidate: string, accepted: string[]): boolean {
  const c = _phoneKey(candidate);
  return c.length === 8 && accepted.some(acc => _phoneKey(acc) === c);
}
function _plateKey(s: string): string { return s.toUpperCase().replace(/[^A-Z0-9]/g, ""); }
function matchesPlate(candidate: string, accepted: string[]): boolean {
  const c = _plateKey(candidate);
  return c.length >= 5 && accepted.some(acc => _plateKey(acc) === c);
}

// Filtra una lista de valores contra el resumen para un tipo dado. Si el
// resumen no tiene referencia para ese tipo, devuelve la lista intacta.
function filterByProfile(
  values: string[],
  point: ConsolidatedDataPoint | null | undefined,
  matcher: (v: string, accepted: string[]) => boolean,
): string[] {
  if (!point) return values;                 // sin referencia → no se filtra
  const accepted = acceptedValues(point);
  if (accepted.length === 0) return values;
  return values.filter(v => matcher(v, accepted));
}

// Filtra los valores de un campo de autocompletado de Chrome contra el resumen.
// El autocompletado del navegador es GLOBAL (Chrome guarda direcciones, RUTs y
// teléfonos una sola vez y se atribuyen a toda empresa con login/compra), por lo
// que arrastra datos que el usuario ingresó en otros sitios. Solo se conservan
// los valores consistentes con el resumen final. Email y usuario no tienen
// referencia en el perfil, por lo que no se filtran.
function filterAutofillValues(
  tipoKey: string,
  valores: string[],
  profile?: ConsolidatedUserProfile | null,
): string[] {
  switch (tipoKey) {
    case "nombre":    return filterByProfile(valores, profile?.name, matchesName);
    case "rut":       return filterByProfile(valores, profile?.rut, matchesRut);
    case "telefono":  return filterByProfile(valores, profile?.phone, matchesPhone);
    case "direccion": return filterByProfile(valores, profile?.address, matchesAddress);
    case "patente":   return filterByProfile(valores, profile?.plate, matchesPlate);
    case "email":     return valores.filter(v => !_isPlaceholderEmail(v));
    default:          return valores;
  }
}

// Correos de prueba/placeholder que Chrome guarda en su autocompletado y no
// corresponden a una cuenta real del usuario (no hay referencia en el perfil
// para validarlos, por lo que se descartan por patrón).
function _isPlaceholderEmail(email: string): boolean {
  const s = email.trim().toLowerCase();
  if (!s.includes("@")) return true;
  if (/@(example|test|sample|ejemplo|domain|email|mail|tld)\.(com|org|net|cl|io)$/.test(s)) return true;
  if (/^(test|prueba|ejemplo|demo|sample|noreply|no-reply|donotreply|do-not-reply|admin|root|user|usuario|cliente\d*|correo\d*)@/.test(s)) return true;
  return false;
}

function buildConfirmedFields(
  c: ConsolidatedCompany,
  profile?: ConsolidatedUserProfile | null,
): ConfirmedField[] {
  const fields: ConfirmedField[] = [];

  // Cada tipo se contrasta contra el resumen final para descartar falsos
  // positivos; donde el resumen no tiene valor, se conserva lo extraído.
  const names = dedup(
    filterByProfile(c.personal_names, profile?.name, matchesName).map(normalizeName),
  ).slice(0, 3);
  if (names.length > 0)
    fields.push({
      key: "nombre", label: "Nombre",
      icon: <User className="h-3.5 w-3.5" />,
      values: names,
      colorBg: "bg-blue-500/10", colorText: "text-blue-700 dark:text-blue-300", colorBorder: "border-blue-500/20",
    });

  const ruts = dedup(
    filterByProfile(c.personal_ruts, profile?.rut, matchesRut).map(normalizeRut),
  ).slice(0, 2);
  if (ruts.length > 0)
    fields.push({
      key: "rut", label: "RUT",
      icon: <CreditCard className="h-3.5 w-3.5" />,
      values: ruts,
      colorBg: "bg-purple-500/10", colorText: "text-purple-700 dark:text-purple-300", colorBorder: "border-purple-500/20",
    });

  const phones = dedup(
    filterByProfile(c.personal_phones, profile?.phone, matchesPhone).map(normalizePhone),
  ).slice(0, 3);
  if (phones.length > 0)
    fields.push({
      key: "telefono", label: "Teléfono",
      icon: <Phone className="h-3.5 w-3.5" />,
      values: phones,
      colorBg: "bg-emerald-500/10", colorText: "text-emerald-700 dark:text-emerald-300", colorBorder: "border-emerald-500/20",
    });

  const addresses = dedup(
    filterByProfile(c.personal_addresses, profile?.address, matchesAddress),
  ).slice(0, 2);
  if (addresses.length > 0)
    fields.push({
      key: "direccion", label: "Dirección",
      icon: <MapPin className="h-3.5 w-3.5" />,
      values: addresses,
      colorBg: "bg-amber-500/10", colorText: "text-amber-700 dark:text-amber-300", colorBorder: "border-amber-500/20",
    });

  const plates = dedup(
    filterByProfile(c.personal_plates, profile?.plate, matchesPlate).map(normalizePlate),
  ).slice(0, 2);
  if (plates.length > 0)
    fields.push({
      key: "patente", label: "Patente",
      icon: <Car className="h-3.5 w-3.5" />,
      values: plates,
      colorBg: "bg-orange-500/10", colorText: "text-orange-700 dark:text-orange-300", colorBorder: "border-orange-500/20",
    });

  // Datos del autocompletado de Chrome. El navegador suele guardar datos de
  // prueba o de terceros (RUTs, teléfonos y correos falsos), por lo que se
  // contrastan contra el resumen final igual que los del correo.
  for (const d of c.confirmed_data) {
    const vals = dedup(filterAutofillValues(d.tipo_key, d.valores, profile)).slice(0, 2);
    if (vals.length === 0) continue;
    // Evitar duplicar si ya tenemos el mismo tipo por email
    const alreadyHave = fields.some(f => f.key === d.tipo_key);
    if (!alreadyHave) {
      fields.push({
        key: d.tipo_key, label: d.tipo,
        icon: <KeyRound className="h-3.5 w-3.5" />,
        values: vals,
        colorBg: "bg-teal-500/10", colorText: "text-teal-700 dark:text-teal-300", colorBorder: "border-teal-500/20",
      });
    }
  }

  return fields;
}

function buildEmailDraft(c: ConsolidatedCompany, holderEmail: string): string {
  const allDataTypes = [
    ...(c.personal_names.length > 0 ? ["Nombre"] : []),
    ...(c.personal_ruts.length > 0 ? ["RUT"] : []),
    ...(c.personal_addresses.length > 0 ? ["Dirección"] : []),
    ...(c.personal_phones.length > 0 ? ["Teléfono"] : []),
    ...(c.personal_plates.length > 0 ? ["Patente"] : []),
    ...c.confirmed_data.map(d => d.tipo),
    ...c.probable_data_types,
  ].filter((v, i, arr) => arr.indexOf(v) === i);

  const sourceNote = c.sources.length === 2
    ? "correos electrónicos e historial de navegación"
    : c.sources.includes("email")
    ? "correos electrónicos"
    : "historial de navegación";

  const lines: string[] = [
    `Estimado equipo de privacidad de ${c.company_name},`,
    "",
    "Solicito el ejercicio de mis derechos sobre datos personales (acceso, oposición y supresión/eliminación).",
    `Esta solicitud se genera a partir del análisis de mi ${sourceNote}.`,
    "",
    `Titular: ${holderEmail || "—"}`,
    `Empresa: ${c.company_name} (${c.primary_domain})`,
    "",
    "1) Información personal detectada:",
    `   - Tipos de datos: ${summarize(allDataTypes, "Sin datos personales tipificados")}`,
  ];

  if (c.personal_names.length > 0) lines.push(`   - Nombre(s): ${summarize(c.personal_names, "No detectado")}`);
  if (c.personal_ruts.length > 0) lines.push(`   - RUT(s): ${summarize(c.personal_ruts, "No detectado")}`);
  if (c.personal_addresses.length > 0) lines.push(`   - Dirección(es): ${summarize(c.personal_addresses, "No detectado")}`);
  if (c.personal_phones.length > 0) lines.push(`   - Teléfono(s): ${summarize(c.personal_phones, "No detectado")}`);
  if (c.personal_plates.length > 0) lines.push(`   - Patente(s): ${summarize(c.personal_plates, "No detectado")}`);
  if (c.confirmed_data.length > 0)
    lines.push(`   - Datos confirmados (login Chrome): ${c.confirmed_data.map(d => `${d.tipo}: ${d.valores.join(", ")}`).join("; ")}`);

  lines.push("", "2) Evidencia del tratamiento:");

  if (c.sources.includes("email")) {
    lines.push(
      `   - Correos detectados de esta empresa: ${c.email_message_count}`,
      `   - Correos clasificados como spam: ${c.email_spam_count}`,
      `   - Remitentes (From): ${summarize(c.email_from_addresses, "No informado")}`,
      `   - Reply-To: ${summarize(c.email_reply_to_addresses, "No informado")}`,
      `   - Return-Path: ${summarize(c.email_return_path_addresses, "No informado")}`,
      `   - IPs de cabecera detectadas (${c.email_header_ips.length}): ${summarize(c.email_header_ips, "No detectadas", 12)}`,
      `   - IPs de cabecera asociadas a Chile (${c.email_header_ip_chile_matches.length}): ${summarize(c.email_header_ip_chile_matches, "No detectadas", 12)}`,
      `   - Asuntos de muestra: ${summarize(c.email_sample_subjects, "No informado", 5)}`,
      `   - Adjuntos observados: ${summarize(c.email_attachment_filenames, "No informado", 5)}`,
    );
  }

  if (c.sources.includes("browser")) {
    lines.push(`   - Visitas en historial de Chrome: ${c.browser_visit_count}`);
    if (c.browser_login_detected) lines.push("   - Login detectado en el historial de navegación");
    if (c.browser_checkout_detected) lines.push("   - Compra detectada en el historial de navegación");
  }

  lines.push(
    "",
    "3) Solicitud:",
    "   - Confirmar si mantienen mis datos personales y detallar su origen, finalidad, base legal y destinatarios.",
    "   - Eliminar/suprimir mis datos personales de sus sistemas y detener futuros envíos.",
    "   - Entregar evidencia de cumplimiento de la eliminación (fecha, sistemas impactados y terceros notificados).",
    "",
    "En caso de rechazo total o parcial, solicito su fundamento legal y el canal formal para reclamar.",
    "",
    "Saludos,",
    holderEmail || "—",
  );

  return lines.join("\n");
}

function buildSenderPayload(c: ConsolidatedCompany) {
  return {
    company_name: c.company_name,
    normalized_domain: c.primary_domain,
    primary_domain: c.primary_domain,
    sender_type: c.sender_type,
    country: c.country,
    is_chilean: c.is_chilean,
    confidence: c.confidence,
    personal_data_confidence: c.personal_data_confidence,
    personal_data_types: c.personal_data_types,
    personal_names: c.personal_names,
    personal_addresses: c.personal_addresses,
    personal_address_evidence: [],
    personal_ruts: c.personal_ruts,
    personal_phones: c.personal_phones,
    personal_phone_evidence: [],
    personal_plates: c.personal_plates,
    personal_plate_evidence: [],
    tags: [],
    matched_targets: [],
    whois: null,
    evidence: {
      message_count: c.email_message_count,
      spam_count: c.email_spam_count,
      trash_count: 0,
      first_seen: null,
      last_seen: c.browser_last_visit,
      sample_subjects: c.email_sample_subjects,
      attachment_filenames: c.email_attachment_filenames,
      from_addresses: c.email_from_addresses,
      reply_to_addresses: c.email_reply_to_addresses,
      return_path_addresses: c.email_return_path_addresses,
      auth_domains: [],
      header_ips: c.email_header_ips,
      header_ip_countries: [],
      header_ip_chile_matches: c.email_header_ip_chile_matches,
      header_ip_details: [],
      subdomains: [],
    },
    risk: {
      level: c.risk_level,
      reasons: [],
      suspected_newsletter: false,
      suspected_data_broker: c.sender_type === "data_broker",
      suspicious_infrastructure: false,
      aggressive_marketing: false,
    },
  };
}

// ── Componente ────────────────────────────────────────────────────────────────

export default function VistaConsolidada() {
  const navigate = useNavigate();
  const [holderEmail, setHolderEmail]         = useState("");
  const [selectedCompany, setSelectedCompany] = useState<ConsolidatedCompany | null>(null);
  const [sending, setSending]                 = useState(false);
  const [bajaSuccess, setBajaSuccess]         = useState<string | null>(null);
  const [bajaError, setBajaError]             = useState<string | null>(null);
  const [sentDomains, setSentDomains]         = useState<Set<string>>(new Set());

  // ── Breach data ──────────────────────────────────────────────────────────
  const [clDomains, setClDomains]   = useState<Set<string>>(new Set());
  const [hibpCache, setHibpCache]   = useState<BreachCache>(new Map());
  const [breachReady, setBreachReady] = useState(false);
  const [hibpLoading, setHibpLoading] = useState(false);
  const hibpFetchingRef = useRef(false);

  // ── Leer localStorage ────────────────────────────────────────────────────
  const { emailResult, browserResult, storedHolder } = useMemo(() => {
    try {
      const emailRaw   = localStorage.getItem(LS_EMAIL_RESULT);
      const browserRaw = localStorage.getItem(LS_BROWSER_RESULT);
      const holder     = localStorage.getItem(LS_EMAIL_HOLDER) ?? "";
      return {
        emailResult:   emailRaw   ? (JSON.parse(emailRaw)   as EmailIdentificationResponse) : null,
        browserResult: browserRaw ? (JSON.parse(browserRaw) as BrowserHistoryResponse)      : null,
        storedHolder:  holder,
      };
    } catch {
      return { emailResult: null, browserResult: null, storedHolder: "" };
    }
  }, []);

  // Resumen final (perfil consolidado): verdad de referencia para filtrar
  // falsos positivos en los detalles por empresa.
  const profile = emailResult?.consolidated_profile ?? null;

  useEffect(() => {
    if (storedHolder && !holderEmail) setHolderEmail(storedHolder);
  }, [storedHolder]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Cargar dominios de filtraciones chilenas y caché HIBP
  useEffect(() => {
    let cancelled = false;

    // 1) Lista CL desde el backend
    fetch("/api/local/breach-scraper/stats")
      .then(r => r.json())
      .then((data: { domains?: string[] }) => {
        if (cancelled) return;
        const set = new Set<string>((data.domains ?? []).map(d => normalizeDomainKey(d)));
        setClDomains(set);
      })
      .catch(() => {});

    // 2) Caché HIBP desde localStorage (guardada por BreachCrossref al analizar)
    try {
      const raw = localStorage.getItem(LS_HIBP_CACHE);
      if (raw) {
        const parsed = JSON.parse(raw) as { ts: number; breaches: Record<string, BreachCacheEntry> };
        const age = Date.now() - parsed.ts;
        if (age < 48 * 60 * 60 * 1000) {  // 48h TTL
          const map: BreachCache = new Map(Object.entries(parsed.breaches));
          setHibpCache(map);
        }
      }
    } catch { /* ignore */ }

    setBreachReady(true);
    return () => { cancelled = true; };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Merge (fusión por dominio) ───────────────────────────────────────────
  const mergedCompanies = useMemo<ConsolidatedCompany[]>(() => {
    const map = new Map<string, ConsolidatedCompany>();

    for (const sender of emailResult?.senders ?? []) {
      const key = normalizeDomainKey(sender.primary_domain ?? "");
      if (!key) continue;
      map.set(key, {
        key,
        company_name: sender.company_name,
        primary_domain: key,
        sources: ["email"],
        personal_names:    sender.personal_names    ?? [],
        personal_ruts:     sender.personal_ruts     ?? [],
        personal_addresses: sender.personal_addresses ?? [],
        personal_phones:   sender.personal_phones   ?? [],
        personal_plates:   sender.personal_plates   ?? [],
        confirmed_data:    [],
        autofill_hints:    [],
        probable_data_types: sender.personal_data_types ?? [],
        personal_data_types: sender.personal_data_types ?? [],
        risk_level:   sender.risk?.level ?? "low",
        sender_type:  sender.sender_type  ?? "",
        is_chilean:   sender.is_chilean   ?? false,
        country:      sender.country      ?? "",
        confidence:              sender.confidence              ?? 0,
        personal_data_confidence: sender.personal_data_confidence ?? 0,
        email_message_count: sender.evidence?.message_count ?? 0,
        email_spam_count:    sender.evidence?.spam_count    ?? 0,
        email_header_ips:              sender.evidence?.header_ips              ?? [],
        email_header_ip_chile_matches: sender.evidence?.header_ip_chile_matches ?? [],
        email_from_addresses:     sender.evidence?.from_addresses     ?? [],
        email_reply_to_addresses: sender.evidence?.reply_to_addresses ?? [],
        email_return_path_addresses: sender.evidence?.return_path_addresses ?? [],
        email_sample_subjects:   sender.evidence?.sample_subjects   ?? [],
        email_attachment_filenames: sender.evidence?.attachment_filenames ?? [],
        browser_visit_count:       0,
        browser_login_detected:    false,
        browser_signup_detected:   false,
        browser_checkout_detected: false,
        browser_last_visit:        null,
      });
    }

    for (const company of browserResult?.companies ?? []) {
      const key = normalizeDomainKey(company.domain ?? company.primary_domain ?? "");
      if (!key) continue;
      const existing = map.get(key);

      if (existing) {
        if (!existing.sources.includes("browser")) existing.sources.push("browser");
        existing.confirmed_data    = company.confirmed_data;
        existing.autofill_hints    = company.autofill_hints ?? [];
        existing.browser_visit_count       = company.visit_count;
        existing.browser_login_detected    = company.login_detected;
        existing.browser_signup_detected   = company.signup_detected;
        existing.browser_checkout_detected = company.checkout_detected;
        existing.browser_last_visit        = company.last_visit_iso;
        for (const dtype of company.probable_data_types) {
          if (!existing.probable_data_types.includes(dtype)) existing.probable_data_types.push(dtype);
        }
        if (riskScore(company.risk_level) > riskScore(existing.risk_level)) {
          existing.risk_level = company.risk_level;
        }
      } else {
        const dataTypes = [
          ...company.confirmed_data.map(d => d.tipo),
          ...company.probable_data_types,
        ].filter((v, i, arr) => arr.indexOf(v) === i);

        map.set(key, {
          key,
          company_name:   company.company_name,
          primary_domain: key,
          sources: ["browser"],
          personal_names:    [],
          personal_ruts:     [],
          personal_addresses: [],
          personal_phones:   [],
          personal_plates:   [],
          confirmed_data:  company.confirmed_data,
          autofill_hints:  company.autofill_hints ?? [],
          probable_data_types: company.probable_data_types,
          personal_data_types: dataTypes,
          risk_level:  company.risk_level,
          sender_type: company.sender_type ?? "",
          is_chilean:  company.is_chilean  ?? false,
          country:     company.country     ?? "",
          confidence:              company.known ? 0.9 : 0.5,
          personal_data_confidence: company.confirmed_data.length > 0 ? 0.85 : 0.4,
          email_message_count: 0,
          email_spam_count:    0,
          email_header_ips:              [],
          email_header_ip_chile_matches: [],
          email_from_addresses:     [],
          email_reply_to_addresses: [],
          email_return_path_addresses: [],
          email_sample_subjects:   [],
          email_attachment_filenames: [],
          browser_visit_count:       company.visit_count,
          browser_login_detected:    company.login_detected,
          browser_signup_detected:   company.signup_detected,
          browser_checkout_detected: company.checkout_detected,
          browser_last_visit:        company.last_visit_iso,
        });
      }
    }

    return Array.from(map.values());
  }, [emailResult, browserResult]);

  // ── Ranking por riesgo ────────────────────────────────────────────────────
  // Se ordena fuera del merge para reaccionar cuando llegan los datos de
  // filtraciones (lista CL y caché HIBP), que se cargan de forma asíncrona.
  const rankedCompanies = useMemo<ConsolidatedCompany[]>(() => {
    const breachOf = (c: ConsolidatedCompany): BreachStatus => {
      const key = normalizeDomainKey(c.primary_domain);
      return { inCl: clDomains.has(key), inHibp: hibpCache.get(key)?.hibpBreach ?? false };
    };
    return [...mergedCompanies].sort(
      (a, b) => companyScore(b, breachOf(b), profile) - companyScore(a, breachOf(a), profile),
    );
  }, [mergedCompanies, clDomains, hibpCache, profile]);

  // ── Consulta automática a HIBP ────────────────────────────────────────────
  // Al entrar al consolidado se consultan en HIBP TODOS los dominios (correo +
  // navegación) que aún no estén en caché, en lotes y con indicador de carga.
  // Solo viaja el dominio, nunca datos del usuario. El resultado se guarda en la
  // caché local (48 h) para no repetir consultas en visitas siguientes.
  // (La lista CL ya se carga completa como conjunto local en el efecto previo.)
  useEffect(() => {
    if (mergedCompanies.length === 0 || hibpFetchingRef.current) return;
    const pending = Array.from(
      new Set(mergedCompanies.map(c => normalizeDomainKey(c.primary_domain)).filter(Boolean)),
    ).filter(d => !hibpCache.has(d));
    if (pending.length === 0) return;

    hibpFetchingRef.current = true;
    setHibpLoading(true);
    let cancelled = false;

    (async () => {
      const CHUNK = 60;
      for (let i = 0; i < pending.length && !cancelled; i += CHUNK) {
        const batch = pending.slice(i, i + CHUNK);
        try {
          const r = await fetch("/api/local/hibp-check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ domains: batch }),
          });
          const data = await r.json() as { results?: Record<string, { hibpBreach: boolean; breachNames: string[] }> };
          if (cancelled || !data.results) continue;
          setHibpCache(prev => {
            const next = new Map(prev);
            for (const [dom, info] of Object.entries(data.results!)) {
              const existing = next.get(dom);
              next.set(dom, {
                hasBreached: info.hibpBreach || (existing?.clBreach ?? false),
                hibpBreach:  info.hibpBreach,
                clBreach:    existing?.clBreach ?? false,
                breachNames: info.breachNames ?? [],
              });
            }
            try {
              const obj: Record<string, BreachCacheEntry> = {};
              next.forEach((v, k) => { obj[k] = v; });
              localStorage.setItem(LS_HIBP_CACHE, JSON.stringify({ ts: Date.now(), breaches: obj }));
            } catch { /* ignore */ }
            return next;
          });
        } catch { /* lote fallido — se omite y se sigue */ }
      }
      if (!cancelled) setHibpLoading(false);
      hibpFetchingRef.current = false;
    })();

    return () => { cancelled = true; hibpFetchingRef.current = false; };
  }, [mergedCompanies]);  // eslint-disable-line react-hooks/exhaustive-deps

  const stats = useMemo(() => ({
    total:       rankedCompanies.length,
    both:        rankedCompanies.filter(c => c.sources.length === 2).length,
    emailOnly:   rankedCompanies.filter(c =>  c.sources.includes("email") && !c.sources.includes("browser")).length,
    browserOnly: rankedCompanies.filter(c => !c.sources.includes("email") &&  c.sources.includes("browser")).length,
    highRisk:    rankedCompanies.filter(c => c.risk_level === "high").length,
    inClList:    rankedCompanies.filter(c => clDomains.has(normalizeDomainKey(c.primary_domain))).length,
    inHibp:      rankedCompanies.filter(c => hibpCache.get(normalizeDomainKey(c.primary_domain))?.hibpBreach).length,
  }), [rankedCompanies, clDomains, hibpCache]);

  // ── Baja ─────────────────────────────────────────────────────────────────
  function openBaja(company: ConsolidatedCompany) {
    setBajaSuccess(null);
    setBajaError(null);
    setSelectedCompany(company);
  }

  function closeBaja() {
    setSelectedCompany(null);
    setBajaSuccess(null);
    setBajaError(null);
  }

  async function handleSendBaja() {
    if (!selectedCompany) return;
    setSending(true);
    setBajaError(null);
    setBajaSuccess(null);
    try {
      const res = await fetch("/api/identification/send-baja-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          holder_email: holderEmail,
          sender: buildSenderPayload(selectedCompany),
        }),
        signal: AbortSignal.timeout(30_000),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `Error ${res.status}`);
      setBajaSuccess(`Solicitud enviada a ${data.destination}`);
      setSentDomains(prev => new Set([...prev, selectedCompany.key]));
    } catch (err) {
      setBajaError(err instanceof Error ? err.message : "No se pudo enviar la solicitud.");
    } finally {
      setSending(false);
    }
  }

  const noData = !emailResult && !browserResult;

  const handleExport = () => {
    exportConsolidatedToExcel({
      companies: rankedCompanies,
      profile: (profile as unknown as ExportProfile) ?? null,
      holderEmail,
      emailAddress: emailResult?.email_address ?? null,
      breachOf: (c) => {
        const key = normalizeDomainKey(c.primary_domain);
        const entry = hibpCache.get(key);
        return {
          inCl: clDomains.has(key),
          inHibp: entry?.hibpBreach ?? false,
          breachNames: entry?.breachNames ?? [],
        };
      },
    });
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <Layout>
      <div className="mx-auto max-w-5xl space-y-6 p-4 sm:p-6">

        {/* Encabezado */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-400 to-violet-600 shadow-md">
            <LayoutDashboard className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Vista consolidada</h1>
            <p className="text-sm text-muted-foreground">
              Ranking de empresas detectadas en correo y navegación — con datos personales encontrados
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {hibpLoading && (
              <div className="flex items-center gap-2 rounded-full border border-red-500/20 bg-red-500/5 px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Consultando filtraciones (HIBP)…
              </div>
            )}
            {!noData && (
              <Button variant="outline" size="sm" onClick={handleExport} className="gap-2">
                <Download className="h-4 w-4" /> Exportar a Excel
              </Button>
            )}
          </div>
        </div>

        {/* Sin datos */}
        {noData && (
          <Card className="border-muted bg-muted/30">
            <CardContent className="flex flex-col items-center gap-4 py-14 text-center">
              <LayoutDashboard className="h-12 w-12 text-muted-foreground/40" />
              <div className="space-y-1">
                <p className="font-medium">No hay datos para mostrar</p>
                <p className="text-sm text-muted-foreground">
                  Ejecuta el análisis de correo o historial de navegación para poblar esta vista.
                </p>
              </div>
              <div className="flex gap-3 pt-2">
                <Button variant="outline" onClick={() => navigate("/identificacion-email")}>
                  <Mail className="mr-2 h-4 w-4" />Identificación de correo
                </Button>
                <Button variant="outline" onClick={() => navigate("/historial-browser")}>
                  <Chrome className="mr-2 h-4 w-4" />Historial de Chrome
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stats */}
        {!noData && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {[
                { label: "Empresas detectadas",  value: stats.total,       icon: Building2   },
                { label: "En ambas fuentes",      value: stats.both,        icon: Globe       },
                { label: "Alto riesgo",           value: stats.highRisk,    icon: ShieldAlert },
                { label: "Solo navegación",       value: stats.browserOnly, icon: Chrome      },
              ].map(item => (
                <Card key={item.label} className="border-violet-500/20 bg-gradient-to-br from-violet-400/10 via-background to-violet-500/[0.03] shadow-[0_16px_45px_-35px_rgba(139,92,246,0.4)]">
                  <CardContent className="p-6">
                    <item.icon className="mb-4 h-5 w-5 text-violet-500" />
                    <div className="text-3xl font-semibold sm:text-4xl">{item.value}</div>
                    <div className="mt-2 text-sm text-muted-foreground">{item.label}</div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Resumen de filtraciones */}
            {breachReady && (stats.inClList > 0 || stats.inHibp > 0) && (
              <div className="flex flex-wrap gap-3">
                {stats.inClList > 0 && (
                  <div className="flex items-center gap-2 rounded-2xl border border-orange-500/30 bg-orange-500/10 px-4 py-2 text-sm">
                    <AlertTriangle className="h-4 w-4 text-orange-500 shrink-0" />
                    <span>
                      <strong className="text-orange-600 dark:text-orange-400">{stats.inClList}</strong>
                      {" "}empresa{stats.inClList !== 1 ? "s" : ""} en la{" "}
                      <span className="font-medium">Lista de filtraciones Chile</span>
                    </span>
                  </div>
                )}
                {stats.inHibp > 0 && (
                  <div className="flex items-center gap-2 rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm">
                    <ShieldOff className="h-4 w-4 text-red-500 shrink-0" />
                    <span>
                      <strong className="text-red-600 dark:text-red-400">{stats.inHibp}</strong>
                      {" "}empresa{stats.inHibp !== 1 ? "s" : ""} con filtración en{" "}
                      <span className="font-medium">HIBP</span>
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Ranking */}
            {rankedCompanies.length > 0 && (
              <Card className="border-violet-500/20 bg-gradient-to-br from-violet-400/10 via-background to-violet-500/[0.04] shadow-[0_24px_70px_-40px_rgba(139,92,246,0.4)]">
                <CardHeader className="pb-3">
                  <CardTitle className="text-xl">Ranking por empresa</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    Orden: presencia en ambas fuentes → riesgo → tipos de datos → volumen de mensajes
                  </p>
                </CardHeader>
                <CardContent className="p-3 sm:p-5">
                  <Accordion type="multiple" className="w-full">
                    {rankedCompanies.map((company, index) => (
                      <AccordionItem
                        key={company.key}
                        value={company.key}
                        className="mb-4 overflow-hidden rounded-3xl border border-violet-500/15 bg-background/80 px-4 shadow-[0_12px_35px_-28px_rgba(139,92,246,0.55)] backdrop-blur-sm"
                      >
                        <AccordionTrigger className="py-5 hover:no-underline">
                          <div className="flex min-w-0 flex-1 items-center justify-between gap-3 pr-4 text-left">
                            <div className="flex min-w-0 items-center gap-4">
                              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-400 to-violet-600 text-sm font-semibold text-white shadow-md">
                                #{index + 1}
                              </div>
                              <div className="min-w-0">
                                <div className="truncate text-base font-semibold sm:text-lg">
                                  {company.company_name}
                                </div>
                                <div className="truncate text-sm text-muted-foreground">
                                  {company.primary_domain}
                                  {company.sender_type ? ` · ${TYPE_LABEL[company.sender_type] ?? company.sender_type}` : ""}
                                </div>
                              </div>
                            </div>
                            <div className="flex shrink-0 flex-wrap items-center gap-2">
                              {company.sources.length === 2 && (
                                <Badge className="bg-violet-600 text-white hover:bg-violet-600/90">
                                  <Mail className="mr-1 h-3 w-3" />Correo + Chrome
                                </Badge>
                              )}
                              {company.sources.length === 1 && company.sources[0] === "email" && (
                                <Badge className="bg-blue-500 text-white hover:bg-blue-500/90">
                                  <Mail className="mr-1 h-3 w-3" />Solo correo
                                </Badge>
                              )}
                              {company.sources.length === 1 && company.sources[0] === "browser" && (
                                <Badge className="bg-emerald-500 text-white hover:bg-emerald-500/90">
                                  <Chrome className="mr-1 h-3 w-3" />Solo Chrome
                                </Badge>
                              )}
                              {company.is_chilean && (
                                <Badge variant="outline" className="border-emerald-500/40 text-emerald-700 text-xs dark:text-emerald-300">
                                  CL
                                </Badge>
                              )}
                              <Badge variant={riskVariant(company.risk_level)}>
                                {RISK_LABEL[company.risk_level]}
                              </Badge>
                              {company.email_spam_count > 0 && (
                                <Badge className="bg-orange-500 text-white hover:bg-orange-500/90">
                                  <Mail className="mr-1 h-3 w-3" />En spam
                                </Badge>
                              )}
                              {clDomains.has(normalizeDomainKey(company.primary_domain)) && (
                                <Badge className="bg-orange-500 text-white hover:bg-orange-500/90">
                                  <AlertTriangle className="mr-1 h-3 w-3" />Lista CL
                                </Badge>
                              )}
                              {hibpCache.get(normalizeDomainKey(company.primary_domain))?.hibpBreach && (
                                <Badge className="bg-red-600 text-white hover:bg-red-600/90">
                                  <ShieldOff className="mr-1 h-3 w-3" />HIBP filtrado
                                </Badge>
                              )}
                              {sentDomains.has(company.key) && (
                                <Badge className="bg-emerald-600 text-white">
                                  <CheckCircle2 className="mr-1 h-3 w-3" />Baja enviada
                                </Badge>
                              )}
                            </div>
                          </div>
                        </AccordionTrigger>

                        <AccordionContent>
                          <div className="space-y-4 rounded-3xl border border-violet-500/10 bg-gradient-to-br from-violet-500/[0.06] via-background to-violet-500/[0.02] p-5">

                            {/* Datos personales encontrados con certeza */}
                            {(() => {
                              const fields = buildConfirmedFields(company, emailResult?.consolidated_profile);
                              if (fields.length === 0) return null;
                              return (
                                <div className="rounded-2xl border border-violet-500/25 bg-violet-500/[0.07] p-4 space-y-3">
                                  <div className="flex items-center gap-2">
                                    <CheckCircle2 className="h-4 w-4 text-violet-500" />
                                    <span className="text-xs font-semibold uppercase tracking-wider text-violet-700 dark:text-violet-300">
                                      Datos personales encontrados
                                    </span>
                                  </div>
                                  <div className="grid gap-2 sm:grid-cols-2">
                                    {fields.map(f => (
                                      <div
                                        key={f.key}
                                        className={`flex items-start gap-2 rounded-xl border px-3 py-2 ${f.colorBg} ${f.colorBorder}`}
                                      >
                                        <span className={`mt-0.5 shrink-0 ${f.colorText}`}>{f.icon}</span>
                                        <div className="min-w-0">
                                          <div className={`text-[10px] font-semibold uppercase tracking-wider ${f.colorText}`}>
                                            {f.label}
                                          </div>
                                          <div className="text-xs text-foreground/90 font-medium break-words">
                                            {f.values.join(" · ")}
                                          </div>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              );
                            })()}

                            {/* Fuentes de datos */}
                            <div className="grid gap-4 sm:grid-cols-2">

                              {/* Correo */}
                              {company.sources.includes("email") && (
                                <div className="space-y-2 rounded-2xl border border-blue-500/20 bg-blue-500/5 p-4">
                                  <div className="flex items-center gap-2">
                                    <Mail className="h-4 w-4 text-blue-500" />
                                    <span className="text-xs font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400">
                                      Correo electrónico
                                    </span>
                                  </div>
                                  <div className="space-y-1 text-xs text-foreground/80">
                                    <div>
                                      <span className="text-muted-foreground">Mensajes: </span>
                                      <strong>{company.email_message_count}</strong>
                                      {company.email_spam_count > 0 && (
                                        <span className="text-muted-foreground"> · {company.email_spam_count} spam</span>
                                      )}
                                    </div>
                                    {company.email_header_ips.length > 0 && (
                                      <div>
                                        <span className="text-muted-foreground">IPs detectadas: </span>
                                        <strong>{company.email_header_ips.length}</strong>
                                        {company.email_header_ip_chile_matches.length > 0 && (
                                          <span className="text-muted-foreground"> · {company.email_header_ip_chile_matches.length} en Chile</span>
                                        )}
                                      </div>
                                    )}
                                    {(() => {
                                      // Filtrado contra el resumen final: el nombre conserva
                                      // sus variantes válidas (Juan Otaegui, J. Otaegui), pero
                                      // se descartan direcciones/RUTs/teléfonos que no coinciden.
                                      const evNames = dedup(filterByProfile(company.personal_names, profile?.name, matchesName).map(normalizeName)).slice(0, 3);
                                      const evRuts  = dedup(filterByProfile(company.personal_ruts, profile?.rut, matchesRut).map(normalizeRut)).slice(0, 2);
                                      const evAddrs = dedup(filterByProfile(company.personal_addresses, profile?.address, matchesAddress)).slice(0, 1);
                                      const evPhones = dedup(filterByProfile(company.personal_phones, profile?.phone, matchesPhone).map(normalizePhone)).slice(0, 2);
                                      return (
                                        <>
                                          {evNames.length > 0 && (
                                            <div><span className="text-muted-foreground">Nombres: </span>{evNames.join(", ")}</div>
                                          )}
                                          {evRuts.length > 0 && (
                                            <div><span className="text-muted-foreground">RUT: </span>{evRuts.join(", ")}</div>
                                          )}
                                          {evAddrs.length > 0 && (
                                            <div><span className="text-muted-foreground">Dirección: </span>{evAddrs[0]}</div>
                                          )}
                                          {evPhones.length > 0 && (
                                            <div><span className="text-muted-foreground">Teléfono: </span>{evPhones.join(", ")}</div>
                                          )}
                                        </>
                                      );
                                    })()}
                                    {(() => {
                                      const evPlates = dedup(filterByProfile(company.personal_plates, profile?.plate, matchesPlate).map(normalizePlate)).slice(0, 2);
                                      return evPlates.length > 0 ? (
                                        <div><span className="text-muted-foreground">Patente: </span>{evPlates.join(", ")}</div>
                                      ) : null;
                                    })()}
                                  </div>
                                </div>
                              )}

                              {/* Navegación */}
                              {company.sources.includes("browser") && (
                                <div className="space-y-2 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4">
                                  <div className="flex items-center gap-2">
                                    <Chrome className="h-4 w-4 text-emerald-500" />
                                    <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                                      Historial Chrome
                                    </span>
                                  </div>
                                  <div className="space-y-1 text-xs text-foreground/80">
                                    <div><span className="text-muted-foreground">Visitas: </span><strong>{company.browser_visit_count}</strong></div>
                                    {company.browser_login_detected && (
                                      <div className="flex items-center gap-1">
                                        <LogIn className="h-3 w-3 text-blue-500" />
                                        <span>Login detectado</span>
                                      </div>
                                    )}
                                    {company.browser_checkout_detected && (
                                      <div className="flex items-center gap-1">
                                        <ShoppingCart className="h-3 w-3 text-purple-500" />
                                        <span>Compra detectada</span>
                                      </div>
                                    )}
                                    {company.confirmed_data.map(d => {
                                      const vals = filterAutofillValues(d.tipo_key, d.valores, profile).slice(0, 2);
                                      if (vals.length === 0) return null;
                                      return (
                                        <div key={d.tipo_key}>
                                          <span className="text-muted-foreground">
                                            <KeyRound className="mr-0.5 inline h-3 w-3 text-emerald-500" />
                                            {d.tipo}:{" "}
                                          </span>
                                          <strong>{vals.join(", ")}</strong>
                                        </div>
                                      );
                                    })}
                                    {company.autofill_hints.map(d => {
                                      const vals = filterAutofillValues(d.tipo_key, d.valores, profile).slice(0, 2);
                                      if (vals.length === 0) return null;
                                      return (
                                        <div key={d.tipo_key}>
                                          <span className="text-muted-foreground">
                                            <CheckCircle2 className="mr-0.5 inline h-3 w-3 text-blue-400" />
                                            {d.tipo}:{" "}
                                          </span>
                                          {vals.join(", ")}
                                        </div>
                                      );
                                    })}
                                    {company.probable_data_types.length > 0 && (
                                      <div className="flex flex-wrap gap-1 pt-1">
                                        {company.probable_data_types.slice(0, 4).map(t => (
                                          <Badge key={t} variant="secondary" className="text-[10px]">{t}</Badge>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>

                            {/* Estado en listas de filtraciones */}
                            {(() => {
                              const domKey  = normalizeDomainKey(company.primary_domain);
                              const inCl    = clDomains.has(domKey);
                              const entry   = hibpCache.get(domKey);
                              const inHibp  = entry?.hibpBreach ?? false;

                              // Solo se muestra si la empresa SÍ aparece en alguna
                              // filtración (Chile o HIBP). Las verificadas sin
                              // filtración no muestran nada.
                              if (!inCl && !inHibp) return null;

                              return (
                                <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-4 space-y-2">
                                  <div className="flex items-center gap-2">
                                    <ShieldOff className="h-4 w-4 text-red-500" />
                                    <span className="text-xs font-semibold uppercase tracking-wider text-red-600 dark:text-red-400">
                                      Filtraciones conocidas
                                    </span>
                                  </div>
                                  <div className="flex flex-wrap gap-2">
                                    {inCl && (
                                      <Badge className="bg-orange-500 text-white text-xs">
                                        <AlertTriangle className="mr-1 h-3 w-3" />
                                        Lista filtraciones Chile
                                      </Badge>
                                    )}
                                    {inHibp && (
                                      <Badge className="bg-red-600 text-white text-xs">
                                        <ShieldOff className="mr-1 h-3 w-3" />
                                        Have I Been Pwned — filtrado
                                      </Badge>
                                    )}
                                  </div>
                                  {inHibp && entry?.breachNames && entry.breachNames.length > 0 && (
                                    <div className="text-xs text-muted-foreground">
                                      <span className="font-medium text-foreground/70">Incidentes HIBP: </span>
                                      {entry.breachNames.slice(0, 5).join(", ")}
                                      {entry.breachNames.length > 5 && ` +${entry.breachNames.length - 5} más`}
                                    </div>
                                  )}
                                  <p className="text-xs text-muted-foreground leading-relaxed">
                                    Esta empresa ha sido identificada en una o más filtraciones de datos. Considera solicitar la baja de tus datos.
                                  </p>
                                </div>
                              );
                            })()}

                            {/* Riesgo */}
                            <div className="flex items-center gap-2 text-sm">
                              {riskIcon(company.risk_level)}
                              <span className="font-medium">Riesgo {RISK_LABEL[company.risk_level].toLowerCase()}</span>
                            </div>

                            {/* Botón baja */}
                            <div className="flex items-center justify-end gap-3">
                              {sentDomains.has(company.key) && (
                                <span className="text-xs text-emerald-600 dark:text-emerald-400">
                                  ✓ Solicitud ya enviada
                                </span>
                              )}
                              <Button
                                variant="outline"
                                className="border-violet-500/30 text-violet-700 hover:bg-violet-500/10 dark:text-violet-300"
                                onClick={() => openBaja(company)}
                              >
                                <Mail className="mr-2 h-4 w-4" />
                                Pedir baja
                              </Button>
                            </div>
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                </CardContent>
              </Card>
            )}
          </>
        )}

        {/* ── Modal baja ── */}
        <Dialog open={!!selectedCompany} onOpenChange={open => { if (!open) closeBaja(); }}>
          <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto">
            {selectedCompany && (
              <>
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2 text-base">
                    <Mail className="h-4 w-4 text-violet-500" />
                    Solicitud de baja — {selectedCompany.company_name}
                  </DialogTitle>
                </DialogHeader>

                {/* Stats clave */}
                <div className="grid grid-cols-3 divide-x divide-violet-500/15 rounded-2xl border border-violet-500/15 bg-violet-500/5">
                  {[
                    { label: "correos recibidos",   value: selectedCompany.email_message_count },
                    { label: "IPs detectadas",       value: selectedCompany.email_header_ips.length },
                    { label: "IPs en Chile",         value: selectedCompany.email_header_ip_chile_matches.length },
                  ].map(item => (
                    <div key={item.label} className="py-4 text-center">
                      <div className="text-2xl font-bold text-violet-700 dark:text-violet-300">{item.value}</div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground">{item.label}</div>
                    </div>
                  ))}
                </div>

                {/* Fuentes */}
                <div className="flex gap-2">
                  {selectedCompany.sources.includes("email") && (
                    <Badge className="bg-blue-500 text-white"><Mail className="mr-1 h-3 w-3" />Correo electrónico</Badge>
                  )}
                  {selectedCompany.sources.includes("browser") && (
                    <Badge className="bg-emerald-500 text-white"><Chrome className="mr-1 h-3 w-3" />Historial Chrome</Badge>
                  )}
                </div>

                {/* Email del titular */}
                <div className="space-y-1.5">
                  <Label htmlFor="holder-email-modal">Tu correo (titular)</Label>
                  <Input
                    id="holder-email-modal"
                    value={holderEmail}
                    onChange={e => setHolderEmail(e.target.value)}
                    placeholder="tu@correo.com"
                    type="email"
                  />
                  <p className="text-[11px] text-muted-foreground">
                    Se usará como identificador del titular en la solicitud.
                  </p>
                </div>

                {/* Preview del correo */}
                <div className="space-y-1.5">
                  <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                    Preview del correo de solicitud
                  </Label>
                  <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-2xl border border-muted bg-muted/40 p-4 font-mono text-xs leading-relaxed">
                    {buildEmailDraft(selectedCompany, holderEmail || "tu@correo.com")}
                  </pre>
                </div>

                {/* Feedback */}
                {bajaError && (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {bajaError}
                  </div>
                )}
                {bajaSuccess && (
                  <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
                    ✓ {bajaSuccess}
                  </div>
                )}

                {/* Botones */}
                <div className="flex justify-end gap-2 pt-1">
                  <Button variant="outline" onClick={closeBaja}>Cerrar</Button>
                  <Button
                    onClick={handleSendBaja}
                    disabled={sending || !!bajaSuccess}
                    className="bg-violet-600 text-white hover:bg-violet-700"
                  >
                    {sending
                      ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Enviando…</>
                      : <><Mail className="mr-2 h-4 w-4" />Enviar solicitud</>}
                  </Button>
                </div>
              </>
            )}
          </DialogContent>
        </Dialog>

      </div>
    </Layout>
  );
}
