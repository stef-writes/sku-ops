import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  LayoutDashboard,
  ShoppingCart,
  Package,
  Users,
  Layers,
  FileUp,
  BarChart3,
  LogOut,
  Wrench,
  HardHat,
  DollarSign,
  History,
} from "lucide-react";

const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  // Role-based navigation
  const getNavItems = () => {
    const role = user?.role;
    
    if (role === "contractor") {
      return [
        { path: "/", icon: LayoutDashboard, label: "Dashboard" },
        { path: "/pos", icon: ShoppingCart, label: "Withdraw Materials" },
        { path: "/my-history", icon: History, label: "My History" },
      ];
    }
    
    if (role === "warehouse_manager") {
      return [
        { path: "/", icon: LayoutDashboard, label: "Dashboard" },
        { path: "/pos", icon: ShoppingCart, label: "Material Terminal" },
        { path: "/inventory", icon: Package, label: "Inventory" },
        { path: "/vendors", icon: Users, label: "Vendors" },
        { path: "/departments", icon: Layers, label: "Departments" },
        { path: "/import", icon: FileUp, label: "Receipt Import" },
        { path: "/reports", icon: BarChart3, label: "Reports" },
      ];
    }
    
    // Admin gets everything
    return [
      { path: "/", icon: LayoutDashboard, label: "Dashboard" },
      { path: "/pos", icon: ShoppingCart, label: "Material Terminal" },
      { path: "/inventory", icon: Package, label: "Inventory" },
      { path: "/vendors", icon: Users, label: "Vendors" },
      { path: "/departments", icon: Layers, label: "Departments" },
      { path: "/import", icon: FileUp, label: "Receipt Import" },
      { path: "/contractors", icon: HardHat, label: "Contractors" },
      { path: "/financials", icon: DollarSign, label: "Financials" },
      { path: "/reports", icon: BarChart3, label: "Reports" },
    ];
  };

  const navItems = getNavItems();

  const getRoleBadge = () => {
    const role = user?.role;
    if (role === "admin") return "bg-red-500";
    if (role === "warehouse_manager") return "bg-blue-500";
    return "bg-green-500";
  };

  const getRoleLabel = () => {
    const role = user?.role;
    if (role === "admin") return "Admin";
    if (role === "warehouse_manager") return "Warehouse";
    return "Contractor";
  };

  return (
    <div className="min-h-screen bg-slate-50 flex" data-testid="app-layout">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 text-white flex flex-col" data-testid="sidebar">
        {/* Logo */}
        <div className="p-6 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-orange-500 rounded-sm flex items-center justify-center">
              <Wrench className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-heading font-bold text-xl uppercase tracking-wider">
                Supply Yard
              </h1>
              <p className="text-xs text-slate-400">Material Management</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 px-3" data-testid="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) =>
                `sidebar-link mb-1 ${isActive ? "active" : ""}`
              }
              data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
            >
              <item.icon className="w-5 h-5" />
              <span className="font-medium">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* User Section */}
        <div className="p-4 border-t border-slate-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-sm">{user?.name}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className={`w-2 h-2 rounded-full ${getRoleBadge()}`}></span>
                <p className="text-xs text-slate-400">{getRoleLabel()}</p>
              </div>
              {user?.company && (
                <p className="text-xs text-slate-500 mt-1">{user.company}</p>
              )}
            </div>
            <button
              onClick={handleLogout}
              className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-sm transition-colors"
              data-testid="logout-btn"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto" data-testid="main-content">
        {children}
      </main>
    </div>
  );
};

export default Layout;
