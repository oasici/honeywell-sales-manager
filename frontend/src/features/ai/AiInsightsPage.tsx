import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Brain, TrendingUp, AlertTriangle, Swords, Sparkles } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { aiApi, opportunitiesApi, quotesApi, customersApi, emailsApi } from '../../lib/api';
import type {
  AiSummarizeResponse,
  PipelineSuggestion,
  DealRiskResult,
  CompetitiveIntelData,
  Opportunity,
  Quote,
  Customer,
  EmailRequest,
  PaginatedResponse,
} from '../../lib/types';

type TabKey = 'summarize' | 'pipeline' | 'risk' | 'competitive';

interface EntityOption {
  id: number;
  label: string;
}

const TABS: { key: TabKey; label: string; icon: React.ReactNode }[] = [
  { key: 'summarize', label: 'AI Özet', icon: <Sparkles size={16} /> },
  { key: 'pipeline', label: 'Pipeline Önerisi', icon: <TrendingUp size={16} /> },
  { key: 'risk', label: 'Risk Analizi', icon: <AlertTriangle size={16} /> },
  { key: 'competitive', label: 'Rekabet İstihbaratı', icon: <Swords size={16} /> },
];

const RISK_COLORS: Record<string, string> = {
  low: 'text-green-600',
  medium: 'text-yellow-600',
  high: 'text-orange-600',
  critical: 'text-red-600',
};

const ENTITY_DROPDOWN_CLASS =
  'rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm w-full min-w-[250px]';

