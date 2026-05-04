import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { activitiesApi } from '../../lib/api';
import { onActivityLogged } from '../../lib/cacheInvalidation';
import { Modal } from '../../components/ui/Modal';
import { Button } from '../../components/ui/Button';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';

interface QuickActivityModalProps {
  isOpen: boolean;
  onClose: () => void;
  opportunityId?: number;
  customerId?: number;
}

type ActivityTab = 'call' | 'meeting' | 'note';

const TAB_DEFS: { key: ActivityTab; labelKey: TranslationKey }[] = [
  { key: 'call', labelKey: 'activity.tab_call' },
  { key: 'meeting', labelKey: 'activity.tab_meeting' },
  { key: 'note', labelKey: 'activity.tab_note' },
];

const CALL_OUTCOMES: { value: string; labelKey: TranslationKey }[] = [
  { value: 'baglandi', labelKey: 'activity.call_connected' },
  { value: 'mesaj_birakti', labelKey: 'activity.call_left_message' },
  { value: 'cevap_yok', labelKey: 'activity.call_no_answer' },
];

const MEETING_OUTCOMES: { value: string; labelKey: TranslationKey }[] = [
  { value: 'tamamlandi', labelKey: 'activity.meeting_completed' },
  { value: 'ertelendi', labelKey: 'activity.meeting_postponed' },
  { value: 'iptal', labelKey: 'activity.meeting_cancelled' },
];

const INITIAL_FORM = {
  summary: '',
  duration_minutes: '',
  outcome: '',
  attendees: '',
  agenda: '',
};

export default function QuickActivityModal({
  isOpen,
  onClose,
  opportunityId,
  customerId,
}: QuickActivityModalProps) {
  const t = useT();
  const [activeTab, setActiveTab] = useState<ActivityTab>('call');
  const [form, setForm] = useState(INITIAL_FORM);

  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => activitiesApi.log(payload),
    onSuccess: () => {
      toast.success(t('activity.toast_saved'));
      // R4-CACHE-112 — activity propagates to customer.last_activity_at,
      // opportunity rotting counters, and revenue_signal stream.
      onActivityLogged(queryClient, opportunityId ?? null, customerId ?? null);
      handleClose();
    },
    onError: () => {
      toast.error(t('activity.toast_save_failed'));
    },
  });

  function handleClose() {
    setForm(INITIAL_FORM);
    setActiveTab('call');
    onClose();
  }

  function handleSubmit() {
    if (!form.summary.trim()) return;

    const payload: Record<string, unknown> = {
      activity_type: activeTab,
      summary: form.summary.trim(),
      opportunity_id: opportunityId || null,
      customer_id: customerId || null,
    };

    if (activeTab === 'call' || activeTab === 'meeting') {
      if (form.duration_minutes) {
        payload.duration_minutes = Number(form.duration_minutes);
      }
      if (form.outcome) {
        payload.outcome = form.outcome;
      }
    }

    if (activeTab === 'meeting') {
      if (form.attendees.trim()) {
        payload.attendees_json = JSON.stringify(
          form.attendees
            .split(',')
            .map((n) => n.trim())
            .filter(Boolean),
        );
      }
      if (form.agenda.trim()) {
        payload.agenda = form.agenda.trim();
      }
    }

    mutation.mutate(payload);
  }

  function updateField(field: string, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  const inputClass =
    'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-honeywell-red/30';

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={t('activity.title')} size="md">
      {/* Tab selector */}
      <div className="mb-4 flex gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
        {TAB_DEFS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => {
              setActiveTab(tab.key);
              setForm(INITIAL_FORM);
            }}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-white'
                : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        {/* Summary — shared by all types */}
        <div>
          <label
            htmlFor="activity-summary"
            className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400"
          >
            {t('activity.summary')}
          </label>
          <textarea
            id="activity-summary"
            rows={3}
            value={form.summary}
            onChange={(e) => updateField('summary', e.target.value)}
            className={inputClass}
            placeholder={t('activity.summary_placeholder')}
          />
        </div>

        {/* Call fields */}
        {activeTab === 'call' && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label
                  htmlFor="call-duration"
                  className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400"
                >
                  {t('activity.duration_min')}
                </label>
                <input
                  id="call-duration"
                  type="number"
                  min={0}
                  value={form.duration_minutes}
                  onChange={(e) => updateField('duration_minutes', e.target.value)}
                  className={inputClass}
                  placeholder="0"
                />
              </div>
              <div>
                <label
                  htmlFor="call-outcome"
                  className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400"
                >
                  {t('activity.outcome')}
                </label>
                <select
                  id="call-outcome"
                  value={form.outcome}
                  onChange={(e) => updateField('outcome', e.target.value)}
                  className={inputClass}
                >
                  <option value="">{t('activity.select')}</option>
                  {CALL_OUTCOMES.map((o) => (
                    <option key={o.value} value={o.value}>
                      {t(o.labelKey)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </>
        )}

        {/* Meeting fields */}
        {activeTab === 'meeting' && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label
                  htmlFor="meeting-duration"
                  className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400"
                >
                  {t('activity.duration_min')}
                </label>
                <input
                  id="meeting-duration"
                  type="number"
                  min={0}
                  value={form.duration_minutes}
                  onChange={(e) => updateField('duration_minutes', e.target.value)}
                  className={inputClass}
                  placeholder="0"
                />
              </div>
              <div>
                <label
                  htmlFor="meeting-outcome"
                  className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400"
                >
                  {t('activity.outcome')}
                </label>
                <select
                  id="meeting-outcome"
                  value={form.outcome}
                  onChange={(e) => updateField('outcome', e.target.value)}
                  className={inputClass}
                >
                  <option value="">{t('activity.select')}</option>
                  {MEETING_OUTCOMES.map((o) => (
                    <option key={o.value} value={o.value}>
                      {t(o.labelKey)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label
                htmlFor="meeting-attendees"
                className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400"
              >
                {t('activity.attendees')}
              </label>
              <input
                id="meeting-attendees"
                type="text"
                value={form.attendees}
                onChange={(e) => updateField('attendees', e.target.value)}
                className={inputClass}
                placeholder={t('activity.attendees_placeholder')}
              />
            </div>
            <div>
              <label
                htmlFor="meeting-agenda"
                className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400"
              >
                {t('activity.agenda')}
              </label>
              <textarea
                id="meeting-agenda"
                rows={2}
                value={form.agenda}
                onChange={(e) => updateField('agenda', e.target.value)}
                className={inputClass}
                placeholder={t('activity.agenda_placeholder')}
              />
            </div>
          </>
        )}

        {/* Note has no extra fields — just summary above */}
      </div>

      {/* Actions */}
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={handleClose}>
          {t('common.cancel')}
        </Button>
        <Button
          size="sm"
          disabled={!form.summary.trim()}
          loading={mutation.isPending}
          onClick={handleSubmit}
        >
          {t('common.save')}
        </Button>
      </div>
    </Modal>
  );
}
