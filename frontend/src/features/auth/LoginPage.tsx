import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthStore } from '../../stores/authStore';
import { SalesSuitLogo } from '../../components/brand/SalesSuitLogo';
import { useT } from '../../hooks/useT';

type LoginForm = { email: string; password: string };

export function LoginPage() {
  const t = useT();

  const loginSchema = z.object({
    email: z.string().min(1, t('auth.email_required')).email(t('auth.email_invalid')),
    password: z.string().min(1, t('auth.password_required')),
  });

  const navigate = useNavigate();
  const location = useLocation();
  const login = useAuthStore((state) => state.login);

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/';

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = async (values: LoginForm) => {
    try {
      await login(values.email, values.password);
      toast.success(t('auth.login_success'));
      navigate(from, { replace: true });
    } catch (error: unknown) {
      const raw = (
        error as { response?: { data?: { detail?: unknown; error?: { message?: string } } } }
      )?.response?.data;
      let message = t('auth.login_failed');
      if (raw?.error?.message) {
        message = raw.error.message;
      } else if (typeof raw?.detail === 'string') {
        message = raw.detail;
      }
      toast.error(message);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 via-white to-red-50 px-4">
      <div className="w-full max-w-md">
        {/* Logo / Brand */}
        <div className="mb-10 flex flex-col items-center">
          <SalesSuitLogo size="lg" className="mb-4" />
          <p className="text-sm text-gray-400 tracking-wide">{t('auth.subtitle')}</p>
        </div>

        {/* Form Card */}
        <div className="card-modern p-8 sm:p-10">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            {/* Email */}
            <div>
              <label htmlFor="email" className="mb-2 block text-sm font-medium text-gray-600">
                {t('auth.email')}
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                placeholder={t('auth.email_placeholder')}
                className={`w-full rounded-xl border bg-gray-50/50 px-4 py-3 text-sm outline-none transition-all duration-200 focus:bg-white focus:border-honeywell-red focus:ring-2 focus:ring-honeywell-light focus:shadow-sm ${
                  errors.email ? 'border-red-400 bg-red-50/30' : 'border-gray-200'
                }`}
                {...register('email')}
              />
              {errors.email && (
                <p className="mt-1.5 text-xs text-red-500">{errors.email.message}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="mb-2 block text-sm font-medium text-gray-600">
                {t('auth.password')}
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="********"
                className={`w-full rounded-xl border bg-gray-50/50 px-4 py-3 text-sm outline-none transition-all duration-200 focus:bg-white focus:border-honeywell-red focus:ring-2 focus:ring-honeywell-light focus:shadow-sm ${
                  errors.password ? 'border-red-400 bg-red-50/30' : 'border-gray-200'
                }`}
                {...register('password')}
              />
              {errors.password && (
                <p className="mt-1.5 text-xs text-red-500">{errors.password.message}</p>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="btn-modern w-full bg-honeywell-red px-4 py-3 text-sm text-white shadow-lg shadow-red-200/50 hover:bg-honeywell-dark hover:shadow-xl hover:shadow-red-300/50 disabled:cursor-not-allowed disabled:opacity-60 active:scale-[0.97]"
            >
              {isSubmitting ? t('auth.logging_in') : t('auth.login')}
            </button>
          </form>
        </div>

        <p className="mt-8 text-center text-xs text-gray-400">{t('auth.footer')}</p>
      </div>
    </div>
  );
}
