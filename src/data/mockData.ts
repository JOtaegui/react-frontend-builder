export type RiskLevel = "Crítico" | "Alto" | "Medio" | "Bajo";

export interface Finding {
  id: string;
  dato: string;
  valor: string;
  fuente: string;
  categoria: string;
  riesgo: RiskLevel;
  estado: string;
}

export interface Alert {
  id: string;
  alerta: string;
  fuente: string;
  prioridad: RiskLevel;
}

export interface CategorySummary {
  categoria: string;
  cantidad: number;
  riesgo: RiskLevel;
}

export interface TimelineEvent {
  fecha: string;
  evento: string;
  fuente: string;
  datosExpuestos: string;
  estado: string;
}

export interface ActionItem {
  id: string;
  accion: string;
  donde: string;
  como: string;
  plazo: string;
  resultado: string;
  completado: boolean;
  prioridad: "Crítico" | "Urgente" | "Buena Práctica";
}

export interface SearchResult {
  id: string;
  nombre: string;
  rut?: string;
  email?: string;
  rrss?: string;
  fecha: string;
  hallazgos: number;
  riesgo: RiskLevel;
  puntajeRiesgo: number;
  fuentes: number;
  datosCriticos: number;
  alertasActivas: number;
  tiempoBusqueda: string;
  findings: Finding[];
  alerts: Alert[];
  categories: CategorySummary[];
  timeline: TimelineEvent[];
  actions: ActionItem[];
}

