import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import POS from "./pages/POS";
import Inventory from "./pages/Inventory";
import Vendors from "./pages/Vendors";
import Departments from "./pages/Departments";
import ReceiptImport from "./pages/ReceiptImport";
import PurchaseOrders from "./pages/PurchaseOrders";
import Reports from "./pages/Reports";
import ProductPerformance from "./pages/ProductPerformance";
import Contractors from "./pages/Contractors";
import Financials from "./pages/Financials";
import Invoices from "./pages/Invoices";
import MyHistory from "./pages/MyHistory";
import RequestMaterials from "./pages/RequestMaterials";
import PendingRequests from "./pages/PendingRequests";
import Graphs from "./pages/Graphs";
import Layout from "./components/Layout";
import "./App.css";

const ProtectedRoute = ({ children, allowedRoles }) => {
  const { user, loading } = useAuth();
  
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-slate-600 font-heading text-xl uppercase tracking-wider">Loading...</div>
      </div>
    );
  }
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  
  return children;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-center" richColors />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/graphs"
            element={
              <ProtectedRoute allowedRoles={["admin", "warehouse_manager"]}>
                <Graphs />
              </ProtectedRoute>
            }
          />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <Layout>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route
                      path="/pos"
                      element={
                        <ProtectedRoute allowedRoles={["admin", "warehouse_manager"]}>
                          <POS />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/request-materials"
                      element={
                        <ProtectedRoute allowedRoles={["contractor"]}>
                          <RequestMaterials />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/pending-requests"
                      element={
                        <ProtectedRoute allowedRoles={["admin", "warehouse_manager"]}>
                          <PendingRequests />
                        </ProtectedRoute>
                      }
                    />
                    <Route 
                      path="/inventory" 
                      element={
                        <ProtectedRoute allowedRoles={["admin", "warehouse_manager"]}>
                          <Inventory />
                        </ProtectedRoute>
                      } 
                    />
                    <Route 
                      path="/vendors" 
                      element={
                        <ProtectedRoute allowedRoles={["admin", "warehouse_manager"]}>
                          <Vendors />
                        </ProtectedRoute>
                      } 
                    />
                    <Route 
                      path="/departments" 
                      element={
                        <ProtectedRoute allowedRoles={["admin", "warehouse_manager"]}>
                          <Departments />
                        </ProtectedRoute>
                      } 
                    />
                    <Route 
                      path="/import" 
                      element={
                        <ProtectedRoute allowedRoles={["admin", "warehouse_manager"]}>
                          <ReceiptImport />
                        </ProtectedRoute>
                      } 
                    />
                    <Route 
                      path="/purchase-orders" 
                      element={
                        <ProtectedRoute allowedRoles={["admin", "warehouse_manager"]}>
                          <PurchaseOrders />
                        </ProtectedRoute>
                      } 
                    />
                    <Route
                      path="/reports"
                      element={
                        <ProtectedRoute allowedRoles={["admin", "warehouse_manager"]}>
                          <Reports />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="/product-performance"
                      element={
                        <ProtectedRoute allowedRoles={["admin", "warehouse_manager"]}>
                          <ProductPerformance />
                        </ProtectedRoute>
                      }
                    />
                    <Route 
                      path="/contractors" 
                      element={
                        <ProtectedRoute allowedRoles={["admin"]}>
                          <Contractors />
                        </ProtectedRoute>
                      } 
                    />
                    <Route 
                      path="/financials" 
                      element={
                        <ProtectedRoute allowedRoles={["admin"]}>
                          <Financials />
                        </ProtectedRoute>
                      } 
                    />
                    <Route 
                      path="/invoices" 
                      element={
                        <ProtectedRoute allowedRoles={["admin"]}>
                          <Invoices />
                        </ProtectedRoute>
                      } 
                    />
                    <Route
                      path="/my-history"
                      element={
                        <ProtectedRoute allowedRoles={["contractor"]}>
                          <MyHistory />
                        </ProtectedRoute>
                      }
                    />
                  </Routes>
                </Layout>
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
