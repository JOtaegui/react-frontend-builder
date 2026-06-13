import { useParams, useLocation } from "react-router-dom";
import {
  Fingerprint, Home, BarChart3, FileSearch, ClipboardCheck, Search, MailSearch, Network, Telescope, ShieldOff, Chrome, DatabaseZap, LayoutDashboard,
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
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

  const activeId = id || location.pathname.match(/\/(resultados|hallazgos|plan)\/(\w+)/)?.[2];
  const dorksNombre = new URLSearchParams(location.search).get("nombre") ?? "";

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
                  <NavLink to="/resultados" end className="hover:bg-muted/50" activeClassName="bg-primary/10 text-primary font-medium">
                    <BarChart3 className="mr-2 h-4 w-4" />
                    {!collapsed && <span>Resultados</span>}
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <NavLink to="/identificacion-email" className="hover:bg-muted/50" activeClassName="bg-primary/10 text-primary font-medium">
                    <MailSearch className="mr-2 h-4 w-4" />
                    {!collapsed && <span>Identificación</span>}
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <NavLink to="/consolidado" className="hover:bg-muted/50" activeClassName="bg-primary/10 text-primary font-medium">
                    <LayoutDashboard className="mr-2 h-4 w-4" />
                    {!collapsed && <span>Vista Consolidada</span>}
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <NavLink to="/historial-browser" className="hover:bg-muted/50" activeClassName="bg-primary/10 text-primary font-medium">
                    <Chrome className="mr-2 h-4 w-4" />
                    {!collapsed && <span>Historial Chrome</span>}
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <NavLink to="/filtraciones" className="hover:bg-muted/50" activeClassName="bg-primary/10 text-primary font-medium">
                    <DatabaseZap className="mr-2 h-4 w-4" />
                    {!collapsed && <span>Filtraciones</span>}
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <NavLink to="/baja-historial" className="hover:bg-muted/50" activeClassName="bg-primary/10 text-primary font-medium">
                    <ShieldOff className="mr-2 h-4 w-4" />
                    {!collapsed && <span>Historial de Bajas</span>}
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <NavLink to="/cabeceras-empresa-temp" className="hover:bg-muted/50" activeClassName="bg-primary/10 text-primary font-medium">
                    <Network className="mr-2 h-4 w-4" />
                    {!collapsed && <span>Cabeceras (Temp)</span>}
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <NavLink to="/exposicion-web-temp" className="hover:bg-muted/50" activeClassName="bg-primary/10 text-primary font-medium">
                    <Telescope className="mr-2 h-4 w-4" />
                    {!collapsed && <span>Exposición Web (Temp)</span>}
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
