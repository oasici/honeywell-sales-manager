import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { activitiesApi } from '../../lib/api';
import { Modal } from '../../components/ui/Modal';
import { Button } from '../../components/ui/Button';

interface QuickActivityModalProps {
  isOpen: boolean;
  onClose: () => void;
  opportunityId?: number;
  customerId?: number;
}

type ActivityTab = 'call' | 'meeting' | 'note';

const TABS: { key: ActivityTab; label: string }[] = [
  { key: 'call', label: 'Arama' },
  { key: 'meeting', label: 'Toplanti' },
  { key: 'note', label: 'Not' },
];

const CALL_OUTCOMES = [
  { value: 'baglandi', label: 'Baglandi' },
  { value: 'mesaj_birakti', label: 'Mesaj Birakti' },
  { value: 'cevap_yok', label: 'Cevap Yok' },
];

const MEETING_OUTCOMES = [
  { value: 'tamamlandi', label: 'Tamamlandi' },
  { value: 'ertelendi', label: 'Ertelendi' },
  { value: 'iptal', label: 'İptal' },
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
  const [activeTab, setActiveTab] = useState<ActivityTab>('call');
  const [form, setForm] = useState(INITIAL_FORM);

  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => activitiesApi.log(payload),
    onSuccess: () => {
      toast.success('Aktivite kaydedildi');
      queryClient.invalidateQueries({ queryKey: ['activities'] });
      if (opportunityId) {
        queryClient.invalidateQueries({ queryKey: ['opportunity-timeline', opportunityId] });
      }
      handleClose();
    },
    onError: () => {
      toast.error('Aktivite kaydedilemedi');
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
          form.attendees.split(',').map((n) => n.trim()).filter(Boolean),
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
    'w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-honeywell-red/30';

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Yeni Aktivite" size="md">
      {/* Tab selector */}
      <div className="mb-4 flex gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => {
              setActiveTab(tab.key);
              setForm(INITIAL_FORM);
            }}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        {/* Summary — shared by all types */}
        <div>
          <label htmlFor="activity-summary" className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
            Özet
          </label>
          <textarea
            id="activity-summary"
            rows={3}
            value={form.summary}
            onChange={(e) => updateField('summary', e.target.value)}
            className={inputClass}
            placeholder="Aktivite ozetini yazin..."
          />
        </div>

        {/* Call fields */}
        {activeTab === 'call' && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="call-duration" className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                  Süre (dk)
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
                <label htmlFor="call-outcome" className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                  Sonuç
                </label>
                <select
                  id="call-outcome"
                  value={form.outcome}
                  onChange={(e) => updateField('outcome', e.target.value)}
                  className={inputClass}
                >
                  <option value="">Seçiniz</option>
                  {CALL_OUTCOMES.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
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
                <label htmlFor="meeting-duration" className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                  Süre (dk)
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
                <label htmlFor="meeting-outcome" className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                  Sonuç
                </label>
                <select
                  id="meeting-outcome"
                  value={form.outcome}
                  onChange={(e) => updateField('outcome', e.target.value)}
                  className={inputClass}
                >
                  <option value="">Seçiniz</option>
                  {MEETING_OUTCOMES.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label htmlFor="meeting-attendees" className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                Katilimcilar (virgul ile ayirin)
              </label>
              <input
                id="meeting-attendees"
                type="text"
                value={form.attendees}
                onChange={(e) => updateField('attendees', e.target.value)}
                className={inputClass}
                placeholder="Ahmet Yilmaz, Mehmet Demir"
              />
            </div>
            <div>
              <label htmlFor="meeting-agenda" className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                Gundem
              </label>
              <textarea
                id="meeting-agenda"
                rows={2}
                value={form.agenda}
                onChange={(e) => updateField('agenda', e.target.value)}
                className={inputClass}
                placeholder="Toplanti gundemi..."
              />
            </div>
          </>
        )}

        {/* Note has no extra fields — just summary above */}
      </div>

      {/* Actions */}
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={handleClose}>
          İptal
        </Button>
        <Button
          size="sm"
          disabled={!form.summary.trim()}
          loading={mutation.isPending}
          onClick={handleSubmit}
        >
          Kaydet
        </Button>
      </div>
    </Modal>
  );
}
