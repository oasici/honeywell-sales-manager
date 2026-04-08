import { motion } from 'framer-motion';
import { Clock, AlertTriangle, FileX, Eye, ShieldAlert } from 'lucide-react';

const PAINS = [
  { icon: Clock, stat: '4+ saat', text: 'E-postadan teklife ortalama sure', color: 'text-red-600' },
  { icon: AlertTriangle, stat: '%15', text: 'Kacan talepler (okunmamis/unutulmus)', color: 'text-amber-600' },
  { icon: FileX, stat: '%22', text: 'Hatali fiyatlandirma ve indirim tutarsizligi', color: 'text-orange-600' },
  { icon: Eye, stat: 'Sifir', text: 'Pipeline gorunurlugu — kim ne asamada?', color: 'text-slate-600' },
  { icon: ShieldAlert, stat: 'Risk', text: '"Kim degistirdi?" sorusunun cevapsiz kalmasi', color: 'text-violet-600' },
];

export default function Problem() {
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
          <p className="text-xs font-semibold uppercase tracking-widest text-red-600">Sorun</p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            Yedek parca satis sureci neden hala 2005 modeli?
          </h2>
          <p className="mt-4 text-base text-slate-600">
            E-posta kutusundan Excel'e, Excel'den PDF'e, PDF'den tekrar e-postaya.
            Her adimda veri kaybi, zaman kaybi ve kontrol kaybi.
          </p>
        </motion.div>

        <div className="mt-14 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {PAINS.map((pain, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              className="group rounded-2xl border border-slate-100 bg-slate-50 p-5 transition-all duration-200 hover:border-slate-200 hover:shadow-md"
            >
              <pain.icon size={20} className={`mb-3 ${pain.color}`} />
              <p className={`text-2xl font-bold ${pain.color}`}>{pain.stat}</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">{pain.text}</p>
            </motion.div>
          ))}
        </div>

        {/* Cost snippet */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.3 }}
          className="mx-auto mt-12 max-w-xl rounded-2xl border border-amber-200 bg-amber-50 p-5 text-center"
        >
          <p className="text-sm font-semibold text-amber-900">
            20 kisilik bir satis ekibi icin bu, yilda tahmini{' '}
            <span className="text-lg font-bold">1.200+ saat</span> ve{' '}
            <span className="text-lg font-bold">%8-15 gelir kaybi</span> demek.
          </p>
        </motion.div>
      </div>
    </section>
  );
}
