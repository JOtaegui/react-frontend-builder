import { useEffect, useMemo, useState } from "react";
import { useParams, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SearchFilter } from "@/components/SearchFilter";
import { Users, Mail, Database, Loader2, SearchX, Building2 } from "lucide-react";

interface NRYFEntry {
  nombre: string;
  rut: string;
  sexo?: string;
  direccion?: string;
  ciudad?: string;
}

interface EmailEntry {
  email: string;
  url?: string;
  fuente?: string;
  contexto?: string;
  confidence?: number;
  match_type?: string;
  existence_status?: string;
  institutional_domain?: string;
  domain_category?: string;
}

interface InstitucionEntry {
  nombre: string;
  confidence?: number;
  source_type?: string;
  fuente?: string;
  url?: string;
  contexto?: string;
}

interface SearchDetailResponse {
  id: string;
  nombre: string;
  rut?: string | null;
  fecha: string;
  riesgo: string;
  risk_score: number;
  hallazgos: number;
  fuentes: number;
  resultado: {
    query: string;
    rut?: string | null;
    search_id?: string | null;
    fuentes?: {
      nryf_nombre?: NRYFEntry[];
      emails_publicos?: EmailEntry[];
      instituciones_relacionadas?: InstitucionEntry[];
    };
    resumen?: {
      total_hallazgos?: number;
      fuentes_con_datos?: string[];
      advertencia?: string;
      emails_encontrados?: string[];
    };
  };
}

