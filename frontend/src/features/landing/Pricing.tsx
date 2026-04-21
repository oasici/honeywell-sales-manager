import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Check, ArrowRight } from 'lucide-react';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';

type Plan = {
  nameKey: TranslationKey;
  priceKey: TranslationKey;
  periodKey: TranslationKey;
  descKey: TranslationKey;
  ctaKey: TranslationKey;
  ctaStyle: string;
  featureKeys: TranslationKey[];
  popular: boolean;
};

export default function Pricing() {
  const t = useT();

  const plans: Plan[] = useMemo(
    () => [
      {
        nameKey: 'landing.plan_starter_name',
        priceKey: 'landing.plan_starter_price',
        periodKey: 'landing.plan_starter_period',
        descKey: 'landing.plan_starter_desc',
        ctaKey: 'landing.plan_starter_cta',
        ctaStyle:
          'border border-slate-200 bg-white text-slate-900 hover:border-slate-300 hover:shadow-md',
        featureKeys: [
          'landing.plan_starter_f1',
          'landing.plan_starter_f2',
          'landing.plan_starter_f3',
          'landing.plan_starter_f4',
          'landing.plan_starter_f5',
        ],
        popular: false,
      },
      {
        nameKey: 'landing.plan_pro_name',
        priceKey: 'landing.plan_pro_price',
        periodKey: 'landing.plan_pro_period',
        descKey: 'landing.plan_pro_desc',
        ctaKey: 'landing.plan_pro_cta',
        ctaStyle: 'bg-slate-900 text-white hover:bg-slate-800 shadow-lg shadow-slate-900/20',
        featureKeys: [
          'landing.plan_pro_f1',
          'landing.plan_pro_f2',
          'landing.plan_pro_f3',
          'landing.plan_pro_f4',
          'landing.plan_pro_f5',
          'landing.plan_pro_f6',
          'landing.plan_pro_f7',
          'landing.plan_pro_f8',
        ],
        popular: true,
      },
      {
        nameKey: 'landing.plan_ent_name',
        priceKey: 'landing.plan_ent_price',
        periodKey: 'landing.plan_ent_period',
        descKey: 'landing.plan_ent_desc',
        ctaKey: 'landing.plan_ent_cta',
        ctaStyle:
          'border border-slate-200 bg-white text-slate-900 hover:border-slate-300 hover:shadow-md',
        featureKeys: [
          'landing.plan_ent_f1',
          'landing.plan_ent_f2',
          'landing.plan_ent_f3',
          'landing.plan_ent_f4',
          'landing.plan_ent_f5',
          'landing.plan_ent_f6',
        ],
        popular: false,
      },
    ],
    [],
  );

  return (
    <section id="pricing" className="bg-white py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-red-600">
            {t('landing.nav_pricing')}
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            {t('landing.pricing_head')}
          </h2>
          <p className="mt-4 text-base text-slate-600">{t('landing.pricing_sub')}</p>
        </motion.div>

        <div className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-3">
          {plans.map((plan, i) => (
            <motion.div
              key={plan.nameKey}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className={`relative rounded-2xl border p-7 ${
                plan.popular
                  ? 'border-slate-900 bg-slate-50 shadow-xl shadow-slate-900/10'
                  : 'border-slate-200 bg-white'
              }`}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-slate-900 px-4 py-1 text-[10px] font-bold text-white">
                  {t('landing.pricing_popular')}
                </div>
              )}

              <p className="text-sm font-bold text-slate-900">{t(plan.nameKey)}</p>
              <div className="mt-3 flex items-baseline gap-1">
                <span className="text-4xl font-extrabold text-slate-900">{t(plan.priceKey)}</span>
                {t(plan.periodKey) ? (
                  <span className="text-sm text-slate-500">{t(plan.periodKey)}</span>
                ) : null}
              </div>
              <p className="mt-2 text-sm text-slate-600">{t(plan.descKey)}</p>

              <a
                href="#demo"
                className={`mt-6 flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition-all duration-200 ${plan.ctaStyle}`}
              >
                {t(plan.ctaKey)}
                <ArrowRight size={14} />
              </a>

              <ul className="mt-6 space-y-2.5 border-t border-slate-100 pt-6">
                {plan.featureKeys.map((fk) => (
                  <li key={fk} className="flex items-start gap-2 text-sm text-slate-700">
                    <Check size={14} className="mt-0.5 shrink-0 text-green-500" />
                    {t(fk)}
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
