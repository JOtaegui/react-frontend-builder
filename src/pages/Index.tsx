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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Fingerprint, SlidersHorizontal, Radar, Eye, Flame, History, ExternalLink,
  Zap, Timer, Telescope, Loader2, Wifi, WifiOff,
  ShieldCheck, Scale, Globe, Search, Users, Vote,
  Building2, Gavel, BadgeCheck, ChevronDown, ChevronUp,
} from "lucide-react";

// ─── Tipos respuesta OSINT ────────────────────────────────────────────────────
interface RutificadorEntry {
  nombre: string; rut: string; sexo?: string; direccion?: string; ciudad?: string;
}
interface ServelEntry {
  nombre: string; rut: string; circunscripcion?: string; region?: string;
  mesa?: string; local?: string; direccion_local?: string;
}
interface EmpresaEntry {
  razon_social: string; rut_empresa?: string; tipo?: string; estado?: string;
}
interface PjudEntry {
  rol: string; tribunal: string; materia?: string; estado?: string; fecha?: string;
}
interface SIIEntry {
  nombre?: string; actividad?: string; contribuyente_iva?: boolean; inicio_actividades?: string;
}
interface NRYFEntry {
  nombre: string; rut: string; sexo?: string; direccion?: string; ciudad?: string;
}
interface OSINTFuentes {
  nryf_nombre:      NRYFEntry[];
  nryf_rut?:        NRYFEntry | null;
  servel?:          ServelEntry | null;
  sii?:             SIIEntry | null;
  empresas:         EmpresaEntry[];
  pjud:             PjudEntry[];
  diario_oficial:   { titulo: string; url: string; descripcion?: string }[];
}
interface OSINTResumen {
  total_hallazgos: number;
  fuentes_con_datos: string[];
  ruts_identificados: string[];
  tiene_antecedentes_judiciales: boolean;
  tiene_actividad_empresarial: boolean;
  inscrito_servel: boolean;
}
interface OSINTResponse {
  query: string;
  fuentes: OSINTFuentes;
  resumen: OSINTResumen;
}

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
    checking: { dot: "bg-yellow-400 animate-pulse", text: "text-yellow-400", label: "Conectando...",           Icon: Wifi },
    online:   { dot: "bg-emerald-400 animate-pulse", text: "text-emerald-400", label: "En vivo",               Icon: Wifi },
    offline:  { dot: "bg-red-500",                   text: "text-red-400",     label: "Sin conexión al backend", Icon: WifiOff },
  }[status];
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span className={`h-2 w-2 rounded-full ${cfg.dot}`} />
      <cfg.Icon className={`h-3.5 w-3.5 ${cfg.text}`} />
      <span className={`font-medium ${cfg.text}`}>{cfg.label}</span>
    </div>
  );
}

// ─── Stats tesis ──────────────────────────────────────────────────────────────
const STATS = [
  { icon: Globe,       value: "2.200+",      label: "Ciberataques diarios en el mundo" },
  { icon: ShieldCheck, value: "71%",         label: "Equipos de ciberseguridad usan OSINT" },
  { icon: Scale,       value: "Ley 21.719",  label: "Nueva Ley de Protección de Datos" },
  { icon: Search,      value: "USD 3.160M",  label: "Mercado OSINT proyectado 2033" },
];

