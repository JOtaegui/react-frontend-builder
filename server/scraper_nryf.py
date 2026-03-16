"""
scraper_nryf.py — Scraper para nombrerutyfirma.com
Usa undetected-chromedriver (Chrome real) para pasar Cloudflare Managed Challenge.

Instalación:
    pip install undetected-chromedriver selenium beautifulsoup4 lxml

Requiere: Google Chrome instalado en el sistema.
"""

import time
import re
from typing import Optional
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


BASE_URL = "https://www.nombrerutyfirma.com"


def get_driver() -> uc.Chrome:
    """Chrome real con undetected-chromedriver — pasa Cloudflare sin detección."""
    opts = uc.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1366,768")
    opts.add_argument("--lang=es-CL")
    # Sin headless — Chrome headless sigue siendo detectable por Cloudflare
    # La ventana se abre pero la movemos fuera de pantalla
    opts.add_argument("--window-position=-2000,0")
    return uc.Chrome(options=opts, version_main=145)  # debe coincidir con tu Chrome instalado


def _esperar_challenge(driver: uc.Chrome, timeout: int = 15) -> bool:
    """
    Espera a que Cloudflare resuelva el challenge.
    Retorna True si la página cargó correctamente.
    """
    try:
        # Esperar a que desaparezca el título de Cloudflare
        WebDriverWait(driver, timeout).until_not(
            EC.title_contains("Integrity Check")
        )
        WebDriverWait(driver, timeout).until_not(
            EC.title_contains("Just a moment")
        )
        return True
    except TimeoutException:
        print(f"[uc] Challenge no resuelto en {timeout}s. Título: {driver.title}")
        return False


def _parsear_tabla(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    tabla = soup.find("table")
    if not tabla:
        return []

    col: dict[str, int] = {}
    for i, th in enumerate(tabla.find_all("th")):
        txt = th.get_text(strip=True).lower()
        if "nombre"    in txt: col["nombre"] = i
        elif "rut"     in txt: col["rut"] = i
        elif "sexo"    in txt: col["sexo"] = i
        elif "direcci" in txt: col["direccion"] = i
        elif "ciudad"  in txt or "comuna" in txt: col["ciudad"] = i
    if not col:
        col = {"nombre": 0, "rut": 1, "sexo": 2, "direccion": 3, "ciudad": 4}

    resultados = []
    for fila in tabla.find_all("tr")[1:]:
        tds = [td.get_text(strip=True) for td in fila.find_all("td")]
        if len(tds) < 2:
            continue
        def gc(k):
            i = col.get(k)
            return tds[i] if i is not None and i < len(tds) and tds[i] else None
        if gc("nombre") and gc("rut"):
            resultados.append({
                "nombre":    gc("nombre"),
                "rut":       gc("rut"),
                "sexo":      gc("sexo"),
                "direccion": gc("direccion"),
                "ciudad":    gc("ciudad"),
            })
    return resultados


def buscar_por_nombre(nombre: str) -> list[dict]:
    driver = get_driver()
    try:
        # 1. Cargar la página principal (resuelve el challenge inicial)
        driver.get(BASE_URL)
        _esperar_challenge(driver, timeout=20)
        time.sleep(2)

        # 2. Escribir en el campo de búsqueda por nombre y enviar
        try:
            campo = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "form#valid input[name='term']"))
            )
            campo.clear()
            campo.send_keys(nombre.strip())
            campo.submit()
        except TimeoutException:
            print("[uc] No encontré el campo de búsqueda por nombre")
            return []

        # 3. Esperar resultados
        _esperar_challenge(driver, timeout=15)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tr td"))
            )
        except TimeoutException:
            pass  # Puede que no haya resultados

        time.sleep(1)
        html = driver.page_source
        print(f"[uc/nombre] URL final: {driver.current_url} | Título: {driver.title}")
        return _parsear_tabla(html)

    except Exception as e:
        print(f"[uc/nombre] Error: {e}")
        return []
    finally:
        driver.quit()


def buscar_por_rut(rut: str) -> Optional[dict]:
    rut_fmt = rut.strip().replace(".", "").upper()
    if "-" not in rut_fmt and len(rut_fmt) > 1:
        rut_fmt = rut_fmt[:-1] + "-" + rut_fmt[-1]

    driver = get_driver()
    try:
        driver.get(BASE_URL)
        _esperar_challenge(driver, timeout=20)
        time.sleep(2)

        # Click en la tab de RUT
        try:
            tab_rut = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='#rut']"))
            )
            tab_rut.click()
            time.sleep(0.5)
        except TimeoutException:
            pass

        # Escribir RUT
        try:
            campo = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "form#formato-live input[name='term']"))
            )
            campo.clear()
            campo.send_keys(rut_fmt)
            campo.submit()
        except TimeoutException:
            print("[uc] No encontré el campo de RUT")
            return None

        _esperar_challenge(driver, timeout=15)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tr td"))
            )
        except TimeoutException:
            pass

        time.sleep(1)
        html = driver.page_source
        resultados = _parsear_tabla(html)
        return resultados[0] if resultados else None

    except Exception as e:
        print(f"[uc/rut] Error: {e}")
        return None
    finally:
        driver.quit()


# ─── Test desde terminal ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python3 scraper_nryf.py <nombre o RUT>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    if re.match(r'^\d{6,9}-?[\dkK]$', query.replace(".", "")):
        print(f"\nBuscando RUT: {query}")
        r = buscar_por_rut(query)
        if r:
            for k, v in r.items():
                print(f"  {k:12}: {v}")
        else:
            print("  No encontrado")
    else:
        print(f"\nBuscando nombre: {query}")
        rs = buscar_por_nombre(query)
        print(f"  {len(rs)} resultados")
        for r in rs[:10]:
            print(f"  {r['nombre']:40} {r['rut']:15} {r.get('ciudad','')}")