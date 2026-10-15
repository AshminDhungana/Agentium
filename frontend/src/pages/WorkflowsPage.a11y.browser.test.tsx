import { describe, it, expect } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { WorkflowsPage } from '@/pages/WorkflowsPage';
import { api } from '@/services/api';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('@/hooks/useToast', () => ({
  showToast: { success: vi.fn(), error: vi.fn() },
}));

const mockWorkflows = [
  { id: 'wf-1', name: 'Daily Scraper', description: 'Scrapes data daily', version: 3, schedule_cron: '0 0 * * *', is_active: true },
];

describe('WorkflowsPage color-contrast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.get as any).mockResolvedValue({ data: mockWorkflows });
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(
      <MemoryRouter initialEntries={['/workflows']}>
        <Routes>
          <Route path="/workflows" element={<WorkflowsPage />} />
        </Routes>
      </MemoryRouter>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <MemoryRouter initialEntries={['/workflows']}>
        <Routes>
          <Route path="/workflows" element={<WorkflowsPage />} />
        </Routes>
      </MemoryRouter>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});