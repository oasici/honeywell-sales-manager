import { motion } from 'framer-motion';
import { Mail, Search, Send, ArrowRight } from 'lucide-react';

const STEPS = [
  {
    num: '01',
    icon: Mail,
    title: 'Email Yakala + Ayikla',
    desc: 'IMAP ile gelen kutusu taranir. AI (Claude) e-postayi ayristirir: musteri, parca kodlari, miktarlar, aciliyet. Dusuk guvenli sonuclar insan onayina sunulur.',
    color: 'from-blue-600 to-blue-500',
  },
  {
    num: '02',
    icon: Search,
    title: 'Parca Eslesir + Teklif Hazirla',
    desc: '4000+ parcalik katalogda fuzzy eslestirme. Kod, isim, semantik benzerlik ile en yakin parcalar bulunur. Fiyat otomatik cekilir, teklif taslagi olusur.',
    color: 'from-violet-600 to-violet-500',
  },
  {
    num: '03',
    icon: Send,
    title: 'Onayla + PDF + Gonder + Izle',
    desc: 'Manager onaylar, profesyonel PDF uretilir, musteri e-postasi tek tikla gonderilir. Her adim denetim izinde. Bildirimler anlik.',
    color: 'from-red-600 to-red-500',
  },
];

export default function Solution() {
  return (
    <section id="solution" className="bg-slate-50 py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-green-600">Cozum</p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            3 adimda: e-postadan profesyonel teklife
          </h2>
        </motion.div>

        <div className="mt-16 grid grid-cols-1 gap-6 md:grid-cols-3">
          {STEPS.map((step, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.15, duration: 0.5 }}
              className="group relative rounded-2xl border border-slate-200 bg-white p-7 transition-all duration-300 hover:shadow-lg"
            >
              {/* Step number */}
              <div className={`mb-5 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${step.color} text-sm font-bold text-white shadow-lg shadow-slate-900/10`}>
                <step.icon size={18} />
              </div>
              <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-slate-400">Adim {step.num}</p>
              <h3 className="mb-3 text-lg font-bold text-slate-900">{step.title}</h3>
              <p className="text-sm leading-relaxed text-slate-600">{step.desc}</p>

              {/* Arrow connector (desktop) */}
              {i < 2 && (
                <div className="absolute right-0 top-1/2 hidden -translate-y-1/2 translate-x-1/2 md:block">
                  <ArrowRight size={16} className="text-slate-300" />
                </div>
              )}
            </motion.div>
          ))}
        </div>

        {/* AI callout */}
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
            <p className="text-sm font-semibold text-blue-900">AI onermede bulunur, insan karar verir.</p>
            <p className="mt-1 text-xs text-blue-700">
              Parca eslestirme ve kategori tahmini AI desteklidir. Ancak her oneri
              guven skoru ile sunulur ve dusuk guvenli sonuclar otomatik olarak
              insan incelemesine yonlendirilir. Hicbir islem otomatik onaylanmaz.
            </p>
          </div>
        </motion.div>

        {/* Mid-CTA */}
        <div className="mt-10 text-center">
          <a
            href="#demo"
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-7 py-3.5 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition-all duration-200 hover:bg-slate-800"
          >
            Demo Planla
            <ArrowRight size={16} />
          </a>
        </div>
      </div>
    </section>
  );
}
