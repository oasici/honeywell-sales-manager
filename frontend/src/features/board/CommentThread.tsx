import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Send, Reply, Trash2 } from 'lucide-react';
import { commentsApi, usersApi } from '../../lib/api';
import { useAuthStore } from '../../stores/authStore';
import { Card } from '../../components/ui/Card';
import { currentLocale, formatRelativeTime } from '../../lib/formatters';
import type { Comment, User } from '../../lib/types';

const REFETCH_INTERVAL_MS = 30_000;

// Round-10 R10-FE-8 — replaced the Turkish-only `formatTimestamp` with
// the locale-aware helper. Falls back to a localised date string once
// the entry crosses the one-week threshold.
function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  const diffDays = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (diffDays >= 7) return date.toLocaleDateString(currentLocale());
  return formatRelativeTime(iso);
}

function getAvatarColor(name: string): string {
  const colors = [
    'bg-blue-500',
    'bg-green-500',
    'bg-amber-500',
    'bg-purple-500',
    'bg-pink-500',
    'bg-indigo-500',
    'bg-teal-500',
    'bg-red-500',
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

function highlightMentions(text: string): React.ReactNode[] {
  const parts = text.split(/(@\w+)/g);
  return parts.map((part, i) => {
    if (part.startsWith('@')) {
      return (
        <span key={i} className="font-semibold text-blue-600 dark:text-blue-400">
          {part}
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

interface CommentItemProps {
  comment: Comment;
  currentUserId: number;
  onReply: (commentId: number) => void;
  onDelete: (commentId: number) => void;
  isReplyTarget: boolean;
  isNested?: boolean;
}

function CommentItem({
  comment,
  currentUserId,
  onReply,
  onDelete,
  isReplyTarget,
  isNested = false,
}: CommentItemProps) {
  const userName = comment.user?.full_name || 'Kullanıcı';
  const initial = userName.charAt(0).toUpperCase();
  const avatarColor = getAvatarColor(userName);

  return (
    <div className={isNested ? 'ml-8 border-l-2 border-slate-200 pl-4 dark:border-slate-800' : ''}>
      <div
        className={`flex gap-3 py-3 ${isReplyTarget ? 'bg-blue-50 dark:bg-blue-900/10 -mx-2 px-2 rounded-lg' : ''}`}
      >
        <div
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${avatarColor}`}
        >
          {initial}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-900 dark:text-white">{userName}</span>
            <span className="text-[10px] text-slate-400">
              {comment.created_at ? formatTimestamp(comment.created_at) : ''}
            </span>
          </div>
          <p className="mt-0.5 text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
            {highlightMentions(comment.body)}
          </p>
          <div className="mt-1 flex items-center gap-3">
            <button
              type="button"
              onClick={() => onReply(comment.id)}
              className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-blue-600 transition-colors"
            >
              <Reply size={12} />
              Yanit
            </button>
            {comment.user_id === currentUserId && (
              <button
                type="button"
                onClick={() => onDelete(comment.id)}
                className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-red-600 transition-colors"
              >
                <Trash2 size={12} />
                Sil
              </button>
            )}
          </div>
        </div>
      </div>
      {comment.replies && comment.replies.length > 0 && (
        <div>
          {comment.replies.map((reply) => (
            <CommentItem
              key={reply.id}
              comment={reply}
              currentUserId={currentUserId}
              onReply={onReply}
              onDelete={onDelete}
              isReplyTarget={false}
              isNested
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface MentionDropdownProps {
  users: User[];
  filter: string;
  onSelect: (name: string) => void;
}

function MentionDropdown({ users, filter, onSelect }: MentionDropdownProps) {
  const filtered = users.filter((u) => u.full_name.toLowerCase().includes(filter.toLowerCase()));

  if (filtered.length === 0) return null;

  return (
    <div className="absolute bottom-full left-0 mb-1 w-56 rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-800 dark:bg-slate-800 z-50 max-h-40 overflow-y-auto">
      {filtered.map((u) => (
        <button
          key={u.id}
          type="button"
          onClick={() => onSelect(u.full_name.split(' ')[0])}
          className="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          <div
            className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold text-white ${getAvatarColor(u.full_name)}`}
          >
            {u.full_name.charAt(0).toUpperCase()}
          </div>
          {u.full_name}
        </button>
      ))}
    </div>
  );
}

interface CommentThreadProps {
  entityType: string;
  entityId: number;
}

export default function CommentThread({ entityType, entityId }: CommentThreadProps) {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const currentUserId = currentUser?.id ?? 0;

  const [newComment, setNewComment] = useState('');
  const [replyToId, setReplyToId] = useState<number | null>(null);
  const [isMentioning, setIsMentioning] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // R6-PAGE-1 — backend canonicalized comments to {items, total, …};
  // accept both shapes during the transition window.
  const { data: commentsData } = useQuery<{ items?: Comment[]; comments?: Comment[] }>({
    queryKey: ['comments', entityType, entityId],
    queryFn: () => commentsApi.list({ entity_type: entityType, entity_id: entityId }),
    refetchInterval: REFETCH_INTERVAL_MS,
  });

  const { data: usersData } = useQuery<{ users: User[] }>({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    staleTime: 300_000,
  });

  const users =
    usersData?.users ?? (Array.isArray(usersData) ? (usersData as unknown as User[]) : []);
  const comments = commentsData?.items ?? commentsData?.comments ?? [];

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => commentsApi.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', entityType, entityId] });
      setNewComment('');
      setReplyToId(null);
    },
    onError: () => toast.error('Yorum gonderilemedi'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => commentsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', entityType, entityId] });
      toast.success('Yorum silindi');
    },
    onError: () => toast.error('Yorum silinemedi'),
  });

  const handleSubmit = () => {
    const trimmed = newComment.trim();
    if (!trimmed) return;

    createMutation.mutate({
      entity_type: entityType,
      entity_id: entityId,
      body: trimmed,
      parent_id: replyToId,
    });
  };

  const handleReply = (commentId: number) => {
    setReplyToId(commentId);
    inputRef.current?.focus();
  };

  const handleInputChange = (value: string) => {
    setNewComment(value);

    // Detect @mention trigger
    const lastAt = value.lastIndexOf('@');
    if (lastAt !== -1) {
      const afterAt = value.slice(lastAt + 1);
      const hasSpace = afterAt.includes(' ');
      if (!hasSpace && afterAt.length <= 20) {
        setIsMentioning(true);
        setMentionFilter(afterAt);
        return;
      }
    }
    setIsMentioning(false);
    setMentionFilter('');
  };

  const handleMentionSelect = (name: string) => {
    const lastAt = newComment.lastIndexOf('@');
    const before = newComment.slice(0, lastAt);
    setNewComment(`${before}@${name} `);
    setIsMentioning(false);
    setMentionFilter('');
    inputRef.current?.focus();
  };

  // Close mention dropdown on click outside
  useEffect(() => {
    const handleClick = () => setIsMentioning(false);
    if (isMentioning) {
      document.addEventListener('click', handleClick);
      return () => document.removeEventListener('click', handleClick);
    }
  }, [isMentioning]);

  return (
    <Card title="Yorumlar">
      <div className="space-y-0 divide-y divide-slate-100 dark:divide-slate-800">
        {comments.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">Henüz yorum yok</p>
        ) : (
          comments.map((comment) => (
            <CommentItem
              key={comment.id}
              comment={comment}
              currentUserId={currentUserId}
              onReply={handleReply}
              onDelete={(id) => deleteMutation.mutate(id)}
              isReplyTarget={comment.id === replyToId}
            />
          ))
        )}
      </div>

      {/* New comment input */}
      <div className="mt-4 border-t border-slate-100 pt-4 dark:border-slate-800">
        {replyToId && (
          <div className="mb-2 flex items-center gap-2">
            <span className="text-xs text-slate-500">Yanit yaziyorsunuz</span>
            <button
              type="button"
              onClick={() => setReplyToId(null)}
              className="text-xs text-red-500 hover:underline"
            >
              İptal
            </button>
          </div>
        )}
        <div className="relative flex gap-2">
          {isMentioning && (
            <MentionDropdown users={users} filter={mentionFilter} onSelect={handleMentionSelect} />
          )}
          <textarea
            ref={inputRef}
            value={newComment}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
              }
            }}
            placeholder="Yorum yazin... (@ile etiketleyin)"
            rows={2}
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm resize-none focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-red dark:border-slate-800 dark:bg-slate-800 dark:text-white"
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!newComment.trim() || createMutation.isPending}
            className="flex h-10 w-10 shrink-0 items-center justify-center self-end rounded-lg bg-honeywell-red text-white transition-colors hover:bg-red-700 disabled:opacity-50"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </Card>
  );
}
