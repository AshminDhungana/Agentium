import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { WorkflowsPage } from '../WorkflowsPage';
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
  { id: 'wf-2', name: 'Report Generator', description: 'Generates weekly reports', version: 1, schedule_cron: null, is_active: true },
];

describe('WorkflowsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.get as any).mockResolvedValue({ data: mockWorkflows });
  });

  it('renders header with "New Workflow" button', async () => {
    render(
      <MemoryRouter initialEntries={['/workflows']}>
        <Routes>
          <Route path="/workflows" element={<WorkflowsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Workflows')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /new workflow/i })).toBeInTheDocument();
    });
  });

  it('shows workflow cards with name, version, schedule', async () => {
    render(
      <MemoryRouter initialEntries={['/workflows']}>
        <Routes>
          <Route path="/workflows" element={<WorkflowsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Daily Scraper')).toBeInTheDocument();
      expect(screen.getByText('Report Generator')).toBeInTheDocument();
      expect(screen.getByText('v3')).toBeInTheDocument();
      expect(screen.getByText('v1')).toBeInTheDocument();
      expect(screen.getByText('0 0 * * *')).toBeInTheDocument();
      expect(screen.getByText('Manual')).toBeInTheDocument();
    });
  });

  it('shows "Active" badge for active workflows', async () => {
    render(
      <MemoryRouter initialEntries={['/workflows']}>
        <Routes>
          <Route path="/workflows" element={<WorkflowsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getAllByText('Active')).toHaveLength(2);
    });
  });

  it('navigates to designer when clicking Edit', async () => {
    render(
      <MemoryRouter initialEntries={['/workflows']}>
        <Routes>
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/workflows/:id" element={<div>Designer</div>} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      const editButtons = screen.getAllByRole('button', { name: /edit/i });
      fireEvent.click(editButtons[0]);
    });

    await waitFor(() => {
      expect(screen.getByText('Designer')).toBeInTheDocument();
    });
  });

  it('shows empty state when no workflows', async () => {
    (api.get as any).mockResolvedValue({ data: [] });

    render(
      <MemoryRouter initialEntries={['/workflows']}>
        <Routes>
          <Route path="/workflows" element={<WorkflowsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('No workflows yet')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /create first workflow/i })).toBeInTheDocument();
    });
  });

  it('navigates to /workflows/new when clicking "New Workflow"', async () => {
    render(
      <MemoryRouter initialEntries={['/workflows']}>
        <Routes>
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/workflows/new" element={<div>New Designer</div>} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      const newButton = screen.getByRole('button', { name: /new workflow/i });
      fireEvent.click(newButton);
    });

    await waitFor(() => {
      expect(screen.getByText('New Designer')).toBeInTheDocument();
    });
  });
});