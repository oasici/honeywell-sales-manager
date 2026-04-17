import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { MessageSquare, UserCheck, X, Send } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { chatApi } from '../../lib/api';
import type { ChatSession, ChatMessage } from '../../lib/types';

const SESSIONS_POLL_MS = 10_000;
const MESSAGES_POLL_MS = 5_000;

const STATUS_BADGES: Record<string, string> = {
  open: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  assigned: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  closed: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
};

const STATUS_LABELS: Record<string, string> = {
  open: 'Acik',
  assigned: 'Atandi',
  closed: 'Kapali',
};

export default function AgentChatPage() {
  const queryClient = useQueryClient();
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [messageInput, setMessageInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    data: sessionsData,
    isLoading: isSessionsLoading,
    isError: isSessionsError,
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
      toast.success('Oturum size atandi');
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
    },
    onError: () => toast.error('Atama başarısız'),
  });

  const closeMutation = useMutation({
    mutationFn: (id: number) => chatApi.closeSession(id),
    onSuccess: () => {
      toast.success('Oturum kapatildi');
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
    },
    onError: () => toast.error('Kapatma başarısız'),
  });

  const sendMutation = useMutation({
    mutationFn: (content: string) =>
      chatApi.sendMessage(selectedSessionId!, {
        content,
        sender_type: 'agent',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-messages-agent', selectedSessionId] });
    },
    onError: () => toast.error('Mesaj gonderilemedi'),
  });

  const sessions = Array.isArray(sessionsData) ? sessionsData : [];
  const messages = Array.isArray(messagesData) ? messagesData : [];
  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;

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
      <div className="space-y-6">
        <PageHeader title="Canlı Sohbet" description="Ziyaretci oturumlarini yonetin" />
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
          <div className="p-8 text-center">
            <p className="text-sm text-red-500">
              Veriler yuklenirken bir hata oluştu. Lütfen sayfayi yenileyin.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in h-full flex flex-col">
      <PageHeader title="Canlı Sohbet" description="Ziyaretci oturumlarini yonetin" />

      <div className="flex flex-1 gap-4 overflow-hidden min-h-0">
        {/* Session list */}
        <div className="w-72 shrink-0 flex flex-col gap-2 overflow-y-auto">
          {isSessionsLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-20 rounded-xl" />
            ))
          ) : sessions.length === 0 ? (
            <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6 text-center">
              <MessageSquare size={32} className="mx-auto mb-2 text-gray-300 dark:text-gray-600" />
              <p className="text-sm text-gray-500">Aktif oturum yok</p>
            </div>
          ) : (
            sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => setSelectedSessionId(session.id)}
                className={`text-left rounded-xl border p-3 transition-colors cursor-pointer ${
                  selectedSessionId === session.id
                    ? 'border-honeywell-red bg-honeywell-red/5 dark:bg-honeywell-red/10'
                    : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                    {session.visitor_id}
                  </span>
                  <span
                    className={`shrink-0 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_BADGES[session.status] ?? ''}`}
                  >
                    {STATUS_LABELS[session.status] ?? session.status}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
                  {session.agent && <span>Temsilci: {session.agent.full_name}</span>}
                  {(session.unread_count ?? 0) > 0 && (
                    <span className="ml-auto flex h-4 min-w-[16px] items-center justify-center rounded-full bg-honeywell-red px-1 text-[10px] font-bold text-white">
                      {session.unread_count}
                    </span>
                  )}
                </div>
              </button>
            ))
          )}
        </div>

        {/* Message thread */}
        <div className="flex-1 flex flex-col rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden min-h-0">
          {selectedSession === null ? (
            <div className="flex flex-1 items-center justify-center text-gray-400">
              <div className="text-center">
                <MessageSquare
                  size={40}
                  className="mx-auto mb-3 text-gray-300 dark:text-gray-600"
                />
                <p className="text-sm">Sol panelden bir oturum seçin</p>
              </div>
            </div>
          ) : (
            <>
              {/* Thread header */}
              <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">
                    {selectedSession.visitor_id}
                  </p>
                  <p className="text-xs text-gray-500">
                    Durum:{' '}
                    <span
                      className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${STATUS_BADGES[selectedSession.status] ?? ''}`}
                    >
                      {STATUS_LABELS[selectedSession.status] ?? selectedSession.status}
                    </span>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {selectedSession.status !== 'closed' && (
                    <>
                      <button
                        onClick={() => assignMutation.mutate(selectedSession.id)}
                        disabled={assignMutation.isPending}
                        className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-400 disabled:opacity-50 transition-colors cursor-pointer"
                      >
                        <UserCheck size={13} />
                        Bana Ata
                      </button>
                      <button
                        onClick={() => closeMutation.mutate(selectedSession.id)}
                        disabled={closeMutation.isPending}
                        className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-red-50 text-red-700 hover:bg-red-100 dark:bg-red-900/30 dark:text-red-400 disabled:opacity-50 transition-colors cursor-pointer"
                      >
                        <X size={13} />
                        Kapat
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
                {messages.length === 0 ? (
                  <p className="text-center text-xs text-gray-400 pt-8">Henüz mesaj yok</p>
                ) : (
                  messages.map((msg) => {
                    const isAgent = msg.sender_type === 'agent';
                    return (
                      <div
                        key={msg.id}
                        className={`flex ${isAgent ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={`max-w-[70%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                            isAgent
                              ? 'bg-honeywell-red text-white rounded-br-sm'
                              : 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 rounded-bl-sm'
                          }`}
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
                <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-3 flex items-center gap-2">
                  <input
                    type="text"
                    value={messageInput}
                    onChange={(e) => setMessageInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Yanit yazin…"
                    disabled={sendMutation.isPending}
                    className="flex-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-honeywell-red disabled:opacity-50"
                    aria-label="Mesaj yaz"
                  />
                  <button
                    onClick={handleSend}
                    disabled={!messageInput.trim() || sendMutation.isPending}
                    className="rounded-lg p-2 bg-honeywell-red text-white hover:bg-honeywell-red/90 disabled:opacity-40 transition-colors cursor-pointer"
                    aria-label="Gönder"
                  >
                    <Send size={16} />
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
