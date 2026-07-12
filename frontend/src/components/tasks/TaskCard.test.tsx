import { render, screen } from '@testing-library/react';
import { TaskCard } from './TaskCard';

// Minimal task fixture: a browser task that is actively streaming.
// `as any` keeps the fixture terse; TaskCard only reads a handful of
// fields (status, task_type, assigned_agents, title, …) and guards the
// rest (governance, delegation, error_info) with optional chaining.
const browserTask = {
  id: 'task-123',
  agentium_id: 'task-123',
  title: 'Open the dashboard',
  description: 'Navigate to the live metrics page',
  status: 'in_progress',
  priority: 'normal',
  task_type: 'browser',
  progress: 35,
  assigned_agents: { task_agents: [] },
  governance: { requires_deliberation: false, council_approved: false, head_approved: false },
  created_at: '2026-07-12T00:00:00.000Z',
} as any;

const browserTaskPending = {
  ...browserTask,
  status: 'pending',
} as any;

const codeTaskActive = {
  ...browserTask,
  task_type: 'code',
} as any;

test('shows View Live for a browser task that is in_progress', () => {
  render(<TaskCard task={browserTask} onViewLive={() => {}} />);
  const btn = screen.getByRole('button', { name: /view live/i }) as HTMLButtonElement;
  expect(btn).toBeInTheDocument();
  expect(btn.disabled).toBe(false);
});

test('hides View Live for a browser task that is not in_progress', () => {
  render(<TaskCard task={browserTaskPending} onViewLive={() => {}} />);
  expect(screen.queryByRole('button', { name: /view live/i })).not.toBeInTheDocument();
});

test('hides View Live for a non-browser task even when active', () => {
  render(<TaskCard task={codeTaskActive} onViewLive={() => {}} />);
  expect(screen.queryByRole('button', { name: /view live/i })).not.toBeInTheDocument();
});
