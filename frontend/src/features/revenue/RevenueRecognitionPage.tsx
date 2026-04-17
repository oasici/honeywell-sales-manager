import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { TrendingUp, ChevronDown, ChevronRight, Plus, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Skeleton } from '../../components/ui/Skeleton';
import { revenueRecApi, contractsApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import type { RevenueSchedule, RevenueScheduleEntry, Contract } from '../../lib/types';

const RECOGNITION_TYPES = [
  { value: 'straight_line', label: 'Duz Hat (Straight Line)' },
  { value: 'milestone', label: 'Kilometre Tasi (Milestone)' },
  { value: 'percentage_completion', label: 'Tamamlanma Yuzdesi' },
  { value: 'point_in_time', label: 'Anlık (Point in Time)' },
];

const ENTRY_STATUS_VARIANTS: Record<string, 'warning' | 'success' | 'info' | 'default'> = {
  pending: 'warning',
  recognized: 'success',
  adjusted: 'info',
};

const ENTRY_STATUS_LABELS: Record<string, string> = {
  pending: 'Bekliyor',
  recognized: 'Tanindi',
  adjusted: 'Duzeltildi',
};

interface RevenueDashboard {
  total_scheduled: number;
  total_recognized: number;
  this_month_pending: number;
  recognition_rate_pct: number;
}

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
      <div
        className="h-full bg-honeywell-red rounded-full transition-all"
        style={{ width: `${pct}%` }}
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      />
    </div>
  );
}

function KpiCard({
  label,
  value,
  suffix,
}: {
  label: string;
  value: string | number;
  suffix?: string;
}) {
  return (
    <Card className="p-5">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">
        {value}
        {suffix && <span className="ml-1 text-base font-medium text-gray-500">{suffix}</span>}
      </p>
    </Card>
  );
}

function EntryRow({
  entry,
  scheduleId,
  onRecognize,
  isRecognizing,
}: {
  entry: RevenueScheduleEntry;
  scheduleId: number;
  onRecognize: (scheduleId: number, entryId: number) => void;
  isRecognizing: boolean;
}) {
  return (
    <tr className="border-t border-gray-100 dark:border-gray-700">
      <td className="py-2 px-4 text-sm text-gray-700 dark:text-gray-300">{entry.period}</td>
      <td className="py-2 px-4 text-sm text-right text-gray-700 dark:text-gray-300">
        {formatCurrency(entry.amount)}
      </td>
      <td className="py-2 px-4 text-sm text-right text-gray-700 dark:text-gray-300">
        {formatCurrency(entry.recognized_amount)}
      </td>
      <td className="py-2 px-4 text-sm">
        <Badge variant={ENTRY_STATUS_VARIANTS[entry.status] ?? 'default'}>
          {ENTRY_STATUS_LABELS[entry.status] ?? entry.status}
        </Badge>
      </td>
      <td className="py-2 px-4 text-sm text-right">
        {entry.status === 'pending' && (
          <button
            onClick={() => onRecognize(scheduleId, entry.id)}
            disabled={isRecognizing}
            className="rounded-md px-2.5 py-1 text-xs font-medium bg-honeywell-red/10 text-honeywell-red hover:bg-honeywell-red/20 disabled:opacity-50 transition-colors cursor-pointer"
          >
            Tani
          </button>
        )}
      </td>
    </tr>
  );
}

