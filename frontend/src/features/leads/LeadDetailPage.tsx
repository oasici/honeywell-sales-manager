import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { onLeadChanged, onLeadConverted, onLeadScoreChanged } from '../../lib/cacheInvalidation';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import AiAttributeValuesPanel from '../intelligence/AiAttributeValuesPanel';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Skeleton } from '../../components/ui/Skeleton';
import { leadsApi, sequenceV2Api } from '../../lib/api';
import { formatDate } from '../../lib/formatters';
import { useT } from '../../hooks/useT';
import { translateLeadStatus } from '../../lib/labelTranslations';
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
  Pencil,
  X as XIcon,
} from 'lucide-react';

const STATUS_COLORS: Record<string, 'default' | 'info' | 'warning' | 'success' | 'danger'> = {
  new: 'default',
  contacted: 'info',
  qualified: 'success',
  unqualified: 'danger',
  converted: 'success',
};

function ScoreHistory({ leadId }: { leadId: number }) {
  const t = useT();
  const { data } = useQuery({
    queryKey: ['score-history', leadId],
    queryFn: () => sequenceV2Api.getDomainEvents('lead.score_changed', 20),
  });

  const events = (data?.events || []).filter((e: Record<string, unknown>) => {
    const payload = e.payload as Record<string, unknown> | null;
    return payload?.lead_id === leadId;
  });

  if (events.length === 0) return null;

  const SCORE_REASON_LABELS: Record<string, string> = {
    email_replied: t('lead_score_reason.email_replied'),
    email_bounced: t('lead_score_reason.email_bounced'),
    meeting_booked: t('lead_score_reason.meeting_booked'),
    quote_sent: t('lead_score_reason.quote_sent'),
    quote_approved: t('lead_score_reason.quote_approved'),
    call_connected: t('lead_score_reason.call_connected'),
    sequence_step_completed: t('lead_score_reason.sequence_step_completed'),
    positive_keyword: t('lead_score_reason.positive_keyword'),
    dnc_flagged: t('lead_score_reason.dnc_flagged'),
    sequence_exited_unresponsive: t('lead_score_reason.sequence_exited_unresponsive'),
    workflow_rule: t('lead_score_reason.workflow_rule'),
  };

  return (
    <div className="border-t mt-3 pt-3">
      <p className="text-xs font-medium text-slate-500 mb-2">{t('lead_detail.score_history')}</p>
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
              <span className="text-slate-500">
                {payload?.old_score} → {payload?.new_score}
              </span>
              <span className="text-slate-400 truncate">
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
  const color = score >= 70 ? '#10b981' : score >= 40 ? '#f59e0b' : '#ef4444';
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
        <span className="text-xl font-bold text-slate-900 dark:text-white">{score}</span>
      </div>
    </div>
  );
}

