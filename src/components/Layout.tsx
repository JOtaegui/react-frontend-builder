import { ReactNode } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { Shield } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Layout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const { id } = useParams();
  const location = useLocation();
  const isHome = location.pathname === "/";

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-card">
        <div className="container mx-auto flex items-center justify-between py-4 px-4">
          <div className="flex items-center gap-3 cursor-pointer" onClick={() => navigate("/")}>
            <Shield className="h-8 w-8 text-primary" />
            <div>
              <h1 className="text-xl font-bold tracking-tight">OSINT CHILE</h1>
              <p className="text-xs text-muted-foreground">Plataforma de identificación de huella digital · Ley N°21.719</p>
            </div>
          </div>
          {!isHome && id && (
            <nav className="flex gap-1">
              <Button variant={location.pathname.startsWith("/resultados") ? "default" : "ghost"} size="sm" onClick={() => navigate(`/resultados/${id}`)}>
                Resultados
              </Button>
              <Button variant={location.pathname.startsWith("/hallazgos") ? "default" : "ghost"} size="sm" onClick={() => navigate(`/hallazgos/${id}`)}>
                Hallazgos
              </Button>
              <Button variant={location.pathname.startsWith("/plan") ? "default" : "ghost"} size="sm" onClick={() => navigate(`/plan/${id}`)}>
                Plan de Acción
              </Button>
            </nav>
          )}
        </div>
      </header>
      <main className="container mx-auto px-4 py-6">{children}</main>
    </div>
  );
}
