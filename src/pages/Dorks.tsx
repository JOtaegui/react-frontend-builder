import { useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ExternalLink, Copy, Check, Search,
  GraduationCap, Newspaper, Linkedin, Globe,
  Shield, Building2, Instagram, BookOpen,
} from "lucide-react";

// ─── Tipos ────────────────────────────────────────────────────────────────────
interface Dork {
  label: string;
  query: (nombre: string) => string;
  nota?: string;
}

interface DorkCategory {
  id: string;
  titulo: string;
  icon: React.ReactNode;
  color: string;
  dorks: Dork[];
}

// ─── Definición de dorks ──────────────────────────────────────────────────────
const CATEGORIAS: DorkCategory[] = [
  {
    id: "rrss",
    titulo: "Redes Sociales",
    icon: <Instagram className="h-4 w-4" />,
    color: "text-pink-400",
    dorks: [
      {
        label: "Instagram",
        query: (n) => `site:instagram.com "${n}" Chile`,
        nota: "Perfiles y menciones en Instagram",
      },
      {
        label: "LinkedIn",
        query: (n) => `site:linkedin.com/in OR site:linkedin.com/pub "${n}" "Chile"`,
        nota: "Perfil profesional",
      },
      {
        label: "Facebook",
        query: (n) => `site:facebook.com "${n}" Chile`,
      },
      {
        label: "Twitter / X",
        query: (n) => `site:twitter.com OR site:x.com "${n}" Chile`,
      },
    ],
  },
  {
    id: "noticias",
    titulo: "Noticias y Prensa",
    icon: <Newspaper className="h-4 w-4" />,
    color: "text-blue-400",
    dorks: [
      {
        label: "El Mercurio",
        query: (n) => `site:www.elmercurio.com "${n}"`,
      },
      {
        label: "La Tercera",
        query: (n) => `site:www.latercera.com "${n}"`,
      },
      {
        label: "BioBío Chile",
        query: (n) => `site:www.biobiochile.cl "${n}"`,
      },
      {
        label: "CIPER Chile",
        query: (n) => `site:ciperchile.cl "${n}"`,
        nota: "Periodismo de investigación",
      },
      {
        label: "Todos los medios",
        query: (n) =>
          `(site:elmercurio.com OR site:latercera.com OR site:biobiochile.cl OR site:ciperchile.cl) "${n}"`,
        nota: "Búsqueda combinada",
      },
    ],
  },
  {
    id: "academico",
    titulo: "Universidades y Repositorios",
    icon: <GraduationCap className="h-4 w-4" />,
    color: "text-violet-400",
    dorks: [
      {
        label: "CRUCH Tradicionales",
        query: (n) =>
          `(site:uchile.cl OR site:uc.cl OR site:usach.cl OR site:uv.cl OR site:udec.cl OR site:uach.cl OR site:usm.cl OR site:ucn.cl OR site:uct.cl OR site:utalca.cl OR site:ubiobio.cl OR site:ufro.cl) "${n}"`,
        nota: "Universidades del CRUCH",
      },
      {
        label: "Universidades Privadas",
        query: (n) =>
          `(site:uai.cl OR site:udd.cl OR site:uandes.cl OR site:udp.cl OR site:uahurtado.cl OR site:umayor.cl OR site:unab.cl OR site:uss.cl OR site:ucentral.cl OR site:autonoma.cl) "${n}"`,
      },
      {
        label: "Repositorios — Estatales",
        query: (n) =>
          `(site:repositorio.uchile.cl OR site:repositorio.uc.cl OR site:repositorio.usach.cl OR site:repositorio.udec.cl OR site:repositorio.uv.cl OR site:repositorio.uach.cl OR site:repositorio.usm.cl OR site:repositorio.ucn.cl OR site:repositorio.utalca.cl OR site:repositorio.ubiobio.cl OR site:repositorio.ufro.cl) "${n}" filetype:pdf`,
        nota: "Tesis y documentos académicos",
      },
      {
        label: "Repositorios — Privadas",
        query: (n) =>
          `(site:repositorio.uai.cl OR site:repositorio.udd.cl OR site:repositorio.unab.cl OR site:repositorio.uahurtado.cl OR site:repositorio.umayor.cl OR site:repositorio.ucentral.cl OR site:repositorio.ucsh.cl) "${n}" filetype:pdf`,
      },
      {
        label: "ANID Investigadores",
        query: (n) => `site:investigadores.anid.cl "${n}"`,
        nota: "Investigadores con fondos del Estado",
      },
    ],
  },
  {
    id: "gobierno",
    titulo: "Gobierno y Registros Oficiales",
    icon: <Building2 className="h-4 w-4" />,
    color: "text-amber-400",
    dorks: [
      {
        label: "Portal Gob.cl general",
        query: (n) => `site:gob.cl "${n}" filetype:pdf OR filetype:doc`,
        nota: "Documentos oficiales del gobierno",
      },
      {
        label: "Mineduc",
        query: (n) => `site:mineduc.cl "${n}"`,
        nota: "Ministerio de Educación",
      },
      {
        label: "Minsal",
        query: (n) => `site:minsal.cl "${n}"`,
        nota: "Ministerio de Salud",
      },
      {
        label: "Diario Oficial",
        query: (n) => `site:diariooficial.interior.gob.cl "${n}"`,
        nota: "Actos oficiales, empresas, nombramientos",
      },
      {
        label: "ChileCompra / Mercado Público",
        query: (n) => `(site:chilecompra.cl OR site:mercadopublico.cl) "${n}"`,
        nota: "Proveedores del Estado",
      },
      {
        label: "Poder Judicial",
        query: (n) => `site:pjud.cl "${n}"`,
        nota: "Causas judiciales, abogados",
      },
    ],
  },
  {
    id: "genealogia",
    titulo: "Historia y Genealogía",
    icon: <BookOpen className="h-4 w-4" />,
    color: "text-emerald-400",
    dorks: [
      {
        label: "Biblioteca Nacional Digital",
        query: (n) => `site:bibliotecanacionaldigital.gob.cl "${n}"`,
      },
      {
        label: "Memoria Chilena",
        query: (n) => `site:memoriachilena.gob.cl "${n}"`,
      },
      {
        label: "Archivo Nacional",
        query: (n) =>
          `(site:archivonacional.gob.cl OR site:documentos.archivonacional.cl) "${n}"`,
      },
      {
        label: "FamilySearch",
        query: (n) => `site:familysearch.org "${n}" Chile`,
        nota: "Registros genealógicos",
      },
      {
        label: "Genealog.cl",
        query: (n) => `site:genealog.cl "${n}"`,
      },
    ],
  },
  {
    id: "fuerzas",
    titulo: "Fuerzas Armadas",
    icon: <Shield className="h-4 w-4" />,
    color: "text-red-400",
    dorks: [
      {
        label: "Sitios .mil.cl",
        query: (n) => `site:*.mil.cl "${n}"`,
        nota: "FFAA, Armada, FACH, Carabineros",
      },
    ],
  },
  {
    id: "generico",
    titulo: "Búsqueda Genérica de Archivos",
    icon: <Globe className="h-4 w-4" />,
    color: "text-cyan-400",
    dorks: [
      {
        label: "Archivos en gob.cl",
        query: (n) =>
          `site:gob.cl "${n}" filetype:pdf OR filetype:xml OR filetype:xlsx OR filetype:doc OR filetype:csv`,
        nota: "PDFs, planillas, documentos oficiales",
      },
      {
        label: "LinkedIn profesional",
        query: (n) => `site:linkedin.com "${n}" Chile`,
      },
      {
        label: "Web general Chile",
        query: (n) => `"${n}" Chile`,
        nota: "Búsqueda libre sin restricción de sitio",
      },
    ],
  },
];