export default function LeadDetailPage() {
  const t = useT();
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

  // R5-FORM-2 — inline edit panel state. Pre-R5 LeadDetailPage only
  // mutated `status`, so editable fields (first_name, last_name,
  // phone, company, title, notes) had no UI affordance — reps had to
  // delete + recreate. Mirrors the customer detail edit pattern.
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    first_name: '',
    last_name: '',
    // R7-FORM-5 — backend LeadUpdate now accepts email; pre-fix
    // typo at lead creation forced delete-and-recreate.
    email: '',
    phone: '',
    company: '',
    title: '',
    notes: '',
  });

  const { data: lead, isLoading } = useQuery({
    queryKey: ['lead', leadId],
    queryFn: () => leadsApi.get(leadId),
    enabled: !!leadId,
  });

  const updateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => leadsApi.update(leadId, payload),
    onSuccess: () => {
      toast.success(t('leads.toast_updated'));
      // Round-15 Sprint 15g cohort 6 — onLeadChanged invalidates the
      // detail card AND list. Replaces the R4-CACHE-2 inline pair.
      onLeadChanged(queryClient, leadId);
    },
  });

  const convertMutation = useMutation({
    mutationFn: () => leadsApi.convert(leadId, convertForm),
    onSuccess: (data: { customer_id?: number; opportunity_id?: number }) => {
      toast.success(t('leads.toast_converted'));
      setShowConvert(false);
      // R4-CACHE-103 — converting creates a Customer + Opportunity and
      // marks the Lead converted. Every related list needs refresh.
      onLeadConverted(queryClient, leadId);
      if (data.customer_id) {
        navigate(`/customers/${data.customer_id}`);
      }
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          t('lead_detail.convert_error'),
      ),
  });

  const rescoreMutation = useMutation({
    mutationFn: () => leadsApi.rescore(leadId),
    onSuccess: () => {
      toast.success(t('leads.toast_rescored'));
      // R4-CACHE-104 — score column on list shows stale value otherwise.
      onLeadScoreChanged(queryClient, leadId);
    },
  });

  if (isLoading) return <Skeleton variant="card" count={3} />;
  if (!lead) return <p className="p-8 text-center text-slate-500">{t('lead_detail.not_found')}</p>;

  const canConvert = ['qualified', 'contacted'].includes(lead.status);
  const isConverted = lead.status === 'converted';

  const startEdit = () => {
    setEditForm({
      first_name: lead.first_name || '',
      last_name: lead.last_name || '',
      email: lead.email || '',
      phone: lead.phone || '',
      company: lead.company || '',
      title: lead.title || '',
      notes: lead.notes || '',
    });
    setIsEditing(true);
  };

  const submitEdit = () => {
    // Only send the editable fields the backend's LeadUpdate accepts.
    const wire: Record<string, unknown> = {
      first_name: editForm.first_name,
      last_name: editForm.last_name,
      phone: editForm.phone || null,
      company: editForm.company || null,
      title: editForm.title || null,
      notes: editForm.notes || null,
    };
    // Only send email if it changed; backend rejects duplicates with
    // 409 (caught upstream as a generic toast).
    if (editForm.email && editForm.email !== lead.email) {
      wire.email = editForm.email;
    }
    updateMutation.mutate(wire, {
      onSuccess: () => setIsEditing(false),
    });
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title={`${lead.first_name} ${lead.last_name}`}
        description={lead.company || lead.email}
      >
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => navigate('/leads')}>
            <ArrowLeft className="mr-1 h-4 w-4" /> {t('lead_detail.back')}
          </Button>
          {!isConverted && (
            <>
              <Button
                variant="secondary"
                onClick={() => rescoreMutation.mutate()}
                loading={rescoreMutation.isPending}
              >
                <RefreshCw className="mr-1 h-4 w-4" /> {t('lead_detail.rescore')}
              </Button>
              {canConvert && (
                <Button onClick={() => setShowConvert(true)}>
                  <UserCheck className="mr-1 h-4 w-4" /> {t('lead_detail.convert')}
                </Button>
              )}
            </>
          )}
        </div>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Score Card + History */}
        <Card title={t('lead_detail.score_title')}>
          <div className="flex flex-col items-center gap-3 py-4">
            <ScoreRing score={lead.lead_score} />
            <Badge variant={STATUS_COLORS[lead.status] || 'default'} size="md">
              {translateLeadStatus(lead.status, t)}
            </Badge>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {t('lead_detail.source_prefix')}: {lead.source}
            </p>
          </div>
          {/* score_breakdown is computed by the backend specifically for
              the detail view (audit F-5). Each row shows which factor
              contributed how many points so reps know *why* the lead is
              scored what it's scored. */}
          {Array.isArray(lead.score_breakdown) && lead.score_breakdown.length > 0 && (
            <div className="border-t mt-3 pt-3">
              <p className="text-xs font-medium text-slate-500 mb-2">
                {t('lead_detail.score_breakdown')}
              </p>
              <ul className="space-y-1">
                {/* R5-TS-3 — Lead.score_breakdown TS shape now matches
                    the wire shape {factor, points, reason}; the local
                    cast is no longer needed. Annotate the map params
                    so strict-mode tsc -b is happy with the optional
                    field narrowing. */}
                {lead.score_breakdown
                  .slice(0, 8)
                  .map((b: { factor: string; points: number; reason?: string }, i: number) => (
                    <li
                      key={i}
                      className="flex items-center justify-between gap-2 text-xs text-slate-600 dark:text-slate-300"
                    >
                      <span className="truncate">{b.reason ?? b.factor}</span>
                      <span
                        className={[
                          'shrink-0 tabular-nums font-semibold',
                          b.points >= 0 ? 'text-emerald-600' : 'text-red-600',
                        ].join(' ')}
                      >
                        {b.points >= 0 ? '+' : ''}
                        {b.points}
                      </span>
                    </li>
                  ))}
              </ul>
            </div>
          )}
          <ScoreHistory leadId={lead.id} />
        </Card>

        {/* Info Card */}
        <Card title={t('lead_detail.contact_title')} className="lg:col-span-2">
          {/* R5-FORM-2 — toggle between read-only summary and inline
              edit form. Editable fields match LeadUpdate (first_name,
              last_name, phone, company, title, notes); status stays
              owned by the buttons in the dedicated card below. */}
          {!isEditing ? (
            <>
              <div className="flex items-center justify-end px-4 pt-3">
                {!isConverted && (
                  <Button variant="ghost" size="sm" onClick={startEdit} type="button">
                    <Pencil className="mr-1 h-3.5 w-3.5" /> {t('leads.edit')}
                  </Button>
                )}
              </div>
              <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
                <div className="flex items-center gap-3">
                  <Mail className="h-4 w-4 text-slate-400" />
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {t('lead_detail.email')}
                    </p>
                    <p className="text-sm font-medium text-slate-900 dark:text-white">
                      {lead.email}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Phone className="h-4 w-4 text-slate-400" />
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">{t('leads.phone')}</p>
                    <p className="text-sm font-medium text-slate-900 dark:text-white">
                      {lead.phone || '-'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Building2 className="h-4 w-4 text-slate-400" />
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {t('leads.company')}
                    </p>
                    <p className="text-sm font-medium text-slate-900 dark:text-white">
                      {lead.company || '-'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Briefcase className="h-4 w-4 text-slate-400" />
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {t('leads.job_title')}
                    </p>
                    <p className="text-sm font-medium text-slate-900 dark:text-white">
                      {lead.title || '-'}
                    </p>
                  </div>
                </div>
              </div>
              {lead.owner_name && (
                <div className="border-t border-slate-100 px-4 py-3 dark:border-slate-800">
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {t('lead_detail.assigned_to')}:{' '}
                    <span className="font-medium text-slate-900 dark:text-white">
                      {lead.owner_name}
                    </span>
                  </p>
                </div>
              )}
            </>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submitEdit();
              }}
              className="space-y-3 p-4"
            >
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Input
                  label={t('leads.first_name')}
                  value={editForm.first_name}
                  onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
                  required
                />
                <Input
                  label={t('leads.last_name')}
                  value={editForm.last_name}
                  onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
                  required
                />
                {/* R7-FORM-5 — email is editable now (backend LeadUpdate
                    accepts EmailStr). */}
                <Input
                  label="E-posta"
                  type="email"
                  value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                />
                <Input
                  label={t('leads.phone')}
                  value={editForm.phone}
                  onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                />
                <Input
                  label={t('leads.company')}
                  value={editForm.company}
                  onChange={(e) => setEditForm({ ...editForm, company: e.target.value })}
                />
                <Input
                  label={t('leads.job_title')}
                  value={editForm.title}
                  onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                />
              </div>
              <div>
                <label
                  htmlFor="lead-edit-notes"
                  className="mb-1.5 block text-[12px] font-medium text-slate-700 dark:text-slate-300"
                >
                  {t('leads.notes')}
                </label>
                <textarea
                  id="lead-edit-notes"
                  rows={3}
                  value={editForm.notes}
                  onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                  placeholder={t('leads.notes_ph')}
                  className="block w-full rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-900 placeholder:text-slate-400 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-1">
                <Button
                  variant="secondary"
                  size="sm"
                  type="button"
                  onClick={() => setIsEditing(false)}
                  disabled={updateMutation.isPending}
                >
                  <XIcon className="mr-1 h-3.5 w-3.5" /> {t('common.cancel')}
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  type="submit"
                  loading={updateMutation.isPending}
                >
                  {t('leads.save')}
                </Button>
              </div>
            </form>
          )}
        </Card>

        {/* Status Management */}
        {!isConverted && (
          <Card title={t('lead_detail.status_mgmt')} className="lg:col-span-3">
            <div className="flex flex-wrap gap-2 p-4">
              {['new', 'contacted', 'qualified', 'unqualified'].map((s) => (
                <Button
                  key={s}
                  variant={lead.status === s ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => updateMutation.mutate({ status: s })}
                  loading={updateMutation.isPending}
                >
                  {translateLeadStatus(s, t)}
                </Button>
              ))}
            </div>
          </Card>
        )}

        {/* Conversion Info */}
        {isConverted && (
          <Card title={t('lead_detail.conversion_info')} className="lg:col-span-3">
            <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <p className="text-xs text-slate-500">{t('lead_detail.conversion_date')}</p>
                <p className="text-sm font-medium text-slate-900 dark:text-white">
                  {formatDate(lead.converted_at)}
                </p>
              </div>
              {lead.converted_customer_id && (
                <div>
                  <p className="text-xs text-slate-500">{t('lead_detail.customer')}</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate(`/customers/${lead.converted_customer_id}`)}
                  >
                    {t('lead_detail.customer')} #{lead.converted_customer_id}
                  </Button>
                </div>
              )}
              {lead.converted_opportunity_id && (
                <div>
                  <p className="text-xs text-slate-500">{t('lead_detail.opportunity')}</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate(`/opportunities/${lead.converted_opportunity_id}`)}
                  >
                    {t('lead_detail.opportunity')} #{lead.converted_opportunity_id}
                  </Button>
                </div>
              )}
              {/* Round-15 §8.1 quick-win — backend has emitted
                  ``lead.converted_by`` since R6 (sales-rep audit trail);
                  the conversion card never showed it. Surface so an
                  operator can see *who* converted the lead at a glance. */}
              {lead.converted_by != null && (
                <div>
                  <p className="text-xs text-slate-500">{t('lead_detail.converted_by')}</p>
                  <p className="text-sm font-medium text-slate-900 dark:text-white">
                    #{lead.converted_by}
                  </p>
                </div>
              )}
            </div>
          </Card>
        )}

        {/* Notes */}
        {lead.notes && (
          <Card title={t('lead_detail.notes')} className="lg:col-span-3">
            <p className="p-4 text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
              {lead.notes}
            </p>
          </Card>
        )}
      </div>

      {/* Round-8 R8-DEAD-2 — AI attribute values for this lead. */}
      <div className="mt-6">
        <AiAttributeValuesPanel entityType="lead" entityId={leadId} />
      </div>

      {/* Convert Modal */}
      <Modal
        isOpen={showConvert}
        onClose={() => setShowConvert(false)}
        title={t('lead_detail.convert_modal_title')}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            convertMutation.mutate();
          }}
          className="space-y-4"
        >
          <p className="text-sm text-slate-600 dark:text-slate-400">
            <strong>
              {lead.first_name} {lead.last_name}
            </strong>{' '}
            {t('lead_detail.convert_modal_body_suffix')}
          </p>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={convertForm.create_opportunity}
              onChange={(e) =>
                setConvertForm({ ...convertForm, create_opportunity: e.target.checked })
              }
              className="rounded border-slate-200"
            />
            <span className="text-sm text-slate-700 dark:text-slate-300">
              {t('lead_detail.create_opportunity')}
            </span>
          </label>
          {convertForm.create_opportunity && (
            <div className="space-y-3 border-l-2 border-blue-200 pl-4 dark:border-blue-800">
              <Input
                label={t('lead_detail.opp_title')}
                value={convertForm.opportunity_title}
                onChange={(e) =>
                  setConvertForm({ ...convertForm, opportunity_title: e.target.value })
                }
                placeholder={t('lead_detail.opp_title_placeholder').replace(
                  '{company}',
                  lead.company || lead.last_name,
                )}
              />
              <Input
                label={t('lead_detail.opp_amount_try')}
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
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={convertMutation.isPending}>
              {t('lead_detail.convert')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
