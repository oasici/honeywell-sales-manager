import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

export const PALETTE = [
  ['#D32F2F', '#fce4ec'],
  ['#1976D2', '#e3f2fd'],
  ['#388E3C', '#e8f5e9'],
  ['#F57C00', '#fff3e0'],
];

interface DoughnutChartProps {
  title: string;
  filled: number;
  total: number;
  unit?: string;
  colorIndex?: number;
}

export const DoughnutChart = React.memo(function DoughnutChart({
  title,
  filled,
  total,
  unit,
  colorIndex = 0,
}: DoughnutChartProps) {
  const pct = total > 0 ? Math.round((filled / total) * 100) : 0;
  const remaining = Math.max(total - filled, 0);
  const data = [
    { name: 'Tamamlanan', value: filled || 0.001 },
    { name: 'Kalan', value: remaining || 0.001 },
  ];
  const colors = PALETTE[colorIndex % PALETTE.length];

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm h-full">
      <p className="mb-3 text-sm font-medium text-gray-500 text-center">{title}</p>
      <div className="flex items-center justify-center">
        <div className="relative" style={{ width: 140, height: 140 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={45}
                outerRadius={65}
                dataKey="value"
                startAngle={90}
                endAngle={-270}
                stroke="none"
                cornerRadius={4}
              >
                {data.map((_, i) => (
                  <Cell key={i} fill={colors[i]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-xl font-bold text-gray-900">%{pct}</span>
          </div>
        </div>
      </div>
      <div className="mt-2 text-center text-xs text-gray-500">
        <span className="font-semibold text-gray-700">
          {typeof filled === 'number' && filled > 1000
            ? filled.toLocaleString('tr-TR', { maximumFractionDigits: 0 })
            : filled}
        </span>
        {' / '}
        {typeof total === 'number' && total > 1000
          ? total.toLocaleString('tr-TR', { maximumFractionDigits: 0 })
          : total}
        {unit && ` ${unit}`}
      </div>
    </div>
  );
});
