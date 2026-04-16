interface DealHealthBadgeProps {
  score: number;
  riskLevel: string;
}

const SCORE_THRESHOLD_HIGH = 70;
const SCORE_THRESHOLD_LOW = 40;

function getColorClasses(score: number): string {
  if (score >= SCORE_THRESHOLD_HIGH) {
    return 'bg-green-100 text-green-700 ring-green-300 dark:bg-green-900/30 dark:text-green-400 dark:ring-green-700';
  }
  if (score >= SCORE_THRESHOLD_LOW) {
    return 'bg-amber-100 text-amber-700 ring-amber-300 dark:bg-amber-900/30 dark:text-amber-400 dark:ring-amber-700';
  }
  return 'bg-red-100 text-red-700 ring-red-300 dark:bg-red-900/30 dark:text-red-400 dark:ring-red-700';
}

export function DealHealthBadge({ score, riskLevel }: DealHealthBadgeProps) {
  const colorClasses = getColorClasses(score);

  return (
    <span
      className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ring-1 ${colorClasses}`}
      title={`Saglik: ${score} (${riskLevel})`}
    >
      {score}
    </span>
  );
}
