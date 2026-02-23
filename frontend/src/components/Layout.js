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
} from "lucide-react";

const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const navItems = [
    { path: "/", icon: LayoutDashboard, label: "Dashboard" },
    { path: "/pos", icon: ShoppingCart, label: "Point of Sale" },
    { path: "/inventory", icon: Package, label: "Inventory" },
    { path: "/vendors", icon: Users, label: "Vendors" },
    { path: "/departments", icon: Layers, label: "Departments" },
    { path: "/import", icon: FileUp, label: "Receipt Import" },
    { path: "/reports", icon: BarChart3, label: "Reports" },
  ];

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
                SKU Central
              </h1>
              <p className="text-xs text-slate-400">Hardware Store POS</p>
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
              <p className="text-xs text-slate-400 capitalize">{user?.role}</p>
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
