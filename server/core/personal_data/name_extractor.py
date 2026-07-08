from __future__ import annotations

import re

# ── Bloques de construcción de los patrones ──────────────────────────────────
# Los separadores entre tokens del nombre son [ \t]+ (NO \s+): con \s+ el
# patrón cruzaba saltos de línea y capturaba el inicio del párrafo siguiente
# ("Hola Claudia\nJunto con saludar" → "Claudia Junto", FP real ×4 en S5).

# Saludos, incluidas variantes en inglés ("Hi Juan Otaegui!", miss real).
_GREETING = (
    r"(?:Estimado|Estimada|ESTIMADO|ESTIMADA|Hola|HOLA|Dear|DEAR|Hi|HI|"
    r"Hello|HELLO|Hey|Sr\.?|Sra\.?|Señor|Señora|SEÑOR|SEÑORA)"
)
# Variantes de género tras el saludo: "Estimado(a)", "Estimado/a", con o sin
# dos puntos ("Estimado(a): Juan…"). Misses reales: bancochile, copecpay,
# minpublico (recall de nombre 28% en 300 muestras de scan real).
_GREETING_SUFFIX = r"(?:[ \t]*[(/][ \t]*[aA][ \t]*\)?)?[ \t]*:?"

# Roles que anteceden al nombre, con o sin dos puntos. Misses reales:
# "Paciente Juan Ignacio Otaegui" (dentalink), "el contribuyente JUAN
# IGNACIO OTAEGUI CERECEDA RUT…" (SII).
_ROLE = (
    r"(?:[Tt]itular|[Cc]liente|[Uu]suario|[Bb]eneficiario|[Pp]aciente|"
    r"[Cc]ontribuyente|[Dd]estinatario|[Rr]emitente|[Aa]filiado|[Aa]segurado|"
    r"TITULAR|CLIENTE|USUARIO|BENEFICIARIO|PACIENTE|CONTRIBUYENTE|"
    r"DESTINATARIO|REMITENTE)"
)
# Etiqueta "Nombre:" / "Nombre del destinatario:" (miss real: tenpo).
_NOMBRE_LABEL = r"(?:Nombre|NOMBRE)(?:[ \t]+(?:de|del|DE|DEL)[ \t]+[A-Za-zÁÉÍÓÚÑáéíóúñ]+)?[ \t]*:"

# Despedidas: el nombre que las sigue es la firma del remitente humano.
# Misses reales: "Muchas gracias Juan Otaegui", "Quedo Atento Juan Otaegui".
_FAREWELL = (
    r"(?:[Gg]racias|[Ss]aludos(?:[ \t]+[Cc]ordiales)?|[Aa]tentamente|"
    r"[Aa]tte\.?|[Cc]ordialmente|[Qq]uedo[ \t]+[Aa]tent[oa]|[Uu]n[ \t]+[Aa]brazo)"
)

_NAME_MIXED = r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,24}(?:[ \t]+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,24}){1,3})"
_NAME_UPPER = r"([A-ZÁÉÍÓÚÑ]{2,24}(?:[ \t]+[A-ZÁÉÍÓÚÑ]{2,24}){1,3})"
# Cierre para nombres EN MAYÚSCULAS: puntuación, fin de línea, "RUT/RUN", o
# cambio de caja (siguiente palabra Capitalizada-minúscula). El patrón
# antiguo exigía puntuación y perdía "Hola JUAN IGNACIO OTAEGUI CERECEDA
# Realizaste un(a) compra…" (miss real ×5 en BCI). Las frases promocionales
# en mayúsculas siguen bloqueadas por las listas de tokens vetados.
_UPPER_END = r"(?=[ \t]*(?:[,.;:!?\n()]|$|RUT\b|RUN\b|[A-ZÁÉÍÓÚÑ][a-záéíóúñ]))"

