import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import Index from "./pages/Index.tsx";
import Resultados from "./pages/Resultados.tsx";
import ResultadosList from "./pages/ResultadosList.tsx";
import Hallazgos from "./pages/Hallazgos.tsx";
import PlanAccion from "./pages/PlanAccion.tsx";
import Dorks from "./pages/Dorks.tsx";
import EmailIdentificacion from "./pages/EmailIdentificacion.tsx";
import CabecerasEmpresasTemp from "./pages/CabecerasEmpresasTemp.tsx";
import ExposicionWebTemp from "./pages/ExposicionWebTemp.tsx";
import NotFound from "./pages/NotFound.tsx";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AppErrorBoundary>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Index />} />
            <Route path="/resultados" element={<ResultadosList />} />
            <Route path="/resultados/:id" element={<Resultados />} />
            <Route path="/hallazgos/:id" element={<Hallazgos />} />
            <Route path="/plan/:id" element={<PlanAccion />} />
            <Route path="/dorks" element={<Dorks />} />
            <Route path="/identificacion-email" element={<EmailIdentificacion />} />
            <Route path="/cabeceras-empresa-temp" element={<CabecerasEmpresasTemp />} />
            <Route path="/exposicion-web-temp" element={<ExposicionWebTemp />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </AppErrorBoundary>
  </QueryClientProvider>
);

export default App;
