import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthStore } from '../../stores/authStore';
import { SalesSuitLogo } from '../../components/brand/SalesSuitLogo';

const loginSchema = z.object({
  email: z.string().min(1, 'E-posta adresi gereklidir').email('Gecerli bir e-posta adresi giriniz'),
  password: z.string().min(1, 'Sifre gereklidir'),
});

type LoginForm = z.infer<typeof loginSchema>;

export function LoginPage() {
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
      toast.success('Giris basarili');
      navigate(from, { replace: true });
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Giris basarisiz. Lutfen bilgilerinizi kontrol ediniz.';
      toast.error(message);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md">
        {/* Logo / Brand */}
        <div className="mb-8 flex flex-col items-center">
          <SalesSuitLogo size="lg" className="mb-4" />
          <p className="text-sm text-gray-500">Hesabiniza giris yapiniz</p>
        </div>

        {/* Form Card */}
        <div className="rounded-xl bg-white p-8 shadow-lg">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            {/* Email */}
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-gray-700">
                E-posta
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="ornek@honeywell.com"
                className={`w-full rounded-lg border px-4 py-2.5 text-sm outline-none transition-colors focus:border-honeywell-red focus:ring-2 focus:ring-honeywell-light ${
                  errors.email ? 'border-red-400' : 'border-gray-300'
                }`}
                {...register('email')}
              />
              {errors.email && (
                <p className="mt-1 text-xs text-red-500">{errors.email.message}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-gray-700">
                Sifre
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="********"
                className={`w-full rounded-lg border px-4 py-2.5 text-sm outline-none transition-colors focus:border-honeywell-red focus:ring-2 focus:ring-honeywell-light ${
                  errors.password ? 'border-red-400' : 'border-gray-300'
                }`}
                {...register('password')}
              />
              {errors.password && (
                <p className="mt-1 text-xs text-red-500">{errors.password.message}</p>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-lg bg-honeywell-red px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-honeywell-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? 'Giris yapiliyor...' : 'Giris Yap'}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-gray-400">
          &copy; 2026 Honeywell Sales Suit. Tum haklar saklidir.
        </p>
      </div>
    </div>
  );
}
