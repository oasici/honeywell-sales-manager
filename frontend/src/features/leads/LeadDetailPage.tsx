import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Skeleton } from '../../components/ui/Skeleton';
import { leadsApi, sequenceV2Api } from '../../lib/api';
import { formatDate } from '../../lib/formatters';
import {
  ArrowLeft,
  UserCheck,
  RefreshCw,
  Mail,
  Phone,
  Building2,
  Briefcase,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';

const STATUS_LABELS: Record<string, string> = {
  new: 'Yeni',
  contacted: 'Iletisime Gecildi',
  qualified: 'Nitelikli',
  unqualified: 'Niteliksiz',
  converted: 'Donusturuldu',
};

const STATUS_COLORS: Record<string, 'default' | 'info' | 'warning' | 'success' | 'danger'> = {
  new: 'default',
  contacted: 'info',
  qualified: 'success',
  unqualified: 'danger',
  converted: 'success',
};

const SCORE_REASON_LABELS: Record<string, string> = {
  email_replied: 'Email yanit',
  email_bounced: 'Email bounce',
  meeting_booked: 'Toplanti',
  quote_sent: 'Teklif gonderildi',
  quote_approved: 'Teklif onaylandi',
  call_connected: 'Arama baglandi',
  sequence_step_completed: 'Dizi adimi',
  positive_keyword: 'Pozitif anahtar kelime',
  dnc_flagged: 'DNC isaretlendi',
  sequence_exited_unresponsive: 'Yanitsiz cikis',
  workflow_rule: 'Is kurali',
};

function ScoreHistory({ leadId }: { leadId: number }) {
  const { data } = useQuery({
    queryKey: ['score-history', leadId],
    queryFn: () => sequenceV2Api.getDomainEvents('lead.score_changed', 20),
  });

  const events = (data?.events || []).filter((e: Record<string, unknown>) => {
    const payload = e.payload as Record<string, unknown> | null;
    return payload?.lead_id === leadId;
  });

  if (events.length === 0) return null;

  return (
    <div className="border-t mt-3 pt-3">
      <p className="text-xs font-medium text-gray-500 mb-2">Skor Gecmisi</p>
      <div className="space-y-1.5 max-h-40 overflow-y-auto">
        {events.map((e: Record<string, unknown>) => {
          const payload = e.payload as Record<string, number | string>;
          const delta = Number(payload?.delta || 0);
          const reason = String(payload?.reason || '');
          return (
            <div key={e.id as number} className="flex items-center gap-2 text-xs">
              {delta > 0 ? (
                <TrendingUp className="w-3 h-3 text-green-500 shrink-0" />
              ) : (
                <TrendingDown className="w-3 h-3 text-red-500 shrink-0" />
              )}
              <span
                className={delta > 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}
              >
                {delta > 0 ? '+' : ''}
                {delta}
              </span>
              <span className="text-gray-500">
                {payload?.old_score} → {payload?.new_score}
              </span>
              <span className="text-gray-400 truncate">
                {SCORE_REASON_LABELS[reason] || reason}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const color = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';
  const pct = Math.min(score, 100);
  const circumference = 2 * Math.PI * 36;
  const offset = circumference - (pct / 100) * circumference;

  return (
    <div className="relative h-24 w-24">
      <svg className="h-24 w-24 -rotate-90" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="36" stroke="#e5e7eb" strokeWidth="6" fill="none" />
        <circle
          cx="40"
          cy="40"
          r="36"
          stroke={color}
          strokeWidth="6"
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-xl font-bold text-gray-900 dark:text-white">{score}</span>
      </div>
    </div>
  );
}

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const leadId = Number(id);

  const [showConvert, setShowConvert] = useState(false);
  const [convertForm, setConvertForm] = useState({
    create_opportunity: true,
    opportunity_title: '',
    opportunity_amount: 0,
  });

  const { data: lead, isLoading } = useQuery({
    queryKey: ['lead', leadId],
    queryFn: () => leadsApi.get(leadId),
    enabled: !!leadId,
  });

  const updateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => leadsApi.update(leadId, payload),
    onSuccess: () => {
      toast.success('Lead guncellendi');
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] });
    },
  });

  const convertMutation = useMutation({
    mutationFn: () => leadsApi.convert(leadId, convertForm),
    onSuccess: (data: { customer_id?: number; opportunity_id?: number }) => {
      toast.success('Lead basariyla donusturuldu!');
      setShowConvert(false);
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] });
      if (data.customer_id) {
        navigate(`/customers/${data.customer_id}`);
      }
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Donusum hatasi',
      ),
  });

  const rescoreMutation = useMutation({
    mutationFn: () => leadsApi.rescore(leadId),
    onSuccess: () => {
      toast.success('Skor guncellendi');
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] });
    },
  });

  if (isLoading) return <Skeleton variant="card" count={3} />;
  if (!lead) return <p className="p-8 text-center text-gray-500">Lead bulunamadi</p>;

  const canConvert = ['qualified', 'contacted'].includes(lead.status);
  const isConverted = lead.status === 'converted';

  return (
    <div className="space-y-4">
      <PageHeader
        title={`${lead.first_name} ${lead.last_name}`}
        description={lead.company || lead.email}
      >
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => navigate('/leads')}>
            <ArrowLeft className="mr-1 h-4 w-4" /> Geri
          </Button>
          {!isConverted && (
            <>
              <Button
                variant="secondary"
                onClick={() => rescoreMutation.mutate()}
                loading={rescoreMutation.isPending}
              >
                <RefreshCw className="mr-1 h-4 w-4" /> Yeniden Skorla
              </Button>
              {canConvert && (
                <Button onClick={() => setShowConvert(true)}>
                  <UserCheck className="mr-1 h-4 w-4" /> Donustur
                </Button>
              )}
            </>
          )}
        </div>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Score Card + History */}
        <Card title="Lead Skoru">
          <div className="flex flex-col items-center gap-3 py-4">
            <ScoreRing score={lead.lead_score} />
            <Badge variant={STATUS_COLORS[lead.status] || 'default'} size="md">
              {STATUS_LABELS[lead.status] || lead.status}
            </Badge>
            <p className="text-xs text-gray-500 dark:text-gray-400">Kaynak: {lead.source}</p>
          </div>
          <ScoreHistory leadId={lead.id} />
        </Card>

        {/* Info Card */}
        <Card title="Iletisim Bilgileri" className="lg:col-span-2">
          <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
            <div className="flex items-center gap-3">
              <Mail className="h-4 w-4 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Email</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">{lead.email}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Phone className="h-4 w-4 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Telefon</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {lead.phone || '-'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Building2 className="h-4 w-4 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Firma</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {lead.company || '-'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Briefcase className="h-4 w-4 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Unvan</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {lead.title || '-'}
                </p>
              </div>
            </div>
          </div>
          {lead.owner_name && (
            <div className="border-t border-gray-100 px-4 py-3 dark:border-gray-700">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Atanan:{' '}
                <span className="font-medium text-gray-900 dark:text-white">{lead.owner_name}</span>
              </p>
            </div>
          )}
        </Card>

        {/* Status Management */}
        {!isConverted && (
          <Card title="Durum Yonetimi" className="lg:col-span-3">
            <div className="flex flex-wrap gap-2 p-4">
              {['new', 'contacted', 'qualified', 'unqualified'].map((s) => (
                <Button
                  key={s}
                  variant={lead.status === s ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => updateMutation.mutate({ status: s })}
                  loading={updateMutation.isPending}
                >
                  {STATUS_LABELS[s]}
                </Button>
              ))}
            </div>
          </Card>
        )}

        {/* Conversion Info */}
        {isConverted && (
          <Card title="Donusum Bilgileri" className="lg:col-span-3">
            <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
              <div>
                <p className="text-xs text-gray-500">Donusum Tarihi</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {formatDate(lead.converted_at)}
                </p>
              </div>
              {lead.converted_customer_id && (
                <div>
                  <p className="text-xs text-gray-500">Musteri</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate(`/customers/${lead.converted_customer_id}`)}
                  >
                    Musteri #{lead.converted_customer_id}
                  </Button>
                </div>
              )}
              {lead.converted_opportunity_id && (
                <div>
                  <p className="text-xs text-gray-500">Firsat</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate(`/opportunities/${lead.converted_opportunity_id}`)}
                  >
                    Firsat #{lead.converted_opportunity_id}
                  </Button>
                </div>
              )}
            </div>
          </Card>
        )}

        {/* Notes */}
        {lead.notes && (
          <Card title="Notlar" className="lg:col-span-3">
            <p className="p-4 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
              {lead.notes}
            </p>
          </Card>
        )}
      </div>

      {/* Convert Modal */}
      <Modal isOpen={showConvert} onClose={() => setShowConvert(false)} title="Lead Donustir">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            convertMutation.mutate();
          }}
          className="space-y-4"
        >
          <p className="text-sm text-gray-600 dark:text-gray-400">
            <strong>
              {lead.first_name} {lead.last_name}
            </strong>{' '}
            musteri olarak kaydedilecek.
          </p>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={convertForm.create_opportunity}
              onChange={(e) =>
                setConvertForm({ ...convertForm, create_opportunity: e.target.checked })
              }
              className="rounded border-gray-300"
            />
            <span className="text-sm text-gray-700 dark:text-gray-300">
              Ayni zamanda firsat olustur
            </span>
          </label>
          {convertForm.create_opportunity && (
            <div className="space-y-3 border-l-2 border-blue-200 pl-4 dark:border-blue-800">
              <Input
                label="Firsat Basligi"
                value={convertForm.opportunity_title}
                onChange={(e) =>
                  setConvertForm({ ...convertForm, opportunity_title: e.target.value })
                }
                placeholder={`${lead.company || lead.last_name} - Yeni Firsat`}
              />
              <Input
                label="Tahmini Tutar (TRY)"
                type="number"
                value={convertForm.opportunity_amount || ''}
                onChange={(e) =>
                  setConvertForm({ ...convertForm, opportunity_amount: Number(e.target.value) })
                }
              />
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setShowConvert(false)} type="button">
              Iptal
            </Button>
            <Button type="submit" loading={convertMutation.isPending}>
              Donustur
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
