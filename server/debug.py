"""
debug.py — Endpoints temporales para diagnosticar qué devuelven las fuentes
Agregar a main.py: from debug import router as debug_router + app.include_router(debug_router)
SOLO PARA DESARROLLO — remover en producción
"""

from fastapi import APIRouter, Query
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup

router = APIRouter(prefix="/debug", tags=["Debug"])

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

@router.get("/rutificador")
async def debug_rutificador(nombre: str = Query(...)):
    """Ver HTML crudo + tablas que devuelve rutificador"""
    url = f"https://www.rutificador.com/buscar.php?tipoBusqueda=nombres&nombre={quote_plus(nombre)}&pagina=1"
    async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
        r = await client.get(url, headers={
            "User-Agent": UA,
            "Accept-Language": "es-CL,es;q=0.9",
            "Referer": "https://www.rutificador.com/",
        })

    soup = BeautifulSoup(r.text, "html.parser")
    tablas = soup.find_all("table")

    info = {
        "status_code": r.status_code,
        "url_final": str(r.url),
        "encoding": r.encoding,
        "total_tablas": len(tablas),
        "tablas": [],
        "title": soup.title.string if soup.title else None,
        # Primeros 3000 chars del HTML para ver qué llegó
        "html_preview": r.text[:3000],
    }

    for i, tabla in enumerate(tablas):
        ths = [th.get_text(strip=True) for th in tabla.find_all("th")]
        filas = tabla.find_all("tr")
        primera_fila = []
        if len(filas) > 1:
            primera_fila = [td.get_text(strip=True) for td in filas[1].find_all("td")]

        info["tablas"].append({
            "tabla_index": i,
            "headers": ths,
            "total_filas": len(filas),
            "primera_fila_data": primera_fila,
        })

    return info


@router.get("/raw-html")
async def raw_html(url: str = Query(...)):
    """Obtener HTML crudo de cualquier URL pública"""
    async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
        r = await client.get(url, headers={"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9"})
    soup = BeautifulSoup(r.text, "html.parser")
    tablas = soup.find_all("table")
    return {
        "status": r.status_code,
        "url_final": str(r.url),
        "title": soup.title.string if soup.title else None,
        "total_tablas": len(tablas),
        "tablas_resumen": [
            {
                "index": i,
                "headers": [th.get_text(strip=True) for th in t.find_all("th")],
                "filas": len(t.find_all("tr")),
                "muestra": [[td.get_text(strip=True) for td in f.find_all("td")] for f in t.find_all("tr")[1:4]],
            }
            for i, t in enumerate(tablas)
        ],
        "html_preview": r.text[:4000],
    }


@router.get("/nryf")
async def debug_nryf(nombre: str = Query(...)):
    """Probar búsqueda por nombre en nombrerutyfirma.com via curl_cffi"""
    from curl_cffi.requests import AsyncSession

    url = "https://www.nombrerutyfirma.com/nombre"
    async with AsyncSession(impersonate="chrome124") as s:
        r = await s.post(url, data={"term": nombre}, headers={
            "Referer": "https://www.nombrerutyfirma.com/",
            "Content-Type": "application/x-www-form-urlencoded",
        }, timeout=15)

    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    tablas = soup.find_all("table")

    return {
        "status": r.status_code,
        "title": soup.title.string if soup.title else None,
        "total_tablas": len(tablas),
        "tablas": [
            {
                "index": i,
                "headers": [th.get_text(strip=True) for th in t.find_all("th")],
                "filas": len(t.find_all("tr")),
                "muestra": [[td.get_text(strip=True) for td in f.find_all("td")] for f in t.find_all("tr")[1:4]],
            }
            for i, t in enumerate(tablas)
        ],
        "html_preview": html[:2000],
    }