NAME_PATTERNS = [
    rf"\b{_GREETING}{_GREETING_SUFFIX}[ \t]+{_NAME_MIXED}",
    rf"\b{_ROLE}[ \t]*:?[ \t]+{_NAME_MIXED}",
    rf"\b{_GREETING}{_GREETING_SUFFIX}[ \t]+{_NAME_UPPER}{_UPPER_END}",
    rf"\b(?:{_ROLE}[ \t]*:?|{_NOMBRE_LABEL})[ \t]+{_NAME_UPPER}{_UPPER_END}",
    rf"\b{_NOMBRE_LABEL}[ \t]+{_NAME_MIXED}",
    rf"\b{_FAREWELL}[,.]?[ \t]+{_NAME_MIXED}",
    # Comprobantes: "La transferencia de Juan Ignacio Otaegui Cereceda por…"
    rf"\b[Tt]ransferencia[ \t]+de[ \t]+{_NAME_MIXED}",
]

# Nombre de persona dentro de un nombre de archivo adjunto, p. ej.
# "Declaración_jurada_simple_-Juan_Otaegui.docx" (miss real: tenpo).
_FILENAME_NAME_RE = re.compile(
    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,24})[_\-]+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,24})"
    r"\.(?:docx?|DOCX?|pdf|PDF|xlsx?|XLSX?|jpe?g|JPE?G|png|PNG)\b"
)

# Tokens típicos de nombres de documentos: si aparecen en el par capturado
# desde un nombre de archivo, no es un nombre de persona.
_FILENAME_DOC_TOKENS = {
    "Declaracion", "Declaración", "Jurada", "Simple", "Denuncia", "Boleta",
    "Factura", "Cartola", "Certificado", "Informe", "Reporte", "Contrato",
    "Formulario", "Anexo", "Copia", "Resumen", "Detalle", "Comprobante",
    "Orden", "Ticket", "Guia", "Guía", "Manual", "Paso", "Documento",
    "Cedula", "Cédula", "Carnet", "Firma", "Firmado", "Final", "Borrador",
    "Version", "Versión", "Enero", "Febrero", "Marzo", "Abril", "Mayo",
    "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre",
    "Diciembre",
}

# Texto HTML aplanado suele pegar palabras ("Juan IgnacioOtaeguiCereceda").
# Separar en los cambios minúscula→Mayúscula recupera esos nombres.
_CAMEL_SPLIT_RE = re.compile(r"([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])")

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

# Conectivos y arranques de frase que siguen al nombre en saludos de
# marketing ("Hola Claudia Recuerda que…", "Estimado Juan Ignacio Con tu
# tarjeta…"). FPs reales de los 5 sujetos: Con, Como, Junto, Nos, Recuerda.
_CONNECTIVE_TOKENS = {
    "Con", "Como", "Junto", "Nos", "Te", "Les", "Este", "Esta",
    "Hoy", "Aqui", "Aquí", "Que", "Por", "Para", "Si",
    # Artículos/partículas que arrancan la frase siguiente a una firma
    # ("Muchas gracias Juan Otaegui El vie, 19 jun…" — caso real).
    "El", "La", "Lo", "Los", "Las", "Al", "Le", "Se", "No",
    # "…CERECEDA RUT N°…": la etiqueta no es parte del nombre.
    "Rut", "Run",
    # Auditoría FP sobre 300 muestras reales: "Transferencia de Fondos Hola
    # Juan Ignacio", "Isabel Clinica Everest" (bot asistente), "Pablo
    # Valdebenito Sa" (razón social pegada).
    "Hola", "Fondos", "Transferencia", "Clinica", "Clínica", "Asistente",
    "Virtual", "Sa", "Spa", "Ltda", "Eirl",
}

# Verbos imperativos típicos de asuntos/cuerpos de marketing. FPs reales:
# "Juan Ahorra" (×2), "Juan Aprende" (×2), "Claudia Recuerda" (×4).
_IMPERATIVE_TOKENS = {
    "Recuerda", "Ahorra", "Aprende", "Aprovecha", "Descubre", "Disfruta",
    "Gana", "Participa", "Conoce", "Renueva", "Compra", "Paga", "Elige",
    "Encuentra", "Obten", "Obtén", "Recibe", "Canjea", "Suma", "Postula",
    "Activa", "Solicita", "Confirma", "Actualiza", "Accede", "Prueba",
    "Mira", "Explora", "Evalua", "Evalúa", "Descarga", "Agenda", "Cotiza",
    "Retira", "Vive", "Juega", "Escucha", "Comparte", "Sigue", "Unete",
    "Únete", "Entra", "Ven", "Llama", "Escribe", "Responde", "Completa",
    "Valida", "Verifica", "Empieza", "Comienza", "Celebra", "Invita",
}

