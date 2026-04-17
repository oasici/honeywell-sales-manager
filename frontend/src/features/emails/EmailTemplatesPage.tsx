import { useState, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Search, Send, Pencil, Trash2, Share2, Tag, X } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { emailTemplatesApi } from '../../lib/api';
import { useAuthStore } from '../../stores/authStore';

import type { EmailTemplate } from '../../lib/types';

const CATEGORY_OPTIONS = [
  { value: '', label: 'Tumu' },
  { value: 'followup', label: 'Takip' },
  { value: 'intro', label: 'Tanitim' },
  { value: 'quote', label: 'Teklif' },
  { value: 'general', label: 'Genel' },
];

const CATEGORY_LABELS: Record<string, string> = {
  followup: 'Takip',
  intro: 'Tanitim',
  quote: 'Teklif',
  general: 'Genel',
};

const CATEGORY_COLORS: Record<string, string> = {
  followup: 'bg-blue-100 text-blue-700',
  intro: 'bg-green-100 text-green-700',
  quote: 'bg-purple-100 text-purple-700',
  general: 'bg-gray-100 text-gray-700',
};

interface TemplateFormState {
  name: string;
  subject: string;
  body_html: string;
  category: string;
  is_shared: boolean;
  variables_json: string;
}

const EMPTY_FORM: TemplateFormState = {
  name: '',
  subject: '',
  body_html: '',
  category: '',
  is_shared: false,
  variables_json: '["customer_name","company","quote_number","rep_name"]',
};

