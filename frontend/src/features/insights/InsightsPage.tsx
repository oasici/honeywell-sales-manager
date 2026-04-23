import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertTriangle, Search, TrendingUp } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Skeleton } from '../../components/ui/Skeleton';
import { insightsApi, usersApi } from '../../lib/api';
import type {
  ConversationInsightsResponse,
  ConversationSearchResponse,
  SignalsDashboardResponse,
  SignalsTrendResponse,
} from '../../lib/types';
import { useT } from '../../hooks/useT';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';

const STAGE_OPTIONS = [
  '',
  'prospecting',
  'qualification',
  'proposal',
  'negotiation',
  'closed_won',
  'closed_lost',
];

const SIGNAL_FILTER_OPTIONS = [
  '',
  'pricing_concern',
  'competitor',
  'objection',
  'no_touch',
  'discount_risk',
];

export default function InsightsPage() {
  const t = useT();
  const navigate = useNavigate();
  const isManager = useAuthStore((s) => s.user?.role === 'sales_manager');
  const [windowDays, setWindowDays] = useState(30);

  const [searchQ, setSearchQ] = useState('');
  const [searchStage, setSearchStage] = useState('');
  const [searchSignal, setSearchSignal] = useState('');
  const [searchOwner, setSearchOwner] = useState('');
  const [searchSubmitted, setSearchSubmitted] = useState<{
    q: string;
    stage: string;
    signal: string;
    owner: string;
  } | null>(null);

  const { data, isLoading, refetch, isFetching, isError } = useQuery<SignalsDashboardResponse>({
    queryKey: ['insights', 'signals', windowDays],
    queryFn: () => insightsApi.getSignals(windowDays),
    retry: false,
    staleTime: 30_000,
  });

  const { data: trendData, isLoading: trendLoading } = useQuery<SignalsTrendResponse>({
    queryKey: ['insights', 'trends', windowDays],
    queryFn: () => insightsApi.getSignalsTrends(windowDays),
    retry: false,
    staleTime: 30_000,
    enabled: !isError,
  });

  const { data: convInsights, isLoading: convInsightLoading } =
    useQuery<ConversationInsightsResponse>({
      queryKey: ['insights', 'conversation-insights', windowDays],
      queryFn: () => insightsApi.getConversationInsights(windowDays),
      retry: false,
      staleTime: 30_000,
      enabled: !isError,
    });

  const { data: usersPage } = useQuery({
    queryKey: ['insights', 'users-options'],
    queryFn: () => usersApi.getUsers({ page: 1, page_size: 100 }),
    enabled: isManager && !isError,
  });

  const { data: searchData, isFetching: searchFetching } = useQuery<ConversationSearchResponse>({
    queryKey: [
      'insights',
      'conversation-search',
      searchSubmitted?.q,
      searchSubmitted?.stage,
      searchSubmitted?.signal,
      searchSubmitted?.owner,
    ],
    queryFn: () =>
      insightsApi.searchConversations({
        q: searchSubmitted!.q,
        ...(searchSubmitted!.stage ? { stage: searchSubmitted!.stage } : {}),
        ...(searchSubmitted!.signal ? { signal_type: searchSubmitted!.signal } : {}),
        ...(searchSubmitted!.owner && isManager
          ? { owner_id: Number(searchSubmitted!.owner) }
          : {}),
      }),
    enabled: Boolean(searchSubmitted?.q && searchSubmitted.q.length >= 2),
    retry: false,
  });

  const topicCards = useMemo(() => {
    const tc = data?.topic_counts ?? {};
    return [
      {
        key: 'pricing_concern',
        label: t('insights.topic_pricing'),
        value: tc.pricing_concern ?? 0,
      },
      { key: 'competitor', label: t('insights.topic_competitor'), value: tc.competitor ?? 0 },
      { key: 'objection', label: t('insights.topic_objection'), value: tc.objection ?? 0 },
    ];
  }, [data?.topic_counts, t]);

  const keywordRows = useMemo(() => {
    const h = convInsights?.transcript_keyword_hits ?? {};
    return [
      { key: 'pricing', label: t('insights.kw_pricing'), value: h.pricing ?? 0 },
      { key: 'objection', label: t('insights.kw_objection'), value: h.objection ?? 0 },
      { key: 'competitor', label: t('insights.kw_competitor'), value: h.competitor ?? 0 },
    ];
  }, [convInsights?.transcript_keyword_hits, t]);

  function runSearch() {
    const q = searchQ.trim();
    if (q.length < 2) return;
    setSearchSubmitted({
      q,
      stage: searchStage,
      signal: searchSignal,
      owner: searchOwner,
    });
  }

  if (isLoading) return <Skeleton variant="card" count={3} />;

  if (isError) {
    return (
      <div className="p-6">
        <p className="text-sm text-gray-600 dark:text-gray-300">{t('insights.unavailable')}</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title={t('insights.title')} description={t('insights.description')}>
        <div className="flex items-center gap-2">
          <select
            className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
          >
            <option value={30}>30</option>
            <option value={60}>60</option>
            <option value={90}>90</option>
          </select>
          <Button variant="secondary" loading={isFetching} onClick={() => refetch()}>
            {t('insights.refresh')}
          </Button>
        </div>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 mb-6">
        {topicCards.map((c) => (
          <Card key={c.key}>
            <div className="p-4 flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-gray-600 dark:text-gray-300">{c.label}</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{c.value}</p>
              </div>
              <TrendingUp className="text-blue-600" size={20} />
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 mb-6">
        <Card title={t('insights.severity')}>
          <div className="p-4 flex flex-wrap gap-2">
            <Badge variant="default" size="sm">
              low: {data?.severity_buckets?.low ?? 0}
            </Badge>
            <Badge variant="warning" size="sm">
              med: {data?.severity_buckets?.med ?? 0}
            </Badge>
            <Badge variant="danger" size="sm">
              high: {data?.severity_buckets?.high ?? 0}
            </Badge>
          </div>
        </Card>
        <Card title={t('insights.impacted')}>
          <div className="p-4">
            {!data?.impacted_opportunity_ids?.length ? (
              <p className="text-sm text-gray-500">{t('insights.none')}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {data.impacted_opportunity_ids.slice(0, 30).map((id) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => navigate(`/opportunities/${id}`)}
                    className="rounded-full border border-gray-200 dark:border-gray-700 px-2 py-1 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    #{id}
                  </button>
                ))}
              </div>
            )}
          </div>
        </Card>
        <Card title={t('insights.note')}>
          <div className="p-4 flex items-start gap-3">
            <AlertTriangle size={18} className="text-amber-500 mt-0.5" />
            <p className="text-sm text-gray-600 dark:text-gray-300">
              {t('insights.moderation_note')}
            </p>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 mb-8">
        <Card title={t('insights.trend_title')}>
          {trendLoading ? (
            <Skeleton variant="line" count={4} className="mt-2" />
          ) : !trendData?.series?.length ? (
            <p className="text-sm text-gray-500 p-4">{t('insights.trend_empty')}</p>
          ) : (
            <div className="h-72 w-full p-2">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={trendData.series}
                  margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" className="opacity-40" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="pricing_concern"
                    stroke="#2563eb"
                    dot={false}
                    name="pricing"
                  />
                  <Line
                    type="monotone"
                    dataKey="competitor"
                    stroke="#ca8a04"
                    dot={false}
                    name="competitor"
                  />
                  <Line
                    type="monotone"
                    dataKey="objection"
                    stroke="#dc2626"
                    dot={false}
                    name="objection"
                  />
                  <Line
                    type="monotone"
                    dataKey="total"
                    stroke="#64748b"
                    strokeDasharray="4 4"
                    dot={false}
                    name="total"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card title={t('insights.conv_keywords_title')}>
          {convInsightLoading ? (
            <Skeleton variant="line" count={3} className="mt-2" />
          ) : (
            <div className="p-4 space-y-3">
              {keywordRows.map((row) => (
                <div key={row.key} className="flex items-center justify-between text-sm">
                  <span className="text-gray-600 dark:text-gray-300">{row.label}</span>
                  <span className="font-semibold tabular-nums">{row.value}</span>
                </div>
              ))}
              <p className="text-xs text-gray-500 pt-2">{t('insights.conv_keywords_hint')}</p>
            </div>
          )}
        </Card>
      </div>

      <Card title={t('insights.search_title')}>
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
            <Input
              label={t('insights.search_q')}
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              placeholder={t('insights.search_q_ph')}
            />
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
                {t('insights.search_stage')}
              </label>
              <select
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
                value={searchStage}
                onChange={(e) => setSearchStage(e.target.value)}
              >
                <option value="">{t('insights.search_any')}</option>
                {STAGE_OPTIONS.filter(Boolean).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
                {t('insights.search_signal')}
              </label>
              <select
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
                value={searchSignal}
                onChange={(e) => setSearchSignal(e.target.value)}
              >
                <option value="">{t('insights.search_any')}</option>
                {SIGNAL_FILTER_OPTIONS.filter(Boolean).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            {isManager ? (
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
                  {t('insights.search_owner')}
                </label>
                <select
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
                  value={searchOwner}
                  onChange={(e) => setSearchOwner(e.target.value)}
                >
                  <option value="">{t('insights.search_any')}</option>
                  {(usersPage?.items ?? []).map(
                    (u: { id: number; full_name: string; email: string }) => (
                      <option key={u.id} value={String(u.id)}>
                        {u.full_name} ({u.email})
                      </option>
                    ),
                  )}
                </select>
              </div>
            ) : (
              <div />
            )}
          </div>
          <Button
            type="button"
            variant="secondary"
            loading={searchFetching}
            onClick={() => runSearch()}
          >
            <Search size={16} className="mr-1 inline" aria-hidden />
            {t('insights.search_btn')}
          </Button>

          {!searchData?.items?.length && searchSubmitted ? (
            <p className="text-sm text-gray-500">{t('insights.search_empty')}</p>
          ) : null}

          {searchData?.items?.length ? (
            <ul className="divide-y divide-gray-100 dark:divide-gray-800 border rounded-lg">
              {searchData.items.map((it) => (
                <li key={`${it.type}-${it.id}`} className="p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="info" size="sm">
                      {it.type}
                    </Badge>
                    <button
                      type="button"
                      className="font-medium text-blue-600 hover:underline"
                      onClick={() => navigate(`/opportunities/${it.opportunity_id}`)}
                    >
                      #{it.opportunity_id}
                    </button>
                    <span className="text-xs text-gray-500">{it.stage}</span>
                  </div>
                  <p className="mt-1 font-medium text-gray-900 dark:text-white">{it.title}</p>
                  <p className="mt-0.5 text-xs text-gray-600 dark:text-gray-300 line-clamp-2">
                    {it.snippet}
                  </p>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
