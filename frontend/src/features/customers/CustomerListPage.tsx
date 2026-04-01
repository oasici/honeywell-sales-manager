import { useState, useRef, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ChevronDown, ExternalLink, FileText, TrendingUp, Users } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { customersApi, quotesApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import { STATUS_LABELS, STATUS_COLORS } from '../../lib/constants';
import type { Customer, Quote, PaginatedResponse } from '../../lib/types';

/* ── Avatar color palette ── */
const AVATAR_COLORS = [
  'bg-rose-500',
  'bg-amber-500',
  'bg-emerald-500',
  'bg-sky-500',
  'bg-violet-500',
  'bg-pink-500',
  'bg-teal-500',
  'bg-indigo-500',
  'bg-orange-500',
  'bg-cyan-500',
];

function getAvatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % AVATAR_COLORS.length;
  return AVATAR_COLORS[index];
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

/* ── Customer Card with Quote Dropdown ── */
function CustomerCard({
  customer: c,
  navigate,
}: {
  customer: Customer;
  navigate: ReturnType<typeof useNavigate>;
}) {
  const [expanded, setExpanded] = useState(false);
  const quoteCount = c.quote_count ?? 0;

  const avatarColor = useMemo(() => getAvatarColor(c.name), [c.name]);
  const initials = useMemo(() => getInitials(c.name), [c.name]);

  const { data: quotesData, isLoading: quotesLoading } = useQuery<PaginatedResponse<Quote>>({
    queryKey: ['customer-quotes-card', c.id],
    queryFn: () => quotesApi.getQuotes({ customer_id: c.id, page_size: 20 }),
    enabled: expanded && quoteCount > 0,
  });

  const quotes = quotesData?.items ?? [];

  return (
    <div className="card-modern flex flex-col cursor-pointer hover:shadow-lg transition-all duration-200">
      {/* Top section - clickable to customer detail */}
      <button
        type="button"
        onClick={() => navigate(`/customers/${c.id}`)}
        className="flex items-start gap-4 p-5 text-left hover:bg-gray-50/60 transition-colors rounded-t-2xl"
      >
        {/* Avatar */}
        <div
          className={`${avatarColor} flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white shadow-sm`}
        >
          {initials}
        </div>

        {/* Info */}
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold text-gray-900 truncate leading-tight">
            {c.name}
          </h3>
          {c.company && (
            <p className="mt-0.5 text-sm text-gray-500 truncate">{c.company}</p>
          )}
          <p className="mt-0.5 text-xs text-gray-400 truncate">{c.email}</p>
        </div>
      </button>

      {/* Stats row + dropdown toggle */}
      <div className="border-t border-gray-100">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            if (quoteCount > 0) setExpanded(!expanded);
          }}
          className={`flex w-full items-center justify-between px-5 py-3.5 text-left transition-colors
            ${quoteCount > 0 ? 'hover:bg-gray-50/60 cursor-pointer' : 'cursor-default'}`}
        >
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-2">
              <FileText size={14} className="text-gray-400" />
              <div>
                <span className="text-[11px] uppercase tracking-wide text-gray-400 font-medium">
                  Teklif
                </span>
                <p className="text-sm font-semibold text-gray-800 leading-tight">
                  {quoteCount}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <TrendingUp size={14} className="text-gray-400" />
              <div>
                <span className="text-[11px] uppercase tracking-wide text-gray-400 font-medium">
                  Toplam Deger
                </span>
                <p className="text-sm font-semibold text-gray-800 leading-tight">
                  {formatCurrency(c.total_quote_value ?? 0, 'TRY')}
                </p>
              </div>
            </div>
          </div>
          {quoteCount > 0 && (
            <ChevronDown
              size={16}
              className={`shrink-0 text-gray-400 transition-transform duration-200 ${
                expanded ? 'rotate-180' : ''
              }`}
            />
          )}
        </button>

        {/* Expanded quote list */}
        {expanded && (
          <div className="border-t border-gray-100 bg-gray-50/40">
            {quotesLoading ? (
              <div className="px-5 py-3 space-y-2">
                {[0, 1].map((i) => (
                  <div key={i} className="h-10 animate-pulse rounded-lg bg-gray-200/70" />
                ))}
              </div>
            ) : quotes.length === 0 ? (
              <p className="px-5 py-3 text-xs text-gray-400">Teklif bulunamadi</p>
            ) : (
              <div className="divide-y divide-gray-100/80">
                {quotes.map((q) => (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => navigate(`/quotes/${q.id}`)}
                    className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left
                      hover:bg-white/80 transition-colors group"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-semibold text-gray-700 truncate">
                          {q.quote_number}
                        </span>
                      </div>
                      {/* Items summary */}
                      {q.items && q.items.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                          {q.items.slice(0, 3).map((item, idx) => (
                            <span key={idx} className="text-[10px] text-gray-400">
                              {item.honeywell_code || item.description?.slice(0, 15) || '-'}{' '}
                              <span className="text-gray-500">x{item.quantity}</span>
                            </span>
                          ))}
                          {q.items.length > 3 && (
                            <span className="text-[10px] text-gray-400">
                              +{q.items.length - 3} daha
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                          STATUS_COLORS[q.status] || 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {STATUS_LABELS[q.status] || q.status}
                      </span>
                      <span className="text-xs font-semibold text-gray-700 tabular-nums">
                        {formatCurrency(q.grand_total, q.currency)}
                      </span>
                      <ExternalLink
                        size={12}
                        className="text-gray-300 group-hover:text-honeywell-red transition-colors"
                      />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const INITIAL_FORM = {
  name: '',
  company: '',
  email: '',
  phone: '',
  address: '',
  tax_id: '',
  preferred_lang: 'tr',
};

export default function CustomerListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const importRef = useRef<HTMLInputElement>(null);

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);

  const { data, isLoading } = useQuery<PaginatedResponse<Customer>>({
    queryKey: ['customers', { page, search }],
    queryFn: () =>
      customersApi.getCustomers({
        page,
        page_size: 12,
        ...(search && { search }),
      }),
  });

  const createMutation = useMutation({
    mutationFn: (payload: typeof form) => customersApi.createCustomer(payload),
    onSuccess: () => {
      toast.success('Musteri basariyla eklendi');
      setModalOpen(false);
      setForm(INITIAL_FORM);
      queryClient.invalidateQueries({ queryKey: ['customers'] });
    },
    onError: () => toast.error('Musteri eklenemedi'),
  });

  const importMutation = useMutation({
    mutationFn: (file: File) => customersApi.importCustomers(file),
    onSuccess: (res) => {
      toast.success(`${res.imported} musteri ice aktarildi`);
      queryClient.invalidateQueries({ queryKey: ['customers'] });
    },
    onError: () => toast.error('Ice aktarma basarisiz'),
  });

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) importMutation.mutate(file);
    e.target.value = '';
  };

  const updateField = (field: string, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const customers = data?.items || [];
  const totalPages = data?.pages || 1;

  return (
    <div>
      <PageHeader title="Musteriler" description="Musteri yonetimi">
        <input
          type="file"
          ref={importRef}
          onChange={handleImport}
          accept=".xlsx,.xls,.csv"
          className="hidden"
        />
        <Button
          variant="secondary"
          loading={importMutation.isPending}
          onClick={() => importRef.current?.click()}
        >
          Ice Aktar
        </Button>
        <Button onClick={() => setModalOpen(true)}>Yeni Musteri</Button>
      </PageHeader>

      {/* Search */}
      <div className="mb-6 max-w-md">
        <Input
          placeholder="Isim, sirket veya email ile ara..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
      </div>

      {/* Customer Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} variant="card" />
          ))}
        </div>
      ) : customers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-gray-100 mb-5">
            <Users size={36} className="text-gray-400" />
          </div>
          <EmptyState
            title="Musteri bulunamadi"
            description="Yeni musteri ekleyerek baslayabilirsiniz"
            action={
              <Button onClick={() => setModalOpen(true)}>Yeni Musteri</Button>
            }
          />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {customers.map((c) => (
              <CustomerCard key={c.id} customer={c} navigate={navigate} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-8 flex items-center justify-between">
              <span className="text-sm text-gray-500">
                Sayfa {page} / {totalPages}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  Onceki
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                >
                  Sonraki
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* New Customer Modal */}
      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Yeni Musteri"
        size="lg"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate(form);
          }}
          className="space-y-5"
        >
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Input
              label="Isim"
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
              required
            />
            <Input
              label="Sirket"
              value={form.company}
              onChange={(e) => updateField('company', e.target.value)}
            />
            <Input
              label="Email"
              type="email"
              value={form.email}
              onChange={(e) => updateField('email', e.target.value)}
              required
            />
            <Input
              label="Telefon"
              value={form.phone}
              onChange={(e) => updateField('phone', e.target.value)}
            />
            <Input
              label="Vergi No"
              value={form.tax_id}
              onChange={(e) => updateField('tax_id', e.target.value)}
            />
            <Input
              label="Tercih Edilen Dil"
              value={form.preferred_lang}
              onChange={(e) => updateField('preferred_lang', e.target.value)}
              placeholder="tr / en"
            />
          </div>
          <Input
            label="Adres"
            value={form.address}
            onChange={(e) => updateField('address', e.target.value)}
          />
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Iptal
            </Button>
            <Button
              type="submit"
              loading={createMutation.isPending}
              className="px-8 shadow-sm"
            >
              Kaydet
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
