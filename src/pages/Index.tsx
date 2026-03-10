import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { RiskBadge } from "@/components/RiskBadge";
import { mockSearches } from "@/data/mockData";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Search, Clock, AlertTriangle } from "lucide-react";

const Index = () => {
  const navigate = useNavigate();
  const [nombre, setNombre] = useState("");
  const [rut, setRut] = useState("");
  const [email, setEmail] = useState("");
  const [rrss, setRrss] = useState("");
  const [profundidad, setProfundidad] = useState("normal");

  return (
    <Layout>
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Search Form */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-5 w-5" />
              Nueva Búsqueda
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Nombre completo *</Label>
                <Input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Ej: Juan Pérez Silva" />
              </div>
              <div className="space-y-2">
                <Label>RUT (opcional)</Label>
                <Input value={rut} onChange={(e) => setRut(e.target.value)} placeholder="12.345.678-9" />
              </div>
              <div className="space-y-2">
                <Label>Email (opcional)</Label>
                <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ejemplo@mail.com" />
              </div>
              <div className="space-y-2">
                <Label>RRSS (opcional)</Label>
                <Input value={rrss} onChange={(e) => setRrss(e.target.value)} placeholder="@usuario" />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-3">
                <Label className="font-semibold">Alcance</Label>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Checkbox id="chile" defaultChecked />
                    <Label htmlFor="chile" className="font-normal">Chile</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox id="intl" />
                    <Label htmlFor="intl" className="font-normal">Internacional</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox id="darkweb" />
                    <Label htmlFor="darkweb" className="font-normal">Incluir Dark Web</Label>
                  </div>
                </div>
              </div>
              <div className="space-y-3">
                <Label className="font-semibold">Profundidad</Label>
                <RadioGroup value={profundidad} onValueChange={setProfundidad}>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="rapida" id="rapida" />
                    <Label htmlFor="rapida" className="font-normal">Rápida (~5 min)</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="normal" id="normal" />
                    <Label htmlFor="normal" className="font-normal">Normal (~15 min)</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="profunda" id="profunda" />
                    <Label htmlFor="profunda" className="font-normal">Profunda (~1h)</Label>
                  </div>
                </RadioGroup>
              </div>
            </div>

            <Button className="w-full md:w-auto" disabled={!nombre.trim()}>
              <Search className="h-4 w-4 mr-2" />
              Iniciar Búsqueda
            </Button>
          </CardContent>
        </Card>

        {/* Recent Searches */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Búsquedas Recientes
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Fecha</TableHead>
                  <TableHead className="text-center">Hallazgos</TableHead>
                  <TableHead>Riesgo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockSearches.map((s) => (
                  <TableRow
                    key={s.id}
                    className="cursor-pointer hover:bg-accent/50 transition-colors"
                    onClick={() => navigate(`/resultados/${s.id}`)}
                  >
                    <TableCell className="font-medium">{s.nombre}</TableCell>
                    <TableCell className="text-muted-foreground">{s.fecha}</TableCell>
                    <TableCell className="text-center">
                      <span className="flex items-center justify-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        {s.hallazgos}
                      </span>
                    </TableCell>
                    <TableCell>
                      <RiskBadge level={s.riesgo} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
};

export default Index;
