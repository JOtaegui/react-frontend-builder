from __future__ import annotations

import re

NAME_PATTERNS = [
    r"\b(?:Estimado|Estimada|Hola|Dear|Sr\.?|Sra\.?|Señor|Señora)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,24}(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,24}){1,2})",
    r"\b(?:Titular|Cliente|Usuario|Beneficiario)\s*:\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,24}(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,24}){1,2})",
]

NAME_STOPWORDS = {
    "Bancoestado",
    "Chile",
    "Cuenta",
    "Cliente",
    "Usuario",
    "Titular",
    "Beneficiario",
    "Soporte",
    "Equipo",
}

NAME_BANNED_TOKENS = {
    "Aprovechar", "Todas", "Oportunidades", "Confirmar", "Evento", "Continuar", "Conversación",
    "Empresa", "Fue", "Enviada", "Seguimiento", "Publicación", "Mantener", "Buena",
    "Experiencia", "Proponer", "Otras", "Fechas", "Revisar", "Detalle", "Seguridad",
    "Desempeñarse", "Unidad", "Mundo", "Laboral", "Comuna", "Lampa", "Oferta",
    "Completar", "Formulario", "Indicar", "Recibiste", "Alumnos", "Ingeniería",
    "Correo", "Estaba", "Puedan", "Realice", "Conectes", "Reagendar", "Gracias",
    "Comunidad", "Universitaria", "Martes", "Próxima", "Semana", "Reporte", "Diario",
    "Semanal", "Tarea", "Actualice", "Configuraciones", "Hora", "Descargar", "Appuandes",
    "Estudiantes", "Ingresa", "Aquí", "Explicar", "Detalle", "Inscribirse", "Profesores",
    "Representatividad", "Niños", "Poder", "Realizar", "Correctamente", "Instalación",
    "Recibir", "Sacramentos", "Acción", "Blue", "Lens", "Comunicarte", "Información",
    "Importante", "Cuenta", "Informar", "Cambios", "Iniciar", "Sesión", "Pruebas",
    "Exponer", "Levantar", "Entorno", "Muestren", "Reducir", "Emails", "Carpeta",
    "Desagregación", "Acceso", "Educativo", "Gratuito", "Instrucciones", "Utilizar",
    "Cualquiera", "Correo", "Electrónico", "Otra", "Banda", "Dejar", "Añada", "Mejor",
    "Trabajo", "Redes", "Sociales", "Cliente", "Potencial", "Curso", "Emprendi",
    "Tus", "Usa", "Hace", "Ya", "Hazlo", "Cuidado",
}


def extract_name_candidates(content: str) -> list[str]:
    if not content:
        return []

    found: list[str] = []
    for pattern in NAME_PATTERNS:
        for match in re.findall(pattern, content):
            cleaned = re.sub(r"\s+", " ", match).strip(" ,.;:-")
            parts = cleaned.split()
            while parts and parts[-1] in NAME_BANNED_TOKENS:
                parts = parts[:-1]
            if len(parts) < 2:
                continue
            if any(part in NAME_STOPWORDS for part in parts):
                continue
            if any(part in NAME_BANNED_TOKENS for part in parts):
                continue
            if not all(re.fullmatch(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,24}", part) for part in parts):
                continue
            normalized = " ".join(part.capitalize() for part in parts)
            if normalized not in found:
                found.append(normalized)
    return found[:5]


def select_primary_name(values: list[str]) -> str | None:
    unique = [value for index, value in enumerate(values) if values.index(value) == index]
    if not unique:
        return None

    best = unique[0]
    best_score = -1
    for candidate in unique:
        parts = candidate.split(" ")
        score = len(parts)
        for value in values:
            if value == candidate:
                score += 3
                continue
            value_parts = value.split(" ")
            score += len([part for part in parts if part in value_parts])

        if score > best_score or (score == best_score and len(candidate) > len(best)):
            best = candidate
            best_score = score
    return best