function SummarizeTab() {
  const [entityType, setEntityType] = useState('opportunity');
  const [entityId, setEntityId] = useState('');
  const [result, setResult] = useState<AiSummarizeResponse | null>(null);

  const { data: entities = [] } = useQuery<EntityOption[]>({
    queryKey: ['ai-entities', entityType],
    queryFn: async (): Promise<EntityOption[]> => {
      if (entityType === 'opportunity') {
        const res: PaginatedResponse<Opportunity> = await opportunitiesApi.list({ limit: 50 });
        const items: Opportunity[] = res?.items ?? [];
        return items.map((o) => ({ id: o.id, label: `#${o.id} - ${o.title}` }));
      }
      if (entityType === 'quote') {
        const res: PaginatedResponse<Quote> = await quotesApi.getQuotes({ limit: 50 });
        const items: Quote[] = res?.items ?? [];
        return items.map((q) => ({ id: q.id, label: q.quote_number }));
      }
      if (entityType === 'customer') {
        const res: PaginatedResponse<Customer> = await customersApi.getCustomers({ limit: 50 });
        const items: Customer[] = res?.items ?? [];
        return items.map((c) => ({ id: c.id, label: `#${c.id} - ${c.name}` }));
      }
      if (entityType === 'email') {
        const res: PaginatedResponse<EmailRequest> = await emailsApi.getEmails({ limit: 50 });
        const items: EmailRequest[] = res?.items ?? [];
        return items.map((e) => ({ id: e.id, label: `#${e.id} - ${e.subject}` }));
      }
      return [];
    },
  });

  const mutation = useMutation({
    mutationFn: () => aiApi.summarize({ entity_type: entityType, entity_id: Number(entityId) }),
    onSuccess: (data) => setResult(data),
    onError: () => toast.error('Özet oluşturulamadı'),
  });

  function handleEntityTypeChange(value: string) {
    setEntityType(value);
    setEntityId('');
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-end flex-wrap">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
            Varlık Tipi
          </label>
          <select
            className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
            value={entityType}
            onChange={(e) => handleEntityTypeChange(e.target.value)}
          >
            <option value="opportunity">Fırsat</option>
            <option value="quote">Teklif</option>
            <option value="email">E-posta</option>
            <option value="customer">Müşteri</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
            Varlık Seç
          </label>
          <select
            className={ENTITY_DROPDOWN_CLASS}
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
          >
            <option value="">-- Seçin --</option>
            {entities.map((ent) => (
              <option key={ent.id} value={ent.id}>
                {ent.label}
              </option>
            ))}
          </select>
        </div>
        <Button onClick={() => mutation.mutate()} loading={mutation.isPending} disabled={!entityId}>
          Ozetle
        </Button>
      </div>
      {result && (
        <Card>
          <div className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <h3 className="text-sm font-semibold text-slate-900">AI Özeti</h3>
              {result.cached && (
                <Badge variant="default" size="sm">
                  Onbellek
                </Badge>
              )}
            </div>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{result.summary}</p>
            {result.sources.length > 0 && (
              <p className="text-xs text-slate-400 mt-2">Kaynaklar: {result.sources.join(', ')}</p>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}

function PipelineTab() {
  const [oppId, setOppId] = useState('');
  const [result, setResult] = useState<PipelineSuggestion | null>(null);

  const { data: opportunities = [] } = useQuery<EntityOption[]>({
    queryKey: ['ai-opps'],
    queryFn: async (): Promise<EntityOption[]> => {
      const res: PaginatedResponse<Opportunity> = await opportunitiesApi.list({ limit: 50 });
      const items: Opportunity[] = res?.items ?? [];
      return items.map((o) => ({ id: o.id, label: `#${o.id} - ${o.title} (${o.stage})` }));
    },
  });

  const mutation = useMutation({
    mutationFn: () => aiApi.suggestPipeline({ opportunity_id: Number(oppId) }),
    onSuccess: (data) => setResult(data),
    onError: () => toast.error('Öneri oluşturulamadı'),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-end flex-wrap">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
            Fırsat Seç
          </label>
          <select
            className={ENTITY_DROPDOWN_CLASS}
            value={oppId}
            onChange={(e) => setOppId(e.target.value)}
          >
            <option value="">-- Seçin --</option>
            {opportunities.map((opp) => (
              <option key={opp.id} value={opp.id}>
                {opp.label}
              </option>
            ))}
          </select>
        </div>
        <Button onClick={() => mutation.mutate()} loading={mutation.isPending} disabled={!oppId}>
          Analiz Et
        </Button>
      </div>
      {result && (
        <Card>
          <div className="p-4 space-y-3">
            <div className="flex items-center gap-4">
              <div>
                <span className="text-xs text-slate-500">Mevcut Aşama</span>
                <p className="text-sm font-medium">{result.current_stage}</p>
              </div>
              <span className="text-slate-300">→</span>
              <div>
                <span className="text-xs text-slate-500">Önerilen Aşama</span>
                <p className="text-sm font-semibold text-honeywell-red">{result.suggested_stage}</p>
              </div>
            </div>
            <div>
              <h4 className="text-xs font-medium text-slate-500 mb-1">Önerilen Sonraki Adımlar</h4>
              <ul className="list-disc list-inside text-sm text-slate-700 space-y-1">
                {result.suggested_next_steps.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="text-xs font-medium text-slate-500 mb-1">Faktorler</h4>
              <div className="flex flex-wrap gap-1">
                {result.factors.map((f, i) => (
                  <Badge key={i} variant="info" size="sm">
                    {f}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function RiskTab() {
  const [oppId, setOppId] = useState('');
  const [result, setResult] = useState<DealRiskResult | null>(null);

  const { data: opportunities = [] } = useQuery<EntityOption[]>({
    queryKey: ['ai-opps'],
    queryFn: async (): Promise<EntityOption[]> => {
      const res: PaginatedResponse<Opportunity> = await opportunitiesApi.list({ limit: 50 });
      const items: Opportunity[] = res?.items ?? [];
      return items.map((o) => ({ id: o.id, label: `#${o.id} - ${o.title} (${o.stage})` }));
    },
  });

  const mutation = useMutation({
    mutationFn: () => aiApi.dealRisk(Number(oppId)),
    onSuccess: (data) => setResult(data),
    onError: () => toast.error('Risk analizi yapilamadi'),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-end flex-wrap">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
            Fırsat Seç
          </label>
          <select
            className={ENTITY_DROPDOWN_CLASS}
            value={oppId}
            onChange={(e) => setOppId(e.target.value)}
          >
            <option value="">-- Seçin --</option>
            {opportunities.map((opp) => (
              <option key={opp.id} value={opp.id}>
                {opp.label}
              </option>
            ))}
          </select>
        </div>
        <Button onClick={() => mutation.mutate()} loading={mutation.isPending} disabled={!oppId}>
          Risk Analizi
        </Button>
      </div>
      {result && (
        <Card>
          <div className="p-4 space-y-3">
            <div className="flex items-center gap-4">
              <div>
                <span className="text-xs text-slate-500">Risk Skoru</span>
                <p
                  className={`text-2xl font-bold ${RISK_COLORS[result.risk_level] ?? 'text-slate-900'}`}
                >
                  {result.risk_score}
                </p>
              </div>
              <Badge
                variant={
                  result.risk_level === 'low'
                    ? 'success'
                    : result.risk_level === 'critical'
                      ? 'danger'
                      : 'warning'
                }
              >
                {result.risk_level.toUpperCase()}
              </Badge>
            </div>
            <div>
              <h4 className="text-xs font-medium text-slate-500 mb-2">Risk Faktorleri</h4>
              <div className="space-y-2">
                {result.factors.map((f, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2"
                  >
                    <div>
                      <p className="text-sm font-medium text-slate-900">{f.name}</p>
                      <p className="text-xs text-slate-500">{f.description}</p>
                    </div>
                    <span className="text-sm font-semibold">{f.score}</span>
                  </div>
                ))}
              </div>
            </div>
            {result.recommendations.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-slate-500 mb-1">Öneriler</h4>
                <ul className="list-disc list-inside text-sm text-slate-700 space-y-1">
                  {result.recommendations.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}

function CompetitiveTab() {
  const [days, setDays] = useState(90);
  const { data, isLoading } = useQuery<CompetitiveIntelData>({
    queryKey: ['ai-competitive', days],
    queryFn: () => aiApi.competitiveIntel(days),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label className="text-sm text-slate-600">Son</label>
        <select
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          <option value={30}>30 gun</option>
          <option value={60}>60 gun</option>
          <option value={90}>90 gun</option>
          <option value={180}>180 gun</option>
        </select>
        {data && (
          <span className="text-sm text-slate-500">Toplam: {data.total_mentions} bahsetme</span>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} variant="card" />
          ))}
        </div>
      ) : !data?.competitors?.length ? (
        <EmptyState title="Rakip verisi yok" description="Bu donemde rakip bahsi bulunamadi" />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {data.competitors.map((comp) => (
            <Card key={comp.name}>
              <div className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-slate-900">{comp.name}</h3>
                  <Badge variant="info" size="sm">
                    {comp.mention_count} bahsetme
                  </Badge>
                </div>
                <div className="text-xs text-slate-500 mb-3">
                  Ortalama duygu:{' '}
                  {comp.sentiment_avg > 0 ? 'Pozitif' : comp.sentiment_avg < 0 ? 'Negatif' : 'Notr'}
                </div>
                {comp.recent_mentions.length > 0 && (
                  <div className="space-y-2">
                    {comp.recent_mentions.slice(0, 3).map((m, i) => (
                      <div key={i} className="rounded bg-slate-50 px-3 py-2 text-xs text-slate-600">
                        <span className="text-slate-400">[{m.source_type}]</span> {m.context_snippet}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AiInsightsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('summarize');

  return (
    <div>
      <PageHeader title="AI Asistan" description="Yapay zeka destekli analizler ve öneriler">
        <Brain size={20} className="text-honeywell-red" />
      </PageHeader>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 rounded-lg bg-slate-100 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'summarize' && <SummarizeTab />}
      {activeTab === 'pipeline' && <PipelineTab />}
      {activeTab === 'risk' && <RiskTab />}
      {activeTab === 'competitive' && <CompetitiveTab />}
    </div>
  );
}
