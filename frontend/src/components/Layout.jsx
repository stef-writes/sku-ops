import { NavLink, useNavigate } from "react-router-dom";
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
  Briefcase,
  Building2,
  CreditCard,
  ShieldCheck,
} from "lucide-react";
import ChatAssistant from "./ChatAssistant";

const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

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
            { path: "/request-materials", icon: ShoppingCart, label: "Request Materials" },
            { path: "/my-history", icon: History, label: "My History" },
          ],
        },
      ];
    }

    const operationsItems = [
      { path: "/pos", icon: ShoppingCart, label: "Issue Materials" },
      { path: "/pending-requests", icon: ClipboardList, label: "Pending Requests" },
      { path: "/contractors", icon: HardHat, label: "Contractors" },
      { path: "/jobs", icon: Briefcase, label: "Jobs" },
    ];

    const inventoryItems = [
      { path: "/inventory", icon: Package, label: "Inventory" },
      { path: "/cycle-counts", icon: ClipboardCheck, label: "Cycle Counts" },
      { path: "/vendors", icon: Users, label: "Vendors" },
      { path: "/departments", icon: Layers, label: "Departments" },
      { path: "/import", icon: Truck, label: "Receive / Import" },
      { path: "/purchase-orders", icon: ClipboardList, label: "Purchase Orders" },
    ];

    const analyticsItems = [
      { path: "/reports", icon: BarChart3, label: "Reports" },
    ];

    if (role === ROLES.ADMIN) {
      analyticsItems.push(
        { path: "/invoices", icon: FileText, label: "Invoices" },
        { path: "/payments", icon: CreditCard, label: "Payments" },
        { path: "/billing-entities", icon: Building2, label: "Billing Entities" },
        { path: "/xero-health", icon: ShieldCheck, label: "Xero Sync Health" },
      );
    }

    return [
      { items: [{ path: "/", icon: LayoutDashboard, label: "Dashboard" }] },
      { section: "Operations", items: operationsItems },
      { section: "Inventory", items: inventoryItems },
      { section: "Analytics & Finance", items: analyticsItems },
    ];
  };

  const navGroups = getNavGroups();

  const getRoleBadge = () => {
    const role = user?.role;
    if (role === ROLES.ADMIN) return "bg-destructive";
    if (role === ROLES.WAREHOUSE_MANAGER) return "bg-info";
    return "bg-success";
  };

  const getRoleLabel = () => {
    const role = user?.role;
    if (role === ROLES.ADMIN) return "Admin";
    if (role === ROLES.WAREHOUSE_MANAGER) return "Warehouse";
    return "Contractor";
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex" data-testid="app-layout">
      <aside className="w-64 bg-sidebar text-sidebar-foreground flex flex-col border-r border-sidebar-border/80 shadow-soft" data-testid="sidebar">
        <div className="p-5 border-b border-sidebar-border">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-accent-gradient-from to-accent-gradient-to rounded-xl flex items-center justify-center shadow-sm ring-1 ring-accent/40">
              <Wrench className="w-5 h-5 text-accent-foreground" />
            </div>
            <div>
              <h1 className="font-semibold text-sidebar-foreground tracking-tight">Supply Yard</h1>
              <p className="text-xs text-sidebar-muted">Material management</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 py-4 px-3 overflow-y-auto" data-testid="sidebar-nav">
          {navGroups.map((group, gi) => (
            <div key={gi} className={gi > 0 ? "mt-4" : ""}>
              {group.section && (
                <p className="px-3 mb-1 text-[10px] font-semibold text-sidebar-muted uppercase tracking-[0.14em]">
                  {group.section}
                </p>
              )}
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === "/"}
                    className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
                    data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                  >
                    <item.icon className="w-5 h-5 shrink-0" />
                    <span className="font-medium text-sm">{item.label}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="p-4 border-t border-sidebar-border">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="font-medium text-sm text-sidebar-foreground truncate">{user?.name}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`w-2 h-2 rounded-full shrink-0 ${getRoleBadge()}`} />
                <p className="text-xs text-sidebar-muted truncate">{getRoleLabel()}</p>
              </div>
              {user?.company && <p className="text-xs text-sidebar-muted/70 truncate mt-0.5">{user.company}</p>}
            </div>
            <button
              onClick={handleLogout}
              className="p-2 text-sidebar-muted hover:text-sidebar-foreground hover:bg-white/5 rounded-lg transition-colors shrink-0"
              data-testid="logout-btn"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 min-h-0 overflow-auto bg-surface-muted/35 flex flex-col" data-testid="main-content">
        {children}
      </main>

      {user?.role !== ROLES.CONTRACTOR && <ChatAssistant />}
    </div>
  );
};

export default Layout;
