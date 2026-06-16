import { useEffect, useState } from "react";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  Building2, CheckCircle2, Chrome, CircleDashed, Globe, KeyRound, Loader2, Mail,
  ShieldAlert, ShieldCheck, ShieldOff, LogIn, ShoppingCart, UserRound, AlertTriangle,
} from "lucide-react";

const BROWSER_OPTIONS = [
  { value: "chrome",        label: "Google Chrome"  },
  { value: "safari",        label: "Safari"         },
  { value: "brave",         label: "Brave"          },
  { value: "edge",          label: "Microsoft Edge" },
  { value: "firefox",       label: "Firefox"        },
  { value: "chrome-canary", label: "Chrome Canary"  },
] as const;

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface ConfirmedDatum {
  tipo: string;
  tipo_key: string;
  valores: string[];
  evidencia: string;
}

interface BrowserCompany {
  domain: string;
  company_name: string;
  sender_type: string;
  country: string;
  is_chilean: boolean;
  visit_count: number;
  last_visit_iso: string | null;
  login_detected: boolean;
  signup_detected: boolean;
  checkout_detected: boolean;
  profile_detected: boolean;
  risk_level: "high" | "medium" | "low";
  confirmed_data: ConfirmedDatum[];   // Login Data: email exacto por dominio
  autofill_hints: ConfirmedDatum[];   // Autofill global: probablemente enviado aquí
  probable_data_types: string[];      // Solo inferencia
  tags: string[];
  known: boolean;
  primary_domain: string;
  autofill_available: boolean;
  login_data_available: boolean;
}

interface AutofillSummary {
  disponible: boolean;
  emails: string[];
  nombres: string[];
  telefonos: string[];
  direcciones: string[];
  ruts: string[];
  patentes: string[];
  usernames: string[];
}

