import { useEffect, useMemo, useState } from "react";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Building2, Link2, Loader2, Mail, ShieldAlert, Telescope, Unlink2, UserRound } from "lucide-react";
import { useNavigate } from "react-router-dom";

type ProviderMode = "manual" | "gmail";
type SummarySignalType = "name" | "address" | "rut" | "phone" | "plate";
type SearchTargets = {
  nombre: string;
  rut: string;
  direccion: string;
  telefono: string;
  patente: string;
};

interface EmailIdentificationResponse {
  provider: string;
  email_address?: string | null;
  summary: {
    total_messages_analyzed: number;
    spam_messages_analyzed: number;
    trash_messages_analyzed: number;
    unique_domains: number;
    unique_companies: number;
    chilean_companies: string[];
    international_companies: string[];
    risky_or_unnecessary_companies: string[];
    suspicious_domains: string[];
    data_brokers: string[];
    spam_domains: string[];
    trash_domains: string[];
  };
  senders: Array<{
    company_name: string;
    primary_domain: string;
    sender_type: string;
    country: string;
    is_chilean: boolean;
    confidence: number;
    personal_data_confidence: number;
    personal_data_types: string[];
    personal_names: string[];
    primary_personal_name?: string | null;
    personal_addresses: string[];
    primary_personal_address?: string | null;
    personal_address_evidence: string[];
    personal_ruts: string[];
    primary_personal_rut?: string | null;
    personal_phones: string[];
    primary_personal_phone?: string | null;
    personal_phone_evidence: string[];
    personal_plates: string[];
    primary_personal_plate?: string | null;
    personal_plate_evidence: string[];
    tags: string[];
    matched_targets?: string[];
    whois?: {
      registrar?: string | null;
    } | null;
    evidence: {
      message_count: number;
      spam_count: number;
      trash_count: number;
      sample_subjects: string[];
      attachment_filenames: string[];
      from_addresses: string[];
      reply_to_addresses: string[];
      return_path_addresses: string[];
      header_ips?: string[];
      header_ip_countries?: string[];
      header_ip_chile_matches?: string[];
    };
    risk: {
      level: "low" | "medium" | "high";
      reasons: string[];
    };
  }>;
}

type EmailSender = EmailIdentificationResponse["senders"][number];

interface GmailOAuthPayload {
  access_token: string;
  email_address?: string;
}

interface GmailStatusResponse {
  configured: boolean;
  callback_origin?: string | null;
}

const sampleMessages = JSON.stringify(
  [
    {
      provider_message_id: "m-1",
      received_at: "2026-03-22T13:41:00Z",
      subject: "Tu cartola digital BancoEstado",
      snippet: "Revisa tus ultimos movimientos.",
      body_text: "Estimado Juan Perez, tu cartola ya esta disponible. Si deseas salir de esta lista usa unsubscribe.",
      headers: [
        { name: "From", value: "BancoEstado <notificaciones@mail.bancoestado.cl>" },
        { name: "Reply-To", value: "soporte@bancoestado.cl" },
        { name: "Return-Path", value: "<bounce@mailer.bancoestado.cl>" },
        { name: "Authentication-Results", value: "spf=pass smtp.mailfrom=mailer.bancoestado.cl dkim=pass header.d=bancoestado.cl" },
      ],
    },
  ],
  null,
  2,
);

const READ_ALL_MESSAGES_LIMIT = "5000";

function riskVariant(level: "low" | "medium" | "high") {
  if (level === "high") return "destructive";
  if (level === "medium") return "secondary";
  return "outline";
}

function personalDataLabel(value: string) {
  const labels: Record<string, string> = {
    nombre: "Nombre",
    direccion: "Direccion",
    patente: "Patente",
    rut: "RUT",
    telefono: "Telefono",
    pedido: "Pedidos/Compras",
    pago: "Pagos/Facturacion",
    cuenta: "Cuenta/Sesion",
  };

  return labels[value] ?? value;
}

function uniqueAddresses(sender: EmailSender) {
  return [
    ...(sender.evidence?.from_addresses ?? []),
    ...(sender.evidence?.reply_to_addresses ?? []),
    ...(sender.evidence?.return_path_addresses ?? []),
  ].filter((value, index, array) => array.indexOf(value) === index);
}

function uniqueNames(senders: EmailSender[]) {
  return senders
    .flatMap((sender) => sender.personal_names ?? [])
    .filter((value, index, array) => array.indexOf(value) === index);
}

