

# Plan: Plataforma OSINT Chile completa + búsqueda en resultados y navegación desde tabla

La app aún no tiene implementación. Este plan cubre la construcción completa del frontend OSINT Chile más las dos funcionalidades solicitadas.

## Estructura de archivos a crear/editar

### Datos mock y tipos
- `src/data/mockData.ts` — Tipos TypeScript e interfaces (SearchResult, Finding, ActionItem, etc.) y datos mock para 3-4 personas con hallazgos, alertas y planes de acción. Cada búsqueda tiene un `id` único.

### Páginas
- `src/pages/Index.tsx` — Home con formulario de búsqueda, configuración de alcance/profundidad, tabla de búsquedas recientes. **Cada fila de la tabla es clickeable** y navega a `/resultados/:id`.
- `src/pages/Resultados.tsx` — Recibe `id` por URL params, carga los datos mock del usuario correspondiente. Muestra índice de riesgo, resumen, hallazgos por categoría, alertas, timeline. **Incluye un campo de búsqueda/filtro** en la parte superior para filtrar los hallazgos por texto (nombre, fuente, categoría, valor).
- `src/pages/Hallazgos.tsx` — Inventario detallado de datos expuestos para el usuario seleccionado (también con `id` en la URL). Incluye filtro de búsqueda.
- `src/pages/PlanAccion.tsx` — Plan de acción con acciones agrupadas por prioridad, checkboxes de estado.

### Componentes
- `src/components/Layout.tsx` — Layout con header (logo OSINT Chile), navegación por tabs entre las 4 vistas, tema oscuro.
- `src/components/RiskBadge.tsx` — Badge de color según nivel de riesgo.
- `src/components/SearchFilter.tsx` — Input de búsqueda reutilizable para filtrar resultados en tablas.

### Routing (`src/App.tsx`)
- `/` → Home
- `/resultados/:id` → Resultados
- `/hallazgos/:id` → Hallazgos detallados
- `/plan/:id` → Plan de acción

## Funcionalidades solicitadas

1. **Buscador en página de resultados**: Un input con icono de lupa en la parte superior de la página de Resultados que filtra en tiempo real los hallazgos, alertas y datos mostrados en las tablas por coincidencia de texto.

2. **Click en búsqueda reciente**: Cada fila de la tabla de búsquedas recientes en el Home usa `useNavigate()` con `onClick` para navegar a `/resultados/{id}`, mostrando los resultados específicos de esa persona.

## Diseño
- Tema oscuro (`bg-gray-950`, `text-white`) con acentos en cyan/blue
- Badges: Crítico=red, Alto=orange, Medio=yellow, Bajo=green
- Responsive con Tailwind
- Usa componentes shadcn/ui existentes (Card, Table, Badge, Input, Button, Tabs, Progress)

