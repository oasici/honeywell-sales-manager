import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  ListChecks,
  GitBranch,
  FlaskConical,
  AlertCircle,
  CheckCircle,
  XCircle,
  Clock,
} from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { engagementApi, sequenceV2Api } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import type { Sequence, SequenceEnrollment } from '../../lib/types';
import { useT } from '../../hooks/useT';
import { useAuthStore } from '../../stores/authStore';

const PERF_QUERY_KEY = ['sequences', 'performance'] as const;

export default function SequencesPage() {
  const t = useT();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const isManager = useAuthStore((s) => s.user?.role === 'sales_manager');

  const [isEnrollOpen, setIsEnrollOpen] = useState(false);
  const [selectedSequenceId, setSelectedSequenceId] = useState<number | null>(null);

  const [enrollForm, setEnrollForm] = useState({
    opportunity_id: '',
    customer_id: '',
  });

  const { data, isLoading } = useQuery<{ sequences: Sequence[] }>({
    queryKey: ['sequences'],
    queryFn: () => engagementApi.listSequences(),
  });

  const { data: enrollmentsData } = useQuery<{ enrollments: SequenceEnrollment[] }>({
    queryKey: ['sequence-enrollments'],
    queryFn: () => engagementApi.listEnrollments(),
  });

  const enrollMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => engagementApi.enrollInSequence(payload),
    onSuccess: () => {
      toast.success(t('sequences.toast_enroll_ok'));
      queryClient.invalidateQueries({ queryKey: ['sequence-enrollments'] });
      queryClient.invalidateQueries({ queryKey: PERF_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: ['cockpit', 'sequence-performance'] });
      queryClient.invalidateQueries({ queryKey: ['sequence-analytics'] });
      queryClient.invalidateQueries({ queryKey: ['cockpit', 'sequence-analytics'] });
      setIsEnrollOpen(false);
      resetEnrollForm();
    },
    onError: () => toast.error(t('sequences.toast_enroll_fail')),
  });

  const pauseMutation = useMutation({
    mutationFn: (enrollmentId: number) => engagementApi.pauseEnrollment(enrollmentId),
    onSuccess: () => {
      toast.success(t('sequences.toast_pause_ok'));
      queryClient.invalidateQueries({ queryKey: ['sequence-enrollments'] });
      queryClient.invalidateQueries({ queryKey: PERF_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: ['cockpit', 'sequence-performance'] });
      queryClient.invalidateQueries({ queryKey: ['sequence-analytics'] });
      queryClient.invalidateQueries({ queryKey: ['cockpit', 'sequence-analytics'] });
    },
    onError: () => toast.error(t('sequences.toast_pause_fail')),
  });

  const resumeMutation = useMutation({
    mutationFn: (enrollmentId: number) => engagementApi.resumeEnrollment(enrollmentId),
    onSuccess: () => {
      toast.success(t('sequences.toast_resume_ok'));
      queryClient.invalidateQueries({ queryKey: ['sequence-enrollments'] });
      queryClient.invalidateQueries({ queryKey: PERF_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: ['cockpit', 'sequence-performance'] });
      queryClient.invalidateQueries({ queryKey: ['sequence-analytics'] });
      queryClient.invalidateQueries({ queryKey: ['cockpit', 'sequence-analytics'] });
    },
    onError: () => toast.error(t('sequences.toast_resume_fail')),
  });

  function resetEnrollForm() {
    setEnrollForm({ opportunity_id: '', customer_id: '' });
  }

  function handleEnroll() {
    if (!selectedSequenceId) return;
    if (!enrollForm.opportunity_id && !enrollForm.customer_id) {
      toast.error(t('sequences.err_need_id'));
      return;
    }
    enrollMutation.mutate({
      sequence_id: selectedSequenceId,
      ...(enrollForm.opportunity_id && { opportunity_id: Number(enrollForm.opportunity_id) }),
      ...(enrollForm.customer_id && { customer_id: Number(enrollForm.customer_id) }),
    });
  }

  function openEnrollModal(sequenceId: number) {
    setSelectedSequenceId(sequenceId);
    resetEnrollForm();
    setIsEnrollOpen(true);
  }

  function getEnrollmentCount(sequenceId: number): number {
    if (!enrollmentsData?.enrollments) return 0;
    return enrollmentsData.enrollments.filter((e) => e.sequence_id === sequenceId).length;
  }

  function getEnrollmentsForSequence(sequenceId: number): SequenceEnrollment[] {
    if (!enrollmentsData?.enrollments) return [];
    return enrollmentsData.enrollments.filter((e) => e.sequence_id === sequenceId);
  }

  // V2 analytics + performance (manager-only; backend returns 403 otherwise)
  const { data: analyticsData } = useQuery({
    queryKey: ['sequence-analytics'],
    queryFn: () => sequenceV2Api.getAnalytics(),
    enabled: Boolean(isManager),
  });

  const { data: variantData } = useQuery({
    queryKey: ['sequence-variants'],
    queryFn: () => sequenceV2Api.getVariantMetrics(),
    enabled: Boolean(isManager),
  });

  const { data: perfData, isLoading: perfLoading } = useQuery({
    queryKey: PERF_QUERY_KEY,
    queryFn: () => sequenceV2Api.getPerformance(),
    enabled: Boolean(isManager),
    refetchInterval: 120_000,
  });

  const sequences = data?.sequences ?? [];
  const perfRows = (perfData?.sequences ?? []) as Array<Record<string, unknown>>;

  const hasVariants = (steps: Record<string, unknown>[]) =>
    steps.some((s) => Array.isArray(s.variants) && s.variants.length > 0);
  const hasBranching = (steps: Record<string, unknown>[]) =>
    steps.some((s) => Array.isArray(s.branch_rules) && s.branch_rules.length > 0);

  const EXIT_LABELS: Record<string, string> = {
    all_steps_completed: t('sequences.status_completed'),
    lead_converted: 'Lead converted',
    opp_closed: t('sequences.exit_opp_closed'),
    email_bounced: 'Email Bounce',
    dnc: 'DNC',
    manual: t('sequences.exit_manual'),
    global_exit: t('sequences.exit_global'),
  };

  const STATUS_CONFIG: Record<
    string,
    {
      variant: 'success' | 'warning' | 'danger' | 'info' | 'default';
      label: string;
      icon: typeof CheckCircle;
    }
  > = {
    active: { variant: 'success', label: t('sequences.status_active'), icon: Clock },
    completed: { variant: 'info', label: t('sequences.status_completed'), icon: CheckCircle },
    exited: { variant: 'danger', label: t('sequences.status_exited'), icon: XCircle },
    paused: { variant: 'warning', label: t('sequences.status_paused'), icon: AlertCircle },
    cancelled: { variant: 'default', label: t('sequences.status_cancelled'), icon: XCircle },
  };

  return (
    <div>
      <PageHeader title={t('sequences.title')} description={t('sequences.description')}>
        <Button onClick={() => navigate('/engagement/sequences/builder')}>
          {t('sequences.new')}
        </Button>
      </PageHeader>

      {isLoading ? (
        <Skeleton variant="card" count={3} />
      ) : sequences.length === 0 ? (
        <EmptyState
          title={t('sequences.empty')}
          description={t('sequences.empty')}
          icon={<ListChecks size={40} />}
          action={
            <Button onClick={() => navigate('/engagement/sequences/builder')}>
              {t('sequences.first_add')}
            </Button>
          }
        />
      ) : (
        <div className="space-y-4">
          {sequences.map((seq) => {
            const enrollments = getEnrollmentsForSequence(seq.id);
            const enrollCount = getEnrollmentCount(seq.id);

            return (
              <Card key={seq.id}>
                <div className="space-y-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-2">
                      <h4 className="text-sm font-semibold text-gray-900">{seq.name}</h4>
                      {seq.description && (
                        <p className="text-sm text-gray-600">{seq.description}</p>
                      )}
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="info" size="sm">
                          {seq.steps.length}
                        </Badge>
                        <Badge variant="default" size="sm">
                          {t('sequences.enroll_count').replace('{count}', String(enrollCount))}
                        </Badge>
                        {hasVariants(seq.steps) && (
                          <Badge variant="warning" size="sm">
                            <FlaskConical size={12} className="mr-1 inline" />
                            {t('sequences.ab_test')}
                          </Badge>
                        )}
                        {hasBranching(seq.steps) && (
                          <Badge variant="info" size="sm">
                            <GitBranch size={12} className="mr-1 inline" />
                            {t('sequences.branching')}
                          </Badge>
                        )}
                        {seq.auto_enroll_rules && (
                          <Badge variant="success" size="sm">
                            {t('sequences.auto_enroll')}
                          </Badge>
                        )}
                        <span className="text-xs text-gray-500">
                          {formatDateTime(seq.created_at)}
                        </span>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => navigate(`/engagement/sequences/${seq.id}/edit`)}
                      >
                        {t('sequences.edit')}
                      </Button>
                      <Button variant="secondary" size="sm" onClick={() => openEnrollModal(seq.id)}>
                        {t('sequences.enroll')}
                      </Button>
                    </div>
                  </div>

                  {/* Enrollments list */}
                  {enrollments.length > 0 && (
                    <div className="border-t border-gray-100 pt-3">
                      <p className="mb-2 text-xs font-medium text-gray-500">
                        {t('sequences.enrollments')}
                      </p>
                      <div className="space-y-2">
                        {enrollments.map((enrollment) => {
                          const sc = STATUS_CONFIG[enrollment.status] || STATUS_CONFIG.active;
                          const StatusIcon = sc.icon;
                          return (
                            <div
                              key={enrollment.id}
                              className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2.5 text-sm"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-mono text-gray-500">#{enrollment.id}</span>
                                {enrollment.opportunity_id && (
                                  <span className="text-xs text-gray-500">
                                    {t('sequences.opp_line').replace(
                                      '{id}',
                                      String(enrollment.opportunity_id),
                                    )}
                                  </span>
                                )}
                                {enrollment.customer_id && (
                                  <span className="text-xs text-gray-500">
                                    {t('sequences.cust_line').replace(
                                      '{id}',
                                      String(enrollment.customer_id),
                                    )}
                                  </span>
                                )}
                                {enrollment.lead_id && (
                                  <span className="text-xs text-gray-500">
                                    {t('sequences.lead_line').replace(
                                      '{id}',
                                      String(enrollment.lead_id),
                                    )}
                                  </span>
                                )}
                                <Badge variant={sc.variant} size="sm">
                                  <StatusIcon size={12} className="mr-1 inline" />
                                  {sc.label}
                                </Badge>
                                <span className="text-xs text-gray-400">
                                  {t('sequences.step_of')
                                    .replace('{step}', String(enrollment.current_step))
                                    .replace('{total}', String(seq.steps.length))}
                                </span>
                                {enrollment.exit_reason && (
                                  <Badge variant="default" size="sm">
                                    {EXIT_LABELS[enrollment.exit_reason] || enrollment.exit_reason}
                                  </Badge>
                                )}
                                {enrollment.completed_at && (
                                  <span className="text-[11px] text-gray-400">
                                    {formatDateTime(enrollment.completed_at)}
                                  </span>
                                )}
                              </div>
                              <div className="flex gap-1">
                                {enrollment.is_paused ? (
                                  <Button
                                    variant="secondary"
                                    size="sm"
                                    loading={resumeMutation.isPending}
                                    onClick={() => resumeMutation.mutate(enrollment.id)}
                                  >
                                    {t('sequences.resume')}
                                  </Button>
                                ) : (
                                  enrollment.status === 'active' && (
                                    <Button
                                      variant="secondary"
                                      size="sm"
                                      loading={pauseMutation.isPending}
                                      onClick={() => pauseMutation.mutate(enrollment.id)}
                                    >
                                      {t('sequences.pause')}
                                    </Button>
                                  )
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Per-sequence performance (manager) */}
      {isManager && (
        <div className="mt-6">
          <Card title={t('cockpit.seq_perf_title')}>
            {perfLoading ? (
              <Skeleton variant="line" count={5} />
            ) : perfRows.length === 0 ? (
              <p className="text-sm text-gray-400">{t('cockpit.seq_perf_empty')}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs text-gray-500">
                      <th className="py-2 pr-3 font-medium">{t('cockpit.seq_perf_col_name')}</th>
                      <th className="py-2 pr-3 font-medium text-right">
                        {t('cockpit.seq_perf_col_total')}
                      </th>
                      <th className="py-2 pr-3 font-medium text-right">
                        {t('cockpit.seq_perf_col_active')}
                      </th>
                      <th className="py-2 pr-3 font-medium text-right">
                        {t('cockpit.seq_perf_col_done')}
                      </th>
                      <th className="py-2 pr-3 font-medium text-right">
                        {t('cockpit.seq_perf_col_exit')}
                      </th>
                      <th className="py-2 font-medium text-right">
                        {t('cockpit.seq_perf_col_avg')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {perfRows.map((row) => (
                      <tr
                        key={String(row.sequence_id)}
                        className="border-b border-gray-50 dark:border-gray-800"
                      >
                        <td className="py-2 pr-3 font-medium text-gray-900 dark:text-white">
                          {String(row.name)}
                          {!row.is_active ? (
                            <span className="ml-2 text-xs font-normal text-gray-400">
                              ({t('opp_detail.inactive')})
                            </span>
                          ) : null}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {Number(row.enrollments_total ?? 0)}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {Number(row.enrollments_active ?? 0)}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {Number(row.enrollments_completed ?? 0)}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {Number(row.enrollments_exited ?? 0)}
                        </td>
                        <td className="py-2 text-right tabular-nums">
                          {Number(row.avg_completed_steps_per_enrollment ?? 0)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* V2 Analytics Summary */}
      {analyticsData && (
        <div className="mt-6">
          <Card title={t('sequences.analytics_v2_title')}>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 mb-4">
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold text-blue-600">
                  {analyticsData.avg_touches_per_target ?? 0}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {t('sequences.analytics_avg_touches')}
                </div>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold text-green-600">
                  {analyticsData.total_step_runs ?? 0}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {t('sequences.analytics_total_step_runs')}
                </div>
              </div>
              {Object.entries(analyticsData.status_distribution || {}).map(([status, count]) => (
                <div key={status} className="rounded-lg border p-3 text-center">
                  <div className="text-2xl font-bold">{count as number}</div>
                  <div className="text-xs text-gray-500 mt-1 capitalize">
                    {STATUS_CONFIG[status]?.label || status}
                  </div>
                </div>
              ))}
            </div>
            {analyticsData.exit_reason_distribution &&
              Object.keys(analyticsData.exit_reason_distribution).length > 0 && (
                <div>
                  <p className="text-xs font-medium text-gray-500 mb-2">
                    {t('sequences.analytics_exit_reason_dist')}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(analyticsData.exit_reason_distribution).map(
                      ([reason, count]) => (
                        <div
                          key={reason}
                          className="flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs"
                        >
                          <span className="font-medium">{EXIT_LABELS[reason] || reason}</span>
                          <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-bold">
                            {count as number}
                          </span>
                        </div>
                      ),
                    )}
                  </div>
                </div>
              )}
          </Card>
        </div>
      )}

      {/* A/B Variant Metrics */}
      {variantData?.variants && variantData.variants.length > 0 && (
        <div className="mt-4">
          <Card title={t('sequences.analytics_ab_perf_title')}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-gray-500">
                    <th className="pb-2 pr-4">{t('sequences.tbl_sequence')}</th>
                    <th className="pb-2 pr-4">{t('sequences.tbl_step')}</th>
                    <th className="pb-2 pr-4">{t('sequences.tbl_variant')}</th>
                    <th className="pb-2 pr-4">{t('sequences.tbl_total')}</th>
                    <th className="pb-2 pr-4">{t('sequences.tbl_completed')}</th>
                    <th className="pb-2">{t('sequences.tbl_failed')}</th>
                  </tr>
                </thead>
                <tbody>
                  {variantData.variants.map((v: Record<string, unknown>, i: number) => (
                    <tr key={i} className="border-b border-gray-50">
                      <td className="py-2 pr-4">#{v.sequence_id as number}</td>
                      <td className="py-2 pr-4">
                        {t('sequences.tbl_step')} {v.step_number as number}
                      </td>
                      <td className="py-2 pr-4">
                        <Badge variant={v.variant_key === 'A' ? 'info' : 'warning'} size="sm">
                          {v.variant_key as string}
                        </Badge>
                      </td>
                      <td className="py-2 pr-4 font-medium">{v.total as number}</td>
                      <td className="py-2 pr-4 text-green-600">{v.completed as number}</td>
                      <td className="py-2 text-red-600">{v.failed as number}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* Enroll Modal */}
      <Modal
        isOpen={isEnrollOpen}
        onClose={() => setIsEnrollOpen(false)}
        title={t('sequences.modal_enroll_title')}
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">{t('sequences.modal_enroll_help')}</p>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              {t('transcripts.lbl_opp_id')}
            </label>
            <Input
              type="number"
              value={enrollForm.opportunity_id}
              onChange={(e) => setEnrollForm((f) => ({ ...f, opportunity_id: e.target.value }))}
              placeholder="Opsiyonel"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              {t('transcripts.lbl_cust_id')}
            </label>
            <Input
              type="number"
              value={enrollForm.customer_id}
              onChange={(e) => setEnrollForm((f) => ({ ...f, customer_id: e.target.value }))}
              placeholder="Opsiyonel"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsEnrollOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button loading={enrollMutation.isPending} onClick={handleEnroll}>
              {t('sequences.enroll')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
