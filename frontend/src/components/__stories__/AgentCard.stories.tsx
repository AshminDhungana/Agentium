import type { Meta, StoryObj } from '@storybook/react';
import { AgentCard } from '../agents/AgentCard';
import { Agent } from '../../types';

/**
 * AgentCard stories -- demonstrates the compact card component
 * summarizing an agent's core metadata across different types and states.
 */

const meta: Meta<typeof AgentCard> = {
  title: 'Agents/AgentCard',
  component: AgentCard,
  tags: ['autodocs'],
  argTypes: {
    agent: { description: 'The agent to display' },
    onSpawn: { description: 'Callback for spawning agent' },
    onTerminate: { description: 'Callback for terminating agent' },
    onPromote: { description: 'Optional callback for task-agent promotion' },
  },
};
export default meta;

type Story = StoryObj<typeof AgentCard>;

const baseAgent: Agent = {
  id: 'agent-1',
  agentium_id: 'A001',
  agent_type: 'head_of_council',
  name: 'Head of Council',
  status: 'active',
  subordinates: [],
  stats: { tasks_completed: 42, tasks_failed: 2, success_rate: 95 },
  constitution_version: 'v1.0',
  is_terminated: false,
};

export const HeadOfCouncil: Story = {
  args: {
    agent: baseAgent,
    onSpawn: () => {},
    onTerminate: () => {},
  },
};

export const CouncilMember: Story = {
  args: {
    agent: {
      ...baseAgent,
      agent_type: 'council_member',
      name: 'Council Delegate',
      status: 'deliberating',
    },
    onSpawn: () => {},
    onTerminate: () => {},
  },
};

export const TaskAgent: Story = {
  args: {
    agent: {
      ...baseAgent,
      agent_type: 'task_agent',
      name: 'Task Runner',
      status: 'working',
      health_score: 78,
      active_task_count: 3,
    },
    onSpawn: () => {},
    onTerminate: () => {},
    onPromote: () => {},
  },
};

export const TerminatedAgent: Story = {
  args: {
    agent: {
      ...baseAgent,
      agent_type: 'task_agent',
      name: 'Decommissioned Worker',
      status: 'terminated',
      is_terminated: true,
    },
    onSpawn: () => {},
    onTerminate: () => {},
  },
};
