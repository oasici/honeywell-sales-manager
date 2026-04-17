import { motion } from 'framer-motion';
import { Zap, Eye, Database } from 'lucide-react';

const PERSONAS = [
  {
    icon: Zap,
    role: 'Satış Temsilcisi',
    headline: 'Daha az manuel is, daha çok satış',
    bullets: [
      'Gelen talebi okuyup parcalari aramak yerine, AI ayristirsin ve eslessin.',
      'Tek tikla teklif taslagi olusur — sadece onayla ve gönder.',
      'Bildirimler ile kacan talep sifira iner.',
    ],
    color: 'border-blue-200 bg-blue-50',
    iconColor: 'bg-blue-600',
  },
  {
    icon: Eye,
    role: 'Satış Yoneticisi',
    headline: 'Pipeline gorunurlugu + kontrol',
    bullets: [
      'Dashboard\'da donusum orani, yanit süresi, temsilci performansi.',
      'Onay akisiyla her teklif kontrolden gecer.',
      'Denetim izi ile "kim ne degistirdi" sorusu cevapsiz kalmaz.',
    ],
    color: 'border-violet-200 bg-violet-50',
    iconColor: 'bg-violet-600',
  },
  {
    icon: Database,
    role: 'Operasyon',
    headline: 'Katalog, fiyat ve veri kalitesi',
    bullets: [
      'Excel/CSV/PDF ile parça ve fiyat listesi toplu import.',
      'Eksik fiyat, katalog disi parça uyarilari.',
      'Veri kalitesi paneli: hangi müşteri/teklif bilgisi eksik?',
    ],
    color: 'border-emerald-200 bg-emerald-50',
    iconColor: 'bg-emerald-600',
  },
];

export default function UseCases() {
  return (
    <section className="bg-slate-50 py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Kullanim Alanları</p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            Her rol için tasarlandi
          </h2>
        </motion.div>

        <div className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-3">
          {PERSONAS.map((p, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.12 }}
              className={`rounded-2xl border p-7 ${p.color}`}
            >
              <div className={`mb-4 inline-flex h-10 w-10 items-center justify-center rounded-xl text-white ${p.iconColor}`}>
                <p.icon size={18} />
              </div>
              <p className="text-xs font-bold uppercase tracking-widest text-slate-500">{p.role}</p>
              <h3 className="mt-2 text-lg font-bold text-slate-900">{p.headline}</h3>
              <ul className="mt-4 space-y-2">
                {p.bullets.map((b, j) => (
                  <li key={j} className="flex items-start gap-2 text-sm text-slate-700">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                    {b}
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
