import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ChevronDown, ExternalLink } from 'lucide-react';
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

  const { data: quotesData, isLoading: quotesLoading } = useQuery<PaginatedResponse<Quote>>({
    queryKey: ['customer-quotes-card', c.id],
    queryFn: () => quotesApi.getQuotes({ customer_id: c.id, page_size: 20 }),
    enabled: expanded && quoteCount > 0,
  });

  const quotes = quotesData?.items ?? [];

  return (
    <div className="flex flex-col rounded-xl border border-gray-200 bg-white shadow-sm transition-shadow hover:shadow-md">
      {/* Top section - clickable to customer detail */}
      <button
        type="button"
        onClick={() => navigate(`/customers/${c.id}`)}
        className="flex flex-col p-5 text-left hover:bg-gray-50/50 transition-colors rounded-t-xl"
      >
        <h3 className="font-semibold text-gray-900 truncate">{c.name}</h3>
        {c.company && (
          <p className="mt-0.5 text-sm text-gray-500 truncate">{c.company}</p>
        )}
        <p className="mt-1 text-xs text-gray-400 truncate">{c.email}</p>
      </button>

      {/* Quote summary - clickable dropdown toggle */}
      <div className="border-t border-gray-100">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            if (quoteCount > 0) setExpanded(!expanded);
          }}
          className={`flex w-full items-center justify-between px-5 py-3 text-left transition-colors
            ${quoteCount > 0 ? 'hover:bg-gray-50 cursor-pointer' : 'cursor-default'}`}
        >
          <div className="flex items-center gap-4">
            <div>
              <span className="text-xs text-gray-400">Teklif</span>
              <p className="text-sm font-semibold text-gray-800">{quoteCount}</p>
            </div>
            <div>
              <span className="text-xs text-gray-400">Toplam Deger</span>
              <p className="text-sm font-semibold text-gray-800">
                {formatCurrency(c.total_quote_value ?? 0, 'TRY')}
              </p>
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
          <div className="border-t border-gray-100 bg-gray-50/50">
            {quotesLoading ? (
              <div className="px-5 py-3 space-y-2">
                {[0, 1].map((i) => (
                  <div key={i} className="h-10 animate-pulse rounded bg-gray-200" />
                ))}
              </div>
            ) : quotes.length === 0 ? (
              <p className="px-5 py-3 text-xs text-gray-400">Teklif bulunamadi</p>
            ) : (
              <div className="divide-y divide-gray-100">
                {quotes.map((q) => (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => navigate(`/quotes/${q.id}`)}
                    className="flex w-full items-center justify-between gap-2 px-5 py-2.5 text-left
                      hover:bg-white transition-colors group"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-semibold text-gray-700 truncate">
                          {q.quote_number}
                        </span>
                        <span
                          className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                            STATUS_COLORS[q.status] || 'bg-gray-100 text-gray-600'
                          }`}
                        >
                          {STATUS_LABELS[q.status] || q.status}
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
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-xs font-semibold text-gray-700">
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} variant="card" />
          ))}
        </div>
      ) : customers.length === 0 ? (
        <EmptyState
          title="Musteri bulunamadi"
          description="Yeni musteri ekleyerek baslayabilirsiniz"
          action={
            <Button onClick={() => setModalOpen(true)}>Yeni Musteri</Button>
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {customers.map((c) => (
              <CustomerCard key={c.id} customer={c} navigate={navigate} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-between">
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
          className="space-y-4"
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Iptal
            </Button>
            <Button type="submit" loading={createMutation.isPending}>
              Kaydet
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
