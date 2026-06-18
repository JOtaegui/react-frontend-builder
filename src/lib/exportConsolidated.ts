// Exporta la vista consolidada a un Excel multi-hoja, en formato tidy/pivotable
// para facilitar gráficos de comparación entre empresas y el análisis académico.
import * as XLSX from "xlsx";

export interface ExportConfirmedDatum {
  tipo: string;
  tipo_key?: string;
  valores: string[];
  evidencia?: string;
}

export interface ExportCompany {
  company_name: string;
  primary_domain: string;
  sources: Array<"email" | "browser">;
  personal_names: string[];
  personal_ruts: string[];
  personal_addresses: string[];
  personal_phones: string[];
  personal_plates: string[];
  confirmed_data: ExportConfirmedDatum[];
  autofill_hints: ExportConfirmedDatum[];
  probable_data_types: string[];
  personal_data_types: string[];
  risk_level: "low" | "medium" | "high";
  sender_type: string;
  is_chilean: boolean;
  country: string;
  confidence: number;
  personal_data_confidence: number;
  email_message_count: number;
  email_spam_count: number;
  email_header_ips: string[];
  email_header_ip_chile_matches: string[];
  email_from_addresses: string[];
  email_reply_to_addresses: string[];
  email_return_path_addresses: string[];
  email_sample_subjects: string[];
  email_attachment_filenames: string[];
  browser_visit_count: number;
  browser_login_detected: boolean;
  browser_signup_detected: boolean;
  browser_checkout_detected: boolean;
  browser_last_visit: string | null;
}

export interface ExportProfilePoint {
  value: string;
  sources?: number;
  confidence?: number;
  confidence_level?: string;
  alternatives?: Array<{ value: string }>;
}

export interface ExportProfile {
  name?: ExportProfilePoint | null;
  rut?: ExportProfilePoint | null;
  address?: ExportProfilePoint | null;
  phone?: ExportProfilePoint | null;
  plate?: ExportProfilePoint | null;
}

export interface BreachStatus {
  inHibp: boolean;
  inCl: boolean;
  breachNames: string[];
}

export interface ExportArgs {
  companies: ExportCompany[];
  profile: ExportProfile | null;
  holderEmail: string;
  emailAddress: string | null;
  breachOf: (company: ExportCompany) => BreachStatus;
}

const yesNo = (value: boolean): string => (value ? "Sí" : "No");

const sourceLabel = (sources: Array<"email" | "browser">): string => {
  const email = sources.includes("email");
  const browser = sources.includes("browser");
  if (email && browser) return "ambos";
  if (email) return "email";
  if (browser) return "browser";
  return "—";
};

const riskScoreNum = (risk: string): number => (risk === "high" ? 3 : risk === "medium" ? 2 : 1);
const pct = (value?: number): number | "" => (typeof value === "number" ? Math.round(value * 100) : "");
const joinList = (values?: string[]): string => (values && values.length ? values.join(" | ") : "");

const totalPersonalData = (c: ExportCompany): number =>
  c.personal_names.length +
  c.personal_ruts.length +
  c.personal_addresses.length +
  c.personal_phones.length +
  c.personal_plates.length +
  c.confirmed_data.reduce((acc, d) => acc + (d.valores?.length ?? 0), 0);

// Crea una hoja desde objetos; si está vacía, mantiene los encabezados.
function sheetFromRows(rows: Record<string, unknown>[], headers: string[]): XLSX.WorkSheet {
  if (rows.length === 0) return XLSX.utils.aoa_to_sheet([headers]);
  return XLSX.utils.json_to_sheet(rows, { header: headers });
}

