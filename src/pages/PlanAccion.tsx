import { useState } from "react";
import { useParams, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { getSearchById } from "@/data/mockData";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ClipboardCheck, Zap, CalendarClock, Shield } from "lucide-react";

export default function PlanAccion() {
  const { id } = useParams();
  const data = getSearchById(id || "");
  const [completed, setCompleted] = useState<Set<string>>(
    new Set(data?.actions.filter((a) => a.completado).map((a) => a.id) || [])
  );

  if (!data) return <Navigate to="/" />;

  const toggle = (actionId: string) => {
    setCompleted((prev) => {
      const next = new Set(prev);
      next.has(actionId) ? next.delete(actionId) : next.add(actionId);
      return next;
    });
  };

  const total = data.actions.length;
  const done = completed.size;
  const pct = Math.round((done / total) * 100);

  const criticas = data.actions.filter((a) => a.prioridad === "Crítico");
  const urgentes = data.actions.filter((a) => a.prioridad === "Urgente");
  const buenas = data.actions.filter((a) => a.prioridad === "Buena Práctica");

  const prioridadBadge = (p: string) => {
    if (p === "Crítico") return <Badge className="bg-red-600 text-white border-red-700">Crítico</Badge>;
    if (p === "Urgente") return <Badge className="bg-orange-500 text-white border-orange-600">Urgente</Badge>;
    return <Badge className="bg-blue-500 text-white border-blue-600">Buena Práctica</Badge>;
  };

  const renderTable = (items: typeof data.actions, icon: React.ReactNode, title: string) => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">✓</TableHead>
              <TableHead>Acción</TableHead>
              <TableHead>Dónde</TableHead>
              <TableHead className="hidden md:table-cell">Cómo</TableHead>
              <TableHead>Plazo</TableHead>
              <TableHead className="hidden lg:table-cell">Resultado</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((a) => (
              <TableRow key={a.id} className={completed.has(a.id) ? "opacity-50" : ""}>
                <TableCell>
                  <Checkbox checked={completed.has(a.id)} onCheckedChange={() => toggle(a.id)} />
                </TableCell>
                <TableCell className={`font-medium ${completed.has(a.id) ? "line-through" : ""}`}>{a.accion}</TableCell>
                <TableCell className="text-muted-foreground">{a.donde}</TableCell>
                <TableCell className="hidden md:table-cell text-muted-foreground text-xs">{a.como}</TableCell>
                <TableCell>{a.plazo}</TableCell>
                <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">{a.resultado}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );

  return (
    <Layout>
      <div className="max-w-6xl mx-auto space-y-6">
        <h2 className="text-2xl font-bold">Plan de Acción — {data.nombre}</h2>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-muted-foreground">Progreso general</span>
              <span className="text-sm font-semibold">{done}/{total} acciones ({pct}%)</span>
            </div>
            <Progress value={pct} className="h-3" />
          </CardContent>
        </Card>

        {criticas.length > 0 && renderTable(criticas, <Zap className="h-5 w-5 text-red-500" />, "Hacer Hoy — Crítico")}
        {urgentes.length > 0 && renderTable(urgentes, <CalendarClock className="h-5 w-5 text-orange-500" />, "Esta Semana — Urgente")}
        {buenas.length > 0 && renderTable(buenas, <Shield className="h-5 w-5 text-blue-500" />, "Buenas Prácticas — Continuo")}
      </div>
    </Layout>
  );
}
