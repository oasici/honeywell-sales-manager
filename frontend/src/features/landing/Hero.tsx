import { motion } from 'framer-motion';
import { ArrowRight, Play, Mail, FileText, CheckCircle, BarChart3, Shield } from 'lucide-react';

function DashboardMock() {
  return (
    <div className="relative mx-auto w-full max-w-4xl">
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-900/10">
        {/* Titlebar */}
        <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50 px-4 py-2.5">
          <div className="flex gap-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-red-400" />
            <div className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
            <div className="h-2.5 w-2.5 rounded-full bg-green-400" />
          </div>
          <div className="mx-auto rounded-md bg-slate-100 px-12 py-1 text-[10px] text-slate-400">
            app.honeywell-sales.com
          </div>
        </div>

        {/* Dashboard content */}
        <div className="flex">
          {/* Sidebar */}
          <div className="hidden w-48 border-r border-slate-100 bg-slate-900 p-3 md:block">
            <div className="mb-4 flex items-center gap-2">
              <div className="h-5 w-5 rounded bg-red-600/20" />
              <span className="text-[10px] font-bold text-white">Honeywell Sales</span>
            </div>
            {[
              { icon: BarChart3, label: 'Dashboard', active: true },
              { icon: Mail, label: 'E-postalar', active: false },
              { icon: FileText, label: 'Teklifler', active: false },
              { icon: Shield, label: 'Denetim', active: false },
            ].map((item, i) => (
              <div
                key={i}
                className={`mb-1 flex items-center gap-2 rounded-lg px-2 py-1.5 ${item.active ? 'bg-red-600/10 text-red-400' : 'text-slate-500'}`}
              >
                <item.icon size={12} />
                <span className="text-[10px]">{item.label}</span>
              </div>
            ))}
          </div>

          {/* Main content */}
          <div className="flex-1 p-4">
            {/* KPI row */}
            <div className="mb-3 grid grid-cols-4 gap-2">
              {[
                { label: 'Teklifler', value: '142', color: 'text-slate-900' },
                { label: 'Gonderilen', value: '89', color: 'text-green-600' },
                { label: 'Bekleyen', value: '12', color: 'text-amber-600' },
                { label: 'Donusum', value: '%62', color: 'text-blue-600' },
              ].map((kpi, i) => (
                <div key={i} className="rounded-lg border border-slate-100 bg-white p-2">
                  <p className="text-[8px] text-slate-500">{kpi.label}</p>
                  <p className={`text-lg font-bold ${kpi.color}`}>{kpi.value}</p>
                </div>
              ))}
            </div>

            {/* Chart area */}
            <div className="mb-3 rounded-lg border border-slate-100 bg-white p-3">
              <p className="mb-2 text-[9px] font-semibold text-slate-700">Aylik Teklif Trendi</p>
              <div className="flex h-16 items-end gap-1">
                {[40, 55, 35, 65, 50, 80, 70, 90, 75, 95, 85, 100].map((h, i) => (
                  <div
                    key={i}
                    className="flex-1 rounded-t bg-gradient-to-t from-red-600 to-red-400 opacity-80"
                    style={{ height: `${h}%` }}
                  />
                ))}
              </div>
            </div>

            {/* Recent items */}
            <div className="rounded-lg border border-slate-100 bg-white p-3">
              <p className="mb-2 text-[9px] font-semibold text-slate-700">Son E-postalar</p>
              {[
                'KORDSA A.S. — Turbinmetre talebi',
                'DEMIOREN — Sensor fiyat istegi',
                'ARCELIK — Kalibrasyon parcasi',
              ].map((item, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between border-b border-slate-50 py-1.5 last:border-0"
                >
                  <span className="text-[9px] text-slate-600">{item}</span>
                  <CheckCircle size={10} className="text-green-500" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Glow effect */}
      <div className="absolute -inset-4 -z-10 rounded-3xl bg-gradient-to-r from-honeywell-red/5 to-slate-400/5 blur-2xl" />
    </div>
  );
}

export default function Hero() {
  return (
    <section className="relative overflow-hidden pt-28 pb-16 md:pt-36 md:pb-24">
      {/* Background */}
      <div className="absolute inset-0 -z-20 bg-gradient-to-b from-slate-50 to-white" />
      <div className="absolute top-0 left-1/2 -z-10 h-[600px] w-[600px] -translate-x-1/2 rounded-full bg-red-600/3 blur-3xl" />

      <div className="mx-auto max-w-7xl px-6">
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-6 flex justify-center"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-xs font-medium text-slate-600 shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
            v2 SalesBoard yakin zamanda
          </div>
        </motion.div>

        {/* Headline */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="mx-auto max-w-3xl text-center"
        >
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-slate-900 md:text-6xl md:leading-tight">
            E-postadan teklife,
            <br />
            <span className="bg-gradient-to-r from-red-600 to-red-500 bg-clip-text text-transparent">
              dakikalar icinde.
            </span>
          </h1>
          <p className="mt-5 text-base leading-relaxed text-slate-600 md:text-lg">
            Honeywell yedek parca satis ekipleri icin: gelen talep e-postalarini AI ile ayristirin,
            parcalari otomatik eslestirin, teklifi hazirlayin, onaylayin ve gonderin. Tek
            platformda.
          </p>
        </motion.div>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center"
        >
          <a
            href="#demo"
            className="group flex items-center gap-2 rounded-xl bg-slate-900 px-7 py-3.5 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition-all duration-200 hover:bg-slate-800 hover:shadow-xl hover:shadow-slate-900/25"
          >
            Demo Planla
            <ArrowRight
              size={16}
              className="transition-transform duration-200 group-hover:translate-x-0.5"
            />
          </a>
          <a
            href="#solution"
            className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-7 py-3.5 text-sm font-semibold text-slate-700 shadow-sm transition-all duration-200 hover:border-slate-300 hover:shadow-md"
          >
            <Play size={14} className="text-red-600" />
            Nasil Calisir?
          </a>
        </motion.div>

        {/* Trust line */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6, duration: 0.5 }}
          className="mt-6 flex flex-wrap items-center justify-center gap-4 text-[11px] text-slate-400"
        >
          <span className="flex items-center gap-1">
            <Shield size={12} /> RBAC + denetim izi
          </span>
          <span className="h-3 w-px bg-slate-200" />
          <span>Sifrelenmis veriler</span>
          <span className="h-3 w-px bg-slate-200" />
          <span>Kurulum 1 gun</span>
        </motion.div>

        {/* Product mock */}
        <motion.div
          initial={{ opacity: 0, y: 60 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.4 }}
          className="mt-12 md:mt-16"
        >
          <DashboardMock />
        </motion.div>
      </div>
    </section>
  );
}
