"""
Módulo: NombreRutYFirma.com
Scraping del directorio público que indexa RUT, nombre, dirección y ciudad.

Estrategia de parsing (el sitio tiene 2 estructuras posibles):
  A) Tabla HTML clásica — /search?q=nombre
  B) Cards con divs    — /nombres/nombre-apellido

Si el sitio público bloquea o devuelve 404/500, cae a un scraper de navegador
basado en undetected-chromedriver, inspirado en el repositorio antiguo.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import logging
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from config import NRYF_BASE_URL, TIMEOUT_NRYF
from modules.base import BaseModule, QueryContext, ModuleResult
from utils.scraping import (
    limpiar_rut, extraer_emails, normalizar,
    parsear_tabla, detectar_bloqueo, get_with_retry,
)

logger = logging.getLogger(__name__)
CACHE_FILE = Path(__file__).resolve().parent.parent / "cache_nryf.json"
CHROME_PROFILE = Path(tempfile.gettempdir()) / "osint_chrome_profile"
RUT_REGEX = re.compile(r"\d{1,2}\.?\d{3}\.?\d{3}[-–][\dkK]")
CHROME_BINARY_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


class NRYFModule(BaseModule):
    name    = "nryf"
    timeout = TIMEOUT_NRYF

    async def run(self, context: QueryContext) -> ModuleResult:
        start = time.time()
        try:
            resultados = await self._buscar(context.nombre)

            rut_data = None
            if context.rut:
                rut_data = await self._buscar_rut(limpiar_rut(context.rut))

            # Deduplicar por RUT
            vistos: Set[str] = set()
            unicos = []
            for r in resultados:
                key = r.get("rut", "") or r.get("nombre", "")
                if key not in vistos:
                    vistos.add(key)
                    unicos.append(r)

            data: dict = {"nryf_nombre": unicos}
            if rut_data:
                data["nryf_rut"] = rut_data

            emails = extraer_emails(" ".join(str(v) for r in unicos for v in r.values()))
            if emails:
                data["emails"] = emails

            return self._result(data, len(unicos), start)

        except Exception as exc:
            return self._error_result(str(exc), start)

    # ── Búsquedas ────────────────────────────────────────────────────────────

    async def _buscar(self, nombre: str) -> List[dict]:
        """Prueba HTTP directo y luego navegador automatizado si el sitio bloquea."""
        urls = [
            f"{NRYF_BASE_URL}/search?q={quote_plus(nombre)}",
            f"{NRYF_BASE_URL}/nombres/{quote_plus(nombre.lower().replace(' ', '-'))}",
            f"{NRYF_BASE_URL}/buscar?nombre={quote_plus(nombre)}",
        ]
        for url in urls:
            resp = await get_with_retry(self.client, url, timeout=self.timeout)
            if not resp:
                continue
            if detectar_bloqueo(resp.text):
                logger.warning(f"[nryf] Bloqueo detectado en {url}")
                continue
            resultados = self._parsear(resp.text, nombre)
            if resultados:
                return resultados
        logger.info("[nryf] HTTP directo sin resultados; probando navegador automatizado")
        return await asyncio.to_thread(self._buscar_con_navegador, nombre, False)

    async def _buscar_rut(self, rut: str) -> Optional[dict]:
        url = f"{NRYF_BASE_URL}/rut/{quote_plus(rut)}"
        resp = await get_with_retry(self.client, url, timeout=self.timeout)
        resultados: List[dict] = []
        if resp and not detectar_bloqueo(resp.text):
            resultados = self._parsear(resp.text, rut)
        if not resultados:
            logger.info("[nryf] Búsqueda HTTP por RUT sin resultados; probando navegador automatizado")
            resultados = await asyncio.to_thread(self._buscar_con_navegador, rut, True)
        return resultados[0] if resultados else None

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parsear(self, html: str, query: str) -> List[dict]:
        soup = BeautifulSoup(html, "lxml")

        # Estrategia A: tabla con columnas conocidas
        resultados = self._parsear_tabla(soup, query)
        if resultados:
            return resultados

        # Estrategia B: cards / divs
        return self._parsear_cards(soup, query)

    def _parsear_tabla(self, soup: BeautifulSoup, query: str) -> List[dict]:
        """Parsea tabla HTML con columnas Nombre|RUT|Sexo|Dirección|Ciudad."""
        # Columnas esperadas si no hay <th>
        COLS = ["nombre", "rut", "sexo", "direccion", "ciudad"]

        for tabla in soup.find_all("table"):
            filas = parsear_tabla(tabla, columnas=COLS)
            if not filas:
                continue

            resultados = []
            for fila in filas:
                nombre = (fila.get("nombre") or fila.get("col_0", "")).strip()
                rut    = (fila.get("rut")    or fila.get("col_1", "")).strip()

                if not nombre or not rut:
                    continue
                if not self._es_relevante(nombre, query):
                    continue

                resultados.append({
                    "nombre":    nombre[:100],
                    "rut":       rut,
                    "sexo":      fila.get("sexo")     or fila.get("col_2") or None,
                    "direccion": fila.get("direccion")or fila.get("col_3") or None,
                    "ciudad":    fila.get("ciudad")   or fila.get("col_4") or None,
                })
            if resultados:
                return resultados[:20]

        return []

    def _parsear_cards(self, soup: BeautifulSoup, query: str) -> List[dict]:
        """Parsea resultados presentados como cards/divs."""
        RUT_RE = re.compile(r"\d{1,2}\.?\d{3}\.?\d{3}[-–][\dkK]")

        candidatos = soup.find_all(
            ["div", "li", "article"],
            class_=re.compile(r"person|result|card|item|row", re.I),
        )

        resultados = []
        for card in candidatos:
            texto = card.get_text(separator=" | ", strip=True)
            rut_match = RUT_RE.search(texto)
            if not rut_match:
                continue

            # Nombre: todo lo anterior al RUT
            nombre_raw = texto[:rut_match.start()].replace("|", " ").strip()
            nombre_raw = re.sub(r"\s+", " ", nombre_raw)[:80]

            if not nombre_raw or not self._es_relevante(nombre_raw, query):
                continue

            # Ciudad: último fragmento que parece una ciudad
            partes = [p.strip() for p in texto[rut_match.end():].split("|") if p.strip()]
            ciudad = partes[-1][:60] if partes else None
            dir_   = partes[0][:120] if len(partes) > 1 else None

            resultados.append({
                "nombre":    nombre_raw,
                "rut":       rut_match.group(),
                "sexo":      None,
                "direccion": dir_,
                "ciudad":    ciudad,
            })

        return resultados[:20]

    def _es_relevante(self, nombre_candidato: str, query: str) -> bool:
        """Al menos la mitad de las palabras del query deben aparecer en el nombre."""
        palabras_query = normalizar(query).split()
        nombre_norm    = normalizar(nombre_candidato)
        matches = sum(1 for p in palabras_query if p in nombre_norm)
        return matches >= max(1, len(palabras_query) // 2)

    # ── Fallback con navegador ───────────────────────────────────────────────

    def _buscar_con_navegador(self, term: str, es_rut: bool) -> List[dict]:
        cache_key = self._cache_key(term, es_rut)
        cache = self._load_cache()
        cached = cache.get(cache_key)
        if isinstance(cached, list) and cached:
            logger.info(f"[nryf] Cache HIT para '{term}'")
            return cached

        html = self._fetch_html_con_driver(term, es_rut)
        if not html:
            return []

        resultados = self._parsear_tabla_browser(html)
        if not resultados:
            resultados = self._parsear(html, term)

        if resultados:
            cache[cache_key] = resultados
            self._save_cache(cache)
        return resultados

    def _fetch_html_con_driver(self, term: str, es_rut: bool) -> str:
        try:
            import undetected_chromedriver as uc
            from selenium.common.exceptions import TimeoutException
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            logger.warning(
                "[nryf] Fallback browser no disponible; instala selenium y undetected-chromedriver: %s",
                exc,
            )
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
                logger.info(f"[nryf] Usando Chrome major version {version_main}")

            driver = uc.Chrome(
                options=opts,
                version_main=version_main,
                use_subprocess=True,
            )
            driver.get(NRYF_BASE_URL)
            self._mover_ventana_afuera()

            try:
                WebDriverWait(driver, 25).until_not(EC.title_contains("Integrity Check"))
            except TimeoutException:
                pass

            if es_rut:
                try:
                    driver.find_element(By.CSS_SELECTOR, "a[href='#rut']").click()
                    time.sleep(0.6)
                except Exception:
                    logger.debug("[nryf] No se pudo cambiar al formulario por RUT")

            selector = "form#formato-live input[name='term']" if es_rut else "form#valid input[name='term']"
            try:
                campo = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
            except TimeoutException:
                campo = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='term']"))
                )

            campo.clear()
            campo.send_keys(term)
            campo.submit()

            try:
                WebDriverWait(driver, 20).until_not(EC.title_contains("Integrity Check"))
            except TimeoutException:
                pass

            try:
                WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table tr td"))
                )
            except TimeoutException:
                logger.debug("[nryf] No apareció tabla; se intentará parsear el HTML igual")

            time.sleep(1)
            logger.info(f"[nryf] Browser URL final: {driver.current_url}")
            return driver.page_source
        except Exception as exc:
            logger.warning(f"[nryf] Error en fallback browser: {exc}")
            return ""
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _parsear_tabla_browser(self, html: str) -> List[dict]:
        soup = BeautifulSoup(html, "lxml")
        tabla = soup.find("table")
        if not tabla:
            return []

        headers = [th.get_text(strip=True) for th in tabla.find_all("th")]
        col: Dict[str, int] = {}
        for i, txt in enumerate(h.lower() for h in headers):
            if "nombre" in txt:
                col["nombre"] = i
            elif "rut" in txt:
                col["rut"] = i
            elif "sexo" in txt:
                col["sexo"] = i
            elif "direcci" in txt:
                col["direccion"] = i
            elif "ciudad" in txt or "comuna" in txt:
                col["ciudad"] = i

        if not col:
            col = {"nombre": 0, "rut": 1, "sexo": 2, "direccion": 3, "ciudad": 4}

        resultados: List[dict] = []
        for fila in tabla.find_all("tr")[1:]:
            tds = [td.get_text(strip=True) for td in fila.find_all("td")]
            if len(tds) < 2:
                continue

            def get_col(key: str) -> Optional[str]:
                idx = col.get(key)
                if idx is None or idx >= len(tds):
                    return None
                return tds[idx] or None

            nombre = get_col("nombre")
            rut = get_col("rut")
            if nombre and rut and RUT_REGEX.search(rut):
                resultados.append({
                    "nombre": nombre[:100],
                    "rut": rut,
                    "sexo": get_col("sexo"),
                    "direccion": get_col("direccion"),
                    "ciudad": get_col("ciudad"),
                })
        return resultados

    def _cache_key(self, term: str, es_rut: bool) -> str:
        valor = limpiar_rut(term) if es_rut else normalizar(term)
        return f"{'rut' if es_rut else 'nombre'}:{valor}"

    def _load_cache(self) -> Dict[str, Any]:
        if not CACHE_FILE.exists():
            return {}
        try:
            contenido = CACHE_FILE.read_text(encoding="utf-8").strip()
            return json.loads(contenido) if contenido else {}
        except Exception as exc:
            logger.warning(f"[nryf] Error leyendo cache; se ignorará: {exc}")
            return {}

    def _save_cache(self, cache: Dict[str, Any]) -> None:
        try:
            CACHE_FILE.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"[nryf] Error guardando cache: {exc}")

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
