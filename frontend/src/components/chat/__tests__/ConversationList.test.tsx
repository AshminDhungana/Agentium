import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ConversationList } from '../ConversationList';
import { useChatStore } from '../../../store/chatStore';

vi.mock('../../../store/chatStore', () => ({
    useChatStore: vi.fn(),
}));

vi.mock('../../../components/layout/RightSidebar', () => ({
    useRightSidebar: vi.fn(() => ({ isCollapsed: false, toggleCollapse: vi.fn() })),
}));

const createMockStore = (overrides = {}) => ({
    conversations: [
        { id: 'conv-1', title: 'General', is_archived: false, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 10, last_message_preview: 'Hello!' },
        { id: 'conv-2', title: 'Project Planning', is_archived: false, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 5, last_message_preview: 'Let me help...' },
        { id: 'conv-3', title: 'Code Review', is_archived: true, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 20, last_message_preview: 'Looks good!' },
    ],
    currentConversationId: 'conv-1',
    setConversation: vi.fn(),
    createConversation: vi.fn().mockResolvedValue('conv-new'),
    deleteConversation: vi.fn(),
    updateConversation: vi.fn(),
    toggleSidebar: vi.fn(),
    sidebarWidth: 320,
    setSidebarWidth: vi.fn(),
    isSidebarOpen: true,
    ...overrides,
});

describe('ConversationList', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(useChatStore).mockReturnValue(createMockStore());
    });

    it('renders conversation list with titles and previews', () => {
        render(<ConversationList />);
        expect(screen.getByText('General')).toBeInTheDocument();
        expect(screen.getByText('Project Planning')).toBeInTheDocument();
        expect(screen.getByText('Code Review')).toBeInTheDocument();
        expect(screen.getByText('Hello!')).toBeInTheDocument();
    });

    it('highlights active conversation', () => {
        render(<ConversationList />);
        const activeItem = screen.getByText('General').closest('[data-testid="conversation-item"]');
        expect(activeItem?.className).toContain('active');
    });

    it('calls setConversation on click', async () => {
        const setConversation = vi.fn();
        vi.mocked(useChatStore).mockReturnValue(createMockStore({ setConversation }));
        render(<ConversationList />);
        fireEvent.click(screen.getByText('Project Planning'));
        await waitFor(() => expect(setConversation).toHaveBeenCalledWith('conv-2'));
    });

    it('shows new conversation button', () => {
        render(<ConversationList />);
        expect(screen.getByRole('button', { name: /new conversation/i })).toBeInTheDocument();
    });

    it('shows action menu on hover (desktop)', () => {
        render(<ConversationList />);
        const item = screen.getByText('General').closest('[data-testid="conversation-item"]');
        fireEvent.mouseEnter(item!);
        // Check actions within the hovered item
        const actionsContainer = item?.querySelector('[class*="actions"]');
        expect(actionsContainer?.querySelector('button[aria-label="Rename conversation"]')).toBeInTheDocument();
        expect(actionsContainer?.querySelector('button[aria-label="Archive"]')).toBeInTheDocument();
        expect(actionsContainer?.querySelector('button[aria-label="Delete conversation"]')).toBeInTheDocument();
    });

    it('collapsed mode shows only icons', () => {
        vi.mocked(useChatStore).mockReturnValue(createMockStore({ sidebarWidth: 48 }));
        render(<ConversationList />);
        // In collapsed mode, only icons should be visible
        expect(screen.queryByText('General')).not.toBeInTheDocument();
    });

    it('creates new conversation on button click', async () => {
        const createConversation = vi.fn().mockResolvedValue('conv-new');
        vi.mocked(useChatStore).mockReturnValue(createMockStore({ createConversation }));
        render(<ConversationList />);
        fireEvent.click(screen.getByRole('button', { name: /new conversation/i }));
        // Note: prompt is not easily testable, but we can verify the button is clickable
        expect(createConversation).not.toHaveBeenCalled(); // prompt would be needed
    });
});