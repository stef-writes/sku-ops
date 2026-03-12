import { useState } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "@/lib/constants";
import {
  LayoutDashboard,
  ShoppingCart,
  Package,
  Users,
  Layers,
  Truck,
  BarChart3,
  LogOut,
  Wrench,
  HardHat,
  History,
  FileText,
  ClipboardList,
  ClipboardCheck,
  Building2,
  CreditCard,
  ShieldCheck,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  ScanBarcode,
} from "lucide-react";
import ChatAssistant from "./ChatAssistant";

const SIDEBAR_KEY = "sidebar-collapsed";

const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDEBAR_KEY) === "true");

  const toggleSidebar = () => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(SIDEBAR_KEY, String(next));
      return next;
    });
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const getNavGroups = () => {
    const role = user?.role;

    if (role === ROLES.CONTRACTOR) {
      return [
        {
          items: [
            { path: "/", icon: LayoutDashboard, label: "Dashboard" },
            {
              path: "/request-materials",
              icon: ShoppingCart,
              label: "Request Materials",
            },
            { path: "/scan", icon: ScanBarcode, label: "Scan & Checkout" },
            { path: "/my-history", icon: History, label: "My History" },
          ],
        },
      ];
    }

    const operationsItems = [
      { path: "/pos", icon: ShoppingCart, label: "Issue Materials" },
      {
        path: "/pending-requests",
        icon: ClipboardList,
        label: "Pending Requests",
      },
      { path: "/contractors", icon: HardHat, label: "Contractors" },
      { path: "/billing-entities", icon: Building2, label: "Billing Entities" },
    ];

    const purchasingItems = [
      { path: "/import", icon: Truck, label: "Receive / Import" },
      {
        path: "/purchase-orders",
        icon: ClipboardList,
        label: "Purchase Orders",
      },
      { path: "/vendors", icon: Users, label: "Vendors" },
    ];

    const inventoryItems = [
      { path: "/inventory", icon: Package, label: "Products" },
      { path: "/departments", icon: Layers, label: "Departments" },
      { path: "/cycle-counts", icon: ClipboardCheck, label: "Stock Counts" },
    ];

    const financeItems = [
      { path: "/invoices", icon: FileText, label: "Invoices" },
      { path: "/payments", icon: CreditCard, label: "Payments" },
      {
        path: "/xero-health",
        icon: ShieldCheck,
        label: "Xero Sync Health",
      },
    ];

    const reportItems = [{ path: "/reports", icon: BarChart3, label: "Reports" }];

    const groups = [
      { items: [{ path: "/", icon: LayoutDashboard, label: "Dashboard" }] },
      { section: "Operations", items: operationsItems },
      { section: "Purchasing", items: purchasingItems },
      { section: "Inventory", items: inventoryItems },
      { section: "Finance", items: financeItems },
      { section: "Reports", items: reportItems },
    ];

    if (role === ROLES.ADMIN) {
      groups.push({
        section: "System",
        items: [{ path: "/settings", icon: Settings, label: "Settings" }],
      });
    }

    return groups;
  };

  const navGroups = getNavGroups();

  const getRoleBadge = () => {
    return user?.role === ROLES.ADMIN ? "bg-destructive" : "bg-success";
  };

  const getRoleLabel = () => {
    return user?.role === ROLES.ADMIN ? "Admin" : "Contractor";
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex" data-testid="app-layout">
      <aside
        className={`${collapsed ? "w-16" : "w-64"} bg-sidebar text-sidebar-foreground flex flex-col border-r border-sidebar-border/80 shadow-soft transition-[width] duration-200 ease-in-out overflow-hidden shrink-0`}
        data-testid="sidebar"
      >
        {/* Header */}
        <div className="p-3 border-b border-sidebar-border flex items-center justify-between gap-2 min-h-[64px]">
          {!collapsed && (
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 bg-gradient-to-br from-accent-gradient-from to-accent-gradient-to rounded-xl flex items-center justify-center shadow-sm ring-1 ring-accent/40 shrink-0">
                <Wrench className="w-5 h-5 text-accent-foreground" />
              </div>
              <div className="min-w-0">
                <h1 className="font-semibold text-sidebar-foreground tracking-tight truncate">
                  Supply Yard
                </h1>
                <p className="text-xs text-sidebar-muted truncate">Material management</p>
              </div>
            </div>
          )}
          {collapsed && (
            <div className="w-10 h-10 bg-gradient-to-br from-accent-gradient-from to-accent-gradient-to rounded-xl flex items-center justify-center shadow-sm ring-1 ring-accent/40 mx-auto">
              <Wrench className="w-5 h-5 text-accent-foreground" />
            </div>
          )}
          <button
            onClick={toggleSidebar}
            className={`p-1.5 text-sidebar-muted hover:text-sidebar-foreground hover:bg-white/5 rounded-lg transition-colors shrink-0 ${collapsed ? "hidden" : ""}`}
            aria-label="Collapse sidebar"
            data-testid="sidebar-toggle"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        </div>

        {/* Nav */}
        <nav
          className="flex-1 py-4 px-2 overflow-y-auto overflow-x-hidden"
          data-testid="sidebar-nav"
        >
          {/* Expand button when collapsed */}
          {collapsed && (
            <button
              onClick={toggleSidebar}
              className="w-10 h-10 mx-auto flex items-center justify-center text-sidebar-muted hover:text-sidebar-foreground hover:bg-white/5 rounded-lg transition-colors mb-3"
              aria-label="Expand sidebar"
            >
              <PanelLeftOpen className="w-4 h-4" />
            </button>
          )}

          {navGroups.map((group, gi) => (
            <div key={gi} className={gi > 0 ? "mt-4" : ""}>
              {group.section && !collapsed && (
                <p className="px-3 mb-1 text-[10px] font-semibold text-sidebar-muted uppercase tracking-[0.14em]">
                  {group.section}
                </p>
              )}
              {group.section && collapsed && (
                <div className="mx-auto w-6 border-t border-sidebar-border/50 mb-2 mt-1" />
              )}
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === "/"}
                    title={collapsed ? item.label : undefined}
                    className={({ isActive }) => {
                      if (item.path.startsWith("/reports?")) {
                        const activeTab = new URLSearchParams(item.path.split("?")[1]).get("tab");
                        const currentTab = new URLSearchParams(location.search).get("tab");
                        const isReportActive =
                          location.pathname === "/reports" && currentTab === activeTab;
                        return `sidebar-link ${isReportActive ? "active" : ""} ${collapsed ? "justify-center px-0 w-10 mx-auto" : ""}`;
                      }
                      return `sidebar-link ${isActive ? "active" : ""} ${collapsed ? "justify-center px-0 w-10 mx-auto" : ""}`;
                    }}
                    data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                  >
                    <item.icon className="w-5 h-5 shrink-0" />
                    {!collapsed && <span className="font-medium text-sm">{item.label}</span>}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-3 border-t border-sidebar-border">
          {collapsed ? (
            <button
              onClick={handleLogout}
              title="Sign out"
              className="w-10 h-10 mx-auto flex items-center justify-center text-sidebar-muted hover:text-sidebar-foreground hover:bg-white/5 rounded-lg transition-colors"
              data-testid="logout-btn"
            >
              <LogOut className="w-5 h-5" />
            </button>
          ) : (
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-sm text-sidebar-foreground truncate">{user?.name}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${getRoleBadge()}`} />
                  <p className="text-xs text-sidebar-muted truncate">{getRoleLabel()}</p>
                </div>
                {user?.company && (
                  <p className="text-xs text-sidebar-muted/70 truncate mt-0.5">{user.company}</p>
                )}
              </div>
              <button
                onClick={handleLogout}
                className="p-2 text-sidebar-muted hover:text-sidebar-foreground hover:bg-white/5 rounded-lg transition-colors shrink-0"
                data-testid="logout-btn"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          )}
        </div>
      </aside>

      <main
        className="flex-1 min-h-0 overflow-auto bg-surface-muted/35 flex flex-col"
        data-testid="main-content"
      >
        {children}
      </main>

      {user?.role !== ROLES.CONTRACTOR && <ChatAssistant />}
    </div>
  );
};

export default Layout;