export default function EmailTemplatesPage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<TemplateFormState>(EMPTY_FORM);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [sendModalId, setSendModalId] = useState<number | null>(null);
  const [sendEmail, setSendEmail] = useState('');
  const [sendContext, setSendContext] = useState<Record<string, string>>({});
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['email-templates'],
    queryFn: emailTemplatesApi.list,
  });

  const { data: variablesData } = useQuery({
    queryKey: ['email-template-variables'],
    queryFn: emailTemplatesApi.getVariables,
  });

  const variables: string[] = variablesData?.variables ?? [];

  const templates: EmailTemplate[] = data?.items ?? [];

  const filtered = templates.filter((t) => {
    const matchesSearch =
      !search ||
      t.name.toLowerCase().includes(search.toLowerCase()) ||
      t.subject.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = !categoryFilter || t.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => emailTemplatesApi.create(payload),
    onSuccess: () => {
      toast.success('Şablon oluşturuldu');
      queryClient.invalidateQueries({ queryKey: ['email-templates'] });
      closeModal();
    },
    onError: () => toast.error('Şablon oluşturulamadı'),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Record<string, unknown> }) =>
      emailTemplatesApi.update(id, payload),
    onSuccess: () => {
      toast.success('Şablon guncellendi');
      queryClient.invalidateQueries({ queryKey: ['email-templates'] });
      closeModal();
    },
    onError: () => toast.error('Şablon guncellenemedi'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => emailTemplatesApi.remove(id),
    onSuccess: () => {
      toast.success('Şablon silindi');
      queryClient.invalidateQueries({ queryKey: ['email-templates'] });
      setDeleteId(null);
    },
    onError: () => toast.error('Şablon silinemedi'),
  });

  const sendMutation = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number;
      payload: { to_email: string; context: Record<string, string> };
    }) => emailTemplatesApi.send(id, payload),
    onSuccess: () => {
      toast.success('Email gönderildi');
      closeSendModal();
    },
    onError: () => toast.error('Email gonderilemedi'),
  });

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setIsModalOpen(true);
  };

  const openEdit = (t: EmailTemplate) => {
    setForm({
      name: t.name,
      subject: t.subject,
      body_html: t.body_html,
      category: t.category || '',
      is_shared: t.is_shared,
      variables_json: t.variables_json || '[]',
    });
    setEditingId(t.id);
    setIsModalOpen(true);
  };

  const handleSave = () => {
    const payload: Record<string, unknown> = {
      name: form.name,
      subject: form.subject,
      body_html: form.body_html,
      category: form.category || null,
      is_shared: form.is_shared,
      variables_json: form.variables_json,
    };

    if (editingId) {
      updateMutation.mutate({ id: editingId, payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  const insertVariable = useCallback(
    (varName: string) => {
      const textarea = bodyRef.current;
      if (!textarea) return;

      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const text = form.body_html;
      const insertion = `{{${varName}}}`;

      setForm((prev) => ({
        ...prev,
        body_html: text.substring(0, start) + insertion + text.substring(end),
      }));

      requestAnimationFrame(() => {
        textarea.focus();
        const newPos = start + insertion.length;
        textarea.setSelectionRange(newPos, newPos);
      });
    },
    [form.body_html],
  );

  const openSendModal = (t: EmailTemplate) => {
    setSendModalId(t.id);
    setSendEmail('');
    const ctx: Record<string, string> = {};
    if (user) {
      ctx.rep_name = user.full_name;
      ctx.rep_email = user.email;
    }
    setSendContext(ctx);
  };

  const closeSendModal = () => {
    setSendModalId(null);
    setSendEmail('');
    setSendContext({});
  };

  const handleSend = () => {
    if (!sendModalId || !sendEmail) return;
    sendMutation.mutate({
      id: sendModalId,
      payload: { to_email: sendEmail, context: sendContext },
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton variant="card" count={3} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Email Şablonları"
        description="Hazir email şablonları olusturun ve gonderin"
      >
        <Button onClick={openCreate}>
          <Plus size={16} className="mr-1" />
          Yeni Şablon
        </Button>
      </PageHeader>

      {/* Filters */}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Şablon ara..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-200 py-2 pl-9 pr-3 text-sm focus:border-honeywell-red focus:outline-none"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-honeywell-red focus:outline-none"
        >
          {CATEGORY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Template Grid */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-200 py-16">
          <p className="text-gray-500 text-sm">Henüz şablon bulunmuyor</p>
          <Button variant="secondary" className="mt-3" onClick={openCreate}>
            <Plus size={16} className="mr-1" />
            İlk Şablonu Oluştur
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((t) => (
            <div
              key={t.id}
              className="group rounded-xl border border-gray-200 bg-white p-5 transition-shadow hover:shadow-md"
            >
              <div className="mb-3 flex items-start justify-between">
                <h3 className="text-sm font-semibold text-gray-900 line-clamp-1">{t.name}</h3>
                <div className="flex items-center gap-1">
                  {t.is_shared && (
                    <span title="Paylasilan">
                      <Share2 size={14} className="text-blue-500" />
                    </span>
                  )}
                  {t.category && (
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                        CATEGORY_COLORS[t.category] || 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      <Tag size={10} />
                      {CATEGORY_LABELS[t.category] || t.category}
                    </span>
                  )}
                </div>
              </div>

              <p className="mb-4 text-xs text-gray-500 line-clamp-2">{t.subject}</p>

              <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => openSendModal(t)}
                  className="flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium text-honeywell-red hover:bg-red-50 transition-colors"
                >
                  <Send size={12} />
                  Gönder
                </button>
                {t.created_by === user?.id && (
                  <>
                    <button
                      type="button"
                      onClick={() => openEdit(t)}
                      className="flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 transition-colors"
                    >
                      <Pencil size={12} />
                      Düzenle
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteId(t.id)}
                      className="flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 transition-colors"
                    >
                      <Trash2 size={12} />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create / Edit Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold text-gray-900">
                {editingId ? 'Şablonu Düzenle' : 'Yeni Şablon'}
              </h2>
              <button
                type="button"
                onClick={closeModal}
                className="text-gray-400 hover:text-gray-600"
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-4">
              <Input
                label="Şablon Adi"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="Örnek: Teklif Takip Maili"
              />

              <Input
                label="Konu"
                value={form.subject}
                onChange={(e) => setForm((p) => ({ ...p, subject: e.target.value }))}
                placeholder="Örnek: {{company}} için Teklif #{{quote_number}}"
              />

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  İçerik (HTML)
                </label>
                <textarea
                  ref={bodyRef}
                  value={form.body_html}
                  onChange={(e) => setForm((p) => ({ ...p, body_html: e.target.value }))}
                  rows={8}
                  className="w-full rounded-lg border border-gray-200 p-3 text-sm font-mono focus:border-honeywell-red focus:outline-none"
                  placeholder="Merhaba {{customer_name}},&#10;&#10;Teklifiniz hazir..."
                />
              </div>

              {/* Variable picker */}
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Degiskenler</label>
                <div className="flex flex-wrap gap-1.5">
                  {variables.map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => insertVariable(v)}
                      className="rounded-full border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:border-honeywell-red hover:text-honeywell-red transition-colors"
                    >
                      {`{{${v}}}`}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Kategori</label>
                  <select
                    value={form.category}
                    onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-honeywell-red focus:outline-none"
                  >
                    <option value="">Seçin...</option>
                    <option value="followup">Takip</option>
                    <option value="intro">Tanitim</option>
                    <option value="quote">Teklif</option>
                    <option value="general">Genel</option>
                  </select>
                </div>

                <div className="flex items-end">
                  <label className="flex items-center gap-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      checked={form.is_shared}
                      onChange={(e) => setForm((p) => ({ ...p, is_shared: e.target.checked }))}
                      className="h-4 w-4 rounded border-gray-300 text-honeywell-red focus:ring-honeywell-red"
                    />
                    Tüm ekiple paylas
                  </label>
                </div>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <Button variant="secondary" onClick={closeModal}>
                İptal
              </Button>
              <Button
                onClick={handleSave}
                loading={createMutation.isPending || updateMutation.isPending}
                disabled={!form.name || !form.subject || !form.body_html}
              >
                {editingId ? 'Güncelle' : 'Oluştur'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Send Modal */}
      {sendModalId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold text-gray-900">Email Gönder</h2>
              <button
                type="button"
                onClick={closeSendModal}
                className="text-gray-400 hover:text-gray-600"
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-4">
              <Input
                label="Alici Email"
                type="email"
                value={sendEmail}
                onChange={(e) => setSendEmail(e.target.value)}
                placeholder="müşteri@şirket.com"
              />

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Degisken Degerleri
                </label>
                <div className="space-y-2">
                  {variables.map((v) => (
                    <div key={v} className="flex items-center gap-2">
                      <span className="w-32 text-xs font-mono text-gray-500">{`{{${v}}}`}</span>
                      <input
                        type="text"
                        value={sendContext[v] || ''}
                        onChange={(e) =>
                          setSendContext((prev) => ({ ...prev, [v]: e.target.value }))
                        }
                        className="flex-1 rounded-md border border-gray-200 px-2.5 py-1.5 text-sm focus:border-honeywell-red focus:outline-none"
                        placeholder={v}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <Button variant="secondary" onClick={closeSendModal}>
                İptal
              </Button>
              <Button onClick={handleSend} loading={sendMutation.isPending} disabled={!sendEmail}>
                <Send size={14} className="mr-1" />
                Gönder
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={deleteId !== null}
        onClose={() => setDeleteId(null)}
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        title="Şablonu Sil"
        message="Bu email şablonu kalici olarak silinecek. Devam etmek istiyor musunuz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
