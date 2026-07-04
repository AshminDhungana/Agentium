import type { Meta, StoryObj } from '@storybook/react';
import { TaskCard } from '../tasks/TaskCard';
import { Task } from '../../types';

/**
 * TaskCard stories -- demonstrates the card displaying a single task's
 * metadata, status badge, priority, and optional action buttons.
 */

const meta: Meta<typeof TaskCard> = {
  title: 'Tasks/TaskCard',
  component: TaskCard,
  tags: ['autodocs'],
  argTypes: {
    task: { description: 'The task to display' },
    onClick: { description: 'Callback when the card is clicked' },
    onViewLive: { description: 'Callback for viewing live browser session' },
  },
};
export default meta;

type Story = StoryObj<typeof TaskCard>;

const baseTask: Task = {
  id: 'task-1',
  title: 'Analyze market data for Q2 projections',
  description: 'Run comprehensive analysis on daily market data to produce Q2 financial projections.',
  status: 'in_progress',
  priority: 'high',
  task_type: 'analysis',
  progress: 65,
  assigned_agents: { task_agents: [] },
  governance: { requires_deliberation: false, council_approved: true, head_approved: true },
  created_at: new Date().toISOString(),
};

export const InProgress: Story = {
  args: {
    task: baseTask,
    onClick: () => {},
    onViewLive: () => {},
  },
};

export const Completed: Story = {
  args: {
    task: {
      ...baseTask,
      status: 'completed',
      progress: 100,
    },
    onClick: () => {},
  },
};

export const Failed: Story = {
  args: {
    task: {
      ...baseTask,
      status: 'failed',
      progress: 30,
    },
    onClick: () => {},
  },
};

export const Pending: Story = {
  args: {
    task: {
      ...baseTask,
      status: 'pending',
      priority: 'critical',
      progress: 0,
    },
    onClick: () => {},
  },
};

export const SovereignPriority: Story = {
  args: {
    task: {
      ...baseTask,
      priority: 'sovereign',
      status: 'executing',
      progress: 45,
    },
    onClick: () => {},
  },
};
