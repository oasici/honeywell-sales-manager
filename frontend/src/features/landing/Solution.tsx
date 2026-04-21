import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Mail, Search, Send, ArrowRight, type LucideIcon } from 'lucide-react';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';

type Step = {
  num: string;
  icon: LucideIcon;
  titleKey: TranslationKey;
  descKey: TranslationKey;
  color: string;
};

export default function Solution() {
  const t = useT();

  const steps: Step[] = useMemo(
    () => [
      {
        num: '01',
        icon: Mail,
        titleKey: 'landing.sol_1_title',
        descKey: 'landing.sol_1_desc',
        color: 'from-blue-600 to-blue-500',
      },
      {
        num: '02',
        icon: Search,
        titleKey: 'landing.sol_2_title',
        descKey: 'landing.sol_2_desc',
        color: 'from-violet-600 to-violet-500',
      },
      {
        num: '03',
        icon: Send,
        titleKey: 'landing.sol_3_title',
        descKey: 'landing.sol_3_desc',
        color: 'from-red-600 to-red-500',
      },
    ],
    [],
  );

  return (
    <section id="solution" className="bg-slate-50 py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-green-600">
            {t('landing.solution_label')}
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            {t('landing.solution_title')}
          </h2>
        </motion.div>

        <div className="mt-16 grid grid-cols-1 gap-6 md:grid-cols-3">
          {steps.map((step, i) => (
            <motion.div
              key={step.num}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.15, duration: 0.5 }}
              className="group relative rounded-2xl border border-slate-200 bg-white p-7 transition-all duration-300 hover:shadow-lg"
            >
              <div
                className={`mb-5 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${step.color} text-sm font-bold text-white shadow-lg shadow-slate-900/10`}
              >
                <step.icon size={18} />
              </div>
              <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-slate-400">
                {t('landing.solution_step_prefix')} {step.num}
              </p>
              <h3 className="mb-3 text-lg font-bold text-slate-900">{t(step.titleKey)}</h3>
              <p className="text-sm leading-relaxed text-slate-600">{t(step.descKey)}</p>

              {i < 2 && (
                <div className="absolute right-0 top-1/2 hidden -translate-y-1/2 translate-x-1/2 md:block">
                  <ArrowRight size={16} className="text-slate-300" />
                </div>
              )}
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.3 }}
          className="mx-auto mt-12 flex max-w-xl items-start gap-3 rounded-2xl border border-blue-100 bg-blue-50 p-5"
        >
          <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white">
            <span className="text-[10px] font-bold">AI</span>
          </div>
          <div>
            <p className="text-sm font-semibold text-blue-900">{t('landing.solution_ai_title')}</p>
            <p className="mt-1 text-xs text-blue-700">{t('landing.solution_ai_body')}</p>
          </div>
        </motion.div>

        <div className="mt-10 text-center">
          <a
            href="#demo"
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-7 py-3.5 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition-all duration-200 hover:bg-slate-800"
          >
            {t('landing.demo')}
            <ArrowRight size={16} />
          </a>
        </div>
      </div>
    </section>
  );
}
