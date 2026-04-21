import { motion } from 'framer-motion';
import { ArrowRight, Shield, Clock, Headphones } from 'lucide-react';
import { useT } from '../../hooks/useT';

export default function FinalCTA() {
  const t = useT();

  return (
    <section id="demo" className="relative overflow-hidden bg-slate-900 py-20 md:py-28">
      {/* Glow */}
      <div className="absolute top-1/2 left-1/2 -z-0 h-[400px] w-[400px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-red-600/10 blur-3xl" />

      <div className="relative z-10 mx-auto max-w-3xl px-6 text-center">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-3xl font-extrabold tracking-tight text-white md:text-5xl">
            {t('landing.final_title_1')}
            <br />
            <span className="bg-gradient-to-r from-red-400 to-red-500 bg-clip-text text-transparent">
              {t('landing.final_title_2')}
            </span>
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-base text-slate-400">{t('landing.final_sub')}</p>

          <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <a
              href="mailto:sales@honeywell-sales.com?subject=Demo%20Talebi"
              className="group flex items-center gap-2 rounded-xl bg-red-600 px-8 py-4 text-sm font-bold text-white shadow-lg shadow-red-600/30 transition-all duration-200 hover:bg-red-500 hover:shadow-xl"
            >
              {t('landing.demo')}
              <ArrowRight
                size={16}
                className="transition-transform duration-200 group-hover:translate-x-0.5"
              />
            </a>
            <a
              href="mailto:sales@honeywell-sales.com?subject=Deneme%20Talebi"
              className="flex items-center gap-2 rounded-xl border border-slate-600 px-8 py-4 text-sm font-semibold text-slate-300 transition-all duration-200 hover:border-slate-500 hover:text-white"
            >
              {t('landing.trial_14')}
            </a>
          </div>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-5 text-xs text-slate-500">
            <span className="flex items-center gap-1.5">
              <Shield size={12} className="text-green-400" /> {t('landing.trust_rbac')}
            </span>
            <span className="flex items-center gap-1.5">
              <Clock size={12} className="text-blue-400" /> {t('landing.trust_setup')}
            </span>
            <span className="flex items-center gap-1.5">
              <Headphones size={12} className="text-violet-400" /> {t('landing.trust_onboard')}
            </span>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
