import { useEffect, useState } from "react";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import {
  AlertTriangle, CheckCircle2, Mail, RefreshCw,
  Send, XCircle, ChevronDown, ChevronUp, Loader2,
  Clock, Building2, FileCheck,
} from "lucide-react";

// ── Tipos ────────────────────────────────────────────────────────────────────

interface Violation {
  id: string;
  baja_id: string;
  received_at: string;
  subject: string | null;
  from_address: string | null;
  snippet: string | null;
}

interface BajaRequest {
  id: string;
  dominio: string;
  empresa: string;
  estado: string;
  numero_solicitud: number;
  fecha_solicitud: string;
  fecha_limite: string;
  fecha_acuse: string | null;
  destinatario: string;
  dias_restantes: number | null;
  dias_en_mora: number | null;
  violations: Violation[];
  evidencia_json: string;
}

interface BajaGroup {
  dominio: string;
  empresa: string;
  estado_actual: string;
  numero_actual: number;
  ultima_solicitud: string;
  solicitudes: BajaRequest[];
  total_violations: number;
}

// ── Evento del flujo ──────────────────────────────────────────────────────────
// Refleja el diagrama: Solicitud → Respuesta empresa → Reincidencia → Nueva solicitud

type EventKind =
  | "solicitud"    // N°X enviada a la empresa
  | "respuesta"    // empresa respondió con evidencia de baja
  | "reincidencia" // correo recibido después de la baja (clickeable con detalle)
  | "espera"       // esperando respuesta
  | "vencida"      // plazo venció sin respuesta
  | "cumplida";    // empresa cumplió y no llegaron más correos

interface FlowEvent {
  kind: EventKind;
  date: string;
  label: string;
  sublabel?: string;
  numero?: number;
  // Datos de detalle (para panel expandible)
  detail?: {
    destinatario?: string;
    fecha_limite?: string;
    dias_restantes?: number | null;
    dias_en_mora?: number | null;
    violation?: Violation;
    violations?: Violation[];   // lista agrupada de reincidencias
    email_subject?: string;     // asunto del mail enviado
    email_to?: string;          // destinatario del mail
    email_body?: string;        // preview del cuerpo
  };
}

