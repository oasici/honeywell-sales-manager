import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';

interface AuthGuardProps {
  children: React.ReactNode;
}

const FORCE_PASSWORD_PATH = '/auth/change-password';

export function AuthGuard({ children }: AuthGuardProps) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isLoading = useAuthStore((state) => state.isLoading);
  const bootstrap = useAuthStore((state) => state.bootstrap);
  const user = useAuthStore((state) => state.user);
  const location = useLocation();

  useEffect(() => {
    if (!isAuthenticated) {
      void bootstrap();
    }
  }, [isAuthenticated, bootstrap]);

  if (isLoading) {
    return null;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // R6-RENDER-4 — admin-reset / first-login users have a temporary
  // password and must replace it before navigating anywhere else. The
  // server flag clears on successful POST /auth/change-password.
  if (user?.password_change_required && location.pathname !== FORCE_PASSWORD_PATH) {
    return <Navigate to={FORCE_PASSWORD_PATH} replace />;
  }

  return <>{children}</>;
}
