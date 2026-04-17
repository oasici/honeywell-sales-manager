import { useCallback } from 'react';
import { toast } from 'sonner';

export function useCopyToClipboard() {
  const copy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success('Kopyalandi');
    } catch {
      toast.error('Kopyalama başarısız');
    }
  }, []);
  return copy;
}