export default function Resultados() {
  const { id } = useParams();
  const [filter, setFilter] = useState("");
  const [data, setData] = useState<SearchDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const cargar = async () => {
      if (!id) {
        setNotFound(true);
        setLoading(false);
        return;
      }

      try {
        const res = await fetch(`/api/searches/${id}`, {
          signal: AbortSignal.timeout(15000),
        });
        if (res.status === 404) {
          if (!cancelled) setNotFound(true);
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload: SearchDetailResponse = await res.json();
        if (!cancelled) setData(payload);
      } catch {
        if (!cancelled) setNotFound(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void cargar();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const q = filter.toLowerCase();
  const nryf = useMemo(
    () => (data?.resultado.fuentes?.nryf_nombre ?? []).filter((item) =>
      [item.nombre, item.rut, item.sexo ?? "", item.direccion ?? "", item.ciudad ?? ""]
        .some((value) => value.toLowerCase().includes(q))
    ),
    [data, q],
  );
  const emails = useMemo(
    () => (data?.resultado.fuentes?.emails_publicos ?? []).filter((item) =>
      [item.email, item.fuente ?? "", item.contexto ?? "", item.url ?? ""]
        .some((value) => value.toLowerCase().includes(q))
    ),
    [data, q],
  );
  const confirmedEmails = useMemo(
    () => emails.filter((item) => item.existence_status === "published" && item.match_type !== "generated"),
    [emails],
  );
  const candidateEmails = useMemo(
    () => emails.filter((item) => item.existence_status !== "published" || item.match_type === "generated"),
    [emails],
  );
  const instituciones = useMemo(
    () => (data?.resultado.fuentes?.instituciones_relacionadas ?? []).filter((item) =>
      [item.nombre, item.fuente ?? "", item.contexto ?? "", item.url ?? ""]
        .some((value) => value.toLowerCase().includes(q))
    ),
    [data, q],
  );

  if (notFound) return <Navigate to="/" replace />;

  return (
    <Layout>
      <div className="max-w-6xl mx-auto space-y-6">
        {loading ? (
          <div className="py-20 text-center space-y-3">
            <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Cargando resultado guardado...</p>
          </div>
        ) : !data ? (
          <div className="py-20 text-center space-y-3">
            <SearchX className="h-8 w-8 mx-auto text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">No se pudo cargar el resultado.</p>
          </div>
        ) : (
          <>
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold">{data.nombre}</h2>
                <p className="text-sm text-muted-foreground">
                  {data.fecha} · {data.hallazgos} hallazgos · {data.fuentes} fuentes
                </p>
                {(data.resultado.resumen?.fuentes_con_datos?.length ?? 0) > 0 && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {data.resultado.resumen?.fuentes_con_datos?.join(" · ")}
                  </p>
                )}
              </div>
              <div className="w-full md:w-80">
                <SearchFilter value={filter} onChange={setFilter} placeholder="Filtrar NRYF o emails..." />
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { icon: Database, label: "Hallazgos", value: data.hallazgos },
                { icon: Users, label: "Registros NRYF", value: data.resultado.fuentes?.nryf_nombre?.length ?? 0 },
                { icon: Mail, label: "Emails públicos", value: confirmedEmails.length },
                { icon: Building2, label: "Instituciones", value: data.resultado.fuentes?.instituciones_relacionadas?.length ?? 0 },
                { icon: Mail, label: "Emails totales", value: data.resultado.resumen?.emails_encontrados?.length ?? 0 },
              ].map((item) => (
                <Card key={item.label}>
                  <CardContent className="pt-6 text-center">
                    <item.icon className="h-6 w-6 mx-auto mb-2 text-primary" />
                    <p className="text-2xl font-bold">{item.value}</p>
                    <p className="text-xs text-muted-foreground">{item.label}</p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {data.resultado.resumen?.advertencia && (
              <div className="px-4 py-3 rounded-lg border border-amber-500/20 bg-amber-500/5 text-sm text-amber-200">
                {data.resultado.resumen?.advertencia}
              </div>
            )}

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Resultados NRYF
                </CardTitle>
              </CardHeader>
              <CardContent>
                {nryf.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No hay resultados NRYF para esta búsqueda.</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Nombre</TableHead>
                        <TableHead>RUT</TableHead>
                        <TableHead>Sexo</TableHead>
                        <TableHead>Dirección</TableHead>
                        <TableHead>Ciudad</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {nryf.map((item, idx) => (
                        <TableRow key={`${item.rut}-${idx}`}>
                          <TableCell className="font-medium">{item.nombre}</TableCell>
                          <TableCell className="font-mono text-xs">{item.rut}</TableCell>
                          <TableCell>{item.sexo ?? "—"}</TableCell>
                          <TableCell>{item.direccion ?? "—"}</TableCell>
                          <TableCell>{item.ciudad ?? "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Building2 className="h-5 w-5" />
                  Instituciones Relacionadas
                </CardTitle>
              </CardHeader>
              <CardContent>
                {instituciones.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Aún no se identificaron instituciones asociadas.</p>
                ) : (
                  <div className="space-y-3">
                    {instituciones.map((item, idx) => (
                      <div key={`${item.nombre}-${idx}`} className="rounded-lg border border-border p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium">{item.nombre}</span>
                          {typeof item.confidence === "number" && (
                            <span className="text-[11px] text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                              conf. {Math.round(item.confidence * 100)}%
                            </span>
                          )}
                          {item.source_type && (
                            <span className="text-[11px] text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded-full">
                              {item.source_type}
                            </span>
                          )}
                          {item.fuente && (
                            <span className="text-[11px] text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                              {item.fuente}
                            </span>
                          )}
                        </div>
                        {item.contexto && (
                          <p className="text-xs text-muted-foreground mt-2">{item.contexto}</p>
                        )}
                        {item.url && (
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-primary hover:underline mt-2 inline-block"
                          >
                            Ver fuente
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Mail className="h-5 w-5" />
                  Emails Confirmados en Web
                </CardTitle>
              </CardHeader>
              <CardContent>
                {confirmedEmails.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Aún no se encontraron emails públicos confirmados con fuente.</p>
                ) : (
                  <div className="space-y-3">
                    {confirmedEmails.map((item, idx) => (
                      <div key={`${item.email}-${idx}`} className="rounded-lg border border-border p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <a href={`mailto:${item.email}`} className="font-mono text-sm hover:text-primary transition-colors">
                            {item.email}
                          </a>
                          <span className={`text-[11px] border px-2 py-0.5 rounded-full ${
                            item.existence_status === "published"
                              ? "text-emerald-300 border-emerald-500/30"
                              : "text-amber-300 border-amber-500/30"
                          }`}>
                            {item.existence_status === "published" ? "existe/publicado" : "no confirmado"}
                          </span>
                          {typeof item.confidence === "number" && (
                            <span className="text-[11px] text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                              conf. {Math.round(item.confidence * 100)}%
                            </span>
                          )}
                          {item.match_type && (
                            <span className="text-[11px] text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                              {item.match_type}
                            </span>
                          )}
                          {item.fuente && (
                            <span className="text-[11px] text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                              {item.fuente}
                            </span>
                          )}
                          {item.institutional_domain && (
                            <span className="text-[11px] text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded-full">
                              dominio institucional: {item.institutional_domain}
                            </span>
                          )}
                          {item.domain_category && !item.institutional_domain && (
                            <span className="text-[11px] text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                              {item.domain_category}
                            </span>
                          )}
                        </div>
                        {item.contexto && (
                          <p className="text-xs text-muted-foreground mt-2">{item.contexto}</p>
                        )}
                        {item.url && (
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-primary hover:underline mt-2 inline-block"
                          >
                            Ver fuente
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Mail className="h-5 w-5" />
                  Posibles Correos
                </CardTitle>
              </CardHeader>
              <CardContent>
                {candidateEmails.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No hay candidatos generados para esta búsqueda.</p>
                ) : (
                  <div className="space-y-3">
                    {candidateEmails.map((item, idx) => (
                      <div key={`${item.email}-${idx}`} className="rounded-lg border border-border p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-sm">{item.email}</span>
                          <span className="text-[11px] text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded-full">
                            no confirmado
                          </span>
                          {typeof item.confidence === "number" && (
                            <span className="text-[11px] text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                              conf. {Math.round(item.confidence * 100)}%
                            </span>
                          )}
                          {item.match_type && (
                            <span className="text-[11px] text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                              {item.match_type}
                            </span>
                          )}
                          {item.fuente && (
                            <span className="text-[11px] text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                              {item.fuente}
                            </span>
                          )}
                          {item.domain_category && (
                            <span className="text-[11px] text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                              {item.domain_category}
                            </span>
                          )}
                        </div>
                        {item.contexto && (
                          <p className="text-xs text-muted-foreground mt-2">{item.contexto}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </Layout>
  );
}
