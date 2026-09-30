import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

vi.mock('@/hooks/useToast', () => ({
  showToast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

// Mock the CitationGraph component since it has its own dependencies
vi.mock('@/components/knowledge/CitationGraph', () => ({
  CitationGraph: () => <div data-testid="citation-graph">Citation Graph Mock</div>,
}));

vi.mock('@/services/skills', () => ({
  skillsApi: {
    search: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    deprecate: vi.fn(),
    getPopular: vi.fn(),
    get: vi.fn(),
    getFull: vi.fn(),
    execute: vi.fn(),
    getPendingSubmissions: vi.fn(),
    reviewSubmission: vi.fn(),
  },
}));

import { SkillsPage } from '@/pages/SkillsPage';
import { skillsApi } from '@/services/skills';
import { useAuthStore } from '@/store/authStore';
import { showToast } from '@/hooks/useToast';

// ── Test Data ─────────────────────────────────────────────────────────────────

const ADMIN_USER = {
  id: 'usr-uuid-1',
  username: 'sovereign',
  is_admin: true,
  isAuthenticated: true,
  isSovereign: true,
  role: 'primary_sovereign' as const,
};

const MOCK_POPULAR_SKILL = {
  skill_id: 'skill_0xxxx_001',
  skill_name: 'react_form_validation',
  display_name: 'React Form Validation',
  skill_type: 'code_generation',
  domain: 'frontend',
  tags: ['react', 'forms'],
  complexity: 'intermediate',
  description: 'Validate forms in React using Zod.',
  success_rate: 0.92,
  usage_count: 45,
  verification_status: 'verified',
  creator_id: '00001',
  created_at: '2026-09-01T12:00:00Z',
};

const MOCK_SEARCH_RESULT = {
  skill_id: 'skill_0xxxx_001',
  relevance_score: 0.87,
  metadata: MOCK_POPULAR_SKILL,
  content_preview: 'Step 1: Install zod\nStep 2: Define schema\n...',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderSkillsPage() {
  useAuthStore.setState({
    user: ADMIN_USER,
    isLoading: false,
    error: null,
  } as any);

  return render(
    <MemoryRouter>
      <SkillsPage />
    </MemoryRouter>,
  );
}

// ── 12.6.1 — SkillsPage lists agent skills ────────────────────────────────────

describe('12.6.1 — SkillsPage lists agent skills', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(skillsApi.getPopular).mockResolvedValue([MOCK_POPULAR_SKILL]);
    vi.mocked(skillsApi.search).mockResolvedValue([MOCK_SEARCH_RESULT]);
  });

  it('renders the Knowledge Library header and all tabs', () => {
    renderSkillsPage();
    expect(screen.getByText('Knowledge Library')).toBeInTheDocument();
    expect(screen.getByText('Browse')).toBeInTheDocument();
    expect(screen.getByText('My Submissions')).toBeInTheDocument();
    expect(screen.getByText('Citation Graph')).toBeInTheDocument();
  });

  it('renders the search bar and Add Skill button', () => {
    renderSkillsPage();
    expect(screen.getByPlaceholderText(/search skills/i)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /add skill/i })[0]).toBeInTheDocument();
  });

  it('loads and displays popular skills on mount', async () => {
    renderSkillsPage();

    await waitFor(() => {
      expect(skillsApi.getPopular).toHaveBeenCalledWith(undefined, 9);
    });

    expect(screen.getByText('React Form Validation')).toBeInTheDocument();
    expect(screen.getByText('92%')).toBeInTheDocument();
    expect(screen.getByText('45 uses')).toBeInTheDocument();
  });

  it('shows empty state when no popular skills exist', async () => {
    vi.mocked(skillsApi.getPopular).mockResolvedValue([]);
    renderSkillsPage();

    await waitFor(() => {
      expect(screen.getByText('No skills available')).toBeInTheDocument();
    });
  });
});

// ── 12.6.2 — Skill creation/editing UI works ──────────────────────────────────

