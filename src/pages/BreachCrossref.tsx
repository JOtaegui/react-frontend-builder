import { useState, useEffect } from "react";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import {
  AlertTriangle, CheckCircle2, Chrome, DatabaseZap, Globe, Loader2,
  Mail, RefreshCw, ShieldAlert, ShieldOff, ShieldCheck, Skull, TriangleAlert, UserCheck,
} from "lucide-react";

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface HibpBreach {
  name: string;
  domain: string;
  breach_date: string | null;
  pwn_count: number;
  data_types: string[];
  description: string;
  source?: string;
}

interface CrossrefCompany {
  domain: string;
  company_name: string;
  sender_type: string;
  country: string;
  is_chilean: boolean;
  visit_count: number;
  risk_level: "high" | "medium" | "low";
  tags: string[];
  // cruce
  also_in_email: boolean;
  hibp_breaches: HibpBreach[];
  breach_count: number;
  has_breach: boolean;
  composite_risk: "critical" | "high" | "medium" | "low";
  recommended_action: string;
  legal_basis: string[];
  hibp_checked: boolean;
  // perfil de datos
  data_profile?: {
    has_email_data:      boolean;
    data_types:          string[];
    data_type_labels:    string[];
    source:              "email_analysis" | "inferred" | "none";
    sender_type:         string;
    sample_subjects:     string[];
    your_exposed_data:   string[];
    your_exposed_labels: string[];
    breach_data_classes: string[];
  };
}

interface ScraperStats {
  total: number;
  high: number;
  medium: number;
  low: number;
  scraped: number;
  hardcoded: number;
  domains: string[];
  last_scraped: string | null;
}

interface ScraperRunResult {
  ok: boolean;
  urls_found: number;
  articles_processed: number;
  incidents_found: number;
  incidents_new: number;
  errors: number;
  stats: ScraperStats;
}

interface CrossrefResponse {
  total_companies: number;
  critical_count: number;
  breach_count: number;
  in_email_count: number;
  hibp_checked: number;
  email_domains_received: number;
  companies: CrossrefCompany[];
}

const BROWSER_OPTIONS = [
  { value: "chrome",        label: "Google Chrome"  },
  { value: "brave",         label: "Brave"          },
  { value: "edge",          label: "Microsoft Edge" },
  { value: "firefox",       label: "Firefox"        },
  { value: "chrome-canary", label: "Chrome Canary"  },
] as const;

// ── Helpers ───────────────────────────────────────────────────────────────────

const COMPOSITE_LABEL: Record<string, string> = {
  critical: "Crítico", high: "Alto", medium: "Medio", low: "Bajo",
};

const COMPOSITE_COLOR: Record<string, string> = {
  critical: "bg-red-100 border-red-200",
  high:     "bg-orange-50 border-orange-200",
  medium:   "bg-amber-50 border-amber-200",
  low:      "bg-muted/30 border-border",
};

function compositeIcon(risk: string) {
  if (risk === "critical") return <Skull       className="h-4 w-4 text-red-600" />;
  if (risk === "high")     return <ShieldOff   className="h-4 w-4 text-orange-500" />;
  if (risk === "medium")   return <ShieldAlert className="h-4 w-4 text-amber-500" />;
  return                          <ShieldCheck className="h-4 w-4 text-emerald-500" />;
}

function compositeBadge(risk: string): "destructive" | "default" | "secondary" | "outline" {
  if (risk === "critical") return "destructive";
  if (risk === "high")     return "destructive";
  if (risk === "medium")   return "default";
  return "secondary";
}

function formatPwnCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M cuentas`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(0)}K cuentas`;
  return `${n} cuentas`;
}

function formatDate(d: string | null): string {
  if (!d) return "—";
  try { return new Date(d).toLocaleDateString("es-CL", { year: "numeric", month: "long" }); }
  catch { return d; }
}

// ── Componente principal ──────────────────────────────────────────────────────

// ── Helpers de localStorage ───────────────────────────────────────────────────

