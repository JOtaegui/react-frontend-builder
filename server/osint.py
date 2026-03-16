"""
osint.py — Motor OSINT multi-fuente para Chile
Fuentes que funcionan sin Cloudflare:
  - SERVEL (padrón electoral por RUT)
  - SII (estado tributario por RUT)
  - Registro de Empresas (por nombre)
  - Poder Judicial (por nombre)
  - Diario Oficial (por nombre, Google Search)

Nota: rutificador.com y nombrerutyfirma.com tienen Cloudflare Managed Challenge
que requiere JS real — no se pueden scrapear sin un browser físico.
La búsqueda por nombre requiere RUT como entrada.
"""

import asyncio
import re
from typing import Optional
from urllib.parse import quote_plus

import httpx
import asyncio as _asyncio
from concurrent.futures import ThreadPoolExecutor
import scraper_nryf
from bs4 import BeautifulSoup
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from curl_cffi.requests import AsyncSession

router = APIRouter(prefix="/api/osint", tags=["OSINT Motor"])

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

def hdr(referer: str = "") -> dict:
    h = {
        "User-Agent": UA,
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if referer:
        h["Referer"] = referer
    return h


# ══════════════════════════════════════════════════════════════════════════════
# MODELOS
# ══════════════════════════════════════════════════════════════════════════════
class PersonaBase(BaseModel):
    nombre: Optional[str] = None
    rut: Optional[str] = None
    sexo: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None

class ServelResult(BaseModel):
    nombre: str
    rut: str
    circunscripcion: Optional[str] = None
    region: Optional[str] = None
    mesa: Optional[str] = None
    local: Optional[str] = None
    direccion_local: Optional[str] = None

class SIIResult(BaseModel):
    nombre: Optional[str] = None
    actividad: Optional[str] = None
    contribuyente_iva: Optional[bool] = None
    inicio_actividades: Optional[str] = None

class EmpresaResult(BaseModel):
    razon_social: str
    rut_empresa: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None

class PjudResult(BaseModel):
    rol: str
    tribunal: str
    materia: Optional[str] = None
    estado: Optional[str] = None
    fecha: Optional[str] = None

class DiarioOficialResult(BaseModel):
    titulo: str
    url: str
    fecha: Optional[str] = None
    descripcion: Optional[str] = None

class OSINTResponse(BaseModel):
    query: str
    rut: Optional[str] = None
    fuentes: dict
    resumen: dict


# ══════════════════════════════════════════════════════════════════════════════
# UTILS
# ══════════════════════════════════════════════════════════════════════════════
def fmt_rut(rut: str) -> tuple[str, str]:
    """Devuelve (numero_sin_dv, dv)"""
    clean = rut.strip().replace(".", "").replace("-", "").upper()
    return clean[:-1], clean[-1]


# ══════════════════════════════════════════════════════════════════════════════
# FUENTE 1 — SERVEL (padrón electoral por RUT)
# ══════════════════════════════════════════════════════════════════════════════
async def fuente_servel(rut: str, client: httpx.AsyncClient) -> Optional[ServelResult]:
    num, dv = fmt_rut(rut)
    if not num:
        return None

    # Endpoint 1: ww2.servel.cl
    urls_a_probar = [
        ("GET",  f"https://ww2.servel.cl/padron-electoral/?rut={num}{dv}", None),
        ("POST", "https://consulta.servel.cl/padron", {"rut": num, "dv": dv}),
    ]

    html = ""
    for method, url, data in urls_a_probar:
        try:
            if method == "GET":
                r = await client.get(url, headers=hdr("https://ww2.servel.cl/"), timeout=10)
            else:
                r = await client.post(url, data=data,
                    headers={**hdr("https://consulta.servel.cl/"), "Content-Type": "application/x-www-form-urlencoded"},
                    timeout=10)
            if r.status_code == 200:
                html = r.text
                break
        except Exception as e:
            print(f"[servel] {url}: {e}")
            continue

    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    res: dict = {}

    for row in soup.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) == 2:
            k = tds[0].get_text(strip=True).lower()
            v = tds[1].get_text(strip=True)
            if "nombre"      in k: res["nombre"] = v
            elif "rut"       in k: res["rut"] = v
            elif "circunscri"in k: res["circunscripcion"] = v
            elif "regi"      in k: res["region"] = v
            elif "mesa"      in k: res["mesa"] = v
            elif "local"     in k: res["local"] = v
            elif "direcci"   in k: res["direccion_local"] = v

    if not res.get("nombre"):
        return None

    return ServelResult(
        nombre=res.get("nombre", ""),
        rut=res.get("rut", rut),
        circunscripcion=res.get("circunscripcion"),
        region=res.get("region"),
        mesa=res.get("mesa"),
        local=res.get("local"),
        direccion_local=res.get("direccion_local"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# FUENTE 2 — SII (estado tributario público por RUT)
# ══════════════════════════════════════════════════════════════════════════════
async def fuente_sii(rut: str, client: httpx.AsyncClient) -> Optional[SIIResult]:
    num, dv = fmt_rut(rut)
    url = f"https://zeus.sii.cl/cvc_cgi/stc/getstc?RUT={num}&DV={dv}&PRG=STC&OPC=NOR"
    try:
        r = await client.get(url, headers=hdr("https://www.sii.cl/"), timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[sii] {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    texto = soup.get_text(" ", strip=True)
    res: dict = {}

    m = re.search(r"Nombre\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ][^\n\r]{3,60}?)(?:\s{2,}|Rut|$)", texto)
    if m: res["nombre"] = m.group(1).strip()

    m = re.search(r"(?:Actividad|Giro)\s*[:\-]?\s*(.+?)(?:\s{2,}|$)", texto)
    if m: res["actividad"] = m.group(1).strip()[:120]

    if "IVA" in texto: res["contribuyente_iva"] = True

    m = re.search(r"Inicio\s+(?:de\s+)?Actividades?\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", texto)
    if m: res["inicio_actividades"] = m.group(1)

    return SIIResult(**res) if res else None


# ══════════════════════════════════════════════════════════════════════════════
# FUENTE 3 — Registro de Empresas (por nombre)
# ══════════════════════════════════════════════════════════════════════════════
async def fuente_empresas(nombre: str, client: httpx.AsyncClient) -> list[EmpresaResult]:
    url = "https://www.registrodeempresasysociedades.cl/BuscarActuaciones2.aspx"
    try:
        r = await client.get(url, params={"NombreEmpresa": nombre},
                             headers=hdr("https://www.registrodeempresasysociedades.cl/"), timeout=12)
        r.raise_for_status()
    except Exception as e:
        print(f"[empresas] {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    res = []
    for tabla in soup.find_all("table"):
        for fila in tabla.find_all("tr")[1:]:
            tds = [td.get_text(strip=True) for td in fila.find_all("td")]
            if len(tds) >= 2 and tds[0]:
                res.append(EmpresaResult(
                    razon_social=tds[0],
                    rut_empresa=tds[1] if len(tds) > 1 else None,
                    tipo=tds[2]        if len(tds) > 2 else None,
                    estado=tds[3]      if len(tds) > 3 else None,
                ))
    return res[:10]


# ══════════════════════════════════════════════════════════════════════════════
# FUENTE 4 — Poder Judicial (por nombre)
# ══════════════════════════════════════════════════════════════════════════════
async def fuente_pjud(nombre: str, client: httpx.AsyncClient) -> list[PjudResult]:
    partes = nombre.strip().split()
    payload = {
        "filtro_busqueda": "nombre",
        "primer_nombre":    partes[0] if len(partes) > 0 else "",
        "segundo_nombre":   partes[1] if len(partes) > 1 else "",
        "primer_apellido":  partes[2] if len(partes) > 2 else "",
        "segundo_apellido": partes[3] if len(partes) > 3 else "",
        "tipo_tribunal": "Civil",
        "btn_buscar": "Buscar",
    }
    try:
        r = await client.post(
            "https://oficinajudicialvirtual.pjud.cl/indexN.php",
            data=payload,
            headers={**hdr("https://oficinajudicialvirtual.pjud.cl/"), "Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[pjud] {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    res = []
    for tabla in soup.find_all("table"):
        for fila in tabla.find_all("tr")[1:]:
            tds = [td.get_text(strip=True) for td in fila.find_all("td")]
            if len(tds) >= 3:
                res.append(PjudResult(
                    rol=tds[0], tribunal=tds[1],
                    materia=tds[2] if len(tds) > 2 else None,
                    estado=tds[3]  if len(tds) > 3 else None,
                    fecha=tds[4]   if len(tds) > 4 else None,
                ))
    return res[:10]


# ══════════════════════════════════════════════════════════════════════════════
# FUENTE 5 — Diario Oficial (Google Search público)
# ══════════════════════════════════════════════════════════════════════════════
async def fuente_diario_oficial(nombre: str) -> list[DiarioOficialResult]:
    """Busca menciones en el Diario Oficial via Google."""
    query = f'site:diariooficial.interior.gob.cl "{nombre}"'
    url = f"https://www.google.com/search?q={quote_plus(query)}&num=5&hl=es"
    try:
        async with AsyncSession(impersonate="chrome124") as s:
            r = await s.get(url, headers={
                "User-Agent": UA,
                "Accept-Language": "es-CL,es;q=0.9",
                "Referer": "https://www.google.com/",
            }, timeout=12)
    except Exception as e:
        print(f"[diario_oficial] {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    res = []
    for g in soup.select("div.g, div[data-sokoban-container]")[:5]:
        a = g.find("a", href=True)
        h3 = g.find("h3")
        desc = g.find("div", {"data-sncf": True}) or g.find("span", class_=re.compile("st|snippet"))
        if a and h3:
            res.append(DiarioOficialResult(
                titulo=h3.get_text(strip=True),
                url=a["href"],
                descripcion=desc.get_text(strip=True)[:200] if desc else None,
            ))
    return res


# ══════════════════════════════════════════════════════════════════════════════
# MOTOR PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
async def run_osint(nombre: str, rut: Optional[str] = None) -> dict:
    limits  = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    timeout = httpx.Timeout(15.0)

    # scraper_nryf usa Selenium (síncrono) — corre en thread pool para no bloquear FastAPI
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=2) as pool:
        # Lanzar scraper en background mientras corren las otras fuentes
        nryf_nombre_future = loop.run_in_executor(pool, scraper_nryf.buscar_por_nombre, nombre)
        nryf_rut_future    = loop.run_in_executor(pool, scraper_nryf.buscar_por_rut, rut) if rut else None

        # Fuentes HTTP en paralelo
        async with httpx.AsyncClient(limits=limits, timeout=timeout, follow_redirects=True) as client:
            empresas_res, pjud_res, diario_res, servel_res, sii_res = await asyncio.gather(
                fuente_empresas(nombre, client),
                fuente_pjud(nombre, client),
                fuente_diario_oficial(nombre),
                fuente_servel(rut, client) if rut else asyncio.sleep(0),
                fuente_sii(rut, client)    if rut else asyncio.sleep(0),
                return_exceptions=True,
            )

        # Esperar scraper (corre en paralelo con las fuentes HTTP)
        nryf_nombre_res = await nryf_nombre_future
        nryf_rut_res    = await nryf_rut_future if nryf_rut_future else None

    def safe(v, default):
        return default if isinstance(v, Exception) or v is None else v

    return {
        "nryf_nombre":    nryf_nombre_res if isinstance(nryf_nombre_res, list) else [],
        "nryf_rut":       nryf_rut_res if isinstance(nryf_rut_res, dict) else None,
        "servel":         safe(servel_res, None),
        "sii":            safe(sii_res, None),
        "empresas":       [e.model_dump() for e in safe(empresas_res, [])],
        "pjud":           [p.model_dump() for p in safe(pjud_res, [])],
        "diario_oficial": [d.model_dump() for d in safe(diario_res, [])],
    }


def build_resumen(data: dict, rut: Optional[str]) -> dict:
    fuentes = []
    if data["nryf_nombre"]:      fuentes.append(f"nombrerutyfirma.com ({len(data['nryf_nombre'])} personas)")
    if data["nryf_rut"]:         fuentes.append("nombrerutyfirma.com (por RUT)")
    if data["servel"]:          fuentes.append("SERVEL (padrón electoral)")
    if data["sii"]:             fuentes.append("SII (estado tributario)")
    if data["empresas"]:        fuentes.append(f"Registro Empresas ({len(data['empresas'])})")
    if data["pjud"]:            fuentes.append(f"PJUD ({len(data['pjud'])} causas)")
    if data["diario_oficial"]:  fuentes.append(f"Diario Oficial ({len(data['diario_oficial'])} menciones)")

    total = (
        len(data["nryf_nombre"]) +
        (1 if data["nryf_rut"] else 0) +
        (1 if data["servel"] else 0) +
        (1 if data["sii"] else 0) +
        len(data["empresas"]) +
        len(data["pjud"]) +
        len(data["diario_oficial"])
    )

    return {
        "total_hallazgos": total,
        "fuentes_con_datos": fuentes,
        "rut_consultado": rut,
        "tiene_antecedentes_judiciales": len(data["pjud"]) > 0,
        "tiene_actividad_empresarial": len(data["empresas"]) > 0,
        "inscrito_servel": data["servel"] is not None,
        "activo_sii": data["sii"] is not None,
        "advertencia": None if rut else "Sin RUT: SERVEL y SII no disponibles. Ingresa el RUT para consulta completa.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════
@router.get("", response_model=OSINTResponse)
async def busqueda_completa(
    nombre: str = Query(..., min_length=3, description="Nombre completo"),
    rut: Optional[str] = Query(None, description="RUT opcional (ej: 12345678-9). Habilita SERVEL y SII."),
):
    """
    Motor OSINT completo.
    - Sin RUT: consulta Empresas, PJUD y Diario Oficial
    - Con RUT: agrega SERVEL (padrón electoral) y SII (estado tributario)
    """
    data    = await run_osint(nombre, rut)
    resumen = build_resumen(data, rut)

    servel_dump = data["servel"].model_dump() if data["servel"] else None
    sii_dump    = data["sii"].model_dump()    if data["sii"]    else None

    return OSINTResponse(
        query=nombre,
        rut=rut,
        fuentes={
            "nryf_nombre":    data["nryf_nombre"],
            "nryf_rut":       data["nryf_rut"],
            "servel":         servel_dump,
            "sii":            sii_dump,
            "empresas":       data["empresas"],
            "pjud":           data["pjud"],
            "diario_oficial": data["diario_oficial"],
        },
        resumen=resumen,
    )