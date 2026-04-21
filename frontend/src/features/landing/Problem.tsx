import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Clock, AlertTriangle, FileX, Eye, ShieldAlert, type LucideIcon } from 'lucide-react';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';

type Pain = {
  icon: LucideIcon;
  statKey: TranslationKey;
  textKey: TranslationKey;
  color: string;
};

export default function Problem() {
  const t = useT();

  const pains: Pain[] = useMemo(
    () => [
      {
        icon: Clock,
        statKey: 'landing.pain_1_stat',
        textKey: 'landing.pain_1_text',
        color: 'text-red-600',
      },
      {
        icon: AlertTriangle,
        statKey: 'landing.pain_2_stat',
        textKey: 'landing.pain_2_text',
        color: 'text-amber-600',
      },
      {
        icon: FileX,
        statKey: 'landing.pain_3_stat',
        textKey: 'landing.pain_3_text',
        color: 'text-orange-600',
      },
      {
        icon: Eye,
        statKey: 'landing.pain_4_stat',
        textKey: 'landing.pain_4_text',
        color: 'text-slate-600',
      },
      {
        icon: ShieldAlert,
        statKey: 'landing.pain_5_stat',
        textKey: 'landing.pain_5_text',
        color: 'text-violet-600',
      },
    ],
    [],
  );

  return (
    <section className="bg-white py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.5 }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-red-600">
            {t('landing.problem_label')}
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            {t('landing.problem_title')}
          </h2>
          <p className="mt-4 text-base text-slate-600">{t('landing.problem_sub')}</p>
        </motion.div>

        <div className="mt-14 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {pains.map((pain, i) => {
            const Icon = pain.icon;
            return (
              <motion.div
                key={pain.statKey}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.08 }}
                className="group rounded-2xl border border-slate-100 bg-slate-50 p-5 transition-all duration-200 hover:border-slate-200 hover:shadow-md"
              >
                <Icon size={20} className={`mb-3 ${pain.color}`} />
                <p className={`text-2xl font-bold ${pain.color}`}>{t(pain.statKey)}</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-600">{t(pain.textKey)}</p>
              </motion.div>
            );
          })}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.3 }}
          className="mx-auto mt-12 max-w-xl rounded-2xl border border-amber-200 bg-amber-50 p-5 text-center"
        >
          <p className="text-sm font-semibold text-amber-900">{t('landing.problem_cost')}</p>
        </motion.div>
      </div>
    </section>
  );
}
