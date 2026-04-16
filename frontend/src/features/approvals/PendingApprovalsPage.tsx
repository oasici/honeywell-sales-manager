import { useState } from 'react';
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

import type { ApprovalRequest } from '../../lib/types';

const STATUS_VARIANT: Record<string, 'warning' | 'success' | 'danger' | 'default'> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
};

const STATUS_LABEL: Record<string, string> = {
  pending: 'Beklemede',
  approved: 'Onaylandi',
  rejected: 'Reddedildi',
};

const ENTITY_LABEL: Record<string, string> = {
  quote: 'Teklif',
  opportunity: 'Firsat',
};

function entityLink(entityType: string, entityId: number) {
  if (entityType === 'quote') return `/quotes/${entityId}`;
  if (entityType === 'opportunity') return `/opportunities/${entityId}`;
  return '#';
}

export default function PendingApprovalsPage() {
  const queryClient = useQueryClient();
  const [actionModal, setActionModal] = useState<{
    isOpen: boolean;
    type: 'approve' | 'reject';
    requestId: number;
  }>({ isOpen: false, type: 'approve', requestId: 0 });
  const [comments, setComments] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => approvalsApi.getPending(),
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) =>
      approvalsApi.approve(id, comment),
    onSuccess: () => {
      toast.success('Onay basarili');
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      closeModal();
    },
    onError: () => {
      toast.error('Onay islemi basarisiz');
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) =>
      approvalsApi.reject(id, comment),
    onSuccess: () => {
      toast.success('Red islemi tamamlandi');
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      closeModal();
    },
    onError: () => {
      toast.error('Red islemi basarisiz');
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
      header: 'Varlik',
      render: (row: ApprovalRequest) => (
        <Link
          to={entityLink(row.entity_type, row.entity_id)}
          className="font-medium text-honeywell-red hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {ENTITY_LABEL[row.entity_type] || row.entity_type} #{row.entity_id}
        </Link>
      ),
    },
    {
      key: 'level',
      header: 'Seviye',
      render: (row: ApprovalRequest) => (
        <span className="text-gray-700 dark:text-gray-300">{row.level}</span>
      ),
    },
    {
      key: 'status',
      header: 'Durum',
      render: (row: ApprovalRequest) => (
        <Badge variant={STATUS_VARIANT[row.status] || 'default'}>
          {STATUS_LABEL[row.status] || row.status}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      header: 'Talep Tarihi',
      render: (row: ApprovalRequest) =>
        row.created_at ? formatDateTime(row.created_at) : '-',
    },
    {
      key: 'actions',
      header: 'Islemler',
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
              Onayla
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={(e) => {
                e.stopPropagation();
                openModal('reject', row.id);
              }}
            >
              Reddet
            </Button>
          </div>
        ) : null,
    },
  ];

  const items: ApprovalRequest[] = data?.items ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Bekleyen Onaylar"
        description="Onay bekleyen teklif ve firsat talepleri"
      />

      <Card>
        <DataTable
          columns={columns}
          data={items}
          loading={isLoading}
          emptyMessage="Bekleyen onay bulunmuyor"
        />
      </Card>

      {/* Approve / Reject Modal */}
      <Modal
        isOpen={actionModal.isOpen}
        onClose={closeModal}
        title={actionModal.type === 'approve' ? 'Onay' : 'Reddet'}
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {actionModal.type === 'approve'
              ? 'Bu talebi onaylamak istediginizden emin misiniz?'
              : 'Bu talebi reddetmek istediginizden emin misiniz?'}
          </p>
          <div>
            <label
              htmlFor="approval-comments"
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Yorumlar
            </label>
            <textarea
              id="approval-comments"
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
                focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light
                dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              rows={3}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Opsiyonel yorum ekleyin..."
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              onClick={closeModal}
              disabled={isSubmitting}
            >
              Iptal
            </Button>
            <Button
              variant={actionModal.type === 'approve' ? 'primary' : 'danger'}
              className={actionModal.type === 'approve' ? '!bg-green-600 hover:!bg-green-700' : ''}
              onClick={handleSubmit}
              loading={isSubmitting}
            >
              {actionModal.type === 'approve' ? 'Onayla' : 'Reddet'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
