import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Sparkles, Power, Eye, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { EmptyState } from '../../components/ui/EmptyState';
import { Skeleton } from '../../components/ui/Skeleton';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { aiAttributesApi } from '../../lib/api';
import {
  onAiAttributeDefinitionChanged,
  onAiAttributeValueChanged,
} from '../../lib/cacheInvalidation';
import { formatDateTime } from '../../lib/formatters';

/**
 * S-H — AI attributes admin page.
 * Manages definition CRUD + on-demand generation preview.
 */

const ENTITY_TYPES = ['opportunity', 'customer', 'lead', 'account', 'quote', 'contract'] as const;
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
  // Round-8 R8-DEAD-4 — admin-side preview: pick a definition + entity_id
  // and trigger value generation to sanity-check prompt output.
  const [previewDefId, setPreviewDefId] = useState<number | null>(null);
  const [previewEntityId, setPreviewEntityId] = useState<string>('');

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
      onAiAttributeDefinitionChanged(qc);
    },
    onError: () => toast.error('Tanım oluşturulamadı'),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      aiAttributesApi.updateDefinition(id, { is_active: !isActive }),
    onSuccess: () => {
      onAiAttributeDefinitionChanged(qc);
    },
  });

  const items = listQuery.data?.items ?? [];
  const previewDef = previewDefId != null ? items.find((d) => d.id === previewDefId) : undefined;

  const previewQuery = useQuery({
    queryKey: ['ai-attributes', 'preview', previewDefId, previewEntityId],
    queryFn: async () => {
      if (!previewDef || !previewEntityId) return null;
      const result = await aiAttributesApi.listValues(
        previewDef.entity_type,
        Number(previewEntityId),
      );
      return result.items.find((v) => v.definition_id === previewDefId) ?? null;
    },
    enabled: previewDef != null && previewEntityId.trim() !== '',
  });

  const previewGenerateMutation = useMutation({
    mutationFn: async (definitionId: number) => {
      const def = items.find((d) => d.id === definitionId);
      if (!def || !previewEntityId) throw new Error('Önce varlık ID gir');
      return aiAttributesApi.generate(definitionId, { entity_id: Number(previewEntityId) });
    },
    onSuccess: () => {
      toast.success('Önizleme değeri üretildi');
      if (previewDef && previewEntityId) {
        onAiAttributeValueChanged(qc, previewDef.entity_type, Number(previewEntityId));
      }
      qc.invalidateQueries({ queryKey: ['ai-attributes', 'preview'] });
    },
    onError: () => toast.error('Önizleme üretilemedi'),
  });

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

      {listQuery.isError && (
        <QueryErrorBanner variant="block" onRetry={() => listQuery.refetch()} />
      )}

      {!listQuery.isError && listQuery.isLoading && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {!listQuery.isError && !listQuery.isLoading && items.length === 0 && (
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
                  <p className="mt-2 text-caption text-slate-500 line-clamp-2">{def.description}</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  variant="tertiary"
                  size="sm"
                  onClick={() => {
                    setPreviewDefId(def.id);
                    setPreviewEntityId('');
                  }}
                  aria-label="Önizle"
                >
                  <Eye className="h-3 w-3" />
                </Button>
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

      <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="Yeni AI özniteliği">
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
              disabled={
                !form.key || !form.label || !form.prompt_template || createMutation.isPending
              }
            >
              Oluştur
            </Button>
          </div>
        </div>
      </Modal>

      {/* Round-8 R8-DEAD-4 — value preview / debug surface. */}
      <Modal
        isOpen={previewDefId != null}
        onClose={() => {
          setPreviewDefId(null);
          setPreviewEntityId('');
        }}
        title={previewDef ? `Önizleme — ${previewDef.label}` : 'Önizleme'}
      >
        <div className="space-y-3">
          <Input
            label={`Varlık ID (${previewDef?.entity_type ?? '...'})`}
            type="number"
            value={previewEntityId}
            onChange={(e) => setPreviewEntityId(e.target.value)}
            placeholder="örn. 42"
          />

          {previewQuery.data ? (
            <Card className="bg-slate-50">
              <p className="text-caption text-slate-500">Mevcut değer</p>
              <p className="mt-1 break-words text-body-strong">
                {String(previewQuery.data.value ?? '—')}
              </p>
              <div className="mt-2 flex items-center gap-2 text-caption text-slate-500">
                {previewQuery.data.confidence != null && (
                  <Badge variant="info">
                    güven: {Math.round(previewQuery.data.confidence * 100)}%
                  </Badge>
                )}
                {previewQuery.data.model_name && (
                  <Badge variant="default">{previewQuery.data.model_name}</Badge>
                )}
                {previewQuery.data.generated_at && (
                  <span>{formatDateTime(previewQuery.data.generated_at)}</span>
                )}
              </div>
            </Card>
          ) : previewEntityId && previewDef && !previewQuery.isLoading ? (
            <p className="text-caption text-slate-500">Bu varlık için henüz değer yok.</p>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="tertiary"
              size="sm"
              onClick={() => {
                setPreviewDefId(null);
                setPreviewEntityId('');
              }}
            >
              Kapat
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => previewDefId && previewGenerateMutation.mutate(previewDefId)}
              disabled={!previewEntityId || previewGenerateMutation.isPending}
            >
              <RefreshCw
                className={`mr-1 h-3 w-3 ${previewGenerateMutation.isPending ? 'animate-spin' : ''}`}
              />
              Şimdi üret
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
