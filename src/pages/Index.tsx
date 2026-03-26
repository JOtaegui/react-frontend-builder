import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { RiskBadge } from "@/components/RiskBadge";
import { mockSearches } from "@/data/mockData";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Badge } from "@/components/ui/badge";
import {
  Fingerprint, SlidersHorizontal, Eye, ExternalLink, Flame, History,
  Zap, Timer, Telescope, Loader2, Wifi, WifiOff,
  Users, Vote, Building2, Gavel, BadgeCheck, Globe,
  ChevronDown, ChevronUp,
} from "lucide-react";

// ─── Tipos ────────────────────────────────────────────────────────────────────
interface NRYFEntry { nombre: string; rut: string; sexo?: string; direccion?: string; ciudad?: string; }
interface ServelEntry { nombre: string; rut: string; circunscripcion?: string; region?: string; mesa?: string; local?: string; direccion_local?: string; }
interface EmpresaEntry { razon_social: string; rut_empresa?: string; tipo?: string; estado?: string; }
interface PjudEntry { rol: string; tribunal: string; materia?: string; estado?: string; fecha?: string; }
interface SIIEntry { nombre?: string; actividad?: string; contribuyente_iva?: boolean; inicio_actividades?: string; }
interface OSINTFuentes {
  nryf_nombre: NRYFEntry[];
  nryf_rut?: NRYFEntry | null;
  servel?: ServelEntry | null;
  sii?: SIIEntry | null;
  empresas: EmpresaEntry[];
  pjud: PjudEntry[];
  diario_oficial: { titulo: string; url: string; descripcion?: string }[];
}
interface OSINTResumen {
  total_hallazgos: number;
  fuentes_con_datos: string[];
  tiene_antecedentes_judiciales: boolean;
  tiene_actividad_empresarial: boolean;
  inscrito_servel: boolean;
  advertencia?: string;
}
interface OSINTResponse { query: string; rut?: string; fuentes: OSINTFuentes; resumen: OSINTResumen; }
type BackendStatus = "checking" | "online" | "offline";

// ─── Hook backend ─────────────────────────────────────────────────────────────
function useBackendStatus(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>("checking");
  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch("/__health", { signal: AbortSignal.timeout(3000) });
        if (!cancelled) setStatus(res.ok ? "online" : "offline");
      } catch { if (!cancelled) setStatus("offline"); }
    };
    check();
    const iv = setInterval(check, 10_000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);
  return status;
}

function BackendIndicator({ status }: { status: BackendStatus }) {
  const cfg = {
    checking: { dot: "bg-yellow-400 animate-pulse", text: "text-yellow-400", label: "Conectando...", Icon: Wifi },
    online:   { dot: "bg-emerald-400 animate-pulse", text: "text-emerald-400", label: "En vivo",      Icon: Wifi },
    offline:  { dot: "bg-red-500",                   text: "text-red-400",     label: "Sin conexión", Icon: WifiOff },
  }[status];
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span className={`h-1.5 w-1.5 rounded-full ${cfg.dot}`} />
      <cfg.Icon className={`h-3 w-3 ${cfg.text}`} />
      <span className={`${cfg.text}`}>{cfg.label}</span>
    </div>
  );
}

