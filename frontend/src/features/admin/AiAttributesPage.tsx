import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Sparkles, Power } from 'lucide-react';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { EmptyState } from '../../components/ui/EmptyState';
import { Skeleton } from '../../components/ui/Skeleton';
import { aiAttributesApi } from '../../lib/api';

/**
 * S-H — AI attributes admin page.
 * Manages definition CRUD + on-demand generation preview.
 */

const ENTITY_TYPES = [
  'opportunity',
  'customer',
  'lead',
  'account',
  'quote',
  'contract',
] as const;
const DATA_TYPES = ['text', 'number', 'boolean', 'list_text'] as const;

interface DefinitionFormState {
  entity_type: string;
  key: string;
  label: string;
  description: string;
  data_type: string;
  prompt_template: string;
  refresh_hours: number;
}

const EMPTY_FORM: DefinitionFormState = {
  entity_type: 'opportunity',
  key: '',
  label: '',
  description: '',
  data_type: 'text',
  prompt_template: 'Açıkla: {{entity_id}}',
  refresh_hours: 24,
};

export default function AiAttributesPage() {
  const qc = useQueryClient();
  const [filterEntity, setFilterEntity] = useState<string | undefined>(undefined);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<DefinitionFormState>(EMPTY_FORM);

  const listQuery = useQuery({
    queryKey: ['ai-attributes', 'definitions', filterEntity ?? 'all'],
    queryFn: () => aiAttributesApi.listDefinitions(filterEntity, false),
  });

  const createMutation = useMutation({
    mutationFn: (body: DefinitionFormState) => aiAttributesApi.createDefinition(body),
    onSuccess: () => {
      toast.success('Tanım oluşturuldu');
      setShowModal(false);
      setForm(EMPTY_FORM);
      qc.invalidateQueries({ queryKey: ['ai-attributes', 'definitions'] });
    },
    onError: () => toast.error('Tanım oluşturulamadı'),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      aiAttributesApi.updateDefinition(id, { is_active: !isActive }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-attributes', 'definitions'] });
    },
  });

  const items = listQuery.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        title="AI Öznitelikleri"
        description="LLM ile doldurulan kalıcı alanlar — özet, sınıflandırma, çıkarım"
      >
        <Button variant="primary" size="sm" onClick={() => setShowModal(true)}>
          <Plus className="mr-1 h-3 w-3" />
          Yeni tanım
        </Button>
      </PageHeader>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-caption text-slate-500">Varlık tipi:</span>
        <button
          onClick={() => setFilterEntity(undefined)}
          className={`rounded-full px-3 py-1 text-caption transition ${
            filterEntity === undefined
              ? 'bg-honeywell-red text-white'
              : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
          }`}
        >
          Tümü
        </button>
        {ENTITY_TYPES.map((et) => (
          <button
            key={et}
            onClick={() => setFilterEntity(et)}
            className={`rounded-full px-3 py-1 text-caption transition ${
              filterEntity === et
                ? 'bg-honeywell-red text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            {et}
          </button>
        ))}
      </div>

      {listQuery.isLoading && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {!listQuery.isLoading && items.length === 0 && (
        <EmptyState
          title="Henüz tanım yok"
          description="Yeni tanım butonuna basarak ilk AI özniteliğini oluştur."
          icon={<Sparkles className="h-8 w-8 text-slate-400" />}
        />
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {items.map((def) => (
          <Card key={def.id}>
            <div className="flex items-start justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-3.5 w-3.5 text-honeywell-red" />
                  <span className="text-body-strong text-slate-800">{def.label}</span>
                  {!def.is_active && <Badge variant="default">pasif</Badge>}
                </div>
                <div className="mt-1 flex items-center gap-2 text-caption text-slate-500">
                  <span>{def.entity_type}</span>
                  <span>·</span>
                  <code className="rounded bg-slate-100 px-1">{def.key}</code>
                  <span>·</span>
                  <span>{def.data_type}</span>
                  <span>·</span>
                  <span>her {def.refresh_hours}s</span>
                </div>
                {def.description && (
                  <p className="mt-2 text-caption text-slate-500 line-clamp-2">
                    {def.description}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  variant="tertiary"
                  size="sm"
                  onClick={() => toggleMutation.mutate({ id: def.id, isActive: def.is_active })}
                  aria-label="Aç/kapat"
                >
                  <Power className="h-3 w-3" />
                </Button>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Yeni AI özniteliği"
      >
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-caption text-slate-500">Varlık tipi</span>
              <select
                value={form.entity_type}
                onChange={(e) => setForm({ ...form, entity_type: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm"
              >
                {ENTITY_TYPES.map((et) => (
                  <option key={et} value={et}>
                    {et}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-caption text-slate-500">Veri tipi</span>
              <select
                value={form.data_type}
                onChange={(e) => setForm({ ...form, data_type: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm"
              >
                {DATA_TYPES.map((dt) => (
                  <option key={dt} value={dt}>
                    {dt}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <Input
            label="Anahtar (key)"
            value={form.key}
            onChange={(e) => setForm({ ...form, key: e.target.value })}
            placeholder="ornek_anahtar"
          />
          <Input
            label="Etiket"
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
            placeholder="Örnek özet alanı"
          />
          <Input
            label="Açıklama"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Bu alanın amacı"
          />
          <label className="block">
            <span className="text-caption text-slate-500">Prompt şablonu</span>
            <textarea
              value={form.prompt_template}
              onChange={(e) => setForm({ ...form, prompt_template: e.target.value })}
              className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm font-mono"
              rows={4}
              placeholder="{{entity_id}} parametresi rendere gelirken doldurulur"
            />
          </label>
          <Input
            type="number"
            label="Yenileme aralığı (saat)"
            value={form.refresh_hours}
            onChange={(e) => setForm({ ...form, refresh_hours: Number(e.target.value) })}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="tertiary" size="sm" onClick={() => setShowModal(false)}>
              İptal
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => createMutation.mutate(form)}
              disabled={!form.key || !form.label || !form.prompt_template || createMutation.isPending}
            >
              Oluştur
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
