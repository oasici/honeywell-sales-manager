import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { ROLE_LABELS } from '../../lib/constants';
import { notificationsApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Bell, Check, CheckCheck } from 'lucide-react';

interface Notification {
  id: number;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

const POLL_INTERVAL_MS = 30_000;
const RECENT_NOTIFICATIONS_LIMIT = 10;

export function Header() {
  const user = useAuthStore((state) => state.user);
  const roleLabel = user?.role ? ROLE_LABELS[user.role] || user.role : '';

  const queryClient = useQueryClient();
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { data: unreadData } = useQuery<{ unread_count: number }>({
    queryKey: ['notifications', 'unread-count'],
    queryFn: notificationsApi.getUnreadCount,
    refetchInterval: POLL_INTERVAL_MS,
  });

  const unreadCount = unreadData?.unread_count ?? 0;

  const { data: notifications, isLoading: isNotificationsLoading } = useQuery<Notification[]>({
    queryKey: ['notifications', 'recent'],
    queryFn: () => notificationsApi.getNotifications(false, RECENT_NOTIFICATIONS_LIMIT),
    enabled: isDropdownOpen,
  });

  const markReadMutation = useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    }

    if (isDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isDropdownOpen]);

  function handleBellClick() {
    setIsDropdownOpen((prev) => !prev);
  }

  function handleMarkRead(id: number) {
    markReadMutation.mutate(id);
  }

  function handleMarkAllRead() {
    markAllReadMutation.mutate();
  }

  const notificationList = Array.isArray(notifications) ? notifications : [];

  return (
    <header className="flex h-16 items-center justify-end border-b border-gray-200 bg-white px-6">
      <div className="flex items-center gap-4">
        {/* Notification bell */}
        <div className="relative" ref={dropdownRef}>
          <button
            className="relative rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
            title="Bildirimler"
            aria-expanded={isDropdownOpen}
            aria-haspopup="true"
            onClick={handleBellClick}
          >
            <Bell size={20} className="shrink-0" />
            {unreadCount > 0 && (
              <span
                className="absolute -top-0.5 -right-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white"
                aria-label={`${unreadCount} okunmamis bildirim`}
              >
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>

          {/* Dropdown */}
          {isDropdownOpen && (
            <div
              className="absolute right-0 top-full mt-2 w-96 rounded-xl border border-gray-200 bg-white shadow-lg z-50"
              role="menu"
            >
              <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
                <h3 className="text-sm font-semibold text-gray-900">Bildirimler</h3>
                {unreadCount > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleMarkAllRead}
                    loading={markAllReadMutation.isPending}
                  >
                    <CheckCheck size={14} className="shrink-0" />
                    Tumu okundu
                  </Button>
                )}
              </div>

              <div className="max-h-80 overflow-y-auto">
                {isNotificationsLoading ? (
                  <div className="space-y-2 p-4">
                    {[0, 1, 2].map((i) => (
                      <div key={i} className="h-12 animate-pulse rounded bg-gray-100" />
                    ))}
                  </div>
                ) : notificationList.length === 0 ? (
                  <p className="px-4 py-8 text-center text-sm text-gray-400">
                    Bildirim bulunmuyor
                  </p>
                ) : (
                  <ul>
                    {notificationList.map((notification) => (
                      <li key={notification.id}>
                        <button
                          type="button"
                          className={`flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-gray-50 ${
                            !notification.is_read ? 'bg-blue-50/50' : ''
                          }`}
                          onClick={() => {
                            if (!notification.is_read) {
                              handleMarkRead(notification.id);
                            }
                          }}
                          role="menuitem"
                        >
                          <div className="min-w-0 flex-1">
                            <p className={`text-sm ${notification.is_read ? 'text-gray-600' : 'font-semibold text-gray-900'}`}>
                              {notification.title}
                            </p>
                            <p className="mt-0.5 text-xs text-gray-400 line-clamp-2">
                              {notification.message}
                            </p>
                            <p className="mt-1 text-[10px] text-gray-300">
                              {formatDateTime(notification.created_at)}
                            </p>
                          </div>
                          {!notification.is_read && (
                            <span className="mt-1 shrink-0" title="Okundu olarak isaretle">
                              <Check size={14} className="text-blue-500" />
                            </span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>

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
