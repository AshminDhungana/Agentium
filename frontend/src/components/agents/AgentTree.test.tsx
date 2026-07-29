import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, beforeAll, afterAll } from 'vitest';
import { AgentTree } from './AgentTree';
import { Agent } from '@/types';
import { DragDropProvider } from '@/context/DragDropContext';

/**
 * Virtualizer factory created via vi.hoisted to ensure it's available
 * at mock factory execution time (vi.mock is hoisted).
 */
const { virtualizerFactory } = vi.hoisted(() => {
  const createMockAgent = (overrides: Partial<Agent> = {}): Agent => ({
    agentium_id: 'test',
    id: 'test',
    name: 'Test',
    agent_type: 'lead_agent',
    status: 'active',
    stats: { tasks_completed: 0, tasks_failed: 0 },
    subordinates: [],
    is_terminated: false,
    constitution_version: '1.0',
    health_score: 90,
    active_task_count: 0,
    ...overrides,
  });

  const buildDefaultMockVirtualItems = () => {
    const head = createMockAgent({ agentium_id: 'head', name: 'Head', agent_type: 'head_of_council' });
    const lead = createMockAgent({ agentium_id: 'agent-1', name: 'Lead Agent', agent_type: 'lead_agent' });
    const task = createMockAgent({ agentium_id: 'agent-2', name: 'Task Agent', agent_type: 'task_agent' });
    return [
      { agent: head, level: 0, hasChildren: true, isExpanded: true, isCriticHeader: false, isCritic: false },
      { agent: lead, level: 1, hasChildren: false, isExpanded: false, isCriticHeader: false, isCritic: false },
      { agent: task, level: 2, hasChildren: false, isExpanded: false, isCriticHeader: false, isCritic: false },
    ];
  };

  const createMockVirtualizer = (items: ReturnType<typeof buildDefaultMockVirtualItems>) => ({
    getVirtualItems: () => items.map((item, index) => ({
      index,
      key: item.agent.agentium_id,
      start: index * 256,
      size: 256,
    })),
    getTotalSize: () => items.length * 256,
    measureElement: vi.fn(),
    parentRef: { current: null },
  });

  let currentVirtualizer = createMockVirtualizer(buildDefaultMockVirtualItems());

  return {
    virtualizerFactory: {
      useVirtualizer: vi.fn(() => currentVirtualizer),
      useVirtual: vi.fn(() => ({
        virtualRows: [],
        totalSize: 1000,
        parentRef: vi.fn(),
      })),
      __setVirtualizer: (virtualizer: ReturnType<typeof createMockVirtualizer>) => {
        currentVirtualizer = virtualizer;
      },
      __buildMockVirtualItems: buildDefaultMockVirtualItems,
    },
  };
});

// Mock @tanstack/react-virtual using the hoisted factory
vi.mock('@tanstack/react-virtual', () => virtualizerFactory);

// Mock Agent type for testing
const createMockAgent = (overrides: Partial<Agent> = {}): Agent => ({
  agentium_id: 'agent-1',
  id: 'agent-1',
  name: 'Test Agent',
  agent_type: 'lead_agent',
  status: 'active',
  stats: { tasks_completed: 5, tasks_failed: 0 },
  subordinates: [],
  is_terminated: false,
  constitution_version: '1.0',
  health_score: 90,
  active_task_count: 0,
  ...overrides,
});

// Default test data matching the mock virtualizer's default
// Structure: Head (head_of_council) -> Lead Agent (lead_agent) -> Task Agent (task_agent)
const defaultHeadAgent = createMockAgent({
  agentium_id: 'head',
  name: 'Head',
  agent_type: 'head_of_council',
  subordinates: ['agent-1']
});
const defaultLeadAgent = createMockAgent({
  agentium_id: 'agent-1',
  name: 'Lead Agent',
  agent_type: 'lead_agent',
  subordinates: ['agent-2']
});
const defaultTaskAgent = createMockAgent({
  agentium_id: 'agent-2',
  name: 'Task Agent',
  agent_type: 'task_agent',
  subordinates: []
});

const mockAgentsMap = new Map<string, Agent>([
  ['head', defaultHeadAgent],
  ['agent-1', defaultLeadAgent],
  ['agent-2', defaultTaskAgent],
]);

const mockOnSpawn = vi.fn();
const mockOnTerminate = vi.fn();
const mockOnPromote = vi.fn();
const mockOnDropCommit = vi.fn();