# Marcas/instituciones que aparecen pegadas al nombre en saludos
# ("Hola Juan Bci te informa…"). FP real: "Juan Bci" (×2).
_BRAND_TOKENS = {
    "Bci", "Santander", "Falabella", "Ripley", "Lider", "Entel",
    "Movistar", "Claro", "Vtr", "Wom", "Latam", "Copec", "Jumbo",
    "Unimarc", "Cencosud", "Sodimac", "Easy", "Netflix", "Spotify",
    "Uber", "Rappi", "Mach", "Tenpo", "Chek", "Banco", "Banca",
}

# Placeholders en inglés de correos transaccionales. FP real:
# "Valued Customer" (×4).
_PLACEHOLDER_TOKENS = {
    "Valued", "Customer", "User", "Member", "Team", "Support", "Service",
}

# Honoríficos que preceden al nombre y no son parte de él. FP real:
# "Miss María Elena" (×4), "Doctor Jorge" (×4).
_HONORIFIC_TOKENS = {
    "Miss", "Mister", "Mr", "Mrs", "Ms", "Doctor", "Doctora", "Dr", "Dra",
    "Don", "Doña", "Profesor", "Profesora", "Padre", "Madre",
}

_ALL_BANNED_TOKENS = (
    NAME_BANNED_TOKENS
    | _CONNECTIVE_TOKENS
    | _IMPERATIVE_TOKENS
    | _BRAND_TOKENS
    | _PLACEHOLDER_TOKENS
)


def _validate_name(raw: str) -> str | None:
    """Limpia y valida un candidato a nombre; None si no sobrevive."""
    cleaned = re.sub(r"\s+", " ", raw).strip(" ,.;:-")
    # nombres en MAYÚSCULAS se llevan a formato título antes de validar
    parts = [part.capitalize() if part.isupper() else part for part in cleaned.split()]
    # honoríficos al inicio no son parte del nombre ("Miss María Elena")
    while parts and parts[0] in _HONORIFIC_TOKENS:
        parts = parts[1:]
    # conectivos/verbos/marcas al final son arranque de la frase
    # siguiente, no apellido ("Juan Ignacio Recuerda" → "Juan Ignacio")
    while parts and parts[-1] in _ALL_BANNED_TOKENS:
        parts = parts[:-1]
    if len(parts) < 2:
        return None
    if any(part in NAME_STOPWORDS for part in parts):
        return None
    if any(part in _ALL_BANNED_TOKENS for part in parts):
        return None
    if not all(re.fullmatch(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,24}", part) for part in parts):
        return None
    # fragmentos de 2 letras por token no son nombres ("Ta Zo", FP real
    # del texto HTML aplanado)
    if max(len(part) for part in parts) <= 2:
        return None
    return " ".join(part.capitalize() for part in parts)


def extract_name_candidates(content: str) -> list[str]:
    if not content:
        return []

    # El HTML aplanado pega palabras ("Juan IgnacioOtaeguiCereceda"): se
    # escanea también una copia con los cambios de caja separados.
    decamel = _CAMEL_SPLIT_RE.sub(r"\1 \2", content)
    texts = [content] if decamel == content else [content, decamel]

    found: list[str] = []
    for text in texts:
        for pattern in NAME_PATTERNS:
            for match in re.findall(pattern, text):
                normalized = _validate_name(match)
                if normalized and normalized not in found:
                    found.append(normalized)

    # Nombres dentro de archivos adjuntos ("…_-Juan_Otaegui.docx")
    for m in _FILENAME_NAME_RE.finditer(content):
        first, last = m.group(1), m.group(2)
        if first in _FILENAME_DOC_TOKENS or last in _FILENAME_DOC_TOKENS:
            continue
        normalized = _validate_name(f"{first} {last}")
        if normalized and normalized not in found:
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