// ─── Componente de un dork individual ────────────────────────────────────────
function DorkItem({ dork, nombre }: { dork: Dork; nombre: string }) {
  const [copied, setCopied] = useState(false);
  const query = dork.query(nombre);
  const googleUrl = `https://www.google.com/search?q=${encodeURIComponent(query)}`;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(query);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex items-start justify-between gap-3 py-2.5 border-b border-border last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">{dork.label}</p>
        {dork.nota && (
          <p className="text-xs text-muted-foreground mt-0.5">{dork.nota}</p>
        )}
        <p className="text-xs font-mono text-muted-foreground/60 mt-1 truncate">{query}</p>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={handleCopy}
          title="Copiar dork"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
        </Button>
        <a href={googleUrl} target="_blank" rel="noopener noreferrer">
          <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs">
            <Search className="h-3 w-3" />
            Buscar
            <ExternalLink className="h-3 w-3" />
          </Button>
        </a>
      </div>
    </div>
  );
}

// ─── Página principal ─────────────────────────────────────────────────────────
export default function Dorks() {
  const [searchParams] = useSearchParams();
  const nombreParam = searchParams.get("nombre") ?? "";
  const [nombre, setNombre] = useState(nombreParam);
  const [nombreActivo, setNombreActivo] = useState(nombreParam);
  const [soloActiva, setSoloActiva] = useState<string | null>(null);

  const aplicar = () => {
    if (nombre.trim()) setNombreActivo(nombre.trim());
  };

  const categoriasFiltradas = soloActiva
    ? CATEGORIAS.filter((c) => c.id === soloActiva)
    : CATEGORIAS;

  return (
    <Layout>
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="space-y-1">
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Search className="h-6 w-6 text-primary" />
            Google Dorks
          </h2>
          <p className="text-sm text-muted-foreground">
            Búsquedas avanzadas para rastrear la huella digital de una persona por nombre
          </p>
        </div>

        {/* Input nombre */}
        <div className="flex gap-2 max-w-xl">
          <Input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && aplicar()}
            placeholder="Nombre Apellido..."
            className="h-11 bg-card border-border"
          />
          <Button onClick={aplicar} disabled={!nombre.trim()} className="h-11 px-5">
            Aplicar
          </Button>
        </div>

        {nombreActivo && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted-foreground">Buscando:</span>
            <Badge variant="secondary" className="font-mono">{nombreActivo}</Badge>
            <span className="text-xs text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground">Filtrar categoría:</span>
            <div className="flex gap-1.5 flex-wrap">
              <Button
                variant={soloActiva === null ? "default" : "outline"}
                size="sm"
                className="h-6 text-xs px-2"
                onClick={() => setSoloActiva(null)}
              >
                Todas
              </Button>
              {CATEGORIAS.map((c) => (
                <Button
                  key={c.id}
                  variant={soloActiva === c.id ? "default" : "outline"}
                  size="sm"
                  className="h-6 text-xs px-2"
                  onClick={() => setSoloActiva(soloActiva === c.id ? null : c.id)}
                >
                  {c.titulo}
                </Button>
              ))}
            </div>
          </div>
        )}

        {/* Sin nombre */}
        {!nombreActivo && (
          <div className="rounded-xl border border-border bg-card/50 px-6 py-10 text-center text-muted-foreground text-sm">
            Ingresa un nombre para generar los dorks
          </div>
        )}

        {/* Categorías */}
        {nombreActivo && (
          <div className="space-y-4">
            {categoriasFiltradas.map((cat) => (
              <Card key={cat.id}>
                <CardHeader className="py-3 px-5">
                  <CardTitle className={`flex items-center gap-2 text-sm font-semibold ${cat.color}`}>
                    {cat.icon}
                    {cat.titulo}
                    <Badge variant="outline" className="ml-auto text-xs font-normal">
                      {cat.dorks.length} dorks
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-5 pb-3 pt-0">
                  {cat.dorks.map((dork, i) => (
                    <DorkItem key={i} dork={dork} nombre={nombreActivo} />
                  ))}
                </CardContent>
              </Card>
            ))}
          </div>
        )}

      </div>
    </Layout>
  );
}