import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { WorkflowDesignerPage } from '../WorkflowDesignerPage';
import { api } from '@/services/api';

// Mock api
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('@/hooks/useToast', () => ({
  showToast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/store/websocketStore', () => ({
  useWebSocketStore: vi.fn(() => ({ lastWorkflowExecution: null })),
}));

vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: vi.fn(() => true),
  BREAKPOINTS: { sm: '(min-width: 640px)', lg: '(min-width: 1024px)' },
}));

const mockWorkflow = {
  id: 'wf-1',
  name: 'Test Workflow',
  description: 'Test description',
  version: 1,
  is_active: true,
  template_json: { steps: [] },
  schedule_cron: '0 0 * * *',
};

const mockVersions = [
  { version: 3, template_json: { steps: [] }, created_at: new Date().toISOString() },
  { version: 2, template_json: { steps: [] }, created_at: new Date(Date.now() - 86400000).toISOString() },
  { version: 1, template_json: { steps: [] }, created_at: new Date(Date.now() - 172800000).toISOString() },
];

describe('WorkflowDesignerPage - New Workflow Mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.get as any).mockImplementation((url: string) => {
      if (url.includes('/versions')) {
        return Promise.resolve({ data: mockVersions });
      }
      return Promise.resolve({ data: mockWorkflow });
    });
    (api.put as any).mockResolvedValue({});
    (api.post as any).mockResolvedValue({ data: { id: 'wf-new', name: 'New Workflow', version: 1 } });
  });

  it('shows "New Workflow" header when id is "new"', async () => {
    render(
      <MemoryRouter initialEntries={['/workflows/new']}>
        <Routes>
          <Route path="/workflows/:id" element={<WorkflowDesignerPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('New Workflow')).toBeInTheDocument();
    });
  });

  it('calls POST on first save for new workflow', async () => {
    render(
      <MemoryRouter initialEntries={['/workflows/new']}>
        <Routes>
          <Route path="/workflows/:id" element={<WorkflowDesignerPage />} />
        </Routes>
      </MemoryRouter>
    );

    // Wait for load, then click save
    await waitFor(() => {
      expect(screen.getByText('New Workflow')).toBeInTheDocument();
    });

    const saveButton = screen.getByRole('button', { name: /save/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/api/v1/workflows/', expect.any(Object));
    });
  });

  it('shows "View Executions" button in header for existing workflows', async () => {
    (api.get as any).mockImplementation((url: string) => {
      if (url.includes('/versions')) {
        return Promise.resolve({ data: mockVersions });
      }
      return Promise.resolve({ data: mockWorkflow });
    });

    render(
      <MemoryRouter initialEntries={['/workflows/wf-1']}>
        <Routes>
          <Route path="/workflows/:id" element={<WorkflowDesignerPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /view executions/i })).toBeInTheDocument();
    });
  });
});