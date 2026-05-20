import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  BarChart3,
  LineChart as LineChartIcon,
  PieChart as PieChartIcon,
  Table,
  Users,
  Mail,
  FileText,
  Target,
  Plus,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Save,
  Check,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';
import { Skeleton } from '../../components/ui/Skeleton';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { reportsApi } from '../../lib/api';

const TOTAL_STEPS = 5;

const ENTITY_TYPES = [
  { key: 'quote', label: 'Teklifler', icon: FileText, color: 'text-blue-500' },
  { key: 'opportunity', label: 'Fırsatlar', icon: Target, color: 'text-green-500' },
  { key: 'customer', label: 'Müşteriler', icon: Users, color: 'text-purple-500' },
  { key: 'email', label: 'Emailler', icon: Mail, color: 'text-orange-500' },
];

const CHART_TYPES = [
  { value: 'bar', label: 'Cubuk Grafik', icon: BarChart3 },
  { value: 'line', label: 'Cizgi Grafik', icon: LineChartIcon },
  { value: 'pie', label: 'Pasta Grafik', icon: PieChartIcon },
  { value: 'table', label: 'Sadece Tablo', icon: Table },
];

const OPERATOR_OPTIONS = [
  { value: 'eq', label: 'Esit' },
  { value: 'neq', label: 'Esit Değil' },
  { value: 'gt', label: 'Buyuk' },
  { value: 'gte', label: 'Buyuk Esit' },
  { value: 'lt', label: 'Kucuk' },
  { value: 'lte', label: 'Kucuk Esit' },
  { value: 'contains', label: 'İçerir' },
];

const CHART_COLORS = [
  '#ef4444',
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#8b5cf6',
  '#ec4899',
  '#06b6d4',
  '#84cc16',
  '#f97316',
  '#6366f1',
];

interface ReportFilter {
  field: string;
  operator: string;
  value: string;
}

interface SaveForm {
  name: string;
  description: string;
  is_public: boolean;
}

const STEP_LABELS = ['Veri Kaynagi', 'Kolonlar', 'Filtreler', 'Gruplama & Grafik', 'Onizleme'];