interface BrowserHistoryResponse {
  total_companies: number;
  login_count: number;
  chilean_count: number;
  high_risk_count: number;
  data_broker_count: number;
  confirmed_count: number;
  companies: BrowserCompany[];
  autofill_summary: AutofillSummary & { login_data_domains: string[] };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const RISK_LABEL: Record<string, string> = {
  high: "Alto", medium: "Medio", low: "Bajo",
};

const TYPE_LABEL: Record<string, string> = {
  retail: "Retail", banca: "Banca", fintech: "Fintech", salud: "Salud",
  telecomunicaciones: "Telecomunicaciones", data_broker: "Data Broker",
  gobierno: "Gobierno", delivery: "Delivery", transporte: "Transporte",
  social: "Red Social", tech: "Tecnología", afp: "AFP",
  educacion: "Educación", marketplace: "Marketplace", desconocido: "Desconocido",
};

function riskVariant(level: string): "destructive" | "default" | "secondary" | "outline" {
  if (level === "high")   return "destructive";
  if (level === "medium") return "default";
  return "secondary";
}

function riskIcon(level: string) {
  if (level === "high")   return <ShieldOff  className="h-4 w-4 text-destructive" />;
  if (level === "medium") return <ShieldAlert className="h-4 w-4 text-amber-500" />;
  return                         <ShieldCheck className="h-4 w-4 text-emerald-500" />;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("es-CL", { year: "numeric", month: "short", day: "numeric" }); }
  catch { return iso; }
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function BrowserHistory() {
  const [browser,     setBrowser]     = useState("chrome");
  const [loading,     setLoading]     = useState(false);
  const [result,      setResult]      = useState<BrowserHistoryResponse | null>(null);
  const [error,       setError]       = useState<string | null>(null);
  const [sendingBaja, setSendingBaja] = useState<string | null>(null);
  const [bajaOk,      setBajaOk]      = useState<string | null>(null);

  // Restaurar el último resultado guardado (p. ej. analizado desde el Inicio).
  useEffect(() => {
    try {
      const raw = localStorage.getItem("browser_history_result");
      if (raw) setResult(JSON.parse(raw) as BrowserHistoryResponse);
    } catch { /* ignore */ }
  }, []);

  // ── Análisis ────────────────────────────────────────────────────────────────
  async function handleAnalyze() {
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await fetch(`/api/local/browser-history?browser=${browser}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(body.detail ?? `Error ${res.status}`);
      }
      const data = await res.json();
      setResult(data);
      try { localStorage.setItem("browser_history_result", JSON.stringify(data)); } catch {}
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }

  // ── Pedir baja ──────────────────────────────────────────────────────────────
  async function handleBaja(company: BrowserCompany) {
    setSendingBaja(company.domain); setBajaOk(null);
    const senderPayload = {
      company_name: company.company_name, normalized_domain: company.domain,
      primary_domain: company.primary_domain, sender_type: company.sender_type,
      country: company.country, is_chilean: company.is_chilean,
      confidence: company.known ? 0.9 : 0.5,
      personal_data_confidence: company.confirmed_data.length > 0 ? 0.85 : 0.4,
      personal_data_types: [
        ...company.confirmed_data.map(d => d.tipo),
        ...company.probable_data_types,
      ],
      personal_names: [], personal_addresses: [], personal_address_evidence: [],
      personal_ruts: [], personal_phones: [], personal_phone_evidence: [],
      personal_plates: [], personal_plate_evidence: [],
      subdomains: [], reply_to_domains: [], return_path_domains: [], auth_domains: [],
      tags: company.tags, matched_targets: [], whois: null,
      evidence: {
        message_count: 0, spam_count: 0, trash_count: 0,
        first_seen: null, last_seen: company.last_visit_iso,
        sample_subjects: [], attachment_filenames: [], from_addresses: [],
        reply_to_addresses: [], return_path_addresses: [], auth_domains: [],
        header_ips: [], header_ip_countries: [], header_ip_chile_matches: [],
        header_ip_details: [], subdomains: [],
      },
      risk: {
        level: company.risk_level, reasons: company.tags,
        suspected_newsletter: false, suspected_data_broker: company.sender_type === "data_broker",
        suspicious_infrastructure: false, aggressive_marketing: false,
      },
    };
    try {
      const res = await fetch("/api/identification/send-baja-report", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ holder_email: "", sender: senderPayload }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(body.detail ?? `Error ${res.status}`);
      }
      setBajaOk(company.domain);
    } catch (err) {
      alert(`No se pudo enviar: ${err instanceof Error ? err.message : err}`);
    } finally {
      setSendingBaja(null);
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <Layout>
      <div className="mx-auto max-w-5xl space-y-6 p-4 sm:p-6">

        {/* Encabezado */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 shadow-md">
            <Chrome className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Historial de navegación</h1>
            <p className="text-sm text-muted-foreground">
              Identifica qué empresas tienen tus datos — confirmados por tu autofill de Chrome
            </p>
          </div>
        </div>

        {/* Panel de inicio */}
        <Card className="border-emerald-500/20 bg-gradient-to-br from-emerald-400/10 via-background to-emerald-500/[0.04] shadow-[0_24px_70px_-40px_rgba(16,185,129,0.45)]">
          <CardContent className="space-y-4 p-6">
            <div className="flex items-center gap-3">
              <Label htmlFor="browser-select" className="shrink-0 text-sm">Navegador</Label>
              <Select value={browser} onValueChange={setBrowser}>
                <SelectTrigger id="browser-select" className="w-52">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BROWSER_OPTIONS.map(opt => (
                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="rounded-2xl border border-emerald-500/15 bg-emerald-500/5 px-4 py-3 text-sm text-muted-foreground">
              <strong className="text-foreground">¿Qué hace esto?</strong>{" "}
              Lee el historial del navegador y el autofill guardado en tu Mac.
              Detecta en qué sitios hiciste login o compraste y muestra los datos reales
              (email, RUT, dirección, patente) que probablemente ingresaste en cada empresa.
              <span className="mt-1 block text-xs">Todo el análisis ocurre localmente — ningún dato sale de tu equipo.</span>
            </div>

            <Button
              onClick={handleAnalyze}
              disabled={loading}
              className="h-14 w-full bg-emerald-500 text-base text-white hover:bg-emerald-600"
            >
              {loading
                ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Analizando…</>
                : <><Chrome className="mr-2 h-4 w-4" />Analizar historial de Chrome</>}
            </Button>

            {error && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}
          </CardContent>
        </Card>

        {result && (
          <div className="space-y-5">

            {/* ── Tarjetas de resumen ── */}
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {[
                { label: "Empresas",          value: result.total_companies,  icon: Building2    },
                { label: "Con datos confirmados", value: result.confirmed_count, icon: CheckCircle2 },
                { label: "Con login",          value: result.login_count,      icon: LogIn        },
                { label: "Alto riesgo",        value: result.high_risk_count,  icon: ShieldAlert  },
              ].map(item => (
                <Card key={item.label} className="border-emerald-500/20 bg-gradient-to-br from-emerald-400/12 via-background to-emerald-500/[0.03] shadow-[0_18px_50px_-35px_rgba(16,185,129,0.5)]">
                  <CardContent className="p-6">
                    <item.icon className="mb-4 h-5 w-5 text-emerald-500" />
                    <div className="text-3xl font-semibold sm:text-4xl">{item.value}</div>
                    <div className="mt-2 text-sm text-muted-foreground">{item.label}</div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* ── Resumen de autofill del usuario ── */}
            {result.autofill_summary.disponible && (
              <Card className="border-blue-500/20 bg-gradient-to-br from-blue-400/8 via-background to-blue-500/[0.03]">
                <CardHeader className="pb-2 pt-4">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <CheckCircle2 className="h-4 w-4 text-blue-500" />
                    Datos encontrados en tu autofill de Chrome
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Estos son los datos que Chrome tiene guardados de formularios que llenaste.
                    Se usan para confirmar qué recibió cada empresa.
                  </p>
                </CardHeader>
                <CardContent className="p-4 pt-0">
                  <div className="flex flex-wrap gap-3">
                    {[
                      { label: "Emails",      values: result.autofill_summary.emails      },
                      { label: "Nombres",     values: result.autofill_summary.nombres     },
                      { label: "RUTs",        values: result.autofill_summary.ruts        },
                      { label: "Teléfonos",   values: result.autofill_summary.telefonos   },
                      { label: "Direcciones", values: result.autofill_summary.direcciones },
                      { label: "Patentes",    values: result.autofill_summary.patentes    },
                    ].filter(g => g.values.length > 0).map(group => (
                      <div key={group.label} className="rounded-xl border border-blue-500/15 bg-blue-500/5 px-3 py-2 min-w-0">
                        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400">
                          {group.label}
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {group.values.slice(0, 3).map(v => (
                            <span key={v} className="rounded-md bg-blue-500/10 px-2 py-0.5 font-mono text-xs text-blue-800 dark:text-blue-200">
                              {v}
                            </span>
                          ))}
                          {group.values.length > 3 && (
                            <span className="text-xs text-muted-foreground">+{group.values.length - 3} más</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* ── Avisos ── */}
            {result.data_broker_count > 0 && (
              <div className="flex items-start gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/8 px-4 py-3 text-sm">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                <span>
                  Se detectaron <strong>{result.data_broker_count} data broker(s)</strong> en tu historial.
                  Estas empresas comercializan datos personales. Se recomienda pedir baja.
                </span>
              </div>
            )}

            {/* ── Acordeón de empresas ── */}
            <Card className="border-emerald-500/20 bg-gradient-to-br from-emerald-400/10 via-background to-emerald-500/[0.04] shadow-[0_24px_70px_-40px_rgba(16,185,129,0.55)]">
              <CardHeader className="flex flex-col gap-3 pb-3 md:flex-row md:items-end md:justify-between">
                <div>
                  <CardTitle className="text-xl">Empresas detectadas</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Ordenadas por riesgo. <strong className="text-foreground">✓ Confirmado</strong> = dato real de tu autofill.
                    <span className="text-muted-foreground"> ○ Probable</span> = inferido por actividad.
                  </p>
                </div>
                {result.companies[0] && (
                  <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-300">Mayor riesgo</div>
                    <div className="mt-1 text-sm font-semibold">{result.companies[0].company_name}</div>
                  </div>
                )}
              </CardHeader>

              <CardContent className="p-3 sm:p-5">
                <Accordion type="multiple" className="w-full">
                  {result.companies.map((company, index) => (
                    <AccordionItem
                      key={company.domain}
                      value={company.domain}
                      className="mb-4 overflow-hidden rounded-3xl border border-emerald-500/15 bg-background/80 px-4 shadow-[0_16px_45px_-38px_rgba(16,185,129,0.7)] backdrop-blur-sm"
                    >
                      {/* Trigger */}
                      <AccordionTrigger className="py-5 hover:no-underline">
                        <div className="flex min-w-0 flex-1 items-center justify-between gap-4 pr-4 text-left">
                          <div className="flex min-w-0 items-center gap-4">
                            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-sm font-semibold text-white shadow-md">
                              #{index + 1}
                            </div>
                            <div className="min-w-0">
                              <div className="truncate text-lg font-semibold sm:text-xl">
                                {company.company_name}
                              </div>
                              <div className="truncate text-sm text-muted-foreground">
                                {company.domain} · {TYPE_LABEL[company.sender_type] ?? company.sender_type} · {company.country}
                              </div>
                            </div>
                          </div>
                          <div className="flex shrink-0 flex-wrap gap-2">
                            {company.is_chilean && (
                              <Badge className="bg-emerald-500 text-white hover:bg-emerald-500/90">Empresa chilena</Badge>
                            )}
                            <Badge variant={riskVariant(company.risk_level)}>
                              {RISK_LABEL[company.risk_level]}
                            </Badge>
                            {company.confirmed_data.length > 0 && (
                              <Badge className="bg-emerald-600 text-white hover:bg-emerald-600/90">
                                <KeyRound className="mr-1 h-3 w-3" />login confirmado
                              </Badge>
                            )}
                            {company.autofill_hints.length > 0 && company.confirmed_data.length === 0 && (
                              <Badge className="bg-blue-500 text-white hover:bg-blue-500/90">
                                <CheckCircle2 className="mr-1 h-3 w-3" />
                                {company.autofill_hints.length} en autofill
                              </Badge>
                            )}
                            {company.login_detected && (
                              <Badge variant="outline" className="border-blue-500/40 text-blue-600 dark:text-blue-400">
                                <LogIn className="mr-1 h-3 w-3" />Login
                              </Badge>
                            )}
                            {company.checkout_detected && (
                              <Badge variant="outline" className="border-purple-500/40 text-purple-600 dark:text-purple-400">
                                <ShoppingCart className="mr-1 h-3 w-3" />Compra
                              </Badge>
                            )}
                            <Badge variant="outline">{company.visit_count} visitas</Badge>
                          </div>
                        </div>
                      </AccordionTrigger>

                      {/* Contenido */}
                      <AccordionContent>
                        {/* Botón baja */}
                        <div className="mb-4 flex flex-wrap items-center justify-end gap-2">
                          {bajaOk === company.domain && (
                            <span className="text-xs text-emerald-600 dark:text-emerald-400">✓ Solicitud enviada</span>
                          )}
                          <Button
                            type="button"
                            variant="outline"
                            className="border-emerald-500/30 text-emerald-700 hover:bg-emerald-500/10 dark:text-emerald-300"
                            disabled={sendingBaja === company.domain}
                            onClick={() => handleBaja(company)}
                          >
                            {sendingBaja === company.domain
                              ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              : <Mail className="mr-2 h-4 w-4" />}
                            {sendingBaja === company.domain ? "Enviando…" : "Pedir baja"}
                          </Button>
                        </div>

                        <div className="space-y-4 rounded-3xl border border-emerald-500/10 bg-gradient-to-br from-emerald-500/[0.07] via-background to-emerald-500/[0.03] p-5 sm:p-6">

                          {/* ── Nivel 1: Confirmado por Login Data (per-domain) ── */}
                          {company.confirmed_data.length > 0 && (
                            <div>
                              <div className="mb-2 flex items-center gap-2">
                                <KeyRound className="h-4 w-4 text-emerald-600" />
                                <span className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-400">
                                  Confirmado — contraseña guardada en Chrome para este sitio
                                </span>
                              </div>
                              <p className="mb-3 text-[11px] text-muted-foreground">
                                Chrome guarda esto cuando haces login y aceptas guardar la contraseña.
                                El email es exactamente el que ingresaste en este dominio.
                              </p>
                              <div className="space-y-2">
                                {company.confirmed_data.map(datum => (
                                  <div key={datum.tipo_key}
                                    className="flex flex-wrap items-start gap-3 rounded-2xl border border-emerald-500/25 bg-emerald-500/8 px-4 py-3"
                                  >
                                    <div className="w-28 shrink-0">
                                      <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">{datum.tipo}</span>
                                      <div className="mt-0.5 text-[10px] text-muted-foreground">{datum.evidencia}</div>
                                    </div>
                                    <div className="flex flex-wrap gap-1.5">
                                      {datum.valores.map(v => (
                                        <span key={v} className="rounded-lg border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-1 font-mono text-xs font-semibold text-emerald-900 dark:text-emerald-100">
                                          {v}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* ── Nivel 2: Probable por autofill global ── */}
                          {company.autofill_hints.length > 0 && (
                            <div>
                              <div className="mb-2 flex items-center gap-2">
                                <CheckCircle2 className="h-4 w-4 text-blue-500" />
                                <span className="text-xs font-semibold uppercase tracking-[0.14em] text-blue-600 dark:text-blue-400">
                                  Probable — datos en tu autofill compatibles con la actividad detectada
                                </span>
                              </div>
                              <p className="mb-3 text-[11px] text-muted-foreground">
                                Estos datos existen en tu Chrome y coinciden con la actividad
                                detectada ({company.login_detected ? "login" : ""}{company.checkout_detected ? " compra" : ""}{company.signup_detected ? " registro" : ""}).
                                No hay evidencia directa de que los ingresaste aquí, pero es probable.
                              </p>
                              <div className="space-y-2">
                                {company.autofill_hints.map(datum => (
                                  <div key={datum.tipo_key}
                                    className="flex flex-wrap items-start gap-3 rounded-2xl border border-blue-500/15 bg-blue-500/5 px-4 py-3"
                                  >
                                    <div className="w-28 shrink-0">
                                      <span className="text-xs font-semibold text-blue-700 dark:text-blue-300">{datum.tipo}</span>
                                      <div className="mt-0.5 text-[10px] text-muted-foreground">{datum.evidencia}</div>
                                    </div>
                                    <div className="flex flex-wrap gap-1.5">
                                      {datum.valores.map(v => (
                                        <span key={v} className="rounded-lg border border-blue-500/20 bg-blue-500/10 px-2.5 py-1 font-mono text-xs text-blue-900 dark:text-blue-100">
                                          {v}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* ── Nivel 3: Solo inferencia ── */}
                          {company.probable_data_types.length > 0 && (
                            <div>
                              <div className="mb-2 flex items-center gap-2">
                                <CircleDashed className="h-4 w-4 text-muted-foreground" />
                                <span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                  Inferido — típico para este tipo de empresa
                                </span>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {company.probable_data_types.map(dtype => (
                                  <Badge key={dtype} variant="secondary"
                                    className="bg-muted/60 px-3 py-1 text-xs text-muted-foreground">
                                    {dtype}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* ── Info adicional ── */}
                          <div className="grid gap-4 pt-1 sm:grid-cols-3">
                            <div className="space-y-1">
                              <div className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">Riesgo</div>
                              <div className="flex items-center gap-2">
                                {riskIcon(company.risk_level)}
                                <span className="font-semibold">{RISK_LABEL[company.risk_level]}</span>
                              </div>
                            </div>
                            <div className="space-y-1">
                              <div className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">Actividad</div>
                              <div className="flex flex-wrap gap-1">
                                {company.login_detected && (
                                  <Badge variant="outline" className="border-blue-500/40 text-xs text-blue-600 dark:text-blue-400">
                                    <LogIn className="mr-1 h-3 w-3" />Login
                                  </Badge>
                                )}
                                {company.signup_detected && (
                                  <Badge variant="outline" className="text-xs"><UserRound className="mr-1 h-3 w-3" />Registro</Badge>
                                )}
                                {company.checkout_detected && (
                                  <Badge variant="outline" className="border-purple-500/40 text-xs text-purple-600 dark:text-purple-400">
                                    <ShoppingCart className="mr-1 h-3 w-3" />Compra
                                  </Badge>
                                )}
                                {!company.login_detected && !company.signup_detected && !company.checkout_detected && (
                                  <span className="text-xs text-muted-foreground">Solo navegación</span>
                                )}
                              </div>
                            </div>
                            <div className="space-y-1">
                              <div className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">Visitas</div>
                              <div className="text-sm font-semibold">{company.visit_count}</div>
                              <div className="text-xs text-muted-foreground">Última: {formatDate(company.last_visit_iso)}</div>
                            </div>
                          </div>
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  ))}
                </Accordion>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </Layout>
  );
}
