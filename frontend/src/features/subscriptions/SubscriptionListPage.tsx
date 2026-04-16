import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Filter } from 'lucide-react';
import { toast } from 'sonner';
import { subscriptionsApi, customersApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import type { Subscription, MrrDashboard } from '../../lib/types';

const STATUS_LABELS: Record<string, string> = {
  active: 'Aktif',
  paused: 'Duraklatildi',
  cancelled: 'Iptal Edildi',
  expired: 'Suresi Doldu',
};

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  paused: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  cancelled: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  expired: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const CYCLE_LABELS: Record<string, string> = {
  monthly: 'Aylik',
  quarterly: 'Ceyrektik',
  annual: 'Yillik',
};

interface CreateFormState {
  name: string;
  customer_id: string;
  billing_cycle: string;
  start_date: string;
  mrr: string;
  auto_renew: boolean;
  currency: string;
  items_json: string;
}

const INITIAL_FORM: CreateFormState = {
  name: '',
  customer_id: '',
  billing_cycle: 'monthly',
  start_date: new Date().toISOString().slice(0, 10),
  mrr: '',
  auto_renew: true,
  currency: 'TRY',
  items_json: '',
};

export default function SubscriptionListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateFormState>(INITIAL_FORM);
  const [tab, setTab] = useState<'all' | 'renewals'>('all');

  const { data: subsData, isLoading } = useQuery({
    queryKey: ['subscriptions', statusFilter],
    queryFn: () => subscriptionsApi.list(statusFilter ? { status: statusFilter } : {}),
  });

  const { data: mrrData } = useQuery<MrrDashboard>({
    queryKey: ['subscriptions', 'mrr-dashboard'],
    queryFn: () => subscriptionsApi.getMrrDashboard(),
  });

  const { data: renewalsData } = useQuery({
    queryKey: ['subscriptions', 'renewals'],
    queryFn: () => subscriptionsApi.getRenewals(30),
    enabled: tab === 'renewals',
  });

  const { data: customers } = useQuery({
    queryKey: ['customers-select'],
    queryFn: () => customersApi.getCustomers({ page_size: 200 }),
    enabled: showCreate,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => subscriptionsApi.create(payload),
    onSuccess: () => {
      toast.success('Abonelik olusturuldu');
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
      setShowCreate(false);
      setForm(INITIAL_FORM);
    },
    onError: () => toast.error('Abonelik olusturulamadi'),
  });

  const handleCreate = () => {
    if (!form.name || !form.customer_id) {
      toast.error('Ad ve musteri alanlari zorunludur');
      return;
    }
    createMutation.mutate({
      name: form.name,
      customer_id: Number(form.customer_id),
      billing_cycle: form.billing_cycle,
      start_date: form.start_date,
      mrr: Number(form.mrr) || 0,
      auto_renew: form.auto_renew,
      currency: form.currency,
      items_json: form.items_json || null,
    });
  };

  const subs: Subscription[] = subsData?.items ?? [];
  const renewalItems: Subscription[] = renewalsData?.items ?? [];
  const displayList = tab === 'renewals' ? renewalItems : subs;

  const filtered = displayList.filter((s) => s.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-6">
      {/* MRR KPI bar */}
      {mrrData && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div
            className="rounded-xl border p-4"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface)' }}
          >
            <p className="text-xs text-gray-500">Toplam MRR</p>
            <p className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
              {formatCurrency(mrrData.total_mrr, 'TRY')}
            </p>
          </div>
          <div
            className="rounded-xl border p-4"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface)' }}
          >
            <p className="text-xs text-gray-500">Aktif Abonelik</p>
            <p className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
              {mrrData.active_count}
            </p>
          </div>
          <div
            className="rounded-xl border p-4"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface)' }}
          >
            <p className="text-xs text-gray-500">Kayip (30 gun)</p>
            <p className="text-xl font-bold text-red-600">{mrrData.churn_count}</p>
          </div>
          <div
            className="rounded-xl border p-4"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface)' }}
          >
            <p className="text-xs text-gray-500">Kayip MRR</p>
            <p className="text-xl font-bold text-red-600">
              {formatCurrency(mrrData.churned_mrr, 'TRY')}
            </p>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
          Abonelikler
        </h1>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-honeywell-red px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors cursor-pointer"
        >
          <Plus size={16} />
          Yeni Abonelik
        </button>
      </div>

      {/* Tabs + search + filter */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div
          className="flex gap-1 rounded-lg p-1"
          style={{ backgroundColor: 'var(--surface-secondary)' }}
        >
          <button
            type="button"
            onClick={() => setTab('all')}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer ${
              tab === 'all'
                ? 'bg-white shadow text-honeywell-red dark:bg-gray-700'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Tumu
          </button>
          <button
            type="button"
            onClick={() => setTab('renewals')}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer ${
              tab === 'renewals'
                ? 'bg-white shadow text-honeywell-red dark:bg-gray-700'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Yaklasan Yenilemeler
            {mrrData && mrrData.upcoming_renewals.length > 0 && (
              <span className="ml-1.5 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-honeywell-red px-1.5 text-[10px] font-bold text-white">
                {mrrData.upcoming_renewals.length}
              </span>
            )}
          </button>
        </div>

        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Abonelik ara..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border py-2 pl-9 pr-3 text-sm"
            style={{
              borderColor: 'var(--border)',
              backgroundColor: 'var(--surface)',
              color: 'var(--text-primary)',
            }}
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter size={16} className="text-gray-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border py-2 px-3 text-sm"
            style={{
              borderColor: 'var(--border)',
              backgroundColor: 'var(--surface)',
              color: 'var(--text-primary)',
            }}
          >
            <option value="">Tum Durumlar</option>
            <option value="active">Aktif</option>
            <option value="paused">Duraklatildi</option>
            <option value="cancelled">Iptal Edildi</option>
            <option value="expired">Suresi Doldu</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div
        className="overflow-x-auto rounded-xl border"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface)' }}
      >
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left" style={{ borderColor: 'var(--border)' }}>
              <th className="px-4 py-3 font-medium text-gray-500">Ad</th>
              <th className="px-4 py-3 font-medium text-gray-500">Durum</th>
              <th className="px-4 py-3 font-medium text-gray-500">Donem</th>
              <th className="px-4 py-3 font-medium text-gray-500">MRR</th>
              <th className="px-4 py-3 font-medium text-gray-500">Sonraki Yenileme</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  Yukleniyor...
                </td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  Abonelik bulunamadi
                </td>
              </tr>
            )}
            {filtered.map((sub) => (
              <tr
                key={sub.id}
                onClick={() => navigate(`/subscriptions/${sub.id}`)}
                className="border-b hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors cursor-pointer"
                style={{ borderColor: 'var(--border)' }}
              >
                <td className="px-4 py-3 font-medium" style={{ color: 'var(--text-primary)' }}>
                  {sub.name}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[sub.status] ?? ''}`}
                  >
                    {STATUS_LABELS[sub.status] ?? sub.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500">
                  {CYCLE_LABELS[sub.billing_cycle] ?? sub.billing_cycle}
                </td>
                <td className="px-4 py-3 font-medium" style={{ color: 'var(--text-primary)' }}>
                  {formatCurrency(sub.mrr, sub.currency)}
                </td>
                <td className="px-4 py-3 text-gray-500">{sub.next_renewal_date ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div
            className="mx-4 w-full max-w-lg rounded-2xl border p-6 shadow-xl"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface)' }}
          >
            <h2 className="mb-4 text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
              Yeni Abonelik
            </h2>
            <div className="space-y-3">
              <div>
                <label htmlFor="sub-name" className="mb-1 block text-sm text-gray-500">
                  Ad
                </label>
                <input
                  id="sub-name"
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{
                    borderColor: 'var(--border)',
                    backgroundColor: 'var(--surface)',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>
              <div>
                <label htmlFor="sub-customer" className="mb-1 block text-sm text-gray-500">
                  Musteri
                </label>
                <select
                  id="sub-customer"
                  value={form.customer_id}
                  onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{
                    borderColor: 'var(--border)',
                    backgroundColor: 'var(--surface)',
                    color: 'var(--text-primary)',
                  }}
                >
                  <option value="">Musteri secin</option>
                  {(customers?.items ?? []).map(
                    (c: { id: number; name: string; company: string }) => (
                      <option key={c.id} value={c.id}>
                        {c.name} - {c.company}
                      </option>
                    ),
                  )}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="sub-cycle" className="mb-1 block text-sm text-gray-500">
                    Fatura Donemi
                  </label>
                  <select
                    id="sub-cycle"
                    value={form.billing_cycle}
                    onChange={(e) => setForm({ ...form, billing_cycle: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    style={{
                      borderColor: 'var(--border)',
                      backgroundColor: 'var(--surface)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    <option value="monthly">Aylik</option>
                    <option value="quarterly">Ceyrektik</option>
                    <option value="annual">Yillik</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="sub-start" className="mb-1 block text-sm text-gray-500">
                    Baslangic Tarihi
                  </label>
                  <input
                    id="sub-start"
                    type="date"
                    value={form.start_date}
                    onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    style={{
                      borderColor: 'var(--border)',
                      backgroundColor: 'var(--surface)',
                      color: 'var(--text-primary)',
                    }}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="sub-mrr" className="mb-1 block text-sm text-gray-500">
                    Aylik Gelir (MRR)
                  </label>
                  <input
                    id="sub-mrr"
                    type="number"
                    min="0"
                    step="0.01"
                    value={form.mrr}
                    onChange={(e) => setForm({ ...form, mrr: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    style={{
                      borderColor: 'var(--border)',
                      backgroundColor: 'var(--surface)',
                      color: 'var(--text-primary)',
                    }}
                  />
                </div>
                <div>
                  <label htmlFor="sub-currency" className="mb-1 block text-sm text-gray-500">
                    Para Birimi
                  </label>
                  <select
                    id="sub-currency"
                    value={form.currency}
                    onChange={(e) => setForm({ ...form, currency: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    style={{
                      borderColor: 'var(--border)',
                      backgroundColor: 'var(--surface)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    <option value="TRY">TRY</option>
                    <option value="USD">USD</option>
                    <option value="EUR">EUR</option>
                  </select>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input
                  id="sub-autorenew"
                  type="checkbox"
                  checked={form.auto_renew}
                  onChange={(e) => setForm({ ...form, auto_renew: e.target.checked })}
                  className="h-4 w-4 rounded border-gray-300"
                />
                <label htmlFor="sub-autorenew" className="text-sm text-gray-500">
                  Otomatik Yenile
                </label>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              >
                Vazgec
              </button>
              <button
                type="button"
                onClick={handleCreate}
                disabled={createMutation.isPending}
                className="rounded-lg bg-honeywell-red px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {createMutation.isPending ? 'Olusturuluyor...' : 'Olustur'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
