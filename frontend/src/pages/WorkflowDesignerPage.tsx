import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  type Node,
  type Edge,
  type Connection,
  type OnConnect,
  type NodeMouseHandler,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { api } from '@/services/api';
import { showToast } from '@/hooks/useToast';
import { useMediaQuery, BREAKPOINTS } from '@/hooks/useMediaQuery';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { Button } from '@/components/ui/button';
import {
  Save,
  ArrowLeft,
  History,
  Plus,
} from 'lucide-react';

import { WorkflowStepNode, type WorkflowNodeData } from '@/components/workflows/WorkflowStepNode';
import { ConditionalEdge } from '@/components/workflows/ConditionalEdge';
import { StepPalette } from '@/components/workflows/StepPalette';
import { NodeConfigDrawer } from '@/components/workflows/NodeConfigDrawer';
import { VersionHistorySidebar } from '@/components/workflows/VersionHistorySidebar';
import { MobileWorkflowViewer } from '@/components/workflows/MobileWorkflowViewer';

// ── React Flow custom registrations ─────────────────────────────────────────

const nodeTypes = { workflowStep: WorkflowStepNode };
const edgeTypes = { conditional: ConditionalEdge };

// ── Types ───────────────────────────────────────────────────────────────────

interface StepConfig {
  step_index: number;
  type: string;
  config: Record<string, unknown>;
  on_success_step?: number;
  on_failure_step?: number;
}

interface WorkflowData {
  id: string;
  name: string;
  description: string;
  version: number;
  is_active: boolean;
  template_json: { steps: StepConfig[] };
  schedule_cron?: string;
}

// ── Conversion helpers ──────────────────────────────────────────────────────

const VERTICAL_SPACING = 160;
const HORIZONTAL_OFFSET = 300;

function stepsToNodesAndEdges(steps: StepConfig[]): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = steps.map((step, i) => ({
    id: `step-${step.step_index}`,
    type: 'workflowStep',
    position: { x: 250, y: i * VERTICAL_SPACING },
    data: {
      step_index: step.step_index,
      type: step.type,
      config: step.config,
      on_success_step: step.on_success_step,
      on_failure_step: step.on_failure_step,
    } satisfies WorkflowNodeData,
  }));

  const edges: Edge[] = [];
  steps.forEach((step) => {
    // Success edge
    const successTarget = step.on_success_step;
    if (successTarget !== undefined) {
      edges.push({
        id: `e-${step.step_index}-s-${successTarget}`,
        source: `step-${step.step_index}`,
        target: `step-${successTarget}`,
        sourceHandle: 'success',
        type: 'conditional',
      });
    }

    // Failure edge
    const failureTarget = step.on_failure_step;
    if (failureTarget !== undefined) {
      edges.push({
        id: `e-${step.step_index}-f-${failureTarget}`,
        source: `step-${step.step_index}`,
        target: `step-${failureTarget}`,
        sourceHandle: 'failure',
        type: 'conditional',
      });
    }
  });

  // Auto-link sequential steps that don't have explicit success routing
  for (let i = 0; i < steps.length - 1; i++) {
    const step = steps[i];
    if (step.on_success_step === undefined) {
      const nextStep = steps[i + 1];
      edges.push({
        id: `e-${step.step_index}-auto-${nextStep.step_index}`,
        source: `step-${step.step_index}`,
        target: `step-${nextStep.step_index}`,
        sourceHandle: 'success',
        type: 'conditional',
      });
    }
  }

  return { nodes, edges };
}

function nodesToSteps(nodes: Node[], edges: Edge[]): StepConfig[] {
  return nodes.map(n => {
    const data = n.data as unknown as WorkflowNodeData;

    // Find success and failure edges from this node
    const successEdge = edges.find(
      e => e.source === n.id && e.sourceHandle === 'success'
    );
    const failureEdge = edges.find(
      e => e.source === n.id && e.sourceHandle === 'failure'
    );

    return {
      step_index: data.step_index,
      type: data.type,
      config: data.config,
      on_success_step: successEdge
        ? parseInt(successEdge.target.replace('step-', ''))
        : undefined,
      on_failure_step: failureEdge
        ? parseInt(failureEdge.target.replace('step-', ''))
        : undefined,
    };
  });
}

