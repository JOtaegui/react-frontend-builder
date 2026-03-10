import { Badge } from "@/components/ui/badge";
import type { RiskLevel } from "@/data/mockData";

const riskStyles: Record<RiskLevel, string> = {
  "Crítico": "bg-red-600 text-white hover:bg-red-700 border-red-700",
  "Alto": "bg-orange-500 text-white hover:bg-orange-600 border-orange-600",
  "Medio": "bg-yellow-500 text-black hover:bg-yellow-600 border-yellow-600",
  "Bajo": "bg-green-500 text-white hover:bg-green-600 border-green-600",
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  return <Badge className={riskStyles[level]}>{level}</Badge>;
}
