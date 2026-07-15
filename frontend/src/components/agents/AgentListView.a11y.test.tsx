import { render } from '@testing-library/react';
import { describe, it } from 'vitest';
import { AgentListView } from './AgentListView';
import { Agent } from '@/types';
import { checkA11y } from '@/test/a11y';

const agent: Agent = {
  id: '30001',
  name: 'Task Alpha',
  agent_type: 'task_agent',
  status: 'active',
  tier: 3,
  capabilities: [],
} as unknown as Agent;

describe('AgentListView accessibility', () => {
  it('names icon-only action buttons', async () => {
    const { container, getByRole } = render(
      <AgentListView
        agents={[agent]}
        onSpawn={() => {}}
        onPromote={() => {}}
        onTerminate={() => {}}
      />
    );

    expect(getByRole('button', { name: 'Terminate agent' })).toBeInTheDocument();

    await checkA11y(container!);
  });
});
