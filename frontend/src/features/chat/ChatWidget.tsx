import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { MessageSquare, X, Send } from 'lucide-react';
import { toast } from 'sonner';
import { chatApi } from '../../lib/api';
import { onChatWidgetMessageChanged } from '../../lib/cacheInvalidation';
import type { ChatMessage, ChatSession } from '../../lib/types';

const VISITOR_ID_KEY = 'chat-visitor-id';
const SESSION_ID_KEY = 'chat-session-id';
const POLL_INTERVAL_MS = 5_000;

// Round-12 R12-FE-1 — SSR guard. ChatWidget is mounted in the app
// shell, so any module-load or initial-render read of `localStorage`
// crashes on Node-side renders. Each helper is a safe no-op (or
// fallback) when no DOM is available; the real value is hydrated
// client-side after mount.
const HAS_STORAGE = typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';

function getOrCreateVisitorId(): string {
  if (!HAS_STORAGE) {
    // SSR placeholder — replaced client-side after hydration.
    return 'visitor-ssr';
  }
  const stored = localStorage.getItem(VISITOR_ID_KEY);
  if (stored) return stored;
  const generated = `visitor-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  localStorage.setItem(VISITOR_ID_KEY, generated);
  return generated;
}

function getStoredSessionId(): number | null {
  if (!HAS_STORAGE) return null;
  const stored = localStorage.getItem(SESSION_ID_KEY);
  return stored ? Number(stored) : null;
}

function storeSessionId(id: number) {
  if (!HAS_STORAGE) return;
  localStorage.setItem(SESSION_ID_KEY, String(id));
}

/**
 * ChatWidget — bottom-right floating chat surface.
 *
 * Visual:
 *   - Trigger: 52×52 brand-red circle with shadow-xl + brand-tinted ring.
 *   - Panel: 360×440 with 16px radius and slate-200 ring; header on
 *     slate-950 with brand-red status dot to read as "live".
 *   - Bubbles: visitor = brand red, agent = slate-100 (light) / slate-800
 *     (dark). Tail corner is intentionally squared so the orientation
 *     remains readable when bubbles stack.
 */
export function ChatWidget() {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(getStoredSessionId);
  const [inputText, setInputText] = useState('');
  const [hasSessionError, setHasSessionError] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const visitorId = useRef(getOrCreateVisitorId());

  const createSessionMutation = useMutation({
    mutationFn: () => chatApi.createSession({ visitor_id: visitorId.current }),
    onSuccess: (session: ChatSession) => {
      storeSessionId(session.id);
      setSessionId(session.id);
      setHasSessionError(false);
    },
    onError: () => {
      setHasSessionError(true);
      toast.error('Bağlantı kurulamadı');
    },
  });

  useEffect(() => {
    if (isOpen && sessionId === null && !createSessionMutation.isPending) {
      createSessionMutation.mutate();
    }
  }, [isOpen, sessionId, createSessionMutation]);

  const { data: messagesData } = useQuery<ChatMessage[]>({
    queryKey: ['chat-messages', sessionId],
    queryFn: () => chatApi.getMessages(sessionId!),
    enabled: isOpen && sessionId !== null,
    refetchInterval: POLL_INTERVAL_MS,
  });

  const sendMutation = useMutation({
    mutationFn: (content: string) =>
      chatApi.sendMessage(sessionId!, {
        content,
        sender_type: 'visitor',
        sender_id: visitorId.current,
      }),
    onSuccess: () => {
      onChatWidgetMessageChanged(queryClient, sessionId);
    },
    onError: () => toast.error('Mesaj gönderilemedi'),
  });

  const messages = Array.isArray(messagesData) ? messagesData : [];

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, isOpen]);

  function handleSend() {
    const content = inputText.trim();
    if (!content || !sessionId) return;
    setInputText('');
    sendMutation.mutate(content);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const isLoadingSession = createSessionMutation.isPending;
  const isEmpty = messages.length === 0 && !isLoadingSession && !hasSessionError;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {/* Chat panel */}
      {isOpen && (
        <div
          className="flex h-[440px] w-[360px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xl) dark:border-slate-800 dark:bg-slate-900 animate-slide-up"
          role="dialog"
          aria-label="Canlı Sohbet"
        >
          {/* Header — slate-950 surface so the white-on-dark contrast reads
              as "agent space" rather than alert. The status dot pulses
              subtly via Tailwind's animate-pulse to suggest live presence. */}
          <div className="flex items-center justify-between border-b border-white/8 bg-slate-950 px-4 py-3 text-white">
            <div className="flex items-center gap-2.5">
              <span className="relative inline-flex h-7 w-7 items-center justify-center rounded-[10px] bg-honeywell-red/15 ring-1 ring-inset ring-honeywell-red/40">
                <MessageSquare size={14} className="text-white" />
              </span>
              <div className="leading-tight">
                <p className="text-[13px] font-semibold">Canlı Destek</p>
                <p className="flex items-center gap-1.5 text-[11px] text-slate-400">
                  <span className="relative inline-flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  </span>
                  Çevrimiçi
                </p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] text-slate-300 transition-colors hover:bg-white/10 hover:text-white focus:outline-none focus:ring-[3px] focus:ring-white/20"
              aria-label="Sohbeti kapat"
            >
              <X size={16} />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 space-y-2 overflow-y-auto bg-slate-50/40 px-3 py-3 dark:bg-slate-900/40">
            {isLoadingSession && (
              <p className="pt-8 text-center text-[12px] text-slate-400">Bağlanıyor…</p>
            )}
            {hasSessionError && !isLoadingSession && (
              <div className="flex flex-col items-center gap-3 pt-10">
                <p className="text-center text-[12px] text-red-500">Bağlantı kurulamadı</p>
                <button
                  type="button"
                  onClick={() => {
                    setHasSessionError(false);
                    createSessionMutation.mutate();
                  }}
                  className="inline-flex h-8 items-center rounded-[10px] bg-honeywell-red px-3 text-[12px] font-semibold text-white transition-colors hover:bg-honeywell-dark focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20"
                >
                  Tekrar Dene
                </button>
              </div>
            )}
            {isEmpty && (
              <div className="flex flex-col items-center gap-2 pt-10 text-center">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] bg-slate-100 text-slate-400 ring-1 ring-inset ring-slate-200 dark:bg-slate-800 dark:text-slate-500 dark:ring-slate-700">
                  <MessageSquare size={18} />
                </span>
                <p className="text-[13px] font-medium text-slate-700 dark:text-slate-200">
                  Nasıl yardımcı olabiliriz?
                </p>
                <p className="max-w-[240px] text-[12px] text-slate-500 dark:text-slate-400">
                  Sorunuzu yazın — ekibimiz birkaç dakika içinde dönüş yapar.
                </p>
              </div>
            )}
            {messages.map((msg) => {
              const isVisitor = msg.sender_type === 'visitor';
              return (
                <div key={msg.id} className={`flex ${isVisitor ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={[
                      'max-w-[78%] rounded-2xl px-3 py-2 text-[13px] leading-5 shadow-(--shadow-xs)',
                      isVisitor
                        ? 'rounded-br-md bg-honeywell-red text-white'
                        : 'rounded-bl-md border border-slate-200 bg-white text-slate-800 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100',
                    ].join(' ')}
                  >
                    {msg.content}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Input bar */}
          <div className="flex items-center gap-2 border-t border-slate-100 bg-white px-3 py-2.5 dark:border-slate-800 dark:bg-slate-900">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Mesajınız…"
              disabled={!sessionId || sendMutation.isPending}
              className="h-9 flex-1 rounded-[10px] border border-slate-200 bg-white px-3 text-[13px] text-slate-900 placeholder:text-slate-400 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:placeholder:text-slate-500"
              aria-label="Mesaj yaz"
            />
            <button
              onClick={handleSend}
              disabled={!inputText.trim() || !sessionId || sendMutation.isPending}
              className="inline-flex h-9 w-9 items-center justify-center rounded-[10px] bg-honeywell-red text-white transition-colors hover:bg-honeywell-dark disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20"
              aria-label="Gönder"
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      )}

      {/* Trigger button */}
      <button
        onClick={() => setIsOpen((v) => !v)}
        className="flex h-13 w-13 items-center justify-center rounded-full bg-honeywell-red text-white shadow-(--shadow-xl) ring-1 ring-honeywell-red/40 transition-all hover:bg-honeywell-dark active:scale-[0.96] focus:outline-none focus:ring-[5px] focus:ring-honeywell-red/25"
        aria-label={isOpen ? 'Sohbeti kapat' : 'Sohbeti aç'}
        style={{ height: 52, width: 52 }}
      >
        {isOpen ? <X size={20} /> : <MessageSquare size={20} />}
      </button>
    </div>
  );
}
