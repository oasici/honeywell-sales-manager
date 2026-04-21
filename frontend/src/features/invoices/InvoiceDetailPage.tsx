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
import { formatCurrency, formatDate } from '../../lib/formatters';
import { Modal } from '../../components/ui/Modal';
import type { Invoice } from '../../lib/types';
import { useT } from '../../hooks/useT';
import { translateInvoiceStatus } from '../../lib/labelTranslations';

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

interface SignatureModalForm {
  signer_email: string;
  signer_name: string;
}

const INITIAL_SIGN_FORM: SignatureModalForm = {
  signer_email: '',
  signer_name: '',
};

export default function InvoiceDetailPage() {
  const t = useT();
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
      toast.success(t('invoices.toast_status_updated'));
      queryClient.invalidateQueries({ queryKey: ['invoice', invoiceId] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
    },
    onError: () => toast.error(t('invoices.toast_status_failed')),
  });

  const signatureMutation = useMutation({
    mutationFn: (payload: {
      document_type: string;
      document_id: number;
      signer_email: string;
      signer_name?: string;
    }) => signaturesApi.request(payload),
    onSuccess: () => {
      toast.success(t('invoices.toast_sign_sent'));
      setIsSignModalOpen(false);
      setSignForm(INITIAL_SIGN_FORM);
    },
    onError: () => toast.error(t('invoices.toast_sign_failed')),
  });

  const handleStatusChange = useCallback(
    (status: string) => {
      statusMutation.mutate(status);
    },
    [statusMutation],
  );

  const handleSignatureRequest = useCallback(() => {
    if (!signForm.signer_email) {
      toast.error(t('invoices.err_signer_email'));
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
        <p className="text-sm text-gray-500">{t('invoices.detail_not_found')}</p>
        <Button variant="secondary" onClick={() => navigate('/invoices')} className="mt-4">
          {t('invoices.detail_back')}
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
        description={t('invoices.detail_desc').replace('{customer}', invoice.customer?.name ?? '')}
      >
        <Badge variant={STATUS_VARIANTS[status] ?? 'default'}>
          {translateInvoiceStatus(status, t)}
        </Badge>

        {/* Status workflow buttons */}
        {status === 'draft' && (
          <>
            <Button onClick={() => handleStatusChange('sent')} loading={statusMutation.isPending}>
              <Send className="mr-1.5 h-4 w-4" />
              {t('invoices.action_send')}
            </Button>
            <Button
              variant="danger"
              onClick={() => handleStatusChange('voided')}
              loading={statusMutation.isPending}
            >
              <Ban className="mr-1.5 h-4 w-4" />
              {t('invoices.action_void')}
            </Button>
          </>
        )}

        {status === 'sent' && (
          <>
            <Button onClick={() => handleStatusChange('paid')} loading={statusMutation.isPending}>
              <CheckCircle className="mr-1.5 h-4 w-4" />
              {t('invoices.action_mark_paid')}
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleStatusChange('overdue')}
              loading={statusMutation.isPending}
            >
              <Clock className="mr-1.5 h-4 w-4" />
              {t('invoices.action_mark_overdue')}
            </Button>
            <Button
              variant="danger"
              onClick={() => handleStatusChange('voided')}
              loading={statusMutation.isPending}
            >
              <Ban className="mr-1.5 h-4 w-4" />
              {t('invoices.action_void')}
            </Button>
          </>
        )}

        {status === 'overdue' && (
          <>
            <Button onClick={() => handleStatusChange('paid')} loading={statusMutation.isPending}>
              <CheckCircle className="mr-1.5 h-4 w-4" />
              {t('invoices.action_mark_paid')}
            </Button>
            <Button
              variant="danger"
              onClick={() => handleStatusChange('voided')}
              loading={statusMutation.isPending}
            >
              <Ban className="mr-1.5 h-4 w-4" />
              {t('invoices.action_void')}
            </Button>
          </>
        )}

        {invoice.status === 'sent' && (
          <Button variant="secondary" onClick={() => setIsSignModalOpen(true)}>
            <PenLine className="mr-1.5 h-4 w-4" />
            {t('invoices.action_request_signature')}
          </Button>
        )}

        <Button variant="secondary" onClick={() => navigate('/invoices')}>
          {t('invoices.detail_back')}
        </Button>
      </PageHeader>

      {/* Invoice Info Card */}
      <Card title={t('invoices.detail_card_info')}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <p className="text-xs text-gray-500">{t('invoices.detail_customer')}</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {invoice.customer?.name ?? `#${invoice.customer_id}`}
            </p>
            {invoice.customer?.company && (
              <p className="text-xs text-gray-400">{invoice.customer.company}</p>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-500">{t('invoices.detail_issue_date')}</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {invoice.issue_date ? formatDate(invoice.issue_date) : '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t('invoices.detail_due_date')}</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {invoice.due_date ? formatDate(invoice.due_date) : '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t('invoices.detail_currency')}</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">{invoice.currency}</p>
          </div>
          {invoice.quote_id && (
            <div>
              <p className="text-xs text-gray-500">{t('invoices.detail_linked_quote')}</p>
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
              <p className="text-xs text-gray-500">{t('invoices.detail_paid_at')}</p>
              <p className="text-sm font-medium text-gray-900 dark:text-white">
                {formatDate(invoice.paid_at)}
              </p>
            </div>
          )}
        </div>
      </Card>

      {/* Line Items */}
      {items.length > 0 && (
        <Card title={t('invoices.detail_card_lines')}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('invoices.detail_col_desc')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                    {t('invoices.detail_col_qty')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                    {t('invoices.detail_col_unit')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                    {t('invoices.detail_col_line_total')}
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
      <Card title={t('invoices.detail_card_totals')}>
        <div className="ml-auto max-w-xs space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">{t('invoices.detail_subtotal')}</span>
            <span className="font-medium text-gray-900 dark:text-white">
              {formatCurrency(invoice.subtotal, invoice.currency)}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">
              {t('invoices.detail_tax').replace('{rate}', String(invoice.tax_rate ?? 0))}
            </span>
            <span className="font-medium text-gray-900 dark:text-white">
              {formatCurrency(invoice.tax_amount, invoice.currency)}
            </span>
          </div>
          <div className="flex justify-between border-t border-gray-200 pt-2 dark:border-gray-700">
            <span className="font-semibold text-gray-900 dark:text-white">
              {t('invoices.detail_grand_total')}
            </span>
            <span className="text-lg font-bold text-honeywell-red">
              {formatCurrency(invoice.grand_total, invoice.currency)}
            </span>
          </div>
        </div>
      </Card>

      {/* Notes */}
      {invoice.notes && (
        <Card title={t('invoices.detail_card_notes')}>
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
        title={t('invoices.detail_modal_sign_title')}
        size="sm"
      >
        <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
          {t('invoices.detail_modal_sign_body').replace('{number}', invoice.invoice_number)}
        </p>
        <div className="space-y-3">
          <Input
            label={t('invoices.detail_signer_email')}
            type="email"
            value={signForm.signer_email}
            onChange={(e) => setSignForm({ ...signForm, signer_email: e.target.value })}
            placeholder={t('invoices.detail_signer_ph')}
          />
          <Input
            label={t('invoices.detail_signer_name')}
            value={signForm.signer_name}
            onChange={(e) => setSignForm({ ...signForm, signer_name: e.target.value })}
            placeholder={t('invoices.detail_signer_name_ph')}
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
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSignatureRequest} loading={signatureMutation.isPending}>
            <PenLine className="mr-1.5 h-4 w-4" />
            {t('invoices.action_send')}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
