from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup
from typing import Optional
import codecs

from dorks import router as dorks_router
from osint import router as osint_router
from debug import router as debug_router

app = FastAPI(title="Huella Digital API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dorks_router)
app.include_router(osint_router)
app.include_router(debug_router)

HEADERS_GET = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.rutificador.com/",
}

HEADERS_POST = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Alt-Used": "www.nombrerutyfirma.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://www.nombrerutyfirma.com/",
    "Origin": "https://www.nombrerutyfirma.com",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9",
}


# ─── Modelos ──────────────────────────────────────────────────────────────────
class PersonaRut(BaseModel):
    nombre: str
    rut: str
    sexo: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    fuente: str

class SearchResponse(BaseModel):
    query: str
    total: int
    resultados: list[PersonaRut]
    mensaje: Optional[str] = None


# ─── Utils ────────────────────────────────────────────────────────────────────
def format_rut(rut: str) -> str:
    """Limpia y formatea un RUT: 12345678-9"""
    rut = rut.strip().replace(".", "").replace(" ", "")
    if "-" not in rut and len(rut) > 1:
        rut = rut[:-1] + "-" + rut[-1]
    return rut.upper()


# ─── Scraper 1: rutificador.com (búsqueda por NOMBRE) ────────────────────────
async def scrape_rutificador(nombre: str) -> list[PersonaRut]:
    nombre_url = nombre.strip().replace(" ", "%20")
    url = f"https://www.rutificador.com/buscar.php?tipoBusqueda=nombres&nombre={nombre_url}&pagina=1"

    async with httpx.AsyncClient(headers=HEADERS_GET, follow_redirects=True, timeout=15.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Error rutificador.com: {e.response.status_code}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Sin conexión a rutificador.com: {str(e)}")

    soup = BeautifulSoup(response.text, "html.parser")
    resultados: list[PersonaRut] = []

    # Encontrar tabla con datos de personas
    tabla_resultados = None
    for tabla in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in tabla.find_all("th")]
        if any(h in headers for h in ["nombre", "rut", "nombres"]):
            tabla_resultados = tabla
            break

    if not tabla_resultados:
        tablas = soup.find_all("table")
        if tablas:
            tabla_resultados = max(tablas, key=lambda t: len(t.find_all("tr")))

    if not tabla_resultados:
        return resultados

    # Detectar índice de cada columna desde los <th>
    col_index: dict[str, int] = {}
    for i, th in enumerate(tabla_resultados.find_all("th")):
        texto = th.get_text(strip=True).lower()
        if "nombre" in texto:       col_index["nombre"] = i
        elif "rut" in texto:        col_index["rut"] = i
        elif "sexo" in texto:       col_index["sexo"] = i
        elif "direcci" in texto:    col_index["direccion"] = i
        elif "ciudad" in texto or "comuna" in texto: col_index["ciudad"] = i

    # Orden por defecto de rutificador.com si no detectó headers
    if not col_index:
        col_index = {"nombre": 0, "rut": 1, "sexo": 2, "direccion": 3, "ciudad": 4}

    for fila in tabla_resultados.find_all("tr")[1:]:
        celdas = [td.get_text(strip=True) for td in fila.find_all("td")]
        if len(celdas) < 2:
            continue

        def get_col(key: str) -> Optional[str]:
            idx = col_index.get(key)
            if idx is None or idx >= len(celdas):
                return None
            return celdas[idx] or None

        nombre_persona = get_col("nombre")
        rut_persona    = get_col("rut")
        if nombre_persona and rut_persona:
            resultados.append(PersonaRut(
                nombre=nombre_persona,
                rut=rut_persona,
                sexo=get_col("sexo"),
                direccion=get_col("direccion"),
                ciudad=get_col("ciudad"),
                fuente="rutificador.com",
            ))

    return resultados


