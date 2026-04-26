import { useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CheckCircle2, ShieldCheck } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { Skeleton } from '../../components/ui/Skeleton';
import { approvalsApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import { useT } from '../../hooks/useT';

import type { ApprovalRequest } from '../../lib/types';

const STATUS_VARIANT: Record<string, 'warning' | 'success' | 'danger' | 'default'> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
};

function entityLink(entityType: string, entityId: number) {
  if (entityType === 'quote') return `/quotes/${entityId}`;
  if (entityType === 'opportunity') return `/opportunities/${entityId}`;
  return '#';
}

export default function PendingApprovalsPage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [actionModal, setActionModal] = useState<{
    isOpen: boolean;
    type: 'approve' | 'reject';
    requestId: number;
  }>({ isOpen: false, type: 'approve', requestId: 0 });
  const [comments, setComments] = useState('');

  const statusLabel = useMemo(
    () => ({
      pending: t('approvals.status_pending'),
      approved: t('approvals.status_approved'),
      rejected: t('approvals.status_rejected'),
    }),
    [t],
  );

  const entityLabel = useMemo(
    () => ({
      quote: t('approvals.entity_quote'),
      opportunity: t('approvals.entity_opportunity'),
    }),
    [t],
  );

  const { data, isLoading } = useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => approvalsApi.getPending(),
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) =>
      approvalsApi.approve(id, comment),
    onSuccess: () => {
      toast.success(t('approvals.toast_approve_ok'));
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      closeModal();
    },
    onError: () => {
      toast.error(t('approvals.toast_approve_fail'));
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) =>
      approvalsApi.reject(id, comment),
    onSuccess: () => {
      toast.success(t('approvals.toast_reject_ok'));
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      closeModal();
    },
    onError: () => {
      toast.error(t('approvals.toast_reject_fail'));
    },
  });

  function openModal(type: 'approve' | 'reject', requestId: number) {
    setActionModal({ isOpen: true, type, requestId });
    setComments('');
  }

  function closeModal() {
    setActionModal({ isOpen: false, type: 'approve', requestId: 0 });
    setComments('');
  }

  function handleSubmit() {
    const payload = { id: actionModal.requestId, comment: comments };
    if (actionModal.type === 'approve') {
      approveMutation.mutate(payload);
    } else {
      rejectMutation.mutate(payload);
    }
  }

  const isSubmitting = approveMutation.isPending || rejectMutation.isPending;

  const columns = [
    {
      key: 'entity',
      header: t('approvals.col_entity'),
      render: (row: ApprovalRequest) => (
        <Link
          to={entityLink(row.entity_type, row.entity_id)}
          className="text-[13px] font-semibold text-slate-900 transition-colors hover:text-honeywell-red dark:text-white"
          onClick={(e) => e.stopPropagation()}
        >
          {entityLabel[row.entity_type as keyof typeof entityLabel] || row.entity_type} #
          {row.entity_id}
        </Link>
      ),
    },
    {
      key: 'level',
      header: t('approvals.col_level'),
      render: (row: ApprovalRequest) => (
        <Badge variant="default" size="sm">
          {row.level}
        </Badge>
      ),
    },
    {
      key: 'status',
      header: t('approvals.col_status'),
      render: (row: ApprovalRequest) => (
        <Badge variant={STATUS_VARIANT[row.status] || 'default'} size="sm" dot>
          {statusLabel[row.status as keyof typeof statusLabel] || row.status}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      header: t('approvals.col_requested'),
      render: (row: ApprovalRequest) => (
        <span className="whitespace-nowrap text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
          {row.created_at ? formatDateTime(row.created_at) : '—'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right' as const,
      render: (row: ApprovalRequest) =>
        row.status === 'pending' ? (
          <div className="flex items-center justify-end gap-1.5">
            <Button
              size="sm"
              variant="primary"
              onClick={(e) => {
                e.stopPropagation();
                openModal('approve', row.id);
              }}
            >
              {t('approvals.approve')}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={(e) => {
                e.stopPropagation();
                openModal('reject', row.id);
              }}
            >
              {t('approvals.reject')}
            </Button>
          </div>
        ) : null,
    },
  ];

  const items: ApprovalRequest[] = data?.items ?? [];
  const isAllClear = !isLoading && items.length === 0;

  return (
    <div>
      <PageHeader title={t('approvals.title')} description={t('approvals.description')} />

      {isLoading ? (
        <Skeleton variant="table" />
      ) : isAllClear ? (
        // "Her şey tamam" state — emerald medallion + reassuring copy.
        // Secondary CTA points at approval-rule setup so admins don't
        // dead-end here when the queue is empty.
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
            <span className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600 ring-1 ring-inset ring-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:ring-emerald-900/40">
              <CheckCircle2 size={24} />
            </span>
            <h3 className="text-heading-3 text-slate-900 dark:text-white">Her şey tamam</h3>
            <p className="mt-1.5 max-w-[420px] text-[13px] text-slate-500 dark:text-slate-400">
              Bekleyen onay talebi yok. Yeni gelen istekler bu sayfada anında listelenecek.
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
              <Button variant="secondary" onClick={() => navigate('/approvals/rules')}>
                <ShieldCheck size={14} />
                Onay Kurallarını Yönet
              </Button>
              <Button variant="tertiary" onClick={() => navigate('/quotes')}>
                Teklifleri Görüntüle
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={items}
          loading={false}
          emptyMessage={t('approvals.empty')}
        />
      )}

      {/* Approve / Reject Modal */}
      <Modal
        isOpen={actionModal.isOpen}
        onClose={closeModal}
        title={
          actionModal.type === 'approve'
            ? t('approvals.modal_approve')
            : t('approvals.modal_reject')
        }
        size="sm"
        description={
          actionModal.type === 'approve'
            ? t('approvals.confirm_approve')
            : t('approvals.confirm_reject')
        }
        footer={
          <>
            <Button variant="secondary" onClick={closeModal} disabled={isSubmitting}>
              {t('common.cancel')}
            </Button>
            <Button
              variant={actionModal.type === 'approve' ? 'primary' : 'danger'}
              onClick={handleSubmit}
              loading={isSubmitting}
            >
              {actionModal.type === 'approve' ? t('approvals.approve') : t('approvals.reject')}
            </Button>
          </>
        }
      >
        <div>
          <label
            htmlFor="approval-comments"
            className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300"
          >
            {t('approvals.comments')}
          </label>
          <textarea
            id="approval-comments"
            className="block w-full resize-none rounded-[12px] border border-slate-200 bg-white px-3.5 py-2.5 text-[13px] text-slate-900 placeholder:text-slate-400 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-transparent dark:text-slate-100 dark:placeholder:text-slate-500"
            rows={3}
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            placeholder={t('approvals.comments_ph')}
          />
        </div>
      </Modal>
    </div>
  );
}
