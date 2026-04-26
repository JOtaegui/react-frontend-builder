import { useEffect, useMemo, useState } from "react";
import { Layout } from "@/components/Layout";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Building2, Link2, Loader2, Network, Unlink2 } from "lucide-react";
import { useLocation } from "react-router-dom";

type ProviderMode = "manual" | "gmail";
type HeaderCriterion = "rango-cl-lacnic" | "rango-cl-csv" | "rdap" | "sin-datos";

interface HeaderIpDetail {
  ip: string;
  country?: string | null;
  is_chilean: boolean;
  criterion: HeaderCriterion;
}

interface EmailSenderHeaderView {
  company_name: string;
  primary_domain: string;
  sender_type: string;
  country: string;
  is_chilean: boolean;
  tags: string[];
  risk: {
    level: "low" | "medium" | "high";
    reasons: string[];
  };
  evidence: {
    message_count: number;
    from_addresses: string[];
    reply_to_addresses: string[];
    return_path_addresses: string[];
    auth_domains: string[];
    header_ips: string[];
    header_ip_countries: string[];
    header_ip_chile_matches: string[];
    header_ip_details?: HeaderIpDetail[];
  };
}

interface EmailHeadersResponse {
  provider: string;
  summary: {
    total_messages_analyzed: number;
    unique_companies: number;
  };
  senders: EmailSenderHeaderView[];
}

interface GmailOAuthPayload {
  access_token: string;
  email_address?: string;
}

interface GmailStatusResponse {
  configured: boolean;
  callback_origin?: string | null;
}

const READ_ALL_MESSAGES_LIMIT = "5000";
const defaultMessages = JSON.stringify(
  [
    {
      provider_message_id: "header-1",
      subject: "Aviso de seguridad",
      headers: [
        { name: "From", value: "BancoEstado <notificaciones@mail.bancoestado.cl>" },
        { name: "Reply-To", value: "soporte@bancoestado.cl" },
        { name: "Return-Path", value: "<bounce@mailer.bancoestado.cl>" },
        { name: "Authentication-Results", value: "spf=pass smtp.mailfrom=mailer.bancoestado.cl dkim=pass header.d=bancoestado.cl" },
        { name: "Received", value: "from mail.bancoestado.cl (mail.bancoestado.cl [190.98.241.10]) by mx.google.com" },
      ],
    },
    {
      provider_message_id: "header-2",
      subject: "Confirmacion de compra",
      headers: [
        { name: "From", value: "Retail Demo <notify@shop.demo.com>" },
        { name: "Reply-To", value: "help@shop.demo.com" },
        { name: "Authentication-Results", value: "spf=pass smtp.mailfrom=mailer.shop.demo.com dkim=pass header.d=shop.demo.com" },
        { name: "Received", value: "from mta.shop.demo.com (mta.shop.demo.com [34.120.20.5]) by mx.google.com" },
      ],
    },
  ],
  null,
  2,
);

function criterionBadgeVariant(criterion: HeaderCriterion) {
  if (criterion === "rango-cl-csv") return "default";
  if (criterion === "rango-cl-lacnic") return "secondary";
  if (criterion === "rdap") return "secondary";
  return "outline";
}

function criterionLabel(criterion: HeaderCriterion) {
  if (criterion === "rango-cl-csv") return "Rango CL CSV";
  if (criterion === "rango-cl-lacnic") return "Rango CL LACNIC";
  if (criterion === "rdap") return "RDAP";
  return "Sin datos";
}

function buildFallbackDetails(sender: EmailSenderHeaderView): HeaderIpDetail[] {
  return (sender.evidence.header_ips ?? []).map((ip) => {
    const chilean = (sender.evidence.header_ip_chile_matches ?? []).includes(ip);
    return {
      ip,
      country: chilean ? "Chile" : null,
      is_chilean: chilean,
      criterion: chilean ? "rango-cl-lacnic" : "sin-datos",
    };
  });
}

