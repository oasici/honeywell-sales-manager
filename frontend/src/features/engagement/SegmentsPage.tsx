import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Users } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { engagementApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import type { Segment } from '../../lib/types';

interface SegmentCustomer {
  id: number;
  name: string;
  company: string;
  email: string;
}

interface SegmentCustomersResponse {
  segment_id: number;
  segment_name: string;
  customers: SegmentCustomer[];
}

export default function SegmentsPage() {
  const queryClient = useQueryClient();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [selectedSegmentId, setSelectedSegmentId] = useState<number | null>(null);

  const [form, setForm] = useState({
    name: '',
    description: '',
    rulesJson: '[]',
  });

  const { data, isLoading } = useQuery<{ segments: Segment[] }>({
    queryKey: ['segments'],
    queryFn: () => engagementApi.listSegments(),
  });

  const customersQuery = useQuery<SegmentCustomersResponse>({
    queryKey: ['segment-customers', selectedSegmentId],
    queryFn: () => engagementApi.getSegmentCustomers(selectedSegmentId!),
    enabled: selectedSegmentId !== null,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => engagementApi.createSegment(payload),
    onSuccess: () => {
      toast.success('Segment oluşturuldu');
      queryClient.invalidateQueries({ queryKey: ['segments'] });
      setIsCreateOpen(false);
      resetForm();
    },
    onError: () => toast.error('Segment oluşturulamadı'),
  });

  function resetForm() {
    setForm({ name: '', description: '', rulesJson: '[]' });
  }

  function handleCreate() {
    if (!form.name.trim()) {
      toast.error('Segment adi zorunludur');
      return;
    }
    let rules: unknown[];
    try {
      rules = JSON.parse(form.rulesJson);
    } catch {
      toast.error('Kurallar geçerli JSON formatinda olmali');
      return;
    }
    createMutation.mutate({
      name: form.name,
      ...(form.description && { description: form.description }),
      rules,
    });
  }

  const segments = data?.segments ?? [];

  return (
    <div>
      <PageHeader title="Segmentler" description="Müşteri segmentasyonu ve gruplari">
        <Button onClick={() => setIsCreateOpen(true)}>Yeni Segment</Button>
      </PageHeader>

      {isLoading ? (
        <Skeleton variant="card" count={3} />
      ) : segments.length === 0 ? (
        <EmptyState
          title="Segment bulunamadi"
          description="Henüz segment tanimlanmamis"
          icon={<Users size={40} />}
          action={<Button onClick={() => setIsCreateOpen(true)}>İlk Segmenti Ekle</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {segments.map((segment) => (
            <button
              key={segment.id}
              type="button"
              className="w-full text-left"
              onClick={() => setSelectedSegmentId(segment.id)}
            >
              <Card>
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-gray-900">{segment.name}</h4>
                  {segment.description && (
                    <p className="text-sm text-gray-600 line-clamp-2">{segment.description}</p>
                  )}
                  <div className="flex items-center gap-3">
                    <Badge variant="info" size="sm">
                      {segment.customer_count} müşteri
                    </Badge>
                    <span className="text-xs text-gray-500">
                      {formatDateTime(segment.created_at)}
                    </span>
                  </div>
                </div>
              </Card>
            </button>
          ))}
        </div>
      )}

      {/* Segment Customers Modal */}
      <Modal
        isOpen={selectedSegmentId !== null}
        onClose={() => setSelectedSegmentId(null)}
        title={customersQuery.data?.segment_name ?? 'Segment Musterileri'}
        size="lg"
      >
        {customersQuery.isLoading ? (
          <Skeleton variant="table" />
        ) : !customersQuery.data?.customers?.length ? (
          <EmptyState
            title="Müşteri bulunamadi"
            description="Bu segmentte müşteri yok"
          />
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Ad
                  </th>
                  <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Şirket
                  </th>
                  <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Email
                  </th>
                </tr>
              </thead>
              <tbody>
                {customersQuery.data.customers.map((customer) => (
                  <tr key={customer.id} className="border-b border-gray-100 last:border-b-0">
                    <td className="px-4 py-3 font-medium text-gray-900">{customer.name}</td>
                    <td className="px-4 py-3 text-gray-600">{customer.company || '-'}</td>
                    <td className="px-4 py-3 text-gray-600">{customer.email}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      {/* Create Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Segment"
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Segment Adi</label>
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Örneğin: Yüksek Degerli Müşteriler"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Açıklama</label>
            <Input
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="Segment aciklamasi"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Kurallar (JSON)
            </label>
            <textarea
              className="w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              rows={6}
              value={form.rulesJson}
              onChange={(e) => setForm((f) => ({ ...f, rulesJson: e.target.value }))}
              placeholder='[{"field": "total_quote_value", "operator": "gt", "value": 10000}]'
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
              İptal
            </Button>
            <Button loading={createMutation.isPending} onClick={handleCreate}>
              Oluştur
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
