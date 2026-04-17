import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Send, CheckCircle, Clock, Ban, PenLine } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Input } from '../../components/ui/Input';
import { Skeleton } from '../../components/ui/Skeleton';
import { invoicesApi, signaturesApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import { Modal } from '../../components/ui/Modal';
import type { Invoice } from '../../lib/types';

const STATUS_LABELS: Record<string, string> = {
  draft: 'Taslak',
  sent: 'Gönderildi',
  paid: 'Ödendi',
  overdue: 'Gecikti',
  voided: 'İptal',
};

const STATUS_VARIANTS: Record<string, 'default' | 'info' | 'warning' | 'success' | 'danger'> = {
  draft: 'default',
  sent: 'info',
  paid: 'success',
  overdue: 'danger',
  voided: 'default',
};

interface LineItem {
  description?: string;
  quantity?: number;
  unit_price?: number;
  line_total?: number;
}

function parseItems(itemsJson?: string): LineItem[] {
  if (!itemsJson) return [];
  try {
    return JSON.parse(itemsJson) as LineItem[];
  } catch {
    return [];
  }
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('tr-TR');
}

interface SignatureModalForm {
  signer_email: string;
  signer_name: string;
}

const INITIAL_SIGN_FORM: SignatureModalForm = {
  signer_email: '',
  signer_name: '',
};

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const invoiceId = Number(id);

  const [isSignModalOpen, setIsSignModalOpen] = useState(false);
  const [signForm, setSignForm] = useState<SignatureModalForm>(INITIAL_SIGN_FORM);

  const { data: invoice, isLoading } = useQuery<Invoice>({
    queryKey: ['invoice', invoiceId],
    queryFn: () => invoicesApi.get(invoiceId),
    enabled: !!invoiceId,
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => invoicesApi.updateStatus(invoiceId, status),
    onSuccess: () => {
      toast.success('Durum guncellendi');
      queryClient.invalidateQueries({ queryKey: ['invoice', invoiceId] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
    },
    onError: () => toast.error('Durum guncellenemedi'),
  });

  const signatureMutation = useMutation({
    mutationFn: (payload: {
      document_type: string;
      document_id: number;
      signer_email: string;
      signer_name?: string;
    }) => signaturesApi.request(payload),
    onSuccess: () => {
      toast.success('Imza istegi gönderildi');
      setIsSignModalOpen(false);
      setSignForm(INITIAL_SIGN_FORM);
    },
    onError: () => toast.error('Imza istegi gonderilemedi'),
  });

  const handleStatusChange = useCallback(
    (status: string) => {
      statusMutation.mutate(status);
    },
    [statusMutation],
  );

  const handleSignatureRequest = useCallback(() => {
    if (!signForm.signer_email) {
      toast.error('E-posta adresi zorunludur');
      return;
    }
    signatureMutation.mutate({
      document_type: 'invoice',
      document_id: invoiceId,
      signer_email: signForm.signer_email,
      signer_name: signForm.signer_name || undefined,
    });
  }, [signForm, invoiceId, signatureMutation]);

  if (isLoading) {
    return <Skeleton variant="card" count={4} />;
  }

  if (!invoice) {
    return (
      <div className="py-16 text-center">
        <p className="text-sm text-gray-500">Fatura bulunamadi</p>
        <Button variant="secondary" onClick={() => navigate('/invoices')} className="mt-4">
          Geri Don
        </Button>
      </div>
    );
  }

  const items = parseItems(invoice.items_json);
  const status = invoice.status;

  return (
    <div className="space-y-6">
      <PageHeader
        title={invoice.invoice_number}
        description={`Fatura detaylari — ${invoice.customer?.name ?? ''}`}
      >
        <Badge variant={STATUS_VARIANTS[status] ?? 'default'}>
          {STATUS_LABELS[status] ?? status}
        </Badge>

        {/* Status workflow buttons */}
        {status === 'draft' && (
          <>
            <Button onClick={() => handleStatusChange('sent')} loading={statusMutation.isPending}>
              <Send className="mr-1.5 h-4 w-4" />
              Gönder
            </Button>
            <Button
              variant="danger"
              onClick={() => handleStatusChange('voided')}
              loading={statusMutation.isPending}
            >
              <Ban className="mr-1.5 h-4 w-4" />
              İptal Et
            </Button>
          </>
        )}

        {status === 'sent' && (
          <>
            <Button onClick={() => handleStatusChange('paid')} loading={statusMutation.isPending}>
              <CheckCircle className="mr-1.5 h-4 w-4" />
              Ödendi
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleStatusChange('overdue')}
              loading={statusMutation.isPending}
            >
              <Clock className="mr-1.5 h-4 w-4" />
              Gecikti
            </Button>
            <Button
              variant="danger"
              onClick={() => handleStatusChange('voided')}
              loading={statusMutation.isPending}
            >
              <Ban className="mr-1.5 h-4 w-4" />
              İptal Et
            </Button>
          </>
        )}

        {status === 'overdue' && (
          <>
            <Button onClick={() => handleStatusChange('paid')} loading={statusMutation.isPending}>
              <CheckCircle className="mr-1.5 h-4 w-4" />
              Ödendi
            </Button>
            <Button
              variant="danger"
              onClick={() => handleStatusChange('voided')}
              loading={statusMutation.isPending}
            >
              <Ban className="mr-1.5 h-4 w-4" />
              İptal Et
            </Button>
          </>
        )}

        {invoice.status === 'sent' && (
          <Button variant="secondary" onClick={() => setIsSignModalOpen(true)}>
            <PenLine className="mr-1.5 h-4 w-4" />
            Imza Iste
          </Button>
        )}

        <Button variant="secondary" onClick={() => navigate('/invoices')}>
          Geri Don
        </Button>
      </PageHeader>

      {/* Invoice Info Card */}
      <Card title="Fatura Bilgileri">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <p className="text-xs text-gray-500">Müşteri</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {invoice.customer?.name ?? `#${invoice.customer_id}`}
            </p>
            {invoice.customer?.company && (
              <p className="text-xs text-gray-400">{invoice.customer.company}</p>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-500">Düzenleme Tarihi</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {formatDate(invoice.issue_date)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Vade Tarihi</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {formatDate(invoice.due_date)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Para Birimi</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">{invoice.currency}</p>
          </div>
          {invoice.quote_id && (
            <div>
              <p className="text-xs text-gray-500">Bagli Teklif</p>
              <button
                type="button"
                onClick={() => navigate(`/quotes/${invoice.quote_id}`)}
                className="text-sm font-medium text-honeywell-red hover:underline"
              >
                #{invoice.quote_id}
              </button>
            </div>
          )}
          {invoice.paid_at && (
            <div>
              <p className="text-xs text-gray-500">Ödeme Tarihi</p>
              <p className="text-sm font-medium text-gray-900 dark:text-white">
                {formatDate(invoice.paid_at)}
              </p>
            </div>
          )}
        </div>
      </Card>

      {/* Line Items */}
      {items.length > 0 && (
        <Card title="Kalemler">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Açıklama</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">Adet</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                    Birim Fiyat
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                    Toplam
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, idx) => (
                  <tr key={idx} className="border-b border-gray-100 dark:border-gray-700">
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                      {item.description ?? '-'}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-400">
                      {item.quantity ?? '-'}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-400">
                      {item.unit_price != null
                        ? formatCurrency(item.unit_price, invoice.currency)
                        : '-'}
                    </td>
                    <td className="px-3 py-2 text-right font-medium text-gray-900 dark:text-white">
                      {item.line_total != null
                        ? formatCurrency(item.line_total, invoice.currency)
                        : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Totals */}
      <Card title="Tutar Özeti">
        <div className="ml-auto max-w-xs space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">Ara Toplam</span>
            <span className="font-medium text-gray-900 dark:text-white">
              {formatCurrency(invoice.subtotal, invoice.currency)}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">KDV ({invoice.tax_rate}%)</span>
            <span className="font-medium text-gray-900 dark:text-white">
              {formatCurrency(invoice.tax_amount, invoice.currency)}
            </span>
          </div>
          <div className="flex justify-between border-t border-gray-200 pt-2 dark:border-gray-700">
            <span className="font-semibold text-gray-900 dark:text-white">Genel Toplam</span>
            <span className="text-lg font-bold text-honeywell-red">
              {formatCurrency(invoice.grand_total, invoice.currency)}
            </span>
          </div>
        </div>
      </Card>

      {/* Notes */}
      {invoice.notes && (
        <Card title="Notlar">
          <p className="text-sm text-gray-700 dark:text-gray-300">{invoice.notes}</p>
        </Card>
      )}

      {/* Signature Request Modal */}
      <Modal
        isOpen={isSignModalOpen}
        onClose={() => {
          setIsSignModalOpen(false);
          setSignForm(INITIAL_SIGN_FORM);
        }}
        title="Imza Istegi Gönder"
        size="sm"
      >
        <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
          Fatura <strong>{invoice.invoice_number}</strong> için imza istegi e-posta ile
          gonderilecektir.
        </p>
        <div className="space-y-3">
          <Input
            label="Imzalayan E-posta"
            type="email"
            value={signForm.signer_email}
            onChange={(e) => setSignForm({ ...signForm, signer_email: e.target.value })}
            placeholder="örnek@firma.com"
          />
          <Input
            label="Imzalayan Adi (isteğe bagli)"
            value={signForm.signer_name}
            onChange={(e) => setSignForm({ ...signForm, signer_name: e.target.value })}
            placeholder="Ad Soyad"
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setIsSignModalOpen(false);
              setSignForm(INITIAL_SIGN_FORM);
            }}
          >
            İptal
          </Button>
          <Button onClick={handleSignatureRequest} loading={signatureMutation.isPending}>
            <PenLine className="mr-1.5 h-4 w-4" />
            Gönder
          </Button>
        </div>
      </Modal>
    </div>
  );
}
