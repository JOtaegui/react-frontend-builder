import { useState } from "react";
import { useParams, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { RiskBadge } from "@/components/RiskBadge";
import { SearchFilter } from "@/components/SearchFilter";
import { getSearchById, type RiskLevel } from "@/data/mockData";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FileText, Layers } from "lucide-react";

export default function Hallazgos() {
  const { id } = useParams();
  const [filter, setFilter] = useState("");
  const data = getSearchById(id || "");

  if (!data) return <Navigate to="/" />;

  const q = filter.toLowerCase();
  const filtered = data.findings.filter(
    (f) =>
      f.dato.toLowerCase().includes(q) ||
      f.valor.toLowerCase().includes(q) ||
      f.fuente.toLowerCase().includes(q) ||
      f.categoria.toLowerCase().includes(q) ||
      f.riesgo.toLowerCase().includes(q)
  );

  // Category summary
  const catMap = new Map<string, { total: number; critico: number; alto: number; medio: number; bajo: number }>();
  data.findings.forEach((f) => {
    const existing = catMap.get(f.categoria) || { total: 0, critico: 0, alto: 0, medio: 0, bajo: 0 };
    existing.total++;
    if (f.riesgo === "Crítico") existing.critico++;
    else if (f.riesgo === "Alto") existing.alto++;
    else if (f.riesgo === "Medio") existing.medio++;
    else existing.bajo++;
    catMap.set(f.categoria, existing);
  });

  return (
    <Layout>
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <h2 className="text-2xl font-bold">Hallazgos Detallados — {data.nombre}</h2>
          <div className="w-full md:w-80">
            <SearchFilter value={filter} onChange={setFilter} placeholder="Buscar dato, fuente, categoría..." />
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Inventario de Datos Expuestos
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dato</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Fuente</TableHead>
                  <TableHead>Categoría</TableHead>
                  <TableHead>Riesgo</TableHead>
                  <TableHead>Estado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((f) => (
                  <TableRow key={f.id}>
                    <TableCell className="font-medium">{f.dato}</TableCell>
                    <TableCell className="text-muted-foreground font-mono text-xs">{f.valor}</TableCell>
                    <TableCell>{f.fuente}</TableCell>
                    <TableCell>{f.categoria}</TableCell>
                    <TableCell><RiskBadge level={f.riesgo} /></TableCell>
                    <TableCell className="text-muted-foreground">{f.estado}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers className="h-5 w-5" />
              Resumen por Categoría
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Categoría</TableHead>
                  <TableHead className="text-center">Total</TableHead>
                  <TableHead className="text-center">Crítico</TableHead>
                  <TableHead className="text-center">Alto</TableHead>
                  <TableHead className="text-center">Medio</TableHead>
                  <TableHead className="text-center">Bajo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Array.from(catMap.entries()).map(([cat, counts]) => (
                  <TableRow key={cat}>
                    <TableCell className="font-medium">{cat}</TableCell>
                    <TableCell className="text-center">{counts.total}</TableCell>
                    <TableCell className="text-center text-red-400">{counts.critico || "-"}</TableCell>
                    <TableCell className="text-center text-orange-400">{counts.alto || "-"}</TableCell>
                    <TableCell className="text-center text-yellow-400">{counts.medio || "-"}</TableCell>
                    <TableCell className="text-center text-green-400">{counts.bajo || "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
