import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Menu, X } from 'lucide-react';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';

const NAV_KEYS: { key: TranslationKey; href: string }[] = [
  { key: 'landing.nav_features', href: '#features' },
  { key: 'landing.nav_how', href: '#solution' },
  { key: 'landing.nav_pricing', href: '#pricing' },
  { key: 'landing.nav_faq', href: '#faq' },
];

export default function Navbar() {
  const [open, setOpen] = useState(false);
  const t = useT();

  const links = useMemo(() => NAV_KEYS.map((item) => ({ ...item, label: t(item.key) })), [t]);

  return (
    <nav className="fixed top-4 left-4 right-4 z-50">
      <div className="mx-auto max-w-7xl rounded-2xl border border-slate-200/60 bg-white/80 px-6 py-3 shadow-lg shadow-slate-900/5 backdrop-blur-xl">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <a href="#" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-600">
              <span className="text-sm font-black text-white">H</span>
            </div>
            <span className="text-base font-bold tracking-tight text-slate-900">Sales Suite</span>
          </a>

          {/* Desktop links */}
          <div className="hidden items-center gap-8 md:flex">
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-sm font-medium text-slate-600 transition-colors duration-200 hover:text-slate-900"
              >
                {link.label}
              </a>
            ))}
          </div>

          {/* CTA */}
          <div className="hidden items-center gap-3 md:flex">
            <a
              href="/login"
              className="text-sm font-medium text-slate-600 transition-colors duration-200 hover:text-slate-900"
            >
              {t('landing.login')}
            </a>
            <a
              href="#demo"
              className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition-all duration-200 hover:bg-slate-800 hover:shadow-lg hover:shadow-slate-900/20"
            >
              {t('landing.demo')}
            </a>
          </div>

          {/* Mobile toggle */}
          <button
            type="button"
            onClick={() => setOpen(!open)}
            className="cursor-pointer rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-100 md:hidden"
            aria-label={t('landing.aria_menu')}
          >
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        {/* Mobile menu */}
        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden md:hidden"
            >
              <div className="flex flex-col gap-3 border-t border-slate-100 pt-4 pb-2">
                {links.map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    onClick={() => setOpen(false)}
                    className="rounded-lg px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
                  >
                    {link.label}
                  </a>
                ))}
                <a
                  href="#demo"
                  onClick={() => setOpen(false)}
                  className="mt-2 rounded-xl bg-slate-900 px-5 py-2.5 text-center text-sm font-semibold text-white"
                >
                  {t('landing.demo')}
                </a>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </nav>
  );
}
