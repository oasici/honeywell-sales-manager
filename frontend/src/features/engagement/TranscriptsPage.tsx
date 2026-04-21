import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { FileText, Search, Sparkles, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { DataTable } from '../../components/ui/DataTable';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { Badge } from '../../components/ui/Badge';
import { engagementApi, aiApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import { useT } from '../../hooks/useT';

import type { Transcript, KeywordPack, RevenueSignalItem } from '../../lib/types';

const PAGE_SIZE = 20;

const CATEGORY_COLORS: Record<string, string> = {
  pricing: 'bg-blue-100 text-blue-800',
  competitor: 'bg-red-100 text-red-800',
  objection: 'bg-orange-100 text-orange-800',
  positive: 'bg-green-100 text-green-800',
  technical: 'bg-purple-100 text-purple-800',
};

const DEFAULT_HIGHLIGHT_CLASS = 'bg-yellow-100 text-yellow-800';

function highlightKeywords(text: string, packs: KeywordPack[]): React.ReactNode {
  const activePacks = packs.filter((p) => p.is_active);
  if (activePacks.length === 0) return text;

  const keywordMap = new Map<string, string>();
  for (const pack of activePacks) {
    const colorClass = CATEGORY_COLORS[pack.category] ?? DEFAULT_HIGHLIGHT_CLASS;
    for (const keyword of pack.keywords) {
      keywordMap.set(keyword.toLowerCase(), colorClass);
    }
  }

  const sortedKeywords = Array.from(keywordMap.keys()).sort((a, b) => b.length - a.length);
  if (sortedKeywords.length === 0) return text;

  const escaped = sortedKeywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const pattern = new RegExp(`(${escaped.join('|')})`, 'gi');
  const parts = text.split(pattern);

  return parts.map((part, idx) => {
    const colorClass = keywordMap.get(part.toLowerCase());
    if (colorClass) {
      return (
        <mark key={idx} className={`rounded px-0.5 font-medium ${colorClass}`}>
          {part}
        </mark>
      );
    }
    return part;
  });
}

function TranscriptSignals({ opportunityId }: { opportunityId: number }) {
  const t = useT();
  const signalsQuery = useQuery<{ signals: RevenueSignalItem[] }>({
    queryKey: ['ai-signals', opportunityId],
    queryFn: () => aiApi.getSignals(opportunityId),
  });

  const signals = signalsQuery.data?.signals ?? [];
  if (signalsQuery.isLoading) {
    return <span className="text-xs text-gray-400">{t('transcripts.signals_loading')}</span>;
  }
  if (signals.length === 0) return null;

  const severityVariant: Record<string, 'danger' | 'warning' | 'info' | 'default'> = {
    critical: 'danger',
    high: 'danger',
    medium: 'warning',
    low: 'info',
  };

  return (
    <div className="mt-3">
      <p className="mb-1 text-xs font-semibold text-gray-600">
        {signals.length} sinyal tespit edildi
      </p>
      <div className="flex flex-wrap gap-1">
        {signals.map((s) => (
          <Badge key={s.id} variant={severityVariant[s.severity] ?? 'default'} size="sm">
            {s.signal_type} ({s.severity})
          </Badge>
        ))}
      </div>
    </div>
  );
}

export default function TranscriptsPage() {
  const t = useT();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [isSearchMode, setIsSearchMode] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [expandedSummaries, setExpandedSummaries] = useState<Record<number, string>>({});
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const [form, setForm] = useState({
    title: '',
    content: '',
    source: '',
    opportunity_id: '',
    customer_id: '',
    duration_minutes: '',
  });

  const listQuery = useQuery<{
    items: Transcript[];
    total: number;
    page: number;
    page_size: number;
  }>({
    queryKey: ['transcripts', { page, page_size: PAGE_SIZE }],
    queryFn: () => engagementApi.listTranscripts({ page, page_size: PAGE_SIZE }),
    enabled: !isSearchMode,
  });

  const searchQuery = useQuery<{ query: string; total: number; items: Transcript[] }>({
    queryKey: ['transcripts-search', { q: search, page, page_size: PAGE_SIZE }],
    queryFn: () => engagementApi.searchTranscripts({ q: search, page, page_size: PAGE_SIZE }),
    enabled: isSearchMode && search.length > 0,
  });

  const keywordPacksQuery = useQuery<{ packs: KeywordPack[] }>({
    queryKey: ['keyword-packs'],
    queryFn: () => engagementApi.listKeywordPacks(),
  });

  const keywordPacks = keywordPacksQuery.data?.packs ?? [];

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => engagementApi.createTranscript(payload),
    onSuccess: () => {
      toast.success(t('transcripts.toast_created'));
      queryClient.invalidateQueries({ queryKey: ['transcripts'] });
      setIsCreateOpen(false);
      resetForm();
    },
    onError: () => toast.error(t('transcripts.toast_create_fail')),
  });

  const summarizeMutation = useMutation({
    mutationFn: (id: number) => engagementApi.summarizeTranscript(id),
    onSuccess: (res: { summary: string; sources: string[] }, id: number) => {
      toast.success(t('transcripts.toast_summary_ok'));
      setExpandedSummaries((prev) => ({ ...prev, [id]: res.summary }));
    },
    onError: () => toast.error(t('transcripts.toast_summary_fail')),
  });

  function resetForm() {
    setForm({
      title: '',
      content: '',
      source: '',
      opportunity_id: '',
      customer_id: '',
      duration_minutes: '',
    });
  }

  function handleCreate() {
    if (!form.title.trim() || !form.content.trim()) {
      toast.error(t('transcripts.err_title_body'));
      return;
    }
    createMutation.mutate({
      title: form.title,
      content: form.content,
      ...(form.source && { source: form.source }),
      ...(form.opportunity_id && { opportunity_id: Number(form.opportunity_id) }),
      ...(form.customer_id && { customer_id: Number(form.customer_id) }),
      ...(form.duration_minutes && { duration_minutes: Number(form.duration_minutes) }),
    });
  }

  function handleSearchToggle() {
    if (isSearchMode) {
      setIsSearchMode(false);
      setSearch('');
      setPage(1);
    } else {
      setIsSearchMode(true);
      setPage(1);
    }
  }

  const activeData = isSearchMode ? searchQuery.data : listQuery.data;
  const isLoading = isSearchMode ? searchQuery.isLoading : listQuery.isLoading;
  const items = activeData?.items ?? [];
  const totalPages = activeData ? Math.ceil(activeData.total / PAGE_SIZE) : 1;

  function handleRowClick(transcript: Transcript) {
    setExpandedId((prev) => (prev === transcript.id ? null : transcript.id));
  }

  const columns = [
    {
      key: 'expand',
      header: '',
      render: (row: Transcript) => (
        <span className="text-gray-400">
          {expandedId === row.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </span>
      ),
    },
    {
      key: 'title',
      header: t('transcripts.col_title'),
      render: (row: Transcript) => (
        <span className="text-sm font-medium text-gray-900">{row.title}</span>
      ),
    },
    {
      key: 'source',
      header: t('transcripts.col_source'),
      render: (row: Transcript) => (
        <span className="text-sm text-gray-600">{row.source || '-'}</span>
      ),
    },
    {
      key: 'duration_minutes',
      header: t('transcripts.col_duration'),
      render: (row: Transcript) => <span className="text-sm">{row.duration_minutes ?? '-'}</span>,
    },
    {
      key: 'keywords_found',
      header: t('transcripts.col_keywords'),
      render: (row: Transcript) => <span className="text-sm">{row.keywords_found}</span>,
    },
    {
      key: 'created_at',
      header: t('transcripts.col_date'),
      sortable: true,
      render: (row: Transcript) => (
        <span className="whitespace-nowrap text-sm">{formatDateTime(row.created_at)}</span>
      ),
    },
    {
      key: 'actions',
      header: t('transcripts.col_actions'),
      render: (row: Transcript) => (
        <Button
          variant="secondary"
          size="sm"
          loading={summarizeMutation.isPending && summarizeMutation.variables === row.id}
          onClick={(e) => {
            e.stopPropagation();
            summarizeMutation.mutate(row.id);
          }}
        >
          <Sparkles size={14} className="mr-1" />
          {t('transcripts.btn_summarize')}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title={t('transcripts.title')} description={t('transcripts.description')}>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={handleSearchToggle}>
            <Search size={16} className="mr-1" />
            {isSearchMode ? t('transcripts.btn_clear_search') : t('transcripts.btn_search')}
          </Button>
          <Button onClick={() => setIsCreateOpen(true)}>{t('transcripts.btn_new')}</Button>
        </div>
      </PageHeader>

      {isSearchMode && (
        <div className="mb-4 w-80">
          <Input
            placeholder={t('transcripts.search_ph')}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
      )}

      {isLoading ? (
        <Skeleton variant="table" />
      ) : items.length === 0 ? (
        <EmptyState
          title={t('transcripts.empty')}
          description={t('transcripts.empty')}
          icon={<FileText size={40} />}
          action={
            <Button onClick={() => setIsCreateOpen(true)}>{t('transcripts.first_add')}</Button>
          }
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            data={items}
            loading={isLoading}
            emptyMessage={t('transcripts.empty')}
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            onRowClick={handleRowClick}
          />

          {expandedId !== null &&
            (() => {
              const transcript = items.find((t) => t.id === expandedId);
              if (!transcript) return null;
              const summary = expandedSummaries[transcript.id] ?? transcript.summary;
              return (
                <div className="mt-3 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-gray-900">{transcript.title}</h3>
                    <div className="flex items-center gap-2">
                      {transcript.opportunity_id && (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
                          onClick={() => navigate(`/opportunities/${transcript.opportunity_id}`)}
                        >
                          <ExternalLink size={12} />
                          {t('transcripts.opp_ref').replace(
                            '{id}',
                            String(transcript.opportunity_id),
                          )}
                        </button>
                      )}
                      {transcript.customer_id && (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 rounded-md bg-green-50 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-100"
                          onClick={() => navigate(`/customers/${transcript.customer_id}`)}
                        >
                          <ExternalLink size={12} />
                          {t('transcripts.cust_ref').replace(
                            '{id}',
                            String(transcript.customer_id),
                          )}
                        </button>
                      )}
                    </div>
                  </div>

                  {summary && (
                    <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50/60 p-3">
                      <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-blue-700">
                        {t('transcripts.summary')}
                      </div>
                      <p className="text-sm leading-relaxed text-gray-700">{summary}</p>
                    </div>
                  )}

                  <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
                      {t('transcripts.content')}
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
                      {transcript.content
                        ? highlightKeywords(transcript.content, keywordPacks)
                        : transcript.summary || t('common.error')}
                    </p>
                  </div>

                  {transcript.opportunity_id && (
                    <TranscriptSignals opportunityId={transcript.opportunity_id} />
                  )}
                </div>
              );
            })()}
        </>
      )}

      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title={t('transcripts.modal_new_title')}
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              {t('transcripts.col_title')}
            </label>
            <Input
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder={t('transcripts.ph_title')}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              {t('transcripts.lbl_content')}
            </label>
            <textarea
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              rows={6}
              value={form.content}
              onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
              placeholder={t('transcripts.content')}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                {t('transcripts.col_source')}
              </label>
              <Input
                value={form.source}
                onChange={(e) => setForm((f) => ({ ...f, source: e.target.value }))}
                placeholder={t('transcripts.ph_channel')}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                {t('transcripts.lbl_duration')}
              </label>
              <Input
                type="number"
                value={form.duration_minutes}
                onChange={(e) => setForm((f) => ({ ...f, duration_minutes: e.target.value }))}
                placeholder="30"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                {t('transcripts.lbl_opp_id')}
              </label>
              <Input
                type="number"
                value={form.opportunity_id}
                onChange={(e) => setForm((f) => ({ ...f, opportunity_id: e.target.value }))}
                placeholder="Opsiyonel"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                {t('transcripts.lbl_cust_id')}
              </label>
              <Input
                type="number"
                value={form.customer_id}
                onChange={(e) => setForm((f) => ({ ...f, customer_id: e.target.value }))}
                placeholder="Opsiyonel"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button loading={createMutation.isPending} onClick={handleCreate}>
              {t('common.create')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
