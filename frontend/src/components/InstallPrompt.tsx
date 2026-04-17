import { useEffect, useState } from 'react';
import { Download, X } from 'lucide-react';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

const DISMISSED_KEY = 'pwa-install-dismissed';

export function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(DISMISSED_KEY) === '1') return;

    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
      // Defer to satisfy react-hooks/set-state-in-effect ESLint rule
      queueMicrotask(() => setIsVisible(true));
    };

    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const handleInstall = async () => {
    if (!deferredPrompt) return;
    await deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    if (choice.outcome === 'accepted') {
      setIsVisible(false);
      setDeferredPrompt(null);
    }
  };

  const handleDismiss = () => {
    localStorage.setItem(DISMISSED_KEY, '1');
    setIsVisible(false);
  };

  if (!isVisible) return null;

  return (
    <div
      role="banner"
      className="fixed top-0 left-0 right-0 z-[100] flex items-center justify-between gap-3 bg-honeywell-red px-4 py-2 text-white shadow-md"
    >
      <div className="flex items-center gap-2 text-sm">
        <Download size={16} className="shrink-0" aria-hidden="true" />
        <span>Bu uygulamayi yukleyin ve daha hızlı erişim saglayin</span>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleInstall}
          className="rounded bg-white px-3 py-1 text-xs font-semibold text-honeywell-red hover:bg-red-50 transition-colors"
        >
          Yükle
        </button>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Kapat"
          className="rounded p-1 hover:bg-red-700 transition-colors"
        >
          <X size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
