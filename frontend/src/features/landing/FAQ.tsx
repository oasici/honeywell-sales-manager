import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';

const FAQS = [
  {
    q: 'E-postalarimiz guvende mi?',
    a: 'Evet. Email sifreleri Fernet (AES-256) ile sifrelenir. IMAP baglantisi SSL/TLS uzerinden yapilir. Tüm veriler PostgreSQL\'de saklanir, erişim RBAC ile kontrol edilir. Denetim izi (audit trail) her işlemi kayıt altina alir.',
  },
  {
    q: 'AI yanlis yaparsa ne olur?',
    a: 'AI (Claude) her ayrıştırma sonucunu bir guven skoru ile sunar. Düşük guvenli sonuclar (<%75) otomatik olarak insan incelemesine yonlendirilir. Hicbir işlem otomatik onaylanmaz — her zaman bir insan karar verir. Hatali sonuclari duzeltebilir ve sistem bu duzeltmelerden ogrenir.',
  },
  {
    q: 'Kurulum ne kadar surer?',
    a: 'Tipik kurulum 1 is gunu. Email baglantisi, parça katalogu ve fiyat listesi yuklendikten sonra sistem kullanima hazir. Ekibinize rehberli egitim dahil.',
  },
  {
    q: 'Mevcut surecimiz bozulur mu?',
    a: 'Hayir. Sistem mevcut email akisinizin yanina eklenir — hicbir seyi degistirmez. Gelen kutunuz aynen calisir, sistem sadece kopyalari okur (readonly IMAP). Kademeli gecis için feature-flag destegi vardir.',
  },
  {
    q: 'Onay ve yetkilendirme nasil calisir?',
    a: 'Uc rol vardir: Satış Temsilcisi (teklif olusturur), Satış Yoneticisi (onaylar/reddeder + tüm verileri gorur), Operasyon (katalog/fiyat yönetimi). Her kullanıcı sadece yetkili oldugu verileri gorur ve işlem yapabilir.',
  },
  {
    q: 'Fiyat listesi ve katalog nasil yuklenir?',
    a: 'Excel (.xlsx), CSV veya PDF formatlarinda toplu import destegi vardir. Sistem Honeywell parça kodlarini otomatik tanir. Fiyat gecerlilik tarihleri, para birimi ve indirim oranlari da yuklenir.',
  },
];

function FAQItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-slate-100 last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center justify-between py-5 text-left"
      >
        <span className="pr-4 text-base font-semibold text-slate-900">{q}</span>
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
            <p className="pb-5 pr-8 text-sm leading-relaxed text-slate-600">{a}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function FAQ() {
  return (
    <section id="faq" className="bg-slate-50 py-20 md:py-28">
      <div className="mx-auto max-w-3xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">SSS</p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            Sik sorulan sorular
          </h2>
        </motion.div>

        <div className="mt-12 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          {FAQS.map((faq, i) => (
            <FAQItem key={i} q={faq.q} a={faq.a} />
          ))}
        </div>
      </div>
    </section>
  );
}
