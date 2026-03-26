import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { mockSearches } from "@/data/mockData";
import { RiskBadge } from "@/components/RiskBadge";
import { Input } from "@/components/ui/input";
import { Search, Ghost, ArrowRight } from "lucide-react";

export default function ResultadosList() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const filtered = mockSearches.filter((s) =>
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

        {/* Results */}
        {filtered.length === 0 ? (
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
                <RiskBadge level={s.riesgo} />
                <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </button>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
