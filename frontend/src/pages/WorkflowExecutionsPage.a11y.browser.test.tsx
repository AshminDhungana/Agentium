import { describe, it, expect } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { WorkflowExecutionsPage } from '@/pages/WorkflowExecutionsPage';
import { api } from '@/services/api';
import { useWebSocketStore } from '@/store/websocketStore';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('@/store/websocketStore', () => ({
  useWebSocketStore: vi.fn(() => ({ lastWorkflowExecution: null })),
}));

vi.mock('@/hooks/useToast', () => ({
  showToast: { success: vi.fn(), error: vi.fn() },
}));

const mockWorkflows = [
  { id: 'wf-1', name: 'Test Workflow', version: 1, schedule_cron: '0 0 * * *', is_active: true },
];

const mockExecutions = [
  { id: 'exec-1', workflow_id: 'wf-1', status: 'COMPLETED', current_step_index: 3, started_at: '2024-01-15T10:00:00Z', completed_at: '2024-01-15T10:05:00Z', context_data: {} },
  { id: 'exec-2', workflow_id: 'wf-1', status: 'RUNNING', current_step_index: 1, started_at: '2024-01-15T11:00:00Z', completed_at: null, context_data: {} },
];

describe('WorkflowExecutionsPage color-contrast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.get as any).mockResolvedValueOnce({ data: mockWorkflows[0] });
    (api.get as any).mockResolvedValueOnce({ data: mockExecutions });
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(
      <MemoryRouter initialEntries={['/workflows/wf-1/executions']}>
        <Routes>
          <Route path="/workflows/:id/executions" element={<WorkflowExecutionsPage />} />
        </Routes>
      </MemoryRouter>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <MemoryRouter initialEntries={['/workflows/wf-1/executions']}>
        <Routes>
          <Route path="/workflows/:id/executions" element={<WorkflowExecutionsPage />} />
        </Routes>
      </MemoryRouter>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});