import { useState, useRef, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { MessageSquare, UserCheck, X, Send, Search, Settings2, Inbox, History } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { chatApi } from '../../lib/api';
import { onChatMessageChanged, onChatSessionChanged } from '../../lib/cacheInvalidation';
import type { ChatSession, ChatMessage } from '../../lib/types';
import { useT } from '../../hooks/useT';
import { translateChatSessionStatus } from '../../lib/labelTranslations';

// Round-15 audit F-029 — polling cadence bumped 2x to cut DB load.
// Pre-fix the agent dashboard polled at 5s + 10s simultaneously (~18
// reqs/min per active operator). For a B2B CRM with 50+ operators
// that scales poorly. Bumped to 15s + 30s; pairs naturally with the
// notifications-SSE design (docs/audits/2026-05-19-15n-notifications-sse-design.md)
// — when SSE lands, AgentChat is the second consumer queued to migrate.
const SESSIONS_POLL_MS = 30_000;
const MESSAGES_POLL_MS = 15_000;

/**
 * Map session status → Badge variant. Open = success (live), assigned =
 * info (handled), closed = default (resolved).
 */
const STATUS_TONE: Record<string, 'success' | 'info' | 'default'> = {
  open: 'success',
  assigned: 'info',
  closed: 'default',
};

type FilterTab = 'open' | 'assigned' | 'mine' | 'closed';

export default function AgentChatPage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [messageInput, setMessageInput] = useState('');
  const [filterTab, setFilterTab] = useState<FilterTab>('open');
  const [searchQuery, setSearchQuery] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    data: sessionsData,
    isLoading: isSessionsLoading,
    isError: isSessionsError,
  // R14-FE-1 exempt: page has its own bespoke isSessionsError UI at AgentChatPage.tsx:156
  } = useQuery<ChatSession[]>({
    queryKey: ['chat-sessions'],
    queryFn: () => chatApi.listSessions(),
    refetchInterval: SESSIONS_POLL_MS,
  });

  const { data: messagesData } = useQuery<ChatMessage[]>({
    queryKey: ['chat-messages-agent', selectedSessionId],
    queryFn: () => chatApi.getMessages(selectedSessionId!),
    enabled: selectedSessionId !== null,
    refetchInterval: MESSAGES_POLL_MS,
  });

  const assignMutation = useMutation({
    mutationFn: (id: number) => chatApi.assignSession(id),
    onSuccess: () => {
      toast.success(t('chat.toast_assigned'));
      onChatSessionChanged(queryClient);
    },
    onError: () => toast.error(t('chat.toast_assign_failed')),
  });

  const closeMutation = useMutation({
    mutationFn: (id: number) => chatApi.closeSession(id),
    onSuccess: () => {
      toast.success(t('chat.toast_closed'));
      onChatSessionChanged(queryClient);
    },
    onError: () => toast.error(t('chat.toast_close_failed')),
  });

  const sendMutation = useMutation({
    mutationFn: (content: string) =>
      chatApi.sendMessage(selectedSessionId!, {
        content,
        sender_type: 'agent',
      }),
    onSuccess: () => {
      onChatMessageChanged(queryClient, selectedSessionId);
    },
    onError: () => toast.error(t('chat.toast_send_failed')),
  });

  const sessions = Array.isArray(sessionsData) ? sessionsData : [];
  const messages = Array.isArray(messagesData) ? messagesData : [];
  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;

  // Filter + search the session list. Tabs are inclusive: "open" matches
  // unassigned active sessions, "assigned" any session that has an agent,
  // "mine" is "assigned to current user" (best-effort heuristic if the
  // backend exposes a `mine` flag), "closed" is the resolved bucket.
  const filteredSessions = useMemo(() => {
    let list = sessions;
    if (filterTab === 'open') {
      list = list.filter((s) => s.status === 'open');
    } else if (filterTab === 'assigned') {
      list = list.filter((s) => s.status === 'assigned');
    } else if (filterTab === 'mine') {
      list = list.filter(
        (s) =>
          (s as { assigned_to_me?: boolean }).assigned_to_me === true || s.status === 'assigned',
      );
    } else if (filterTab === 'closed') {
      list = list.filter((s) => s.status === 'closed');
    }
    const q = searchQuery.trim().toLowerCase();
    if (q.length > 0) {
      list = list.filter(
        (s) =>
          s.visitor_id.toLowerCase().includes(q) || s.agent?.full_name?.toLowerCase().includes(q),
      );
    }
    return list;
  }, [sessions, filterTab, searchQuery]);

  const tabCounts = useMemo(() => {
    return {
      open: sessions.filter((s) => s.status === 'open').length,
      assigned: sessions.filter((s) => s.status === 'assigned').length,
      mine: sessions.filter(
        (s) =>
          (s as { assigned_to_me?: boolean }).assigned_to_me === true || s.status === 'assigned',
      ).length,
      closed: sessions.filter((s) => s.status === 'closed').length,
    };
  }, [sessions]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  function handleSend() {
    const content = messageInput.trim();
    if (!content || selectedSessionId === null) return;
    setMessageInput('');
    sendMutation.mutate(content);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (isSessionsError) {
    return (
      <div>
        <PageHeader title={t('chat.agent_title')} description={t('chat.agent_description')} />
        <div className="rounded-2xl border border-red-100 bg-red-50/40 p-8 text-center dark:border-red-900/40 dark:bg-red-950/20">
          <p className="text-[14px] font-medium text-red-700 dark:text-red-400">
            {t('chat.load_error')}
          </p>
        </div>
      </div>
    );
  }

  const TABS: Array<{ key: FilterTab; label: string; count: number }> = [
    { key: 'open', label: 'Aktif', count: tabCounts.open },
    { key: 'assigned', label: 'Atanan', count: tabCounts.assigned },
    { key: 'mine', label: 'Bende', count: tabCounts.mine },
    { key: 'closed', label: 'Kapanan', count: tabCounts.closed },
  ];

  const isInboxEmpty = !isSessionsLoading && filteredSessions.length === 0;
  const isFullyEmpty = !isSessionsLoading && sessions.length === 0;

  return (
    <div className="flex h-full animate-fade-in flex-col">
      <PageHeader title={t('chat.agent_title')} description={t('chat.agent_description')}>
        <Button variant="secondary" onClick={() => navigate('/integrations')}>
          <Settings2 size={14} />
          Chat Widget Ayarları
        </Button>
      </PageHeader>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden lg:flex-row">
        {/* ─── Left panel — session inbox ─────────────────────────────── */}
        <aside className="flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) lg:w-[320px] lg:shrink-0 dark:border-slate-800 dark:bg-slate-900">
          {/* Search */}
          <div className="border-b border-slate-100 p-3 dark:border-slate-800">
            <div className="relative">
              <Search
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                aria-hidden
              />
              <input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Ziyaretçi veya temsilci ara"
                className="block h-9 w-full rounded-[10px] border border-slate-200 bg-white pl-8 pr-3 text-[13px] text-slate-900 placeholder:text-slate-400 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:placeholder:text-slate-500"
              />
            </div>
          </div>

          {/* Status filter tabs */}
          <div className="border-b border-slate-100 px-2 py-2 dark:border-slate-800">
            <div className="flex flex-wrap gap-1" role="tablist" aria-label="Sohbet filtresi">
              {TABS.map((tab) => {
                const isActive = filterTab === tab.key;
                return (
                  <button
                    key={tab.key}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    onClick={() => setFilterTab(tab.key)}
                    className={[
                      'inline-flex h-7 items-center gap-1.5 rounded-[8px] px-2.5 text-[12px] font-medium transition-colors',
                      'focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20',
                      isActive
                        ? 'bg-honeywell-red/10 text-honeywell-red'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200',
                    ].join(' ')}
                  >
                    {tab.label}
                    {tab.count > 0 && (
                      <span
                        className={[
                          'inline-flex h-4 min-w-[18px] items-center justify-center rounded-full px-1 text-[10px] font-bold tabular-nums',
                          isActive
                            ? 'bg-honeywell-red text-white'
                            : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
                        ].join(' ')}
                      >
                        {tab.count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Session list */}
          <div className="flex-1 overflow-y-auto">
            {isSessionsLoading ? (
              <div className="space-y-2 p-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-[68px] rounded-xl" />
                ))}
              </div>
            ) : isFullyEmpty ? (
              // Top-level empty inbox — copy reassures the agent that this
              // is the expected state and points at config + history paths.
              <div className="flex flex-col items-center px-6 py-12 text-center">
                <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-50 text-slate-400 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-500 dark:ring-slate-800">
                  <Inbox size={20} />
                </span>
                <p className="text-[13px] font-semibold text-slate-700 dark:text-slate-200">
                  Aktif sohbet yok
                </p>
                <p className="mt-1 max-w-[240px] text-[12px] text-slate-500 dark:text-slate-400">
                  Yeni ziyaretçi konuşmaları burada görünecek.
                </p>
                <div className="mt-4 flex flex-col gap-1.5 sm:flex-row">
                  <Button variant="tertiary" size="sm" onClick={() => navigate('/integrations')}>
                    <Settings2 size={13} />
                    Widget Ayarları
                  </Button>
                  <Button variant="tertiary" size="sm" onClick={() => setFilterTab('closed')}>
                    <History size={13} />
                    Geçmiş Konuşmalar
                  </Button>
                </div>
              </div>
            ) : isInboxEmpty ? (
              <p className="px-4 py-8 text-center text-[12px] text-slate-500 dark:text-slate-400">
                Bu filtreye uyan sohbet yok.
              </p>
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {filteredSessions.map((session) => {
                  const tone = STATUS_TONE[session.status] ?? 'default';
                  const unread = session.unread_count ?? 0;
                  const isActive = selectedSessionId === session.id;
                  return (
                    <li key={session.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedSessionId(session.id)}
                        className={[
                          'flex w-full flex-col gap-1.5 px-3 py-2.5 text-left transition-colors',
                          isActive
                            ? 'bg-honeywell-red/4'
                            : 'hover:bg-slate-50 dark:hover:bg-slate-800/40',
                        ].join(' ')}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span
                            className={[
                              'truncate text-[13px]',
                              unread > 0
                                ? 'font-semibold text-slate-900 dark:text-white'
                                : 'font-medium text-slate-700 dark:text-slate-200',
                            ].join(' ')}
                          >
                            {session.visitor_id}
                          </span>
                          <Badge variant={tone} size="sm" dot>
                            {translateChatSessionStatus(session.status, t)}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                          <span className="truncate">
                            {session.agent
                              ? `${t('chat.agent_prefix')} ${session.agent.full_name}`
                              : 'Atanmadı'}
                          </span>
                          {unread > 0 && (
                            <span className="ml-auto inline-flex h-4 min-w-[18px] items-center justify-center rounded-full bg-honeywell-red px-1 text-[10px] font-bold tabular-nums text-white">
                              {unread}
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
        </aside>

        {/* ─── Right panel — message thread ───────────────────────────── */}
        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          {selectedSession === null ? (
            <div className="flex flex-1 items-center justify-center px-6 py-12 text-center">
              <div>
                <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-50 text-slate-400 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-500 dark:ring-slate-800">
                  <MessageSquare size={20} />
                </span>
                <p className="text-[13px] font-medium text-slate-700 dark:text-slate-200">
                  {t('chat.select_session')}
                </p>
                <p className="mt-1 max-w-[300px] text-[12px] text-slate-500 dark:text-slate-400">
                  Sol panelden bir sohbet seçtiğinizde mesajlar ve müşteri bilgisi burada görünecek.
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* Thread header */}
              <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-3.5 dark:border-slate-800">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-honeywell-red/10 text-[12px] font-semibold text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                    {selectedSession.visitor_id.slice(0, 2).toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-[14px] font-semibold text-slate-900 dark:text-white">
                      {selectedSession.visitor_id}
                    </p>
                    <div className="mt-0.5 flex items-center gap-1.5">
                      <Badge
                        variant={STATUS_TONE[selectedSession.status] ?? 'default'}
                        size="sm"
                        dot
                      >
                        {translateChatSessionStatus(selectedSession.status, t)}
                      </Badge>
                      {selectedSession.agent && (
                        <span className="text-[11px] text-slate-500 dark:text-slate-400">
                          · {selectedSession.agent.full_name}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  {selectedSession.status !== 'closed' && (
                    <>
                      <Button
                        variant="tertiary"
                        size="sm"
                        onClick={() => assignMutation.mutate(selectedSession.id)}
                        loading={assignMutation.isPending}
                      >
                        <UserCheck size={13} />
                        {t('chat.assign_to_me')}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => closeMutation.mutate(selectedSession.id)}
                        loading={closeMutation.isPending}
                      >
                        <X size={13} className="text-red-500" />
                        {t('chat.close_session')}
                      </Button>
                    </>
                  )}
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 space-y-2 overflow-y-auto bg-slate-50/40 px-5 py-4 dark:bg-slate-900/40">
                {messages.length === 0 ? (
                  <p className="pt-8 text-center text-[12px] text-slate-400">
                    {t('chat.no_messages')}
                  </p>
                ) : (
                  messages.map((msg) => {
                    const isAgent = msg.sender_type === 'agent';
                    return (
                      <div
                        key={msg.id}
                        className={`flex ${isAgent ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={[
                            'max-w-[70%] rounded-2xl px-3 py-2 text-[13px] leading-5 shadow-(--shadow-xs)',
                            isAgent
                              ? 'rounded-br-md bg-honeywell-red text-white'
                              : 'rounded-bl-md border border-slate-200 bg-white text-slate-800 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100',
                          ].join(' ')}
                        >
                          {msg.content}
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              {selectedSession.status !== 'closed' && (
                <div className="flex items-center gap-2 border-t border-slate-100 px-4 py-3 dark:border-slate-800">
                  <input
                    type="text"
                    value={messageInput}
                    onChange={(e) => setMessageInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={t('chat.input_placeholder')}
                    disabled={sendMutation.isPending}
                    className="h-10 flex-1 rounded-[12px] border border-slate-200 bg-white px-3.5 text-[13px] text-slate-900 placeholder:text-slate-400 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:placeholder:text-slate-500"
                    aria-label={t('chat.aria_message_input')}
                  />
                  <button
                    type="button"
                    onClick={handleSend}
                    disabled={!messageInput.trim() || sendMutation.isPending}
                    className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] bg-honeywell-red text-white transition-colors hover:bg-honeywell-dark disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20"
                    aria-label={t('chat.aria_send')}
                  >
                    <Send size={16} />
                  </button>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
