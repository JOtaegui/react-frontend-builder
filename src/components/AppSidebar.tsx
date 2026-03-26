import { useState } from "react";
import { useParams, useLocation } from "react-router-dom";
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

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const { id } = useParams();
  const location = useLocation();
  const [searchQuery, setSearchQuery] = useState("");

  const activeId = id || location.pathname.match(/\/(resultados|hallazgos|plan)\/(\w+)/)?.[2];

  const dorksNombre = new URLSearchParams(location.search).get("nombre") ?? "";

  const filteredSearches = mockSearches.filter((s) =>
    s.nombre.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const subPages = [
    { title: "Resultados",     base: "resultados", icon: BarChart3 },
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
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* ── Resultados guardados ──────────────────────── */}
        {!collapsed && (
          <SidebarGroup>
            <SidebarGroupLabel>Resultados</SidebarGroupLabel>
            <SidebarGroupContent>
              <div className="px-2 pb-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Buscar..."
                    className="h-8 pl-8 text-xs bg-muted/30 border-border"
                  />
                </div>
              </div>
              <SidebarMenu>
                {filteredSearches.length === 0 ? (
                  <div className="px-3 py-4 text-center">
                    <Ghost className="h-5 w-5 mx-auto mb-1.5 text-muted-foreground/50" />
                    <p className="text-xs text-muted-foreground/70">Sin resultados</p>
                  </div>
                ) : (
                  filteredSearches.map((s) => (
                    <SidebarMenuItem key={s.id}>
                      <SidebarMenuButton asChild>
                        <NavLink
                          to={`/resultados/${s.id}`}
                          className="hover:bg-muted/50 flex items-center gap-2"
                          activeClassName="bg-primary/10 text-primary font-medium"
                        >
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-medium truncate">{s.nombre}</p>
                            <p className="text-[10px] text-muted-foreground truncate">{s.fecha} · {s.hallazgos} hallazgos</p>
                          </div>
                          <RiskBadge level={s.riesgo} />
                        </NavLink>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))
                )}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

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
