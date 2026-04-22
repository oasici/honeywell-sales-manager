import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CheckCircle2, CloudUpload } from 'lucide-react';

import { Button } from '../../components/ui/Button';
import { erpApi, type ERPConnection } from '../../lib/api';

interface Props {
  quoteId: number;
  disabled?: boolean;
}

/**
 * Shown on approved/accepted quotes. Lets the user pick an active ERP
 * connection (Paraşüt / Logo / SAP B1) and push the quote as an invoice.
 */
export function ERPInvoicePushButton({ quoteId, disabled }: Props) {
  const [pickerOpen, setPickerOpen] = useState(false);

  const connectionsQuery = useQuery({
    queryKey: ['erp', 'connections'],
    queryFn: () => erpApi.listConnections(),
    enabled: pickerOpen,
  });

  const pushMutation = useMutation({
    mutationFn: (connectionId: number) => erpApi.pushInvoice(quoteId, connectionId),
    onSuccess: (result) => {
      if (result.already_pushed) {
        toast.info(`Fatura zaten oluşturulmuş: ${result.external_id}`);
      } else {
        toast.success(`ERP faturası oluşturuldu: ${result.external_id}`);
      }
      setPickerOpen(false);
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : 'ERP faturası oluşturulamadı';
      toast.error(message);
    },
  });

  const activeConnections = (connectionsQuery.data ?? []).filter(
    (conn) => conn.is_active && ['parasut', 'logo', 'sap_b1'].includes(conn.type),
  );

  if (!pickerOpen) {
    return (
      <Button
        variant="secondary"
        onClick={() => setPickerOpen(true)}
        disabled={disabled}
        className="!bg-indigo-600 !text-white hover:!bg-indigo-700"
      >
        <CloudUpload className="w-4 h-4 mr-1.5" />
        ERP'ye Fatura Gönder
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-2 bg-white dark:bg-gray-900 border border-indigo-200 dark:border-indigo-800 rounded-md px-2 py-1 shadow-sm">
      {connectionsQuery.isLoading && (
        <span className="text-xs text-gray-500">Yükleniyor…</span>
      )}
      {!connectionsQuery.isLoading && activeConnections.length === 0 && (
        <span className="text-xs text-amber-600">Aktif ERP bağlantısı yok</span>
      )}
      {activeConnections.map((conn: ERPConnection) => (
        <button
          key={conn.id}
          type="button"
          onClick={() => pushMutation.mutate(conn.id)}
          disabled={pushMutation.isPending}
          className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md border border-indigo-200 dark:border-indigo-800 hover:bg-indigo-50 dark:hover:bg-indigo-900/40"
        >
          <CheckCircle2 className="w-3.5 h-3.5 text-indigo-500" />
          {conn.type.toUpperCase()}: {conn.name}
        </button>
      ))}
      <button
        type="button"
        onClick={() => setPickerOpen(false)}
        className="text-xs text-gray-500 hover:text-gray-700 ml-1"
      >
        İptal
      </button>
    </div>
  );
}
