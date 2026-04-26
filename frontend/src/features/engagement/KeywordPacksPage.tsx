import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Tag } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { engagementApi } from '../../lib/api';
import type { KeywordPack } from '../../lib/types';

const CATEGORY_OPTIONS = [
  { value: 'pricing', label: 'Fiyatlandirma' },
  { value: 'competitor', label: 'Rakip' },
  { value: 'objection', label: 'Itiraz' },
  { value: 'positive', label: 'Olumlu' },
  { value: 'technical', label: 'Teknik' },
  { value: 'custom', label: 'Özel' },
];

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'default';

const CATEGORY_BADGE_VARIANT: Record<string, BadgeVariant> = {
  pricing: 'warning',
  competitor: 'danger',
  objection: 'danger',
  positive: 'success',
  technical: 'info',
  custom: 'default',
};

function getCategoryLabel(category: string): string {
  const found = CATEGORY_OPTIONS.find((o) => o.value === category);
  return found ? found.label : category;
}

export default function KeywordPacksPage() {
  const queryClient = useQueryClient();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [form, setForm] = useState({
    name: '',
    category: 'custom',
    keywordsText: '',
  });

  const { data, isLoading } = useQuery<{ packs: KeywordPack[] }>({
    queryKey: ['keyword-packs'],
    queryFn: () => engagementApi.listKeywordPacks(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => engagementApi.createKeywordPack(payload),
    onSuccess: () => {
      toast.success('Anahtar kelime paketi oluşturuldu');
      queryClient.invalidateQueries({ queryKey: ['keyword-packs'] });
      setIsCreateOpen(false);
      resetForm();
    },
    onError: () => toast.error('Paket oluşturulamadı'),
  });

  function resetForm() {
    setForm({ name: '', category: 'custom', keywordsText: '' });
  }

  function handleCreate() {
    if (!form.name.trim()) {
      toast.error('Paket adi zorunludur');
      return;
    }
    const keywords = form.keywordsText
      .split(',')
      .map((k) => k.trim())
      .filter(Boolean);
    if (keywords.length === 0) {
      toast.error('En az bir anahtar kelime giriniz');
      return;
    }
    createMutation.mutate({
      name: form.name,
      category: form.category,
      keywords,
    });
  }

  const packs = data?.packs ?? [];

  return (
    <div>
      <PageHeader title="Anahtar Kelime Paketleri" description="Görüşme analizi için kelime gruplari">
        <Button onClick={() => setIsCreateOpen(true)}>Yeni Paket</Button>
      </PageHeader>

      {isLoading ? (
        <Skeleton variant="card" count={3} />
      ) : packs.length === 0 ? (
        <EmptyState
          title="Paket bulunamadi"
          description="Henüz anahtar kelime paketi eklenmemis"
          icon={<Tag size={40} />}
          action={<Button onClick={() => setIsCreateOpen(true)}>İlk Paketi Ekle</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {packs.map((pack) => (
            <Card key={pack.id}>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-slate-900">{pack.name}</h4>
                  <Badge variant={pack.is_active ? 'success' : 'default'} size="sm">
                    {pack.is_active ? 'Aktif' : 'Pasif'}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={CATEGORY_BADGE_VARIANT[pack.category] ?? 'default'} size="sm">
                    {getCategoryLabel(pack.category)}
                  </Badge>
                  <span className="text-xs text-slate-500">
                    {pack.keywords.length} kelime
                  </span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {pack.keywords.map((keyword, idx) => (
                    <span
                      key={idx}
                      className="inline-flex rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Anahtar Kelime Paketi"
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Paket Adi</label>
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Örneğin: Fiyat Kelimeleri"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Kategori</label>
            <select
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              value={form.category}
              onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
            >
              {CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Anahtar Kelimeler (virgul ile ayirin)
            </label>
            <Input
              value={form.keywordsText}
              onChange={(e) => setForm((f) => ({ ...f, keywordsText: e.target.value }))}
              placeholder="fiyat, teklif, indirim, kampanya"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
              İptal
            </Button>
            <Button loading={createMutation.isPending} onClick={handleCreate}>
              Oluştur
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
