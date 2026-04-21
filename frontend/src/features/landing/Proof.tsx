import { useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  TrendingDown,
  TrendingUp,
  Clock,
  Shield,
  Lock,
  Server,
  type LucideIcon,
} from 'lucide-react';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';

type Metric = {
  icon: LucideIcon;
  valueKey: TranslationKey;
  labelKey: TranslationKey;
  descKey: TranslationKey;
};

type Trust = {
  icon: LucideIcon;
  labelKey: TranslationKey;
  descKey: TranslationKey;
};

export default function Proof() {
  const t = useT();

  const metrics: Metric[] = useMemo(
    () => [
      {
        icon: TrendingDown,
        valueKey: 'landing.proof_m1_val',
        labelKey: 'landing.proof_m1_label',
        descKey: 'landing.proof_m1_desc',
      },
      {
        icon: TrendingUp,
        valueKey: 'landing.proof_m2_val',
        labelKey: 'landing.proof_m2_label',
        descKey: 'landing.proof_m2_desc',
      },
      {
        icon: Clock,
        valueKey: 'landing.proof_m3_val',
        labelKey: 'landing.proof_m3_label',
        descKey: 'landing.proof_m3_desc',
      },
    ],
    [],
  );

  const trustSignals: Trust[] = useMemo(
    () => [
      { icon: Shield, labelKey: 'landing.proof_t1_label', descKey: 'landing.proof_t1_desc' },
      { icon: Lock, labelKey: 'landing.proof_t2_label', descKey: 'landing.proof_t2_desc' },
      { icon: Server, labelKey: 'landing.proof_t3_label', descKey: 'landing.proof_t3_desc' },
    ],
    [],
  );

  return (
    <section className="bg-slate-900 py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-red-400">
            {t('landing.proof_label')}
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-white md:text-4xl">
            {t('landing.proof_title')}
          </h2>
        </motion.div>

        <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-3">
          {metrics.map((m, i) => {
            const MetricIcon = m.icon;
            return (
              <motion.div
                key={m.valueKey}
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="rounded-2xl border border-slate-700 bg-slate-800/50 p-6 text-center"
              >
                <MetricIcon size={24} className="mx-auto mb-3 text-red-400" />
                <p className="text-4xl font-extrabold text-white">{t(m.valueKey)}</p>
                <p className="mt-1 text-sm font-semibold text-slate-300">{t(m.labelKey)}</p>
                <p className="mt-2 text-xs text-slate-500">{t(m.descKey)}</p>
              </motion.div>
            );
          })}
        </div>

        <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-3">
          {trustSignals.map((item, i) => {
            const TrustIcon = item.icon;
            return (
              <motion.div
                key={item.labelKey}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.2 + i * 0.1 }}
                className="flex items-start gap-3 rounded-xl border border-slate-700/50 bg-slate-800/30 p-4"
              >
                <TrustIcon size={18} className="mt-0.5 shrink-0 text-green-400" />
                <div>
                  <p className="text-sm font-semibold text-white">{t(item.labelKey)}</p>
                  <p className="mt-1 text-xs text-slate-400">{t(item.descKey)}</p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