function looksLikeEmail(value?: string | null) {
  if (!value) return false;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function chooseWebSearchEmail(senders: EmailSender[], preferred?: string | null) {
  if (looksLikeEmail(preferred)) return preferred!.trim().toLowerCase();

  const candidates = senders.flatMap((sender) => [
    ...(sender.evidence?.from_addresses ?? []),
    ...(sender.evidence?.reply_to_addresses ?? []),
    ...(sender.evidence?.return_path_addresses ?? []),
  ]);

  const normalized = candidates
    .map((item) => item.trim().toLowerCase())
    .filter((item, index, array) => array.indexOf(item) === index)
    .filter((item) => looksLikeEmail(item))
    .filter((item) => !/(^noreply@|^no-reply@|^reply-|^bounce@|mailer|notification)/.test(item));

  return normalized[0] ?? "";
}

function normalizeName(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function nameParts(value: string) {
  return normalizeName(value).split(" ").filter(Boolean);
}

function areNamesRelated(a?: string | null, b?: string | null) {
  if (!a || !b) return false;
  const aParts = nameParts(a);
  const bParts = nameParts(b);
  if (aParts.length === 0 || bParts.length === 0) return false;

  const shared = aParts.filter((part) => bParts.includes(part));
  const shorterLength = Math.min(aParts.length, bParts.length);
  const hasSubset = aParts.every((part) => bParts.includes(part)) || bParts.every((part) => aParts.includes(part));

  return hasSubset || shared.length >= Math.min(2, shorterLength);
}

function matchedNameVariants(sender: EmailSender, probableName?: string | null) {
  const names = sender.personal_names ?? [];
  if (!probableName) return names;
  const related = names.filter((name) => areNamesRelated(name, probableName));
  return related.length > 0 ? related : names;
}

function mostFrequentValue(values: string[]) {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  let best: string | null = null;
  let bestCount = 0;
  for (const [value, count] of counts.entries()) {
    if (count > bestCount) {
      best = value;
      bestCount = count;
    }
  }
  return { value: best, count: bestCount };
}

function mostProbableStructuredValue(values: string[], kind: "phone" | "plate") {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }

  let best: string | null = null;
  let bestScore = -1;
  let bestCount = 0;

  for (const [value, count] of counts.entries()) {
    const quality = kind === "phone"
      ? (value.startsWith("+56 9") ? 3 : value.startsWith("+56 2") ? 1 : 0)
      : (/^[A-Z]{4}\d{2}$/.test(value) ? 3 : /^[A-Z]{2}\d{4}$/.test(value) ? 1 : 0);
    const score = count * 4 + quality;

    if (score > bestScore || (score === bestScore && count > bestCount) || (score === bestScore && count === bestCount && value.length > (best?.length ?? 0))) {
      best = value;
      bestScore = score;
      bestCount = count;
    }
  }

  if (!best) return { value: null as string | null, count: 0 };
  const minimumCount = kind === "phone" ? 1 : 1;
  const minimumScore = kind === "phone" ? 7 : 5;
  if (bestCount < minimumCount || bestScore < minimumScore) {
    return { value: null as string | null, count: 0 };
  }
  return { value: best, count: bestCount };
}

function mostProbableName(values: string[]) {
  const unique = values.filter((value, index, array) => array.indexOf(value) === index);
  if (unique.length === 0) return { value: null as string | null, count: 0 };

  let best = unique[0];
  let bestScore = -1;

  for (const candidate of unique) {
    const parts = candidate.split(" ");
    const score = values.reduce((acc, value) => {
      if (value === candidate) return acc + 3;
      const valueParts = value.split(" ");
      const shared = parts.filter((part) => valueParts.includes(part)).length;
      return acc + shared;
    }, 0) + parts.length;

    if (score > bestScore || (score === bestScore && candidate.length > best.length)) {
      best = candidate;
      bestScore = score;
    }
  }

  const count = values.filter((value) => {
    const candidateParts = best.split(" ");
    const valueParts = value.split(" ");
    return candidateParts.every((part) => valueParts.includes(part)) || valueParts.every((part) => candidateParts.includes(part));
  }).length;

  return { value: best, count };
}

function confidenceLabel(value: number) {
  if (value >= 0.75) return "Alta";
  if (value >= 0.4) return "Media";
  return "Baja";
}

function summarizeList(values: Array<string | null | undefined>, fallback: string, limit = 8) {
  const cleaned = values
    .map((value) => (value ?? "").trim())
    .filter(Boolean)
    .filter((value, index, array) => array.indexOf(value) === index);
  if (cleaned.length === 0) return fallback;
  return cleaned.slice(0, limit).join(", ");
}

function buildDataRightsDraft(sender: EmailSender, holderEmail: string) {
  const headerIps = sender.evidence?.header_ips ?? [];
  const chileIps = sender.evidence?.header_ip_chile_matches ?? [];
  const fromAddresses = sender.evidence?.from_addresses ?? [];
  const replyToAddresses = sender.evidence?.reply_to_addresses ?? [];
  const returnPathAddresses = sender.evidence?.return_path_addresses ?? [];
  const sampleSubjects = sender.evidence?.sample_subjects ?? [];
  const attachmentFilenames = sender.evidence?.attachment_filenames ?? [];
  const personalDataTypes = (sender.personal_data_types ?? []).map((item) => personalDataLabel(item));

  return [
    `Estimado equipo de privacidad de ${sender.company_name},`,
    "",
    "Solicito el ejercicio de mis derechos sobre datos personales (acceso, oposicion y supresion/eliminacion).",
    "Este correo se envia en modo prueba a mi propia casilla para validar el formato antes de enviarlo a la empresa.",
    "",
    `Titular: ${holderEmail}`,
    `Empresa analizada: ${sender.company_name} (${sender.primary_domain})`,
    "",
    "1) Informacion personal detectada en sus correos:",
    `- Tipos de datos: ${summarizeList(personalDataTypes, "Sin datos personales tipificados")}`,
    `- Nombre(s): ${summarizeList(sender.personal_names ?? [], "No detectado")}`,
    `- Direccion(es): ${summarizeList(sender.personal_addresses ?? [], "No detectado")}`,
    `- RUT(s): ${summarizeList(sender.personal_ruts ?? [], "No detectado")}`,
    `- Telefono(s): ${summarizeList(sender.personal_phones ?? [], "No detectado")}`,
    `- Patente(s): ${summarizeList(sender.personal_plates ?? [], "No detectado")}`,
    "",
    "2) Evidencia del tratamiento y envio de correos:",
    `- Cantidad de correos detectados de esta empresa: ${sender.evidence?.message_count ?? 0}`,
    `- Correos clasificados como spam: ${sender.evidence?.spam_count ?? 0}`,
    `- Correos clasificados como papelera: ${sender.evidence?.trash_count ?? 0}`,
    `- Remitentes (From): ${summarizeList(fromAddresses, "No informado")}`,
    `- Reply-To: ${summarizeList(replyToAddresses, "No informado")}`,
    `- Return-Path: ${summarizeList(returnPathAddresses, "No informado")}`,
    `- IPs de cabecera detectadas (${headerIps.length}): ${summarizeList(headerIps, "No detectadas", 12)}`,
    `- IPs de cabecera asociadas a Chile (${chileIps.length}): ${summarizeList(chileIps, "No detectadas", 12)}`,
    `- Asuntos de muestra: ${summarizeList(sampleSubjects, "No informado", 6)}`,
    `- Adjuntos observados: ${summarizeList(attachmentFilenames, "No informado", 6)}`,
    "",
    "3) Solicitud:",
    "- Confirmar si mantienen mis datos personales y detallar su origen, finalidad, base legal y destinatarios.",
    "- Eliminar/suprimir mis datos personales de sus sistemas y detener futuros envios.",
    "- Entregar evidencia de cumplimiento de la eliminacion (fecha, sistemas impactados y terceros notificados).",
    "",
    "En caso de rechazo total o parcial, solicito su fundamento legal y el canal formal para reclamar.",
    "",
    "Saludos,",
    holderEmail,
  ].join("\n");
}

function availableSummarySignal(summarySignals: {
  name: { value: string | null; count: number };
  address: { value: string | null; count: number };
  rut: { value: string | null; count: number };
  phone: { value: string | null; count: number };
  plate: { value: string | null; count: number };
}): SummarySignalType {
  if (summarySignals.name.value) return "name";
  if (summarySignals.address.value) return "address";
  if (summarySignals.rut.value) return "rut";
  if (summarySignals.phone.value) return "phone";
  return "plate";
}

export default function EmailIdentificacion() {
  const navigate = useNavigate();
  const [provider, setProvider] = useState<ProviderMode>("gmail");
  const [emailAddress, setEmailAddress] = useState("");
  const [gmailAuth, setGmailAuth] = useState<GmailOAuthPayload | null>(null);
  const [gmailConfigured, setGmailConfigured] = useState<boolean | null>(null);
  const [gmailCallbackOrigin, setGmailCallbackOrigin] = useState<string | null>(null);
  const [oauthLoading, setOauthLoading] = useState(false);
  const [maxMessages, setMaxMessages] = useState("150");
  const [searchTargets, setSearchTargets] = useState<SearchTargets>({
    nombre: "",
    rut: "",
    direccion: "",
    telefono: "",
    patente: "",
  });
  const [messagesJson, setMessagesJson] = useState(sampleMessages);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<EmailIdentificationResponse | null>(null);
  const [selectedSummarySignal, setSelectedSummarySignal] = useState<SummarySignalType>("name");
  const [draftError, setDraftError] = useState<string | null>(null);
  const [draftSuccess, setDraftSuccess] = useState<string | null>(null);
  const [sendingBaja, setSendingBaja] = useState<string | null>(null);
  const [bajaDestination, setBajaDestination] = useState<string | null>(null);
  const [bajaSmtpOk, setBajaSmtpOk] = useState<boolean | null>(null);

  const payloadPreview = useMemo(() => {
    try {
      const parsed = JSON.parse(messagesJson);
      return Array.isArray(parsed) ? `${parsed.length}` : "0";
    } catch {
      return "0";
    }
  }, [messagesJson]);

  useEffect(() => {
    fetch("/api/identification/baja-status", { signal: AbortSignal.timeout(5000) })
      .then((r) => r.json())
      .then((data) => {
        setBajaSmtpOk(Boolean(data.smtp_configured));
        setBajaDestination(data.destination ?? null);
      })
      .catch(() => {
        setBajaSmtpOk(false);
      });
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadStatus = async () => {
      try {
        const res = await fetch("/api/auth/gmail/status", { signal: AbortSignal.timeout(8000) });
        const data: GmailStatusResponse = await res.json();
        if (!cancelled) {
          setGmailConfigured(Boolean(data.configured));
          setGmailCallbackOrigin(data.callback_origin ?? null);
        }
      } catch {
        if (!cancelled) setGmailConfigured(false);
      }
    };

    void loadStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const allowedOrigins = new Set(
        [window.location.origin, gmailCallbackOrigin].filter((value): value is string => Boolean(value)),
      );
      if (!allowedOrigins.has(event.origin)) return;

      if (event.data?.type === "gmail-oauth-success") {
        const payload = event.data.payload as GmailOAuthPayload;
        setGmailAuth(payload);
        setEmailAddress(payload.email_address ?? "");
        setOauthLoading(false);
        setError(null);
      }

      if (event.data?.type === "gmail-oauth-error") {
        setOauthLoading(false);
        setError(event.data.message ?? "No se pudo conectar Gmail.");
      }
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [gmailCallbackOrigin]);

  const connectGmail = () => {
    setOauthLoading(true);
    setError(null);
    const popup = window.open("/api/auth/gmail/start", "gmail-oauth", "popup=yes,width=540,height=720,resizable=yes,scrollbars=yes");
    if (!popup) {
      setOauthLoading(false);
      setError("No se pudo abrir el popup.");
    }
  };

  const disconnectGmail = () => {
    setGmailAuth(null);
    setResult(null);
    setError(null);
    if (provider === "gmail") setEmailAddress("");
  };

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const payload: Record<string, unknown> = {
        provider,
        email_address: emailAddress.trim() || undefined,
        max_messages: Number(maxMessages) || 150,
      };
      const normalizedTargets = Object.fromEntries(
        Object.entries(searchTargets)
          .map(([key, value]) => [key, value.trim()])
          .filter(([, value]) => Boolean(value)),
      );
      if (Object.keys(normalizedTargets).length > 0) {
        payload.search_targets = normalizedTargets;
      }

      if (provider === "gmail") {
        if (!gmailAuth?.access_token) throw new Error("Conecta Gmail primero.");
        payload.gmail_access_token = gmailAuth.access_token;
      } else {
        payload.messages = JSON.parse(messagesJson);
      }

      const res = await fetch("/api/identification/email-footprint", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(240_000),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo analizar.");
    } finally {
      setLoading(false);
    }
  };

  const canAnalyze = provider === "gmail" ? Boolean(gmailAuth?.access_token) : payloadPreview !== "0";
  const draftDestination = useMemo(() => {
    if (looksLikeEmail(emailAddress)) return emailAddress.trim().toLowerCase();
    if (looksLikeEmail(gmailAuth?.email_address)) return (gmailAuth?.email_address ?? "").trim().toLowerCase();
    return "";
  }, [emailAddress, gmailAuth?.email_address]);
  const namesFound = useMemo(() => uniqueNames(result?.senders ?? []), [result]);
  const sendersWithPersonalData = useMemo(
    () => (result?.senders ?? []).filter((sender) =>
      (sender.personal_data_types ?? []).length > 0 ||
      (sender.personal_names ?? []).length > 0 ||
      (sender.personal_addresses ?? []).length > 0 ||
      (sender.personal_ruts ?? []).length > 0 ||
      (sender.personal_phones ?? []).length > 0 ||
      (sender.personal_plates ?? []).length > 0,
    ),
    [result],
  );
  const rankedSenders = useMemo(
    () => [...sendersWithPersonalData].sort((a, b) =>
      ((b.matched_targets?.length ?? 0) > 0 ? 1 : 0) - ((a.matched_targets?.length ?? 0) > 0 ? 1 : 0) ||
      (b.personal_data_confidence ?? 0) - (a.personal_data_confidence ?? 0) ||
      (b.evidence?.message_count ?? 0) - (a.evidence?.message_count ?? 0) ||
      a.company_name.localeCompare(b.company_name),
    ),
    [sendersWithPersonalData],
  );
  const summarySignals = useMemo(() => {
    const senders = result?.senders ?? [];
    // Senders with target match are higher priority for "most probable"
    const targetMatchedSenders = senders.filter((s) => (s.matched_targets?.length ?? 0) > 0);
    const pickFrom = (field: "personal_names" | "personal_ruts" | "personal_phones" | "personal_plates") =>
      targetMatchedSenders.length > 0
        ? [...targetMatchedSenders.flatMap((s) => (s[field] as string[]) ?? []), ...senders.flatMap((s) => (s[field] as string[]) ?? [])]
        : senders.flatMap((s) => (s[field] as string[]) ?? []);
    const pickAddresses = () => {
      if (targetMatchedSenders.length > 0) {
        const targetAddresses = targetMatchedSenders.flatMap((s) => s.primary_personal_address ? [s.primary_personal_address] : []);
        const allAddresses = senders.flatMap((s) => s.primary_personal_address ? [s.primary_personal_address] : []);
        return [...targetAddresses, ...allAddresses];
      }
      return senders.flatMap((s) => s.primary_personal_address ? [s.primary_personal_address] : []);
    };
    const names = pickFrom("personal_names");
    const addresses = pickAddresses();
    const ruts = pickFrom("personal_ruts");
    const phones = pickFrom("personal_phones");
    const plates = pickFrom("personal_plates");
    const avgConfidence = sendersWithPersonalData.length > 0
      ? sendersWithPersonalData.reduce((acc, sender) => acc + (sender.personal_data_confidence ?? 0), 0) / sendersWithPersonalData.length
      : 0;

    return {
      name: mostProbableName(names),
      address: mostFrequentValue(addresses),
      rut: mostFrequentValue(ruts),
      phone: mostProbableStructuredValue(phones, "phone"),
      plate: mostProbableStructuredValue(plates, "plate"),
      avgConfidence,
    };
  }, [result, sendersWithPersonalData]);
  const probableName = summarySignals.name.value;
  const summaryEvidence = useMemo(() => {
    return {
      name: (result?.senders ?? [])
        .filter((sender) => probableName && matchedNameVariants(sender, probableName).length > 0)
        .map((sender) => ({
          company: sender.company_name,
          domain: sender.primary_domain,
          variants: matchedNameVariants(sender, probableName),
          locations: [
            ...(sender.evidence.sample_subjects ?? []).slice(0, 2).map((subject) => `Correo: ${subject}`),
            ...(sender.evidence.attachment_filenames ?? []).slice(0, 2).map((filename) => `Adjunto: ${filename}`),
          ],
          evidence: ["Detectado en el contenido analizado del correo."],
        })),
      address: (result?.senders ?? [])
        .filter((sender) => summarySignals.address.value && (sender.personal_addresses ?? []).includes(summarySignals.address.value))
        .map((sender) => ({
          company: sender.company_name,
          domain: sender.primary_domain,
          variants: [summarySignals.address.value as string],
          locations: [
            ...(sender.evidence.sample_subjects ?? []).slice(0, 2).map((subject) => `Correo: ${subject}`),
            ...(sender.evidence.attachment_filenames ?? []).slice(0, 2).map((filename) => `Adjunto: ${filename}`),
          ],
          evidence: (sender.personal_address_evidence ?? []).slice(0, 3).length > 0
            ? (sender.personal_address_evidence ?? []).slice(0, 3)
            : ["Detectado en el contenido analizado del correo."],
        })),
      rut: (result?.senders ?? [])
        .filter((sender) => summarySignals.rut.value && (sender.personal_ruts ?? []).includes(summarySignals.rut.value))
        .map((sender) => ({
          company: sender.company_name,
          domain: sender.primary_domain,
          variants: [summarySignals.rut.value as string],
          locations: [
            ...(sender.evidence.sample_subjects ?? []).slice(0, 2).map((subject) => `Correo: ${subject}`),
            ...(sender.evidence.attachment_filenames ?? []).slice(0, 2).map((filename) => `Adjunto: ${filename}`),
          ],
          evidence: ["Detectado en el contenido analizado del correo."],
        })),
      phone: (result?.senders ?? [])
        .filter((sender) => summarySignals.phone.value && (sender.personal_phones ?? []).includes(summarySignals.phone.value))
        .map((sender) => ({
          company: sender.company_name,
          domain: sender.primary_domain,
          variants: [summarySignals.phone.value as string],
          locations: [
            ...(sender.evidence.sample_subjects ?? []).slice(0, 2).map((subject) => `Correo: ${subject}`),
            ...(sender.evidence.attachment_filenames ?? []).slice(0, 2).map((filename) => `Adjunto: ${filename}`),
          ],
          evidence: (sender.personal_phone_evidence ?? []).slice(0, 3).length > 0
            ? (sender.personal_phone_evidence ?? []).slice(0, 3)
            : ["Detectado en el contenido analizado del correo."],
        })),
      plate: (result?.senders ?? [])
        .filter((sender) => summarySignals.plate.value && (sender.personal_plates ?? []).includes(summarySignals.plate.value))
        .map((sender) => ({
          company: sender.company_name,
          domain: sender.primary_domain,
          variants: [summarySignals.plate.value as string],
          locations: [
            ...(sender.evidence.sample_subjects ?? []).slice(0, 2).map((subject) => `Correo: ${subject}`),
            ...(sender.evidence.attachment_filenames ?? []).slice(0, 2).map((filename) => `Adjunto: ${filename}`),
          ],
          evidence: (sender.personal_plate_evidence ?? []).slice(0, 3),
        })),
    };
  }, [probableName, result, summarySignals.address.value, summarySignals.phone.value, summarySignals.plate.value, summarySignals.rut.value]);

  useEffect(() => {
    setSelectedSummarySignal(availableSummarySignal(summarySignals));
  }, [summarySignals]);

  const openHeaderAnalysisView = () => {
    if (!result) return;
    navigate("/cabeceras-empresa-temp", {
      state: {
        prefilledResult: result,
        source: "investigacion",
      },
    });
  };

  const openWebExposureView = () => {
    if (!result) return;
    const probableWebName = summarySignals.name.value ?? namesFound[0] ?? "";
    const probableWebRut = summarySignals.rut.value ?? "";
    const probableWebEmail = chooseWebSearchEmail(result.senders ?? [], emailAddress);

    navigate("/exposicion-web-temp", {
      state: {
        source: "investigacion",
        prefilledIdentity: {
          nombre: probableWebName,
          rut: probableWebRut,
          email: probableWebEmail,
        },
      },
    });
  };

  const openUnsubscribeDraft = async (sender: EmailSender) => {
    setDraftError(null);
    setDraftSuccess(null);
    setSendingBaja(sender.company_name);

    const holderEmail = draftDestination || result?.email_address || "usuario@desconocido";

    try {
      const res = await fetch("/api/identification/send-baja-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          holder_email: holderEmail,
          sender,
          access_token: gmailAuth?.access_token ?? null,
          sender_email: gmailAuth?.email_address ?? null,
        }),
        signal: AbortSignal.timeout(30_000),
      });

      const data = await res.json();

      if (!res.ok) {
        setDraftError(data.detail ?? `Error ${res.status} al enviar el informe.`);
        return;
      }

      setDraftSuccess(`Informe de ${sender.company_name} enviado a ${data.destination}.`);
    } catch (err) {
      setDraftError(err instanceof Error ? err.message : "No se pudo enviar el informe.");
    } finally {
      setSendingBaja(null);
    }
  };

  const updateSearchTarget = (field: keyof SearchTargets, value: string) => {
    setSearchTargets((previous) => ({ ...previous, [field]: value }));
  };

  return (
    <Layout>
      <div className="mx-auto max-w-[1760px] space-y-8 px-2 sm:px-4 lg:px-6">
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Exposicion por correo</h1>
          <p className="mx-auto max-w-3xl text-sm text-muted-foreground sm:text-base">
            Conecta tu correo y ejecuta el analisis. Los resultados apareceran despues organizados por empresa en dropdowns.
          </p>
        </div>

        <Card className="border-emerald-500/25 bg-gradient-to-b from-emerald-400/15 via-background to-background shadow-[0_18px_60px_-30px_rgba(16,185,129,0.45)]">
          <CardContent className="space-y-6 p-6 sm:p-8">
            <div className="flex justify-center gap-2">
              <Button variant={provider === "gmail" ? "default" : "outline"} onClick={() => setProvider("gmail")}>Gmail</Button>
              <Button variant={provider === "manual" ? "default" : "outline"} onClick={() => setProvider("manual")}>Manual</Button>
            </div>

            <div className="mx-auto max-w-4xl space-y-5">
              <div className="space-y-2">
                <Label htmlFor="emailAddress">Cuenta</Label>
                <Input
                  id="emailAddress"
                  value={emailAddress}
                  onChange={(event) => setEmailAddress(event.target.value)}
                  placeholder="usuario@gmail.com"
                  className="h-12 text-base"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor="maxMessages">Mensajes a revisar</Label>
                  <Button
                    type="button"
                    variant={maxMessages === READ_ALL_MESSAGES_LIMIT ? "default" : "outline"}
                    onClick={() => setMaxMessages(READ_ALL_MESSAGES_LIMIT)}
                    className={maxMessages === READ_ALL_MESSAGES_LIMIT ? "bg-emerald-500 text-white hover:bg-emerald-600" : ""}
                  >
                    Leer todos los mensajes
                  </Button>
                </div>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Input
                    id="maxMessages"
                    value={maxMessages === READ_ALL_MESSAGES_LIMIT ? "" : maxMessages}
                    onChange={(event) => setMaxMessages(event.target.value.replace(/[^\d]/g, ""))}
                    inputMode="numeric"
                    placeholder={maxMessages === READ_ALL_MESSAGES_LIMIT ? "Leyendo todos los mensajes" : "150"}
                    className="h-12 flex-1 text-base"
                  />
                  {maxMessages === READ_ALL_MESSAGES_LIMIT && (
                    <Button type="button" variant="outline" onClick={() => setMaxMessages("150")} className="h-12 sm:w-auto">
                      Usar limite manual
                    </Button>
                  )}
                </div>
                <div className="text-xs text-muted-foreground">
                  {maxMessages === READ_ALL_MESSAGES_LIMIT
                    ? "Se intentaran revisar todos los mensajes disponibles de la cuenta."
                    : "Tambien puedes indicar un numero exacto de mensajes a revisar."}
                </div>
              </div>

              <div className="space-y-3 rounded-2xl border border-emerald-500/15 bg-emerald-500/[0.04] p-4">
                <div className="space-y-1">
                  <Label className="text-sm">Parametros opcionales para mayor precision</Label>
                  <p className="text-xs text-muted-foreground">
                    Si completas estos datos, el analisis prioriza coincidencias de nombre, RUT, direccion, telefono y patente.
                  </p>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="targetNombre" className="text-xs text-muted-foreground">Nombre objetivo</Label>
                    <Input
                      id="targetNombre"
                      value={searchTargets.nombre}
                      onChange={(event) => updateSearchTarget("nombre", event.target.value)}
                      placeholder="Nombre Apellido"
                      className="h-10 text-sm"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="targetRut" className="text-xs text-muted-foreground">RUT objetivo</Label>
                    <Input
                      id="targetRut"
                      value={searchTargets.rut}
                      onChange={(event) => updateSearchTarget("rut", event.target.value)}
                      placeholder="12.345.678-9"
                      className="h-10 text-sm"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="targetDireccion" className="text-xs text-muted-foreground">Direccion objetivo</Label>
                    <Input
                      id="targetDireccion"
                      value={searchTargets.direccion}
                      onChange={(event) => updateSearchTarget("direccion", event.target.value)}
                      placeholder="Av. Apoquindo 4501, Las Condes"
                      className="h-10 text-sm"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="targetTelefono" className="text-xs text-muted-foreground">Telefono objetivo</Label>
                    <Input
                      id="targetTelefono"
                      value={searchTargets.telefono}
                      onChange={(event) => updateSearchTarget("telefono", event.target.value)}
                      placeholder="+56 9 1234 5678"
                      className="h-10 text-sm"
                    />
                  </div>
                  <div className="space-y-1.5 md:col-span-2">
                    <Label htmlFor="targetPatente" className="text-xs text-muted-foreground">Patente objetivo</Label>
                    <Input
                      id="targetPatente"
                      value={searchTargets.patente}
                      onChange={(event) => updateSearchTarget("patente", event.target.value.toUpperCase())}
                      placeholder="ABCD12"
                      className="h-10 text-sm"
                    />
                  </div>
                </div>
              </div>

              {provider === "gmail" ? (
                <div className="space-y-4 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium">Conexion Gmail</div>
                      <div className="text-xs text-muted-foreground">
                        {gmailAuth?.email_address ?? "Autoriza la cuenta para continuar."}
                      </div>
                    </div>
                    <Badge variant={gmailAuth ? "secondary" : "outline"} className={gmailAuth ? "bg-emerald-500 text-white hover:bg-emerald-500/90" : ""}>
                      {gmailAuth ? "Conectado" : "Pendiente"}
                    </Badge>
                  </div>

                  <div className="flex flex-col gap-3 sm:flex-row">
                    <Button onClick={connectGmail} disabled={!gmailConfigured || oauthLoading} className="h-12 flex-1 bg-emerald-500 text-base text-white hover:bg-emerald-600">
                      {oauthLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
                      Conectar Gmail
                    </Button>
                    <Button variant="outline" onClick={disconnectGmail} disabled={!gmailAuth} className="h-12 sm:w-auto">
                      <Unlink2 className="h-4 w-4" />
                    </Button>
                  </div>

                  {gmailConfigured === false && (
                    <div className="text-xs text-destructive">Falta configurar Google OAuth en el backend.</div>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="messagesJson">Mensajes autorizados</Label>
                    <span className="text-xs text-muted-foreground">{payloadPreview} mensajes</span>
                  </div>
                  <Textarea
                    id="messagesJson"
                    value={messagesJson}
                    onChange={(event) => setMessagesJson(event.target.value)}
                    className="min-h-[260px] font-mono text-xs"
                  />
                </div>
              )}

              <Button onClick={handleAnalyze} disabled={loading || !canAnalyze} className="h-14 w-full bg-emerald-500 text-base text-white hover:bg-emerald-600">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                Analizar correos
              </Button>

              {!canAnalyze && (
                <div className="text-center text-xs text-muted-foreground">
                  {provider === "gmail" ? "Conecta Gmail antes de analizar." : "Carga al menos un mensaje valido para continuar."}
                </div>
              )}

              {error && (
                <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {result && (
          <div className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {[
                { label: "Empresas", value: result.summary.unique_companies, icon: Building2 },
                { label: "Nombres", value: namesFound.length, icon: UserRound },
                { label: "Con datos", value: sendersWithPersonalData.length, icon: ShieldAlert },
                { label: "Top empresa", value: rankedSenders[0]?.company_name ?? "—", icon: Mail },
              ].map((item) => (
                <Card key={item.label} className="border-emerald-500/20 bg-gradient-to-br from-emerald-400/12 via-background to-emerald-500/[0.03] shadow-[0_18px_50px_-35px_rgba(16,185,129,0.5)]">
                  <CardContent className="p-6">
                    <item.icon className="mb-4 h-5 w-5 text-emerald-500" />
                    <div className="text-3xl font-semibold sm:text-4xl">{item.value}</div>
                    <div className="mt-2 text-sm text-muted-foreground">{item.label}</div>
                  </CardContent>
                </Card>
              ))}
            </div>

            <Card className="border-emerald-500/20 bg-gradient-to-br from-emerald-400/10 via-background to-emerald-500/[0.04] shadow-[0_24px_70px_-40px_rgba(16,185,129,0.55)]">
              <CardHeader className="flex flex-col gap-3 pb-3 md:flex-row md:items-end md:justify-between">
                <div>
                  <CardTitle className="text-xl">Ranking de empresas</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Ordenadas por la fuerza de las señales personales encontradas en tus correos.
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {gmailAuth
                      ? `Los informes de baja se enviarán a: ${gmailAuth.email_address ?? "tu Gmail"}`
                      : bajaSmtpOk === false
                        ? "Conecta tu Gmail para poder enviar informes de baja"
                        : bajaDestination
                          ? `Los informes de baja se enviarán a: ${bajaDestination}`
                          : "Conecta tu Gmail para poder enviar informes de baja"}
                  </p>
                </div>
                {rankedSenders[0] && (
                  <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-300">Mayor exposición</div>
                    <div className="mt-1 text-sm font-semibold">{rankedSenders[0].company_name}</div>
                  </div>
                )}
              </CardHeader>
              <CardContent className="p-3 sm:p-5">
                <Accordion type="multiple" className="w-full">
                  {rankedSenders.map((sender, index) => (
                    <AccordionItem
                      key={`${sender.company_name}-${sender.primary_domain}`}
                      value={`${sender.company_name}-${sender.primary_domain}`}
                      className="mb-4 overflow-hidden rounded-3xl border border-emerald-500/15 bg-background/80 px-4 shadow-[0_16px_45px_-38px_rgba(16,185,129,0.7)] backdrop-blur-sm"
                    >
                      <AccordionTrigger className="py-5 hover:no-underline">
                        <div className="flex min-w-0 flex-1 items-center justify-between gap-4 pr-4 text-left">
                          <div className="flex min-w-0 items-center gap-4">
                            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-sm font-semibold text-white shadow-md">
                              #{index + 1}
                            </div>
                            <div className="min-w-0">
                              <div className="truncate text-lg font-semibold sm:text-xl">{sender.company_name}</div>
                              <div className="truncate text-sm text-muted-foreground">
                                {sender.primary_domain} · {sender.sender_type} · {sender.is_chilean ? "Chile" : sender.country}
                              </div>
                            </div>
                          </div>
                          <div className="flex shrink-0 flex-wrap gap-2">
                            <Badge variant={sender.is_chilean ? "default" : "outline"} className={sender.is_chilean ? "bg-emerald-500 text-white hover:bg-emerald-500/90" : ""}>
                              {sender.is_chilean ? "Empresa chilena" : "Empresa no chilena"}
                            </Badge>
                            <Badge variant={riskVariant(sender.risk.level)}>{sender.risk.level}</Badge>
                            <Badge variant="secondary" className="bg-emerald-500 text-white hover:bg-emerald-500/90">conf. {confidenceLabel(sender.personal_data_confidence)}</Badge>
                            <Badge variant="outline">{sender.evidence?.message_count ?? 0} correos</Badge>
                            {sender.matched_targets && sender.matched_targets.length > 0 && (
                              <Badge className="bg-amber-500 text-white hover:bg-amber-500/90">
                                ✓ Coincide con objetivo
                              </Badge>
                            )}
                          </div>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent>
                        <div className="mb-4 flex flex-wrap items-center justify-end gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            className="border-emerald-500/30 text-emerald-700 hover:bg-emerald-500/10 dark:text-emerald-300"
                            disabled={sendingBaja === sender.company_name || (!gmailAuth && !bajaSmtpOk)}
                            title={!gmailAuth && !bajaSmtpOk ? "Conecta tu Gmail primero" : undefined}
                            onClick={() => openUnsubscribeDraft(sender)}
                          >
                            {sendingBaja === sender.company_name
                              ? <Loader2 className="h-4 w-4 animate-spin" />
                              : <Mail className="h-4 w-4" />}
                            {sendingBaja === sender.company_name ? "Enviando..." : "Pedir baja"}
                          </Button>
                        </div>

                        <div className="rounded-3xl border border-emerald-500/10 bg-gradient-to-br from-emerald-500/[0.07] via-background to-emerald-500/[0.03] p-5 sm:p-6">
                          <div className="grid gap-5 pt-1 xl:grid-cols-[180px_minmax(0,1.7fr)_minmax(0,1fr)_minmax(0,1fr)]">
                            <div className="space-y-2">
                              <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Ranking</div>
                              <div className="text-4xl font-semibold text-emerald-500">#{index + 1}</div>
                              <div className="text-xs text-muted-foreground">Ordenado por confianza y consistencia.</div>
                            </div>
                            <div className="space-y-2">
                              <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Direcciones</div>
                              <div className="flex flex-wrap gap-2">
                                {uniqueAddresses(sender).length > 0 ? (
                                  uniqueAddresses(sender).slice(0, 10).map((address) => (
                                    <Badge key={address} variant="outline" className="border-emerald-500/25 bg-background/80 font-mono text-xs">
                                      {address}
                                    </Badge>
                                  ))
                                ) : (
                                  <span className="text-xs text-muted-foreground">Sin direcciones detectadas.</span>
                                )}
                              </div>
                            </div>

                            <div className="space-y-2">
                              <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Nombre detectado en esta empresa</div>
                              {sender.primary_personal_name ? (
                                <div className="space-y-3">
                                  <div className="flex flex-wrap gap-2">
                                    <Badge variant="secondary" className="bg-emerald-500 px-3 py-1 text-xs text-white hover:bg-emerald-500/90">
                                      {sender.primary_personal_name}
                                    </Badge>
                                    {probableName && areNamesRelated(sender.primary_personal_name, probableName) && (
                                      <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/5 text-xs text-emerald-700 dark:text-emerald-300">
                                        Variante de {probableName}
                                      </Badge>
                                    )}
                                  </div>

                                  <div className="space-y-2">
                                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Variantes encontradas</div>
                                    <div className="flex flex-wrap gap-2">
                                      {matchedNameVariants(sender, probableName).map((name) => (
                                        <Badge key={name} variant="outline" className="border-emerald-500/25 bg-background/80 text-xs">
                                          {name}
                                        </Badge>
                                      ))}
                                    </div>
                                  </div>

                                  <div className="rounded-2xl border border-emerald-500/12 bg-background/80 p-3 text-xs text-muted-foreground">
                                    El nombre se detecto dentro del contenido de correos analizados de esta empresa. Si aparece una variante parecida al nombre global, se considera que esta empresa igualmente tiene tu nombre.
                                  </div>
                                </div>
                              ) : (
                                <span className="text-xs text-muted-foreground">Sin nombre confirmado.</span>
                              )}
                            </div>

                            <div className="space-y-2">
                              <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Datos personales</div>
                              <div className="flex flex-wrap gap-2">
                                {(sender.personal_data_types ?? []).length > 0 ? (
                                  (sender.personal_data_types ?? []).map((item) => (
                                    <Badge key={item} variant="secondary" className="bg-emerald-500/15 px-3 py-1 text-xs text-emerald-700 dark:text-emerald-300">
                                      {personalDataLabel(item)}
                                    </Badge>
                                  ))
                                ) : (
                                  <span className="text-xs text-muted-foreground">No se detectaron datos personales claros.</span>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>

                        {((sender.personal_addresses ?? []).length > 0 || (sender.personal_ruts ?? []).length > 0 || (sender.personal_phones ?? []).length > 0 || (sender.personal_plates ?? []).length > 0) && (
                          <div className="mt-4 grid gap-5 lg:grid-cols-2 xl:grid-cols-4">
                            {(sender.personal_addresses ?? []).length > 0 && (
                              <div className="rounded-2xl border border-emerald-500/12 bg-background/80 p-4">
                                <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Direccion personal</div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {sender.primary_personal_address && (
                                    <Badge variant="outline" className="border-emerald-500/30 text-xs">
                                      {sender.primary_personal_address}
                                    </Badge>
                                  )}
                                </div>
                                {(sender.personal_address_evidence ?? []).length > 0 && (
                                  <div className="mt-3 space-y-2">
                                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Donde se encontro</div>
                                    <div className="space-y-2">
                                      {(sender.personal_address_evidence ?? []).slice(0, 3).map((snippet) => (
                                        <div key={snippet} className="rounded-xl border border-emerald-500/12 bg-emerald-500/[0.04] px-3 py-2 text-xs text-muted-foreground">
                                          {snippet}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}

                            {(sender.personal_ruts ?? []).length > 0 && (
                              <div className="rounded-2xl border border-emerald-500/12 bg-background/80 p-4">
                                <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">RUT más probable</div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {sender.primary_personal_rut && (
                                    <Badge variant="outline" className="border-emerald-500/30 font-mono text-xs">
                                      {sender.primary_personal_rut}
                                    </Badge>
                                  )}
                                </div>
                              </div>
                            )}

                            {(sender.personal_phones ?? []).length > 0 && (
                              <div className="rounded-2xl border border-emerald-500/12 bg-background/80 p-4">
                                <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Telefono más probable</div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {sender.primary_personal_phone && (
                                    <Badge variant="outline" className="border-emerald-500/30 font-mono text-xs">
                                      {sender.primary_personal_phone}
                                    </Badge>
                                  )}
                                </div>
                                {(sender.personal_phone_evidence ?? []).length > 0 && (
                                  <div className="mt-3 space-y-2">
                                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Donde se encontro</div>
                                    <div className="space-y-2">
                                      {(sender.personal_phone_evidence ?? []).slice(0, 3).map((snippet) => (
                                        <div key={snippet} className="rounded-xl border border-emerald-500/12 bg-emerald-500/[0.04] px-3 py-2 text-xs text-muted-foreground">
                                          {snippet}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}

                            {(sender.personal_plates ?? []).length > 0 && (
                              <div className="rounded-2xl border border-emerald-500/12 bg-background/80 p-4">
                                <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Patente más probable</div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {sender.primary_personal_plate && (
                                    <Badge variant="outline" className="border-emerald-500/30 font-mono text-xs">
                                      {sender.primary_personal_plate}
                                    </Badge>
                                  )}
                                </div>
                                {(sender.personal_plate_evidence ?? []).length > 0 && (
                                  <div className="mt-3 space-y-2">
                                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Donde se encontro</div>
                                    <div className="space-y-2">
                                      {(sender.personal_plate_evidence ?? []).slice(0, 3).map((snippet) => (
                                        <div key={snippet} className="rounded-xl border border-emerald-500/12 bg-emerald-500/[0.04] px-3 py-2 text-xs text-muted-foreground">
                                          {snippet}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )}

                        {sender.risk.reasons.length > 0 && (
                          <div className="mt-4 rounded-xl border border-emerald-500/10 bg-background/80 px-4 py-3 text-sm text-muted-foreground">
                            {sender.risk.reasons[0]}
                          </div>
                        )}

                        {((sender.evidence.header_ips ?? []).length > 0 || (sender.evidence.header_ip_chile_matches ?? []).length > 0) && (
                          <div className="mt-4 rounded-2xl border border-emerald-500/12 bg-background/80 p-4">
                            <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">IPs detectadas en cabeceras</div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {(sender.evidence.header_ips ?? []).slice(0, 8).map((ip) => (
                                <Badge key={ip} variant="outline" className="border-emerald-500/25 font-mono text-xs">
                                  {ip}
                                </Badge>
                              ))}
                            </div>
                            {(sender.evidence.header_ip_chile_matches ?? []).length > 0 && (
                              <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300">
                                Se detectaron IPs de cabecera asociadas a Chile.
                              </div>
                            )}
                          </div>
                        )}

                        {(sender.evidence.sample_subjects ?? []).length > 0 && (
                          <div className="mt-4 rounded-2xl border border-emerald-500/12 bg-background/80 p-4">
                            <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Correos donde se encontro la señal</div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {(sender.evidence.sample_subjects ?? []).slice(0, 3).map((subject) => (
                                <Badge key={subject} variant="outline" className="max-w-full border-emerald-500/20 bg-background/90 text-xs">
                                  {subject}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}

                        {(sender.evidence.attachment_filenames ?? []).length > 0 && (
                          <div className="mt-4 rounded-2xl border border-emerald-500/12 bg-background/80 p-4">
                            <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Adjuntos revisados</div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {(sender.evidence.attachment_filenames ?? []).slice(0, 6).map((filename) => (
                                <Badge key={filename} variant="outline" className="max-w-full border-emerald-500/20 bg-background/90 text-xs">
                                  {filename}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                      </AccordionContent>
                    </AccordionItem>
                  ))}
                </Accordion>
                {draftError && (
                  <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {draftError}
                  </div>
                )}
                {draftSuccess && (
                  <div className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
                    {draftSuccess}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border-emerald-500/20 bg-gradient-to-br from-emerald-400/15 via-background to-emerald-500/[0.04] shadow-[0_24px_70px_-42px_rgba(16,185,129,0.6)]">
              <CardHeader className="pb-3">
                <CardTitle className="text-xl">Resumen Final</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {sendersWithPersonalData.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No se confirmo informacion personal clara en las empresas analizadas.</p>
                ) : (
                  <div className="space-y-5 rounded-[28px] border border-emerald-500/20 bg-gradient-to-br from-emerald-400/15 via-background to-emerald-500/[0.05] p-6 sm:p-7">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="text-base font-semibold text-emerald-700 dark:text-emerald-300">Señales personales más probables</div>
                        <div className="mt-1 text-sm text-muted-foreground">
                          Cruce entre empresas y repetición de hallazgos detectados en correos.
                        </div>
                      </div>
                      <Badge variant="secondary" className="w-fit bg-emerald-500 px-4 py-1.5 text-white hover:bg-emerald-500/90">
                        Confianza general {confidenceLabel(summarySignals.avgConfidence)} ({Math.round(summarySignals.avgConfidence * 100)}%)
                      </Badge>
                    </div>

                    <div className="grid gap-4 xl:grid-cols-5">
                      <button
                        type="button"
                        onClick={() => setSelectedSummarySignal("name")}
                        className={`rounded-3xl border bg-background/90 p-6 text-left shadow-sm transition ${selectedSummarySignal === "name" ? "border-emerald-500/40 ring-2 ring-emerald-500/20" : "border-emerald-500/15"}`}
                      >
                        <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Nombre más probable</div>
                        <div className="mt-3 text-2xl font-semibold">{summarySignals.name.value ?? "Sin confirmar"}</div>
                        <div className="mt-2 text-sm text-muted-foreground">
                          Detectado en {summarySignals.name.count} coincidencia{summarySignals.name.count === 1 ? "" : "s"}.
                        </div>
                      </button>

                      <button
                        type="button"
                        onClick={() => setSelectedSummarySignal("address")}
                        className={`rounded-3xl border bg-background/90 p-6 text-left shadow-sm transition ${selectedSummarySignal === "address" ? "border-emerald-500/40 ring-2 ring-emerald-500/20" : "border-emerald-500/15"}`}
                      >
                        <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Direccion más probable</div>
                        <div className="mt-3 text-2xl font-semibold">{summarySignals.address.value ?? "Sin confirmar"}</div>
                        <div className="mt-2 text-sm text-muted-foreground">
                          {summarySignals.address.value ? `Detectada en ${summarySignals.address.count} coincidencia${summarySignals.address.count === 1 ? "" : "s"}.` : "No hubo una direccion validada suficiente."}
                        </div>
                      </button>

                      <button
                        type="button"
                        onClick={() => setSelectedSummarySignal("rut")}
                        className={`rounded-3xl border bg-background/90 p-6 text-left shadow-sm transition ${selectedSummarySignal === "rut" ? "border-emerald-500/40 ring-2 ring-emerald-500/20" : "border-emerald-500/15"}`}
                      >
                        <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">RUT más probable</div>
                        <div className="mt-3 text-2xl font-semibold">{summarySignals.rut.value ?? "Sin confirmar"}</div>
                        <div className="mt-2 text-sm text-muted-foreground">
                          {summarySignals.rut.value ? `Detectado en ${summarySignals.rut.count} coincidencia${summarySignals.rut.count === 1 ? "" : "s"}.` : "No hubo un RUT validado suficiente."}
                        </div>
                      </button>

                      <button
                        type="button"
                        onClick={() => setSelectedSummarySignal("phone")}
                        className={`rounded-3xl border bg-background/90 p-6 text-left shadow-sm transition ${selectedSummarySignal === "phone" ? "border-emerald-500/40 ring-2 ring-emerald-500/20" : "border-emerald-500/15"}`}
                      >
                        <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Telefono más probable</div>
                        <div className="mt-3 text-2xl font-semibold">{summarySignals.phone.value ?? "Sin confirmar"}</div>
                        <div className="mt-2 text-sm text-muted-foreground">
                          {summarySignals.phone.value ? `Detectado en ${summarySignals.phone.count} coincidencia${summarySignals.phone.count === 1 ? "" : "s"}.` : "No hubo un telefono validado suficiente."}
                        </div>
                      </button>

                      <button
                        type="button"
                        onClick={() => setSelectedSummarySignal("plate")}
                        className={`rounded-3xl border bg-background/90 p-6 text-left shadow-sm transition ${selectedSummarySignal === "plate" ? "border-emerald-500/40 ring-2 ring-emerald-500/20" : "border-emerald-500/15"}`}
                      >
                        <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Patente más probable</div>
                        <div className="mt-3 text-2xl font-semibold">{summarySignals.plate.value ?? "Sin confirmar"}</div>
                        <div className="mt-2 text-sm text-muted-foreground">
                          {summarySignals.plate.value ? `Detectada en ${summarySignals.plate.count} coincidencia${summarySignals.plate.count === 1 ? "" : "s"}.` : "No hubo una patente con contexto suficiente."}
                        </div>
                      </button>
                    </div>

                    <div className="rounded-3xl border border-emerald-500/15 bg-background/90 p-6 shadow-sm">
                      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                        <div>
                          <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Dónde se encontró</div>
                          <div className="mt-1 text-lg font-semibold">
                            {selectedSummarySignal === "name" && (summarySignals.name.value ?? "Sin confirmar")}
                            {selectedSummarySignal === "address" && (summarySignals.address.value ?? "Sin confirmar")}
                            {selectedSummarySignal === "rut" && (summarySignals.rut.value ?? "Sin confirmar")}
                            {selectedSummarySignal === "phone" && (summarySignals.phone.value ?? "Sin confirmar")}
                            {selectedSummarySignal === "plate" && (summarySignals.plate.value ?? "Sin confirmar")}
                          </div>
                        </div>
                        <Badge variant="outline" className="w-fit border-emerald-500/25">
                          {selectedSummarySignal === "name" ? "Nombre" : selectedSummarySignal === "address" ? "Direccion" : selectedSummarySignal === "rut" ? "RUT" : selectedSummarySignal === "phone" ? "Telefono" : "Patente"}
                        </Badge>
                      </div>

                      <div className="mt-4 space-y-3">
                        {(selectedSummarySignal === "name" ? summaryEvidence.name : selectedSummarySignal === "address" ? summaryEvidence.address : selectedSummarySignal === "rut" ? summaryEvidence.rut : selectedSummarySignal === "phone" ? summaryEvidence.phone : summaryEvidence.plate).length > 0 ? (
                          (selectedSummarySignal === "name" ? summaryEvidence.name : selectedSummarySignal === "address" ? summaryEvidence.address : selectedSummarySignal === "rut" ? summaryEvidence.rut : selectedSummarySignal === "phone" ? summaryEvidence.phone : summaryEvidence.plate).map((entry) => (
                            <div key={`${selectedSummarySignal}-${entry.company}-${entry.domain}`} className="rounded-2xl border border-emerald-500/12 bg-emerald-500/[0.04] p-4">
                              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                                <div>
                                  <div className="font-medium">{entry.company}</div>
                                  <div className="text-xs text-muted-foreground">{entry.domain}</div>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                  {entry.variants.map((variant) => (
                                    <Badge key={variant} variant="secondary" className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                                      {variant}
                                    </Badge>
                                  ))}
                                </div>
                              </div>

                              <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                                {entry.evidence.map((item) => (
                                  <div key={item}>{item}</div>
                                ))}
                              </div>

                              {entry.locations.length > 0 && (
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {entry.locations.map((location) => (
                                    <Badge key={location} variant="outline" className="border-emerald-500/20 bg-background/90 text-xs">
                                      {location}
                                    </Badge>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))
                        ) : (
                          <div className="rounded-2xl border border-emerald-500/12 bg-emerald-500/[0.04] p-4 text-sm text-muted-foreground">
                            No hay evidencia suficiente para ese dato en el resumen actual.
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-3xl border border-emerald-500/15 bg-background/90 p-6 shadow-sm">
                      <div className="text-base">
                        Las empresas parecen tener información tuya en <span className="font-medium">{sendersWithPersonalData.length}</span> caso{sendersWithPersonalData.length === 1 ? "" : "s"}.
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground">
                        Esto resume lo más consistente entre nombre, RUT y patente; no muestra señales débiles como si fueran confirmaciones.
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <div className="flex flex-wrap justify-end gap-3">
              <Button
                variant="outline"
                onClick={openWebExposureView}
                className="h-12 border-emerald-500/35 bg-background text-emerald-700 hover:bg-emerald-500/10 dark:text-emerald-300"
                disabled={!summarySignals.name.value && namesFound.length === 0}
              >
                <Telescope className="h-4 w-4" />
                Buscar datos en la web
              </Button>
              <Button onClick={openHeaderAnalysisView} className="h-12 bg-emerald-500 text-white hover:bg-emerald-600">
                <Link2 className="h-4 w-4" />
                Ver cabeceras
              </Button>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
