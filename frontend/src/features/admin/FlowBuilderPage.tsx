import { useState, useCallback, useRef, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  Panel,
  type Connection,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { toast } from 'sonner';

import { TriggerNode } from './flow-nodes/TriggerNode';
import { ConditionNode } from './flow-nodes/ConditionNode';
import { ActionNode } from './flow-nodes/ActionNode';
import { DecisionNode } from './flow-nodes/DecisionNode';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { workflowRulesApi } from '../../lib/api';

import type { WorkflowRule } from '../../lib/types';

const MAX_HISTORY = 30;

interface FlowSnapshot {
  nodes: Node[];
  edges: Edge[];
}

function validateFlow(nodes: Node[], edges: Edge[]): string[] {
  const issues: string[] = [];

  const triggerNodes = nodes.filter((n) => n.type === 'trigger');
  if (triggerNodes.length !== 1) {
    issues.push(`Tam olarak 1 Tetikleyici dugumu olmali (su an: ${triggerNodes.length})`);
  }

  const decisionAndConditionNodes = nodes.filter(
    (n) => n.type === 'condition' || n.type === 'decision',
  );
  for (const node of decisionAndConditionNodes) {
    const hasOutgoing = edges.some((e) => e.source === node.id);
    if (!hasOutgoing) {
      const label = (node.data.label as string) || node.id;
      issues.push(`"${label}" dugumunun giden baglantisi yok`);
    }
  }

  for (const node of nodes) {
    if (node.type === 'trigger') continue;
    const hasIncoming = edges.some((e) => e.target === node.id);
    if (!hasIncoming) {
      const label = (node.data.label as string) || node.id;
      issues.push(`"${label}" dugumu izole (gelen baglanti yok)`);
    }
  }

  return issues;
}

const nodeTypes = {
  trigger: TriggerNode,
  condition: ConditionNode,
  action: ActionNode,
  decision: DecisionNode,
};

const defaultEdgeOptions = {
  animated: true,
  style: { stroke: '#94a3b8', strokeWidth: 2 },
};

const ENTITY_TYPE_OPTIONS = [
  { value: 'opportunity', label: 'Fırsat' },
  { value: 'quote', label: 'Teklif' },
  { value: 'email', label: 'E-posta' },
  { value: 'customer', label: 'Müşteri' },
];

const TRIGGER_EVENT_OPTIONS: Record<string, { value: string; label: string }[]> = {
  opportunity: [
    { value: 'stage_changed', label: 'Aşama Değişti' },
    { value: 'created', label: 'Oluşturuldu' },
    { value: 'amount_changed', label: 'Tutar Değişti' },
  ],
  quote: [
    { value: 'approved', label: 'Onaylandı' },
    { value: 'sent', label: 'Gönderildi' },
    { value: 'created', label: 'Oluşturuldu' },
  ],
  email: [
    { value: 'parsed', label: 'Ayrıştırma Tamamlandi' },
    { value: 'received', label: 'Alindi' },
  ],
  customer: [
    { value: 'created', label: 'Oluşturuldu' },
    { value: 'updated', label: 'Güncellendi' },
  ],
};

const ACTION_TYPE_OPTIONS = [
  { value: 'send_notification', label: 'Bildirim Gönder' },
  { value: 'create_task', label: 'Gorev Oluştur' },
  { value: 'emit_signal', label: 'Sinyal Yayinla' },
  { value: 'field_update', label: 'Alan Güncelle' },
];

const OPERATOR_OPTIONS = [
  { value: 'eq', label: 'Esit' },
  { value: 'neq', label: 'Esit Değil' },
  { value: 'contains', label: 'İçerir' },
  { value: 'gte', label: 'Buyuk Esit' },
  { value: 'lte', label: 'Kucuk Esit' },
];

const PALETTE_ITEMS = [
  { type: 'trigger', label: 'Tetikleyici', color: 'border-green-400 text-green-700' },
  { type: 'condition', label: 'Kosul', color: 'border-amber-400 text-amber-700' },
  { type: 'action', label: 'Aksiyon', color: 'border-blue-400 text-blue-700' },
  { type: 'decision', label: 'Karar', color: 'border-orange-400 text-orange-700' },
];

const DEFAULT_NODE_LABELS: Record<string, string> = {
  trigger: 'Tetikleyici',
  condition: 'Kosul',
  action: 'Aksiyon',
  decision: 'Karar',
};

function buildDefaultNodes(rule: WorkflowRule): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  let yOffset = 0;

  const triggerNode: Node = {
    id: 'trigger_default',
    type: 'trigger',
    position: { x: 250, y: yOffset },
    data: {
      label: 'Tetikleyici',
      entity_type: rule.entity_type,
      trigger_event: rule.trigger_event,
    },
  };
  nodes.push(triggerNode);
  let lastNodeId = triggerNode.id;
  yOffset += 120;

  if (rule.conditions_json) {
    try {
      const conditions = JSON.parse(rule.conditions_json);
      conditions.forEach((cond: Record<string, string>, idx: number) => {
        const nodeId = `condition_${idx}`;
        nodes.push({
          id: nodeId,
          type: 'condition',
          position: { x: 250, y: yOffset },
          data: {
            label: `Kosul ${idx + 1}`,
            field: cond.field,
            operator: cond.operator,
            value: cond.value,
          },
        });
        edges.push({
          id: `e_${lastNodeId}_${nodeId}`,
          source: lastNodeId,
          target: nodeId,
          ...defaultEdgeOptions,
        });
        lastNodeId = nodeId;
        yOffset += 120;
      });
    } catch {
      // skip invalid JSON
    }
  }

  try {
    const actions = JSON.parse(rule.actions_json);
    actions.forEach((action: Record<string, string>, idx: number) => {
      const nodeId = `action_${idx}`;
      nodes.push({
        id: nodeId,
        type: 'action',
        position: { x: 250, y: yOffset },
        data: {
          label: action.title || `Aksiyon ${idx + 1}`,
          action_type: action.type,
          title: action.title,
          message: action.message,
        },
      });
      edges.push({
        id: `e_${lastNodeId}_${nodeId}`,
        source: lastNodeId,
        target: nodeId,
        ...defaultEdgeOptions,
      });
      lastNodeId = nodeId;
      yOffset += 120;
    });
  } catch {
    // skip invalid JSON
  }

  return { nodes, edges };
}

