"""
dorks.py — Generador de Google Dorks para OSINT
Montar en FastAPI como router independiente de main.py
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional
from urllib.parse import quote_plus

router = APIRouter(prefix="/api/dorks", tags=["Dorks"])


# ─── Modelos ──────────────────────────────────────────────────────────────────
class Dork(BaseModel):
    label: str
    query: str
    google_url: str
    categoria: str
    nota: Optional[str] = None


class DorkCategory(BaseModel):
    id: str
    titulo: str
    dorks: list[Dork]


class DorksResponse(BaseModel):
    nombre: str
    total_dorks: int
    categorias: list[DorkCategory]


# ─── Builder ──────────────────────────────────────────────────────────────────
def build_dork(label: str, raw_query: str, categoria: str, nota: Optional[str] = None) -> Dork:
    google_url = f"https://www.google.com/search?q={quote_plus(raw_query)}"
    return Dork(label=label, query=raw_query, google_url=google_url, categoria=categoria, nota=nota)


def generate_dorks(nombre: str) -> list[DorkCategory]:
    n = nombre.strip()

    categorias: list[DorkCategory] = [

        # ── Redes Sociales ────────────────────────────────────────────────────
        DorkCategory(
            id="rrss",
            titulo="Redes Sociales",
            dorks=[
                build_dork("Instagram",    f'site:instagram.com "{n}" Chile',                                "rrss"),
                build_dork("LinkedIn",     f'site:linkedin.com/in OR site:linkedin.com/pub "{n}" "Chile"',  "rrss", "Perfil profesional"),
                build_dork("Facebook",     f'site:facebook.com "{n}" Chile',                                "rrss"),
                build_dork("Twitter / X",  f'site:twitter.com OR site:x.com "{n}" Chile',                  "rrss"),
            ],
        ),

        # ── Noticias y Prensa ─────────────────────────────────────────────────
        DorkCategory(
            id="noticias",
            titulo="Noticias y Prensa",
            dorks=[
                build_dork("El Mercurio",       f'site:www.elmercurio.com "{n}"',                                                                                    "noticias"),
                build_dork("La Tercera",         f'site:www.latercera.com "{n}"',                                                                                    "noticias"),
                build_dork("BioBío Chile",       f'site:www.biobiochile.cl "{n}"',                                                                                   "noticias"),
                build_dork("CIPER Chile",        f'site:ciperchile.cl "{n}"',                                                                                        "noticias", "Periodismo de investigación"),
                build_dork("Todos los medios",   f'(site:elmercurio.com OR site:latercera.com OR site:biobiochile.cl OR site:ciperchile.cl) "{n}"',                  "noticias", "Búsqueda combinada"),
            ],
        ),

        # ── Universidades y Repositorios ──────────────────────────────────────
        DorkCategory(
            id="academico",
            titulo="Universidades y Repositorios",
            dorks=[
                build_dork(
                    "CRUCH Tradicionales",
                    f'(site:uchile.cl OR site:uc.cl OR site:usach.cl OR site:uv.cl OR site:udec.cl OR site:uach.cl OR site:usm.cl OR site:ucn.cl OR site:uct.cl OR site:utalca.cl OR site:ubiobio.cl OR site:ufro.cl) "{n}"',
                    "academico", "Universidades del CRUCH",
                ),
                build_dork(
                    "Universidades Privadas",
                    f'(site:uai.cl OR site:udd.cl OR site:uandes.cl OR site:udp.cl OR site:uahurtado.cl OR site:umayor.cl OR site:unab.cl OR site:uss.cl OR site:ucentral.cl OR site:autonoma.cl) "{n}"',
                    "academico",
                ),
                build_dork(
                    "Repositorios — Estatales",
                    f'(site:repositorio.uchile.cl OR site:repositorio.uc.cl OR site:repositorio.usach.cl OR site:repositorio.udec.cl OR site:repositorio.uv.cl OR site:repositorio.uach.cl OR site:repositorio.usm.cl OR site:repositorio.ucn.cl OR site:repositorio.utalca.cl OR site:repositorio.ubiobio.cl OR site:repositorio.ufro.cl) "{n}" filetype:pdf',
                    "academico", "Tesis y documentos académicos",
                ),
                build_dork(
                    "Repositorios — Privadas",
                    f'(site:repositorio.uai.cl OR site:repositorio.udd.cl OR site:repositorio.unab.cl OR site:repositorio.uahurtado.cl OR site:repositorio.umayor.cl OR site:repositorio.ucentral.cl OR site:repositorio.ucsh.cl) "{n}" filetype:pdf',
                    "academico",
                ),
                build_dork("ANID Investigadores", f'site:investigadores.anid.cl "{n}"', "academico", "Investigadores con fondos del Estado"),
            ],
        ),

        # ── Gobierno y Registros Oficiales ────────────────────────────────────
        DorkCategory(
            id="gobierno",
            titulo="Gobierno y Registros Oficiales",
            dorks=[
                build_dork("Portal Gob.cl",         f'site:gob.cl "{n}" filetype:pdf OR filetype:doc',                           "gobierno", "Documentos oficiales"),
                build_dork("Mineduc",                f'site:mineduc.cl "{n}"',                                                    "gobierno", "Ministerio de Educación"),
                build_dork("Minsal",                 f'site:minsal.cl "{n}"',                                                     "gobierno", "Ministerio de Salud"),
                build_dork("Diario Oficial",         f'site:diariooficial.interior.gob.cl "{n}"',                                 "gobierno", "Actos oficiales, empresas, nombramientos"),
                build_dork("ChileCompra",            f'(site:chilecompra.cl OR site:mercadopublico.cl) "{n}"',                    "gobierno", "Proveedores del Estado"),
                build_dork("Poder Judicial",         f'site:pjud.cl "{n}"',                                                      "gobierno", "Causas judiciales, abogados"),
                build_dork("SII — Empresas",         f'site:sii.cl "{n}"',                                                       "gobierno", "Roles corporativos, estado tributario"),
                build_dork("Registro de Empresas",   f'site:registrodeempresasysociedades.cl "{n}"',                              "gobierno", "Propiedad empresarial, roles directivos"),
            ],
        ),

        # ── Historia y Genealogía ─────────────────────────────────────────────
        DorkCategory(
            id="genealogia",
            titulo="Historia y Genealogía",
            dorks=[
                build_dork("Biblioteca Nacional Digital", f'site:bibliotecanacionaldigital.gob.cl "{n}"',                          "genealogia"),
                build_dork("Memoria Chilena",              f'site:memoriachilena.gob.cl "{n}"',                                    "genealogia"),
                build_dork("Archivo Nacional",             f'(site:archivonacional.gob.cl OR site:documentos.archivonacional.cl) "{n}"', "genealogia"),
                build_dork("FamilySearch",                 f'site:familysearch.org "{n}" Chile',                                   "genealogia", "Registros genealógicos"),
                build_dork("Genealog.cl",                  f'site:genealog.cl "{n}"',                                              "genealogia"),
            ],
        ),

        # ── Fuerzas Armadas ───────────────────────────────────────────────────
        DorkCategory(
            id="fuerzas",
            titulo="Fuerzas Armadas",
            dorks=[
                build_dork("Sitios .mil.cl", f'site:*.mil.cl "{n}"', "fuerzas", "FFAA, Armada, FACH, Carabineros"),
            ],
        ),

        # ── Genérico ──────────────────────────────────────────────────────────
        DorkCategory(
            id="generico",
            titulo="Búsqueda Genérica",
            dorks=[
                build_dork(
                    "Archivos en gob.cl",
                    f'site:gob.cl "{n}" filetype:pdf OR filetype:xml OR filetype:xlsx OR filetype:doc OR filetype:csv',
                    "generico", "PDFs, planillas, documentos oficiales",
                ),
                build_dork("Web general Chile", f'"{n}" Chile', "generico", "Sin restricción de sitio"),
            ],
        ),
    ]

    return categorias


# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.get("", response_model=DorksResponse)
async def get_dorks(
    nombre: str = Query(..., min_length=3, description="Nombre completo (ej: Juan Pérez)"),
):
    """
    Genera todos los Google Dorks para un nombre dado.
    Devuelve queries listas para copiar + URL directa de Google.
    """
    categorias = generate_dorks(nombre)
    total = sum(len(c.dorks) for c in categorias)

    return DorksResponse(nombre=nombre, total_dorks=total, categorias=categorias)


@router.get("/categoria/{categoria_id}", response_model=DorkCategory)
async def get_dorks_categoria(
    categoria_id: str,
    nombre: str = Query(..., min_length=3, description="Nombre completo"),
):
    """
    Devuelve solo los dorks de una categoría específica.
    Categorías: rrss, noticias, academico, gobierno, genealogia, fuerzas, generico
    """
    categorias = generate_dorks(nombre)
    cat = next((c for c in categorias if c.id == categoria_id), None)

    if not cat:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"Categoría '{categoria_id}' no encontrada. Disponibles: {[c.id for c in categorias]}",
        )

    return cat