export const mockSearches: SearchResult[] = [
  {
    id: "1",
    nombre: "Carlos Andrés Muñoz Soto",
    rut: "12.345.678-9",
    email: "carlos.munoz@gmail.com",
    rrss: "@carlosmunoz",
    fecha: "2024-01-15",
    hallazgos: 23,
    riesgo: "Alto",
    puntajeRiesgo: 72,
    fuentes: 8,
    datosCriticos: 5,
    alertasActivas: 3,
    tiempoBusqueda: "12 min",
    findings: [
      { id: "f1", dato: "Email personal", valor: "carlos.munoz@gmail.com", fuente: "LinkedIn", categoria: "Contacto", riesgo: "Medio", estado: "Expuesto" },
      { id: "f2", dato: "RUT", valor: "12.345.678-9", fuente: "Registro Civil filtrado", categoria: "Identidad", riesgo: "Crítico", estado: "Filtrado" },
      { id: "f3", dato: "Teléfono", valor: "+56 9 1234 5678", fuente: "Facebook", categoria: "Contacto", riesgo: "Alto", estado: "Público" },
      { id: "f4", dato: "Dirección", valor: "Av. Providencia 1234, Santiago", fuente: "Google Maps Reviews", categoria: "Ubicación", riesgo: "Crítico", estado: "Público" },
      { id: "f5", dato: "Foto de perfil", valor: "Imagen HD disponible", fuente: "Instagram", categoria: "Biométrico", riesgo: "Medio", estado: "Público" },
      { id: "f6", dato: "Lugar de trabajo", valor: "Empresa XYZ SpA", fuente: "LinkedIn", categoria: "Laboral", riesgo: "Bajo", estado: "Público" },
      { id: "f7", dato: "Contraseña filtrada", valor: "c***s2019", fuente: "Have I Been Pwned", categoria: "Credenciales", riesgo: "Crítico", estado: "Filtrado" },
      { id: "f8", dato: "IP registrada", valor: "190.xxx.xx.45", fuente: "Foro público", categoria: "Técnico", riesgo: "Alto", estado: "Expuesto" },
    ],
    alerts: [
      { id: "a1", alerta: "Contraseña filtrada en breach de 2023", fuente: "Have I Been Pwned", prioridad: "Crítico" },
      { id: "a2", alerta: "RUT expuesto en base de datos filtrada", fuente: "Dark Web Monitor", prioridad: "Crítico" },
      { id: "a3", alerta: "Dirección personal visible en reseñas", fuente: "Google Maps", prioridad: "Alto" },
    ],
    categories: [
      { categoria: "Identidad", cantidad: 3, riesgo: "Crítico" },
      { categoria: "Contacto", cantidad: 5, riesgo: "Alto" },
      { categoria: "Ubicación", cantidad: 4, riesgo: "Crítico" },
      { categoria: "Laboral", cantidad: 3, riesgo: "Bajo" },
      { categoria: "Credenciales", cantidad: 2, riesgo: "Crítico" },
      { categoria: "Biométrico", cantidad: 3, riesgo: "Medio" },
      { categoria: "Técnico", cantidad: 3, riesgo: "Alto" },
    ],
    timeline: [
      { fecha: "2023-12-01", evento: "Breach detectado", fuente: "Have I Been Pwned", datosExpuestos: "Email, contraseña", estado: "Sin resolver" },
      { fecha: "2023-10-15", evento: "Perfil público indexado", fuente: "Google", datosExpuestos: "Nombre, foto, empleo", estado: "Activo" },
      { fecha: "2023-08-20", evento: "RUT filtrado en base de datos", fuente: "Dark Web", datosExpuestos: "RUT, nombre completo", estado: "Sin resolver" },
      { fecha: "2023-06-10", evento: "Reseña con dirección publicada", fuente: "Google Maps", datosExpuestos: "Dirección domicilio", estado: "Activo" },
    ],
    actions: [
      { id: "ac1", accion: "Cambiar contraseña filtrada", donde: "Gmail, LinkedIn", como: "Usar gestor de contraseñas, crear clave de 16+ caracteres", plazo: "Hoy", resultado: "Eliminar acceso no autorizado", completado: false, prioridad: "Crítico" },
      { id: "ac2", accion: "Activar 2FA en todas las cuentas", donde: "Gmail, Facebook, Instagram, LinkedIn", como: "Configurar app de autenticación (Google Authenticator)", plazo: "Hoy", resultado: "Capa adicional de seguridad", completado: false, prioridad: "Crítico" },
      { id: "ac3", accion: "Eliminar reseña con dirección", donde: "Google Maps", como: "Editar o eliminar la reseña que contiene la dirección", plazo: "Hoy", resultado: "Dirección no visible públicamente", completado: true, prioridad: "Crítico" },
      { id: "ac4", accion: "Solicitar eliminación de datos filtrados", donde: "Registro Civil / SERNAC", como: "Enviar solicitud formal bajo Ley 21.719", plazo: "Esta semana", resultado: "Datos removidos de bases filtradas", completado: false, prioridad: "Urgente" },
      { id: "ac5", accion: "Configurar privacidad en redes sociales", donde: "Facebook, Instagram", como: "Cambiar perfil a privado, limitar visibilidad de publicaciones", plazo: "Esta semana", resultado: "Reducir exposición pública", completado: false, prioridad: "Urgente" },
      { id: "ac6", accion: "Eliminar cuenta de foro público", donde: "Foro detectado", como: "Solicitar baja de cuenta o eliminar posts", plazo: "Esta semana", resultado: "IP y datos removidos", completado: false, prioridad: "Urgente" },
      { id: "ac7", accion: "Monitoreo periódico de breaches", donde: "Have I Been Pwned", como: "Registrar email para alertas automáticas", plazo: "Continuo", resultado: "Detección temprana de filtraciones", completado: true, prioridad: "Buena Práctica" },
      { id: "ac8", accion: "Revisar permisos de apps conectadas", donde: "Google, Facebook", como: "Revocar acceso a apps no reconocidas", plazo: "Mensual", resultado: "Menor superficie de ataque", completado: false, prioridad: "Buena Práctica" },
    ],
  },
  {
    id: "2",
    nombre: "María José López Fernández",
    rut: "15.678.901-2",
    email: "mjlopez@outlook.com",
    fecha: "2024-01-12",
    hallazgos: 15,
    riesgo: "Medio",
    puntajeRiesgo: 45,
    fuentes: 5,
    datosCriticos: 2,
    alertasActivas: 1,
    tiempoBusqueda: "8 min",
    findings: [
      { id: "f1", dato: "Email personal", valor: "mjlopez@outlook.com", fuente: "LinkedIn", categoria: "Contacto", riesgo: "Bajo", estado: "Público" },
      { id: "f2", dato: "Nombre completo", valor: "María José López Fernández", fuente: "Registro público", categoria: "Identidad", riesgo: "Bajo", estado: "Público" },
      { id: "f3", dato: "Teléfono laboral", valor: "+56 2 2345 6789", fuente: "Sitio web empresa", categoria: "Contacto", riesgo: "Medio", estado: "Público" },
      { id: "f4", dato: "Foto profesional", valor: "Imagen HD disponible", fuente: "LinkedIn", categoria: "Biométrico", riesgo: "Bajo", estado: "Público" },
      { id: "f5", dato: "Contraseña antigua filtrada", valor: "m***z2020", fuente: "Have I Been Pwned", categoria: "Credenciales", riesgo: "Alto", estado: "Filtrado" },
    ],
    alerts: [
      { id: "a1", alerta: "Contraseña antigua encontrada en breach", fuente: "Have I Been Pwned", prioridad: "Alto" },
    ],
    categories: [
      { categoria: "Contacto", cantidad: 4, riesgo: "Medio" },
      { categoria: "Identidad", cantidad: 3, riesgo: "Bajo" },
      { categoria: "Credenciales", cantidad: 1, riesgo: "Alto" },
      { categoria: "Biométrico", cantidad: 2, riesgo: "Bajo" },
      { categoria: "Laboral", cantidad: 5, riesgo: "Bajo" },
    ],
    timeline: [
      { fecha: "2023-11-20", evento: "Breach detectado", fuente: "Have I Been Pwned", datosExpuestos: "Email, contraseña", estado: "Resuelto" },
      { fecha: "2023-09-05", evento: "Perfil LinkedIn indexado", fuente: "Google", datosExpuestos: "Nombre, cargo, empresa", estado: "Activo" },
    ],
    actions: [
      { id: "ac1", accion: "Verificar cambio de contraseña", donde: "Outlook", como: "Confirmar que la contraseña filtrada ya no está en uso", plazo: "Hoy", resultado: "Credencial segura", completado: true, prioridad: "Crítico" },
      { id: "ac2", accion: "Activar 2FA", donde: "Outlook, LinkedIn", como: "Configurar autenticación de dos factores", plazo: "Hoy", resultado: "Mayor seguridad", completado: false, prioridad: "Crítico" },
      { id: "ac3", accion: "Revisar información pública en LinkedIn", donde: "LinkedIn", como: "Limitar datos visibles a no-conexiones", plazo: "Esta semana", resultado: "Menor exposición", completado: false, prioridad: "Urgente" },
      { id: "ac4", accion: "Monitoreo continuo", donde: "Have I Been Pwned", como: "Suscribirse a alertas", plazo: "Continuo", resultado: "Detección temprana", completado: true, prioridad: "Buena Práctica" },
    ],
  },
  {
    id: "3",
    nombre: "Alejandro Sebastián Rojas Pinto",
    rut: "18.901.234-5",
    email: "arojas.dev@gmail.com",
    rrss: "@alexrojas_dev",
    fecha: "2024-01-10",
    hallazgos: 31,
    riesgo: "Crítico",
    puntajeRiesgo: 89,
    fuentes: 12,
    datosCriticos: 9,
    alertasActivas: 6,
    tiempoBusqueda: "18 min",
    findings: [
      { id: "f1", dato: "Email personal", valor: "arojas.dev@gmail.com", fuente: "GitHub", categoria: "Contacto", riesgo: "Medio", estado: "Público" },
      { id: "f2", dato: "RUT", valor: "18.901.234-5", fuente: "Base filtrada 2022", categoria: "Identidad", riesgo: "Crítico", estado: "Filtrado" },
      { id: "f3", dato: "Múltiples contraseñas", valor: "3 contraseñas filtradas", fuente: "Have I Been Pwned", categoria: "Credenciales", riesgo: "Crítico", estado: "Filtrado" },
      { id: "f4", dato: "Dirección domicilio", valor: "Los Leones 567, Providencia", fuente: "Registro electoral filtrado", categoria: "Ubicación", riesgo: "Crítico", estado: "Filtrado" },
      { id: "f5", dato: "Número de cuenta", valor: "Últimos 4 dígitos visibles", fuente: "Screenshot en foro", categoria: "Financiero", riesgo: "Crítico", estado: "Expuesto" },
      { id: "f6", dato: "API keys expuestas", valor: "2 keys en repos públicos", fuente: "GitHub", categoria: "Técnico", riesgo: "Crítico", estado: "Público" },
      { id: "f7", dato: "Foto con geolocalización", valor: "EXIF data con coordenadas", fuente: "Twitter", categoria: "Ubicación", riesgo: "Alto", estado: "Público" },
      { id: "f8", dato: "CV completo", valor: "PDF con datos personales", fuente: "Sitio de empleo", categoria: "Identidad", riesgo: "Alto", estado: "Público" },
      { id: "f9", dato: "Teléfono personal", valor: "+56 9 8765 4321", fuente: "WhatsApp Business", categoria: "Contacto", riesgo: "Alto", estado: "Público" },
    ],
    alerts: [
      { id: "a1", alerta: "3 contraseñas filtradas en múltiples breaches", fuente: "Have I Been Pwned", prioridad: "Crítico" },
      { id: "a2", alerta: "API keys de producción expuestas en GitHub", fuente: "GitHub", prioridad: "Crítico" },
      { id: "a3", alerta: "Datos bancarios parcialmente visibles", fuente: "Foro público", prioridad: "Crítico" },
      { id: "a4", alerta: "RUT en base de datos del dark web", fuente: "Dark Web Monitor", prioridad: "Crítico" },
      { id: "a5", alerta: "Dirección domicilio en registro filtrado", fuente: "Registro electoral", prioridad: "Alto" },
      { id: "a6", alerta: "Fotos con metadatos de ubicación", fuente: "Twitter", prioridad: "Alto" },
    ],
    categories: [
      { categoria: "Credenciales", cantidad: 5, riesgo: "Crítico" },
      { categoria: "Identidad", cantidad: 4, riesgo: "Crítico" },
      { categoria: "Ubicación", cantidad: 5, riesgo: "Crítico" },
      { categoria: "Financiero", cantidad: 2, riesgo: "Crítico" },
      { categoria: "Técnico", cantidad: 6, riesgo: "Crítico" },
      { categoria: "Contacto", cantidad: 5, riesgo: "Alto" },
      { categoria: "Biométrico", cantidad: 4, riesgo: "Alto" },
    ],
    timeline: [
      { fecha: "2024-01-05", evento: "API keys detectadas en GitHub", fuente: "GitHub Scanner", datosExpuestos: "2 API keys de producción", estado: "Sin resolver" },
      { fecha: "2023-12-15", evento: "Breach masivo detectado", fuente: "Have I Been Pwned", datosExpuestos: "Email, 3 contraseñas", estado: "Sin resolver" },
      { fecha: "2023-11-01", evento: "Datos bancarios en screenshot", fuente: "Foro público", datosExpuestos: "Últimos 4 dígitos cuenta", estado: "Sin resolver" },
      { fecha: "2023-09-20", evento: "RUT en dark web", fuente: "Dark Web Monitor", datosExpuestos: "RUT, nombre, dirección", estado: "Sin resolver" },
      { fecha: "2023-07-10", evento: "CV publicado sin protección", fuente: "Sitio de empleo", datosExpuestos: "Datos personales completos", estado: "Activo" },
    ],
    actions: [
      { id: "ac1", accion: "Revocar API keys expuestas INMEDIATAMENTE", donde: "GitHub, proveedor de API", como: "Regenerar keys y actualizar en entorno seguro", plazo: "Ahora", resultado: "Eliminar acceso no autorizado a APIs", completado: false, prioridad: "Crítico" },
      { id: "ac2", accion: "Cambiar TODAS las contraseñas", donde: "Gmail, GitHub, y todos los servicios", como: "Usar gestor de contraseñas, claves únicas de 20+ caracteres", plazo: "Hoy", resultado: "Credenciales seguras", completado: false, prioridad: "Crítico" },
      { id: "ac3", accion: "Contactar banco por datos expuestos", donde: "Banco personal", como: "Solicitar nuevo número de cuenta y monitoreo de fraude", plazo: "Hoy", resultado: "Proteger cuenta bancaria", completado: false, prioridad: "Crítico" },
      { id: "ac4", accion: "Activar 2FA en todos los servicios", donde: "Gmail, GitHub, banco", como: "Usar llave de seguridad hardware (YubiKey) preferentemente", plazo: "Hoy", resultado: "Máxima seguridad en accesos", completado: false, prioridad: "Crítico" },
      { id: "ac5", accion: "Eliminar repos con datos sensibles", donde: "GitHub", como: "Eliminar historial de commits con git filter-branch", plazo: "Hoy", resultado: "Keys removidas del historial", completado: false, prioridad: "Crítico" },
      { id: "ac6", accion: "Solicitar eliminación de CV público", donde: "Sitio de empleo", como: "Contactar plataforma para baja del documento", plazo: "Esta semana", resultado: "Datos personales no accesibles", completado: false, prioridad: "Urgente" },
      { id: "ac7", accion: "Eliminar metadatos de fotos", donde: "Twitter, Instagram", como: "Resubir fotos sin EXIF data", plazo: "Esta semana", resultado: "Ubicación no rastreable por fotos", completado: false, prioridad: "Urgente" },
      { id: "ac8", accion: "Solicitar eliminación bajo Ley 21.719", donde: "SERNAC / Registro Civil", como: "Presentar solicitud formal de supresión de datos", plazo: "Esta semana", resultado: "Datos eliminados de bases filtradas", completado: false, prioridad: "Urgente" },
      { id: "ac9", accion: "Configurar alertas de monitoreo", donde: "Have I Been Pwned, GitHub", como: "Activar notificaciones automáticas", plazo: "Continuo", resultado: "Detección temprana", completado: false, prioridad: "Buena Práctica" },
      { id: "ac10", accion: "Auditoría trimestral de huella digital", donde: "Todas las plataformas", como: "Revisar configuración de privacidad cada 3 meses", plazo: "Trimestral", resultado: "Exposición controlada", completado: false, prioridad: "Buena Práctica" },
    ],
  },
];

export function getSearchById(id: string): SearchResult | undefined {
  return mockSearches.find((s) => s.id === id);
}
