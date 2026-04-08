import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Input } from "@/components/ui/input";
import { Search, Ghost, ArrowRight, Loader2 } from "lucide-react";

interface SearchHistoryItem {
  id: string;
  nombre: string;
  rut?: string | null;
  fecha: string;
  riesgo: string;
  hallazgos: number;
  fuentes: number;
}

export default function ResultadosList() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SearchHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const cargar = async () => {
      try {
        const res = await fetch("/api/searches?limit=100", {
          signal: AbortSignal.timeout(10000),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: SearchHistoryItem[] = await res.json();
        if (!cancelled) setItems(data);
      } catch {
        if (!cancelled) setItems([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void cargar();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = items.filter((s) =>
    s.nombre.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <Layout>
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h2 className="text-2xl font-bold">Resultados</h2>
          <p className="text-sm text-muted-foreground">Selecciona una búsqueda para ver el análisis completo</p>
        </div>

        {/* Search bar */}
        <div className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar por nombre..."
            className="h-12 pl-11 text-sm bg-card border-border"
          />
        </div>

        {loading ? (
          <div className="text-center py-16 space-y-2">
            <Loader2 className="h-8 w-8 mx-auto text-muted-foreground/60 animate-spin" />
            <p className="text-sm text-muted-foreground">Cargando búsquedas...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16 space-y-2">
            <Ghost className="h-8 w-8 mx-auto text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">No se encontraron resultados</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((s) => (
              <button
                key={s.id}
                onClick={() => navigate(`/resultados/${s.id}`)}
                className="w-full flex items-center gap-4 px-5 py-4 rounded-xl border border-border bg-card hover:bg-muted/40 transition-colors text-left group"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{s.nombre}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {s.fecha} · {s.hallazgos} hallazgos · {s.fuentes} fuentes
                  </p>
                </div>
                <span className="text-xs text-muted-foreground border border-border px-2 py-1 rounded-full shrink-0">
                  {s.riesgo || "Sin datos"}
                </span>
                <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </button>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
