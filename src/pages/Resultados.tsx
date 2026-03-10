import { useState } from "react";
import { useParams, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { RiskBadge } from "@/components/RiskBadge";
import { SearchFilter } from "@/components/SearchFilter";
import { getSearchById } from "@/data/mockData";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FileSearch, ShieldAlert, BarChart3, Clock, Database, AlertTriangle, Eye } from "lucide-react";

export default function Resultados() {
  const { id } = useParams();
  const [filter, setFilter] = useState("");
  const data = getSearchById(id || "");

  if (!data) return <Navigate to="/" />;

  const q = filter.toLowerCase();
  const filteredFindings = data.categories.filter(
    (c) => c.categoria.toLowerCase().includes(q) || c.riesgo.toLowerCase().includes(q)
  );
  const filteredAlerts = data.alerts.filter(
    (a) => a.alerta.toLowerCase().includes(q) || a.fuente.toLowerCase().includes(q) || a.prioridad.toLowerCase().includes(q)
  );

  const riskColor =
    data.puntajeRiesgo >= 75 ? "text-red-500" : data.puntajeRiesgo >= 50 ? "text-orange-500" : data.puntajeRiesgo >= 25 ? "text-yellow-500" : "text-green-500";

  return (
    <Layout>
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold">{data.nombre}</h2>
            <p className="text-sm text-muted-foreground">
              Búsqueda: {data.fecha} · {data.hallazgos} hallazgos · {data.tiempoBusqueda}
            </p>
          </div>
          <div className="w-full md:w-80">
            <SearchFilter value={filter} onChange={setFilter} placeholder="Filtrar resultados..." />
          </div>
        </div>

        {/* Risk Index */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5" />
              Índice de Riesgo Global
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <span className={`text-4xl font-bold ${riskColor}`}>{data.puntajeRiesgo}</span>
              <span className="text-muted-foreground text-lg">/ 100</span>
              <RiskBadge level={data.riesgo} />
            </div>
            <Progress value={data.puntajeRiesgo} className="mt-3 h-3" />
          </CardContent>
        </Card>

        {/* Quick Summary */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { icon: FileSearch, label: "Total hallazgos", value: data.hallazgos },
            { icon: Database, label: "Fuentes", value: data.fuentes },
            { icon: AlertTriangle, label: "Datos críticos", value: data.datosCriticos },
            { icon: Eye, label: "Alertas activas", value: data.alertasActivas },
          ].map((m) => (
            <Card key={m.label}>
              <CardContent className="pt-6 text-center">
                <m.icon className="h-6 w-6 mx-auto mb-2 text-primary" />
                <p className="text-2xl font-bold">{m.value}</p>
                <p className="text-xs text-muted-foreground">{m.label}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Categories */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              Hallazgos por Categoría
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Categoría</TableHead>
                  <TableHead className="text-center">Cantidad</TableHead>
                  <TableHead>Riesgo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredFindings.map((c) => (
                  <TableRow key={c.categoria}>
                    <TableCell className="font-medium">{c.categoria}</TableCell>
                    <TableCell className="text-center">{c.cantidad}</TableCell>
                    <TableCell><RiskBadge level={c.riesgo} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Alerts */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Alertas Prioritarias
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Alerta</TableHead>
                  <TableHead>Fuente</TableHead>
                  <TableHead>Prioridad</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredAlerts.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell>{a.alerta}</TableCell>
                    <TableCell className="text-muted-foreground">{a.fuente}</TableCell>
                    <TableCell><RiskBadge level={a.prioridad} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Timeline */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Línea de Tiempo de Exposición
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {data.timeline.map((t, i) => (
                <div key={i} className="flex gap-4 items-start">
                  <div className="flex flex-col items-center">
                    <div className="h-3 w-3 rounded-full bg-primary" />
                    {i < data.timeline.length - 1 && <div className="w-px h-full bg-border flex-1 min-h-[2rem]" />}
                  </div>
                  <div className="pb-4">
                    <p className="text-sm font-semibold">{t.evento}</p>
                    <p className="text-xs text-muted-foreground">{t.fecha} · {t.fuente}</p>
                    <p className="text-xs text-muted-foreground">Datos: {t.datosExpuestos}</p>
                    <span className={`text-xs ${t.estado === "Sin resolver" ? "text-red-400" : "text-yellow-400"}`}>{t.estado}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
