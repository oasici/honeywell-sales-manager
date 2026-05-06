import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ShieldCheck } from 'lucide-react';
import { useAuthStore } from '../../stores/authStore';
import { authApi } from '../../lib/api';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';

interface ForcePasswordForm {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
}

const schema = z
  .object({
    currentPassword: z.string().min(1, 'Mevcut sifre gereklidir'),
    newPassword: z
      .string()
      .min(8, 'Sifre en az 8 karakter olmalidir')
      .max(128, 'Sifre 128 karakteri asamaz'),
    confirmPassword: z.string().min(1, 'Sifreyi tekrar giriniz'),
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Sifreler uyusmuyor',
  })
  .refine((data) => data.newPassword !== data.currentPassword, {
    path: ['newPassword'],
    message: 'Yeni sifre mevcut sifreden farkli olmalidir',
  });

/**
 * R6-RENDER-4 — admin-reset / first-login users land here on success.
 * Until they change their temporary password, every other route is
 * blocked. Backend clears `password_change_required` on a successful
 * POST /auth/change-password, then we refresh the local user via
 * authApi.getMe() and unblock navigation.
 */
export function ForcePasswordChangePage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const setAuth = useAuthStore((s) => s.setAuth);
  const token = useAuthStore((s) => s.token);
  const refreshToken = useAuthStore((s) => s.refreshToken);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForcePasswordForm>({
    resolver: zodResolver(schema),
    defaultValues: { currentPassword: '', newPassword: '', confirmPassword: '' },
  });

  const onSubmit = async (values: ForcePasswordForm) => {
    try {
      await authApi.changePassword(values.currentPassword, values.newPassword);
      const me = await authApi.getMe();
      // Refresh the auth store so password_change_required clears and
      // AuthGuard stops routing back here.
      setAuth(token ?? '', refreshToken ?? '', me);
      toast.success('Sifreniz basariyla degistirildi');
      navigate('/', { replace: true });
    } catch (error: unknown) {
      const raw = (
        error as { response?: { data?: { detail?: unknown; error?: { message?: string } } } }
      )?.response?.data;
      let message = 'Sifre degistirme basarisiz, lutfen tekrar deneyin';
      if (raw?.error?.message) {
        message = raw.error.message;
      } else if (typeof raw?.detail === 'string') {
        message = raw.detail;
      }
      toast.error(message);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-[420px]">
        <div className="rounded-2xl border border-slate-200 bg-white p-7 shadow-(--shadow-sm) sm:p-8">
          <header className="mb-6">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-[10px] bg-honeywell-red/10 text-honeywell-red">
              <ShieldCheck size={18} />
            </span>
            <h2 className="mt-3 text-heading-2 text-slate-900">Sifrenizi yenileyin</h2>
            <p className="mt-1.5 text-[13px] text-slate-500">
              {user?.email ? `${user.email} ` : ''}hesabiniz icin gecici bir sifre kullaniliyor.
              Devam etmeden once yeni bir sifre belirlemeniz gerekiyor.
            </p>
          </header>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <Input
              label="Mevcut sifre"
              type="password"
              autoComplete="current-password"
              error={errors.currentPassword?.message}
              {...register('currentPassword')}
            />
            <Input
              label="Yeni sifre"
              type="password"
              autoComplete="new-password"
              error={errors.newPassword?.message}
              {...register('newPassword')}
            />
            <Input
              label="Yeni sifre (tekrar)"
              type="password"
              autoComplete="new-password"
              error={errors.confirmPassword?.message}
              {...register('confirmPassword')}
            />

            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={isSubmitting}
              className="w-full"
            >
              {isSubmitting ? 'Kaydediliyor...' : 'Sifreyi Degistir'}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default ForcePasswordChangePage;
