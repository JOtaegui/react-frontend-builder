import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Fingerprint, Mail, Chrome, LayoutDashboard, ShieldCheck, CheckCircle2,
  Lock, Eye, ArrowRight, Loader2, AlertTriangle, Target,
} from "lucide-react";
import {
  LS_EMAIL_RESULT, LS_BROWSER_RESULT,
  connectGmailPopup, runEmailFootprint, saveEmailResult,
  runBrowserHistory, saveBrowserResult, getSystemInfo,
} from "@/lib/analysis";

const BROWSER_LABELS: Record<string, string> = {
  chrome: "Google Chrome",
  safari: "Safari",
  brave: "Brave",
  edge: "Microsoft Edge",
  firefox: "Firefox",
  "chrome-canary": "Chrome Canary",
};

type Phase = "idle" | "connecting" | "running" | "done" | "error";

function readDone() {
  try {
    return {
      email:   Boolean(localStorage.getItem(LS_EMAIL_RESULT)),
      browser: Boolean(localStorage.getItem(LS_BROWSER_RESULT)),
    };
  } catch {
    return { email: false, browser: false };
  }
}

export default function Inicio() {
  const navigate = useNavigate();

  // Estado del paso de correo
  const [emailPhase, setEmailPhase] = useState<Phase>("idle");
  const [emailMsg, setEmailMsg]     = useState<string>("");

  // Datos de búsqueda opcionales para afinar el análisis de correo
  const [searchTargets, setSearchTargets] = useState({
    nombre: "", rut: "", direccion: "", telefono: "", patente: "",
  });
  const updateTarget = (field: keyof typeof searchTargets, value: string) =>
    setSearchTargets((prev) => ({ ...prev, [field]: value }));
  const filledTargets = Object.values(searchTargets).filter((v) => v.trim()).length;

  // Estado del paso de navegación
  const [browser, setBrowser]         = useState("chrome");
  const [browserOptions, setBrowserOptions] = useState<string[]>(Object.keys(BROWSER_LABELS));
  const [browserPhase, setBrowserPhase] = useState<Phase>("idle");
  const [browserMsg, setBrowserMsg]     = useState<string>("");

  const [done, setDone] = useState(readDone);

  // Marcar pasos ya hechos en visitas anteriores
  useEffect(() => {
    const d = readDone();
    setDone(d);
    if (d.email) setEmailPhase("done");
    if (d.browser) setBrowserPhase("done");
  }, []);

  // Detectar SO y navegadores instalados para ofrecer solo los disponibles
  useEffect(() => {
    getSystemInfo()
      .then(info => {
        if (info.available_browsers?.length) {
          setBrowserOptions(info.available_browsers);
          setBrowser(info.available_browsers[0]);
        }
      })
      .catch(() => { /* se mantiene la lista por defecto */ });
  }, []);

  // ── Paso 1: conectar Gmail y analizar todos los correos ───────────────────
  async function handleEmail() {
    setEmailPhase("connecting");
    setEmailMsg("Abriendo Google para autorizar el acceso…");
    try {
      const auth = await connectGmailPopup();
      setEmailPhase("running");
      setEmailMsg("Analizando tus correos… esto puede tardar varios minutos.");
      const normalizedTargets = Object.fromEntries(
        Object.entries(searchTargets)
          .map(([key, value]) => [key, value.trim()])
          .filter(([, value]) => Boolean(value)),
      ) as Record<string, string>;
      const data = await runEmailFootprint(auth.access_token, {
        searchTargets: normalizedTargets,
        onProgress: (processed, total, stage) => {
          const label = stage || "Analizando correos";
          setEmailMsg(
            total > 1
              ? `${label}… ${processed.toLocaleString()} de ${total.toLocaleString()}`
              : `${label}…`,
          );
        },
      });
      saveEmailResult(data, auth.email_address ?? "");
      const n = data.senders?.length ?? 0;
      setEmailPhase("done");
      setEmailMsg(`${n} empresa${n === 1 ? "" : "s"} detectada${n === 1 ? "" : "s"} en tu correo.`);
      setDone(d => ({ ...d, email: true }));
    } catch (err) {
      setEmailPhase("error");
      setEmailMsg(err instanceof Error ? err.message : "No se pudo completar el análisis.");
    }
  }

  // ── Paso 2: analizar el navegador elegido ──────────────────────────────────
  async function handleBrowser() {
    setBrowserPhase("running");
    setBrowserMsg(`Analizando el historial de ${BROWSER_LABELS[browser] ?? browser}…`);
    try {
      const data = await runBrowserHistory(browser);
      saveBrowserResult(data);
      const n = data.companies?.length ?? 0;
      setBrowserPhase("done");
      setBrowserMsg(`${n} empresa${n === 1 ? "" : "s"} detectada${n === 1 ? "" : "s"} en tu navegación.`);
      setDone(d => ({ ...d, browser: true }));
    } catch (err) {
      setBrowserPhase("error");
      setBrowserMsg(err instanceof Error ? err.message : "No se pudo analizar el navegador.");
    }
  }

  const analyzed = done.email || done.browser;
  const emailBusy = emailPhase === "connecting" || emailPhase === "running";
  const browserBusy = browserPhase === "running";

  function statusRow(phase: Phase, msg: string) {
    if (!msg) return null;
    const isErr = phase === "error";
    const isDone = phase === "done";
    return (
      <div className={`mt-2 flex items-center gap-1.5 text-xs ${isErr ? "text-red-600 dark:text-red-400" : isDone ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`}>
        {(phase === "connecting" || phase === "running") && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        {isDone && <CheckCircle2 className="h-3.5 w-3.5" />}
        {isErr && <AlertTriangle className="h-3.5 w-3.5" />}
        <span>{msg}</span>
      </div>
    );
  }

  return (
    <Layout>
      <div className="mx-auto max-w-3xl space-y-8 p-6">

        {/* Encabezado */}
        <div className="space-y-3 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/80 to-primary shadow-md">
            <Fingerprint className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">Descubre y controla tu huella digital</h1>
          <p className="mx-auto max-w-xl text-sm text-muted-foreground">
            En tres pasos identificas qué organizaciones tienen tus datos personales, dimensionas el
            riesgo y ejerces tu derecho a la supresión según la Ley N°21.719.
          </p>
        </div>

        {/* Garantía de privacidad */}
        <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.06] px-5 py-3 text-xs text-emerald-700 dark:text-emerald-300">
          <span className="flex items-center gap-1.5"><Lock className="h-3.5 w-3.5" /> Todo se procesa en tu equipo</span>
          <span className="flex items-center gap-1.5"><Eye className="h-3.5 w-3.5" /> Acceso de solo lectura</span>
          <span className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> Puedes revocar el acceso cuando quieras</span>
        </div>

        <div className="space-y-4">

          {/* Paso 1 — Correo */}
          <Card className={`overflow-hidden transition-all ${done.email ? "border-emerald-500/30" : ""}`}>
            <CardContent className="flex items-center gap-4 p-5">
              <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-400 to-violet-600 text-white shadow">
                {done.email ? <CheckCircle2 className="h-6 w-6" /> : <Mail className="h-5 w-5" />}
                <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-background text-[11px] font-bold text-foreground shadow ring-1 ring-border">1</span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold">Conecta tu correo</h3>
                  {done.email && <Badge className="bg-emerald-500/15 text-[10px] text-emerald-700 dark:text-emerald-300">Completado</Badge>}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  Conecta tu Gmail y analizamos todos tus mensajes para identificar qué empresas te
                  escriben y qué datos personales tuyos manejan.
                </p>
                <Dialog>
                  <DialogTrigger asChild>
                    <Button type="button" variant="outline" size="sm" className="mt-2 h-8 gap-1.5 text-xs">
                      <Target className="h-3.5 w-3.5 text-emerald-500" />
                      Datos de búsqueda (opcional)
                      {filledTargets > 0 && (
                        <Badge className="ml-0.5 bg-emerald-500 px-1.5 text-[10px] text-white hover:bg-emerald-500/90">
                          {filledTargets}
                        </Badge>
                      )}
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                      <DialogTitle>Datos de búsqueda</DialogTitle>
                      <DialogDescription>
                        Opcional. Si los completas, el análisis prioriza las coincidencias de tu nombre,
                        RUT, dirección, teléfono o patente dentro de los correos.
                      </DialogDescription>
                    </DialogHeader>
                    <div className="grid gap-3 py-2">
                      <div className="space-y-1.5">
                        <Label htmlFor="homeNombre" className="text-xs text-muted-foreground">Nombre</Label>
                        <Input id="homeNombre" value={searchTargets.nombre} onChange={(e) => updateTarget("nombre", e.target.value)} placeholder="Nombre Apellido" className="h-10 text-sm" />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="homeRut" className="text-xs text-muted-foreground">RUT</Label>
                        <Input id="homeRut" value={searchTargets.rut} onChange={(e) => updateTarget("rut", e.target.value)} placeholder="12.345.678-9" className="h-10 text-sm" />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="homeDireccion" className="text-xs text-muted-foreground">Dirección</Label>
                        <Input id="homeDireccion" value={searchTargets.direccion} onChange={(e) => updateTarget("direccion", e.target.value)} placeholder="Av. Apoquindo 4501, Las Condes" className="h-10 text-sm" />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="homeTelefono" className="text-xs text-muted-foreground">Teléfono</Label>
                        <Input id="homeTelefono" value={searchTargets.telefono} onChange={(e) => updateTarget("telefono", e.target.value)} placeholder="+56 9 1234 5678" className="h-10 text-sm" />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="homePatente" className="text-xs text-muted-foreground">Patente</Label>
                        <Input id="homePatente" value={searchTargets.patente} onChange={(e) => updateTarget("patente", e.target.value.toUpperCase())} placeholder="ABCD12" className="h-10 text-sm" />
                      </div>
                    </div>
                    <DialogFooter>
                      <DialogClose asChild>
                        <Button type="button" className="w-full bg-emerald-500 text-white hover:bg-emerald-600">Listo</Button>
                      </DialogClose>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
                {statusRow(emailPhase, emailMsg)}
              </div>
              <Button onClick={handleEmail} disabled={emailBusy} className="shrink-0 gap-1.5">
                {emailBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {done.email ? "Volver a analizar" : "Conectar Gmail"}
              </Button>
            </CardContent>
          </Card>

          {/* Paso 2 — Navegación */}
          <Card className={`overflow-hidden transition-all ${done.browser ? "border-emerald-500/30" : ""}`}>
            <CardContent className="flex items-center gap-4 p-5">
              <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-white shadow">
                {done.browser ? <CheckCircle2 className="h-6 w-6" /> : <Chrome className="h-5 w-5" />}
                <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-background text-[11px] font-bold text-foreground shadow ring-1 ring-border">2</span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold">Analiza tu navegador</h3>
                  <Badge variant="secondary" className="text-[10px]">Opcional</Badge>
                  {done.browser && <Badge className="bg-emerald-500/15 text-[10px] text-emerald-700 dark:text-emerald-300">Completado</Badge>}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  Elige tu navegador y revisamos tu historial local para detectar empresas con las
                  que tienes cuenta, compras o registros.
                </p>
                {statusRow(browserPhase, browserMsg)}
              </div>
              <div className="flex shrink-0 flex-col items-stretch gap-2">
                <Select value={browser} onValueChange={setBrowser} disabled={browserBusy}>
                  <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {browserOptions.map(b => (
                      <SelectItem key={b} value={b}>{BROWSER_LABELS[b] ?? b}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button onClick={handleBrowser} disabled={browserBusy} variant={done.browser ? "outline" : "default"} className="gap-1.5">
                  {browserBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {done.browser ? "Volver a analizar" : "Analizar"}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Paso 3 — Exposición */}
          <Card className={`overflow-hidden transition-all ${analyzed ? "hover:shadow-md" : "opacity-60"}`}>
            <CardContent className="flex items-center gap-4 p-5">
              <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 text-white shadow">
                <LayoutDashboard className="h-5 w-5" />
                <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-background text-[11px] font-bold text-foreground shadow ring-1 ring-border">3</span>
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold">Revisa tu exposición y actúa</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Vemos en un solo lugar qué empresas tienen tus datos, cuáles han sufrido
                  filtraciones y desde ahí puedes solicitar la baja.
                </p>
              </div>
              <Button onClick={() => navigate("/consolidado")} disabled={!analyzed} className="shrink-0 gap-1.5">
                Ver mi exposición <ArrowRight className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Accesos secundarios */}
        <div className="flex flex-wrap items-center justify-center gap-2 pt-2 text-sm">
          <Button variant="ghost" size="sm" onClick={() => navigate("/identificacion-email")} className="gap-1.5 text-muted-foreground">
            <Mail className="h-4 w-4" /> Ver detalle del correo
          </Button>
          <span className="text-muted-foreground/40">·</span>
          <Button variant="ghost" size="sm" onClick={() => navigate("/baja-historial")} className="gap-1.5 text-muted-foreground">
            <ShieldCheck className="h-4 w-4" /> Solicitudes de baja
          </Button>
        </div>
      </div>
    </Layout>
  );
}
