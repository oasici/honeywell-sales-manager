import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
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
          className="font-medium text-honeywell-red hover:underline"
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
        <span className="text-gray-700 dark:text-gray-300">{row.level}</span>
      ),
    },
    {
      key: 'status',
      header: t('approvals.col_status'),
      render: (row: ApprovalRequest) => (
        <Badge variant={STATUS_VARIANT[row.status] || 'default'}>
          {statusLabel[row.status as keyof typeof statusLabel] || row.status}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      header: t('approvals.col_requested'),
      render: (row: ApprovalRequest) => (row.created_at ? formatDateTime(row.created_at) : '-'),
    },
    {
      key: 'actions',
      header: t('approvals.col_actions'),
      render: (row: ApprovalRequest) =>
        row.status === 'pending' ? (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="primary"
              className="!bg-green-600 hover:!bg-green-700"
              onClick={(e) => {
                e.stopPropagation();
                openModal('approve', row.id);
              }}
            >
              {t('approvals.approve')}
            </Button>
            <Button
              size="sm"
              variant="danger"
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

  return (
    <div className="space-y-4">
      <PageHeader title={t('approvals.title')} description={t('approvals.description')} />

      <Card>
        <DataTable
          columns={columns}
          data={items}
          loading={isLoading}
          emptyMessage={t('approvals.empty')}
        />
      </Card>

      {/* Approve / Reject Modal */}
      <Modal
        isOpen={actionModal.isOpen}
        onClose={closeModal}
        title={
          actionModal.type === 'approve'
            ? t('approvals.modal_approve')
            : t('approvals.modal_reject')
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {actionModal.type === 'approve'
              ? t('approvals.confirm_approve')
              : t('approvals.confirm_reject')}
          </p>
          <div>
            <label
              htmlFor="approval-comments"
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              {t('approvals.comments')}
            </label>
            <textarea
              id="approval-comments"
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
                focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light
                dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              rows={3}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder={t('approvals.comments_ph')}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={closeModal} disabled={isSubmitting}>
              {t('common.cancel')}
            </Button>
            <Button
              variant={actionModal.type === 'approve' ? 'primary' : 'danger'}
              className={actionModal.type === 'approve' ? '!bg-green-600 hover:!bg-green-700' : ''}
              onClick={handleSubmit}
              loading={isSubmitting}
            >
              {actionModal.type === 'approve' ? t('approvals.approve') : t('approvals.reject')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
