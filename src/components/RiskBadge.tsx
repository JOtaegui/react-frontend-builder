import { Badge } from "@/components/ui/badge";
import type { RiskLevel } from "@/data/mockData";

const riskStyles: Record<RiskLevel, string> = {
  "Crítico": "bg-red-600 text-white hover:bg-red-700 border-red-700",
  "Alto": "bg-orange-500 text-white hover:bg-orange-600 border-orange-600",
  "Medio": "bg-yellow-500 text-black hover:bg-yellow-600 border-yellow-600",
  "Bajo": "bg-green-500 text-white hover:bg-green-600 border-green-600",
};

function normalizeRiskLevel(level: string | null | undefined): RiskLevel | null {
  if (typeof level !== "string") {
    return null;
  }
  if (level in riskStyles) {
    return level as RiskLevel;
  }
  return null;
}

export function RiskBadge({ level }: { level?: string | null }) {
  const normalized = normalizeRiskLevel(level);
  if (!normalized) {
    return (
      <Badge className="bg-muted text-muted-foreground hover:bg-muted border-border">
        {level || "Sin datos"}
      </Badge>
    );
  }

  return <Badge className={riskStyles[normalized]}>{normalized}</Badge>;
}
