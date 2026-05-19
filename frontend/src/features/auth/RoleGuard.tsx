import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';

/**
 * Round-15 audit F-032 — SPA-side role gate for admin-only routes.
 *
 * The backend already enforces role at the API layer (every admin
 * endpoint declares ``Depends(require_role(UserRole.SALES_MANAGER))``)
 * so this is **not** a security control — a sales_rep trying to call
 * an admin API still gets 403. ``RoleGuard`` exists to close the UX
 * hole where a rep typing ``/admin/field-permissions`` into the URL
 * landed on a half-rendered admin page that failed silently on every
 * mutation.
 *
 * Usage in App.tsx:
 *   <Route path="/admin/*" element={
 *     <RoleGuard role="sales_manager">
 *       <AdminRoutes />
 *     </RoleGuard>
 *   } />
 *
 * Accepted roles map to ``UserRole`` server enum:
 *   - ``sales_manager`` — admin tooling
 *   - ``operations``    — billing/reconciliation tooling
 *   - ``sales_rep``     — default; not used as a gate keyword
 */

type AllowedRole = 'sales_manager' | 'operations';

interface RoleGuardProps {
  role: AllowedRole | AllowedRole[];
  /** Where to redirect when the user doesn't match. Defaults to ``/``. */
  redirectTo?: string;
  children: React.ReactNode;
}

export function RoleGuard({ role, redirectTo = '/', children }: RoleGuardProps) {
  const user = useAuthStore((state) => state.user);
  const location = useLocation();

  const allowed = Array.isArray(role) ? role : [role];
  const currentRole = user?.role;

  if (!currentRole || !allowed.includes(currentRole as AllowedRole)) {
    return <Navigate to={redirectTo} state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
