import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { MessageSquare, X, Send } from 'lucide-react';
import { toast } from 'sonner';
import { chatApi } from '../../lib/api';
import type { ChatMessage, ChatSession } from '../../lib/types';

const VISITOR_ID_KEY = 'chat-visitor-id';
const SESSION_ID_KEY = 'chat-session-id';
const POLL_INTERVAL_MS = 5_000;

function getOrCreateVisitorId(): string {
  const stored = localStorage.getItem(VISITOR_ID_KEY);
  if (stored) return stored;
  const generated = `visitor-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  localStorage.setItem(VISITOR_ID_KEY, generated);
  return generated;
}

function getStoredSessionId(): number | null {
  const stored = localStorage.getItem(SESSION_ID_KEY);
  return stored ? Number(stored) : null;
}

function storeSessionId(id: number) {
  localStorage.setItem(SESSION_ID_KEY, String(id));
}

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
      toast.error('Baglanti kurulamadi');
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
      queryClient.invalidateQueries({ queryKey: ['chat-messages', sessionId] });
    },
    onError: () => toast.error('Mesaj gonderilemedi'),
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

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {/* Chat panel */}
      {isOpen && (
        <div
          className="w-80 h-96 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 flex flex-col overflow-hidden animate-slide-up"
          role="dialog"
          aria-label="Canli Sohbet"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-honeywell-red text-white">
            <div className="flex items-center gap-2">
              <MessageSquare size={16} />
              <span className="text-sm font-semibold">Canli Destek</span>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="rounded p-1 hover:bg-white/20 transition-colors cursor-pointer"
              aria-label="Sohbeti kapat"
            >
              <X size={16} />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
            {createSessionMutation.isPending && (
              <p className="text-center text-xs text-gray-400">Baglaniyor…</p>
            )}
            {hasSessionError && !createSessionMutation.isPending && (
              <div className="flex flex-col items-center gap-2 pt-8">
                <p className="text-center text-xs text-red-500">Hata olustu, tekrar deneyin</p>
                <button
                  type="button"
                  onClick={() => {
                    setHasSessionError(false);
                    createSessionMutation.mutate();
                  }}
                  className="rounded-lg px-3 py-1.5 text-xs font-medium bg-honeywell-red text-white hover:bg-honeywell-red/90 transition-colors"
                >
                  Tekrar Dene
                </button>
              </div>
            )}
            {messages.length === 0 && !createSessionMutation.isPending && !hasSessionError && (
              <p className="text-center text-xs text-gray-400 pt-8">Nasil yardimci olabiliriz?</p>
            )}
            {messages.map((msg) => {
              const isVisitor = msg.sender_type === 'visitor';
              return (
                <div key={msg.id} className={`flex ${isVisitor ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[75%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                      isVisitor
                        ? 'bg-honeywell-red text-white rounded-br-sm'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 rounded-bl-sm'
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-gray-200 dark:border-gray-700 px-3 py-2 flex items-center gap-2">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Mesajiniz…"
              disabled={!sessionId || sendMutation.isPending}
              className="flex-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-1.5 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-honeywell-red disabled:opacity-50"
              aria-label="Mesaj yaz"
            />
            <button
              onClick={handleSend}
              disabled={!inputText.trim() || !sessionId || sendMutation.isPending}
              className="rounded-lg p-1.5 bg-honeywell-red text-white hover:bg-honeywell-red/90 disabled:opacity-40 transition-colors cursor-pointer"
              aria-label="Gonder"
            >
              <Send size={15} />
            </button>
          </div>
        </div>
      )}

      {/* Toggle button */}
      <button
        onClick={() => setIsOpen((v) => !v)}
        className="flex h-13 w-13 items-center justify-center rounded-full bg-honeywell-red text-white shadow-lg hover:bg-honeywell-red/90 transition-all active:scale-95 cursor-pointer"
        aria-label={isOpen ? 'Sohbeti kapat' : 'Sohbeti ac'}
        style={{ height: 52, width: 52 }}
      >
        {isOpen ? <X size={22} /> : <MessageSquare size={22} />}
      </button>
    </div>
  );
}
