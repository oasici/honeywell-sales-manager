export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white py-12">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-4">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-600">
                <span className="text-sm font-black text-white">H</span>
              </div>
              <span className="text-base font-bold tracking-tight text-slate-900">Sales Suite</span>
            </div>
            <p className="mt-3 text-sm text-slate-500">
              Honeywell Turkiye yedek parça satış sureci için tasarlandi.
            </p>
          </div>

          {/* Product */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400">Ürün</h4>
            <ul className="mt-3 space-y-2 text-sm text-slate-600">
              <li><a href="#features" className="transition-colors hover:text-slate-900">Ozellikler</a></li>
              <li><a href="#pricing" className="transition-colors hover:text-slate-900">Fiyatlar</a></li>
              <li><a href="#solution" className="transition-colors hover:text-slate-900">Nasil Calisir</a></li>
              <li><a href="#faq" className="transition-colors hover:text-slate-900">SSS</a></li>
            </ul>
          </div>

          {/* Company */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400">Şirket</h4>
            <ul className="mt-3 space-y-2 text-sm text-slate-600">
              <li><a href="/login" className="transition-colors hover:text-slate-900">Giris Yap</a></li>
              <li><a href="#demo" className="transition-colors hover:text-slate-900">Demo Planla</a></li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400">Guvenlik</h4>
            <ul className="mt-3 space-y-2 text-sm text-slate-600">
              <li>RBAC + Audit Trail</li>
              <li>AES-256 Sifreleme</li>
              <li>KVKK Uyumlu</li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-slate-100 pt-6 text-center text-xs text-slate-400">
          &copy; {new Date().getFullYear()} Honeywell Sales Suite. Tum haklari saklidir.
        </div>
      </div>
    </footer>
  );
}