/**
 * Render AgentTree with default test data (matches mock virtualizer defaults).
 * Other tests should call virtualizerFactory.__setVirtualizer with a
 * virtualizer built from their own data before rendering.
 */
const renderTree = () => {
  // Build virtualizer to match the component's actual virtualItems from this test data
  buildVirtualizerFromData(defaultHeadAgent, mockAgentsMap);

  return render(
    <DragDropProvider onDropCommit={mockOnDropCommit}>
      <AgentTree
        agent={defaultHeadAgent}
        agentsMap={mockAgentsMap}
        onSpawn={mockOnSpawn}
        onTerminate={mockOnTerminate}
        onPromote={mockOnPromote}
      />
    </DragDropProvider>
  );
};

/**
 * Build a virtualizer from the given agentsMap and rootAgent that matches
 * what AgentTree.computeVirtualItems would produce.
 * This mirrors the flattenDeep logic in AgentTree.tsx.
 */
function buildVirtualizerFromData(rootAgent: Agent | undefined, agentsMap: Map<string, Agent>, criticExpanded = true) {
  if (!rootAgent) {
    virtualizerFactory.__setVirtualizer({
      getVirtualItems: () => [],
      getTotalSize: () => 0,
      measureElement: vi.fn(),
      parentRef: { current: null },
    });
    return;
  }

  // Build flattenedNodes (same logic as AgentTree.tsx)
  const nodes: any[] = [];
  const allCritics: Agent[] = [];

  for (const a of agentsMap.values()) {
    if (a.agent_type === 'critic' || (a.agentium_id && a.agentium_id.startsWith('critic'))) {
      allCritics.push(a);
    }
  }

  const isCriticAgent = (agent: Agent): boolean => {
    return agent.agent_type === 'critic' || (agent.agentium_id && agent.agentium_id.startsWith('critic'));
  };

  const collapsedNodes = new Set<string>(); // default all expanded

  const flattenDeep = (agentId: string, depth: number) => {
    const ag = agentsMap.get(agentId);
    if (!ag || isCriticAgent(ag)) return;

    const subordinateIds = Array.isArray(ag.subordinates) ? ag.subordinates : [];
    const mainChildren = subordinateIds.filter(subId => {
      const sub = agentsMap.get(subId);
      return sub && !isCriticAgent(sub);
    });
    const hasChildren = mainChildren.length > 0;
    const isCollapsed = collapsedNodes.has(ag.agentium_id);

    nodes.push({ agent: ag, level: depth, hasChildren, isExpanded: !isCollapsed });

    if (!isCollapsed && hasChildren) {
      for (const subId of mainChildren) flattenDeep(subId, depth + 1);
    }
  };

  flattenDeep(rootAgent.agentium_id, 0);

  // Build virtualItems (same logic as AgentTree virtualItems useMemo)
  const virtualItems = [...nodes];

  if (allCritics.length > 0) {
    virtualItems.push({
      agent: {
        agentium_id: '__critic_header__', name: 'Critic Header',
        agent_type: 'task_agent', status: 'active',
        stats: { tasks_completed: 0, tasks_failed: 0 },
        subordinates: [], is_terminated: false, constitution_version: '',
      } as unknown as Agent,
      level: 0, hasChildren: true, isExpanded: criticExpanded, isCriticHeader: true,
    });

    if (criticExpanded) {
      for (const critic of allCritics) {
        virtualItems.push({ agent: critic, level: 1, hasChildren: false, isExpanded: false, isCritic: true });
      }
    }
  }

  const virtualizer = {
    getVirtualItems: () => virtualItems.map((item, index) => ({
      index,
      key: item.agent.agentium_id,
      start: index * 256,
      size: 256,
    })),
    getTotalSize: () => virtualItems.length * 256,
    measureElement: vi.fn(),
    parentRef: { current: null },
  };

  virtualizerFactory.__setVirtualizer(virtualizer);
}

