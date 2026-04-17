import { Handle, Position, type NodeProps } from '@xyflow/react';

interface ConditionNodeData {
  label?: string;
  field?: string;
  operator?: string;
  value?: string;
  [key: string]: unknown;
}

const OPERATOR_LABELS: Record<string, string> = {
  eq: '=',
  neq: '!=',
  contains: 'içerir',
  gte: '>=',
  lte: '<=',
};

export function ConditionNode({ data, selected }: NodeProps) {
  const nodeData = data as ConditionNodeData;
  const operatorLabel = OPERATOR_LABELS[nodeData.operator || 'eq'] || nodeData.operator;

  return (
    <div
      className={`rounded-lg border-2 px-4 py-3 min-w-[180px] bg-amber-50 ${
        selected ? 'border-amber-500 shadow-lg' : 'border-amber-300'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-amber-500 !w-3 !h-3" />
      <div className="text-[10px] font-bold text-amber-600 uppercase mb-1">Kosul</div>
      <div className="text-sm font-semibold text-gray-900">{nodeData.label || 'Kosul Belirle'}</div>
      {nodeData.field && (
        <div className="text-xs text-gray-500 mt-0.5">
          {nodeData.field} {operatorLabel} {nodeData.value}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-amber-500 !w-3 !h-3" />
    </div>
  );
}
