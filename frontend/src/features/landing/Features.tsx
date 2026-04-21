import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Mail, Search, FileCheck, Shield, Bell, BarChart3, type LucideIcon } from 'lucide-react';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';

type Feature = {
  icon: LucideIcon;
  titleKey: TranslationKey;
  descKey: TranslationKey;
};

export default function Features() {
  const t = useT();

  const features: Feature[] = useMemo(
    () => [
      { icon: Mail, titleKey: 'landing.feat_1_title', descKey: 'landing.feat_1_desc' },
      { icon: Search, titleKey: 'landing.feat_2_title', descKey: 'landing.feat_2_desc' },
      { icon: FileCheck, titleKey: 'landing.feat_3_title', descKey: 'landing.feat_3_desc' },
      { icon: Shield, titleKey: 'landing.feat_4_title', descKey: 'landing.feat_4_desc' },
      { icon: Bell, titleKey: 'landing.feat_5_title', descKey: 'landing.feat_5_desc' },
      { icon: BarChart3, titleKey: 'landing.feat_6_title', descKey: 'landing.feat_6_desc' },
    ],
    [],
  );

  return (
    <section id="features" className="bg-white py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-red-600">
            {t('landing.features_label')}
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            {t('landing.features_title')}
          </h2>
        </motion.div>

        <div className="mt-14 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f, i) => (
            <motion.div
              key={f.titleKey}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08 }}
              className="group cursor-pointer rounded-2xl border border-slate-100 bg-slate-50/50 p-6 transition-all duration-300 hover:border-slate-200 hover:bg-white hover:shadow-lg"
            >
              <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white transition-colors duration-200 group-hover:bg-red-600">
                <f.icon size={18} />
              </div>
              <h3 className="mb-2 text-base font-bold text-slate-900">{t(f.titleKey)}</h3>
              <p className="text-sm leading-relaxed text-slate-600">{t(f.descKey)}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