// ─── Sección colapsable ───────────────────────────────────────────────────────
function Section({ title, icon, badge, children, defaultOpen = true }: {
  title: string; icon: React.ReactNode; badge?: string | number;
  children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card>
      <CardHeader
        className="py-3 px-5 cursor-pointer select-none"
        onClick={() => setOpen(!open)}
      >
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          {icon}
          {title}
          {badge !== undefined && (
            <Badge variant="secondary" className="ml-1 text-xs">{badge}</Badge>
          )}
          <span className="ml-auto text-muted-foreground">
            {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </span>
        </CardTitle>
      </CardHeader>
      {open && <CardContent className="px-5 pb-4 pt-0">{children}</CardContent>}
    </Card>
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
      setError("El backend no está disponible. Asegúrate de que corre en el puerto 8000.");
      return;
    }
    setLoading(true);
    setError(null);
    setOsint(null);

    try {
      const rutParam = rut.trim() ? `&rut=${encodeURIComponent(rut.trim())}` : '';
      const res = await fetch(
        `/api/osint?nombre=${encodeURIComponent(nombre.trim())}${rutParam}`,
        { signal: AbortSignal.timeout(25_000) }
      );
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.includes("application/json"))
        throw new Error(`Respuesta inesperada (HTTP ${res.status}). ¿Proxy de Vite configurado?`);
      const data: OSINTResponse = await res.json();
      if (!res.ok) throw new Error((data as { detail?: string }).detail ?? `Error ${res.status}`);
      setOsint(data);
      setQueryRealizada(data.query);
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "TimeoutError")
        setError("La búsqueda tardó demasiado (>25s). Intenta de nuevo.");
      else
        setError(e instanceof Error ? e.message : "Error desconocido.");
    } finally {
      setLoading(false);
    }
  };

  const f = osint?.fuentes;
  const r = osint?.resumen;

  return (
    <Layout>
      <div className="max-w-5xl mx-auto space-y-8">

        {/* ── Hero ────────────────────────────────────────────────────────── */}
        <div className="flex flex-col items-center text-center pt-8 space-y-4">
          <div className="relative">
            <div className="absolute -inset-6 rounded-full bg-primary/20 blur-3xl" />
            <Fingerprint className="relative h-16 w-16 text-primary" strokeWidth={1.5} />
          </div>
          <div className="space-y-1.5">
            <h1 className="text-3xl font-bold tracking-tight">OSINT Chile — Huella Digital</h1>
            <p className="text-muted-foreground text-sm max-w-lg">
              Plataforma de identificación y monitoreo de exposición de datos personales
              alineada con la <span className="text-primary font-medium">Ley N°21.719</span>
            </p>
          </div>
          <BackendIndicator status={backendStatus} />
        </div>

        {/* ── Stats ───────────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {STATS.map(({ icon: Icon, value, label }) => (
            <Card key={label} className="bg-card border-border">
              <CardContent className="pt-5 pb-4 text-center space-y-1.5">
                <Icon className="h-5 w-5 mx-auto text-primary" />
                <p className="text-lg font-bold leading-tight">{value}</p>
                <p className="text-[11px] text-muted-foreground leading-snug">{label}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        <Separator />

        {/* ── Buscador ────────────────────────────────────────────────────── */}
        <div className="space-y-3">
          <div>
            <h2 className="text-lg font-semibold">Rastrear huella digital</h2>
            <p className="text-xs text-muted-foreground">
              Consulta 6 fuentes públicas chilenas en paralelo: Rutificador · SERVEL · SII · Empresas · PJUD
            </p>
          </div>

          <div className="flex gap-2 max-w-2xl">
            <div className="relative flex-1">
              <Radar className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-primary" />
              <Input
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleBuscar()}
                placeholder="Nombre completo..."
                className="h-13 pl-12 pr-4 text-base rounded-xl bg-card border-border"
              />
            </div>

            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="icon" className="h-13 w-13 rounded-xl shrink-0">
                  <SlidersHorizontal className="h-5 w-5" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 space-y-5" align="end">
                <p className="text-sm font-semibold">Parámetros opcionales</p>
                <div className="space-y-3">
                  {[
                    { label: "RUT",   value: rut,   set: setRut,   ph: "12.345.678-9"     },
                    { label: "Email", value: email, set: setEmail, ph: "ejemplo@mail.com"  },
                    { label: "RRSS",  value: rrss,  set: setRrss,  ph: "@usuario"          },
                  ].map(({ label, value, set, ph }) => (
                    <div key={label} className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{label}</Label>
                      <Input value={value} onChange={(e) => set(e.target.value)} placeholder={ph} className="h-9" />
                    </div>
                  ))}
                </div>
                <div className="border-t border-border pt-4 space-y-3">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Alcance</p>
                  <div className="flex flex-wrap gap-x-4 gap-y-2">
                    {[["chile","Chile"],["intl","Internacional"],["darkweb","Dark Web"]].map(([id, lbl]) => (
                      <div key={id} className="flex items-center gap-1.5">
                        <Checkbox id={id} defaultChecked={id === "chile"} />
                        <Label htmlFor={id} className="text-xs font-normal">{lbl}</Label>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="border-t border-border pt-4 space-y-3">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Profundidad</p>
                  <RadioGroup value={profundidad} onValueChange={setProfundidad} className="space-y-1.5">
                    {[
                      { value: "rapida",   Icon: Zap,       label: "Rápida (~5 min)"  },
                      { value: "normal",   Icon: Timer,     label: "Normal (~15 min)" },
                      { value: "profunda", Icon: Telescope, label: "Profunda (~1h)"   },
                    ].map(({ value, Icon, label }) => (
                      <div key={value} className="flex items-center gap-2">
                        <RadioGroupItem value={value} id={value} />
                        <Icon className="h-3.5 w-3.5 text-primary" />
                        <Label htmlFor={value} className="text-xs font-normal">{label}</Label>
                      </div>
                    ))}
                  </RadioGroup>
                </div>
              </PopoverContent>
            </Popover>

            <Button
              disabled={!nombre.trim() || loading || backendStatus === "offline"}
              onClick={handleBuscar}
              className="h-13 px-6 rounded-xl text-base font-semibold shrink-0"
            >
              {loading
                ? <><Loader2 className="h-5 w-5 mr-2 animate-spin" />Buscando...</>
                : <><Eye className="h-5 w-5 mr-2" />Buscar</>}
            </Button>
          </div>
        </div>

        {/* ── Error ───────────────────────────────────────────────────────── */}
        {error && (
          <div className="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            ⚠️ {error}
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════════
            RESULTADOS OSINT
        ══════════════════════════════════════════════════════════════════ */}
        {osint && f && r && (
          <div className="space-y-4">

            {/* Resumen general */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-base font-semibold">
                  {r.total_hallazgos} hallazgo{r.total_hallazgos !== 1 ? "s" : ""} para{" "}
                  <span className="text-primary">"{queryRealizada}"</span>
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {r.fuentes_con_datos.join(" · ") || "Sin datos en ninguna fuente"}
                </p>
              </div>
              <div className="flex gap-2 flex-wrap">
                {(f.nryf_nombre?.length > 0 || f.nryf_rut) && <Badge className="bg-primary/80 text-white text-xs">✓ NRyF</Badge>}
                {r.inscrito_servel          && <Badge className="bg-blue-600 text-white text-xs">✓ SERVEL</Badge>}
                {r.tiene_actividad_empresarial && <Badge className="bg-amber-600 text-white text-xs">✓ Empresas</Badge>}
                {r.tiene_antecedentes_judiciales && <Badge className="bg-red-600 text-white text-xs">⚠ PJUD</Badge>}
                <Button variant="outline" size="sm" className="text-xs h-7"
                  onClick={() => navigate(`/dorks?nombre=${encodeURIComponent(queryRealizada)}`)}>
                  Ver Dorks →
                </Button>
                <Button variant="ghost" size="sm" className="text-xs h-7" onClick={() => setOsint(null)}>
                  Limpiar
                </Button>
              </div>
            </div>

            {/* ── NombreRutYFirma — búsqueda por nombre ───────────────────── */}
            {f.nryf_nombre?.length > 0 && (
              <Section title="NombreRutYFirma.com" icon={<Users className="h-4 w-4 text-primary" />} badge={f.nryf_nombre.length}>
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent border-border">
                      {["Nombre","RUT","Sexo","Dirección","Ciudad"].map(h => (
                        <TableHead key={h} className="text-muted-foreground text-xs uppercase tracking-wider">{h}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {f.nryf_nombre.map((p, i) => (
                      <TableRow key={i} className="border-border hover:bg-primary/5">
                        <TableCell className="font-medium">{p.nombre}</TableCell>
                        <TableCell className="font-mono text-sm">{p.rut}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">{p.sexo ?? "—"}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">{p.direccion ?? "—"}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">{p.ciudad ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Section>
            )}

            {/* ── NombreRutYFirma — resultado por RUT ─────────────────────── */}
            {f.nryf_rut && (
              <Section title="NombreRutYFirma.com — RUT" icon={<Users className="h-4 w-4 text-primary" />} badge={1}>
                <div className="rounded-lg border border-border p-4 space-y-1.5 text-sm">
                  <div className="flex items-center justify-between">
                    <p className="font-medium">{f.nryf_rut.nombre}</p>
                    <span className="font-mono text-xs text-muted-foreground">{f.nryf_rut.rut}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                    {f.nryf_rut.sexo      && <span>👤 {f.nryf_rut.sexo}</span>}
                    {f.nryf_rut.direccion && <span>📍 {f.nryf_rut.direccion}</span>}
                    {f.nryf_rut.ciudad    && <span>🏙 {f.nryf_rut.ciudad}</span>}
                  </div>
                </div>
              </Section>
            )}

            {/* ── SERVEL ──────────────────────────────────────────────────── */}
            {Object.keys(f.servel).length > 0 && (
              <Section title="SERVEL — Padrón Electoral" icon={<Vote className="h-4 w-4 text-blue-400" />} badge={Object.keys(f.servel).length}>
                {Object.entries(f.servel).map(([rut, s]) => (
                  <div key={rut} className="rounded-lg border border-border p-4 mb-3 last:mb-0 space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="font-medium text-sm">{s.nombre}</p>
                      <span className="font-mono text-xs text-muted-foreground">{rut}</span>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs text-muted-foreground">
                      {s.region          && <span>📍 {s.region}</span>}
                      {s.circunscripcion && <span>🗺 {s.circunscripcion}</span>}
                      {s.mesa            && <span>🗳 Mesa {s.mesa}</span>}
                      {s.local           && <span>🏫 {s.local}</span>}
                      {s.direccion_local && <span>📬 {s.direccion_local}</span>}
                    </div>
                  </div>
                ))}
              </Section>
            )}

            {/* ── SII ─────────────────────────────────────────────────────── */}
            {Object.keys(f.sii).length > 0 && (
              <Section title="SII — Estado Tributario" icon={<BadgeCheck className="h-4 w-4 text-amber-400" />} badge={Object.keys(f.sii).length}>
                {Object.entries(f.sii).map(([rut, s]) => (
                  <div key={rut} className="rounded-lg border border-border p-4 mb-3 last:mb-0 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <p className="font-medium text-sm">{s.nombre ?? "—"}</p>
                      <span className="font-mono text-xs text-muted-foreground">{rut}</span>
                    </div>
                    <div className="text-xs text-muted-foreground space-y-0.5">
                      {s.actividad          && <p>💼 {s.actividad}</p>}
                      {s.inicio_actividades && <p>📅 Inicio actividades: {s.inicio_actividades}</p>}
                      {s.contribuyente_iva  && <p>🧾 Contribuyente de IVA</p>}
                    </div>
                  </div>
                ))}
              </Section>
            )}

            {/* ── Empresas ────────────────────────────────────────────────── */}
            {f.empresas.length > 0 && (
              <Section title="Registro de Empresas y Sociedades" icon={<Building2 className="h-4 w-4 text-orange-400" />} badge={f.empresas.length}>
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent border-border">
                      {["Razón Social","RUT Empresa","Tipo","Estado"].map(h => (
                        <TableHead key={h} className="text-muted-foreground text-xs uppercase tracking-wider">{h}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {f.empresas.map((e, i) => (
                      <TableRow key={i} className="border-border hover:bg-primary/5">
                        <TableCell className="font-medium text-sm">{e.razon_social}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{e.rut_empresa ?? "—"}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">{e.tipo ?? "—"}</TableCell>
                        <TableCell>
                          <Badge variant={e.estado === "Vigente" ? "default" : "secondary"} className="text-xs">
                            {e.estado ?? "—"}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Section>
            )}

            {/* ── PJUD ────────────────────────────────────────────────────── */}
            {f.pjud.length > 0 && (
              <Section title="Poder Judicial — Causas Públicas" icon={<Gavel className="h-4 w-4 text-red-400" />} badge={f.pjud.length} defaultOpen={false}>
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent border-border">
                      {["Rol","Tribunal","Materia","Estado","Fecha"].map(h => (
                        <TableHead key={h} className="text-muted-foreground text-xs uppercase tracking-wider">{h}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {f.pjud.map((p, i) => (
                      <TableRow key={i} className="border-border hover:bg-primary/5">
                        <TableCell className="font-mono text-xs">{p.rol}</TableCell>
                        <TableCell className="text-sm">{p.tribunal}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">{p.materia ?? "—"}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">{p.estado ?? "—"}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">{p.fecha ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Section>
            )}

            {/* ── Diario Oficial ──────────────────────────────────────── */}
            {f.diario_oficial?.length > 0 && (
              <Section title="Diario Oficial" icon={<Globe className="h-4 w-4 text-cyan-400" />} badge={f.diario_oficial.length} defaultOpen={false}>
                <div className="space-y-3">
                  {f.diario_oficial.map((d, i) => (
                    <div key={i} className="border-b border-border pb-3 last:border-0">
                      <a href={d.url} target="_blank" rel="noopener noreferrer"
                         className="text-sm font-medium text-primary hover:underline flex items-center gap-1">
                        {d.titulo} <ExternalLink className="h-3 w-3" />
                      </a>
                      {d.descripcion && <p className="text-xs text-muted-foreground mt-1">{d.descripcion}</p>}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Sin resultados en ninguna fuente */}
            {r.total_hallazgos === 0 && (
              <div className="rounded-xl border border-border bg-card/50 px-6 py-10 text-center text-muted-foreground text-sm">
                No se encontraron datos en ninguna fuente para "{queryRealizada}"
              </div>
            )}
          </div>
        )}

        {/* ── Búsquedas recientes mock ─────────────────────────────────────── */}
        {!osint && !loading && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-muted-foreground">
              <History className="h-4 w-4" />
              <span className="text-sm font-medium uppercase tracking-wider">Búsquedas recientes</span>
            </div>
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent border-border">
                    {["Nombre","Fecha","Hallazgos","Riesgo"].map((h, i) => (
                      <TableHead key={h} className={`text-muted-foreground text-xs uppercase tracking-wider ${i === 2 ? "text-center" : ""}`}>{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mockSearches.map((s) => (
                    <TableRow key={s.id} className="cursor-pointer hover:bg-primary/5 transition-colors border-border"
                      onClick={() => navigate(`/resultados/${s.id}`)}>
                      <TableCell className="font-medium">{s.nombre}</TableCell>
                      <TableCell className="text-muted-foreground text-sm">{s.fecha}</TableCell>
                      <TableCell className="text-center">
                        <span className="flex items-center justify-center gap-1.5">
                          <Flame className="h-3.5 w-3.5 text-destructive" />{s.hallazgos}
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

        {/* ── Contexto tesis ──────────────────────────────────────────────── */}
        <div className="rounded-xl border border-border bg-card/40 p-5 space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Sobre esta plataforma</p>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Memoria de titulación que analiza el uso de{" "}
            <span className="text-foreground font-medium">OSINT</span> en ciberseguridad,
            con foco en Chile. Permite identificar y monitorear datos personales expuestos en fuentes
            públicas, alineándose con la{" "}
            <span className="text-primary font-medium">Ley N°21.719 de Protección de Datos Personales</span>.
          </p>
          <div className="flex flex-wrap gap-2">
            {["OSINT","Huella Digital","Ley 21.719","Ciberseguridad Chile","Data Brokers","Dark Web"].map(tag => (
              <Badge key={tag} variant="secondary" className="text-xs font-normal">{tag}</Badge>
            ))}
          </div>
        </div>

      </div>
    </Layout>
  );
};

export default Index;