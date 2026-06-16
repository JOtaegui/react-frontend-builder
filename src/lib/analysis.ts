// analysis.ts — Lógica compartida de análisis (correo y navegación) y su
// persistencia en localStorage. Usado tanto por la página de Inicio (flujo
// guiado) como por las vistas dedicadas, para no duplicar la lógica ni que los
// resultados queden desincronizados entre vistas.

// ── Claves de localStorage (deben coincidir en todas las vistas) ─────────────
export const LS_EMAIL_RESULT     = "email_footprint_result";
export const LS_EMAIL_HOLDER     = "email_footprint_holder";
export const LS_CROSSREF_DOMAINS = "email_crossref_domains";
export const LS_CROSSREF_SENDERS = "email_crossref_senders";
export const LS_CROSSREF_TS      = "email_crossref_ts";
export const LS_BROWSER_RESULT   = "browser_history_result";

// "Leer todos los mensajes" — tope alto para cubrir buzones grandes. El backend
// pagina la API de Gmail (500 por página) y no impone un límite rígido.
export const READ_ALL_MESSAGES = 25000;

interface GmailPayload { access_token: string; email_address?: string | null; }

// ── Conexión a Gmail por popup OAuth ─────────────────────────────────────────
// Abre el popup de Google y resuelve cuando el callback hace postMessage.
// IMPORTANTE: el window.open debe ser lo PRIMERO y SÍNCRONO dentro del gesto del
// usuario (el clic). Si hay un await antes, el navegador bloquea el popup.
export function connectGmailPopup(): Promise<GmailPayload> {
  const popup = window.open(
    "/api/auth/gmail/start",
    "gmail-oauth",
    "popup=yes,width=540,height=720,resizable=yes,scrollbars=yes",
  );

  return new Promise(async (resolve, reject) => {
    if (!popup) {
      reject(new Error("No se pudo abrir la ventana de Google. Permite las ventanas emergentes para este sitio e inténtalo de nuevo."));
      return;
    }

    // El origen del callback se consulta DESPUÉS de abrir el popup (el OAuth
    // tarda segundos, hay tiempo de sobra para registrar el listener antes).
    let callbackOrigin: string | null = null;
    try {
      const r = await fetch("/api/auth/gmail/status", { signal: AbortSignal.timeout(8000) });
      const d = await r.json();
      callbackOrigin = d.callback_origin ?? null;
    } catch { /* seguimos con el origen actual */ }

    const allowed = new Set([window.location.origin, callbackOrigin].filter(Boolean) as string[]);
    let settled = false;

    const cleanup = () => {
      window.removeEventListener("message", onMessage);
      clearInterval(closedTimer);
    };
    const onMessage = (event: MessageEvent) => {
      if (allowed.size > 0 && !allowed.has(event.origin)) return;
      if (event.data?.type === "gmail-oauth-success") {
        settled = true; cleanup();
        resolve(event.data.payload as GmailPayload);
      } else if (event.data?.type === "gmail-oauth-error") {
        settled = true; cleanup();
        reject(new Error(event.data.message ?? "No se pudo conectar Gmail."));
      }
    };
    window.addEventListener("message", onMessage);

    // Si el usuario cierra el popup sin autorizar.
    const closedTimer = setInterval(() => {
      if (popup.closed && !settled) {
        cleanup();
        reject(new Error("Conexión cancelada."));
      }
    }, 700);
  });
}

// ── Análisis de correo (trabajo en segundo plano, no expira) ─────────────────
// Inicia el trabajo en el backend y sondea su estado en peticiones cortas, en
// lugar de una sola petición larga que el navegador aborta por timeout. El
// trabajo sigue corriendo en el servidor aunque el usuario cambie de vista.
export interface EmailJobOptions {
  maxMessages?: number;
  onProgress?: (processed: number, total: number) => void;
  searchTargets?: Record<string, string>;
  pollMs?: number;
}

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

export async function runEmailFootprint(
  accessToken: string,
  opts: EmailJobOptions = {},
): Promise<any> {
  const { maxMessages = READ_ALL_MESSAGES, onProgress, searchTargets, pollMs = 2500 } = opts;

  const body: Record<string, unknown> = {
    provider: "gmail",
    gmail_access_token: accessToken,
    max_messages: maxMessages,
  };
  if (searchTargets && Object.keys(searchTargets).length > 0) body.search_targets = searchTargets;

  const startRes = await fetch("/api/identification/email-footprint/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const startData = await startRes.json();
  if (!startRes.ok) throw new Error(startData.detail ?? `HTTP ${startRes.status}`);
  const jobId: string = startData.job_id;

  // Sondeo hasta completar. Cada consulta es corta → nunca expira.
  for (;;) {
    await sleep(pollMs);
    const sRes = await fetch(`/api/identification/email-footprint/status?job_id=${encodeURIComponent(jobId)}`);
    const s = await sRes.json();
    if (!sRes.ok) throw new Error(s.detail ?? `HTTP ${sRes.status}`);
    if (onProgress && s.total) onProgress(s.processed ?? 0, s.total);
    if (s.status === "done") return s.result;
    if (s.status === "error") throw new Error(s.error ?? "No se pudo completar el análisis.");
  }
}

// Persiste el resultado del correo en todas las claves que leen las otras vistas.
export function saveEmailResult(data: any, emailAddressFallback = ""): void {
  try {
    const senders = (data.senders ?? [])
      .filter((s: any) => Boolean(s.primary_domain))
      .map((s: any) => ({
        primary_domain:      s.primary_domain,
        personal_data_types: s.personal_data_types ?? [],
        sender_type:         s.sender_type ?? "",
        sample_subjects:     s.evidence?.sample_subjects?.slice(0, 3) ?? [],
      }));
    const domains = senders.map((s: any) => s.primary_domain);
    localStorage.setItem(LS_EMAIL_RESULT, JSON.stringify(data));
    localStorage.setItem(LS_EMAIL_HOLDER, data.email_address ?? emailAddressFallback ?? "");
    if (domains.length > 0) {
      localStorage.setItem(LS_CROSSREF_DOMAINS, JSON.stringify(domains));
      localStorage.setItem(LS_CROSSREF_SENDERS, JSON.stringify(senders));
      localStorage.setItem(LS_CROSSREF_TS, new Date().toISOString());
    }
  } catch { /* localStorage no disponible — no crítico */ }
}

// ── Análisis de navegación ───────────────────────────────────────────────────
export async function runBrowserHistory(browser: string): Promise<any> {
  const res = await fetch(`/api/local/browser-history?browser=${encodeURIComponent(browser)}`);
  const data = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) throw new Error(data.detail ?? `Error ${res.status}`);
  return data;
}

export function saveBrowserResult(data: any): void {
  try { localStorage.setItem(LS_BROWSER_RESULT, JSON.stringify(data)); } catch { /* ignore */ }
}

// ── Info del sistema (SO + navegadores instalados) ───────────────────────────
export async function getSystemInfo(): Promise<{ os: string; os_label: string; available_browsers: string[] }> {
  const r = await fetch("/api/local/system-info", { signal: AbortSignal.timeout(8000) });
  return r.json();
}