describe('12.6.2 — Skill creation/editing UI works', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(skillsApi.getPopular).mockResolvedValue([MOCK_POPULAR_SKILL]);
    vi.mocked(skillsApi.search).mockResolvedValue([MOCK_SEARCH_RESULT]);
    vi.mocked(skillsApi.create).mockResolvedValue({ skill_id: 'skill_new_001' });
    vi.mocked(skillsApi.update).mockResolvedValue(MOCK_POPULAR_SKILL);
    vi.mocked(skillsApi.deprecate).mockResolvedValue(undefined);
  });

  it('opens create modal with all required fields', async () => {
    const user = userEvent.setup();
    renderSkillsPage();

    const addButtons = screen.getAllByRole('button', { name: /add skill/i });
    await user.click(addButtons[0]);

    // Modal opens
    expect(screen.getByText('Create New Skill')).toBeInTheDocument();
    expect(screen.getByText('Display Name *')).toBeInTheDocument();
    expect(screen.getByText('Skill Type *')).toBeInTheDocument();
    expect(screen.getByText('Domain *')).toBeInTheDocument();
    expect(screen.getByText('Complexity *')).toBeInTheDocument();
    expect(screen.getByText('Description *')).toBeInTheDocument();
    expect(screen.getByText('Steps *')).toBeInTheDocument();
  });

  it('submits a new skill via create', async () => {
    const user = userEvent.setup();
    renderSkillsPage();

    const addButtons = screen.getAllByRole('button', { name: /add skill/i });
    await user.click(addButtons[0]);

    // Fill required fields
    await user.type(
      screen.getByPlaceholderText('e.g., React Form Validation with Zod'),
      'Test Skill Name',
    );
    await user.type(
      screen.getByPlaceholderText(/describe what this skill does/i),
      'A test skill description.',
    );
    await user.type(screen.getByPlaceholderText('Step 1...'), 'Do the first thing');

    // Submit — council/head users get "Create & Verify"
    const submitBtn = screen.getByText('Create & Verify');
    await user.click(submitBtn);

    await waitFor(() => {
      expect(skillsApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          display_name: 'Test Skill Name',
          description: 'A test skill description.',
        }),
        true, // canAutoVerify = true for admin user
      );
    });

    expect(showToast.success).toHaveBeenCalled();
  });

  it('opens delete confirmation and deletes skill', async () => {
    const user = userEvent.setup();
    renderSkillsPage();

    // Search to get a result with delete button
    await user.type(screen.getByPlaceholderText(/search skills/i), 'react');
    await user.click(screen.getByRole('button', { name: /^search$/i }));

    await waitFor(() => {
      expect(screen.getByText('87% match')).toBeInTheDocument();
    });

    // Click delete on the skill card
    const deleteBtn = screen.getByRole('button', { name: /delete skill/i });
    await user.click(deleteBtn);

    // Confirmation modal
    expect(screen.getByText('Delete Skill?')).toBeInTheDocument();

    // Confirm delete
    await user.click(screen.getByText('Delete Skill'));

    await waitFor(() => {
      expect(skillsApi.deprecate).toHaveBeenCalledWith('skill_0xxxx_001', 'Deleted by user');
    });

    expect(showToast.success).toHaveBeenCalledWith('Skill deleted.');
  });
});

// ── 12.6.3 — Skill RAG search works ──────────────────────────────────────────

describe('12.6.3 — Skill RAG search works', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(skillsApi.getPopular).mockResolvedValue([]);
    vi.mocked(skillsApi.search).mockResolvedValue([MOCK_SEARCH_RESULT]);
  });

  it('searches skills and displays results with relevance scores', async () => {
    const user = userEvent.setup();
    renderSkillsPage();

    // Type a query
    const searchInput = screen.getByPlaceholderText(/search skills/i);
    await user.type(searchInput, 'react form');

    // Click search
    await user.click(screen.getByRole('button', { name: /^search$/i }));

    await waitFor(() => {
      expect(skillsApi.search).toHaveBeenCalledWith('react form');
    });

    // Results show
    expect(screen.getByText('Search Results')).toBeInTheDocument();
    expect(screen.getByText('87% match')).toBeInTheDocument();
    expect(screen.getByText('React Form Validation')).toBeInTheDocument();
    expect(screen.getByText('frontend')).toBeInTheDocument();
    expect(screen.getByText('code_generation')).toBeInTheDocument();
    expect(screen.getByText('intermediate')).toBeInTheDocument();
  });

  it('clears search results', async () => {
    const user = userEvent.setup();
    renderSkillsPage();

    await user.type(screen.getByPlaceholderText(/search skills/i), 'test');
    await user.click(screen.getByRole('button', { name: /^search$/i }));

    await waitFor(() => {
      expect(screen.getByText('Search Results')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Clear'));

    expect(screen.queryByText('Search Results')).not.toBeInTheDocument();
  });

  it('switches to My Submissions tab', async () => {
    const user = userEvent.setup();
    renderSkillsPage();

    await user.click(screen.getByText('My Submissions'));

    await waitFor(() => {
      expect(screen.getByText('Your Skill Submissions')).toBeInTheDocument();
    });
  });
});
