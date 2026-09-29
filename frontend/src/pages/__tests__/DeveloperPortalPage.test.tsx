import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('@/services/apiKeysService', () => ({
  apiKeysService: {
    listKeys: vi.fn(),
    createKey: vi.fn(),
    deleteKey: vi.fn(),
    getSpendHistory: vi.fn(),
    testFailover: vi.fn(),
  },
}));

import DeveloperPortalPage from '@/pages/DeveloperPortalPage';
import { apiKeysService } from '@/services/apiKeysService';

describe('DeveloperPortalPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
      configurable: true,
      writable: true,
    });
    vi.mocked(apiKeysService.listKeys).mockResolvedValue({
      overall_status: 'HEALTHY',
      providers: {
        OPENAI: {
          total_keys: 1,
          healthy: 1,
          keys: [
            {
              id: 'key-uuid-1',
              provider: 'OPENAI',
              priority: 1,
              status: 'HEALTHY',
              failure_count: 0,
              cooldown_until: null,
              monthly_budget_usd: 100,
              current_spend_usd: 15.5,
              budget_remaining_pct: 84.5,
            },
          ],
        },
      },
      summary: {},
      generated_at: '2026-09-29T12:00:00Z',
    });
  });

  const renderComponent = () =>
    render(
      <MemoryRouter>
        <DeveloperPortalPage />
      </MemoryRouter>
    );

  it('renders documentation tabs including API Keys', () => {
    renderComponent();
    expect(screen.getByText('API Reference')).toBeInTheDocument();
    expect(screen.getByText('API Keys')).toBeInTheDocument();
    expect(screen.getByText('Python SDK')).toBeInTheDocument();
    expect(screen.getByText('TypeScript SDK')).toBeInTheDocument();
    expect(screen.getByText('cURL')).toBeInTheDocument();
    expect(screen.getByText('Webhook Events')).toBeInTheDocument();
  });

  it('renders API endpoints by default on overview tab', () => {
    renderComponent();
    expect(screen.getByText('/api/v1/agents')).toBeInTheDocument();
    expect(screen.getByText('List all agents')).toBeInTheDocument();
  });

  it('switches to API Keys tab and loads keys', async () => {
    const user = userEvent.setup();
    renderComponent();

    const apiKeysTabBtn = screen.getByRole('button', { name: /api keys/i });
    await user.click(apiKeysTabBtn);

    await waitFor(() => {
      expect(apiKeysService.listKeys).toHaveBeenCalled();
    });

    expect(screen.getByText('Generate and manage API keys for programmatic access to the Agentium platform.')).toBeInTheDocument();
    expect(screen.getByText('key-uuid-1')).toBeInTheDocument();
    expect(screen.getByText('HEALTHY')).toBeInTheDocument();
  });

  it('opens create key form and submits new key', async () => {
    const user = userEvent.setup();
    vi.mocked(apiKeysService.createKey).mockResolvedValue({
      success: true,
      key_id: 'new-key-123',
      provider: 'OPENAI',
      config_name: 'Prod GPT-4',
      genesis_triggered: false,
      message: 'API key saved successfully.',
    });

    renderComponent();
    await user.click(screen.getByRole('button', { name: /api keys/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /generate new key/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /generate new key/i }));

    // Fill form
    await user.type(screen.getByPlaceholderText('e.g. Production GPT-4o'), 'Prod GPT-4');
    await user.type(screen.getByPlaceholderText('e.g. gpt-4o, claude-sonnet-4-20250514'), 'gpt-4o');
    await user.type(screen.getByPlaceholderText('sk-...'), 'sk-test-secret-key-1234');

    const submitBtn = screen.getByRole('button', { name: /create key/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(apiKeysService.createKey).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'OPENAI',
          config_name: 'Prod GPT-4',
          model_name: 'gpt-4o',
          api_key: 'sk-test-secret-key-1234',
        })
      );
    });
  });

  it('allows deleting an API key', async () => {
    const user = userEvent.setup();
    vi.mocked(apiKeysService.deleteKey).mockResolvedValue({
      success: true,
      message: 'Key deleted',
      key_id: 'key-uuid-1',
    });

    renderComponent();
    await user.click(screen.getByRole('button', { name: /api keys/i }));

    await waitFor(() => {
      expect(screen.getByTitle('Delete key')).toBeInTheDocument();
    });

    await user.click(screen.getByTitle('Delete key'));

    await waitFor(() => {
      expect(apiKeysService.deleteKey).toHaveBeenCalledWith('key-uuid-1', true);
    });
  });
});