# ─── Scraper 2: nombrerutyfirma.com (búsqueda por RUT) ───────────────────────
async def scrape_nombrerutyfirma(rut: str) -> Optional[PersonaRut]:
    rut_formateado = format_rut(rut)

    # URL ofuscada con rot13 (igual que el script original)
    url_rot = "uggcf://jjj.abzoerehglsvezn.pbz/ehg"
    url     = codecs.decode(url_rot, "rot_13")  # https://www.nombrerutyfirma.com/rut

    async with httpx.AsyncClient(
        headers=HEADERS_POST,
        follow_redirects=True,
        timeout=15.0,
    ) as client:
        try:
            response = await client.post(
                url,
                data={"term": rut_formateado},  # body form-urlencoded
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # No lanzamos excepción global, simplemente no hay datos
            print(f"[nombrerutyfirma] HTTP {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            print(f"[nombrerutyfirma] Error de conexión: {e}")
            return None

    soup = BeautifulSoup(response.content, "html.parser")

    # El script original buscaba <tr tabindex="1"> con los <td> dentro
    fila = soup.find("tr", {"tabindex": "1"})

    # Fallback: buscar en tbody si cambió la estructura
    if not fila:
        for tabla in soup.find_all("table"):
            filas = tabla.find_all("tr")
            for f in filas:
                tds = f.find_all("td")
                if len(tds) >= 3:
                    fila = f
                    break
            if fila:
                break

    if not fila:
        return None

    tds = fila.find_all("td")
    if len(tds) < 2:
        return None

    return PersonaRut(
        nombre    = tds[0].get_text(strip=True) if len(tds) > 0 else "",
        rut       = tds[1].get_text(strip=True) if len(tds) > 1 else rut_formateado,
        sexo      = tds[2].get_text(strip=True) if len(tds) > 2 else None,
        direccion = tds[3].get_text(strip=True) if len(tds) > 3 else None,
        ciudad    = tds[4].get_text(strip=True) if len(tds) > 4 else None,
        fuente    = "nombrerutyfirma.com",
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "ok", "mensaje": "Huella Digital API activa"}


@app.get("/api/search/rut", response_model=SearchResponse)
async def buscar_por_nombre(
    nombre: str = Query(..., min_length=2, description="Nombre a buscar en rutificador.com"),
):
    """Busca personas por nombre. Fuente: rutificador.com"""
    resultados = await scrape_rutificador(nombre)
    return SearchResponse(
        query=nombre,
        total=len(resultados),
        resultados=resultados,
        mensaje=None if resultados else "No se encontraron resultados.",
    )


@app.get("/api/search/nryf", response_model=SearchResponse)
async def buscar_por_rut(
    rut: str = Query(..., min_length=7, description="RUT a buscar en nombrerutyfirma.com (ej: 12345678-9)"),
):
    """Busca persona por RUT. Fuente: nombrerutyfirma.com (inscripción SERVEL)"""
    resultado = await scrape_nombrerutyfirma(rut)
    resultados = [resultado] if resultado else []
    return SearchResponse(
        query=rut,
        total=len(resultados),
        resultados=resultados,
        mensaje=None if resultados else "No encontrado o no inscrito en SERVEL.",
    )


@app.get("/api/search/full")
async def buscar_completo(
    nombre: str = Query(..., min_length=2),
    rut: Optional[str] = Query(None, description="RUT opcional para cruzar con nombrerutyfirma.com"),
):
    """
    Búsqueda combinada: nombre en rutificador + RUT en nombrerutyfirma (si se provee).
    """
    import asyncio

    tasks = [scrape_rutificador(nombre)]
    if rut:
        tasks.append(scrape_nombrerutyfirma(rut))  # type: ignore

    resultados_raw = await asyncio.gather(*tasks, return_exceptions=True)

    rutificador_res = resultados_raw[0] if not isinstance(resultados_raw[0], Exception) else []
    nryf_res = resultados_raw[1] if len(resultados_raw) > 1 and not isinstance(resultados_raw[1], Exception) else None

    return {
        "query": nombre,
        "fuentes": {
            "rutificador.com": {
                "total": len(rutificador_res),          # type: ignore
                "resultados": [r.model_dump() for r in rutificador_res],  # type: ignore
            },
            "nombrerutyfirma.com": {
                "total": 1 if nryf_res else 0,
                "resultado": nryf_res.model_dump() if nryf_res else None,
                "nota": "Solo disponible con RUT" if not rut else None,
            },
        },
    }