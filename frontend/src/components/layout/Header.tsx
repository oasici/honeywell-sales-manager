import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { translateUserRole } from '../../lib/labelTranslations';
import { notificationsApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Bell, Check, CheckCheck, ExternalLink } from 'lucide-react';
import { useT } from '../../hooks/useT';

interface Notification {
  id: number;
  title: string;
  message: string;
  is_read: boolean;
  entity_type?: string | null;
  entity_id?: number | null;
  created_at: string;
}

// Reduced from 30s to 90s for scale (1500+ users → 50 req/s → ~17 req/s)
const POLL_INTERVAL_MS = 90_000;
const RECENT_NOTIFICATIONS_LIMIT = 10;

function getEntityRoute(entityType?: string | null, entityId?: number | null): string | null {
  if (!entityType || !entityId) return null;
  if (entityType === 'email') return `/emails/${entityId}`;
  if (entityType === 'quote') return `/quotes/${entityId}`;
  return null;
}

function getInitial(name?: string): string {
  return (name?.trim()?.[0] ?? '?').toUpperCase();
}

export function Header() {
  const user = useAuthStore((state) => state.user);
  const navigate = useNavigate();
  const t = useT();
  const roleLabel = user?.role ? translateUserRole(user.role, t) : '';

  const queryClient = useQueryClient();
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // R14-FE-1 exempt: chrome notification badge polling — empty badge is acceptable on transient failure
  const { data: unreadData } = useQuery<{ unread_count: number }>({
    queryKey: ['notifications', 'unread-count'],
    queryFn: notificationsApi.getUnreadCount,
    refetchInterval: POLL_INTERVAL_MS,
  });

  const unreadCount = unreadData?.unread_count ?? 0;

  const { data: notifications, isLoading: isNotificationsLoading } = useQuery<Notification[]>({
    queryKey: ['notifications', 'recent'],
    queryFn: () => notificationsApi.getNotifications<Notification>(false, RECENT_NOTIFICATIONS_LIMIT),
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
    <header className="flex h-16 items-center justify-end border-b border-slate-200 bg-white px-6 dark:border-slate-800 dark:bg-slate-950">
      <div className="flex items-center gap-3">
        {/* Notification bell */}
        <div className="relative" ref={dropdownRef}>
          <button
            className="relative inline-flex h-9 w-9 items-center justify-center rounded-[10px] text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            title={t('notifications.title')}
            aria-expanded={isDropdownOpen}
            aria-haspopup="true"
            onClick={handleBellClick}
          >
            <Bell size={18} className="shrink-0" />
            {unreadCount > 0 && (
              <span
                className="absolute -top-0.5 -right-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-honeywell-red px-1 text-[10px] font-semibold leading-none text-white ring-2 ring-white dark:ring-slate-950"
                aria-label={`${unreadCount} ${t('notifications.unread_suffix')}`}
              >
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>

          {/* Dropdown */}
          {isDropdownOpen && (
            <div
              className="absolute right-0 top-full z-50 mt-2 w-[380px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xl) dark:border-slate-800 dark:bg-slate-900"
              role="menu"
            >
              <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <h3 className="text-[13px] font-semibold text-slate-900 dark:text-slate-100">
                    {t('notifications.title')}
                  </h3>
                  {unreadCount > 0 && (
                    <Badge variant="danger" size="sm" dot>
                      {unreadCount}
                    </Badge>
                  )}
                </div>
                {unreadCount > 0 && (
                  <Button
                    variant="tertiary"
                    size="sm"
                    onClick={handleMarkAllRead}
                    loading={markAllReadMutation.isPending}
                  >
                    <CheckCheck size={14} className="shrink-0" />
                    {t('notifications.mark_all_read')}
                  </Button>
                )}
              </div>

              <div className="max-h-[420px] overflow-y-auto">
                {isNotificationsLoading ? (
                  <div className="space-y-1 p-3">
                    {[0, 1, 2].map((i) => (
                      <div
                        key={i}
                        className="h-14 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800"
                      />
                    ))}
                  </div>
                ) : notificationList.length === 0 ? (
                  <div className="px-4 py-2">
                    <EmptyState
                      variant="compact"
                      icon={<Bell size={18} />}
                      title={t('notifications.none')}
                    />
                  </div>
                ) : (
                  <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                    {notificationList.map((notification) => {
                      const route = getEntityRoute(
                        notification.entity_type,
                        notification.entity_id,
                      );
                      return (
                        <li key={notification.id}>
                          <button
                            type="button"
                            className={[
                              'group relative flex w-full items-start gap-3 px-4 py-3 text-left transition-colors',
                              'hover:bg-slate-50 dark:hover:bg-slate-800/60',
                              !notification.is_read ? 'bg-honeywell-red/4' : '',
                            ].join(' ')}
                            onClick={() => {
                              if (!notification.is_read) {
                                handleMarkRead(notification.id);
                              }
                              if (route) {
                                setIsDropdownOpen(false);
                                navigate(route);
                              }
                            }}
                            role="menuitem"
                          >
                            {/* Unread indicator dot */}
                            <span
                              className={[
                                'mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full',
                                notification.is_read ? 'bg-transparent' : 'bg-honeywell-red',
                              ].join(' ')}
                              aria-hidden
                            />
                            <div className="min-w-0 flex-1">
                              <p
                                className={[
                                  'text-[13px] leading-5',
                                  notification.is_read
                                    ? 'text-slate-600 dark:text-slate-300'
                                    : 'font-semibold text-slate-900 dark:text-white',
                                ].join(' ')}
                              >
                                {notification.title}
                              </p>
                              <p className="mt-0.5 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">
                                {notification.message}
                              </p>
                              <p className="mt-1 text-[11px] tabular-nums text-slate-400 dark:text-slate-500">
                                {formatDateTime(notification.created_at)}
                              </p>
                            </div>
                            <div className="mt-1 flex shrink-0 items-center gap-1 text-slate-400">
                              {route && (
                                <ExternalLink size={12} className="opacity-0 transition-opacity group-hover:opacity-100" />
                              )}
                              {!notification.is_read && (
                                <span title={t('notifications.mark_read')}>
                                  <Check size={14} className="text-honeywell-red" />
                                </span>
                              )}
                            </div>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Vertical divider */}
        <div className="h-6 w-px bg-slate-200 dark:bg-slate-800" aria-hidden />

        {/* User info */}
        <div className="flex items-center gap-2.5">
          <span
            className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-honeywell-red/10 text-[13px] font-semibold text-honeywell-red ring-1 ring-inset ring-honeywell-red/20"
            aria-hidden
          >
            {getInitial(user?.full_name)}
          </span>
          <div className="text-right">
            <p className="text-[13px] font-medium leading-tight text-slate-900 dark:text-slate-100">
              {user?.full_name || t('common.user')}
            </p>
            {roleLabel && (
              <p className="text-[11px] leading-tight text-slate-500 dark:text-slate-400">
                {roleLabel}
              </p>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
