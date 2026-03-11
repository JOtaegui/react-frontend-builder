import { useParams, useLocation } from "react-router-dom";
import { Fingerprint, Home, BarChart3, FileSearch, ClipboardCheck, Ghost, UserSearch } from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { mockSearches } from "@/data/mockData";
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

  // Determine active id from any route
  const activeId = id || location.pathname.match(/\/(resultados|hallazgos|plan)\/(\w+)/)?.[2];

  const subPages = [
    { title: "Resultados", base: "resultados", icon: BarChart3 },
    { title: "Hallazgos", base: "hallazgos", icon: FileSearch },
    { title: "Plan de Acción", base: "plan", icon: ClipboardCheck },
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
        {/* Main nav */}
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
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Searches list */}
        <SidebarGroup>
          <SidebarGroupLabel>
            <UserSearch className="h-3.5 w-3.5 mr-1.5" />
            Búsquedas
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {mockSearches.length === 0 ? (
                <div className="px-3 py-4 text-center">
                  <Ghost className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
                  {!collapsed && (
                    <p className="text-xs text-muted-foreground">Aún no hay resultados</p>
                  )}
                </div>
              ) : (
                mockSearches.map((s) => (
                  <SidebarMenuItem key={s.id}>
                    <SidebarMenuButton asChild>
                      <NavLink
                        to={`/resultados/${s.id}`}
                        className={`hover:bg-muted/50 ${activeId === s.id ? "bg-primary/10 text-primary font-medium" : ""}`}
                      >
                        <span className={`shrink-0 h-2 w-2 rounded-full mr-2 ${
                          s.riesgo === "Crítico" ? "bg-destructive" :
                          s.riesgo === "Alto" ? "bg-orange-500" :
                          s.riesgo === "Medio" ? "bg-yellow-500" :
                          "bg-primary"
                        }`} />
                        {!collapsed && (
                          <span className="truncate text-xs">{s.nombre.split(" ").slice(0, 2).join(" ")}</span>
                        )}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Sub-pages for active search */}
        {activeId && (
          <SidebarGroup defaultOpen>
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
