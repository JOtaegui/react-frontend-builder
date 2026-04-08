"""
Módulo: Emails públicos

Recolecta posibles correos asociados a una persona usando varias estrategias:
- buscador HTML con queries dirigidas
- extracción desde HTML, mailto y texto ofuscado
- extracción desde PDFs públicos
- generación de candidatos de baja confianza cuando hay dominio/contexto

El módulo prioriza aislamiento: si una estrategia falla, las demás siguen.
"""
from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from bs4 import BeautifulSoup

from config import BRAVE_SEARCH_API_KEY, BRAVE_SEARCH_API_URL, TIMEOUT_EMAILS
from modules.base import BaseModule, ModuleResult, QueryContext
from utils.scraping import extraer_emails, normalizar

logger = logging.getLogger(__name__)

DDG_HTML_SEARCH = "https://html.duckduckgo.com/html/"
BLOCKED_HOSTS = {
    "webcache.googleusercontent.com",
    "translate.google.com",
}
HIGH_SIGNAL_HOST_HINTS = (
    "gob.cl", "gov.cl", "presidencia.cl", "senado.cl", "camara.cl",
    "edu.cl", "uchile.cl", "uc.cl", "usach.cl", "uai.cl", "udec.cl",
    "github.com", "linkedin.com", "mercadopublico.cl", "portaltransparencia.cl",
)
FREE_EMAIL_DOMAINS = ("gmail.com", "outlook.com", "hotmail.com", "yahoo.com")
CHROME_PROFILE = Path(tempfile.gettempdir()) / "osint_chrome_profile_emails"
CHROME_BINARY_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


