import { useT } from '../../hooks/useT';

export default function Footer() {
  const t = useT();
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-slate-200 bg-white py-12">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-4">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-600">
                <span className="text-sm font-black text-white">H</span>
              </div>
              <span className="text-base font-bold tracking-tight text-slate-900">Sales Suite</span>
            </div>
            <p className="mt-3 text-sm text-slate-500">{t('landing.footer_tagline')}</p>
          </div>

          {/* Product */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
              {t('landing.footer_product')}
            </h4>
            <ul className="mt-3 space-y-2 text-sm text-slate-600">
              <li>
                <a href="#features" className="transition-colors hover:text-slate-900">
                  {t('landing.nav_features')}
                </a>
              </li>
              <li>
                <a href="#pricing" className="transition-colors hover:text-slate-900">
                  {t('landing.nav_pricing')}
                </a>
              </li>
              <li>
                <a href="#solution" className="transition-colors hover:text-slate-900">
                  {t('landing.nav_how')}
                </a>
              </li>
              <li>
                <a href="#faq" className="transition-colors hover:text-slate-900">
                  {t('landing.nav_faq')}
                </a>
              </li>
            </ul>
          </div>

          {/* Company */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
              {t('landing.footer_company')}
            </h4>
            <ul className="mt-3 space-y-2 text-sm text-slate-600">
              <li>
                <a href="/login" className="transition-colors hover:text-slate-900">
                  {t('landing.login')}
                </a>
              </li>
              <li>
                <a href="#demo" className="transition-colors hover:text-slate-900">
                  {t('landing.demo')}
                </a>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
              {t('landing.footer_security')}
            </h4>
            <ul className="mt-3 space-y-2 text-sm text-slate-600">
              <li>{t('landing.footer_sec_rbac')}</li>
              <li>{t('landing.footer_sec_aes')}</li>
              <li>{t('landing.footer_sec_kvkk')}</li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-slate-100 pt-6 text-center text-xs text-slate-400">
          © {year} Honeywell Sales Suite. {t('landing.footer_rights')}
        </div>
      </div>
    </footer>
  );
}