export default function ReportBuilderPage() {
  const navigate = useNavigate();

  const [step, setStep] = useState(1);
  const [entityType, setEntityType] = useState('');
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [filters, setFilters] = useState<ReportFilter[]>([]);
  const [groupBy, setGroupBy] = useState('');
  const [chartType, setChartType] = useState('bar');
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [saveForm, setSaveForm] = useState<SaveForm>({
    name: '',
    description: '',
    is_public: false,
  });

  const {
    data: columnsData,
    isLoading: isColumnsLoading,
    isError: isColumnsError,
    refetch: refetchColumns,
  } = useQuery<{
    data: { entity_type: string; columns: string[]; join_columns?: string[] };
  }>({
    queryKey: ['report-columns', entityType],
    queryFn: () => reportsApi.getAvailableColumns(entityType),
    enabled: !!entityType && step >= 2,
  });

  const availableColumns: string[] = [
    ...(columnsData?.data?.columns ?? []),
    ...(columnsData?.data?.join_columns ?? []),
  ];

  const previewMutation = useMutation({
    mutationFn: async () => {
      if (!entityType || selectedColumns.length === 0) {
        throw new Error('Veri kaynagi ve en az bir kolon secilmeli');
      }
      return reportsApi.preview({
        entity_type: entityType,
        columns: selectedColumns,
        filters: filters.length > 0 ? filters : undefined,
        group_by: groupBy || undefined,
        sort_order: 'desc',
        limit: 100,
        page: 1,
        page_size: 100,
      });
    },
    onError: (err: unknown) => {
      const apiErr = err as {
        response?: { data?: { detail?: string; error?: { message?: string } } };
        message?: string;
      };
      const msg =
        apiErr?.response?.data?.detail ||
        apiErr?.response?.data?.error?.message ||
        apiErr?.message ||
        'Onizleme yuklenemedi';
      toast.error(msg);
      // Round-14 R14-LOG-1 — toast.error already surfaces the failure
      // to the user; the leftover console.error was dev-only debug
      // noise reaching prod. Removed.
    },
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      reportsApi.createTemplate({
        name: saveForm.name,
        description: saveForm.description || null,
        entity_type: entityType,
        columns_json: JSON.stringify(selectedColumns),
        filters_json: filters.length > 0 ? JSON.stringify(filters) : null,
        group_by: groupBy || null,
        chart_type: chartType,
        is_public: saveForm.is_public,
      }),
    onSuccess: () => {
      toast.success('Rapor şablonu kaydedildi');
      setIsSaveModalOpen(false);
      navigate('/reports/saved');
    },
    onError: () => toast.error('Rapor kaydedilemedi'),
  });

  const columnOptions = availableColumns.map((col) => ({
    value: col,
    label: col,
  }));

  const handleNext = () => {
    if (step === 4) {
      // Trigger preview and move to step 5
      previewMutation.mutate();
    }
    setStep((prev) => Math.min(prev + 1, TOTAL_STEPS));
  };

  // Auto-trigger preview when step 5 is reached without data
  useEffect(() => {
    if (
      step === 5 &&
      !previewMutation.data &&
      !previewMutation.isPending &&
      !previewMutation.isError &&
      selectedColumns.length > 0
    ) {
      previewMutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const handlePrev = () => {
    setStep((prev) => Math.max(prev - 1, 1));
  };

  const toggleColumn = (col: string) => {
    setSelectedColumns((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col],
    );
  };

  const addFilter = () => {
    setFilters((prev) => [...prev, { field: '', operator: 'eq', value: '' }]);
  };

  const updateFilter = (idx: number, field: keyof ReportFilter, value: string) => {
    setFilters((prev) => prev.map((f, i) => (i === idx ? { ...f, [field]: value } : f)));
  };

  const removeFilter = (idx: number) => {
    setFilters((prev) => prev.filter((_, i) => i !== idx));
  };

  const isNextDisabled = () => {
    if (step === 1) return !entityType;
    if (step === 2) return selectedColumns.length === 0;
    return false;
  };

  const previewRaw = previewMutation.data;
  // API returns {data: {columns, rows, total}} — unwrap the nested data
  const previewData = previewRaw?.data ?? previewRaw;
  const previewRows: Record<string, unknown>[] = previewData?.rows ?? [];
  const previewColumns: string[] = previewData?.columns ?? selectedColumns;

  return (
    <div>
      <PageHeader title="Rapor Olusturucu" description="Adım adım özel rapor olusturun">
        <Button variant="secondary" onClick={() => navigate('/reports/saved')}>
          Geri Don
        </Button>
      </PageHeader>

      {/* Stepper */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          {STEP_LABELS.map((label, idx) => {
            const stepNum = idx + 1;
            const isActive = step === stepNum;
            const isComplete = step > stepNum;
            return (
              <div key={stepNum} className="flex flex-1 items-center">
                <div className="flex flex-col items-center">
                  <div
                    className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                      isActive
                        ? 'bg-honeywell-red text-white'
                        : isComplete
                          ? 'bg-green-500 text-white'
                          : 'bg-gray-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                    }`}
                  >
                    {isComplete ? <Check size={14} /> : stepNum}
                  </div>
                  <span
                    className={`mt-1 text-[10px] font-medium ${
                      isActive ? 'text-honeywell-red' : 'text-slate-400 dark:text-slate-500'
                    }`}
                  >
                    {label}
                  </span>
                </div>
                {idx < STEP_LABELS.length - 1 && (
                  <div
                    className={`mx-2 h-0.5 flex-1 ${
                      step > stepNum ? 'bg-green-500' : 'bg-gray-200 dark:bg-slate-800'
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Step 1: Entity Type */}
      {step === 1 && (
        <Card title="Veri Kaynagi Seçin">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {ENTITY_TYPES.map((et) => {
              const Icon = et.icon;
              const isSelected = entityType === et.key;
              return (
                <button
                  key={et.key}
                  type="button"
                  onClick={() => {
                    setEntityType(et.key);
                    setSelectedColumns([]);
                    setFilters([]);
                    setGroupBy('');
                  }}
                  className={`flex flex-col items-center gap-3 rounded-xl border-2 p-6 transition-all ${
                    isSelected
                      ? 'border-honeywell-red bg-honeywell-red/5 shadow-md'
                      : 'border-slate-200 hover:border-slate-200 dark:border-slate-700 dark:hover:border-slate-700'
                  }`}
                >
                  <Icon size={32} className={isSelected ? 'text-honeywell-red' : et.color} />
                  <span
                    className={`text-sm font-semibold ${
                      isSelected ? 'text-honeywell-red' : 'text-slate-700 dark:text-slate-300'
                    }`}
                  >
                    {et.label}
                  </span>
                </button>
              );
            })}
          </div>
        </Card>
      )}

      {/* Step 2: Columns */}
      {step === 2 && (
        <Card title="Kolonlari Seçin">
          {isColumnsError ? (
            <QueryErrorBanner variant="block" onRetry={() => refetchColumns()} />
          ) : isColumnsLoading ? (
            <Skeleton variant="line" count={6} />
          ) : availableColumns.length === 0 ? (
            <p className="py-4 text-sm text-slate-500">Kullanilabilir kolon bulunamadi</p>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {availableColumns.map((col) => (
                <label
                  key={col}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2.5 text-sm cursor-pointer hover:bg-slate-50 transition-colors dark:border-slate-800 dark:hover:bg-slate-800"
                >
                  <input
                    type="checkbox"
                    checked={selectedColumns.includes(col)}
                    onChange={() => toggleColumn(col)}
                    className="h-4 w-4 rounded border-slate-200 text-honeywell-red focus:ring-honeywell-red"
                  />
                  <span className="text-slate-700 dark:text-slate-300">{col}</span>
                </label>
              ))}
            </div>
          )}
          {selectedColumns.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              <span className="text-xs text-slate-500 mr-1">Secili:</span>
              {selectedColumns.map((col) => (
                <Badge key={col} variant="info" size="sm">
                  {col}
                </Badge>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Step 3: Filters */}
      {step === 3 && (
        <Card
          title="Filtreler"
          action={
            <Button size="sm" variant="secondary" onClick={addFilter}>
              <Plus size={14} className="mr-1" />
              Filtre Ekle
            </Button>
          }
        >
          {filters.length === 0 ? (
            <p className="py-4 text-sm text-slate-500 dark:text-slate-400">
              Filtre eklenmedi. Tüm veriler dahil edilecek.
            </p>
          ) : (
            <div className="space-y-3">
              {filters.map((filter, idx) => (
                <div
                  key={idx}
                  className="flex items-end gap-3 rounded-lg border border-slate-200 p-3 dark:border-slate-800"
                >
                  <Select
                    label="Alan"
                    options={columnOptions}
                    value={filter.field}
                    onChange={(e) => updateFilter(idx, 'field', e.target.value)}
                    placeholder="Alan seçin"
                  />
                  <Select
                    label="Operator"
                    options={OPERATOR_OPTIONS}
                    value={filter.operator}
                    onChange={(e) => updateFilter(idx, 'operator', e.target.value)}
                  />
                  <Input
                    label="Değer"
                    value={filter.value}
                    onChange={(e) => updateFilter(idx, 'value', e.target.value)}
                    placeholder="Değer girin"
                  />
                  <button
                    type="button"
                    onClick={() => removeFilter(idx)}
                    className="mb-1 rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors dark:hover:bg-red-900/20"
                    title="Kaldir"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Step 4: Group By & Chart Type */}
      {step === 4 && (
        <Card title="Gruplama & Grafik Tipi">
          <div className="space-y-6">
            <Select
              label="Gruplama Alani"
              options={[{ value: '', label: 'Gruplama Yok' }, ...columnOptions]}
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value)}
            />

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                Grafik Tipi
              </label>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {CHART_TYPES.map((ct) => {
                  const Icon = ct.icon;
                  const isSelected = chartType === ct.value;
                  return (
                    <button
                      key={ct.value}
                      type="button"
                      onClick={() => setChartType(ct.value)}
                      className={`flex flex-col items-center gap-2 rounded-xl border-2 p-4 transition-all ${
                        isSelected
                          ? 'border-honeywell-red bg-honeywell-red/5'
                          : 'border-slate-200 hover:border-slate-200 dark:border-slate-700'
                      }`}
                    >
                      <Icon
                        size={24}
                        className={isSelected ? 'text-honeywell-red' : 'text-slate-400'}
                      />
                      <span
                        className={`text-xs font-medium ${
                          isSelected ? 'text-honeywell-red' : 'text-slate-500 dark:text-slate-400'
                        }`}
                      >
                        {ct.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Step 5: Preview */}
      {step === 5 && (
        <div className="space-y-6">
          <Card title="Onizleme">
            {previewMutation.isPending ? (
              <Skeleton variant="card" count={2} />
            ) : previewRows.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500 dark:text-slate-400">
                Onizleme verisi bulunamadi
              </p>
            ) : (
              <>
                {/* Chart */}
                {chartType !== 'table' && previewRows.length > 0 && (
                  <div className="mb-6 h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      {chartType === 'bar' ? (
                        <BarChart data={previewRows}>
                          <XAxis dataKey={groupBy || previewColumns[0]} tick={{ fontSize: 11 }} />
                          <YAxis tick={{ fontSize: 11 }} />
                          <Tooltip />
                          <Bar
                            dataKey={previewColumns[1] || previewColumns[0]}
                            fill="#ef4444"
                            radius={[4, 4, 0, 0]}
                          />
                        </BarChart>
                      ) : chartType === 'line' ? (
                        <LineChart data={previewRows}>
                          <XAxis dataKey={groupBy || previewColumns[0]} tick={{ fontSize: 11 }} />
                          <YAxis tick={{ fontSize: 11 }} />
                          <Tooltip />
                          <Line
                            type="monotone"
                            dataKey={previewColumns[1] || previewColumns[0]}
                            stroke="#ef4444"
                            strokeWidth={2}
                          />
                        </LineChart>
                      ) : (
                        <PieChart>
                          <Pie
                            data={previewRows}
                            dataKey={previewColumns[1] || previewColumns[0]}
                            nameKey={groupBy || previewColumns[0]}
                            cx="50%"
                            cy="50%"
                            outerRadius={80}
                            label
                          >
                            {previewRows.map((_, idx) => (
                              <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip />
                        </PieChart>
                      )}
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Data Table */}
                <DataTable
                  columns={previewColumns.map((col) => ({
                    key: col,
                    header: col,
                    sortable: true,
                  }))}
                  data={previewRows}
                />
              </>
            )}
          </Card>
        </div>
      )}

      {/* Navigation Buttons */}
      <div className="mt-6 flex items-center justify-between">
        <Button variant="secondary" onClick={handlePrev} disabled={step === 1}>
          <ChevronLeft size={16} className="mr-1" />
          Önceki
        </Button>

        <div className="flex gap-2">
          {step === TOTAL_STEPS && (
            <Button onClick={() => setIsSaveModalOpen(true)}>
              <Save size={16} className="mr-1" />
              Kaydet
            </Button>
          )}
          {step < TOTAL_STEPS && (
            <Button onClick={handleNext} disabled={isNextDisabled()}>
              Sonraki
              <ChevronRight size={16} className="ml-1" />
            </Button>
          )}
        </div>
      </div>

      {/* Save Modal */}
      <Modal
        isOpen={isSaveModalOpen}
        onClose={() => setIsSaveModalOpen(false)}
        title="Raporu Kaydet"
      >
        <div className="space-y-4">
          <Input
            label="Rapor Adi"
            value={saveForm.name}
            onChange={(e) => setSaveForm((prev) => ({ ...prev, name: e.target.value }))}
            placeholder="örnek: Aylik Teklif Özeti"
          />
          <Input
            label="Açıklama"
            value={saveForm.description}
            onChange={(e) =>
              setSaveForm((prev) => ({
                ...prev,
                description: e.target.value,
              }))
            }
            placeholder="Rapor aciklamasi (opsiyonel)"
          />
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={saveForm.is_public}
              onChange={(e) =>
                setSaveForm((prev) => ({
                  ...prev,
                  is_public: e.target.checked,
                }))
              }
              className="h-4 w-4 rounded border-slate-200 text-honeywell-red focus:ring-honeywell-red"
            />
            <span className="text-sm text-slate-700 dark:text-slate-300">Herkese Acik</span>
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsSaveModalOpen(false)}>
              İptal
            </Button>
            <Button
              onClick={() => saveMutation.mutate()}
              loading={saveMutation.isPending}
              disabled={!saveForm.name}
            >
              Kaydet
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