function ScheduleCard({
  schedule,
  onRecognizeEntry,
  isRecognizing,
  onGenerateEntries,
  isGenerating,
}: {
  schedule: RevenueSchedule;
  onRecognizeEntry: (scheduleId: number, entryId: number) => void;
  isRecognizing: boolean;
  onGenerateEntries: (scheduleId: number) => void;
  isGenerating: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const pct =
    schedule.total_amount > 0
      ? Math.round((schedule.recognized_amount / schedule.total_amount) * 100)
      : 0;

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start justify-between p-4 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors cursor-pointer"
        aria-expanded={expanded}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-900 dark:text-white truncate">
              {schedule.contract?.title ?? `Kontrat #${schedule.contract_id}`}
            </span>
            <span className="text-xs rounded-full px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
              {RECOGNITION_TYPES.find((r) => r.value === schedule.recognition_type)?.label ??
                schedule.recognition_type}
            </span>
          </div>
          <div className="mt-2 flex items-center gap-4 text-sm text-gray-500 flex-wrap">
            <span>
              {formatCurrency(schedule.recognized_amount, schedule.currency)} /{' '}
              {formatCurrency(schedule.total_amount, schedule.currency)}
            </span>
            <span>{pct}% tamamlandi</span>
            <span>
              {schedule.start_date} - {schedule.end_date}
            </span>
          </div>
          <div className="mt-2 w-full max-w-xs">
            <ProgressBar value={schedule.recognized_amount} max={schedule.total_amount} />
          </div>
        </div>
        <div className="ml-4 shrink-0 text-gray-400">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 dark:border-gray-700">
          {schedule.entries && schedule.entries.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-800/50">
                    <th className="py-2 px-4 text-left text-xs font-semibold text-gray-500 uppercase">
                      Donem
                    </th>
                    <th className="py-2 px-4 text-right text-xs font-semibold text-gray-500 uppercase">
                      Tutar
                    </th>
                    <th className="py-2 px-4 text-right text-xs font-semibold text-gray-500 uppercase">
                      Tanınan
                    </th>
                    <th className="py-2 px-4 text-left text-xs font-semibold text-gray-500 uppercase">
                      Durum
                    </th>
                    <th className="py-2 px-4 text-right text-xs font-semibold text-gray-500 uppercase">
                      İşlem
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {schedule.entries.map((entry) => (
                    <EntryRow
                      key={entry.id}
                      entry={entry}
                      scheduleId={schedule.id}
                      onRecognize={onRecognizeEntry}
                      isRecognizing={isRecognizing}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-6 text-center">
              <p className="text-sm text-gray-500 mb-3">
                Kayıt yok. Kayıtları olusturmak için butona basin.
              </p>
              <Button onClick={() => onGenerateEntries(schedule.id)} loading={isGenerating}>
                Kayıtları Oluştur
              </Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

interface CreateScheduleFormState {
  contractId: string;
  recognitionType: string;
  startDate: string;
  endDate: string;
  totalAmount: string;
  currency: string;
}

interface FormErrors {
  endDate?: string;
  totalAmount?: string;
}

const EMPTY_FORM: CreateScheduleFormState = {
  contractId: '',
  recognitionType: 'straight_line',
  startDate: '',
  endDate: '',
  totalAmount: '',
  currency: 'USD',
};

export default function RevenueRecognitionPage() {
  const queryClient = useQueryClient();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [form, setForm] = useState<CreateScheduleFormState>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<FormErrors>({});
  const [newScheduleId, setNewScheduleId] = useState<number | null>(null);

  const {
    data: dashboard,
    isLoading: isDashboardLoading,
    isError: isDashboardError,
  } = useQuery<RevenueDashboard>({
    queryKey: ['revenue-dashboard'],
    queryFn: () => revenueRecApi.getDashboard(),
  });

  const {
    data: schedulesData,
    isLoading: isSchedulesLoading,
    isError: isSchedulesError,
  } = useQuery<RevenueSchedule[]>({
    queryKey: ['revenue-schedules'],
    queryFn: async () => {
      const res = await revenueRecApi.listSchedules();
      return res?.schedules ?? res?.items ?? (Array.isArray(res) ? res : []);
    },
  });

  const { data: contractsData } = useQuery<{ items: Contract[] }>({
    queryKey: ['contracts-simple'],
    queryFn: () => contractsApi.list({ limit: 200 }),
    enabled: isCreateOpen,
  });

  function validateForm(): boolean {
    const errors: FormErrors = {};
    if (form.startDate && form.endDate && form.endDate <= form.startDate) {
      errors.endDate = 'Bitis tarihi baslangic tarihinden sonra olmalidir';
    }
    const amount = Number(form.totalAmount);
    if (form.totalAmount !== '' && (isNaN(amount) || amount <= 0)) {
      errors.totalAmount = "Toplam tutar 0'dan buyuk olmalidir";
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  }

  const createMutation = useMutation({
    mutationFn: () =>
      revenueRecApi.createSchedule({
        contract_id: Number(form.contractId),
        recognition_type: form.recognitionType,
        start_date: form.startDate,
        end_date: form.endDate,
        total_amount: Number(form.totalAmount),
        currency: form.currency,
      }),
    onSuccess: (created: RevenueSchedule) => {
      toast.success('Takvim oluşturuldu');
      setIsCreateOpen(false);
      setForm(EMPTY_FORM);
      setFormErrors({});
      setNewScheduleId(created.id);
      queryClient.invalidateQueries({ queryKey: ['revenue-schedules'] });
      queryClient.invalidateQueries({ queryKey: ['revenue-dashboard'] });
    },
    onError: () => toast.error('Takvim oluşturulamadı'),
  });

  const generateMutation = useMutation({
    mutationFn: (scheduleId: number) => revenueRecApi.generateEntries(scheduleId),
    onSuccess: () => {
      toast.success('Kayıtlar oluşturuldu');
      setNewScheduleId(null);
      queryClient.invalidateQueries({ queryKey: ['revenue-schedules'] });
    },
    onError: () => toast.error('Kayıtlar oluşturulamadı'),
  });

  const recognizeMutation = useMutation({
    mutationFn: ({ scheduleId, entryId }: { scheduleId: number; entryId: number }) =>
      revenueRecApi.recognizeEntry(scheduleId, entryId),
    onSuccess: () => {
      toast.success('Gelir tanindi');
      queryClient.invalidateQueries({ queryKey: ['revenue-schedules'] });
      queryClient.invalidateQueries({ queryKey: ['revenue-dashboard'] });
    },
    onError: () => toast.error('Tanıma başarısız'),
  });

  function handleRecognizeEntry(scheduleId: number, entryId: number) {
    recognizeMutation.mutate({ scheduleId, entryId });
  }

  const schedules = Array.isArray(schedulesData) ? schedulesData : [];
  const contracts = contractsData?.items ?? [];

  if (isDashboardError || isSchedulesError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Gelir Tanıma" description="ASC 606 / IFRS 15 uyumlu gelir zamanlamasi" />
        <Card>
          <div className="p-8 text-center">
            <p className="text-sm text-red-500">
              Veriler yuklenirken bir hata oluştu. Lütfen sayfayi yenileyin.
            </p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <PageHeader title="Gelir Tanıma" description="ASC 606 / IFRS 15 uyumlu gelir zamanlamasi">
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus size={16} className="mr-1.5" />
          Yeni Takvim
        </Button>
      </PageHeader>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 mb-8">
        {isDashboardLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)
        ) : (
          <>
            <KpiCard
              label="Toplam Planlanan"
              value={formatCurrency(dashboard?.total_scheduled ?? 0)}
            />
            <KpiCard
              label="Toplam Tanınan"
              value={formatCurrency(dashboard?.total_recognized ?? 0)}
            />
            <KpiCard
              label="Bu Ay Bekleyen"
              value={formatCurrency(dashboard?.this_month_pending ?? 0)}
            />
            <KpiCard
              label="Tanıma Orani"
              value={Math.round(dashboard?.recognition_rate_pct ?? 0)}
              suffix="%"
            />
          </>
        )}
      </div>

      {/* Generate Entries CTA */}
      {newScheduleId !== null && (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-yellow-200 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-900/20 px-4 py-3">
          <Zap size={18} className="text-yellow-600 dark:text-yellow-400 shrink-0" />
          <p className="flex-1 text-sm text-yellow-800 dark:text-yellow-200">
            Takvim oluşturuldu. Donem kayitlarini otomatik olusturmak ister misiniz?
          </p>
          <button
            onClick={() => generateMutation.mutate(newScheduleId)}
            disabled={generateMutation.isPending}
            className="rounded-lg px-3 py-1.5 text-xs font-medium bg-yellow-600 text-white hover:bg-yellow-700 disabled:opacity-50 transition-colors cursor-pointer"
          >
            {generateMutation.isPending ? 'Oluşturuluyor…' : 'Kayıtları Oluştur'}
          </button>
          <button
            onClick={() => setNewScheduleId(null)}
            className="text-yellow-600 hover:text-yellow-800 text-sm cursor-pointer"
            aria-label="Kapat"
          >
            ×
          </button>
        </div>
      )}

      {/* Schedule List */}
      <div className="space-y-3">
        {isSchedulesLoading ? (
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)
        ) : schedules.length === 0 ? (
          <Card className="py-16 text-center">
            <TrendingUp size={40} className="mx-auto mb-3 text-gray-300 dark:text-gray-600" />
            <p className="text-gray-500">Henüz gelir takvimi yok.</p>
            <p className="text-sm text-gray-400 mt-1">
              Yeni bir takvim olusturmak icin "Yeni Takvim" dusinesine tiklayin.
            </p>
          </Card>
        ) : (
          schedules.map((schedule) => (
            <ScheduleCard
              key={schedule.id}
              schedule={schedule}
              onRecognizeEntry={handleRecognizeEntry}
              isRecognizing={recognizeMutation.isPending}
              onGenerateEntries={(scheduleId) => generateMutation.mutate(scheduleId)}
              isGenerating={generateMutation.isPending}
            />
          ))
        )}
      </div>

      {/* Create Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Gelir Takvimi"
      >
        <div className="space-y-4">
          <div>
            <label
              htmlFor="rev-contract"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Kontrat
            </label>
            <select
              id="rev-contract"
              value={form.contractId}
              onChange={(e) => setForm((f) => ({ ...f, contractId: e.target.value }))}
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-honeywell-red dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              <option value="">Kontrat seçin…</option>
              {contracts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="rev-type"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Tanıma Tipi
            </label>
            <select
              id="rev-type"
              value={form.recognitionType}
              onChange={(e) => setForm((f) => ({ ...f, recognitionType: e.target.value }))}
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-honeywell-red dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              {RECOGNITION_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="rev-start"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                Baslangic Tarihi
              </label>
              <Input
                id="rev-start"
                type="date"
                value={form.startDate}
                onChange={(e) => {
                  setForm((f) => ({ ...f, startDate: e.target.value }));
                  setFormErrors((prev) => ({ ...prev, endDate: undefined }));
                }}
              />
            </div>
            <div>
              <label
                htmlFor="rev-end"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                Bitis Tarihi
              </label>
              <Input
                id="rev-end"
                type="date"
                value={form.endDate}
                onChange={(e) => {
                  setForm((f) => ({ ...f, endDate: e.target.value }));
                  setFormErrors((prev) => ({ ...prev, endDate: undefined }));
                }}
              />
              {formErrors.endDate && (
                <p className="mt-1 text-xs text-red-500">{formErrors.endDate}</p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="rev-amount"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                Toplam Tutar
              </label>
              <Input
                id="rev-amount"
                type="number"
                min="0"
                step="0.01"
                placeholder="0.00"
                value={form.totalAmount}
                onChange={(e) => {
                  setForm((f) => ({ ...f, totalAmount: e.target.value }));
                  setFormErrors((prev) => ({ ...prev, totalAmount: undefined }));
                }}
              />
              {formErrors.totalAmount && (
                <p className="mt-1 text-xs text-red-500">{formErrors.totalAmount}</p>
              )}
            </div>
            <div>
              <label
                htmlFor="rev-currency"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                Para Birimi
              </label>
              <select
                id="rev-currency"
                value={form.currency}
                onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))}
                className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-honeywell-red dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              >
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="TRY">TRY</option>
              </select>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Button
              variant="ghost"
              onClick={() => {
                setIsCreateOpen(false);
                setFormErrors({});
              }}
            >
              İptal
            </Button>
            <Button
              onClick={() => {
                if (validateForm()) createMutation.mutate();
              }}
              disabled={
                createMutation.isPending ||
                !form.contractId ||
                !form.startDate ||
                !form.endDate ||
                !form.totalAmount
              }
            >
              {createMutation.isPending ? 'Kaydediliyor…' : 'Oluştur'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
