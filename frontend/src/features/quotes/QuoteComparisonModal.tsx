import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { quotesApi } from '../../lib/api';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { formatCurrency } from '../../lib/formatters';
import type { QuoteVersionItem, QuoteComparisonResult } from '../../lib/types';

interface QuoteComparisonModalProps {
  isOpen: boolean;
  onClose: () => void;
  quoteId: number;
}

export default function QuoteComparisonModal({
  isOpen,
  onClose,
  quoteId,
}: QuoteComparisonModalProps) {
  const [selectedPair, setSelectedPair] = useState<{
    prev: number;
    curr: number;
  } | null>(null);

  const { data: versionsData, isLoading: versionsLoading } = useQuery<{
    quote_id: number;
    versions: QuoteVersionItem[];
  }>({
    queryKey: ['quote-versions', quoteId],
    queryFn: () => quotesApi.getVersions(quoteId),
    enabled: isOpen,
  });

  const versions = versionsData?.versions ?? [];

  // Auto-select last two versions for comparison
  const compPrev =
    selectedPair?.prev ?? (versions.length >= 2 ? versions[versions.length - 2].id : null);
  const compCurr =
    selectedPair?.curr ?? (versions.length >= 2 ? versions[versions.length - 1].id : null);

  const { data: comparison, isLoading: compLoading } = useQuery<QuoteComparisonResult>({
    queryKey: ['quote-comparison', compPrev, compCurr],
    queryFn: () => quotesApi.compareVersions(compPrev!, compCurr!),
    enabled: isOpen && compPrev != null && compCurr != null,
  });

  if (!isOpen) return null;

  const addedCount = comparison?.added_items.length ?? 0;
  const removedCount = comparison?.removed_items.length ?? 0;
  const totalDiff = comparison
    ? comparison.summary_diff.grand_total.to - comparison.summary_diff.grand_total.from
    : 0;
  const currency = comparison?.summary_diff.currency.to ?? 'TRY';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white shadow-xl dark:bg-gray-900 p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">
            Versiyon Karsilastirmasi
          </h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Kapat
          </Button>
        </div>

        {versionsLoading ? (
          <Skeleton variant="card" count={2} />
        ) : versions.length < 2 ? (
          <p className="py-12 text-center text-sm text-gray-500">Bu teklifin tek versiyonu var</p>
        ) : (
          <>
            {/* Version selector */}
            <div className="mb-4 flex items-center gap-3 text-sm">
              <label className="text-gray-500 dark:text-gray-400">Onceki:</label>
              <select
                value={compPrev ?? ''}
                onChange={(e) =>
                  setSelectedPair((p) => ({
                    prev: Number(e.target.value),
                    curr: p?.curr ?? compCurr ?? 0,
                  }))
                }
                className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
              >
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version} - {v.quote_number}
                  </option>
                ))}
              </select>
              <label className="text-gray-500 dark:text-gray-400">Sonraki:</label>
              <select
                value={compCurr ?? ''}
                onChange={(e) =>
                  setSelectedPair((p) => ({
                    prev: p?.prev ?? compPrev ?? 0,
                    curr: Number(e.target.value),
                  }))
                }
                className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
              >
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version} - {v.quote_number}
                  </option>
                ))}
              </select>
            </div>

            {compLoading ? (
              <Skeleton variant="table" />
            ) : comparison ? (
              <div className="space-y-4">
                {/* Changed items */}
                {comparison.changed_items.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                      Degisen Kalemler
                    </h3>
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-gray-700">
                          <th className="py-2 px-3 text-left text-xs text-gray-500">Urun</th>
                          <th className="py-2 px-3 text-left text-xs text-gray-500">Alan</th>
                          <th className="py-2 px-3 text-right text-xs text-gray-500">Onceki</th>
                          <th className="py-2 px-3 text-right text-xs text-gray-500">Yeni</th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.changed_items.map((item) =>
                          Object.entries(item.changes).map(([field, change]) => (
                            <tr
                              key={`${item.key}-${field}`}
                              className="border-b border-gray-50 dark:border-gray-800 bg-yellow-50 dark:bg-yellow-900/10"
                            >
                              <td className="py-2 px-3 text-gray-900 dark:text-white">
                                {item.description}
                              </td>
                              <td className="py-2 px-3 text-gray-600 dark:text-gray-400">
                                {field}
                              </td>
                              <td className="py-2 px-3 text-right text-gray-500">{change.from}</td>
                              <td className="py-2 px-3 text-right font-semibold text-gray-900 dark:text-white">
                                {change.to}
                              </td>
                            </tr>
                          )),
                        )}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Added items */}
                {comparison.added_items.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                      Eklenen Kalemler
                    </h3>
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-gray-700">
                          <th className="py-2 px-3 text-left text-xs text-gray-500">Urun</th>
                          <th className="py-2 px-3 text-right text-xs text-gray-500">Miktar</th>
                          <th className="py-2 px-3 text-right text-xs text-gray-500">
                            Birim Fiyat
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.added_items.map((item) => (
                          <tr
                            key={item.key}
                            className="border-b border-gray-50 dark:border-gray-800 bg-green-50 dark:bg-green-900/10"
                          >
                            <td className="py-2 px-3 text-gray-900 dark:text-white">
                              {item.description}
                            </td>
                            <td className="py-2 px-3 text-right">{item.quantity}</td>
                            <td className="py-2 px-3 text-right">
                              {formatCurrency(item.unit_price, currency)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Removed items */}
                {comparison.removed_items.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                      Kaldirilan Kalemler
                    </h3>
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-gray-700">
                          <th className="py-2 px-3 text-left text-xs text-gray-500">Urun</th>
                          <th className="py-2 px-3 text-right text-xs text-gray-500">Miktar</th>
                          <th className="py-2 px-3 text-right text-xs text-gray-500">
                            Birim Fiyat
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.removed_items.map((item) => (
                          <tr
                            key={item.key}
                            className="border-b border-gray-50 dark:border-gray-800 bg-red-50 dark:bg-red-900/10"
                          >
                            <td className="py-2 px-3 text-gray-900 dark:text-white line-through">
                              {item.description}
                            </td>
                            <td className="py-2 px-3 text-right line-through">{item.quantity}</td>
                            <td className="py-2 px-3 text-right line-through">
                              {formatCurrency(item.unit_price, currency)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Summary */}
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-600 dark:text-gray-400">
                      +{addedCount} urun eklendi, -{removedCount} urun kaldirildi
                    </span>
                    <span
                      className={`font-bold ${totalDiff >= 0 ? 'text-green-600' : 'text-red-600'}`}
                    >
                      Toplam fark: {totalDiff >= 0 ? '+' : ''}
                      {formatCurrency(totalDiff, currency)}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-xs text-gray-500">
                    <span>
                      Onceki toplam:{' '}
                      {formatCurrency(comparison.summary_diff.grand_total.from, currency)}
                    </span>
                    <span>
                      Yeni toplam:{' '}
                      {formatCurrency(comparison.summary_diff.grand_total.to, currency)}
                    </span>
                  </div>
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
