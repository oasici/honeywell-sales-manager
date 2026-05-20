import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { opportunitiesApi } from '../../lib/api';
import { Skeleton } from '../../components/ui/Skeleton';
import type { StageRequirementStatus } from '../../lib/types';

interface SalesPathBarProps {
  oppId: number;
  currentStage: string;
}

const CHECK_ICON_PATH = 'M4.5 12.75l6 6 9-13.5';
const CROSS_ICON_PATH = 'M6 18L18 6M6 6l12 12';

function StageChevron({
  stage,
  isFirst,
  isLast,
  isExpanded,
  onClick,
}: {
  stage: StageRequirementStatus;
  isFirst: boolean;
  isLast: boolean;
  isExpanded: boolean;
  onClick: () => void;
}) {
  const isClosed = stage.stage === 'closed_won' || stage.stage === 'closed_lost';
  const _isCompleted = stage.order < getStageOrder(stage) && !stage.is_current;
  void _isCompleted;

  let bgClass = 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400';
  if (stage.is_current) {
    bgClass = 'bg-honeywell-red text-white';
  } else if (stage.completion_pct === 100 && !isClosed) {
    bgClass = 'bg-green-500 text-white';
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        relative flex flex-1 flex-col items-center justify-center px-3 py-2.5
        transition-all duration-200 cursor-pointer
        ${bgClass}
        ${isFirst ? 'rounded-l-lg' : ''}
        ${isLast ? 'rounded-r-lg' : ''}
        ${isExpanded ? 'ring-2 ring-honeywell-red ring-offset-1 dark:ring-offset-gray-900' : ''}
        hover:opacity-90
      `}
      aria-pressed={isExpanded}
      aria-label={`${stage.label} - %${stage.completion_pct} tamamlandi`}
    >
      <span className="text-xs font-semibold leading-tight truncate max-w-full">
        {stage.label}
      </span>
      <span className="text-[10px] mt-0.5 opacity-80">
        %{stage.completion_pct}
      </span>
      {/* Chevron separator */}
      {!isLast && (
        <div className="absolute -right-2 top-0 z-10 flex h-full items-center">
          <div className="h-4 w-4 rotate-45 border-r-2 border-t-2 border-white/60 dark:border-gray-900/60" />
        </div>
      )}
    </button>
  );
}

function getStageOrder(stage: StageRequirementStatus): number {
  return stage.order;
}

function ExpandedPanel({ stage }: { stage: StageRequirementStatus }) {
  const filledPct = Math.max(stage.completion_pct, 2);

  return (
    <div className="mt-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-slate-900 dark:text-white">
          {stage.label} - Gereksinimler
        </h4>
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          %{stage.completion_pct} tamamlandi
        </span>
      </div>

      {/* Completion bar */}
      <div className="mb-4 h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800">
        <div
          className={`h-2 rounded-full transition-all duration-500 ${
            stage.completion_pct === 100
              ? 'bg-green-500'
              : stage.completion_pct >= 50
                ? 'bg-amber-500'
                : 'bg-red-500'
          }`}
          style={{ width: `${filledPct}%` }}
        />
      </div>

      {/* Required fields */}
      {stage.required_fields.length > 0 && (
        <div className="space-y-2 mb-4">
          <h5 className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
            Zorunlu Alanlar
          </h5>
          {stage.required_fields.map((field) => (
            <div
              key={field.name}
              className="flex items-center gap-2 text-sm"
            >
              <svg
                className={`h-4 w-4 shrink-0 ${
                  field.completed ? 'text-green-500' : 'text-red-400'
                }`}
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2.5}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d={field.completed ? CHECK_ICON_PATH : CROSS_ICON_PATH}
                />
              </svg>
              <span
                className={
                  field.completed
                    ? 'text-slate-700 dark:text-slate-300'
                    : 'text-red-600 dark:text-red-400 font-medium'
                }
              >
                {field.label}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Coaching tips */}
      {stage.coaching_tips.length > 0 && (
        <div className="space-y-1.5">
          <h5 className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
            Ipuclari
          </h5>
          {stage.coaching_tips.map((tip, idx) => (
            <div
              key={idx}
              className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400"
            >
              <svg
                className="mt-0.5 h-4 w-4 shrink-0 text-blue-500"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"
                />
              </svg>
              <span>{tip}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SalesPathBar({ oppId }: SalesPathBarProps) {
  const [expandedStage, setExpandedStage] = useState<string | null>(null);

  // R14-FE-1 exempt: decorative pipeline progress bar; empty render is acceptable
  const { data, isLoading } = useQuery<{ data: StageRequirementStatus[] }>({
    queryKey: ['stage-requirements', oppId],
    queryFn: () => opportunitiesApi.getStageRequirements(oppId),
    enabled: !!oppId,
  });

  if (isLoading) {
    return (
      <div className="mb-6">
        <Skeleton variant="card" />
      </div>
    );
  }

  const stages = data?.data;
  if (!stages || stages.length === 0) {
    return null;
  }

  const handleToggle = (stageName: string) => {
    setExpandedStage((prev) => (prev === stageName ? null : stageName));
  };

  const expandedData = stages.find((s) => s.stage === expandedStage);

  return (
    <div className="mb-6">
      <div className="flex w-full gap-0.5">
        {stages.map((stage, idx) => (
          <StageChevron
            key={stage.stage}
            stage={stage}
            isFirst={idx === 0}
            isLast={idx === stages.length - 1}
            isExpanded={expandedStage === stage.stage}
            onClick={() => handleToggle(stage.stage)}
          />
        ))}
      </div>
      {expandedData && <ExpandedPanel stage={expandedData} />}
    </div>
  );
}
