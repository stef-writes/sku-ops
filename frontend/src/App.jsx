import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { queryClient } from "./lib/query-client";
import { ROLES } from "./lib/constants";
import { useRealtimeSync } from "./hooks/useRealtimeSync";
import Login from "./pages/Login";
import Layout from "./components/Layout";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Inventory = lazy(() => import("./pages/inventory"));
const CycleCountsPage = lazy(() => import("./pages/inventory/CycleCountsPage"));
const CycleCountDetailPage = lazy(() => import("./pages/inventory/CycleCountDetailPage"));
const Reports = lazy(() => import("./pages/Reports"));
const POS = lazy(() => import("./pages/operations/POS"));
const PendingRequests = lazy(() => import("./pages/operations/PendingRequests"));
const RequestMaterials = lazy(() => import("./pages/operations/RequestMaterials"));
const ScanModePage = lazy(() => import("./pages/operations/ScanModePage"));
const Contractors = lazy(() => import("./pages/operations/Contractors"));
const Departments = lazy(() => import("./pages/operations/Departments"));
const Vendors = lazy(() => import("./pages/operations/Vendors"));
const PurchaseOrders = lazy(() => import("./pages/operations/PurchaseOrders"));
const MyHistory = lazy(() => import("./pages/operations/MyHistory"));
const ReceiptImport = lazy(() => import("./pages/operations/ReceiptImport"));
const Jobs = lazy(() => import("./pages/operations/Jobs"));
const Invoices = lazy(() => import("./pages/finance/Invoices"));
const Payments = lazy(() => import("./pages/finance/Payments"));
const XeroHealthPage = lazy(() => import("./pages/finance/XeroHealthPage"));
const BillingEntities = lazy(() => import("./pages/identity/BillingEntities"));
const SettingsPage = lazy(() => import("./pages/settings/SettingsPage"));

const ProtectedRoute = ({ children, allowedRoles }) => {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen bg-muted flex items-center justify-center">
        <div className="text-muted-foreground font-heading text-xl uppercase tracking-wider">
          Loading...
        </div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (allowedRoles && !allowedRoles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
};

function RealtimeSync() {
  useRealtimeSync();
  return null;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Toaster position="top-center" richColors />
          <ErrorBoundary>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                path="/*"
                element={
                  <ProtectedRoute>
                    <RealtimeSync />
                    <Layout>
                      <ErrorBoundary>
                        <Suspense
                          fallback={
                            <div className="min-h-[50vh] flex items-center justify-center">
                              <div className="text-muted-foreground font-heading text-sm uppercase tracking-wider">
                                Loading...
                              </div>
                            </div>
                          }
                        >
                          <Routes>
                            <Route path="/" element={<Dashboard />} />
                            <Route
                              path="/pos"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <POS />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/request-materials"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.CONTRACTOR]}>
                                  <RequestMaterials />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/scan"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.CONTRACTOR, ROLES.ADMIN]}>
                                  <ScanModePage />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/pending-requests"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <PendingRequests />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/inventory"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <Inventory />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/cycle-counts"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <CycleCountsPage />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/cycle-counts/:countId"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <CycleCountDetailPage />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/vendors"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <Vendors />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/departments"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <Departments />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/import"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <ReceiptImport />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/purchase-orders"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <PurchaseOrders />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/reports"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <Reports />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/contractors"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <Contractors />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/jobs"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <Jobs />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/financials"
                              element={<Navigate to="/reports" replace />}
                            />
                            <Route
                              path="/invoices"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <Invoices />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/payments"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <Payments />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/billing-entities"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <BillingEntities />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/xero-health"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <XeroHealthPage />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/settings"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.ADMIN]}>
                                  <SettingsPage />
                                </ProtectedRoute>
                              }
                            />
                            <Route
                              path="/my-history"
                              element={
                                <ProtectedRoute allowedRoles={[ROLES.CONTRACTOR]}>
                                  <MyHistory />
                                </ProtectedRoute>
                              }
                            />
                          </Routes>
                        </Suspense>
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
