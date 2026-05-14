import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { UserPlus, Trash2, Users } from 'lucide-react';

import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { teamsApi } from '../../lib/api';
import { onTeamMemberChanged } from '../../lib/cacheInvalidation';
import type { TeamMember } from '../../lib/types';

interface AccountTeamPanelProps {
  customerId: number;
}

const ROLE_OPTIONS = [
  { value: 'owner', label: 'Sahip' },
  { value: 'member', label: 'Üye' },
  { value: 'viewer', label: 'Izleyici' },
];

const ROLE_BADGE_CLASSES: Record<string, string> = {
  owner: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  member: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  viewer: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
};

const ROLE_LABELS: Record<string, string> = {
  owner: 'Sahip',
  member: 'Üye',
  viewer: 'Izleyici',
};

function getInitials(name: string | null | undefined): string {
  if (!name) return '?';
  return name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

export default function AccountTeamPanel({ customerId }: AccountTeamPanelProps) {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<TeamMember | null>(null);
  const [form, setForm] = useState({ user_id: '', role: 'member' });

  const { data, isLoading } = useQuery<{ data: TeamMember[] }>({
    queryKey: ['team-members', customerId],
    queryFn: () => teamsApi.getMembers(customerId),
    enabled: !!customerId,
  });

  const members: TeamMember[] = data?.data ?? (Array.isArray(data) ? data as TeamMember[] : []);

  const addMutation = useMutation({
    mutationFn: () =>
      teamsApi.addMember(customerId, Number(form.user_id), form.role),
    onSuccess: () => {
      toast.success('Ekip uyesi eklendi');
      onTeamMemberChanged(queryClient, customerId);
      setIsModalOpen(false);
      setForm({ user_id: '', role: 'member' });
    },
    onError: () => toast.error('Ekip uyesi eklenemedi'),
  });

  const removeMutation = useMutation({
    mutationFn: (userId: number) => teamsApi.removeMember(customerId, userId),
    onSuccess: () => {
      toast.success('Ekip uyesi kaldırıldı');
      onTeamMemberChanged(queryClient, customerId);
      setRemoveTarget(null);
    },
    onError: () => toast.error('Ekip uyesi kaldirilamadi'),
  });

  if (isLoading) {
    return <Skeleton variant="card" />;
  }

  return (
    <>
      <Card
        title="Hesap Ekibi"
        action={
          <Button size="sm" onClick={() => setIsModalOpen(true)}>
            <UserPlus size={14} className="mr-1.5" />
            Ekip Uyesi Ekle
          </Button>
        }
      >
        {members.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-center">
            <Users size={32} className="mb-2 text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Henüz ekip uyesi eklenmemis
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {members.map((member) => (
              <li
                key={member.user_id}
                className="flex items-center justify-between py-3"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {getInitials(member.user_full_name)}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 dark:text-white truncate">
                      {member.user_full_name || `Kullanıcı #${member.user_id}`}
                    </p>
                    {member.user_email && (
                      <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                        {member.user_email}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      ROLE_BADGE_CLASSES[member.role] || ROLE_BADGE_CLASSES.viewer
                    }`}
                  >
                    {ROLE_LABELS[member.role] || member.role}
                  </span>
                  <button
                    type="button"
                    onClick={() => setRemoveTarget(member)}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors dark:hover:bg-red-900/20"
                    title="Kaldir"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Ekip Uyesi Ekle"
      >
        <div className="space-y-4">
          <Input
            label="Kullanıcı ID"
            type="number"
            value={form.user_id}
            onChange={(e) => setForm((prev) => ({ ...prev, user_id: e.target.value }))}
            placeholder="Kullanıcı ID girin"
          />
          <Select
            label="Rol"
            options={ROLE_OPTIONS}
            value={form.role}
            onChange={(e) => setForm((prev) => ({ ...prev, role: e.target.value }))}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              İptal
            </Button>
            <Button
              onClick={() => addMutation.mutate()}
              loading={addMutation.isPending}
              disabled={!form.user_id}
            >
              Ekle
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={!!removeTarget}
        onClose={() => setRemoveTarget(null)}
        onConfirm={() => {
          if (removeTarget) {
            removeMutation.mutate(removeTarget.user_id);
          }
        }}
        title="Ekip Uyesini Kaldir"
        message={`${removeTarget?.user_full_name || 'Bu kullanıcı'} ekipten kaldirilacak. Devam etmek istiyor musunuz?`}
        confirmLabel="Kaldir"
        confirmVariant="danger"
        isLoading={removeMutation.isPending}
      />
    </>
  );
}
