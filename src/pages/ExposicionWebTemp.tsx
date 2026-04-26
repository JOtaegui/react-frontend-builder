import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Building2, ExternalLink, FileSearch, Loader2, Mail, Scale, Telescope } from "lucide-react";

interface BreachEntry {
  source: string;
  data_types: string[];
  breach_date?: string | null;
}

interface HibpResult {
  email: string;
  breaches: BreachEntry[];
  pwned: boolean;
}

interface EmailEntry {
  email: string;
  url?: string;
  fuente?: string;
  contexto?: string;
}

interface EmpresaEntry {
  razon_social: string;
  rut_empresa?: string;
  tipo?: string;
  estado?: string;
}

interface PjudEntry {
  rol: string;
  tribunal: string;
  materia?: string;
  estado?: string;
  fecha?: string;
}

interface DiarioOficialEntry {
  titulo: string;
  url: string;
  descripcion?: string;
}

interface OSINTResponse {
  query: string;
  rut?: string;
  search_id?: string | null;
  fuentes: {
    emails_publicos: EmailEntry[];
    empresas: EmpresaEntry[];
    pjud: PjudEntry[];
    diario_oficial: DiarioOficialEntry[];
    hibp?: HibpResult[];
  };
  resumen: {
    total_hallazgos: number;
    fuentes_con_datos: string[];
    total_leaks?: number;
    emails_encontrados: string[];
    advertencia?: string | null;
  };
}

interface NavigationState {
  source?: string;
  prefilledIdentity?: {
    nombre?: string;
    rut?: string;
    email?: string;
  };
}

function hasEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export default function ExposicionWebTemp() {
  const navigate = useNavigate();
  const location = useLocation();

  const navState = (location.state as NavigationState | null) ?? null;
  const [nombre, setNombre] = useState("");
  const [rut, setRut] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OSINTResponse | null>(null);
  const [autoRunDone, setAutoRunDone] = useState(false);

  useEffect(() => {
    const identity = navState?.prefilledIdentity;
    if (!identity) return;
    setNombre((identity.nombre ?? "").trim());
    setRut((identity.rut ?? "").trim());
    setEmail((identity.email ?? "").trim());
  }, [navState?.prefilledIdentity]);

  const canSearch = nombre.trim().length >= 2;

  const runSearch = async (override?: { nombre?: string; rut?: string; email?: string }) => {
    const nombreValue = (override?.nombre ?? nombre).trim();
    const rutValue = (override?.rut ?? rut).trim();
    const emailValue = (override?.email ?? email).trim();
    if (nombreValue.length < 2) return;

    setLoading(true);
    setError(null);
    try {
      const rutParam = rutValue ? `&rut=${encodeURIComponent(rutValue)}` : "";
      const emailParam = hasEmail(emailValue) ? `&email=${encodeURIComponent(emailValue)}` : "";
      const response = await fetch(
        `/api/osint?nombre=${encodeURIComponent(nombreValue)}${rutParam}${emailParam}`,
        { signal: AbortSignal.timeout(120_000) },
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo completar la búsqueda web.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (autoRunDone) return;
    const identity = navState?.prefilledIdentity;
    if (!identity?.nombre || identity.nombre.trim().length < 2) return;
    setAutoRunDone(true);
    void runSearch({
      nombre: identity.nombre,
      rut: identity.rut ?? "",
      email: identity.email ?? "",
    });
  }, [autoRunDone, navState?.prefilledIdentity]);

  const leaksCount = useMemo(() => {
    if (!result?.fuentes?.hibp) return 0;
    return result.fuentes.hibp.reduce((acc, item) => acc + (item.breaches?.length ?? 0), 0);
  }, [result]);

  return (
    <Layout>
      <div className="mx-auto max-w-[1600px] space-y-6 px-2 sm:px-4 lg:px-6">
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Vista temporal: exposición web</h1>
          <p className="mx-auto max-w-3xl text-sm text-muted-foreground sm:text-base">
            Búsqueda web usando nombre, RUT y correo detectados en la investigación. Se ignoran dirección y patente por ahora.
          </p>
        </div>

        <Card className="border-emerald-500/20 bg-gradient-to-br from-emerald-400/10 via-background to-emerald-500/[0.04]">
          <CardContent className="space-y-4 p-6">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="nombre">Nombre</Label>
                <Input id="nombre" value={nombre} onChange={(event) => setNombre(event.target.value)} placeholder="Nombre completo" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="rut">RUT</Label>
                <Input id="rut" value={rut} onChange={(event) => setRut(event.target.value)} placeholder="12.345.678-9" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Correo</Label>
                <Input id="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="persona@correo.cl" />
              </div>
            </div>

            <div className="flex flex-wrap justify-end gap-3">
              <Button variant="outline" onClick={() => navigate("/identificacion-email")}>
                Volver a investigación
              </Button>
              <Button onClick={() => runSearch()} disabled={loading || !canSearch} className="bg-emerald-500 text-white hover:bg-emerald-600">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Telescope className="h-4 w-4" />}
                Buscar datos en la web
              </Button>
            </div>

            {error && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}
          </CardContent>
        </Card>

        {result && (
          <div className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <Card className="border-emerald-500/20">
                <CardContent className="p-6">
                  <FileSearch className="mb-4 h-5 w-5 text-emerald-500" />
                  <div className="text-3xl font-semibold">{result.resumen.total_hallazgos ?? 0}</div>
                  <div className="mt-2 text-sm text-muted-foreground">Hallazgos web</div>
                </CardContent>
              </Card>
              <Card className="border-emerald-500/20">
                <CardContent className="p-6">
                  <Mail className="mb-4 h-5 w-5 text-emerald-500" />
                  <div className="text-3xl font-semibold">{result.fuentes.emails_publicos?.length ?? 0}</div>
                  <div className="mt-2 text-sm text-muted-foreground">Correos públicos</div>
                </CardContent>
              </Card>
              <Card className="border-emerald-500/20">
                <CardContent className="p-6">
                  <Building2 className="mb-4 h-5 w-5 text-emerald-500" />
                  <div className="text-3xl font-semibold">{result.fuentes.empresas?.length ?? 0}</div>
                  <div className="mt-2 text-sm text-muted-foreground">Empresas relacionadas</div>
                </CardContent>
              </Card>
              <Card className="border-emerald-500/20">
                <CardContent className="p-6">
                  <Scale className="mb-4 h-5 w-5 text-emerald-500" />
                  <div className="text-3xl font-semibold">{leaksCount}</div>
                  <div className="mt-2 text-sm text-muted-foreground">Brechas detectadas</div>
                </CardContent>
              </Card>
            </div>

            {result.search_id && (
              <div className="flex justify-end">
                <Button variant="outline" onClick={() => navigate(`/resultados/${result.search_id}`)}>
                  <ExternalLink className="h-4 w-4" />
                  Ver resultado OSINT completo
                </Button>
              </div>
            )}

            <Card className="border-emerald-500/20">
              <CardHeader>
                <CardTitle>Fuentes con datos</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {(result.resumen.fuentes_con_datos ?? []).map((fuente) => (
                    <Badge key={fuente} variant="secondary" className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                      {fuente}
                    </Badge>
                  ))}
                </div>
                {result.resumen.advertencia && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                    {result.resumen.advertencia}
                  </div>
                )}
              </CardContent>
            </Card>

            <div className="grid gap-5 xl:grid-cols-2">
              <Card className="border-emerald-500/20">
                <CardHeader>
                  <CardTitle>Correos públicos encontrados</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {(result.fuentes.emails_publicos ?? []).length === 0 ? (
                    <div className="text-sm text-muted-foreground">No se encontraron correos públicos asociados.</div>
                  ) : (
                    (result.fuentes.emails_publicos ?? []).slice(0, 20).map((item) => (
                      <div key={`${item.email}-${item.url ?? item.fuente ?? "sin-fuente"}`} className="rounded-xl border border-emerald-500/12 bg-emerald-500/[0.04] p-3">
                        <div className="font-medium">{item.email}</div>
                        <div className="text-xs text-muted-foreground">{item.fuente ?? "fuente no especificada"}</div>
                        {item.url && (
                          <a href={item.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-emerald-700 hover:underline dark:text-emerald-300">
                            Ver fuente <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card className="border-emerald-500/20">
                <CardHeader>
                  <CardTitle>Empresas y causas públicas</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {(result.fuentes.empresas ?? []).slice(0, 10).map((item) => (
                    <div key={`${item.razon_social}-${item.rut_empresa ?? ""}`} className="rounded-xl border border-emerald-500/12 bg-emerald-500/[0.04] p-3">
                      <div className="font-medium">{item.razon_social}</div>
                      <div className="text-xs text-muted-foreground">
                        {item.rut_empresa ? `RUT empresa: ${item.rut_empresa}` : "RUT empresa no disponible"}
                        {item.estado ? ` · ${item.estado}` : ""}
                      </div>
                    </div>
                  ))}

                  {(result.fuentes.pjud ?? []).slice(0, 8).map((item) => (
                    <div key={`${item.rol}-${item.tribunal}`} className="rounded-xl border border-emerald-500/12 bg-background p-3">
                      <div className="text-sm font-medium">{item.rol}</div>
                      <div className="text-xs text-muted-foreground">{item.tribunal}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {item.materia ?? "materia no informada"} {item.estado ? `· ${item.estado}` : ""}
                      </div>
                    </div>
                  ))}

                  {(result.fuentes.empresas ?? []).length === 0 && (result.fuentes.pjud ?? []).length === 0 && (
                    <div className="text-sm text-muted-foreground">No se detectaron empresas ni causas públicas relevantes.</div>
                  )}
                </CardContent>
              </Card>
            </div>

            <Card className="border-emerald-500/20">
              <CardHeader>
                <CardTitle>Diario Oficial y brechas</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {(result.fuentes.diario_oficial ?? []).slice(0, 8).map((item) => (
                  <div key={item.url} className="rounded-xl border border-emerald-500/12 bg-background p-3">
                    <div className="text-sm font-medium">{item.titulo}</div>
                    {item.descripcion && <div className="mt-1 text-xs text-muted-foreground">{item.descripcion}</div>}
                    <a href={item.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-emerald-700 hover:underline dark:text-emerald-300">
                      Abrir publicación <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                ))}

                {(result.fuentes.hibp ?? []).length > 0 && (
                  <div className="space-y-2">
                    {(result.fuentes.hibp ?? []).map((item) => (
                      <div key={item.email} className="rounded-xl border border-emerald-500/12 bg-emerald-500/[0.04] p-3">
                        <div className="text-sm font-medium">{item.email}</div>
                        <div className="text-xs text-muted-foreground">
                          {item.pwned ? `${item.breaches?.length ?? 0} brechas asociadas` : "Sin brechas asociadas"}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {(result.fuentes.diario_oficial ?? []).length === 0 && (result.fuentes.hibp ?? []).length === 0 && (
                  <div className="text-sm text-muted-foreground">No se detectaron publicaciones o brechas adicionales.</div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </Layout>
  );
}