interface EmailSenderProfile {
  primary_domain:      string;
  personal_data_types: string[];
  sender_type:         string;
  sample_subjects:     string[];
}

function loadEmailDomainsFromStorage(): { domains: string[]; ts: string | null } {
  try {
    const raw = localStorage.getItem("email_crossref_domains");
    const ts  = localStorage.getItem("email_crossref_ts");
    if (!raw) return { domains: [], ts: null };
    return { domains: JSON.parse(raw) as string[], ts };
  } catch {
    return { domains: [], ts: null };
  }
}

function loadEmailSendersFromStorage(): EmailSenderProfile[] {
  try {
    const raw = localStorage.getItem("email_crossref_senders");
    if (!raw) return [];
    return JSON.parse(raw) as EmailSenderProfile[];
  } catch {
    return [];
  }
}

function formatStorageTs(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("es-CL", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function BreachCrossref() {
  const [browser,       setBrowser]       = useState("chrome");
  const [emailDomains,  setEmailDomains]  = useState("");
  const [loading,       setLoading]       = useState(false);
  const [result,        setResult]        = useState<CrossrefResponse | null>(null);
  const [error,         setError]         = useState<string | null>(null);
  const [storedInfo,    setStoredInfo]    = useState<{ domains: string[]; ts: string | null }>({ domains: [], ts: null });
  const [scraperStats,  setScraperStats]  = useState<ScraperStats | null>(null);
  const [scraperRunning, setScraperRunning] = useState(false);
  const [scraperResult,  setScraperResult]  = useState<ScraperRunResult | null>(null);

  // Al montar: leer dominios guardados + stats del scraper
  useEffect(() => {
    const stored = loadEmailDomainsFromStorage();
    setStoredInfo(stored);
    if (stored.domains.length > 0 && !emailDomains) {
      setEmailDomains(stored.domains.join(", "));
    }
    fetch("/api/local/breach-scraper/stats")
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setScraperStats(d))
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleRunScraper() {
    setScraperRunning(true); setScraperResult(null);
    try {
      const res = await fetch("/api/local/breach-scraper/run", { method: "POST" });
      const data: ScraperRunResult = await res.json();
      setScraperResult(data);
      if (data.stats) setScraperStats(data.stats);
    } catch {
      // silencioso
    } finally {
      setScraperRunning(false);
    }
  }

  // ── Análisis ────────────────────────────────────────────────────────────────
  async function handleAnalyze() {
    setLoading(true); setError(null); setResult(null);

    // Parsear dominios de correo (separados por coma, newline o espacio)
    const parsedDomains = emailDomains
      .split(/[\n,;\s]+/)
      .map(d => d.trim().toLowerCase())
      .filter(d => d.length > 0 && d.includes("."));

    // Cargar perfiles enriquecidos del análisis de email desde localStorage
    const emailSenders = loadEmailSendersFromStorage();

    try {
      const res = await fetch("/api/local/breach-crossref", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          browser,
          limit: 5000,
          email_domains: parsedDomains,
          email_senders: emailSenders,
          max_hibp_domains: 100,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(body.detail ?? `Error ${res.status}`);
      }
      const data: CrossrefResponse = await res.json();
      setResult(data);
      // Persistir resultados para Vista Consolidada
      try {
        const cachePayload: Record<string, { hasBreached: boolean; hibpBreach: boolean; clBreach: boolean; breachNames: string[] }> = {};
        for (const c of data.companies) {
          const domain = c.domain.toLowerCase().replace(/^www\./, "");
          cachePayload[domain] = {
            hasBreached:  c.has_breach,
            hibpBreach:   c.hibp_breaches.some(b => b.source !== "scraped_cl"),
            clBreach:     c.hibp_breaches.some(b => b.source === "scraped_cl"),
            breachNames:  c.hibp_breaches.map(b => b.name),
          };
        }
        localStorage.setItem("consolidated_hibp_result", JSON.stringify({ ts: Date.now(), breaches: cachePayload }));
      } catch { /* ignore storage errors */ }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }

  // ── Estadísticas rápidas ─────────────────────────────────────────────────────
  const statCards = result ? [
    {
      label: "Empresas analizadas",
      value: result.total_companies,
      icon: <Globe className="h-5 w-5 text-muted-foreground" />,
      color: "bg-card",
    },
    {
      label: "Con filtración",
      value: result.breach_count,
      icon: <DatabaseZap className="h-5 w-5 text-red-500" />,
      color: result.breach_count > 0 ? "bg-red-50 border-red-200" : "bg-card",
    },
    {
      label: "También en correo",
      value: result.in_email_count,
      icon: <Mail className="h-5 w-5 text-blue-500" />,
      color: result.in_email_count > 0 ? "bg-blue-50 border-blue-200" : "bg-card",
    },
    {
      label: "Riesgo Crítico",
      value: result.critical_count,
      icon: <Skull className="h-5 w-5 text-red-600" />,
      color: result.critical_count > 0 ? "bg-red-50 border-red-200" : "bg-card",
    },
  ] : [];

  return (
    <Layout>
      <div className="max-w-5xl mx-auto space-y-6 p-6">

        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <DatabaseZap className="h-6 w-6 text-red-500" />
            Cruce de Filtraciones
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Cruza las empresas de tu historial de navegación con filtraciones globales (HIBP)
            y con las empresas que te envían correos. Identifica dónde estás más expuesto.
          </p>
        </div>

        {/* Configuración */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Configuración del análisis</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Navegador */}
              <div className="space-y-1.5">
                <Label htmlFor="browser-select">Navegador</Label>
                <Select value={browser} onValueChange={setBrowser}>
                  <SelectTrigger id="browser-select" className="w-full">
                    <Chrome className="h-4 w-4 mr-2 text-muted-foreground" />
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {BROWSER_OPTIONS.map(o => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Dominios de correo */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <Label htmlFor="email-domains">
                    Dominios del análisis de correo{" "}
                    <span className="text-muted-foreground font-normal">(opcional)</span>
                  </Label>
                  {storedInfo.domains.length > 0 && (
                    <span className="flex items-center gap-1.5 text-[11px] text-blue-700 bg-blue-50 border border-blue-200 rounded-full px-2 py-0.5">
                      <CheckCircle2 className="h-3 w-3" />
                      {storedInfo.domains.length} dominios cargados desde Identificación de Correo
                      {storedInfo.ts && (
                        <span className="text-blue-500">· {formatStorageTs(storedInfo.ts)}</span>
                      )}
                    </span>
                  )}
                </div>
                <textarea
                  id="email-domains"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none h-[72px] focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder={"falabella.com, bancoestado.cl, ripley.cl\n(separados por coma o línea)"}
                  value={emailDomains}
                  onChange={e => setEmailDomains(e.target.value)}
                />
                {storedInfo.domains.length > 0 && emailDomains !== storedInfo.domains.join(", ") && (
                  <button
                    type="button"
                    className="text-[11px] text-blue-600 hover:underline"
                    onClick={() => setEmailDomains(storedInfo.domains.join(", "))}
                  >
                    Restaurar {storedInfo.domains.length} dominios guardados
                  </button>
                )}
              </div>
            </div>

            {/* Panel scraper */}
            <div className="rounded-lg border bg-muted/30 p-3 space-y-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <RefreshCw className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Base de incidentes chilenos</span>
                  {scraperStats && scraperStats.total > 0 ? (
                    <span className="text-[11px] bg-emerald-100 border border-emerald-300 text-emerald-800 rounded-full px-2 py-0.5">
                      {scraperStats.total} incidente{scraperStats.total > 1 ? "s" : ""} verificados
                      {scraperStats.high > 0 && ` · ${scraperStats.high} alta confianza`}
                    </span>
                  ) : (
                    <span className="text-[11px] text-muted-foreground">cargando…</span>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRunScraper}
                  disabled={scraperRunning}
                  className="gap-1.5 text-xs"
                >
                  {scraperRunning
                    ? <><Loader2 className="h-3 w-3 animate-spin" />Buscando…</>
                    : <><RefreshCw className="h-3 w-3" />Actualizar ahora</>
                  }
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Lista base: {scraperStats ? scraperStats.hardcoded : "…"} incidentes verificados con fuentes (BleepingComputer, SecurityAffairs, Cybernews, df.cl).
                "Actualizar" agrega nuevos casos scrapeando DuckDuckGo + Gemini (requiere GEMINI_API_KEY válida).
              </p>
              {scraperRunning && (
                <p className="text-[11px] text-amber-700">
                  Buscando artículos y extrayendo datos… puede tardar 30–90 segundos.
                </p>
              )}
              {scraperResult && (
                <div className="text-[11px] text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 pt-1">
                  <span>URLs: <strong>{scraperResult.urls_found}</strong></span>
                  <span>Artículos: <strong>{scraperResult.articles_processed}</strong></span>
                  <span>Detectados: <strong>{scraperResult.incidents_found}</strong></span>
                  <span className="text-emerald-700 font-medium">Nuevos: {scraperResult.incidents_new}</span>
                  {scraperResult.errors > 0 && (
                    <span className="text-amber-600">Errores: {scraperResult.errors}</span>
                  )}
                </div>
              )}
              {scraperStats?.last_scraped && (
                <p className="text-[11px] text-muted-foreground">
                  Última actualización: {formatStorageTs(scraperStats.last_scraped)}
                </p>
              )}
            </div>

            <div className="flex items-center gap-3">
              <Button onClick={handleAnalyze} disabled={loading} className="gap-2">
                {loading
                  ? <><Loader2 className="h-4 w-4 animate-spin" />Analizando…</>
                  : <><DatabaseZap className="h-4 w-4" />Analizar filtraciones</>
                }
              </Button>
              {loading && (
                <p className="text-xs text-muted-foreground">
                  Consultando HIBP para hasta 100 dominios · puede tardar ~15 s
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Error */}
        {error && (
          <Card className="border-destructive/50 bg-destructive/5">
            <CardContent className="pt-4 flex items-start gap-3">
              <TriangleAlert className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-destructive text-sm">Error en el análisis</p>
                <p className="text-sm text-muted-foreground mt-0.5">{error}</p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Resultados */}
        {result && (
          <>
            {/* Tarjetas de resumen */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {statCards.map((s) => (
                <Card key={s.label} className={`border ${s.color}`}>
                  <CardContent className="pt-4 pb-3">
                    <div className="flex items-center justify-between mb-1">
                      {s.icon}
                      <span className="text-2xl font-bold">{s.value}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">{s.label}</p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Banner crítico */}
            {result.critical_count > 0 && (
              <Card className="border-red-300 bg-red-50">
                <CardContent className="pt-4 flex items-start gap-3">
                  <Skull className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-red-800 text-sm">
                      {result.critical_count} empresa{result.critical_count > 1 ? "s" : ""} en riesgo crítico
                    </p>
                    <p className="text-xs text-red-700 mt-0.5">
                      Estas empresas tuvieron una filtración de datos Y están en contacto contigo.
                      Art. 22 Ley 21.719 te da el derecho de supresión reforzado — puedes exigir
                      la eliminación completa de tus datos.
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Nota fuente */}
            <p className="text-xs text-muted-foreground">
              {result.hibp_checked} de {result.total_companies} dominios consultados en{" "}
              <a href="https://haveibeenpwned.com" target="_blank" rel="noreferrer" className="underline hover:text-foreground">
                HaveIBeenPwned
              </a>
              {result.email_domains_received > 0 &&
                ` · ${result.email_domains_received} dominios de correo cruzados`
              }.{" "}
              Fuentes: HIBP (global) + Lista Chile (incidentes chilenos verificados con fuentes públicas).
            </p>

            {/* Tabla de empresas */}
            <CompanyTable companies={result.companies} />
          </>
        )}
      </div>
    </Layout>
  );
}

// ── Tabla de empresas ─────────────────────────────────────────────────────────

function CompanyTable({ companies }: { companies: CrossrefCompany[] }) {
  if (companies.length === 0) {
    return (
      <Card>
        <CardContent className="pt-8 pb-8 text-center text-sm text-muted-foreground">
          No se encontraron empresas en el historial.
        </CardContent>
      </Card>
    );
  }

  return (
    <Accordion type="multiple" className="space-y-2">
      {companies.map((c) => (
        <CompanyRow key={c.domain} company={c} />
      ))}
    </Accordion>
  );
}

// ── Fila de empresa ───────────────────────────────────────────────────────────

function CompanyRow({ company: c }: { company: CrossrefCompany }) {
  const riskColor = COMPOSITE_COLOR[c.composite_risk] ?? COMPOSITE_COLOR.low;

  return (
    <Card className={`border overflow-hidden ${riskColor}`}>
      <AccordionItem value={c.domain} className="border-0">
        <AccordionTrigger className="px-4 py-3 hover:no-underline hover:bg-black/5 [&>svg]:shrink-0">
          <div className="flex flex-1 items-center gap-3 text-left min-w-0">

            {/* Icono de riesgo compuesto */}
            <div className="shrink-0">{compositeIcon(c.composite_risk)}</div>

            {/* Nombre + dominio */}
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-sm truncate">{c.company_name}</p>
              <p className="text-xs text-muted-foreground truncate">{c.domain}</p>
            </div>

            {/* Señales */}
            <div className="flex items-center gap-1.5 shrink-0">
              {c.has_breach && (
                <Badge variant="destructive" className="text-[10px] gap-1 px-1.5 py-0">
                  <DatabaseZap className="h-3 w-3" />
                  {c.breach_count} filtración{c.breach_count > 1 ? "es" : ""}
                </Badge>
              )}
              {c.also_in_email && (
                <Badge variant="outline" className="text-[10px] gap-1 px-1.5 py-0 border-blue-400 text-blue-700 bg-blue-50">
                  <Mail className="h-3 w-3" />
                  en correo
                </Badge>
              )}
              <Badge variant={compositeBadge(c.composite_risk)} className="text-[10px] px-1.5 py-0">
                {COMPOSITE_LABEL[c.composite_risk] ?? c.composite_risk}
              </Badge>
            </div>
          </div>
        </AccordionTrigger>

        <AccordionContent className="px-4 pb-4">
          <div className="space-y-4 pt-1">

            {/* Señales de presencia */}
            <PresenceSection company={c} />

            {/* Datos personales en riesgo */}
            {c.data_profile && (c.data_profile.data_types.length > 0 || c.data_profile.your_exposed_data.length > 0) && (
              <DataProfileSection profile={c.data_profile} hasBreach={c.has_breach} />
            )}

            {/* Filtraciones HIBP */}
            {c.has_breach && <BreachSection breaches={c.hibp_breaches} />}

            {/* Sin filtración conocida */}
            {c.hibp_checked && !c.has_breach && (
              <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                Sin filtraciones conocidas en HIBP para este dominio.
              </div>
            )}

            {/* Acción recomendada */}
            <ActionSection company={c} />
          </div>
        </AccordionContent>
      </AccordionItem>
    </Card>
  );
}

// ── Sección: perfil de datos personales ──────────────────────────────────────

type DataProfile = NonNullable<CrossrefCompany["data_profile"]>;

function DataProfileSection({ profile, hasBreach }: { profile: DataProfile; hasBreach: boolean }) {
  const hasExposed = profile.your_exposed_labels.length > 0;
  const hasKnown   = profile.data_type_labels.length > 0;

  return (
    <div className="space-y-2">
      {/* Datos que esta empresa tiene del usuario */}
      {hasKnown && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5 flex items-center gap-1.5">
            <UserCheck className="h-3.5 w-3.5 text-blue-500" />
            Datos que esta empresa tiene sobre ti
            {profile.source === "inferred" && (
              <span className="font-normal normal-case text-muted-foreground">(inferido del tipo de empresa)</span>
            )}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {profile.data_type_labels.map(label => (
              <span
                key={label}
                className={`text-[11px] rounded-full px-2.5 py-0.5 border font-medium ${
                  hasBreach && profile.your_exposed_labels.includes(label)
                    ? "bg-red-100 border-red-300 text-red-800"
                    : "bg-blue-50 border-blue-200 text-blue-800"
                }`}
              >
                {label}
                {hasBreach && profile.your_exposed_labels.includes(label) && " ⚠"}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Datos tuyos en riesgo por la filtración */}
      {hasBreach && hasExposed && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
          <p className="text-xs font-semibold text-red-800 mb-1.5 flex items-center gap-1.5">
            <ShieldOff className="h-3.5 w-3.5" />
            Tus datos en riesgo según la filtración
          </p>
          <div className="flex flex-wrap gap-1.5">
            {profile.your_exposed_labels.map(label => (
              <span key={label} className="text-[11px] bg-red-100 border border-red-300 text-red-800 rounded-full px-2.5 py-0.5 font-semibold">
                {label}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Breach pero sin datos de email → mostrar qué expuso el breach igual */}
      {hasBreach && !hasExposed && profile.breach_data_classes.length > 0 && !hasKnown && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5 flex items-center gap-1.5">
            <DatabaseZap className="h-3.5 w-3.5 text-orange-500" />
            Tipos de datos expuestos en la filtración
          </p>
          <div className="flex flex-wrap gap-1">
            {profile.breach_data_classes.slice(0, 8).map(dt => (
              <Badge key={dt} variant="outline" className="text-[10px] px-1.5 py-0 border-orange-300 text-orange-700">
                {dt}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sección: presencia en fuentes ─────────────────────────────────────────────

function PresenceSection({ company: c }: { company: CrossrefCompany }) {
  return (
    <div>
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
        Señales de presencia
      </p>
      <div className="flex flex-wrap gap-2">
        {/* Siempre en browser */}
        <div className="flex items-center gap-1.5 bg-muted/60 rounded-md px-2.5 py-1.5 text-xs">
          <Chrome className="h-3.5 w-3.5 text-muted-foreground" />
          <span>Historial del navegador</span>
          <span className="text-muted-foreground">· {c.visit_count} visitas</span>
          <Badge
            variant={c.risk_level === "high" ? "destructive" : c.risk_level === "medium" ? "default" : "secondary"}
            className="text-[10px] ml-1 px-1 py-0"
          >
            {c.risk_level === "high" ? "Alto" : c.risk_level === "medium" ? "Medio" : "Bajo"}
          </Badge>
        </div>

        {/* En correo (si aplica) */}
        {c.also_in_email && (
          <div className="flex items-center gap-1.5 bg-blue-50 border border-blue-200 rounded-md px-2.5 py-1.5 text-xs text-blue-800">
            <Mail className="h-3.5 w-3.5" />
            <span>Encontrada en análisis de correo</span>
          </div>
        )}

        {/* País */}
        <div className="flex items-center gap-1.5 bg-muted/40 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground">
          <Globe className="h-3.5 w-3.5" />
          {c.country}
        </div>
      </div>
    </div>
  );
}

// ── Sección: filtraciones (HIBP + lista chilena) ──────────────────────────────

function BreachSection({ breaches }: { breaches: HibpBreach[] }) {
  // Separar por origen
  const hibpBreaches = breaches.filter(b => b.source !== "scraped_cl");
  const clBreaches   = breaches.filter(b => b.source === "scraped_cl");

  return (
    <div className="space-y-4">

      {/* ── HIBP ── */}
      {hibpBreaches.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <DatabaseZap className="h-3.5 w-3.5 text-red-500" />
            Filtraciones globales · HaveIBeenPwned
          </p>
          <div className="space-y-2">
            {hibpBreaches.map((b) => (
              <div key={b.name} className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-red-800">{b.name}</p>
                    {b.breach_date && (
                      <p className="text-xs text-red-600 mt-0.5">{formatDate(b.breach_date)}</p>
                    )}
                  </div>
                  {b.pwn_count > 0 && (
                    <span className="text-xs text-red-700 font-medium shrink-0">
                      {formatPwnCount(b.pwn_count)}
                    </span>
                  )}
                </div>
                {b.data_types?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {b.data_types.map(dt => (
                      <Badge key={dt} variant="outline" className="text-[10px] px-1.5 py-0 border-red-300 text-red-700 bg-red-50">
                        {dt}
                      </Badge>
                    ))}
                  </div>
                )}
                {b.description && (
                  <p className="text-xs text-red-700 mt-2 leading-relaxed line-clamp-3">{b.description}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Lista Chile ── */}
      {clBreaches.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <ShieldAlert className="h-3.5 w-3.5 text-orange-500" />
            Incidente verificado · Lista Chile
          </p>
          <div className="space-y-2">
            {clBreaches.map((b: any) => {
              const nombre   = b.company_name || b.name || "—";
              const fecha    = b.incident_date || b.breach_date || "";
              const fuentes: string[] = b.sources || [];
              const tipos: string[]   = b.data_types || [];
              const conf: string      = b.confidence || "medium";
              const confColor = conf === "high"
                ? "border-orange-300 text-orange-700 bg-orange-50"
                : "border-yellow-300 text-yellow-700 bg-yellow-50";
              return (
                <div key={b.id || nombre} className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-sm">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-orange-900">{nombre}</p>
                      {fecha && (
                        <p className="text-xs text-orange-700 mt-0.5">{fecha}</p>
                      )}
                    </div>
                    <Badge variant="outline" className={`text-[10px] px-1.5 py-0 shrink-0 ${confColor}`}>
                      {conf === "high" ? "alta confianza" : "media confianza"}
                    </Badge>
                  </div>

                  {b.confirmed_facts && (
                    <p className="text-xs text-orange-800 mt-2 leading-relaxed">{b.confirmed_facts}</p>
                  )}
                  {b.unconfirmed && (
                    <p className="text-xs text-orange-600 mt-1 leading-relaxed italic">
                      No confirmado: {b.unconfirmed}
                    </p>
                  )}
                  {tipos.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {tipos.map(dt => (
                        <Badge key={dt} variant="outline" className="text-[10px] px-1.5 py-0 border-orange-300 text-orange-700 bg-orange-50">
                          {dt}
                        </Badge>
                      ))}
                    </div>
                  )}
                  {fuentes.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {fuentes.map(url => {
                        const domain = url.replace(/https?:\/\/(www\.)?/, "").split("/")[0];
                        return (
                          <a key={url} href={url} target="_blank" rel="noopener noreferrer"
                            className="text-[10px] text-orange-600 underline hover:text-orange-800">
                            {domain}
                          </a>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

    </div>
  );
}

// ── Sección: acción recomendada ───────────────────────────────────────────────

function ActionSection({ company: c }: { company: CrossrefCompany }) {
  const isCritical = c.composite_risk === "critical";
  const isHigh     = c.composite_risk === "high";

  const bgColor = isCritical
    ? "bg-red-50 border-red-200"
    : isHigh
    ? "bg-orange-50 border-orange-200"
    : "bg-muted/40 border-border";

  const textColor = isCritical ? "text-red-800" : isHigh ? "text-orange-800" : "text-foreground";
  const subColor  = isCritical ? "text-red-700" : isHigh ? "text-orange-700" : "text-muted-foreground";

  return (
    <div className={`rounded-lg border p-3 ${bgColor}`}>
      <div className="flex items-start gap-2">
        {isCritical
          ? <AlertTriangle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
          : isHigh
          ? <ShieldOff className="h-4 w-4 text-orange-500 shrink-0 mt-0.5" />
          : <ShieldCheck className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
        }
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold ${textColor}`}>{c.recommended_action}</p>
          {c.legal_basis.length > 0 && (
            <ul className={`mt-1.5 space-y-0.5 text-xs ${subColor}`}>
              {c.legal_basis.map((b) => (
                <li key={b} className="flex items-center gap-1.5">
                  <span className="w-1 h-1 rounded-full bg-current shrink-0" />
                  {b}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
