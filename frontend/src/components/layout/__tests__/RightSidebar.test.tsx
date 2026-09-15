import { render, screen, fireEvent } from '@testing-library/react';
import { RightSidebar } from '../RightSidebar';

describe('RightSidebar', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    children: <div data-testid="sidebar-content">Content</div>,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders children when open', () => {
    render(<RightSidebar {...defaultProps} />);
    expect(screen.getByTestId('sidebar-content')).toBeInTheDocument();
  });

  it('does not render children when closed (desktop)', () => {
    render(<RightSidebar {...defaultProps} isOpen={false} />);
    expect(screen.queryByTestId('sidebar-content')).not.toBeInTheDocument();
  });

  it('calls onClose when overlay clicked', () => {
    render(<RightSidebar {...defaultProps} />);
    fireEvent.click(screen.getByTestId('sidebar-overlay'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('applies correct width style', () => {
    render(<RightSidebar {...defaultProps} width={400} />);
    const sidebar = screen.getByTestId('sidebar-panel');
    expect(sidebar).toHaveStyle('width: 400px');
  });

  const mockMatchMedia = (matches: boolean) => {
    return vi.fn().mockImplementation(query => ({
      matches: query === '(max-width: 767px)' ? matches : false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    }));
  };

  it('switches to bottom sheet on mobile', () => {
    Object.defineProperty(window, 'matchMedia', { value: mockMatchMedia(true) });
    render(<RightSidebar {...defaultProps} position="bottom" />);
    const panel = screen.getByTestId('sidebar-panel');
    expect(panel.className).toContain('bottom');
  });

  it('renders drag handle on mobile bottom sheet', () => {
    Object.defineProperty(window, 'matchMedia', { value: mockMatchMedia(true) });
    render(<RightSidebar {...defaultProps} position="bottom" />);
    expect(screen.getByRole('button', { name: /drag to close/i })).toBeInTheDocument();
  });

  it('closes on swipe down on mobile', () => {
    const onClose = vi.fn();
    Object.defineProperty(window, 'matchMedia', { value: mockMatchMedia(true) });
    render(<RightSidebar {...defaultProps} onClose={onClose} position="bottom" />);
    const panel = screen.getByTestId('sidebar-panel');
    fireEvent.touchStart(panel, { touches: [{ clientY: 100 }] });
    fireEvent.touchMove(panel, { touches: [{ clientY: 250 }] });
    fireEvent.touchEnd(panel, { changedTouches: [{ clientY: 250 }] });
    expect(onClose).toHaveBeenCalled();
  });

  it('does not close on small swipe', () => {
    const onClose = vi.fn();
    Object.defineProperty(window, 'matchMedia', { value: mockMatchMedia(true) });
    render(<RightSidebar {...defaultProps} onClose={onClose} position="bottom" />);
    const panel = screen.getByTestId('sidebar-panel');
    fireEvent.touchStart(panel, { touches: [{ clientY: 100 }] });
    fireEvent.touchMove(panel, { touches: [{ clientY: 150 }] });
    fireEvent.touchEnd(panel, { changedTouches: [{ clientY: 150 }] });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('toggles collapse on handle click', () => {
    render(<RightSidebar {...defaultProps} />);
    const handle = screen.getByRole('button', { name: /Collapse sidebar/i });
    fireEvent.click(handle);
    expect(screen.getByRole('button', { name: /Expand sidebar/i })).toBeInTheDocument();
  });
});