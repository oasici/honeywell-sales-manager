import { motion } from 'framer-motion';
import { Mail, Search, FileCheck, Shield, Bell, BarChart3 } from 'lucide-react';

const FEATURES = [
  {
    icon: Mail,
    title: 'Email → Teklif Otomasyonu',
    desc: 'IMAP ile gelen kutusunu tarayin. AI, her e-postadan musteri adini, parca kodlarini ve miktarlari cikarir. Manuel kopyala-yapistir tarih oldu.',
  },
  {
    icon: Search,
    title: 'Akilli Parca Eslestirme',
    desc: '5 stratejiyle (tam kod, prefix, fuzzy, isim, semantik) katalogunuzdaki 4000+ parcayi saniyede eslestirir. Guven skoru ile sunar.',
  },
  {
    icon: FileCheck,
    title: 'Onay Akisi + PDF Uretim',
    desc: 'Manager tek tikla onaylar, profesyonel PDF otomatik olusur, musteri e-postasi ek ile gonderilir. Tum surecler denetim izinde.',
  },
  {
    icon: Shield,
    title: 'Denetim Izi (Audit Trail)',
    desc: 'Her islem — olusturma, guncelleme, onay, gonderim — kimin, ne zaman, ne yaptigi ile kayit altindadir. Uyumluluk icin hazir.',
  },
  {
    icon: Bell,
    title: 'Bildirimler + Is Kuyrugu',
    desc: 'Yeni talepler, onay bekleyen teklifler, suresi dolan firsatlar anlik bildirimlerle takip edilir. Hicbir sey gozden kacar kacirilmaz.',
  },
  {
    icon: BarChart3,
    title: 'Raporlar + Musteri Sagligi',
    desc: 'Donusum orani, yanit suresi, temsilci performansi, indirim analizi, musteri saglik skoru. Yoneticiler icin tek ekranda.',
  },
];

export default function Features() {
  return (
    <section id="features" className="bg-white py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-red-600">Ozellikler</p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            Satis surecinin her adiminida kapsayan tek platform
          </h2>
        </motion.div>

        <div className="mt-14 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08 }}
              className="group cursor-pointer rounded-2xl border border-slate-100 bg-slate-50/50 p-6 transition-all duration-300 hover:border-slate-200 hover:bg-white hover:shadow-lg"
            >
              <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white transition-colors duration-200 group-hover:bg-red-600">
                <f.icon size={18} />
              </div>
              <h3 className="mb-2 text-base font-bold text-slate-900">{f.title}</h3>
              <p className="text-sm leading-relaxed text-slate-600">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
