import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';

type FaqItem = { qKey: TranslationKey; aKey: TranslationKey };

function FAQItem({ qKey, aKey }: FaqItem) {
  const t = useT();
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-slate-100 last:border-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center justify-between py-5 text-left"
      >
        <span className="pr-4 text-base font-semibold text-slate-900">{t(qKey)}</span>
        <ChevronDown
          size={18}
          className={`shrink-0 text-slate-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <p className="pb-5 pr-8 text-sm leading-relaxed text-slate-600">{t(aKey)}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function FAQ() {
  const t = useT();

  const items: FaqItem[] = useMemo(
    () => [
      { qKey: 'landing.faq_q1', aKey: 'landing.faq_a1' },
      { qKey: 'landing.faq_q2', aKey: 'landing.faq_a2' },
      { qKey: 'landing.faq_q3', aKey: 'landing.faq_a3' },
      { qKey: 'landing.faq_q4', aKey: 'landing.faq_a4' },
      { qKey: 'landing.faq_q5', aKey: 'landing.faq_a5' },
      { qKey: 'landing.faq_q6', aKey: 'landing.faq_a6' },
    ],
    [],
  );

  return (
    <section id="faq" className="bg-slate-50 py-20 md:py-28">
      <div className="mx-auto max-w-3xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            {t('landing.faq_label')}
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            {t('landing.faq_title')}
          </h2>
        </motion.div>

        <div className="mt-12 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          {items.map((faq) => (
            <FAQItem key={faq.qKey} qKey={faq.qKey} aKey={faq.aKey} />
          ))}
        </div>
      </div>
    </section>
  );
}
