import { useState } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import {
  Fingerprint, Home, BarChart3, FileSearch, ClipboardCheck, Search, Ghost,
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { mockSearches } from "@/data/mockData";
import { RiskBadge } from "@/components/RiskBadge";
import { Input } from "@/components/ui/input";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const { id } = useParams();
  const location = useLocation();
  const [searchQuery, setSearchQuery] = useState("");
  const [resultadosOpen, setResultadosOpen] = useState(false);

  const activeId = id || location.pathname.match(/\/(resultados|hallazgos|plan)\/(\w+)/)?.[2];
  const dorksNombre = new URLSearchParams(location.search).get("nombre") ?? "";

  // Auto-open when on a results page
  const isOnResultsPage = location.pathname.startsWith("/resultados");
  const isOpen = resultadosOpen || isOnResultsPage;

  const filteredSearches = mockSearches.filter((s) =>
    s.nombre.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const subPages = [
    { title: "Hallazgos",      base: "hallazgos",  icon: FileSearch },
    { title: "Plan de Acción", base: "plan",        icon: ClipboardCheck },
  ];

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-4">
        <NavLink to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
          <Fingerprint className="h-7 w-7 text-primary shrink-0" />
          {!collapsed && (
            <div className="overflow-hidden">
              <p className="text-sm font-bold tracking-tight truncate">OSINT CHILE</p>
              <p className="text-[10px] text-muted-foreground truncate">Huella Digital · Ley 21.719</p>
            </div>
          )}
        </NavLink>
      </SidebarHeader>

      <SidebarContent>
        {/* ── General ───────────────────────────────────── */}
        <SidebarGroup>
          <SidebarGroupLabel>General</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <NavLink to="/" end className="hover:bg-muted/50" activeClassName="bg-primary/10 text-primary font-medium">
                    <Home className="mr-2 h-4 w-4" />
                    {!collapsed && <span>Inicio</span>}
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <NavLink
                    to={dorksNombre ? `/dorks?nombre=${encodeURIComponent(dorksNombre)}` : "/dorks"}
                    className="hover:bg-muted/50"
                    activeClassName="bg-primary/10 text-primary font-medium"
                  >
                    <Search className="mr-2 h-4 w-4" />
                    {!collapsed && <span>Dorks</span>}
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>

              {/* Resultados - collapsible */}
              <SidebarMenuItem>
                <Collapsible open={isOpen} onOpenChange={setResultadosOpen}>
                  <CollapsibleTrigger className="w-full flex items-center gap-2 px-2 py-2 rounded-md text-sm hover:bg-muted/50 transition-colors">
                    <BarChart3 className="h-4 w-4 shrink-0" />
                    {!collapsed && (
                      <>
                        <span className="flex-1 text-left">Resultados</span>
                        <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${isOpen ? "rotate-180" : ""}`} />
                      </>
                    )}
                  </CollapsibleTrigger>

                  {!collapsed && (
                    <CollapsibleContent>
                      <div className="mt-1 ml-2 border-l border-border pl-3 space-y-2">
                        {/* Search inside */}
                        <div className="relative">
                          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                          <Input
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="Buscar por nombre..."
                            className="h-7 pl-8 text-xs bg-muted/30 border-border"
                          />
                        </div>

                        {/* Results list */}
                        <div className="space-y-0.5 max-h-[280px] overflow-y-auto">
                          {filteredSearches.length === 0 ? (
                            <div className="py-3 text-center">
                              <Ghost className="h-4 w-4 mx-auto mb-1 text-muted-foreground/50" />
                              <p className="text-[10px] text-muted-foreground/70">Sin resultados</p>
                            </div>
                          ) : (
                            filteredSearches.map((s) => (
                              <NavLink
                                key={s.id}
                                to={`/resultados/${s.id}`}
                                className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors"
                                activeClassName="bg-primary/10 text-primary"
                              >
                                <div className="flex-1 min-w-0">
                                  <p className="text-[11px] font-medium truncate">{s.nombre}</p>
                                  <p className="text-[10px] text-muted-foreground truncate">{s.hallazgos} hallazgos</p>
                                </div>
                                <RiskBadge level={s.riesgo} />
                              </NavLink>
                            ))
                          )}
                        </div>
                      </div>
                    </CollapsibleContent>
                  )}
                </Collapsible>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* ── Análisis de búsqueda activa ──────────────── */}
        {activeId && (
          <SidebarGroup>
            <SidebarGroupLabel>Análisis</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {subPages.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton asChild>
                      <NavLink
                        to={`/${item.base}/${activeId}`}
                        className="hover:bg-muted/50"
                        activeClassName="bg-primary/10 text-primary font-medium"
                      >
                        <item.icon className="mr-2 h-4 w-4" />
                        {!collapsed && <span>{item.title}</span>}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
    </Sidebar>
  );
}
