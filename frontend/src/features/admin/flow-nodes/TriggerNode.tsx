import { Handle, Position, type NodeProps } from '@xyflow/react';

interface TriggerNodeData {
  label?: string;
  entity_type?: string;
  trigger_event?: string;
  [key: string]: unknown;
}

export function TriggerNode({ data, selected }: NodeProps) {
  const nodeData = data as TriggerNodeData;

  return (
    <div
      className={`rounded-lg border-2 px-4 py-3 min-w-[180px] bg-green-50 ${
        selected ? 'border-green-500 shadow-lg' : 'border-green-300'
      }`}
    >
      <div className="text-[10px] font-bold text-green-600 uppercase mb-1">Tetikleyici</div>
      <div className="text-sm font-semibold text-gray-900">{nodeData.label || 'Olay Seç'}</div>
      {nodeData.entity_type && (
        <div className="text-xs text-gray-500 mt-0.5">
          {nodeData.entity_type} . {nodeData.trigger_event}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-green-500 !w-3 !h-3" />
    </div>
  );
}
