import React, { useId } from 'react';
import { PieChart, Pie, Cell } from 'recharts';

const PALETTE = [
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
  const uid = useId().replace(/:/g, '');
  const pct = total > 0 ? Math.round((filled / total) * 100) : 0;
  const remaining = Math.max(total - filled, 0);
  const data = [
    { name: 'Tamamlanan', value: filled || 0.001 },
    { name: 'Kalan', value: remaining || 0.001 },
  ];
  const colors = PALETTE[colorIndex % PALETTE.length];
  const gradId = `doughnutGrad-${uid}`;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm h-full dark:border-gray-700 dark:bg-gray-800">
      <p className="mb-3 text-sm font-medium text-gray-500 text-center dark:text-gray-400">
        {title}
      </p>
      <div className="flex items-center justify-center">
        <div className="relative" style={{ width: 150, height: 150 }}>
          <PieChart width={150} height={150}>
            <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor={colors[0]} stopOpacity={1} />
                  <stop offset="100%" stopColor={colors[0]} stopOpacity={0.7} />
                </linearGradient>
                <filter id={`shadow-${uid}`}>
                  <feDropShadow
                    dx="0"
                    dy="1"
                    stdDeviation="2"
                    floodColor={colors[0]}
                    floodOpacity="0.25"
                  />
                </filter>
              </defs>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={68}
                dataKey="value"
                startAngle={90}
                endAngle={-270}
                stroke="none"
                cornerRadius={6}
                animationBegin={0}
                animationDuration={1200}
                animationEasing="ease-out"
              >
                <Cell fill={`url(#${gradId})`} style={{ filter: `url(#shadow-${uid})` }} />
                <Cell fill={colors[1]} />
              </Pie>
            </PieChart>
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span className="text-2xl font-bold text-gray-900 dark:text-white">%{pct}</span>
          </div>
        </div>
      </div>
      <div className="mt-2 text-center text-xs text-gray-500 dark:text-gray-400">
        <span className="font-semibold text-gray-700 dark:text-gray-200">
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