// ── Inner Designer (needs ReactFlowProvider context) ────────────────────────

function DesignerInner() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // Responsive detection
  const isTabletUp = useMediaQuery(BREAKPOINTS.sm);   // ≥ 640px
  const isDesktop  = useMediaQuery(BREAKPOINTS.lg);    // ≥ 1024px
  const isPhone    = !isTabletUp;

  // Data state
  const [workflow, setWorkflow] = useState<WorkflowData | null>(null);
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);

  // Canvas state
  const [nodes, setNodes, onNodesChange] = useNodesState([] as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([] as Edge[]);

  // UI state
  const [selectedNode, setSelectedNode]       = useState<WorkflowNodeData | null>(null);
  const [configDrawerOpen, setConfigDrawerOpen] = useState(false);
  const [versionSidebarOpen, setVersionSidebarOpen] = useState(false);
  const [showMobilePalette, setShowMobilePalette]  = useState(false);

  // Detect dark mode for canvas theme
  const [isDark, setIsDark] = useState(
    typeof window !== 'undefined' && document.documentElement.classList.contains('dark')
  );
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains('dark'));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  // Ref for next step index
  const nextStepIndexRef = useRef(0);

  // ── Load workflow ─────────────────────────────────────────────────────────

  useEffect(() => {
    if (!id) return;
    setLoading(true);

    api.get(`/api/v1/workflows/${id}`)
      .then(res => {
        const wf: WorkflowData = res.data;
        setWorkflow(wf);

        const steps: StepConfig[] = wf.template_json?.steps ?? [];
        const { nodes: n, edges: e } = stepsToNodesAndEdges(steps);
        setNodes(n);
        setEdges(e);

        // Track next available step index
        nextStepIndexRef.current = steps.length > 0
          ? Math.max(...steps.map(s => s.step_index)) + 1
          : 0;
      })
      .catch(() => {
        showToast.error('Failed to load workflow');
        navigate('/tasks');
      })
      .finally(() => setLoading(false));
  }, [id, setNodes, setEdges, navigate]);

  // ── Auto-open version sidebar on desktop ──────────────────────────────────

  useEffect(() => {
    if (isDesktop) setVersionSidebarOpen(true);
    else setVersionSidebarOpen(false);
  }, [isDesktop]);

  // ── Edge connections ──────────────────────────────────────────────────────

  const onConnect: OnConnect = useCallback(
    (conn: Connection) => {
      setEdges(eds => addEdge({ ...conn, type: 'conditional' }, eds));
    },
    [setEdges],
  );

  // ── Node click → open config drawer ───────────────────────────────────────

  const onNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      setSelectedNode(node.data as unknown as WorkflowNodeData);
      setConfigDrawerOpen(true);
    },
    [],
  );

  // ── Add node (from palette drag-and-drop or button) ───────────────────────

  const handleAddNode = useCallback(
    (type: string, config: Record<string, unknown>, position: { x: number; y: number }) => {
      const stepIndex = nextStepIndexRef.current++;

      const newNode: Node = {
        id: `step-${stepIndex}`,
        type: 'workflowStep',
        position,
        data: {
          step_index: stepIndex,
          type,
          config,
        } satisfies WorkflowNodeData,
      };

      setNodes(nds => [...nds, newNode]);
    },
    [setNodes],
  );

  // ── HTML5 drop handler (desktop drag from palette) ────────────────────────

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const raw = e.dataTransfer.getData('application/agentium-step');
      if (!raw) return;

      const { type, config } = JSON.parse(raw);
      // We need the reactFlowInstance to convert screen to flow position
      // but since we're inside ReactFlowProvider, we use the wrapper's bounds
      const bounds = (e.target as HTMLElement).closest('.react-flow')?.getBoundingClientRect();
      if (!bounds) return;

      const position = {
        x: e.clientX - bounds.left,
        y: e.clientY - bounds.top,
      };

      handleAddNode(type, config, position);
    },
    [handleAddNode],
  );

  // ── Save node config changes ──────────────────────────────────────────────

  const handleSaveNodeConfig = useCallback(
    (stepIndex: number, changes: Partial<WorkflowNodeData>) => {
      setNodes(nds =>
        nds.map(n => {
          const data = n.data as unknown as WorkflowNodeData;
          if (data.step_index === stepIndex) {
            return {
              ...n,
              data: { ...data, ...changes },
            };
          }
          return n;
        }),
      );
    },
    [setNodes],
  );

  // ── Delete node ───────────────────────────────────────────────────────────

  const handleDeleteNode = useCallback(
    (stepIndex: number) => {
      const nodeId = `step-${stepIndex}`;
      setNodes(nds => nds.filter(n => n.id !== nodeId));
      setEdges(eds => eds.filter(e => e.source !== nodeId && e.target !== nodeId));
    },
    [setNodes, setEdges],
  );

  // ── Save workflow ─────────────────────────────────────────────────────────

  const handleSave = useCallback(async () => {
    if (!workflow || !id) return;
    setSaving(true);
    try {
      const steps = nodesToSteps(nodes, edges);
      await api.put(`/api/v1/workflows/${id}`, {
        name: workflow.name,
        template_json: { steps },
      });
      setWorkflow(prev => prev ? { ...prev, version: prev.version + 1 } : prev);
      showToast.success('Workflow saved');
    } catch {
      showToast.error('Failed to save workflow');
    } finally {
      setSaving(false);
    }
  }, [workflow, id, nodes, edges]);

  // ── All step indexes (for config drawer dropdowns) ────────────────────────

  const allStepIndexes = useMemo(
    () => nodes.map(n => (n.data as unknown as WorkflowNodeData).step_index),
    [nodes],
  );

  // ── Loading state ─────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!workflow) return null;

  // ── Phone → read-only view ────────────────────────────────────────────────

  if (isPhone) {
    return (
      <MobileWorkflowViewer
        workflowName={workflow.name}
        version={workflow.version}
        steps={workflow.template_json?.steps ?? []}
      />
    );
  }

  // ── Tablet / Desktop → full canvas ────────────────────────────────────────

  return (
    <div className="flex flex-col h-full">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="
        flex items-center justify-between gap-4 px-4 py-3
        border-b border-gray-200 dark:border-[#1e2535]
        bg-white dark:bg-[#161b27]
        flex-shrink-0
      ">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate('/tasks')}
            aria-label="Back to tasks"
            className="p-2 rounded-lg text-gray-600 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="min-w-0">
            <h1 className="text-base font-bold text-gray-900 dark:text-white truncate">
              {workflow.name}
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 dark:bg-[#1e2535] dark:text-gray-400">
                v{workflow.version}
              </span>
              <span className="text-xs text-gray-600 dark:text-gray-500">
                {nodes.length} steps
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Version history toggle (tablet only — desktop auto-opens) */}
          {!isDesktop && (
            <button
              onClick={() => setVersionSidebarOpen(v => !v)}
              aria-label="Toggle version history"
              className={`
                p-2 rounded-lg transition-colors
                ${versionSidebarOpen
                  ? 'bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400'
                  : 'text-gray-600 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535]'
                }
              `}
            >
              <History className="w-4 h-4" />
            </button>
          )}

          <Button
            onClick={handleSave}
            disabled={saving}
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm"
          >
            {saving ? <LoadingSpinner size="sm" /> : <Save className="w-4 h-4 mr-1.5" />}
            Save
          </Button>
        </div>
      </div>

      {/* ── Canvas area ──────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Step palette — sidebar on desktop */}
        {isDesktop && (
          <StepPalette
            variant="sidebar"
            onAddNode={handleAddNode}
          />
        )}

        {/* React Flow canvas */}
        <div className="flex-1 relative" onDragOver={onDragOver} onDrop={onDrop}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            minZoom={0.3}
            maxZoom={2}
            deleteKeyCode="Delete"
            className="bg-gray-50 dark:bg-[#0a0d14]"
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={20}
              size={1}
              color={isDark ? '#374151' : '#d1d5db'}
              className="dark:!bg-[#0a0d14]"
            />
            <Controls
              className="!bg-white dark:!bg-[#161b27] !border-gray-200 dark:!border-[#1e2535] !shadow-lg !rounded-xl [&>button]:!bg-white [&>button]:dark:!bg-[#161b27] [&>button]:!border-gray-200 [&>button]:dark:!border-[#1e2535] [&>button]:!text-gray-600 [&>button]:dark:!text-gray-600 [&>button:hover]:!bg-gray-100 [&>button:hover]:dark:!bg-[#1e2535]"
            />
            {isDesktop && (
              <MiniMap
                className="!bg-white dark:!bg-[#161b27] !border-gray-200 dark:!border-[#1e2535] !rounded-xl !shadow-lg"
                nodeColor={() => '#6366f1'}
                maskColor="rgba(0, 0, 0, 0.08)"
              />
            )}
          </ReactFlow>

          {/* Tablet FAB for adding steps */}
          {!isDesktop && (
            <button
              onClick={() => setShowMobilePalette(v => !v)}
              aria-label="Toggle steps palette"
              className="
                absolute bottom-5 right-5 z-20
                w-14 h-14 rounded-2xl
                bg-gradient-to-br from-indigo-500 to-purple-600
                text-white shadow-xl shadow-indigo-500/30
                flex items-center justify-center
                active:scale-95 transition-transform
              "
            >
              <Plus className={`w-6 h-6 transition-transform ${showMobilePalette ? 'rotate-45' : ''}`} />
            </button>
          )}

          {/* Tablet bottom sheet palette */}
          {!isDesktop && showMobilePalette && (
            <div className="absolute bottom-20 left-0 right-0 z-10 mx-4">
              <div className="rounded-2xl shadow-2xl shadow-black/20 overflow-hidden">
                <StepPalette
                  variant="bottom-sheet"
                  onAddNode={(type, config, position) => {
                    handleAddNode(type, config, position);
                    setShowMobilePalette(false);
                  }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Version history sidebar */}
        {versionSidebarOpen && (
          <VersionHistorySidebar
            workflowId={id!}
            currentVersion={workflow.version}
            onRollback={() => {
              // Reload workflow after rollback
              api.get(`/api/v1/workflows/${id}`)
                .then(res => {
                  const wf: WorkflowData = res.data;
                  setWorkflow(wf);
                  const steps = wf.template_json?.steps ?? [];
                  const { nodes: n, edges: e } = stepsToNodesAndEdges(steps);
                  setNodes(n);
                  setEdges(e);
                });
            }}
            isExpanded={versionSidebarOpen}
            onToggle={() => setVersionSidebarOpen(v => !v)}
          />
        )}
      </div>

      {/* ── Node config drawer ───────────────────────────────────────────── */}
      <NodeConfigDrawer
        isOpen={configDrawerOpen}
        onClose={() => {
          setConfigDrawerOpen(false);
          setSelectedNode(null);
        }}
        nodeData={selectedNode}
        onSave={handleSaveNodeConfig}
        onDelete={handleDeleteNode}
        allStepIndexes={allStepIndexes}
      />
    </div>
  );
}

// ── Exported page component (wraps in ReactFlowProvider) ────────────────────

export function WorkflowDesignerPage() {
  return (
    <ReactFlowProvider>
      <DesignerInner />
    </ReactFlowProvider>
  );
}
