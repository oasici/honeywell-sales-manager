import { useAuthStore } from '../../stores/authStore';
import { ROLE_LABELS } from '../../lib/constants';
import { Badge } from '../ui/Badge';
import { Bell } from 'lucide-react';

export function Header() {
  const user = useAuthStore((state) => state.user);
  const roleLabel = user?.role ? ROLE_LABELS[user.role] || user.role : '';

  return (
    <header className="flex h-16 items-center justify-end border-b border-gray-200 bg-white px-6">
      <div className="flex items-center gap-4">
        {/* Notification bell (placeholder) */}
        <button
          className="relative rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          title="Bildirimler"
        >
          <Bell size={20} className="shrink-0" />
        </button>

        {/* User info */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-sm font-medium text-gray-700">{user?.full_name || 'Kullanici'}</p>
          </div>
          {roleLabel && (
            <Badge variant="info" size="sm">
              {roleLabel}
            </Badge>
          )}
        </div>
      </div>
    </header>
  );
}