describe('AgentTree', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset virtualizer to default for each test
    virtualizerFactory.__setVirtualizer(
      { getVirtualItems: () => [], getTotalSize: () => 0, measureElement: vi.fn(), parentRef: { current: null } }
    );
  });

  it('renders the root agent', () => {
    // Default test data matches default mock, so just render
    renderTree();
    expect(screen.getByText('Head')).toBeInTheDocument();
  });

  it('renders subordinate agents', () => {
    renderTree();
    // "Lead Agent" appears in both header and body of the card, so use getAllByText
    expect(screen.getAllByText('Lead Agent').length).toBeGreaterThan(0);
    // "Task Agent" also appears multiple times
    expect(screen.getAllByText('Task Agent').length).toBeGreaterThan(0);
  });

  it('shows tier toolbar when max depth > 0', () => {
    renderTree();
    expect(screen.getByText('Tier Groups:')).toBeInTheDocument();
    expect(screen.getByText('Expand All')).toBeInTheDocument();
    expect(screen.getByText('Level 1')).toBeInTheDocument();
  });

  it('renders critic section when critics exist', () => {
    const criticAgent = createMockAgent({
      agentium_id: 'critic-1',
      name: 'Critic Agent',
      agent_type: 'code_critic'
    });
    const agentsWithCritics = new Map(mockAgentsMap);
    agentsWithCritics.set('critic-1', criticAgent);

    // Update virtualizer to match this test's data
    buildVirtualizerFromData(defaultHeadAgent, agentsWithCritics);

    render(
      <DragDropProvider onDropCommit={mockOnDropCommit}>
        <AgentTree
          agent={defaultHeadAgent}
          agentsMap={agentsWithCritics}
          onSpawn={mockOnSpawn}
          onTerminate={mockOnTerminate}
          onPromote={mockOnPromote}
        />
      </DragDropProvider>
    );

    expect(screen.getByText('Critic Agents')).toBeInTheDocument();
    expect(screen.getByText('Critic Agent')).toBeInTheDocument();
  });

  it('does not render when no root agent', () => {
    // Empty virtualizer for no root agent
    virtualizerFactory.__setVirtualizer({
      getVirtualItems: () => [],
      getTotalSize: () => 0,
      measureElement: vi.fn(),
      parentRef: { current: null },
    });

    const { container } = render(
      <DragDropProvider onDropCommit={mockOnDropCommit}>
        <AgentTree
          agent={undefined as any}
          agentsMap={mockAgentsMap}
          onSpawn={mockOnSpawn}
          onTerminate={mockOnTerminate}
          onPromote={mockOnPromote}
        />
      </DragDropProvider>
    );
    expect(container.firstChild).toBeNull();
  });
});

// DraggableCard is not exported, so we test through AgentTree render
describe('AgentTree - DraggableCard behavior', () => {
  it('allows drag for non-head agents', () => {
    const draggableAgent = createMockAgent({
      agentium_id: 'draggable-1',
      name: 'Draggable Lead',
      agent_type: 'lead_agent'
    });

    const treeAgentMap = new Map([
      ['head', createMockAgent({ agentium_id: 'head', agent_type: 'head_of_council', name: 'Head', subordinates: ['draggable-1'] })],
      ['draggable-1', draggableAgent],
    ]);

    const headAgent = treeAgentMap.get('head')!;

    // Update virtualizer for this test's data
    buildVirtualizerFromData(headAgent, treeAgentMap);

    render(
      <DragDropProvider onDropCommit={mockOnDropCommit}>
        <AgentTree
          agent={headAgent}
          agentsMap={treeAgentMap}
          onSpawn={mockOnSpawn}
          onTerminate={mockOnTerminate}
          onPromote={mockOnPromote}
        />
      </DragDropProvider>
    );

    // Test passes if component renders without error
    expect(screen.getByText('Head')).toBeInTheDocument();
  });

  it('does not allow drag for head_of_council', () => {
    const headAgent = createMockAgent({
      agentium_id: 'head',
      agent_type: 'head_of_council',
      name: 'Head of Council'
    });

    const treeAgentMap = new Map([
      ['head', headAgent],
    ]);

    // Update virtualizer for this test's data (single item)
    buildVirtualizerFromData(headAgent, treeAgentMap);

    render(
      <DragDropProvider onDropCommit={mockOnDropCommit}>
        <AgentTree
          agent={headAgent}
          agentsMap={treeAgentMap}
          onSpawn={mockOnSpawn}
          onTerminate={mockOnTerminate}
          onPromote={mockOnPromote}
        />
      </DragDropProvider>
    );

    // Head agent renders without draggable wrapper
    expect(screen.getByText('Head of Council')).toBeInTheDocument();
  });
});