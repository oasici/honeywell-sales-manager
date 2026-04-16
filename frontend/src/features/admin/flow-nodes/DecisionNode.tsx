import { Handle, Position, type NodeProps } from '@xyflow/react';

interface DecisionNodeData {
  label?: string;
  condition_text?: string;
  [key: string]: unknown;
}

export function DecisionNode({ data, selected }: NodeProps) {
  const nodeData = data as DecisionNodeData;

  return (
    <div
      className={`relative rounded-lg border-2 px-4 py-3 min-w-[180px] bg-orange-50 ${
        selected ? 'border-orange-500 shadow-lg' : 'border-orange-300'
      }`}
      style={{
        clipPath: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)',
        padding: '2rem 2.5rem',
      }}
    >
      <Handle type="target" position={Position.Top} className="!bg-orange-500 !w-3 !h-3" />
      <div className="text-[10px] font-bold text-orange-600 uppercase mb-1 text-center">Karar</div>
      <div className="text-sm font-semibold text-gray-900 text-center">
        {nodeData.label || 'Karar Ver'}
      </div>
      {nodeData.condition_text && (
        <div className="text-xs text-gray-500 mt-0.5 text-center">{nodeData.condition_text}</div>
      )}
      <Handle
        type="source"
        position={Position.Bottom}
        id="yes"
        className="!bg-green-500 !w-3 !h-3"
        style={{ left: '30%' }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="no"
        className="!bg-red-500 !w-3 !h-3"
        style={{ left: '70%' }}
      />
      <div
        className="absolute text-[9px] font-bold text-green-600"
        style={{ bottom: '-2px', left: '20%' }}
      >
        Evet
      </div>
      <div
        className="absolute text-[9px] font-bold text-red-600"
        style={{ bottom: '-2px', left: '62%' }}
      >
        Hayir
      </div>
    </div>
  );
}
