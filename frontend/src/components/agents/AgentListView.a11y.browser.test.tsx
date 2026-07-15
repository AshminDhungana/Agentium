import { describe, it } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { AgentListView } from '@/components/agents/AgentListView';
import type { Agent } from '@/types';

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="bg-white dark:bg-[#0f1117] p-6">{children}</div>
);

const mockAgent: Agent = {
  id: '1',
  agentium_id: '30042',
  agent_type: 'task_agent',
  name: 'Task Agent 30042',
  status: 'active',
  subordinates: [],
  stats: { tasks_completed: 12, tasks_failed: 1 },
  active_task_count: 0,
  constitution_version: 'v1.0.0',
  is_terminated: false,
};

const noop = () => {};

describe('AgentListView color-contrast', () => {
  it('passes in light theme (with agent)', async () => {
    const result = await auditRoute(
      <Shell><AgentListView agents={[mockAgent]} onSpawn={noop} onTerminate={noop} onPromote={noop} /></Shell>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme (with agent)', async () => {
    const result = await auditRoute(
      <Shell><AgentListView agents={[mockAgent]} onSpawn={noop} onTerminate={noop} onPromote={noop} /></Shell>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in light theme (empty)', async () => {
    const result = await auditRoute(
      <Shell><AgentListView agents={[]} onSpawn={noop} onTerminate={noop} /></Shell>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme (empty)', async () => {
    const result = await auditRoute(
      <Shell><AgentListView agents={[]} onSpawn={noop} onTerminate={noop} /></Shell>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});