export default function CabecerasEmpresasTemp() {
  const location = useLocation();
  const [provider, setProvider] = useState<ProviderMode>("manual");
  const [gmailAuth, setGmailAuth] = useState<GmailOAuthPayload | null>(null);
  const [gmailConfigured, setGmailConfigured] = useState<boolean | null>(null);
  const [gmailCallbackOrigin, setGmailCallbackOrigin] = useState<string | null>(null);
  const [oauthLoading, setOauthLoading] = useState(false);
  const [emailAddress, setEmailAddress] = useState("");
  const [maxMessages, setMaxMessages] = useState("200");
  const [messagesJson, setMessagesJson] = useState(defaultMessages);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EmailHeadersResponse | null>(null);

  useEffect(() => {
    const navState = location.state as { prefilledResult?: EmailHeadersResponse; source?: string } | null;
    if (navState?.prefilledResult) {
      setResult(navState.prefilledResult);
    }
  }, [location.state]);

  const payloadPreview = useMemo(() => {
    try {
      const parsed = JSON.parse(messagesJson);
      return Array.isArray(parsed) ? `${parsed.length}` : "0";
    } catch {
      return "0";
    }
  }, [messagesJson]);

  const canAnalyze = provider === "gmail" ? Boolean(gmailAuth?.access_token) : payloadPreview !== "0";

  const companySenders = useMemo(
    () => [...(result?.senders ?? [])].sort((a, b) =>
      Number(b.is_chilean) - Number(a.is_chilean) ||
      ((b.evidence?.header_ip_chile_matches?.length ?? 0) - (a.evidence?.header_ip_chile_matches?.length ?? 0)) ||
      ((b.evidence?.message_count ?? 0) - (a.evidence?.message_count ?? 0)) ||
      a.company_name.localeCompare(b.company_name),
    ),
    [result],
  );

  const stats = useMemo(() => {
    const senders = result?.senders ?? [];
    const withHeaderIps = senders.filter((sender) => (sender.evidence?.header_ips?.length ?? 0) > 0).length;
    const withChileIps = senders.filter((sender) => (sender.evidence?.header_ip_chile_matches?.length ?? 0) > 0).length;
    const uniqueIps = new Set<string>();
    for (const sender of senders) {
      for (const ip of sender.evidence?.header_ips ?? []) uniqueIps.add(ip);
    }
    return {
      companies: senders.length,
      withHeaderIps,
      withChileIps,
      uniqueIps: uniqueIps.size,
    };
  }, [result]);

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
        max_messages: Number(maxMessages) || 200,
      };
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
      setError(err instanceof Error ? err.message : "No se pudo analizar cabeceras.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div className="mx-auto max-w-[1680px] space-y-6 px-2 sm:px-4 lg:px-6">
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Vista temporal: cabeceras por empresa</h1>
          <p className="mx-auto max-w-4xl text-sm text-muted-foreground sm:text-base">
            Pantalla temporal para revisar solo metadatos de cabeceras de correo agrupados por empresa.
          </p>
        </div>

        <Card className="border-emerald-500/25 bg-gradient-to-b from-emerald-400/15 via-background to-background shadow-[0_18px_60px_-30px_rgba(16,185,129,0.45)]">
          <CardContent className="space-y-6 p-6 sm:p-8">
            <div className="flex justify-center gap-2">
              <Button variant={provider === "manual" ? "default" : "outline"} onClick={() => setProvider("manual")}>Manual</Button>
              <Button variant={provider === "gmail" ? "default" : "outline"} onClick={() => setProvider("gmail")}>Gmail</Button>
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
                    placeholder={maxMessages === READ_ALL_MESSAGES_LIMIT ? "Leyendo todos los mensajes" : "200"}
                    className="h-12 flex-1 text-base"
                  />
                  {maxMessages === READ_ALL_MESSAGES_LIMIT && (
                    <Button type="button" variant="outline" onClick={() => setMaxMessages("200")} className="h-12 sm:w-auto">
                      Usar limite manual
                    </Button>
                  )}
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
                    <Label htmlFor="messagesJson">Mensajes (cabeceras)</Label>
                    <span className="text-xs text-muted-foreground">{payloadPreview} mensajes</span>
                  </div>
                  <Textarea
                    id="messagesJson"
                    value={messagesJson}
                    onChange={(event) => setMessagesJson(event.target.value)}
                    className="min-h-[280px] font-mono text-xs"
                  />
                </div>
              )}

              <Button onClick={handleAnalyze} disabled={loading || !canAnalyze} className="h-14 w-full bg-emerald-500 text-base text-white hover:bg-emerald-600">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Network className="h-4 w-4" />}
                Analizar cabeceras
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
                { label: "Empresas", value: stats.companies, icon: Building2 },
                { label: "Con IP en cabecera", value: stats.withHeaderIps, icon: Network },
                { label: "IPs unicas", value: stats.uniqueIps, icon: Link2 },
                { label: "Empresas con IP Chile", value: stats.withChileIps, icon: Network },
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
              <CardHeader>
                <CardTitle className="text-xl">Analisis de cabeceras por empresa (mismo listado)</CardTitle>
              </CardHeader>
              <CardContent className="p-3 sm:p-5">
                <Accordion type="multiple" className="w-full">
                  {companySenders.map((sender, index) => {
                    const headerDetails = (sender.evidence.header_ip_details ?? []).length > 0
                      ? sender.evidence.header_ip_details ?? []
                      : buildFallbackDetails(sender);

                    return (
                      <AccordionItem
                        key={`${sender.company_name}-${sender.primary_domain}`}
                        value={`${sender.company_name}-${sender.primary_domain}`}
                        className="mb-4 overflow-hidden rounded-3xl border border-emerald-500/15 bg-background/80 px-4 shadow-[0_16px_45px_-38px_rgba(16,185,129,0.7)] backdrop-blur-sm"
                      >
                        <AccordionTrigger className="py-5 hover:no-underline">
                          <div className="flex min-w-0 flex-1 items-center justify-between gap-4 pr-4 text-left">
                            <div className="min-w-0">
                              <div className="truncate text-lg font-semibold sm:text-xl">
                                #{index + 1} {sender.company_name}
                              </div>
                              <div className="truncate text-sm text-muted-foreground">
                                {sender.primary_domain} · {sender.sender_type} · {sender.is_chilean ? "Chile" : sender.country}
                              </div>
                            </div>
                            <div className="flex shrink-0 flex-wrap gap-2">
                              <Badge variant={sender.is_chilean ? "default" : "outline"} className={sender.is_chilean ? "bg-emerald-500 text-white hover:bg-emerald-500/90" : ""}>
                                {sender.is_chilean ? "Empresa chilena" : "Empresa no chilena"}
                              </Badge>
                              <Badge variant="outline">{sender.evidence.message_count} correos</Badge>
                              <Badge variant="secondary">{headerDetails.length} IPs</Badge>
                              <Badge variant="outline">{(sender.evidence.header_ip_chile_matches ?? []).length} IPs Chile</Badge>
                            </div>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent className="space-y-4 pb-5">
                          <div className="grid gap-4 lg:grid-cols-2">
                            <div className="rounded-2xl border border-emerald-500/12 bg-background/80 p-4">
                              <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Direcciones de envio</div>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {[...(sender.evidence.from_addresses ?? []), ...(sender.evidence.reply_to_addresses ?? []), ...(sender.evidence.return_path_addresses ?? [])]
                                  .filter((value, index, array) => array.indexOf(value) === index)
                                  .slice(0, 12)
                                  .map((address) => (
                                    <Badge key={address} variant="outline" className="border-emerald-500/25 bg-background/80 font-mono text-xs">
                                      {address}
                                    </Badge>
                                  ))}
                              </div>
                              {(sender.evidence.auth_domains ?? []).length > 0 && (
                                <div className="mt-4">
                                  <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Dominios de autenticacion</div>
                                  <div className="mt-2 flex flex-wrap gap-2">
                                    {(sender.evidence.auth_domains ?? []).map((domain) => (
                                      <Badge key={domain} variant="outline" className="border-emerald-500/25 text-xs">
                                        {domain}
                                      </Badge>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>

                            <div className="rounded-2xl border border-emerald-500/12 bg-background/80 p-4">
                              <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">Riesgo</div>
                              <div className="mt-3 flex items-center gap-2">
                                <Badge variant="outline">{sender.risk.level}</Badge>
                                {(sender.tags ?? []).slice(0, 4).map((tag) => (
                                  <Badge key={tag} variant="secondary">{tag}</Badge>
                                ))}
                              </div>
                              {(sender.risk.reasons ?? []).length > 0 && (
                                <div className="mt-3 rounded-xl border border-emerald-500/12 bg-emerald-500/[0.04] px-3 py-2 text-xs text-muted-foreground">
                                  {sender.risk.reasons[0]}
                                </div>
                              )}
                            </div>
                          </div>

                          <div className="rounded-2xl border border-emerald-500/12 bg-background/80 p-4">
                            <div className="mb-3 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">IPs en cabeceras</div>
                            {headerDetails.length === 0 ? (
                              <p className="text-sm text-muted-foreground">No se detectaron IPs publicas en cabeceras para esta empresa.</p>
                            ) : (
                              <div className="space-y-2">
                                {headerDetails.map((detail) => (
                                  <div key={detail.ip} className="flex flex-col gap-2 rounded-xl border border-emerald-500/12 bg-emerald-500/[0.04] px-3 py-2 text-xs sm:flex-row sm:items-center sm:justify-between">
                                    <div className="font-mono text-sm">{detail.ip}</div>
                                    <div className="flex flex-wrap items-center gap-2">
                                      <Badge variant="outline">{detail.country ?? "desconocido"}</Badge>
                                      <Badge variant={criterionBadgeVariant(detail.criterion)} className={detail.criterion === "rango-cl-lacnic" ? "bg-emerald-500 text-white hover:bg-emerald-500/90" : ""}>
                                        {criterionLabel(detail.criterion)}
                                      </Badge>
                                      {detail.is_chilean && (
                                        <Badge variant="secondary" className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                                          Chile
                                        </Badge>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    );
                  })}
                </Accordion>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </Layout>
  );
}
