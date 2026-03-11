import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { RiskBadge } from "@/components/RiskBadge";
import { mockSearches } from "@/data/mockData";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Fingerprint, SlidersHorizontal, Radar, Eye, Flame, History, Zap, Timer, Telescope } from "lucide-react";

const Index = () => {
  const navigate = useNavigate();
  const [nombre, setNombre] = useState("");
  const [rut, setRut] = useState("");
  const [email, setEmail] = useState("");
  const [rrss, setRrss] = useState("");
  const [profundidad, setProfundidad] = useState("normal");

  return (
    <Layout>
      <div className="max-w-4xl mx-auto space-y-12">
        {/* Hero Search */}
        <div className="flex flex-col items-center text-center pt-8 pb-4 space-y-6">
          <div className="relative">
            <div className="absolute -inset-4 rounded-full bg-primary/20 blur-2xl" />
            <Fingerprint className="relative h-16 w-16 text-primary" strokeWidth={1.5} />
          </div>
          <div className="space-y-2">
            <h2 className="text-3xl font-bold tracking-tight">Rastrea la huella digital</h2>
            <p className="text-muted-foreground text-sm max-w-md">
              Ingresa un nombre para descubrir su exposición en la red
            </p>
          </div>

          <div className="w-full max-w-xl flex gap-2">
            <div className="relative flex-1">
              <Radar className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-primary" />
              <Input
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Nombre completo..."
                className="h-14 pl-12 pr-4 text-base rounded-xl bg-card border-border focus-visible:ring-primary/50 focus-visible:border-primary/50"
              />
            </div>

            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="icon" className="h-14 w-14 rounded-xl border-border shrink-0">
                  <SlidersHorizontal className="h-5 w-5" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 space-y-5" align="end">
                <p className="text-sm font-semibold text-foreground">Parámetros opcionales</p>

                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">RUT</Label>
                    <Input value={rut} onChange={(e) => setRut(e.target.value)} placeholder="12.345.678-9" className="h-9" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Email</Label>
                    <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ejemplo@mail.com" className="h-9" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">RRSS</Label>
                    <Input value={rrss} onChange={(e) => setRrss(e.target.value)} placeholder="@usuario" className="h-9" />
                  </div>
                </div>

                <div className="border-t border-border pt-4 space-y-3">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Alcance</p>
                  <div className="flex flex-wrap gap-x-4 gap-y-2">
                    <div className="flex items-center gap-1.5">
                      <Checkbox id="chile" defaultChecked />
                      <Label htmlFor="chile" className="text-xs font-normal">Chile</Label>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Checkbox id="intl" />
                      <Label htmlFor="intl" className="text-xs font-normal">Internacional</Label>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Checkbox id="darkweb" />
                      <Label htmlFor="darkweb" className="text-xs font-normal">Dark Web</Label>
                    </div>
                  </div>
                </div>

                <div className="border-t border-border pt-4 space-y-3">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Profundidad</p>
                  <RadioGroup value={profundidad} onValueChange={setProfundidad} className="space-y-1.5">
                    <div className="flex items-center gap-2">
                      <RadioGroupItem value="rapida" id="rapida" />
                      <Zap className="h-3.5 w-3.5 text-primary" />
                      <Label htmlFor="rapida" className="text-xs font-normal">Rápida (~5 min)</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <RadioGroupItem value="normal" id="normal" />
                      <Timer className="h-3.5 w-3.5 text-primary" />
                      <Label htmlFor="normal" className="text-xs font-normal">Normal (~15 min)</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <RadioGroupItem value="profunda" id="profunda" />
                      <Telescope className="h-3.5 w-3.5 text-primary" />
                      <Label htmlFor="profunda" className="text-xs font-normal">Profunda (~1h)</Label>
                    </div>
                  </RadioGroup>
                </div>
              </PopoverContent>
            </Popover>

            <Button
              disabled={!nombre.trim()}
              className="h-14 px-6 rounded-xl text-base font-semibold shrink-0"
            >
              <Eye className="h-5 w-5 mr-2" />
              Buscar
            </Button>
          </div>
        </div>

        {/* Recent Searches */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <History className="h-4 w-4" />
            <span className="text-sm font-medium uppercase tracking-wider">Recientes</span>
          </div>
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent border-border">
                  <TableHead className="text-muted-foreground text-xs uppercase tracking-wider">Nombre</TableHead>
                  <TableHead className="text-muted-foreground text-xs uppercase tracking-wider">Fecha</TableHead>
                  <TableHead className="text-center text-muted-foreground text-xs uppercase tracking-wider">Hallazgos</TableHead>
                  <TableHead className="text-muted-foreground text-xs uppercase tracking-wider">Riesgo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockSearches.map((s) => (
                  <TableRow
                    key={s.id}
                    className="cursor-pointer hover:bg-primary/5 transition-colors border-border"
                    onClick={() => navigate(`/resultados/${s.id}`)}
                  >
                    <TableCell className="font-medium">{s.nombre}</TableCell>
                    <TableCell className="text-muted-foreground text-sm">{s.fecha}</TableCell>
                    <TableCell className="text-center">
                      <span className="flex items-center justify-center gap-1.5">
                        <Flame className="h-3.5 w-3.5 text-destructive" />
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
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default Index;
