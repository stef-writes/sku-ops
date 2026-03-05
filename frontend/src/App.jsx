import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { queryClient } from "./lib/query-client";
import { ROLES, ADMIN_ROLES } from "./lib/constants";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import POS from "./pages/POS";
import Inventory from "./pages/inventory";
import Vendors from "./pages/Vendors";
import Departments from "./pages/Departments";
import ReceiptImport from "./pages/ReceiptImport";
import PurchaseOrders from "./pages/PurchaseOrders";
import Reports from "./pages/Reports";
import Contractors from "./pages/Contractors";
import Financials from "./pages/Financials";
import Invoices from "./pages/Invoices";
import MyHistory from "./pages/MyHistory";
import RequestMaterials from "./pages/RequestMaterials";
import PendingRequests from "./pages/PendingRequests";
import Layout from "./components/Layout";

const ProtectedRoute = ({ children, allowedRoles }) => {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-slate-600 font-heading text-xl uppercase tracking-wider">Loading...</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (allowedRoles && !allowedRoles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
};

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Toaster position="top-center" richColors />
          <ErrorBoundary>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route
                path="/*"
                element={
                  <ProtectedRoute>
                    <Layout>
                      <ErrorBoundary>
                        <Routes>
                          <Route path="/" element={<Dashboard />} />
                          <Route path="/pos" element={<ProtectedRoute allowedRoles={ADMIN_ROLES}><POS /></ProtectedRoute>} />
                          <Route path="/request-materials" element={<ProtectedRoute allowedRoles={[ROLES.CONTRACTOR]}><RequestMaterials /></ProtectedRoute>} />
                          <Route path="/pending-requests" element={<ProtectedRoute allowedRoles={ADMIN_ROLES}><PendingRequests /></ProtectedRoute>} />
                          <Route path="/inventory" element={<ProtectedRoute allowedRoles={ADMIN_ROLES}><Inventory /></ProtectedRoute>} />
                          <Route path="/vendors" element={<ProtectedRoute allowedRoles={ADMIN_ROLES}><Vendors /></ProtectedRoute>} />
                          <Route path="/departments" element={<ProtectedRoute allowedRoles={ADMIN_ROLES}><Departments /></ProtectedRoute>} />
                          <Route path="/import" element={<ProtectedRoute allowedRoles={ADMIN_ROLES}><ReceiptImport /></ProtectedRoute>} />
                          <Route path="/purchase-orders" element={<ProtectedRoute allowedRoles={ADMIN_ROLES}><PurchaseOrders /></ProtectedRoute>} />
                          <Route path="/reports" element={<ProtectedRoute allowedRoles={ADMIN_ROLES}><Reports /></ProtectedRoute>} />
                          <Route path="/contractors" element={<ProtectedRoute allowedRoles={[ROLES.ADMIN]}><Contractors /></ProtectedRoute>} />
                          <Route path="/financials" element={<ProtectedRoute allowedRoles={[ROLES.ADMIN]}><Financials /></ProtectedRoute>} />
                          <Route path="/invoices" element={<ProtectedRoute allowedRoles={[ROLES.ADMIN]}><Invoices /></ProtectedRoute>} />
                          <Route path="/my-history" element={<ProtectedRoute allowedRoles={[ROLES.CONTRACTOR]}><MyHistory /></ProtectedRoute>} />
                        </Routes>
                      </ErrorBoundary>
                    </Layout>
                  </ProtectedRoute>
                }
              />
            </Routes>
          </ErrorBoundary>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
