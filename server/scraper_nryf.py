"""
scraper_nryf.py — nombrerutyfirma.com con undetected-chromedriver + caché en disco
Usa un perfil de Chrome separado para no interferir con tu Chrome normal,
y mueve la ventana fuera de pantalla vía AppleScript (macOS).
"""

import re
import time
import json
import os
import subprocess
import tempfile
from typing import Optional
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

BASE_URL       = "https://www.nombrerutyfirma.com"
CHROME_VERSION = 145
CACHE_FILE     = os.path.join(os.getcwd(), "cache_nryf.json")

# Perfil temporal separado — no toca tu Chrome personal
CHROME_PROFILE = os.path.join(tempfile.gettempdir(), "osint_chrome_profile")


# ── Mover ventana fuera de pantalla via AppleScript ───────────────────────────
def _mover_ventana_afuera():
    """Mueve la ventana de Chrome fuera de pantalla usando AppleScript."""
    script = '''
    tell application "Google Chrome"
        if (count of windows) > 0 then
            set bounds of front window to {-2000, -2000, -634, -1232}
        end if
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", script],
                      capture_output=True, timeout=3)
    except Exception:
        pass


# ── Caché en disco ─────────────────────────────────────────────────────────────
def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"[cache] {len(data)} entradas cargadas")
                return data
        except Exception as e:
            print(f"[cache] Error leyendo: {e}")
    return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"[cache] Guardado: {len(cache)} entradas en {CACHE_FILE}")
    except Exception as e:
        print(f"[cache] Error guardando: {e}")


# ── Driver ─────────────────────────────────────────────────────────────────────
def _get_driver() -> uc.Chrome:
    opts = uc.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1280,800")
    # Posición inicial muy fuera de pantalla
    opts.add_argument("--window-position=-3000,-3000")
    opts.add_argument("--lang=es-CL")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    # Perfil separado — no mezcla cookies con tu Chrome personal
    opts.add_argument(f"--user-data-dir={CHROME_PROFILE}")
    # Sin notificaciones ni popups
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-popup-blocking")
    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
    }
    opts.add_experimental_option("prefs", prefs)
    return uc.Chrome(options=opts, version_main=CHROME_VERSION)


# ── Parser ─────────────────────────────────────────────────────────────────────
def _parsear_tabla(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    tabla = soup.find("table")
    if not tabla:
        return []

    ths = [th.get_text(strip=True) for th in tabla.find_all("th")]
    print(f"[parser] Headers: {ths}")

    col: dict[str, int] = {}
    for i, txt in enumerate(th.lower() for th in ths):
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
    print(f"[parser] {len(resultados)} resultados")
    return resultados


# ── Scraper ────────────────────────────────────────────────────────────────────
def _buscar(term: str, es_rut: bool = False) -> str:
    driver = _get_driver()
    try:
        driver.get(BASE_URL)

        # Mover ventana fuera de pantalla via AppleScript apenas carga
        _mover_ventana_afuera()

        # Esperar que pase el challenge de Cloudflare
        try:
            WebDriverWait(driver, 25).until_not(
                EC.title_contains("Integrity Check")
            )
        except TimeoutException:
            pass

        # Volver a mover por si el challenge movió la ventana
        _mover_ventana_afuera()
        time.sleep(2)

        if es_rut:
            try:
                driver.find_element(By.CSS_SELECTOR, "a[href='#rut']").click()
                time.sleep(0.6)
            except Exception:
                pass

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
            WebDriverWait(driver, 20).until_not(
                EC.title_contains("Integrity Check")
            )
        except TimeoutException:
            pass

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tr td"))
            )
        except TimeoutException:
            pass

        time.sleep(1)
        html = driver.page_source
        print(f"[uc] URL: {driver.current_url} | Título: {driver.title}")
        return html

    except Exception as e:
        print(f"[uc] Error: {e}")
        return ""
    finally:
        driver.quit()


# ── API pública con caché ──────────────────────────────────────────────────────
def buscar_por_nombre(nombre: str) -> list[dict]:
    key = nombre.lower().strip()
    cache = _load_cache()

    if key in cache:
        print(f"[cache] HIT '{nombre}' → {len(cache[key])} resultados")
        return cache[key]

    print(f"[cache] MISS '{nombre}' → abriendo Chrome")
    resultados = _parsear_tabla(_buscar(nombre.strip()))
    cache[key] = resultados
    _save_cache(cache)
    return resultados


def buscar_por_rut(rut: str) -> Optional[dict]:
    rut_fmt = rut.strip().replace(".", "").upper()
    if "-" not in rut_fmt and len(rut_fmt) > 1:
        rut_fmt = rut_fmt[:-1] + "-" + rut_fmt[-1]

    key = rut_fmt.lower()
    cache = _load_cache()

    if key in cache:
        print(f"[cache] HIT rut '{rut_fmt}'")
        return cache[key]

    print(f"[cache] MISS rut '{rut_fmt}' → abriendo Chrome")
    resultados = _parsear_tabla(_buscar(rut_fmt, es_rut=True))
    resultado = resultados[0] if resultados else None
    cache[key] = resultado
    _save_cache(cache)
    return resultado


def limpiar_cache() -> int:
    cache = _load_cache()
    n = len(cache)
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    print(f"[cache] Limpiado — {n} entradas eliminadas")
    return n


# ── Test terminal ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python3 scraper_nryf.py <nombre o RUT>")
        print("     python3 scraper_nryf.py --limpiar-cache")
        sys.exit(1)

    if sys.argv[1] == "--limpiar-cache":
        print(f"Limpiadas {limpiar_cache()} entradas")
        sys.exit(0)

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
            print(f"  {r.get('nombre',''):40} {r.get('rut',''):15} {r.get('sexo',''):5} {r.get('ciudad','')}")