import { motion } from 'framer-motion';
import { Check, ArrowRight } from 'lucide-react';

const PLANS = [
  {
    name: 'Starter',
    price: '$49',
    period: '/kullanici/ay',
    desc: 'Kucuk ekipler icin temel satis otomasyonu.',
    cta: 'Baslat',
    ctaStyle: 'border border-slate-200 bg-white text-slate-900 hover:border-slate-300 hover:shadow-md',
    features: [
      '5 kullaniciya kadar',
      'Email ayristirma (gunluk 50)',
      'Teklif olusturma + PDF',
      'Temel raporlar',
      'Email destek',
    ],
    popular: false,
  },
  {
    name: 'Pro',
    price: '$89',
    period: '/kullanici/ay',
    desc: 'Buyuyen ekipler icin tam ozellik.',
    cta: 'Pro ile Basla',
    ctaStyle: 'bg-slate-900 text-white hover:bg-slate-800 shadow-lg shadow-slate-900/20',
    features: [
      '25 kullaniciya kadar',
      'Sinirsiz email ayristirma',
      'Onay akisi + RBAC',
      'Denetim izi (audit trail)',
      'Gelismis analitik + raporlar',
      'Musteri sagligi skoru',
      'Bildirimler + is kuyrugu',
      'Oncelikli destek',
    ],
    popular: true,
  },
  {
    name: 'Enterprise',
    price: 'Ozel',
    period: '',
    desc: 'Buyuk organizasyonlar icin tam kontrol.',
    cta: 'Goruselim',
    ctaStyle: 'border border-slate-200 bg-white text-slate-900 hover:border-slate-300 hover:shadow-md',
    features: [
      'Sinirsiz kullanici',
      'Ozel entegrasyonlar (CRM/ERP)',
      'SalesBoard v2 (kanban + AI)',
      'SSO + gelismis guvenlik',
      'SLA garantisi',
      'Ozel egitim + teknik danismanlik',
    ],
    popular: false,
  },
];

export default function Pricing() {
  return (
    <section id="pricing" className="bg-white py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-red-600">Fiyatlar</p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            Ekip buyuklugune gore esnek planlar
          </h2>
          <p className="mt-4 text-base text-slate-600">
            14 gun rehberli deneme. Kredi karti gerekmez.
          </p>
        </motion.div>

        <div className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-3">
          {PLANS.map((plan, i) => (
            <motion.div
              key={i}
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
                  EN POPULER
                </div>
              )}

              <p className="text-sm font-bold text-slate-900">{plan.name}</p>
              <div className="mt-3 flex items-baseline gap-1">
                <span className="text-4xl font-extrabold text-slate-900">{plan.price}</span>
                {plan.period && <span className="text-sm text-slate-500">{plan.period}</span>}
              </div>
              <p className="mt-2 text-sm text-slate-600">{plan.desc}</p>

              <a
                href="#demo"
                className={`mt-6 flex w-full items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition-all duration-200 cursor-pointer ${plan.ctaStyle}`}
              >
                {plan.cta}
                <ArrowRight size={14} />
              </a>

              <ul className="mt-6 space-y-2.5 border-t border-slate-100 pt-6">
                {plan.features.map((f, j) => (
                  <li key={j} className="flex items-start gap-2 text-sm text-slate-700">
                    <Check size={14} className="mt-0.5 shrink-0 text-green-500" />
                    {f}
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
