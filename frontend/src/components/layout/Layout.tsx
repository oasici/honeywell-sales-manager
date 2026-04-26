import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { MobileBottomNav } from './MobileBottomNav';
import { QuickAddFAB } from './QuickAddFAB';
import { ChatWidget } from '../../features/chat/ChatWidget';
import { InstallPrompt } from '../InstallPrompt';
import { useT } from '../../hooks/useT';

export function Layout() {
  const t = useT();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ backgroundColor: 'var(--surface-secondary)' }}
    >
      <InstallPrompt />
      {/* Mobile sidebar overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar - hidden on mobile, shown on lg+ */}
      <div
        className={`fixed inset-y-0 left-0 z-50 lg:static lg:z-auto transition-transform duration-200 ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <Sidebar onNavigate={() => setMobileMenuOpen(false)} />
      </div>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile header */}
        <header
          className="flex items-center lg:hidden border-b px-4 py-2"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface)' }}
        >
          <button
            type="button"
            onClick={() => setMobileMenuOpen(true)}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
            aria-label={t('layout.mobile_open_menu')}
          >
            <Menu size={22} />
          </button>
          <span className="ml-2 text-sm font-bold text-honeywell-red">Honeywell</span>
          <span className="ml-1 text-xs text-slate-400">Sales Suite</span>
        </header>

        {/* Desktop header */}
        <div className="hidden lg:block">
          <Header />
        </div>

        {/* Scrollable content */}
        <main className="flex-1 overflow-y-auto p-4 pb-20 sm:p-6 lg:p-8 lg:pb-8">
          <Outlet />
        </main>
      </div>

      <MobileBottomNav />
      <QuickAddFAB />
      <ChatWidget />
    </div>
  );
}
