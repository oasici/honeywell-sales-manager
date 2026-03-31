import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthGuard } from '../features/auth/AuthGuard';
import { LoginPage } from '../features/auth/LoginPage';
import { Layout } from '../components/layout/Layout';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { ErrorBoundary } from '../components/ui/ErrorBoundary';

const DashboardPage = lazy(() => import('../features/dashboard/DashboardPage'));
const EmailListPage = lazy(() => import('../features/emails/EmailListPage'));
const EmailDetailPage = lazy(() => import('../features/emails/EmailDetailPage'));
const PartsPage = lazy(() => import('../features/parts/PartsPage'));
const QuoteListPage = lazy(() => import('../features/quotes/QuoteListPage'));
const QuoteEditorPage = lazy(() => import('../features/quotes/QuoteEditorPage'));
const CustomerListPage = lazy(() => import('../features/customers/CustomerListPage'));
const CustomerDetailPage = lazy(() => import('../features/customers/CustomerDetailPage'));
const SettingsPage = lazy(() => import('../features/settings/SettingsPage'));
const ReportsPage = lazy(() => import('../features/admin/ReportsPage'));
const UserManagementPage = lazy(() => import('../features/admin/UserManagementPage'));
const AuditLogPage = lazy(() => import('../features/admin/AuditLogPage'));

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/"
        element={
          <AuthGuard>
            <Layout />
          </AuthGuard>
        }
      >
        <Route
          index
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <DashboardPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="emails"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <EmailListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="emails/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <EmailDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="parts"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <PartsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="quotes"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <QuoteListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="quotes/new"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <QuoteEditorPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="quotes/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <QuoteEditorPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="customers"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <CustomerListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="customers/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <CustomerDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="settings"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <SettingsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="reports"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <ReportsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="users"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <UserManagementPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="audit"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <AuditLogPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
