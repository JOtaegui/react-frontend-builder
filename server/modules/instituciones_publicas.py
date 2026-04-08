"""
Módulo: Instituciones relacionadas

Infiere organizaciones e instituciones asociadas a una persona, priorizando:
- snippets públicos de LinkedIn
- páginas institucionales / corporativas
- PDFs públicos
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
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from bs4 import BeautifulSoup

from config import BRAVE_SEARCH_API_KEY, BRAVE_SEARCH_API_URL, TIMEOUT_INSTITUCIONES
from modules.base import BaseModule, ModuleResult, QueryContext
from utils.scraping import normalizar

logger = logging.getLogger(__name__)

DDG_HTML_SEARCH = "https://html.duckduckgo.com/html/"
INSTITUTION_PATTERNS = [
    re.compile(r"(?:en|at|@\s*)\s*([A-Za-zÁÉÍÓÚÑáéíóúñ][\w&.\- ]{2,80})", re.I),
    re.compile(r"(?:trabaja(?:\s+actualmente)?\s+en)\s+([A-Za-zÁÉÍÓÚÑáéíóúñ][\w&.\- ]{2,80})", re.I),
    re.compile(r"(?:profesor|investigador|director|gerente|presidente|fundador|asesor|ceo|founder|cofounder)\s+(?:de|del|de la|de los|de las|en)\s+(?:la|el|los|las\s+)?([A-Za-zÁÉÍÓÚÑáéíóúñ][\w&.\- ]{2,80})", re.I),
    re.compile(r"(?:presidente|director|gerente|ceo|founder|cofounder|asesor)[^|,;]{0,40}(?:@|[-–—|])\s*([A-Za-zÁÉÍÓÚÑáéíóúñ][\w&.\- ]{2,80})", re.I),
]
INSTITUTION_SUFFIXES = (
    "universidad", "ministerio", "municipalidad", "fundacion", "fundación",
    "corporacion", "corporación", "partido", "senado", "camara", "cámara",
    "presidencia", "gobierno", "hospital", "instituto", "empresa", "spa", "s.a.", "ltda",
    "bank", "banco", "holding", "group", "grupo", "republica", "república",
)
HIGH_SIGNAL_DOMAINS = (
    "linkedin.com", "gob.cl", "gov.cl", "edu.cl", "uchile.cl", "uc.cl",
    "usach.cl", "uai.cl", "udec.cl", "mercadopublico.cl", "camara.cl", "senado.cl",
)
CHROME_PROFILE = Path(tempfile.gettempdir()) / "osint_chrome_profile_instituciones"
CHROME_BINARY_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


class InstitucionesPublicasModule(BaseModule):
    name = "instituciones_publicas"
    timeout = TIMEOUT_INSTITUCIONES

    async def run(self, context: QueryContext) -> ModuleResult:
        start = time.time()
        try:
            items = await self._buscar_instituciones(context)
            if not items:
                return self._result({}, 0, start)
            return self._result({"instituciones_relacionadas": items}, len(items), start)
        except Exception as exc:
            return self._error_result(str(exc), start)

    async def _buscar_instituciones(self, context: QueryContext) -> List[dict]:
        candidatos: Dict[str, dict] = {}
        urls_visitadas: Set[str] = set()
        browser_candidates: List[dict] = []
        opened_documents = 0
        empty_queries = 0
        deadline = time.monotonic() + max(6.0, float(self.timeout) - 3.0)

        for query, source_type in self._build_queries(context):
            if time.monotonic() >= deadline:
                logger.info("[instituciones_publicas] Presupuesto agotado; devolviendo hallazgos parciales")
                break

            resultados = await self._buscar_query_segura(query, source_type, deadline)
            if not resultados:
                empty_queries += 1
                if empty_queries >= 3 and not browser_candidates:
                    logger.info("[instituciones_publicas] Varias queries sin resultados; cambiando a descubrimiento con navegador")
                    break
            else:
                empty_queries = 0
            for resultado in resultados:
                if time.monotonic() >= deadline:
                    logger.info("[instituciones_publicas] Presupuesto agotado durante analisis de resultados")
                    break
                title = resultado.get("title", "")
                snippet = resultado.get("snippet", "")
                url = resultado.get("url")
                host = self._host(url)
                logger.info(
                    f"[instituciones_publicas] Resultado candidato | source={source_type} | host={host} | title={title[:100]!r} | url={url}"
                )
                self._push_browser_candidate(browser_candidates, resultado, context, source_type)

                hallazgos_texto = self._extract_from_text(
                    text=" ".join([title, snippet]),
                    context=context,
                    source_type=source_type,
                    fuente=host,
                    url=url,
                )
                if hallazgos_texto:
                    logger.info(
                        f"[instituciones_publicas] Instituciones en snippet/title | url={url} | encontradas={', '.join(item['nombre'] for item in hallazgos_texto[:4])}"
                    )
                self._merge(
                    candidatos,
                    hallazgos_texto,
                )
                hallazgos_titulo = self._extract_from_title_segments(
                    title=title,
                    context=context,
                    source_type=source_type,
                    fuente=host,
                    url=url,
                )
                if hallazgos_titulo:
                    logger.info(
                        f"[instituciones_publicas] Instituciones en titulo | url={url} | encontradas={', '.join(item['nombre'] for item in hallazgos_titulo[:4])}"
                    )
                self._merge(
                    candidatos,
                    hallazgos_titulo,
                )

                if not url or url in urls_visitadas:
                    continue
                urls_visitadas.add(url)
                if opened_documents >= 3:
                    continue
                if not self._should_open_document(resultado, source_type, context):
                    logger.info(f"[instituciones_publicas] Saltando documento sin señal fuerte | url={url}")
                    continue

                logger.info(f"[instituciones_publicas] Abriendo documento | source={source_type} | url={url}")
                doc = await self._fetch_document(url, deadline)
                if not doc:
                    continue
                opened_documents += 1
                contenido, host, detected_type = doc
                hallazgos_doc = self._extract_from_text(
                    text=contenido,
                    context=context,
                    source_type=detected_type,
                    fuente=host,
                    url=url,
                )
                if hallazgos_doc:
                    logger.info(
                        f"[instituciones_publicas] Instituciones en documento | url={url} | encontradas={', '.join(item['nombre'] for item in hallazgos_doc[:4])}"
                    )
                else:
                    logger.info(f"[instituciones_publicas] Documento analizado sin institución clara | url={url}")
                self._merge(
                    candidatos,
                    hallazgos_doc,
                )

                if len(candidatos) >= 12:
                    break
            if len(candidatos) >= 12:
                break

        if not candidatos and not BRAVE_SEARCH_API_KEY:
            logger.info("[instituciones_publicas] BRAVE_SEARCH_API_KEY no configurada; se omite discovery robusto")

        ordenados = sorted(candidatos.values(), key=lambda x: -(x.get("confidence") or 0.0))
        return ordenados[:10]

    async def _buscar_query_segura(self, query: str, source_type: str, deadline: float) -> List[dict]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return []
        try:
            logger.info(f"[instituciones_publicas] Query: {query}")
            return await asyncio.wait_for(
                self._buscar_resultados(query),
                timeout=min(3.5, remaining),
            )
        except asyncio.TimeoutError:
            logger.info(f"[instituciones_publicas] Query timeout | source={source_type} | query={query}")
            return []
        except Exception as exc:
            logger.debug(f"[instituciones_publicas] search error '{query}': {exc}")
            return []

    def _build_queries(self, context: QueryContext) -> List[Tuple[str, str]]:
        nombre = context.nombre.strip()
        simple = self._nombre_simple(nombre)
        ascii_name = self._nombre_ascii(nombre)
        return [
            (f'site:linkedin.com/in "{nombre}"', "linkedin"),
            (f'site:linkedin.com/pub "{nombre}"', "linkedin"),
            (f'"{nombre}" linkedin', "linkedin"),
            (f'site:cl "{nombre}" linkedin', "linkedin"),
            (f'site:gob.cl "{nombre}"', "web"),
            (f'site:edu.cl "{nombre}"', "web"),
            (f'site:cl "{nombre}" "director" OR "gerente" OR "fundador" OR "presidente"', "web"),
            (f'site:linkedin.com/in "{ascii_name}"', "linkedin"),
            (f'site:linkedin.com/in "{simple}"', "linkedin"),
        ]

    async def _buscar_resultados(self, query: str) -> List[dict]:
        if BRAVE_SEARCH_API_KEY:
            return await self._buscar_resultados_brave(query)

        try:
            resp = await self.client.get(
                DDG_HTML_SEARCH,
                params={"q": query, "kl": "cl-es"},
                timeout=self.timeout,
            )
        except Exception as exc:
            logger.debug(f"[instituciones_publicas] search error '{query}': {exc}")
            return []

        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        resultados: List[dict] = []
        for item in soup.select(".result, .web-result"):
            a_tag = item.select_one(".result__a") or item.find("a", href=True)
            if not a_tag:
                continue

            href = self._clean_result_url(a_tag.get("href", ""))
            if not href:
                continue
            snippet_tag = item.select_one(".result__snippet") or item.find(class_=re.compile("snippet", re.I))
            resultados.append({
                "title": a_tag.get_text(" ", strip=True)[:180],
                "url": href,
                "snippet": snippet_tag.get_text(" ", strip=True)[:500] if snippet_tag else "",
            })
            if len(resultados) >= 3:
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
            logger.debug(f"[instituciones_publicas] Brave error '{query}': {exc}")
            return []

        if resp.status_code != 200:
            logger.info(f"[instituciones_publicas] Brave sin respuesta valida | status={resp.status_code} | query={query}")
            return []

        payload = resp.json()
        results = (((payload or {}).get("web") or {}).get("results") or [])
        resultados: List[dict] = []
        for item in results:
            url = item.get("url")
            host = self._host(url)
            if not url or not host:
                continue
            snippets = [item.get("description") or ""]
            snippets.extend(item.get("extra_snippets") or [])
            source_type = "linkedin" if "linkedin.com" in host else "web"
            resultados.append({
                "title": (item.get("title") or "")[:180],
                "url": url,
                "snippet": " ".join(snippets)[:700],
                "source_type": source_type,
            })
            logger.info(
                f"[instituciones_publicas] Brave candidato | source={source_type} | title={(item.get('title') or '')[:100]!r} | url={url}"
            )
            if len(resultados) >= 3:
                break
        return resultados

    def _should_open_document(self, resultado: dict, source_type: str, context: QueryContext) -> bool:
        combined = f"{resultado.get('title', '')} {resultado.get('snippet', '')} {resultado.get('url', '')}"
        texto_norm = normalizar(combined)
        host = self._host(resultado.get("url"))
        if source_type == "linkedin":
            return self._texto_relevante(texto_norm, context, source_type=source_type, fuente=host)
        if ".pdf" in (resultado.get("url") or "").lower():
            return True
        return self._texto_relevante(texto_norm, context, source_type=source_type, fuente=host)

    async def _fetch_document(self, url: str, deadline: float) -> Optional[Tuple[str, Optional[str], str]]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            resp = await asyncio.wait_for(
                self.client.get(url, timeout=min(3.5, float(self.timeout), remaining)),
                timeout=min(4.0, remaining),
            )
        except Exception as exc:
            logger.debug(f"[instituciones_publicas] page error '{url}': {exc}")
            return None

        if resp.status_code != 200:
            return None

        host = self._host(url)
        content_type = (resp.headers.get("content-type") or "").lower()
        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            texto = self._extract_pdf_text(resp.content)
            logger.info(f"[instituciones_publicas] PDF cargado | host={host} | chars={len(texto)}")
            return (texto, host, "pdf")

        soup = BeautifulSoup(resp.text, "lxml")
        texto = " ".join(
            piece for piece in [
                self._extract_html_signals(soup),
                soup.get_text(" ", strip=True),
            ]
            if piece
        )
        return (texto, host, "page")

    def _push_browser_candidate(self, target: List[dict], resultado: dict, context: QueryContext, source_type: str) -> None:
        url = resultado.get("url")
        if not url:
            return
        score = self._browser_priority(resultado, context, source_type)
        if score <= 0:
            return
        if any(item.get("url") == url for item in target):
            return
        target.append({
            "url": url,
            "title": resultado.get("title"),
            "source_type": source_type,
            "score": score,
        })
        target.sort(key=lambda item: -item.get("score", 0))

    def _browser_priority(self, resultado: dict, context: QueryContext, source_type: str) -> int:
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
        if self._texto_relevante(texto_norm, context, source_type=source_type, fuente=self._host(resultado.get("url"))):
            score += 2
        host = (self._host(resultado.get("url")) or "").lower()
        if "linkedin.com" in host:
            score += 3
        if any(hint in host for hint in HIGH_SIGNAL_DOMAINS):
            score += 2
        return score

    def _collect_with_browser(self, browser_candidates: List[dict], context: QueryContext) -> List[dict]:
        hallazgos: List[dict] = []
        for candidate in browser_candidates:
            url = candidate.get("url")
            source_type = candidate.get("source_type", "page")
            if not url:
                continue
            logger.info(f"[instituciones_publicas] Browser fallback abriendo | source={source_type} | url={url}")
            html = self._fetch_html_with_browser(url)
            if not html:
                logger.info(f"[instituciones_publicas] Browser fallback sin HTML util | url={url}")
                continue
            soup = BeautifulSoup(html, "lxml")
            contenido = " ".join(
                part for part in [
                    self._extract_html_signals(soup),
                    soup.get_text(" ", strip=True),
                ]
                if part
            )
            encontrados = self._extract_from_text(
                text=contenido,
                context=context,
                source_type="browser",
                fuente=self._host(url),
                url=url,
            )
            if encontrados:
                logger.info(
                    f"[instituciones_publicas] Browser fallback encontro instituciones | url={url} | encontradas={', '.join(item['nombre'] for item in encontrados[:4])}"
                )
                hallazgos.extend(encontrados)
            else:
                logger.info(f"[instituciones_publicas] Browser fallback sin instituciones | url={url}")
        return hallazgos[:8]

    def _fetch_html_with_browser(self, url: str) -> str:
        try:
            import undetected_chromedriver as uc
        except ImportError as exc:
            logger.warning("[instituciones_publicas] Browser fallback no disponible: %s", exc)
            return ""

        driver = None
        try:
            opts = uc.ChromeOptions()
            opts.add_argument("--no-sandbox")
            opts.add_argument("--window-size=1280,800")
            opts.add_argument("--window-position=-3000,-3000")
            opts.add_argument("--lang=es-CL")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument(f"--user-data-dir={CHROME_PROFILE}")
            opts.add_argument("--disable-notifications")
            chrome_binary = self._detectar_chrome_binario()
            if chrome_binary:
                opts.binary_location = chrome_binary

            version_main = self._detectar_chrome_version_main(chrome_binary)
            if version_main:
                logger.info(f"[instituciones_publicas] Usando Chrome major version {version_main}")

            driver = uc.Chrome(
                options=opts,
                version_main=version_main,
                use_subprocess=True,
            )
            driver.set_page_load_timeout(12)
            driver.get(url)
            self._mover_ventana_afuera()
            time.sleep(2)
            logger.info(f"[instituciones_publicas] Browser URL final: {driver.current_url}")
            return driver.page_source or ""
        except Exception as exc:
            logger.warning(f"[instituciones_publicas] Error en browser fallback: {exc}")
            return ""
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

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
            logger.info(f"[instituciones_publicas] Browser search query | query={query}")
            html = self._fetch_html_with_browser(search_url)
            if not html:
                continue
            for resultado in self._parse_browser_search_results(html):
                url = resultado.get("url")
                if not url or url in vistos:
                    continue
                vistos.add(url)
                if not self._texto_relevante(
                    normalizar(" ".join([resultado.get("title", ""), resultado.get("snippet", ""), url])),
                    context,
                    source_type=resultado.get("source_type", "linkedin"),
                    fuente=self._host(url),
                ):
                    continue
                logger.info(
                    f"[instituciones_publicas] Browser search candidato | title={resultado.get('title', '')[:100]!r} | url={url}"
                )
                self._push_browser_candidate(
                    candidatos,
                    {
                        "url": url,
                        "title": resultado.get("title"),
                        "snippet": resultado.get("snippet"),
                    },
                    context,
                    resultado.get("source_type", "linkedin"),
                )
                if len(candidatos) >= 5:
                    return candidatos
        return candidatos

    def _parse_browser_search_results(self, html: str) -> List[dict]:
        soup = BeautifulSoup(html, "lxml")
        resultados: List[dict] = []
        for a_tag in soup.select("a.result__a, a[data-testid='result-title-a'], a[href^='/url?q='], a[href^='http']"):
            href = self._clean_result_url(a_tag.get("href", ""))
            host = self._host(href)
            if not href or not host or "duckduckgo.com" in host:
                continue
            title = a_tag.get_text(" ", strip=True)[:180]
            if len(title) < 3:
                continue
            container = a_tag.find_parent(["article", "div", "li"])
            snippet = container.get_text(" ", strip=True)[:500] if container else ""
            source_type = "linkedin" if "linkedin.com" in host else "web"
            resultados.append({
                "title": title,
                "url": href,
                "snippet": snippet,
                "source_type": source_type,
            })
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
    def _extract_pdf_text(self, content: bytes) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            return " ".join((page.extract_text() or "") for page in reader.pages[:8])
        except Exception as exc:
            logger.debug(f"[instituciones_publicas] pdf error: {exc}")
            return ""

    def _extract_from_text(
        self,
        text: str,
        context: QueryContext,
        source_type: str,
        fuente: Optional[str],
        url: Optional[str],
    ) -> List[dict]:
        if not text:
            return []

        texto = re.sub(r"\s+", " ", text).strip()
        texto_norm = normalizar(texto)
        if not self._texto_relevante(texto_norm, context, source_type=source_type, fuente=fuente):
            return []

        hallazgos: Dict[str, float] = defaultdict(float)

        for pattern in INSTITUTION_PATTERNS:
            for match in pattern.finditer(texto):
                nombre = self._clean_institution_name(match.group(1))
                if nombre:
                    hallazgos[nombre] = max(hallazgos[nombre], self._base_score(source_type, fuente))

        for fragment in self._candidate_phrases(texto):
            nombre = self._clean_institution_name(fragment)
            if nombre:
                hallazgos[nombre] = max(hallazgos[nombre], self._base_score(source_type, fuente) - 0.1)

        host_candidate = self._institution_from_host(fuente, texto, context)
        if host_candidate:
            hallazgos[host_candidate] = max(hallazgos[host_candidate], self._base_score(source_type, fuente) - 0.05)

        resultados = []
        for nombre, score in hallazgos.items():
            if score < 0.45:
                continue
            resultados.append({
                "nombre": nombre,
                "confidence": round(min(0.98, score), 3),
                "source_type": source_type,
                "fuente": fuente,
                "url": url,
                "contexto": self._resumir_contexto(texto, nombre),
            })
        if resultados:
            logger.info(
                f"[instituciones_publicas] Candidatas extraidas | fuente={fuente} | source={source_type} | valores={', '.join(item['nombre'] for item in resultados[:4])}"
            )
        return resultados

    def _extract_from_title_segments(
        self,
        title: str,
        context: QueryContext,
        source_type: str,
        fuente: Optional[str],
        url: Optional[str],
    ) -> List[dict]:
        if not title:
            return []

        title_norm = normalizar(title)
        if not self._texto_relevante(title_norm, context, source_type=source_type, fuente=fuente):
            return []

        hallazgos: Dict[str, float] = defaultdict(float)
        segments = [seg.strip() for seg in re.split(r"\s+[|:\-–—]\s+", title) if seg.strip()]
        nombre_norm = normalizar(context.nombre)

        for segment in segments:
            seg_norm = normalizar(segment)
            if seg_norm == nombre_norm or seg_norm in nombre_norm:
                continue
            nombre = self._clean_institution_name(segment)
            if nombre:
                score = self._base_score(source_type, fuente) + 0.1
                hallazgos[nombre] = max(hallazgos[nombre], score)

        return [
            {
                "nombre": nombre,
                "confidence": round(min(0.98, score), 3),
                "source_type": source_type,
                "fuente": fuente,
                "url": url,
                "contexto": title[:220],
            }
            for nombre, score in hallazgos.items()
            if score >= 0.45
        ]

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
            text = script.get_text(" ", strip=True)
            if text:
                pieces.append(text[:600])
        return " ".join(piece for piece in pieces if piece)

    def _candidate_phrases(self, text: str) -> List[str]:
        phrases = []
        for part in re.split(r"[|,;·]|\s[-–—]\s", text):
            part = part.strip()
            if len(part) < 4:
                continue
            lower = part.lower()
            if any(token in lower for token in INSTITUTION_SUFFIXES):
                phrases.append(part[:100])
        return phrases[:10]

    def _clean_institution_name(self, value: str) -> Optional[str]:
        clean = re.sub(r"\s+", " ", value).strip(" -:|,.;")
        clean = re.sub(r"\s+\b(?:linkedin|perfil|profile)\b.*$", "", clean, flags=re.I).strip()
        clean = re.sub(r"^(?:en|at|de|del|de la|de los|de las|@)\s+", "", clean, flags=re.I).strip()
        clean = re.sub(r"^(?:la|el|los|las)\s+", "", clean, flags=re.I).strip()
        clean = re.sub(r"\b(?:chile|linkedin|official site|home page)\b", "", clean, flags=re.I).strip(" -:|,.;")
        if len(clean) < 3:
            return None
        lower = clean.lower()
        if any(x in lower for x in ("linkedin", "perfil", "ver perfil", "contacto")):
            return None
        if lower in {"chile", "santiago", "presidente", "director", "gerente"}:
            return None
        if not any(token in lower for token in INSTITUTION_SUFFIXES) and not re.search(r"\b[A-Z]{2,}\b", clean) and len(clean.split()) < 2:
            return None
        return clean[:120]

    def _institution_from_host(self, fuente: Optional[str], texto: str, context: QueryContext) -> Optional[str]:
        host = (fuente or "").lower()
        if not host or "linkedin.com" in host:
            return None
        if not self._texto_relevante(normalizar(texto), context, source_type="web", fuente=fuente):
            return None
        host = re.sub(r"^www\.", "", host)
        parts = [part for part in host.split(".") if part and part not in {"cl", "com", "org", "net", "edu", "gov", "gob"}]
        if not parts:
            return None
        candidate = " ".join(part.replace("-", " ") for part in parts[:2]).strip()
        if len(candidate) < 3:
            return None
        return candidate.title()

    def _base_score(self, source_type: str, fuente: Optional[str]) -> float:
        score = 0.35
        if source_type == "linkedin":
            score += 0.35
        elif source_type == "pdf":
            score += 0.3
        else:
            score += 0.2

        host = (fuente or "").lower()
        if any(hint in host for hint in HIGH_SIGNAL_DOMAINS):
            score += 0.15
        return score

    def _texto_relevante(self, texto_norm: str, context: QueryContext, source_type: str, fuente: Optional[str]) -> bool:
        palabras = [p for p in normalizar(context.nombre).split() if len(p) > 2]
        coincidencias = sum(1 for p in palabras if p in texto_norm)
        if source_type == "linkedin" or "linkedin.com" in (fuente or ""):
            return coincidencias >= max(1, min(2, len(palabras)))
        return coincidencias >= max(2, min(3, len(palabras)))

    def _nombre_simple(self, nombre: str) -> str:
        partes = nombre.split()
        if len(partes) >= 2:
            return f"{partes[0]} {partes[-1]}"
        return nombre

    def _nombre_ascii(self, nombre: str) -> str:
        return normalizar(nombre).title()

    def _resumir_contexto(self, texto: str, valor: str) -> Optional[str]:
        idx = texto.lower().find(valor.lower())
        if idx == -1:
            return None
        inicio = max(0, idx - 90)
        fin = min(len(texto), idx + len(valor) + 90)
        return texto[inicio:fin].strip()[:220]

    def _merge(self, target: Dict[str, dict], items: List[dict]) -> None:
        for item in items:
            key = normalizar(item["nombre"])
            prev = target.get(key)
            if not prev or (item.get("confidence") or 0.0) > (prev.get("confidence") or 0.0):
                target[key] = item

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
