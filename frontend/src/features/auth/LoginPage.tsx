import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { ShieldCheck, Sparkles, Lock } from 'lucide-react';
import { useAuthStore } from '../../stores/authStore';
import { SalesSuitLogo } from '../../components/brand/SalesSuitLogo';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { useT } from '../../hooks/useT';

type LoginForm = { email: string; password: string };

/**
 * LoginPage — split-screen marketing + auth surface.
 *
 * Visual:
 *   - Left: brand panel with marketing pitch + value bullets. Hidden under
 *     lg: so the form is always full-width on tablet/mobile.
 *   - Right: auth card on a soft slate canvas. Inputs use the design-system
 *     Input primitive (44px / 12px radius / 3px focus ring).
 *
 * Why split-screen:
 *   - First impression matters; a centered card on a beige gradient looks like
 *     a generic admin tool. The split panel asserts "this is a product."
 *   - Trust signal bullets address procurement-style questions without making
 *     the user click a marketing site.
 */
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

  const trustBullets = [
    {
      icon: <ShieldCheck size={16} />,
      title: 'KVKK uyumlu altyapı',
      body: 'Veriler şifreli depolanır, denetim kayıtları otomatik tutulur.',
    },
    {
      icon: <Sparkles size={16} />,
      title: 'AI destekli boru hattı',
      body: 'Claude tabanlı parser; e-posta → teklif → fırsat tek akışta.',
    },
    {
      icon: <Lock size={16} />,
      title: 'Rol tabanlı erişim',
      body: 'Saha ekibi, yöneticiler ve admin için ayrı yetki katmanları.',
    },
  ];

  return (
    <div className="grid min-h-screen grid-cols-1 bg-slate-50 lg:grid-cols-[5fr_6fr]">
      {/* ─── Brand panel (lg+) ─────────────────────────────────────────── */}
      <aside className="relative hidden overflow-hidden bg-slate-950 text-white lg:flex lg:flex-col lg:justify-between lg:px-12 lg:py-14">
        {/* Subtle ambient glow — adds depth without looking like a stock gradient.
            Two radial blots: brand-red top-left, slate-700 bottom-right. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.55]"
          style={{
            background:
              'radial-gradient(60% 50% at 15% 10%, rgba(229,57,53,0.18), transparent 60%), radial-gradient(50% 50% at 85% 90%, rgba(71,85,105,0.35), transparent 70%)',
          }}
        />
        {/* Faint grid texture */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.6) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
          }}
        />

        <div className="relative">
          <div className="flex items-center gap-2">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-[10px] bg-honeywell-red text-[15px] font-bold text-white ring-1 ring-honeywell-red/40">
              H
            </span>
            <div className="leading-tight">
              <p className="text-[15px] font-semibold">Honeywell</p>
              <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                Sales Suite
              </p>
            </div>
          </div>
        </div>

        <div className="relative max-w-md">
          <p className="text-[11px] uppercase tracking-[0.14em] text-honeywell-red/80">
            B2B revenue OS
          </p>
          <h1 className="mt-3 text-[40px] font-bold leading-[1.1] tracking-tight">
            Boru hattı, teklif ve müşteri zekâsı tek panelde.
          </h1>
          <p className="mt-4 text-[15px] leading-relaxed text-slate-300">
            E-postadan teklife, sinyalden tahmine — saha ekibinizin günlük
            iş akışını hızlandıran modern satış komuta merkezi.
          </p>

          <ul className="mt-10 space-y-4">
            {trustBullets.map((bullet) => (
              <li key={bullet.title} className="flex items-start gap-3">
                <span className="mt-0.5 inline-flex h-8 w-8 items-center justify-center rounded-[10px] bg-white/5 text-white ring-1 ring-inset ring-white/10">
                  {bullet.icon}
                </span>
                <div className="min-w-0">
                  <p className="text-[13px] font-semibold text-white">{bullet.title}</p>
                  <p className="mt-0.5 text-[12px] leading-relaxed text-slate-400">
                    {bullet.body}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative flex items-center gap-3 text-[11px] text-slate-500">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 ring-2 ring-emerald-400/30" />
          Tüm sistemler operasyonel
          <span className="ml-auto">© {new Date().getFullYear()} Honeywell</span>
        </div>
      </aside>

      {/* ─── Auth panel ────────────────────────────────────────────────── */}
      <main className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-[400px]">
          {/* Mobile-only brand mark */}
          <div className="mb-8 flex items-center justify-center lg:hidden">
            <SalesSuitLogo size="lg" />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-7 shadow-(--shadow-sm) sm:p-8">
            <header className="mb-6">
              <h2 className="text-heading-2 text-slate-900">Tekrar hoş geldiniz</h2>
              <p className="mt-1.5 text-[13px] text-slate-500">
                Hesabınıza giriş yaparak panele devam edin.
              </p>
            </header>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <Input
                label={t('auth.email')}
                type="email"
                autoComplete="email"
                placeholder={t('auth.email_placeholder')}
                error={errors.email?.message}
                {...register('email')}
              />

              <Input
                label={t('auth.password')}
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                error={errors.password?.message}
                {...register('password')}
              />

              <Button
                type="submit"
                variant="primary"
                size="lg"
                loading={isSubmitting}
                className="w-full"
              >
                {isSubmitting ? t('auth.logging_in') : t('auth.login')}
              </Button>
            </form>
          </div>

          <p className="mt-6 text-center text-[12px] text-slate-500">
            {t('auth.footer')}
          </p>
        </div>
      </main>
    </div>
  );
}