function buildEvents(solicitudes: BajaRequest[]): FlowEvent[] {
  const events: FlowEvent[] = [];

  // Deduplicar por numero_solicitud
  const seen = new Set<number>();
  const unique = solicitudes.filter((s) => {
    if (seen.has(s.numero_solicitud)) return false;
    seen.add(s.numero_solicitud);
    return true;
  });

  for (let i = 0; i < unique.length; i++) {
    const s = unique[i];
    const isLast = i === unique.length - 1;

    // 1. Solicitud enviada
    let evidencia: Record<string, string> = {};
    try { evidencia = JSON.parse(s.evidencia_json || "{}"); } catch { /* ignore */ }

    events.push({
      kind: "solicitud",
      date: s.fecha_solicitud,
      label: `Solicitud N°${s.numero_solicitud}`,
      sublabel: fmtDate(s.fecha_solicitud),
      numero: s.numero_solicitud,
      detail: {
        destinatario: s.destinatario,
        fecha_limite: s.fecha_limite,
        dias_restantes: s.dias_restantes,
        dias_en_mora: s.dias_en_mora,
        email_subject: evidencia.subject,
        email_to: evidencia.to,
        email_body: evidencia.body_preview,
      },
    });

    // 2. Respuesta empresa — solo si la empresa acusó recibo formalmente
    const respondio = s.fecha_acuse != null;
    if (respondio) {
      events.push({
        kind: "respuesta",
        date: s.fecha_acuse!,
        label: "Empresa respondió",
        sublabel: fmtDate(s.fecha_acuse!),
        detail: { destinatario: s.destinatario },
      });
    }

    // 3. Reincidencias agrupadas — UN solo evento con todas las violations
    if (s.violations.length > 0) {
      const sorted = [...s.violations].sort(
        (a, b) => new Date(a.received_at).getTime() - new Date(b.received_at).getTime()
      );
      const n = sorted.length;
      const firstDate = sorted[0].received_at;
      const lastDate = sorted[n - 1].received_at;

      const label = n === 1 ? "1 correo recibido" : `${n} correos recibidos`;
      const sublabel = n === 1
        ? fmtDate(firstDate)
        : `${fmtDateShort(firstDate)} – ${fmtDateShort(lastDate)}`;

      events.push({
        kind: "reincidencia",
        date: firstDate,
        label,
        sublabel,
        detail: { violations: sorted },
      });
    }

    // 4. Nodo terminal — solo en la última solicitud
    if (isLast) {
      if (s.estado === "CUMPLIDA") {
        // Con acuse formal = empresa cumplió; sin acuse = cierre por inactividad
        events.push({
          kind: "cumplida",
          date: s.fecha_acuse ?? s.fecha_solicitud,
          label: s.fecha_acuse ? "Empresa cumplió" : "Cierre por inactividad",
          sublabel: s.fecha_acuse ? undefined : "30 días sin actividad",
        });
      } else if (s.estado === "VENCIDA") {
        events.push({
          kind: "vencida",
          date: s.fecha_limite,
          label: "Plazo vencido",
          sublabel: s.dias_en_mora != null ? `${s.dias_en_mora}d en mora` : undefined,
          detail: { dias_en_mora: s.dias_en_mora, fecha_limite: s.fecha_limite },
        });
      } else {
        events.push({
          kind: "espera",
          date: s.fecha_limite,
          label: "En espera",
          sublabel: s.dias_restantes != null ? `${s.dias_restantes}d restantes` : undefined,
          detail: { fecha_limite: s.fecha_limite, dias_restantes: s.dias_restantes },
        });
      }
    }
  }

  events.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
  return events;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString("es-CL", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch { return iso.slice(0, 10); }
}

function fmtDateShort(iso: string) {
  try {
    return new Date(iso).toLocaleDateString("es-CL", {
      day: "2-digit", month: "short",
    });
  } catch { return iso.slice(0, 10); }
}

// ── Estado badge ──────────────────────────────────────────────────────────────

type EstadoKey = "SOLICITADA" | "VENCIDA" | "REINCIDENTE" | "CUMPLIDA";

const ESTADO: Record<EstadoKey, { label: string; dot: string; text: string }> = {
  SOLICITADA:  { label: "En espera",   dot: "bg-blue-500",    text: "text-blue-500" },
  VENCIDA:     { label: "Vencida",     dot: "bg-amber-500",   text: "text-amber-500" },
  REINCIDENTE: { label: "Reincidente", dot: "bg-red-500",     text: "text-red-500" },
  CUMPLIDA:    { label: "Cumplida",    dot: "bg-emerald-500", text: "text-emerald-500" },
};

const STEP_COLORS: Record<number, string> = {
  1: "bg-blue-500", 2: "bg-amber-500", 3: "bg-red-500",
};

// ── Config visual por tipo de evento ─────────────────────────────────────────

const BOX_CFG: Record<EventKind, {
  icon: React.ElementType;
  border: string;
  bg: string;
  iconBg: string;
  iconColor: string;
  titleCls: string;
  ringCls: string;
}> = {
  solicitud:    {
    icon: Send,
    border: "border-blue-500/30",    bg: "bg-blue-500/[0.05]",
    iconBg: "bg-blue-500/15",        iconColor: "text-blue-500",
    titleCls: "text-foreground font-semibold",
    ringCls: "ring-blue-500/50",
  },
  respuesta:    {
    icon: FileCheck,
    border: "border-emerald-500/30", bg: "bg-emerald-500/[0.04]",
    iconBg: "bg-emerald-500/15",     iconColor: "text-emerald-500",
    titleCls: "text-emerald-600 dark:text-emerald-400 font-medium",
    ringCls: "ring-emerald-500/50",
  },
  reincidencia: {
    icon: AlertTriangle,
    border: "border-red-500/30",     bg: "bg-red-500/[0.05]",
    iconBg: "bg-red-500/15",         iconColor: "text-red-500",
    titleCls: "text-red-500 font-semibold",
    ringCls: "ring-red-500/50",
  },
  espera:       {
    icon: Clock,
    border: "border-blue-400/20",    bg: "bg-blue-400/[0.03]",
    iconBg: "bg-blue-400/10",        iconColor: "text-blue-400",
    titleCls: "text-blue-400 font-medium",
    ringCls: "ring-blue-400/40",
  },
  cumplida:     {
    icon: CheckCircle2,
    border: "border-emerald-500/40", bg: "bg-emerald-500/[0.05]",
    iconBg: "bg-emerald-500/20",     iconColor: "text-emerald-500",
    titleCls: "text-emerald-600 dark:text-emerald-400 font-semibold",
    ringCls: "ring-emerald-500/50",
  },
  vencida:      {
    icon: XCircle,
    border: "border-amber-500/40",   bg: "bg-amber-500/[0.05]",
    iconBg: "bg-amber-500/15",       iconColor: "text-amber-500",
    titleCls: "text-amber-600 dark:text-amber-400 font-semibold",
    ringCls: "ring-amber-500/50",
  },
};

// ── Arrow ─────────────────────────────────────────────────────────────────────

function Arrow() {
  return (
    <div className="flex shrink-0 items-center self-center px-1 text-muted-foreground/25">
      <svg width="18" height="10" viewBox="0 0 18 10" fill="none">
        <path d="M0 5h14M10 1l5 4-5 4" stroke="currentColor" strokeWidth="1.4"
          strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

// ── Box clickeable ────────────────────────────────────────────────────────────

function StepBox({
  ev, selected, onClick,
}: {
  ev: FlowEvent;
  selected: boolean;
  onClick: () => void;
}) {
  const cfg = BOX_CFG[ev.kind];
  const Icon = cfg.icon;
  const hasDetail = !!ev.detail;

  return (
    <button
      onClick={hasDetail ? onClick : undefined}
      className={[
        "flex w-36 shrink-0 flex-col gap-1.5 rounded-xl border p-3 text-left transition-all",
        cfg.border, cfg.bg,
        hasDetail ? "cursor-pointer hover:brightness-110" : "cursor-default",
        selected ? `ring-2 ${cfg.ringCls}` : "",
      ].join(" ")}
    >
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1.5">
          <div className={`relative flex h-5 w-5 shrink-0 items-center justify-center rounded-md ${cfg.iconBg}`}>
            <Icon className={`h-3 w-3 ${cfg.iconColor}`} />
            {ev.kind === "reincidencia" && ev.detail?.violations && ev.detail.violations.length > 0 && (
              <span className="absolute -top-1.5 -right-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white leading-none">
                {ev.detail.violations.length}
              </span>
            )}
          </div>
          {ev.numero != null && (
            <span className={`text-[10px] font-bold ${cfg.iconColor}`}>N°{ev.numero}</span>
          )}
        </div>
        {hasDetail && (
          <span className="text-[9px] text-muted-foreground/30">ver</span>
        )}
      </div>
      <p className={`text-[11px] leading-tight ${cfg.titleCls} line-clamp-2`}>{ev.label}</p>
      {ev.sublabel && (
        <p className="text-[10px] leading-tight text-muted-foreground/45 tabular-nums">{ev.sublabel}</p>
      )}
    </button>
  );
}

// ── Panel de detalle ──────────────────────────────────────────────────────────

function DetailPanel({ ev }: { ev: FlowEvent }) {
  const d = ev.detail;
  if (!d) return null;
  const cfg = BOX_CFG[ev.kind];

  return (
    <div className={`mt-3 rounded-xl border ${cfg.border} ${cfg.bg} px-4 py-3 text-xs`}>
      {/* Solicitud */}
      {ev.kind === "solicitud" && (
        <div className="space-y-1.5">
          {d.email_to && <Row label="Enviada a" value={d.email_to} />}
          {!d.email_to && d.destinatario && <Row label="Enviada a" value={d.destinatario} />}
          {d.email_subject && <Row label="Asunto" value={d.email_subject} />}
          {d.fecha_limite && <Row label="Plazo legal" value={fmtDate(d.fecha_limite)} />}
          {d.dias_restantes != null && d.dias_restantes > 0 && (
            <Row label="Días restantes" value={`${d.dias_restantes} días`} />
          )}
          {d.dias_en_mora != null && d.dias_en_mora > 0 && (
            <Row label="Días en mora" value={`${d.dias_en_mora} días`} warn />
          )}
          {d.email_body && (
            <div className="mt-2 rounded-lg border border-border/30 bg-muted/20 px-3 py-2">
              <p className="text-[10px] text-muted-foreground/70 leading-relaxed line-clamp-5 whitespace-pre-wrap">
                {d.email_body}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Respuesta empresa */}
      {ev.kind === "respuesta" && (
        <div className="space-y-1.5">
          <Row label="Respondió" value={d.destinatario} />
          {ev.date && <Row label="Fecha" value={fmtDate(ev.date)} />}
          {d.email_body && (
            <div className="mt-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
              <p className="text-[10px] text-muted-foreground/60 leading-relaxed line-clamp-5 whitespace-pre-wrap">
                {d.email_body}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Reincidencia agrupada */}
      {ev.kind === "reincidencia" && d.violations && (
        <div className="space-y-2">
          <p className="text-[10px] font-semibold text-red-500/80 uppercase tracking-wide">
            {d.violations.length} correo{d.violations.length !== 1 ? "s" : ""} recibido{d.violations.length !== 1 ? "s" : ""} post-baja
          </p>
          <div className="divide-y divide-red-500/10">
            {d.violations.map((v) => (
              <div key={v.id} className="py-2 space-y-1">
                <div className="flex items-baseline gap-2">
                  <span className="w-28 shrink-0 text-[10px] text-muted-foreground/50">Recibido</span>
                  <span className="text-[11px] text-foreground/80 tabular-nums">{fmtDateShort(v.received_at)}</span>
                </div>
                {v.from_address && (
                  <div className="flex items-baseline gap-2">
                    <span className="w-28 shrink-0 text-[10px] text-muted-foreground/50">De</span>
                    <span className="text-[11px] font-mono text-muted-foreground">{v.from_address}</span>
                  </div>
                )}
                {v.subject && (
                  <div className="flex items-baseline gap-2">
                    <span className="w-28 shrink-0 text-[10px] text-muted-foreground/50">Asunto</span>
                    <span className="text-[11px] text-foreground/80">{v.subject}</span>
                  </div>
                )}
                {v.snippet && (
                  <div className="mt-1 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2">
                    <p className="text-[10px] text-muted-foreground/60 leading-relaxed line-clamp-3">
                      {v.snippet}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reincidencia individual (fallback) */}
      {ev.kind === "reincidencia" && d.violation && !d.violations && (
        <div className="space-y-1.5">
          <Row label="Recibido" value={fmtDateShort(d.violation.received_at)} />
          {d.violation.from_address && <Row label="De" value={d.violation.from_address} mono />}
          {d.violation.subject && <Row label="Asunto" value={d.violation.subject} />}
          {d.violation.snippet && (
            <div className="mt-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2">
              <p className="text-[10px] text-muted-foreground/60 leading-relaxed line-clamp-4">
                {d.violation.snippet}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Vencida */}
      {ev.kind === "vencida" && (
        <div className="space-y-1.5">
          {d.fecha_limite && <Row label="Plazo era" value={fmtDate(d.fecha_limite)} />}
          {d.dias_en_mora != null && <Row label="Días en mora" value={`${d.dias_en_mora} días`} warn />}
        </div>
      )}

      {/* En espera */}
      {ev.kind === "espera" && (
        <div className="space-y-1.5">
          {d.fecha_limite && <Row label="Plazo límite" value={fmtDate(d.fecha_limite)} />}
          {d.dias_restantes != null && (
            <Row label="Días restantes" value={`${d.dias_restantes} días`} />
          )}
        </div>
      )}
    </div>
  );
}

function Row({
  label, value, mono = false, warn = false,
}: {
  label: string; value?: string | null; mono?: boolean; warn?: boolean;
}) {
  if (!value) return null;
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-28 shrink-0 text-[10px] text-muted-foreground/50">{label}</span>
      <span className={[
        "text-[11px]",
        mono ? "font-mono text-muted-foreground" : "text-foreground/80",
        warn ? "text-amber-400" : "",
      ].join(" ")}>{value}</span>
    </div>
  );
}

// ── Flujo visual ──────────────────────────────────────────────────────────────

function FlowTimeline({ solicitudes }: { solicitudes: BajaRequest[] }) {
  const events = buildEvents(solicitudes);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

  const toggle = (i: number) => setSelectedIdx((prev) => prev === i ? null : i);
  const selected = selectedIdx !== null ? events[selectedIdx] : null;

  return (
    <div className="space-y-0">
      {/* Boxes + flechas */}
      <div className="overflow-x-auto pb-1">
        <div className="flex min-w-max items-start gap-0">
          {events.map((ev, i) => (
            <div key={i} className="flex items-center">
              <StepBox
                ev={ev}
                selected={selectedIdx === i}
                onClick={() => toggle(i)}
              />
              {i < events.length - 1 && <Arrow />}
            </div>
          ))}
        </div>
      </div>

      {/* Panel detalle */}
      {selected && selectedIdx !== null && (
        <DetailPanel ev={selected} />
      )}
    </div>
  );
}

// ── Card empresa ──────────────────────────────────────────────────────────────

function EmpresaCard({ g }: { g: BajaGroup }) {
  const [open, setOpen] = useState(false);
  const est = ESTADO[g.estado_actual as EstadoKey];
  const last = g.solicitudes[g.solicitudes.length - 1];

  return (
    <div className="overflow-hidden rounded-xl border border-border/60 bg-card">
      <button className="w-full text-left" onClick={() => setOpen((v) => !v)}>
        <div className="flex items-center gap-3 px-4 py-3">
          <div className={`h-2 w-2 shrink-0 rounded-full ${est?.dot ?? "bg-muted"}`} />

          <div className="flex-1 min-w-0">
            <span className="text-sm font-semibold">{g.empresa}</span>
            <span className="ml-2 font-mono text-[11px] text-muted-foreground/50">{g.dominio}</span>
          </div>

          <div className="flex shrink-0 items-center gap-2.5">
            {est && <span className={`text-xs font-medium ${est.text}`}>{est.label}</span>}

            {last?.estado === "SOLICITADA" && last.dias_restantes != null && (
              <span className="text-[11px] text-blue-400">{last.dias_restantes}d restantes</span>
            )}
            {last?.dias_en_mora != null && last.estado !== "CUMPLIDA" && (
              <span className="text-[11px] text-amber-400">{last.dias_en_mora}d en mora</span>
            )}

            <div className="flex gap-0.5">
              {[1, 2, 3].map((n) => (
                <div
                  key={n}
                  className={`h-1 w-4 rounded-full ${n <= g.numero_actual ? (STEP_COLORS[n] ?? "bg-red-500") : "bg-muted/30"}`}
                />
              ))}
            </div>

            {g.total_violations > 0 && (
              <span className="flex items-center gap-0.5 rounded-full bg-red-500/10 px-1.5 py-0.5 text-[10px] font-bold text-red-500">
                <AlertTriangle className="h-2.5 w-2.5" />
                {g.total_violations}
              </span>
            )}

            {open
              ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground/50" />
              : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground/50" />}
          </div>
        </div>
      </button>

      {open && (
        <div className="border-t border-border/40 bg-muted/[0.02] px-4 py-4">
          <FlowTimeline solicitudes={g.solicitudes} />
        </div>
      )}
    </div>
  );
}

// ── Página ────────────────────────────────────────────────────────────────────

export default function BajaHistorial() {
  const [groups, setGroups] = useState<BajaGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/baja/historial");
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
      setGroups(data.groups ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar.");
    } finally {
      setLoading(false);
    }
  };

  const seedDemo = async () => {
    setSeeding(true);
    try {
      const res = await fetch("/api/baja/poc/seed-demo", { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al crear demo.");
    } finally {
      setSeeding(false);
    }
  };

  useEffect(() => { load(); }, []);

  const total        = groups.length;
  const enEspera     = groups.filter((g) => g.estado_actual === "SOLICITADA").length;
  const reincidentes = groups.filter((g) => g.estado_actual === "REINCIDENTE").length;
  const cumplidas    = groups.filter((g) => g.estado_actual === "CUMPLIDA").length;
  const vencidas     = groups.filter((g) => g.estado_actual === "VENCIDA").length;

  return (
    <Layout>
      <div className="space-y-4 px-4 py-6 sm:px-6 lg:px-8">

        {/* header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold">Historial de Bajas</h1>
            <p className="text-xs text-muted-foreground">Solicitudes de supresión · Ley 21.719</p>
          </div>
          <div className="flex items-center gap-3">
            {!loading && total > 0 && (
              <div className="flex items-center divide-x divide-border/50 rounded-lg border border-border/50 bg-muted/10 px-3 py-1.5">
                {[
                  { v: total,        l: "total",     c: "text-foreground" },
                  { v: enEspera,     l: "espera",    c: "text-blue-500" },
                  { v: reincidentes, l: "reincid.",  c: "text-red-500" },
                  { v: vencidas,     l: "vencidas",  c: "text-amber-500" },
                  { v: cumplidas,    l: "cumplidas", c: "text-emerald-500" },
                ].map(({ v, l, c }) => (
                  <div key={l} className="px-3 text-center first:pl-0 last:pr-0">
                    <div className={`text-sm font-bold leading-none ${c}`}>{v}</div>
                    <div className="text-[10px] text-muted-foreground/60">{l}</div>
                  </div>
                ))}
              </div>
            )}
            <Button variant="outline" size="sm" onClick={seedDemo} disabled={seeding || loading}>
              {seeding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <span className="text-xs">Cargar demo</span>}
            </Button>
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>

        {loading && (
          <div className="space-y-1.5">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 animate-pulse rounded-xl bg-muted/20" />
            ))}
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-500">
            {error}
          </div>
        )}

        {!loading && !error && groups.length === 0 && (
          <div className="rounded-xl border border-border/40 bg-muted/10 py-14 text-center">
            <Mail className="mx-auto mb-2 h-7 w-7 text-muted-foreground/25" />
            <p className="text-sm text-muted-foreground">Sin solicitudes registradas</p>
            <p className="mt-1 text-xs text-muted-foreground/50">
              Presiona <strong>Cargar demo</strong> para ver ejemplos de cada estado del flujo
            </p>
          </div>
        )}

        {!loading && !error && groups.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {groups.map((g) => <EmpresaCard key={g.dominio} g={g} />)}
          </div>
        )}

        {/* leyenda */}
        {!loading && groups.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-0.5">
            {(["solicitud", "respuesta", "reincidencia", "espera", "cumplida", "vencida"] as EventKind[]).map((k) => {
              const cfg = BOX_CFG[k];
              const Icon = cfg.icon;
              const labels: Record<EventKind, string> = {
                solicitud:    "Solicitud enviada",
                respuesta:    "Empresa respondió",
                reincidencia: "Correo post-baja",
                espera:       "En espera",
                cumplida:     "Cumplida",
                vencida:      "Plazo vencido",
              };
              return (
                <div key={k} className="flex items-center gap-1 text-[10px] text-muted-foreground/50">
                  <div className={`flex h-3 w-3 shrink-0 items-center justify-center rounded-md ${cfg.iconBg}`}>
                    <Icon className={`h-1.5 w-1.5 ${cfg.iconColor}`} />
                  </div>
                  {labels[k]}
                </div>
              );
            })}
            <span className="text-[10px] text-muted-foreground/30 ml-1">· click en un paso para ver detalle</span>
          </div>
        )}

      </div>
    </Layout>
  );
}