class EmailsPublicosModule(BaseModule):
    name = "emails_publicos"
    timeout = TIMEOUT_EMAILS

    async def run(self, context: QueryContext) -> ModuleResult:
        start = time.time()
        try:
            candidatos = await self._collect_candidates(context)
            resultados = self._format_results(candidatos)

            if not resultados:
                return self._result({}, 0, start)

            confirmed = [
                item["email"]
                for item in resultados
                if item.get("match_type") != "generated" and (item.get("confidence") or 0.0) >= 0.7
            ]

            return self._result(
                {"emails_publicos": resultados, "emails": confirmed},
                len(resultados),
                start,
            )
        except Exception as exc:
            return self._error_result(str(exc), start)

    async def _collect_candidates(self, context: QueryContext) -> Dict[str, dict]:
        candidatos: Dict[str, dict] = {}
        urls_visitadas: Set[str] = set()
        observed_domains: Set[str] = set()
        browser_candidates: List[dict] = []
        opened_documents = 0
        empty_queries = 0
        deadline = time.monotonic() + max(6.0, float(self.timeout) - 3.0)

        for query in self._build_queries(context):
            if time.monotonic() >= deadline:
                logger.info("[emails_publicos] Presupuesto agotado; devolviendo hallazgos parciales")
                break

            resultados = await self._buscar_query_segura(query, deadline)
            if not resultados:
                empty_queries += 1
                if empty_queries >= 3 and not browser_candidates:
                    logger.info("[emails_publicos] Varias queries sin resultados; cambiando a descubrimiento con navegador")
                    break
            else:
                empty_queries = 0
            for resultado in resultados:
                if time.monotonic() >= deadline:
                    logger.info("[emails_publicos] Presupuesto agotado durante analisis de resultados")
                    break
                snippet = resultado.get("snippet", "")
                host = self._host(resultado.get("url"))
                title = resultado.get("title", "")
                if host:
                    observed_domains.add(host)

                logger.info(
                    f"[emails_publicos] Resultado candidato | host={host} | title={title[:90]!r} | url={resultado.get('url')}"
                )
                self._push_browser_candidate(browser_candidates, resultado, context)

                hallazgos_snippet = self._extract_from_text(
                    text=snippet,
                    context=context,
                    fuente=resultado.get("title") or host,
                    url=resultado.get("url"),
                    match_type="snippet",
                )
                if hallazgos_snippet:
                    logger.info(
                        f"[emails_publicos] Emails en snippet | url={resultado.get('url')} | encontrados={', '.join(item['email'] for item in hallazgos_snippet[:4])}"
                    )
                self._merge_candidates(
                    candidatos,
                    hallazgos_snippet,
                )

                url = resultado.get("url")
                if not url or url in urls_visitadas:
                    continue
                urls_visitadas.add(url)
                if opened_documents >= 3:
                    continue
                if not self._should_open_document(resultado, context):
                    logger.info(f"[emails_publicos] Saltando documento sin señal fuerte | url={url}")
                    continue

                try:
                    logger.info(f"[emails_publicos] Abriendo documento | url={url}")
                    documento = await self._fetch_document(url, deadline)
                    if documento:
                        opened_documents += 1
                        contenido, extra = documento
                        if extra.get("host"):
                            observed_domains.add(extra["host"])

                        hallazgos_doc = self._extract_from_text(
                            text=contenido,
                            context=context,
                            fuente=resultado.get("title") or extra.get("host"),
                            url=url,
                            match_type=extra.get("match_type", "page"),
                        )
                        if hallazgos_doc:
                            logger.info(
                                f"[emails_publicos] Emails en documento | url={url} | tipo={extra.get('match_type', 'page')} | encontrados={', '.join(item['email'] for item in hallazgos_doc[:4])}"
                            )
                        else:
                            logger.info(
                                f"[emails_publicos] Documento analizado sin emails claros | url={url} | tipo={extra.get('match_type', 'page')}"
                            )
                        self._merge_candidates(
                            candidatos,
                            hallazgos_doc,
                        )
                except Exception as exc:
                    logger.debug(f"[emails_publicos] Documento falló '{url}': {exc}")

                if len(candidatos) >= 15:
                    break

            if len(candidatos) >= 15:
                break

        if not self._has_confirmed_candidates(candidatos) and not BRAVE_SEARCH_API_KEY:
            logger.info("[emails_publicos] BRAVE_SEARCH_API_KEY no configurada; se omite discovery robusto")

        generated = self._generate_candidates(context, observed_domains, candidatos)
        if generated:
            logger.info(
                f"[emails_publicos] Candidatos generados por patron: {', '.join(item['email'] for item in generated[:4])}"
            )
        self._merge_candidates(candidatos, generated)
        return candidatos

    async def _buscar_query_segura(self, query: str, deadline: float) -> List[dict]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return []
        try:
            logger.info(f"[emails_publicos] Query: {query}")
            return await asyncio.wait_for(
                self._buscar_resultados(query),
                timeout=min(3.5, remaining),
            )
        except asyncio.TimeoutError:
            logger.info(f"[emails_publicos] Query timeout | query={query}")
            return []
        except Exception as exc:
            logger.debug(f"[emails_publicos] Query falló '{query}': {exc}")
            return []

    def _build_queries(self, context: QueryContext) -> List[str]:
        nombre = context.nombre.strip()
        nombre_simple = self._nombre_simple(nombre)
        nombre_ascii = self._ascii_name(nombre)
        queries = [
            f'"{nombre}" email',
            f'"{nombre}" correo',
            f'site:cl "{nombre}" email',
            f'site:gob.cl "{nombre}"',
            f'site:edu.cl "{nombre}"',
            f'site:linkedin.com/in "{nombre}"',
            f'site:cl "{nombre}" contacto',
        ]
        if nombre_ascii and nombre_ascii != nombre:
            queries.extend([
                f'"{nombre_ascii}" email',
            ])
        if nombre_simple and nombre_simple not in {nombre, nombre_ascii}:
            queries.extend([
                f'"{nombre_simple}" email',
            ])
        if context.rut:
            queries.extend([
                f'"{context.rut}" email',
            ])
        return queries[:6]

    async def _buscar_resultados(self, query: str) -> List[dict]:
        if BRAVE_SEARCH_API_KEY:
            return await self._buscar_resultados_brave(query)

        resp = await self.client.get(
            DDG_HTML_SEARCH,
            params={"q": query, "kl": "cl-es"},
            timeout=min(6.0, float(self.timeout)),
        )
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        resultados: List[dict] = []
        for item in soup.select(".result, .web-result"):
            a_tag = item.select_one(".result__a") or item.find("a", href=True)
            if not a_tag:
                continue

            href = self._clean_result_url(a_tag.get("href", ""))
            host = self._host(href)
            if not href or host in BLOCKED_HOSTS:
                continue

            snippet_tag = item.select_one(".result__snippet") or item.find(class_=re.compile("snippet", re.I))
            resultados.append({
                "title": a_tag.get_text(" ", strip=True)[:160],
                "url": href,
                "snippet": snippet_tag.get_text(" ", strip=True)[:500] if snippet_tag else "",
            })
            if len(resultados) >= 2:
                break
        return resultados

    async def _buscar_resultados_brave(self, query: str) -> List[dict]:
        try:
            resp = await self.client.get(
                BRAVE_SEARCH_API_URL,
                params={
                    "q": query,
                    "count": 5,
                    "country": "CL",
                    "search_lang": "es",
                    "extra_snippets": "true",
                },
                headers={"X-Subscription-Token": BRAVE_SEARCH_API_KEY},
                timeout=min(6.0, float(self.timeout)),
            )
        except Exception as exc:
            logger.debug(f"[emails_publicos] Brave error '{query}': {exc}")
            return []

        if resp.status_code != 200:
            logger.info(f"[emails_publicos] Brave sin respuesta valida | status={resp.status_code} | query={query}")
            return []

        payload = resp.json()
        results = (((payload or {}).get("web") or {}).get("results") or [])
        resultados: List[dict] = []
        for item in results:
            url = item.get("url")
            host = self._host(url)
            if not url or not host or host in BLOCKED_HOSTS:
                continue
            snippets = [item.get("description") or ""]
            snippets.extend(item.get("extra_snippets") or [])
            resultados.append({
                "title": (item.get("title") or "")[:160],
                "url": url,
                "snippet": " ".join(snippets)[:700],
            })
            logger.info(
                f"[emails_publicos] Brave candidato | title={(item.get('title') or '')[:90]!r} | url={url}"
            )
            if len(resultados) >= 3:
                break
        return resultados

    def _should_open_document(self, resultado: dict, context: QueryContext) -> bool:
        url = resultado.get("url") or ""
        host = (self._host(url) or "").lower()
        snippet = resultado.get("snippet", "")
        title = resultado.get("title", "")
        combined = f"{title} {snippet}"
        if self._resultado_fuertemente_relevante(resultado, context):
            return True
        if ".pdf" in url.lower():
            return True
        if extraer_emails(combined) or self._extract_obfuscated_emails(combined):
            return True
        if any(hint in host for hint in HIGH_SIGNAL_HOST_HINTS):
            return self._texto_relevante(normalizar(combined), context)
        return False

    async def _fetch_document(self, url: str, deadline: float) -> Optional[Tuple[str, dict]]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            resp = await asyncio.wait_for(
                self.client.get(url, timeout=min(3.5, float(self.timeout), remaining)),
                timeout=min(4.0, remaining),
            )
        except Exception as exc:
            logger.debug(f"[emails_publicos] Error page '{url}': {exc}")
            return None

        if resp.status_code != 200:
            return None

        content_type = (resp.headers.get("content-type") or "").lower()
        host = self._host(url)

        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            texto = self._extract_pdf_text(resp.content)
            logger.info(f"[emails_publicos] Documento PDF cargado | host={host} | chars={len(texto)}")
            return (texto, {"match_type": "pdf", "host": host})

        html = resp.text
        soup = BeautifulSoup(html, "lxml")
        text_parts = [self._extract_html_signals(soup), soup.get_text(" ", strip=True)]
        mailtos = []
        for a_tag in soup.select("a[href^='mailto:']"):
            href = a_tag.get("href", "")
            if ":" in href:
                mailtos.append(href.split(":", 1)[1].split("?", 1)[0])
        if mailtos:
            text_parts.append(" ".join(mailtos))
            logger.info(f"[emails_publicos] Mailto detectado | url={url} | emails={', '.join(mailtos[:4])}")

        return (" ".join(part for part in text_parts if part), {"match_type": "page", "host": host})

    def _extract_pdf_text(self, content: bytes) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            textos = []
            for page in reader.pages[:10]:
                textos.append(page.extract_text() or "")
            return " ".join(textos)
        except Exception as exc:
            logger.debug(f"[emails_publicos] PDF no legible: {exc}")
            return ""

    def _extract_from_text(
        self,
        text: str,
        context: QueryContext,
        fuente: Optional[str],
        url: Optional[str],
        match_type: str,
    ) -> List[dict]:
        if not text:
            return []

        raw_emails = set(extraer_emails(text))
        raw_emails.update(self._extract_obfuscated_emails(text))

        resultados: List[dict] = []
        texto_norm = normalizar(text)
        texto_relevante = self._texto_relevante(texto_norm, context)
        for email in raw_emails:
            if self._email_descartable(email):
                continue

            confidence = self._score_email(email, text, context, match_type, texto_relevante, url)
            if confidence < 0.45:
                continue

            resultados.append({
                "email": email.lower(),
                "url": url,
                "fuente": fuente or self._host(url),
                "contexto": self._resumir_contexto(text, email),
                "confidence": round(confidence, 3),
                "match_type": match_type,
                "existence_status": "published",
                "institutional_domain": self._institutional_domain(email),
                "domain_category": self._domain_category(email),
            })
        return resultados

    def _generate_candidates(
        self,
        context: QueryContext,
        observed_domains: Set[str],
        existing: Dict[str, dict],
    ) -> List[dict]:
        tokens = [t for t in normalizar(context.nombre).split() if len(t) > 1]
        if len(tokens) < 2:
            return []

        first = tokens[0]
        last = tokens[-1]
        middle = tokens[1] if len(tokens) > 2 else ""
        local_parts = {
            f"{first}.{last}",
            f"{first}{last}",
            f"{first[0]}{last}",
            f"{first}.{middle}.{last}" if middle else "",
            f"{last}.{first}",
        }
        local_parts = {lp for lp in local_parts if lp}

        candidate_domains = {
            domain for domain in observed_domains
            if any(hint in domain for hint in HIGH_SIGNAL_HOST_HINTS)
        }
        candidate_domains.update(FREE_EMAIL_DOMAINS)

        resultados: List[dict] = []
        for domain in sorted(candidate_domains):
            for local in sorted(local_parts):
                email = f"{local}@{domain}"
                if email in existing:
                    continue
                confidence = 0.28 if domain in FREE_EMAIL_DOMAINS else 0.42
                resultados.append({
                    "email": email,
                    "url": None,
                    "fuente": domain,
                    "contexto": "Candidato generado por patron de nombre y dominio observado",
                    "confidence": round(confidence, 3),
                    "match_type": "generated",
                    "existence_status": "unconfirmed",
                    "institutional_domain": self._institutional_domain(email),
                    "domain_category": self._domain_category(email),
                })
        return resultados[:8]

    def _merge_candidates(self, target: Dict[str, dict], items: List[dict]) -> None:
        for item in items:
            email = item["email"].lower()
            previo = target.get(email)
            if not previo or (item.get("confidence") or 0.0) > (previo.get("confidence") or 0.0):
                target[email] = item

    def _extract_obfuscated_emails(self, text: str) -> Set[str]:
        transformed = text
        replacements = [
            (r"\[\s*at\s*\]|\(\s*at\s*\)|\s+at\s+|\s+arroba\s+", "@"),
            (r"\[\s*dot\s*\]|\(\s*dot\s*\)|\s+dot\s+|\s+punto\s+", "."),
        ]
        for pattern, repl in replacements:
            transformed = re.sub(pattern, repl, transformed, flags=re.I)
        transformed = re.sub(r"\s*@\s*", "@", transformed)
        transformed = re.sub(r"\s*\.\s*", ".", transformed)
        return set(extraer_emails(transformed))

    def _score_email(
        self,
        email: str,
        text: str,
        context: QueryContext,
        match_type: str,
        texto_relevante: bool,
        url: Optional[str],
    ) -> float:
        score = 0.2
        if match_type == "snippet":
            score += 0.2
        elif match_type == "page":
            score += 0.3
        elif match_type == "pdf":
            score += 0.35

        if texto_relevante:
            score += 0.25

        local = email.split("@", 1)[0].replace(".", " ").replace("_", " ").replace("-", " ")
        if self._nombre_parece_email(normalizar(local), context):
            score += 0.2

        host = self._host(url) or ""
        if any(hint in host for hint in HIGH_SIGNAL_HOST_HINTS):
            score += 0.1
        if any(email.endswith(f"@{dom}") for dom in FREE_EMAIL_DOMAINS):
            score += 0.05

        return min(0.99, score)

    def _resultado_fuertemente_relevante(self, resultado: dict, context: QueryContext) -> bool:
        combined = " ".join(
            [
                resultado.get("title", ""),
                resultado.get("snippet", ""),
                resultado.get("url", ""),
            ]
        )
        texto_norm = normalizar(combined)
        nombre_full = normalizar(context.nombre)
        nombre_simple = normalizar(self._nombre_simple(context.nombre))
        return bool(
            (nombre_full and nombre_full in texto_norm)
            or (nombre_simple and nombre_simple in texto_norm)
            or self._texto_relevante(texto_norm, context)
        )

    def _extract_html_signals(self, soup: BeautifulSoup) -> str:
        pieces: List[str] = []
        if soup.title and soup.title.string:
            pieces.append(soup.title.string.strip())
        for attrs in (
            {"property": "og:title"},
            {"property": "og:description"},
            {"name": "description"},
            {"name": "twitter:title"},
            {"name": "twitter:description"},
        ):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                pieces.append(tag.get("content", "").strip())
        for script in soup.select("script[type='application/ld+json']"):
            texto = script.get_text(" ", strip=True)
            if texto:
                pieces.append(texto[:600])
        return " ".join(piece for piece in pieces if piece)

    def _texto_relevante(self, texto_norm: str, context: QueryContext) -> bool:
        palabras = [p for p in normalizar(context.nombre).split() if len(p) > 2]
        coincidencias = sum(1 for p in palabras if p in texto_norm)
        if coincidencias >= max(2, min(3, len(palabras))):
            return True
        if context.rut:
            rut_limpio = re.sub(r"[.\s]", "", context.rut).lower()
            if rut_limpio and rut_limpio in texto_norm.replace(".", "").replace(" ", ""):
                return True
        return False

    def _nombre_parece_email(self, local_norm: str, context: QueryContext) -> bool:
        tokens = [p for p in normalizar(context.nombre).split() if len(p) > 2]
        coincidencias = sum(1 for token in tokens if token in local_norm)
        return coincidencias >= max(1, min(2, len(tokens)))

    def _email_descartable(self, email: str) -> bool:
        email_low = email.lower()
        descartables = [
            "noreply@", "no-reply@", "donotreply@", "example@", "ventas@",
            "soporte@", "support@", "press@", "prensa@", ".png", ".jpg",
            ".jpeg", ".gif", ".webp",
        ]
        return any(x in email_low for x in descartables)

    def _resumir_contexto(self, texto: str, email: str) -> Optional[str]:
        idx = texto.lower().find(email.lower())
        if idx == -1:
            return None
        inicio = max(0, idx - 100)
        fin = min(len(texto), idx + len(email) + 100)
        return texto[inicio:fin].strip()[:240]

    def _clean_result_url(self, href: str) -> str:
        if not href:
            return ""
        if href.startswith("//"):
            return f"https:{href}"
        if href.startswith("http"):
            parsed = urlparse(href)
            if parsed.netloc.endswith("duckduckgo.com"):
                target = parse_qs(parsed.query).get("uddg", [])
                if target:
                    return unquote(target[0])
            return href
        return ""

    def _host(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        try:
            return urlparse(url).netloc or None
        except Exception:
            return None

    def _nombre_simple(self, nombre: str) -> str:
        partes = nombre.split()
        if len(partes) >= 2:
            return f"{partes[0]} {partes[-1]}"
        return nombre

    def _ascii_name(self, nombre: str) -> str:
        return normalizar(nombre).title()

    def _format_results(self, candidatos: Dict[str, dict]) -> List[dict]:
        ordenados = sorted(
            candidatos.values(),
            key=lambda item: (
                item.get("match_type") == "generated",
                -(item.get("confidence") or 0.0),
                item["email"],
            ),
        )
        return ordenados[:15]

    def _has_confirmed_candidates(self, candidatos: Dict[str, dict]) -> bool:
        return any(
            item.get("existence_status") == "published" and item.get("match_type") != "generated"
            for item in candidatos.values()
        )

    def _push_browser_candidate(self, target: List[dict], resultado: dict, context: QueryContext) -> None:
        url = resultado.get("url")
        if not url:
            return
        score = self._browser_priority(resultado, context)
        if score <= 0:
            return
        if any(item.get("url") == url for item in target):
            return
        target.append({
            "url": url,
            "title": resultado.get("title"),
            "score": score,
        })
        target.sort(key=lambda item: -item.get("score", 0))

    def _browser_priority(self, resultado: dict, context: QueryContext) -> int:
        combined = " ".join([
            resultado.get("title", ""),
            resultado.get("snippet", ""),
            resultado.get("url", ""),
        ])
        texto_norm = normalizar(combined)
        score = 0
        if normalizar(context.nombre) in texto_norm:
            score += 4
        if normalizar(self._nombre_simple(context.nombre)) in texto_norm:
            score += 2
        if self._texto_relevante(texto_norm, context):
            score += 2
        host = (self._host(resultado.get("url")) or "").lower()
        if "linkedin.com" in host:
            score += 3
        if any(hint in host for hint in HIGH_SIGNAL_HOST_HINTS):
            score += 2
        return score

    def _collect_with_browser(self, browser_candidates: List[dict], context: QueryContext) -> List[dict]:
        hallazgos: List[dict] = []
        for candidate in browser_candidates:
            url = candidate.get("url")
            if not url:
                continue
            logger.info(f"[emails_publicos] Browser fallback abriendo | url={url}")
            html = self._fetch_html_with_browser(url)
            if not html:
                logger.info(f"[emails_publicos] Browser fallback sin HTML util | url={url}")
                continue
            soup = BeautifulSoup(html, "lxml")
            contenido = " ".join(
                part for part in [
                    self._extract_html_signals(soup),
                    soup.get_text(" ", strip=True),
                    self._extract_mailtos(soup),
                ]
                if part
            )
            encontrados = self._extract_from_text(
                text=contenido,
                context=context,
                fuente=candidate.get("title") or self._host(url),
                url=url,
                match_type="browser",
            )
            if encontrados:
                logger.info(
                    f"[emails_publicos] Browser fallback encontro emails | url={url} | encontrados={', '.join(item['email'] for item in encontrados[:4])}"
                )
                hallazgos.extend(encontrados)
            else:
                logger.info(f"[emails_publicos] Browser fallback sin emails | url={url}")
        return hallazgos[:10]

    def _fetch_html_with_browser(self, url: str) -> str:
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
        except ImportError as exc:
            logger.warning("[emails_publicos] Browser fallback no disponible: %s", exc)
            return ""

        driver = None
        try:
            opts = uc.ChromeOptions()
            opts.add_argument("--no-sandbox")
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1280,800")
            opts.add_argument("--window-position=-3000,-3000")
            opts.add_argument("--lang=es-CL")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument(f"--user-data-dir={CHROME_PROFILE}")
            opts.add_argument("--disable-notifications")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-extensions")
            opts.add_argument("--blink-settings=imagesEnabled=false")
            opts.add_argument("--disable-background-networking")
            opts.add_argument("--disable-renderer-backgrounding")
            opts.add_argument("--disable-features=Translate,BackForwardCache,InterestFeedContentSuggestions,OptimizationHints")
            opts.page_load_strategy = "eager"
            chrome_binary = self._detectar_chrome_binario()
            if chrome_binary:
                opts.binary_location = chrome_binary

            version_main = self._detectar_chrome_version_main(chrome_binary)
            if version_main:
                logger.info(f"[emails_publicos] Usando Chrome major version {version_main}")

            caps = DesiredCapabilities.CHROME.copy()
            caps["pageLoadStrategy"] = "eager"
            driver = uc.Chrome(
                options=opts,
                version_main=version_main,
                use_subprocess=True,
                desired_capabilities=caps,
            )
            driver.set_page_load_timeout(8)
            driver.get(url)
            self._mover_ventana_afuera()
            time.sleep(1.2)
            logger.info(f"[emails_publicos] Browser URL final: {driver.current_url}")
            return driver.page_source or ""
        except Exception as exc:
            logger.warning(f"[emails_publicos] Error en browser fallback: {exc}")
            return ""
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _extract_mailtos(self, soup: BeautifulSoup) -> str:
        emails: List[str] = []
        for a_tag in soup.select("a[href^='mailto:']"):
            href = a_tag.get("href", "")
            if ":" in href:
                emails.append(href.split(":", 1)[1].split("?", 1)[0])
        if emails:
            logger.info(f"[emails_publicos] Mailto detectado en browser/html | emails={', '.join(emails[:4])}")
        return " ".join(emails)

    def _mover_ventana_afuera(self) -> None:
        script = """
        tell application "Google Chrome"
            if (count of windows) > 0 then
                set bounds of front window to {-2000, -2000, -634, -1232}
            end if
        end tell
        """
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=3,
                check=False,
            )
        except Exception:
            pass

    def _detectar_chrome_binario(self) -> Optional[str]:
        for path in CHROME_BINARY_CANDIDATES:
            if Path(path).exists():
                return path
        return None

    def _discover_candidates_with_browser_search(self, queries: List[str], context: QueryContext) -> List[dict]:
        candidatos: List[dict] = []
        vistos: Set[str] = set()
        for query in queries:
            search_url = f"https://duckduckgo.com/?q={quote_plus(query)}&kl=cl-es"
            logger.info(f"[emails_publicos] Browser search query | query={query}")
            html = self._fetch_html_with_browser(search_url)
            if not html:
                continue
            for resultado in self._parse_browser_search_results(html):
                url = resultado.get("url")
                if not url or url in vistos:
                    continue
                vistos.add(url)
                if not self._resultado_fuertemente_relevante(resultado, context):
                    continue
                logger.info(
                    f"[emails_publicos] Browser search candidato | title={resultado.get('title', '')[:90]!r} | url={url}"
                )
                self._push_browser_candidate(candidatos, resultado, context)
                if len(candidatos) >= 5:
                    return candidatos
        return candidatos

    def _parse_browser_search_results(self, html: str) -> List[dict]:
        soup = BeautifulSoup(html, "lxml")
        resultados: List[dict] = []
        for a_tag in soup.select("a.result__a, a[data-testid='result-title-a'], a[href^='/url?q='], a[href^='http']"):
            href = self._clean_result_url(a_tag.get("href", ""))
            host = self._host(href)
            if not href or not host or host in BLOCKED_HOSTS or "duckduckgo.com" in host:
                continue
            title = a_tag.get_text(" ", strip=True)[:180]
            if len(title) < 3:
                continue
            container = a_tag.find_parent(["article", "div", "li"])
            snippet = container.get_text(" ", strip=True)[:500] if container else ""
            resultados.append({"title": title, "url": href, "snippet": snippet})
            if len(resultados) >= 6:
                break
        return resultados

    def _detectar_chrome_version_main(self, chrome_binary: Optional[str]) -> Optional[int]:
        comandos: List[List[str]] = []
        if chrome_binary:
            comandos.append([chrome_binary, "--version"])
        comandos.extend([
            ["google-chrome", "--version"],
            ["chromium", "--version"],
            ["chromium-browser", "--version"],
        ])

        for cmd in comandos:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                salida = (result.stdout or result.stderr or "").strip()
                match = re.search(r"(\d+)\.\d+\.\d+\.\d+", salida)
                if match:
                    return int(match.group(1))
            except Exception:
                continue
        return None

    def _institutional_domain(self, email: str) -> Optional[str]:
        domain = email.split("@", 1)[-1].lower()
        categoria = self._domain_category(email)
        if categoria == "institutional":
            return domain
        return None

    def _domain_category(self, email: str) -> Optional[str]:
        domain = email.split("@", 1)[-1].lower()
        if domain.endswith(".gob.cl") or domain.endswith(".gov.cl") or any(
            hint in domain for hint in ("presidencia.cl", "senado.cl", "camara.cl", "municipalidad", "ministerio")
        ):
            return "government"
        if domain.endswith(".edu.cl") or any(
            hint in domain for hint in ("uchile.cl", "uc.cl", "usach.cl", "uai.cl", "udec.cl", "uandes.cl", "udp.cl")
        ):
            return "institutional"
        if domain.endswith(".org.cl") or domain.endswith(".cl"):
            if domain not in FREE_EMAIL_DOMAINS and any(hint in domain for hint in HIGH_SIGNAL_HOST_HINTS):
                return "institutional"
        if domain in FREE_EMAIL_DOMAINS:
            return "personal"
        return "other"
