import { motion } from 'framer-motion';
import { TrendingDown, TrendingUp, Clock, Shield, Lock, Server } from 'lucide-react';

const METRICS = [
  { icon: TrendingDown, value: '%60', label: 'Daha hizli teklif hazirlama', desc: 'Beklenen etki: 4+ saatten 90 dakikanin altina' },
  { icon: TrendingUp, value: '%35', label: 'Daha yuksek donusum orani', desc: 'Beklenen etki: hizli yanit + tutarli fiyatlandirma' },
  { icon: Clock, value: '0', label: 'Kacan talep', desc: 'Beklenen etki: otomatik tarama + bildirimler' },
];

const TRUST_SIGNALS = [
  { icon: Shield, label: 'RBAC + rol bazli erisim', desc: 'sales_rep, sales_manager, operations — her rol sadece yetkili oldugu verileri gorur.' },
  { icon: Lock, label: 'Fernet sifreleme + audit trail', desc: 'Email sifreleri AES ile korunur. Her islem denetim izinde kayitlidir.' },
  { icon: Server, label: 'Multi-worker + Redis', desc: 'Gunicorn 4 worker, Redis paylasimli state, PgBouncer connection pooling.' },
];

export default function Proof() {
  return (
    <section className="bg-slate-900 py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-red-400">Beklenen Etki</p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-white md:text-4xl">
            Rakamlarla donusum
          </h2>
        </motion.div>

        {/* Metrics */}
        <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-3">
          {METRICS.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="rounded-2xl border border-slate-700 bg-slate-800/50 p-6 text-center"
            >
              <m.icon size={24} className="mx-auto mb-3 text-red-400" />
              <p className="text-4xl font-extrabold text-white">{m.value}</p>
              <p className="mt-1 text-sm font-semibold text-slate-300">{m.label}</p>
              <p className="mt-2 text-xs text-slate-500">{m.desc}</p>
            </motion.div>
          ))}
        </div>

        {/* Trust signals */}
        <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-3">
          {TRUST_SIGNALS.map((t, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.2 + i * 0.1 }}
              className="flex items-start gap-3 rounded-xl border border-slate-700/50 bg-slate-800/30 p-4"
            >
              <t.icon size={18} className="mt-0.5 shrink-0 text-green-400" />
              <div>
                <p className="text-sm font-semibold text-white">{t.label}</p>
                <p className="mt-1 text-xs text-slate-400">{t.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