export default function FlowBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);

  const isNew = id === 'new' || !id;
  const ruleId = isNew ? null : Number(id);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [ruleName, setRuleName] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const isInitializedRef = useRef(false);

  // Clipboard for copy/paste
  const clipboardRef = useRef<Node[]>([]);

  // Undo/redo history
  const historyRef = useRef<FlowSnapshot[]>([]);
  const historyIndexRef = useRef<number>(-1);
  const isRestoringRef = useRef(false);

  // Keep live refs to current nodes/edges for use in keyboard handler
  const nodesRef = useRef<Node[]>(nodes);
  const edgesRef = useRef<Edge[]>(edges);
  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);
  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  const pushHistory = useCallback(() => {
    if (isRestoringRef.current) return;
    const snapshot: FlowSnapshot = {
      nodes: nodesRef.current.map((n) => ({ ...n })),
      edges: edgesRef.current.map((e) => ({ ...e })),
    };
    const truncated = historyRef.current.slice(0, historyIndexRef.current + 1);
    truncated.push(snapshot);
    if (truncated.length > MAX_HISTORY) {
      truncated.shift();
    }
    historyRef.current = truncated;
    historyIndexRef.current = truncated.length - 1;
  }, []);

  const { data: ruleData } = useQuery<{ items: WorkflowRule[]; total: number }>({
    queryKey: ['workflowRules'],
    queryFn: () => workflowRulesApi.list(),
    enabled: ruleId !== null,
  });

  const rule = ruleData?.items?.find((r) => r.id === ruleId) ?? null;

  useEffect(() => {
    if (isInitializedRef.current) return;
    if (isNew) {
      isInitializedRef.current = true;
      return;
    }
    if (!rule) return;

    isInitializedRef.current = true;

    queueMicrotask(() => {
      setRuleName(rule.name);
      setIsActive(rule.is_active);

      if (rule.flow_json) {
        try {
          const flowData = JSON.parse(rule.flow_json);
          setNodes(flowData.nodes || []);
          setEdges(flowData.edges || []);
        } catch {
          const defaultLayout = buildDefaultNodes(rule);
          setNodes(defaultLayout.nodes);
          setEdges(defaultLayout.edges);
        }
      } else {
        const defaultLayout = buildDefaultNodes(rule);
        setNodes(defaultLayout.nodes);
        setEdges(defaultLayout.edges);
      }
    });
  }, [rule, isNew, setNodes, setEdges]);

  // Keyboard shortcuts: copy/paste, undo/redo
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().includes('MAC');
      const ctrl = isMac ? e.metaKey : e.ctrlKey;
      if (!ctrl) return;

      if (e.key === 'c' || e.key === 'C') {
        const selected = nodesRef.current.filter((n) => n.selected);
        if (selected.length > 0) {
          clipboardRef.current = selected;
        }
        return;
      }

      if (e.key === 'v' || e.key === 'V') {
        if (clipboardRef.current.length === 0) return;
        e.preventDefault();
        pushHistory();
        const newNodes = clipboardRef.current.map((n) => ({
          ...n,
          id: crypto.randomUUID(),
          position: { x: n.position.x + 50, y: n.position.y + 50 },
          selected: false,
        }));
        setNodes((nds) => [...nds, ...newNodes]);
        return;
      }

      if (e.key === 'z' || e.key === 'Z') {
        e.preventDefault();
        const idx = historyIndexRef.current;
        if (idx <= 0) return;
        const prev = historyRef.current[idx - 1];
        if (!prev) return;
        isRestoringRef.current = true;
        historyIndexRef.current = idx - 1;
        setNodes(prev.nodes);
        setEdges(prev.edges);
        queueMicrotask(() => {
          isRestoringRef.current = false;
        });
        return;
      }

      if (e.key === 'y' || e.key === 'Y') {
        e.preventDefault();
        const idx = historyIndexRef.current;
        if (idx >= historyRef.current.length - 1) return;
        const next = historyRef.current[idx + 1];
        if (!next) return;
        isRestoringRef.current = true;
        historyIndexRef.current = idx + 1;
        setNodes(next.nodes);
        setEdges(next.edges);
        queueMicrotask(() => {
          isRestoringRef.current = false;
        });
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [pushHistory, setNodes, setEdges]);

  const onNodesChangeWithHistory = useCallback(
    (changes: Parameters<typeof onNodesChange>[0]) => {
      const hasStructural = changes.some((c) => c.type === 'remove' || c.type === 'add');
      if (hasStructural) pushHistory();
      onNodesChange(changes);
    },
    [onNodesChange, pushHistory],
  );

  const onEdgesChangeWithHistory = useCallback(
    (changes: Parameters<typeof onEdgesChange>[0]) => {
      const hasStructural = changes.some((c) => c.type === 'remove' || c.type === 'add');
      if (hasStructural) pushHistory();
      onEdgesChange(changes);
    },
    [onEdgesChange, pushHistory],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      pushHistory();
      setEdges((eds) => addEdge({ ...connection, ...defaultEdgeOptions }, eds));
    },
    [setEdges, pushHistory],
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData('application/reactflow');
      if (!type || !reactFlowInstance) return;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newNode: Node = {
        id: `${type}_${Date.now()}`,
        type,
        position,
        data: { label: DEFAULT_NODE_LABELS[type] || type },
      };

      pushHistory();
      setNodes((nds) => [...nds, newNode]);
    },
    [reactFlowInstance, setNodes, pushHistory],
  );

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) ?? null;

  const updateNodeData = useCallback(
    (key: string, value: string) => {
      if (!selectedNodeId) return;
      setNodes((nds) =>
        nds.map((n) => (n.id === selectedNodeId ? { ...n, data: { ...n.data, [key]: value } } : n)),
      );
    },
    [selectedNodeId, setNodes],
  );

  const deleteSelectedNode = useCallback(() => {
    if (!selectedNodeId) return;
    pushHistory();
    setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId));
    setEdges((eds) =>
      eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId),
    );
    setSelectedNodeId(null);
  }, [selectedNodeId, setNodes, setEdges, pushHistory]);

  const handleUndo = useCallback(() => {
    const idx = historyIndexRef.current;
    if (idx <= 0) return;
    const prev = historyRef.current[idx - 1];
    if (!prev) return;
    isRestoringRef.current = true;
    historyIndexRef.current = idx - 1;
    setNodes(prev.nodes);
    setEdges(prev.edges);
    queueMicrotask(() => {
      isRestoringRef.current = false;
    });
  }, [setNodes, setEdges]);

  const handleRedo = useCallback(() => {
    const idx = historyIndexRef.current;
    if (idx >= historyRef.current.length - 1) return;
    const next = historyRef.current[idx + 1];
    if (!next) return;
    isRestoringRef.current = true;
    historyIndexRef.current = idx + 1;
    setNodes(next.nodes);
    setEdges(next.edges);
    queueMicrotask(() => {
      isRestoringRef.current = false;
    });
  }, [setNodes, setEdges]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const validationIssues = validateFlow(nodes, edges);
      if (validationIssues.length > 0) {
        for (const issue of validationIssues) {
          toast.error(issue);
        }
        throw new Error('Validasyon hatasi');
      }

      const flowData = { nodes, edges };

      const conditionNodes = nodes.filter((n) => n.type === 'condition');
      const conditions = conditionNodes.map((n) => ({
        field: (n.data.field as string) || '',
        operator: (n.data.operator as string) || 'eq',
        value: (n.data.value as string) || '',
      }));

      const actionNodes = nodes.filter((n) => n.type === 'action');
      const actions = actionNodes.map((n) => ({
        type: (n.data.action_type as string) || 'send_notification',
        title: (n.data.title as string) || '',
        message: (n.data.message as string) || '',
      }));

      const triggerNode = nodes.find((n) => n.type === 'trigger');

      const payload: Record<string, unknown> = {
        name: ruleName || 'Isimsiz Kural',
        entity_type: (triggerNode?.data.entity_type as string) || 'opportunity',
        trigger_event: (triggerNode?.data.trigger_event as string) || 'stage_changed',
        conditions_json: conditions.length > 0 ? JSON.stringify(conditions) : null,
        actions_json: JSON.stringify(actions.length > 0 ? actions : []),
        flow_json: JSON.stringify(flowData),
        is_active: isActive,
      };

      if (ruleId) {
        return workflowRulesApi.update(ruleId, payload);
      }
      return workflowRulesApi.create(payload);
    },
    onSuccess: () => {
      toast.success('Kural kaydedildi');
      queryClient.invalidateQueries({ queryKey: ['workflowRules'] });
      if (isNew) {
        navigate('/admin/workflow-rules');
      }
    },
    onError: () => toast.error('Kaydetme başarısız oldu'),
  });

  const currentTriggerOptions =
    TRIGGER_EVENT_OPTIONS[(selectedNode?.data.entity_type as string) || 'opportunity'] ?? [];

  return (
    <div>
      <PageHeader
        title="Gorsel İş Kuralı Editoru"
        description="Surukle-birak ile is akisi olusturun"
      >
        <Button variant="secondary" onClick={() => navigate('/admin/workflow-rules')}>
          Form Gorunumu
        </Button>
        <Button variant="ghost" onClick={handleUndo} title="Geri Al (Ctrl+Z)">
          Geri Al
        </Button>
        <Button variant="ghost" onClick={handleRedo} title="Yinele (Ctrl+Y)">
          Yinele
        </Button>
        <Button onClick={() => saveMutation.mutate()} loading={saveMutation.isPending}>
          Kaydet
        </Button>
      </PageHeader>

      <div className="mb-4 flex items-center gap-4">
        <div className="w-72">
          <Input
            label="Kural Adi"
            placeholder="Kural adi girin"
            value={ruleName}
            onChange={(e) => setRuleName(e.target.value)}
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 mt-5">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="rounded border-slate-200"
          />
          Aktif
        </label>
      </div>

      <div className="flex gap-4">
        {/* Left sidebar: node palette */}
        <div className="w-48 shrink-0 space-y-3">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Dugumler</h3>
          <p className="text-xs text-slate-400">Tuval uzerine surukleyin</p>
          {PALETTE_ITEMS.map((item) => (
            <div
              key={item.type}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData('application/reactflow', item.type);
                e.dataTransfer.effectAllowed = 'move';
              }}
              className={`cursor-grab rounded-lg border-2 border-dashed p-3 text-center text-sm font-medium hover:border-honeywell-red hover:shadow-sm transition-all ${item.color}`}
            >
              {item.label}
            </div>
          ))}
        </div>

        {/* Main canvas */}
        <div
          ref={reactFlowWrapper}
          className="flex-1 rounded-lg border border-slate-200 dark:border-slate-800 dark:bg-slate-900"
          style={{ height: '70vh' }}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChangeWithHistory}
            onEdgesChange={onEdgesChangeWithHistory}
            onConnect={onConnect}
            onInit={setReactFlowInstance}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            fitView
          >
            <Controls />
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <MiniMap nodeStrokeWidth={3} className="!bg-slate-50 dark:!bg-gray-800" />
            <Panel position="top-right" className="text-xs text-slate-400">
              {nodes.length} dugum, {edges.length} baglanti
            </Panel>
          </ReactFlow>
        </div>

        {/* Right sidebar: node editor */}
        <div className="w-64 shrink-0">
          {selectedNode ? (
            <div className="space-y-4 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800 p-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Dugum Ozellikleri
                </h3>
                <button
                  type="button"
                  onClick={deleteSelectedNode}
                  className="text-xs text-red-500 hover:text-red-700"
                  aria-label="Dugumu sil"
                >
                  Sil
                </button>
              </div>

              <div className="text-xs text-slate-400 uppercase">
                {DEFAULT_NODE_LABELS[selectedNode.type || ''] || selectedNode.type}
              </div>

              <Input
                label="Etiket"
                value={(selectedNode.data.label as string) || ''}
                onChange={(e) => updateNodeData('label', e.target.value)}
              />

              {selectedNode.type === 'trigger' && (
                <>
                  <Select
                    label="Varlık Tipi"
                    options={ENTITY_TYPE_OPTIONS}
                    value={(selectedNode.data.entity_type as string) || 'opportunity'}
                    onChange={(e) => updateNodeData('entity_type', e.target.value)}
                  />
                  <Select
                    label="Tetikleyici Olay"
                    options={currentTriggerOptions}
                    value={(selectedNode.data.trigger_event as string) || ''}
                    onChange={(e) => updateNodeData('trigger_event', e.target.value)}
                  />
                </>
              )}

              {selectedNode.type === 'condition' && (
                <>
                  <Input
                    label="Alan"
                    placeholder="stage"
                    value={(selectedNode.data.field as string) || ''}
                    onChange={(e) => updateNodeData('field', e.target.value)}
                  />
                  <Select
                    label="Operator"
                    options={OPERATOR_OPTIONS}
                    value={(selectedNode.data.operator as string) || 'eq'}
                    onChange={(e) => updateNodeData('operator', e.target.value)}
                  />
                  <Input
                    label="Değer"
                    placeholder="negotiation"
                    value={(selectedNode.data.value as string) || ''}
                    onChange={(e) => updateNodeData('value', e.target.value)}
                  />
                </>
              )}

              {selectedNode.type === 'action' && (
                <>
                  <Select
                    label="Aksiyon Tipi"
                    options={ACTION_TYPE_OPTIONS}
                    value={(selectedNode.data.action_type as string) || 'send_notification'}
                    onChange={(e) => updateNodeData('action_type', e.target.value)}
                  />
                  <Input
                    label="Baslik"
                    placeholder="Bildirim basligi"
                    value={(selectedNode.data.title as string) || ''}
                    onChange={(e) => updateNodeData('title', e.target.value)}
                  />
                  <Input
                    label="Mesaj"
                    placeholder="Detay mesaji"
                    value={(selectedNode.data.message as string) || ''}
                    onChange={(e) => updateNodeData('message', e.target.value)}
                  />
                </>
              )}

              {selectedNode.type === 'decision' && (
                <Input
                  label="Kosul Metni"
                  placeholder="Tutar > 10000?"
                  value={(selectedNode.data.condition_text as string) || ''}
                  onChange={(e) => updateNodeData('condition_text', e.target.value)}
                />
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 dark:border-slate-700 p-4 text-center text-sm text-slate-400">
              Bir dugum seçin veya yeni dugum surukleyin
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