export function exportConsolidatedToExcel(args: ExportArgs): void {
  const { companies, profile, holderEmail, emailAddress, breachOf } = args;
  const wb = XLSX.utils.book_new();

  // ── 1) Resumen ──────────────────────────────────────────────────────────
  const onlyEmail = companies.filter((c) => sourceLabel(c.sources) === "email").length;
  const onlyBrowser = companies.filter((c) => sourceLabel(c.sources) === "browser").length;
  const both = companies.filter((c) => sourceLabel(c.sources) === "ambos").length;
  const withPii = companies.filter((c) => totalPersonalData(c) > 0).length;
  const breached = companies.filter((c) => {
    const b = breachOf(c);
    return b.inHibp || b.inCl;
  }).length;

  const resumen = XLSX.utils.aoa_to_sheet([
    ["EmailAnalyzer — Exposición consolidada"],
    [],
    ["Generado", new Date().toLocaleString("es-CL")],
    ["Cuenta analizada (Gmail)", emailAddress ?? "—"],
    ["Titular", holderEmail || "—"],
    [],
    ["Total empresas", companies.length],
    ["Solo correo", onlyEmail],
    ["Solo navegador", onlyBrowser],
    ["En ambos (correo + navegador)", both],
    ["Con datos personales", withPii],
    ["Con filtración (HIBP o CL)", breached],
  ]);
  XLSX.utils.book_append_sheet(wb, resumen, "Resumen");

  // ── 2) Perfil consolidado ───────────────────────────────────────────────
  const perfilHeaders = ["tipo", "valor", "n_fuentes", "confianza_pct", "nivel", "alternativas"];
  const perfilRows: Record<string, unknown>[] = [];
  const addPoint = (tipo: string, p?: ExportProfilePoint | null) => {
    if (!p || !p.value) return;
    perfilRows.push({
      tipo,
      valor: p.value,
      n_fuentes: p.sources ?? "",
      confianza_pct: pct(p.confidence),
      nivel: p.confidence_level ?? "",
      alternativas: (p.alternatives ?? []).map((a) => a.value).join(" | "),
    });
  };
  addPoint("nombre", profile?.name);
  addPoint("rut", profile?.rut);
  addPoint("direccion", profile?.address);
  addPoint("telefono", profile?.phone);
  addPoint("patente", profile?.plate);
  XLSX.utils.book_append_sheet(wb, sheetFromRows(perfilRows, perfilHeaders), "Perfil consolidado");

  // ── 3) Empresas (1 fila por empresa, columnas comparables para gráficos) ──
  const empresaHeaders = [
    "empresa", "dominio", "fuente", "tipo_remitente", "pais", "es_chileno",
    "riesgo", "riesgo_score", "confianza_pct", "confianza_datos_pct",
    "n_correos", "n_spam", "visitas_browser", "login", "registro", "checkout", "ultima_visita",
    "n_nombres", "n_ruts", "n_direcciones", "n_telefonos", "n_patentes", "total_datos_personales",
    "tipos_datos", "n_ips_cabecera", "n_ips_chile",
    "filtrada", "filtrada_hibp", "filtrada_cl", "brechas",
  ];
  const empresaRows = companies.map((c) => {
    const b = breachOf(c);
    return {
      empresa: c.company_name,
      dominio: c.primary_domain,
      fuente: sourceLabel(c.sources),
      tipo_remitente: c.sender_type,
      pais: c.country,
      es_chileno: yesNo(c.is_chilean),
      riesgo: c.risk_level,
      riesgo_score: riskScoreNum(c.risk_level),
      confianza_pct: pct(c.confidence),
      confianza_datos_pct: pct(c.personal_data_confidence),
      n_correos: c.email_message_count,
      n_spam: c.email_spam_count,
      visitas_browser: c.browser_visit_count,
      login: yesNo(c.browser_login_detected),
      registro: yesNo(c.browser_signup_detected),
      checkout: yesNo(c.browser_checkout_detected),
      ultima_visita: c.browser_last_visit ?? "",
      n_nombres: c.personal_names.length,
      n_ruts: c.personal_ruts.length,
      n_direcciones: c.personal_addresses.length,
      n_telefonos: c.personal_phones.length,
      n_patentes: c.personal_plates.length,
      total_datos_personales: totalPersonalData(c),
      tipos_datos: joinList(c.personal_data_types),
      n_ips_cabecera: c.email_header_ips.length,
      n_ips_chile: c.email_header_ip_chile_matches.length,
      filtrada: yesNo(b.inHibp || b.inCl),
      filtrada_hibp: yesNo(b.inHibp),
      filtrada_cl: yesNo(b.inCl),
      brechas: joinList(b.breachNames),
    };
  });
  XLSX.utils.book_append_sheet(wb, sheetFromRows(empresaRows, empresaHeaders), "Empresas");

  // ── 4) Datos personales (tidy: 1 fila por empresa·tipo·valor) ────────────
  const piiHeaders = ["empresa", "dominio", "fuente", "tipo", "valor", "origen"];
  const piiRows: Record<string, unknown>[] = [];
  const pushPii = (c: ExportCompany, tipo: string, valor: string, origen: string) => {
    piiRows.push({ empresa: c.company_name, dominio: c.primary_domain, fuente: sourceLabel(c.sources), tipo, valor, origen });
  };
  for (const c of companies) {
    c.personal_names.forEach((v) => pushPii(c, "nombre", v, "correo"));
    c.personal_ruts.forEach((v) => pushPii(c, "rut", v, "correo"));
    c.personal_addresses.forEach((v) => pushPii(c, "direccion", v, "correo"));
    c.personal_phones.forEach((v) => pushPii(c, "telefono", v, "correo"));
    c.personal_plates.forEach((v) => pushPii(c, "patente", v, "correo"));
    c.confirmed_data.forEach((d) => (d.valores ?? []).forEach((v) => pushPii(c, d.tipo, v, "navegador")));
  }
  XLSX.utils.book_append_sheet(wb, sheetFromRows(piiRows, piiHeaders), "Datos personales");

  // ── 5) Cabeceras (IPs) — hoja aparte ─────────────────────────────────────
  const ipHeaders = ["empresa", "dominio", "ip", "ip_en_chile"];
  const ipRows: Record<string, unknown>[] = [];
  for (const c of companies) {
    const chile = new Set(c.email_header_ip_chile_matches.map((x) => x.trim()));
    for (const ip of c.email_header_ips) {
      ipRows.push({ empresa: c.company_name, dominio: c.primary_domain, ip, ip_en_chile: yesNo(chile.has(ip.trim())) });
    }
  }
  XLSX.utils.book_append_sheet(wb, sheetFromRows(ipRows, ipHeaders), "Cabeceras (IPs)");

  // ── 6) Dominios — dominio + fuente (email/browser/ambos) ─────────────────
  const domHeaders = ["dominio", "empresa", "fuente"];
  const domRows = companies.map((c) => ({
    dominio: c.primary_domain,
    empresa: c.company_name,
    fuente: sourceLabel(c.sources),
  }));
  XLSX.utils.book_append_sheet(wb, sheetFromRows(domRows, domHeaders), "Dominios");

  // ── 7) Filtraciones ──────────────────────────────────────────────────────
  const breachHeaders = ["empresa", "dominio", "filtrada", "hibp", "cl", "brechas"];
  const breachRows = companies.map((c) => {
    const b = breachOf(c);
    return {
      empresa: c.company_name,
      dominio: c.primary_domain,
      filtrada: yesNo(b.inHibp || b.inCl),
      hibp: yesNo(b.inHibp),
      cl: yesNo(b.inCl),
      brechas: joinList(b.breachNames),
    };
  });
  XLSX.utils.book_append_sheet(wb, sheetFromRows(breachRows, breachHeaders), "Filtraciones");

  // ── 8) Evidencia (tidy: asuntos, adjuntos, from/reply-to/return-path) ────
  const evHeaders = ["empresa", "dominio", "tipo", "valor"];
  const evRows: Record<string, unknown>[] = [];
  const pushEv = (c: ExportCompany, tipo: string, valores: string[]) => {
    valores.forEach((v) => evRows.push({ empresa: c.company_name, dominio: c.primary_domain, tipo, valor: v }));
  };
  for (const c of companies) {
    pushEv(c, "asunto", c.email_sample_subjects);
    pushEv(c, "adjunto", c.email_attachment_filenames);
    pushEv(c, "from", c.email_from_addresses);
    pushEv(c, "reply_to", c.email_reply_to_addresses);
    pushEv(c, "return_path", c.email_return_path_addresses);
  }
  XLSX.utils.book_append_sheet(wb, sheetFromRows(evRows, evHeaders), "Evidencia");

  // ── Descargar ─────────────────────────────────────────────────────────────
  const stamp = new Date().toISOString().slice(0, 10);
  XLSX.writeFile(wb, `exposicion_consolidada_${stamp}.xlsx`);
}
