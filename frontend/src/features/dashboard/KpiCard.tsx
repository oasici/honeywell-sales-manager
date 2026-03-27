import React from 'react';

export const KpiCard = React.memo(function KpiCard({
  label,
  value,
  suffix,
  onClick,
}: {
  label: string;
  value: string | number;
  suffix?: string;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`rounded-xl border border-gray-200 bg-white p-5 shadow-sm ${
        onClick ? 'cursor-pointer hover:shadow-md hover:border-honeywell-light transition-all' : ''
      }`}
    >
      <p className="text-sm font-medium text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">
        {value}
        {suffix && <span className="ml-1 text-sm font-normal text-gray-400">{suffix}</span>}
      </p>
    </div>
  );
});
