import { render, screen, fireEvent } from '@testing-library/react';
import { ConversationSidebar } from '../ConversationSidebar';
import { useChatStore } from '../../../store/chatStore';

vi.mock('../../../store/chatStore', () => ({
    useChatStore: vi.fn(),
}));

vi.mock('../../../components/layout/RightSidebar', () => ({
    useRightSidebar: vi.fn(() => ({ isCollapsed: false, toggleCollapse: vi.fn() })),
}));

const mockStore = {
    conversations: [],
    currentConversationId: null,
    setConversation: vi.fn(),
    createConversation: vi.fn(),
    deleteConversation: vi.fn(),
    updateConversation: vi.fn(),
    toggleSidebar: vi.fn(),
    sidebarWidth: 320,
    setSidebarWidth: vi.fn(),
    isSidebarOpen: true,
};

describe('ConversationSidebar', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(useChatStore).mockReturnValue(mockStore);
    });

    it('renders ConversationList inside', () => {
        render(<ConversationSidebar />);
        expect(screen.getByRole('button', { name: /new conversation/i })).toBeInTheDocument();
    });

    it('shows collapse button with correct label', () => {
        render(<ConversationSidebar />);
        expect(screen.getByRole('button', { name: /collapse sidebar/i })).toBeInTheDocument();
    });
});