import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Plus,
  Trash2,
  Webhook,
  ChevronDown,
  ChevronUp,
  PlayCircle,
  ExternalLink,
} from 'lucide-react';

import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { webhooksApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';
import type { WebhookSubscription, WebhookDelivery } from '../../lib/types';

const AVAILABLE_EVENTS: { value: string; labelKey: TranslationKey }[] = [
  { value: 'opportunity.created', labelKey: 'webhooks.event.opportunity_created' },
  { value: 'opportunity.stage_changed', labelKey: 'webhooks.event.opportunity_stage_changed' },
  { value: 'quote.approved', labelKey: 'webhooks.event.quote_approved' },
  { value: 'quote.sent', labelKey: 'webhooks.event.quote_sent' },
  { value: 'lead.converted', labelKey: 'webhooks.event.lead_converted' },
  { value: 'customer.created', labelKey: 'webhooks.event.customer_created' },
  { value: 'email.parsed', labelKey: 'webhooks.event.email_parsed' },
];

const MAX_URL_DISPLAY_LENGTH = 40;

interface WebhookForm {
  name: string;
  url: string;
  event_types: string[];
  secret: string;
}

const INITIAL_FORM: WebhookForm = {
  name: '',
  url: '',
  event_types: [],
  secret: '',
};

function truncateUrl(url: string): string {
  if (url.length <= MAX_URL_DISPLAY_LENGTH) return url;
  return url.slice(0, MAX_URL_DISPLAY_LENGTH) + '...';
}

function StatusCodeBadge({ code }: { code: number }) {
  if (code >= 200 && code < 300) {
    return <Badge variant="success">{code}</Badge>;
  }
  if (code >= 400) {
    return <Badge variant="danger">{code}</Badge>;
  }
  return <Badge variant="warning">{code}</Badge>;
}

function DeliveryHistory({ webhookId }: { webhookId: number }) {
  const t = useT();
  const { data, isLoading } = useQuery<{ data: WebhookDelivery[] }>({
    queryKey: ['webhook-deliveries', webhookId],
    queryFn: () => webhooksApi.getDeliveries(webhookId),
  });

  const deliveries: WebhookDelivery[] =
    data?.data ?? (Array.isArray(data) ? (data as WebhookDelivery[]) : []);

  if (isLoading) {
    return (
      <div className="px-4 py-3">
        <Skeleton variant="line" count={3} />
      </div>
    );
  }

  if (deliveries.length === 0) {
    return (
      <p className="px-4 py-3 text-xs text-slate-400 dark:text-slate-500">
        {t('webhooks.no_deliveries')}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-slate-100 dark:border-slate-800">
            <th className="px-4 py-2 font-semibold text-slate-500 dark:text-slate-400">
              {t('webhooks.table_event')}
            </th>
            <th className="px-4 py-2 font-semibold text-slate-500 dark:text-slate-400">
              {t('webhooks.table_status')}
            </th>
            <th className="px-4 py-2 font-semibold text-slate-500 dark:text-slate-400">
              {t('webhooks.table_date')}
            </th>
          </tr>
        </thead>
        <tbody>
          {deliveries.map((d) => (
            <tr key={d.id} className="border-b border-gray-50 dark:border-slate-800 last:border-0">
              <td className="px-4 py-2 text-slate-700 dark:text-slate-300">{d.event_type}</td>
              <td className="px-4 py-2">
                <StatusCodeBadge code={d.status_code} />
              </td>
              <td className="px-4 py-2 text-slate-500 dark:text-slate-400">
                {d.delivered_at ? formatDateTime(d.delivered_at) : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WebhookCard({
  webhook,
  onDelete,
}: {
  webhook: WebhookSubscription;
  onDelete: () => void;
}) {
  const t = useT();
  const queryClient = useQueryClient();
  const [isExpanded, setIsExpanded] = useState(false);

  const toggleMutation = useMutation({
    mutationFn: () => webhooksApi.update(webhook.id, { is_active: !webhook.is_active }),
    onSuccess: () => {
      toast.success(webhook.is_active ? t('webhooks.toast_disabled') : t('webhooks.toast_enabled'));
      queryClient.invalidateQueries({ queryKey: ['webhooks'] });
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  const testMutation = useMutation({
    mutationFn: () => webhooksApi.test(webhook.id),
    onSuccess: () => {
      toast.success(t('webhooks.toast_test_sent'));
      queryClient.invalidateQueries({
        queryKey: ['webhook-deliveries', webhook.id],
      });
    },
    onError: () => toast.error(t('webhooks.toast_test_failed')),
  });

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-800">
      <div className="flex items-start justify-between p-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-slate-900 dark:text-white truncate">
              {webhook.name}
            </h4>
            {webhook.is_active ? (
              <Badge variant="success" size="sm">
                {t('webhooks.active')}
              </Badge>
            ) : (
              <Badge variant="default" size="sm">
                {t('webhooks.inactive')}
              </Badge>
            )}
          </div>
          <p
            className="mt-1 text-xs text-slate-500 dark:text-slate-400 font-mono truncate"
            title={webhook.url}
          >
            <ExternalLink size={10} className="mr-1 inline" />
            {truncateUrl(webhook.url)}
          </p>
          <div className="mt-2 flex flex-wrap gap-1">
            {webhook.event_types.map((event) => (
              <Badge key={event} variant="info" size="sm">
                {event}
              </Badge>
            ))}
          </div>
          {webhook.failure_count > 0 && (
            <p className="mt-1.5 text-xs text-red-500">
              {webhook.failure_count} {t('webhooks.failure_count_suffix')}
            </p>
          )}
        </div>
        <div className="ml-3 flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => toggleMutation.mutate()}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
              webhook.is_active ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'
            }`}
            title={webhook.is_active ? t('webhooks.toggle_disable') : t('webhooks.toggle_enable')}
          >
            <span
              className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                webhook.is_active ? 'translate-x-4' : 'translate-x-0.5'
              }`}
            />
          </button>
          <button
            type="button"
            onClick={() => testMutation.mutate()}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-blue-50 hover:text-blue-500 transition-colors dark:hover:bg-blue-900/20"
            title={t('common.test')}
          >
            <PlayCircle size={16} />
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors dark:hover:bg-red-900/20"
            title={t('common.delete')}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div className="border-t border-slate-100 dark:border-slate-800">
        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex w-full items-center justify-between px-4 py-2 text-xs font-medium text-slate-500 hover:text-slate-700 transition-colors dark:text-slate-400 dark:hover:text-slate-200"
        >
          {t('webhooks.deliveries')}
          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        {isExpanded && <DeliveryHistory webhookId={webhook.id} />}
      </div>
    </div>
  );
}

export default function WebhookSettings() {
  const t = useT();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<WebhookSubscription | null>(null);
  const [form, setForm] = useState<WebhookForm>(INITIAL_FORM);

  // Round-13 R13-API-1 — list endpoint now emits the canonical envelope
  // (`items`) alongside the legacy `webhooks` alias. Prefer items; fall
  // back through webhooks and the bare-array form for transitional CI.
  const { data, isLoading } = useQuery<{
    items?: WebhookSubscription[];
    webhooks?: WebhookSubscription[];
  }>({
    queryKey: ['webhooks'],
    queryFn: webhooksApi.list,
  });

  const webhooks: WebhookSubscription[] =
    data?.items ??
    data?.webhooks ??
    (Array.isArray(data) ? (data as WebhookSubscription[]) : []);

  const createMutation = useMutation({
    mutationFn: () =>
      webhooksApi.create({
        name: form.name,
        url: form.url,
        event_types: form.event_types,
        secret: form.secret || undefined,
      }),
    onSuccess: () => {
      toast.success(t('webhooks.toast_created'));
      queryClient.invalidateQueries({ queryKey: ['webhooks'] });
      setIsModalOpen(false);
      setForm(INITIAL_FORM);
    },
    onError: () => toast.error(t('webhooks.toast_create_failed')),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => webhooksApi.remove(id),
    onSuccess: () => {
      toast.success(t('webhooks.toast_deleted'));
      queryClient.invalidateQueries({ queryKey: ['webhooks'] });
      setDeleteTarget(null);
    },
    onError: () => toast.error(t('webhooks.toast_delete_failed')),
  });

  const toggleEvent = (eventValue: string) => {
    setForm((prev) => {
      const isSelected = prev.event_types.includes(eventValue);
      return {
        ...prev,
        event_types: isSelected
          ? prev.event_types.filter((e) => e !== eventValue)
          : [...prev.event_types, eventValue],
      };
    });
  };

  if (isLoading) {
    return <Skeleton variant="card" />;
  }

  return (
    <>
      <Card
        title={t('webhooks.title')}
        action={
          <Button size="sm" onClick={() => setIsModalOpen(true)}>
            <Plus size={14} className="mr-1.5" />
            {t('webhooks.new')}
          </Button>
        }
      >
        {webhooks.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-center">
            <Webhook size={32} className="mb-2 text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-slate-500 dark:text-slate-400">{t('webhooks.empty')}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {webhooks.map((wh) => (
              <WebhookCard key={wh.id} webhook={wh} onDelete={() => setDeleteTarget(wh)} />
            ))}
          </div>
        )}
      </Card>

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={t('webhooks.modal_title')}
        size="lg"
      >
        <div className="space-y-4">
          <Input
            label={t('webhooks.name_label')}
            value={form.name}
            onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            placeholder={t('webhooks.name_placeholder')}
          />
          <Input
            label={t('webhooks.url_label')}
            type="url"
            value={form.url}
            onChange={(e) => setForm((prev) => ({ ...prev, url: e.target.value }))}
            placeholder={t('webhooks.url_placeholder')}
          />

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">
              {t('webhooks.event_types')}
            </label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {AVAILABLE_EVENTS.map((event) => (
                <label
                  key={event.value}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm cursor-pointer hover:bg-slate-50 transition-colors dark:border-slate-800 dark:hover:bg-slate-800"
                >
                  <input
                    type="checkbox"
                    checked={form.event_types.includes(event.value)}
                    onChange={() => toggleEvent(event.value)}
                    className="h-4 w-4 rounded border-slate-200 text-honeywell-red focus:ring-honeywell-red"
                  />
                  <span className="text-slate-700 dark:text-slate-300">{t(event.labelKey)}</span>
                </label>
              ))}
            </div>
          </div>

          <Input
            label={t('webhooks.secret_label')}
            value={form.secret}
            onChange={(e) => setForm((prev) => ({ ...prev, secret: e.target.value }))}
            placeholder={t('webhooks.secret_placeholder')}
          />

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => createMutation.mutate()}
              loading={createMutation.isPending}
              disabled={!form.name || !form.url || form.event_types.length === 0}
            >
              {t('common.create')}
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteMutation.mutate(deleteTarget.id);
          }
        }}
        title={t('webhooks.delete_title')}
        message={`${t('webhooks.delete_message_prefix')}"${deleteTarget?.name}"${t('webhooks.delete_message_suffix')}`}
        confirmLabel={t('common.delete')}
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </>
  );
}
