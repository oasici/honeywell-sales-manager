import { Handle, Position, type NodeProps } from '@xyflow/react';

interface ActionNodeData {
  label?: string;
  action_type?: string;
  title?: string;
  message?: string;
  [key: string]: unknown;
}

const ACTION_LABELS: Record<string, string> = {
  send_notification: 'Bildirim',
  create_task: 'Gorev',
  emit_signal: 'Sinyal',
  field_update: 'Güncelleme',
};

export function ActionNode({ data, selected }: NodeProps) {
  const nodeData = data as ActionNodeData;
  const actionLabel = ACTION_LABELS[nodeData.action_type || ''] || nodeData.action_type;

  return (
    <div
      className={`rounded-lg border-2 px-4 py-3 min-w-[180px] bg-blue-50 ${
        selected ? 'border-blue-500 shadow-lg' : 'border-blue-300'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-blue-500 !w-3 !h-3" />
      <div className="text-[10px] font-bold text-blue-600 uppercase mb-1">Aksiyon</div>
      <div className="flex items-center gap-2">
        <div className="text-sm font-semibold text-slate-900">
          {nodeData.label || 'Aksiyon Belirle'}
        </div>
        {actionLabel && (
          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700">
            {actionLabel}
          </span>
        )}
      </div>
      {nodeData.title && <div className="text-xs text-slate-500 mt-0.5">{nodeData.title}</div>}
      {nodeData.message && (
        <div className="text-xs text-slate-400 mt-0.5 truncate max-w-[200px]">
          {nodeData.message}
        </div>
      )}
    </div>
  );
}