// ─── Sección colapsable ───────────────────────────────────────────────────────
function Section({ title, icon, badge, children, defaultOpen = true }: {
  title: string; icon: React.ReactNode; badge?: string | number;
  children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center gap-2.5 px-5 py-3.5 text-left hover:bg-muted/30 transition-colors"
        onClick={() => setOpen(!open)}
      >
        {icon}
        <span className="text-sm font-medium flex-1">{title}</span>
        {badge !== undefined && (
          <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full mr-1">{badge}</span>
        )}
        {open
          ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
          : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
      </button>
      {open && <div className="px-5 pb-4 pt-2 border-t border-border">{children}</div>}
    </div>
  );
}

// ─── Página ───────────────────────────────────────────────────────────────────
const Index = () => {
  const navigate = useNavigate();
  const backendStatus = useBackendStatus();

  const [nombre, setNombre]   = useState("");
  const [rut, setRut]         = useState("");
  const [email, setEmail]     = useState("");
  const [rrss, setRrss]       = useState("");
  const [profundidad, setProfundidad] = useState("normal");

  const [loading, setLoading]               = useState(false);
  const [error, setError]                   = useState<string | null>(null);
  const [osint, setOsint]                   = useState<OSINTResponse | null>(null);
  const [queryRealizada, setQueryRealizada] = useState("");

  const handleBuscar = async () => {
    if (!nombre.trim()) return;
    if (backendStatus === "offline") {
      setError("Backend no disponible en puerto 8000.");
      return;
    }
    setLoading(true);
    setError(null);
    setOsint(null);

    try {
      const rutParam = rut.trim() ? `&rut=${encodeURIComponent(rut.trim())}` : "";
      const res = await fetch(
        `/api/osint?nombre=${encodeURIComponent(nombre.trim())}${rutParam}`,
        { signal: AbortSignal.timeout(90_000) }
      );
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.includes("application/json")) throw new Error(`HTTP ${res.status}`);
      const data: OSINTResponse = await res.json();
      if (!res.ok) throw new Error((data as { detail?: string }).detail ?? `Error ${res.status}`);
      setOsint(data);
      setQueryRealizada(data.query);
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "TimeoutError")
        setError("Búsqueda demoró más de 90s. Intenta de nuevo.");
      else
        setError(e instanceof Error ? e.message : "Error desconocido.");
    } finally {
      setLoading(false);
    }
  };

  const f = osint?.fuentes;
  const r = osint?.resumen;
  const hasResults = osint && f && r;

  return (
    <Layout>
      <div className="max-w-3xl mx-auto space-y-8">

        {/* ── Hero ─────────────────────────────────────────────────────────── */}
        <div className="flex flex-col items-center text-center pt-10 space-y-4">
          <div className="relative">
            <div className="absolute -inset-5 rounded-full bg-primary/15 blur-2xl" />
            <Fingerprint className="relative h-14 w-14 text-primary" strokeWidth={1.5} />
          </div>
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">OSINT Chile — Huella Digital</h1>
            <p className="text-sm text-muted-foreground max-w-sm">
              Plataforma de identificación y monitoreo de exposición de datos personales
              alineada con la <span className="text-primary">Ley N°21.719</span>
            </p>
          </div>
          <BackendIndicator status={backendStatus} />
        </div>

        {/* ── Buscador ─────────────────────────────────────────────────────── */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleBuscar()}
              placeholder="Nombre completo..."
              className="w-full h-14 px-5 rounded-xl bg-card border border-border text-base focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-colors"
            />
          </div>

          <Popover>
            <PopoverTrigger asChild>
              <button className="h-14 w-14 rounded-xl border border-border bg-card hover:bg-muted/50 transition-colors flex items-center justify-center shrink-0">
                <SlidersHorizontal className="h-5 w-5 text-muted-foreground" />
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-72 space-y-4" align="end">
              <div className="space-y-3">
                {[
                  { label: "RUT",   value: rut,   set: setRut,   ph: "12.345.678-9"    },
                  { label: "Email", value: email, set: setEmail, ph: "ejemplo@mail.com" },
                  { label: "RRSS",  value: rrss,  set: setRrss,  ph: "@usuario"         },
                ].map(({ label, value, set, ph }) => (
                  <div key={label} className="space-y-1">
                    <Label className="text-xs text-muted-foreground">{label}</Label>
                    <Input value={value} onChange={(e) => set(e.target.value)} placeholder={ph} className="h-8 text-xs" />
                  </div>
                ))}
              </div>
              <div className="border-t border-border pt-3 space-y-2">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Profundidad</p>
                <RadioGroup value={profundidad} onValueChange={setProfundidad} className="space-y-1">
                  {[
                    { value: "rapida",   Icon: Zap,       label: "Rápida (~5 min)"  },
                    { value: "normal",   Icon: Timer,     label: "Normal (~15 min)" },
                    { value: "profunda", Icon: Telescope, label: "Profunda (~1h)"   },
                  ].map(({ value, Icon, label }) => (
                    <div key={value} className="flex items-center gap-2">
                      <RadioGroupItem value={value} id={value} />
                      <Icon className="h-3 w-3 text-muted-foreground" />
                      <Label htmlFor={value} className="text-xs font-normal">{label}</Label>
                    </div>
                  ))}
                </RadioGroup>
              </div>
              <div className="border-t border-border pt-3 space-y-2">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Alcance</p>
                <div className="flex flex-wrap gap-3">
                  {[["chile","Chile"],["intl","Internacional"],["darkweb","Dark Web"]].map(([id, lbl]) => (
                    <div key={id} className="flex items-center gap-1.5">
                      <Checkbox id={id} defaultChecked={id === "chile"} />
                      <Label htmlFor={id} className="text-xs font-normal">{lbl}</Label>
                    </div>
                  ))}
                </div>
              </div>
            </PopoverContent>
          </Popover>

          <button
            disabled={!nombre.trim() || loading || backendStatus === "offline"}
            onClick={handleBuscar}
            className="h-14 px-6 rounded-xl bg-primary text-primary-foreground text-base font-medium shrink-0 disabled:opacity-40 hover:bg-primary/90 transition-colors flex items-center gap-2"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
            {loading ? "Buscando..." : "Buscar"}
          </button>
        </div>

        {/* ── Loading ───────────────────────────────────────────────────────── */}
        {loading && (
          <div className="text-center py-12 space-y-2">
            <Loader2 className="h-5 w-5 animate-spin text-primary mx-auto" />
            <p className="text-sm text-muted-foreground">Consultando fuentes públicas...</p>
            <p className="text-xs text-muted-foreground/50">Primera búsqueda puede tardar ~20-30 segundos</p>
          </div>
        )}

        {/* ── Error ────────────────────────────────────────────────────────── */}
        {error && (
          <div className="px-4 py-3 rounded-lg border border-destructive/30 bg-destructive/5 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* ── Resultados ───────────────────────────────────────────────────── */}
        {hasResults && (
          <div className="space-y-3">

            {/* Encabezado de resultados */}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-medium">
                  {r.total_hallazgos > 0
                    ? `${r.total_hallazgos} hallazgo${r.total_hallazgos !== 1 ? "s" : ""}`
                    : "Sin resultados"
                  }{" "}
                  <span className="text-muted-foreground font-normal">para "{queryRealizada}"</span>
                </p>
                {r.fuentes_con_datos.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-0.5">{r.fuentes_con_datos.join(" · ")}</p>
                )}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {r.inscrito_servel               && <span className="text-xs text-blue-400 border border-blue-400/30 px-2 py-0.5 rounded-full">SERVEL</span>}
                {r.tiene_actividad_empresarial   && <span className="text-xs text-amber-400 border border-amber-400/30 px-2 py-0.5 rounded-full">Empresas</span>}
                {r.tiene_antecedentes_judiciales && <span className="text-xs text-red-400 border border-red-400/30 px-2 py-0.5 rounded-full">PJUD</span>}
                <button
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors ml-1"
                  onClick={() => { setOsint(null); setError(null); }}
                >
                  Limpiar
                </button>
              </div>
            </div>

            {/* NombreRutYFirma */}
            {f.nryf_nombre?.length > 0 && (
              <Section title="NombreRutYFirma.com" icon={<Users className="h-3.5 w-3.5 text-muted-foreground" />} badge={f.nryf_nombre.length}>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        {["Nombre","RUT","Sexo","Dirección","Ciudad"].map(h => (
                          <th key={h} className="text-left py-2 pr-4 text-xs font-medium text-muted-foreground">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {f.nryf_nombre.map((p, i) => (
                        <tr key={i} className="border-b border-border/40 last:border-0 hover:bg-muted/20 transition-colors">
                          <td className="py-2.5 pr-4 font-medium text-sm">{p.nombre}</td>
                          <td className="py-2.5 pr-4 font-mono text-xs text-muted-foreground">{p.rut}</td>
                          <td className="py-2.5 pr-4 text-xs text-muted-foreground">{p.sexo ?? "—"}</td>
                          <td className="py-2.5 pr-4 text-xs text-muted-foreground">{p.direccion ?? "—"}</td>
                          <td className="py-2.5 text-xs text-muted-foreground">{p.ciudad ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            )}

            {/* SERVEL */}
            {f.servel && (
              <Section title="SERVEL — Padrón Electoral" icon={<Vote className="h-3.5 w-3.5 text-blue-400" />} badge={1}>
                <div className="space-y-1 pt-1">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">{f.servel.nombre}</p>
                    <span className="font-mono text-xs text-muted-foreground">{f.servel.rut}</span>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {f.servel.region          && <span>📍 {f.servel.region}</span>}
                    {f.servel.circunscripcion && <span>🗺 {f.servel.circunscripcion}</span>}
                    {f.servel.mesa            && <span>🗳 Mesa {f.servel.mesa}</span>}
                    {f.servel.local           && <span>🏫 {f.servel.local}</span>}
                  </div>
                </div>
              </Section>
            )}

            {/* SII */}
            {f.sii && (
              <Section title="SII — Estado Tributario" icon={<BadgeCheck className="h-3.5 w-3.5 text-amber-400" />} badge={1}>
                <div className="space-y-1 pt-1">
                  {f.sii.nombre             && <p className="text-sm font-medium">{f.sii.nombre}</p>}
                  {f.sii.actividad          && <p className="text-xs text-muted-foreground">💼 {f.sii.actividad}</p>}
                  {f.sii.inicio_actividades && <p className="text-xs text-muted-foreground">📅 Inicio: {f.sii.inicio_actividades}</p>}
                  {f.sii.contribuyente_iva  && <p className="text-xs text-muted-foreground">🧾 Contribuyente de IVA</p>}
                </div>
              </Section>
            )}

            {/* Empresas */}
            {f.empresas.length > 0 && (
              <Section title="Registro de Empresas" icon={<Building2 className="h-3.5 w-3.5 text-orange-400" />} badge={f.empresas.length}>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        {["Razón Social","RUT","Tipo","Estado"].map(h => (
                          <th key={h} className="text-left py-2 pr-4 text-xs font-medium text-muted-foreground">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {f.empresas.map((e, i) => (
                        <tr key={i} className="border-b border-border/40 last:border-0 hover:bg-muted/20 transition-colors">
                          <td className="py-2.5 pr-4 font-medium text-sm">{e.razon_social}</td>
                          <td className="py-2.5 pr-4 font-mono text-xs text-muted-foreground">{e.rut_empresa ?? "—"}</td>
                          <td className="py-2.5 pr-4 text-xs text-muted-foreground">{e.tipo ?? "—"}</td>
                          <td className="py-2.5 text-xs">
                            <span className={`px-2 py-0.5 rounded-full border text-xs ${e.estado === "Vigente" ? "border-emerald-400/30 text-emerald-400" : "border-border text-muted-foreground"}`}>
                              {e.estado ?? "—"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            )}

            {/* PJUD */}
            {f.pjud.length > 0 && (
              <Section title="Poder Judicial — Causas" icon={<Gavel className="h-3.5 w-3.5 text-red-400" />} badge={f.pjud.length} defaultOpen={false}>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        {["Rol","Tribunal","Materia","Estado"].map(h => (
                          <th key={h} className="text-left py-2 pr-4 text-xs font-medium text-muted-foreground">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {f.pjud.map((p, i) => (
                        <tr key={i} className="border-b border-border/40 last:border-0 hover:bg-muted/20 transition-colors">
                          <td className="py-2.5 pr-4 font-mono text-xs">{p.rol}</td>
                          <td className="py-2.5 pr-4 text-xs">{p.tribunal}</td>
                          <td className="py-2.5 pr-4 text-xs text-muted-foreground">{p.materia ?? "—"}</td>
                          <td className="py-2.5 text-xs text-muted-foreground">{p.estado ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            )}

            {/* Diario Oficial */}
            {f.diario_oficial?.length > 0 && (
              <Section title="Diario Oficial" icon={<Globe className="h-3.5 w-3.5 text-cyan-400" />} badge={f.diario_oficial.length} defaultOpen={false}>
                <div className="space-y-2.5 pt-1">
                  {f.diario_oficial.map((d, i) => (
                    <div key={i} className="border-b border-border/40 last:border-0 pb-2.5 last:pb-0">
                      <a href={d.url} target="_blank" rel="noopener noreferrer"
                         className="text-xs font-medium hover:text-primary transition-colors flex items-center gap-1">
                        {d.titulo} <ExternalLink className="h-2.5 w-2.5 shrink-0" />
                      </a>
                      {d.descripcion && <p className="text-xs text-muted-foreground mt-0.5">{d.descripcion}</p>}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {r.total_hallazgos === 0 && (
              <div className="py-12 text-center text-sm text-muted-foreground">
                Sin resultados para "{queryRealizada}"
              </div>
            )}
          </div>
        )}

        {/* ── Búsquedas recientes ───────────────────────────────────────────── */}
        {!osint && !loading && !error && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-muted-foreground">
              <History className="h-3.5 w-3.5" />
              <span className="text-xs font-medium uppercase tracking-wider">Recientes</span>
            </div>
            <div className="rounded-lg border border-border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent border-border">
                    {["Nombre","Fecha","Hallazgos","Riesgo"].map((h, i) => (
                      <TableHead key={h} className={`text-muted-foreground text-xs ${i === 2 ? "text-center" : ""}`}>{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mockSearches.map((s) => (
                    <TableRow key={s.id} className="cursor-pointer hover:bg-muted/30 transition-colors border-border"
                      onClick={() => navigate(`/resultados/${s.id}`)}>
                      <TableCell className="font-medium text-sm">{s.nombre}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">{s.fecha}</TableCell>
                      <TableCell className="text-center">
                        <span className="flex items-center justify-center gap-1">
                          <Flame className="h-3 w-3 text-destructive" />
                          <span className="text-xs">{s.hallazgos}</span>
                        </span>
                      </TableCell>
                      <TableCell><RiskBadge level={s.riesgo} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}

      </div>
    </Layout>
  );
};

export default Index;