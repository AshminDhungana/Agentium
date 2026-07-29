import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DragDropProvider, useDragDrop } from "@/context/DragDropContext";
import React from 'react';

// Error boundary to catch errors in tests
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error: Error | null }> {
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return <div data-testid="error-boundary">{this.state.error?.message}</div>;
    }
    return this.props.children;
  }
}

// Test component that uses the drag drop context
const TestComponent: React.FC<{ onDropCommit: (agent: any, parentId: string) => void }> = ({ onDropCommit, children }) => {
  return (
    <DragDropProvider onDropCommit={onDropCommit}>
      {children}
    </DragDropProvider>
  );
};

// Consumer component to test context values
const Consumer: React.FC = () => {
  const {
    draggingAgentId,
    dropTargetId,
    draggingAgent,
    onDragStart,
    onDragEnd,
    onDragEnter,
    onDragLeave,
    onDrop
  } = useDragDrop();

  return (
    <div data-testid="consumer">
      <span data-testid="dragging-id">{draggingAgentId || 'null'}</span>
      <span data-testid="drop-target-id">{dropTargetId || 'null'}</span>
      <span data-testid="dragging-agent">{draggingAgent?.agentium_id || 'null'}</span>
      <button data-testid="btn-drag-start" onClick={() => onDragStart({ agentium_id: 'agent-1', name: 'Test Agent' } as any)}>Drag Start</button>
      <button data-testid="btn-drag-end" onClick={onDragEnd}>Drag End</button>
      <button data-testid="btn-drag-enter" onClick={() => onDragEnter('target-1')}>Drag Enter</button>
      <button data-testid="btn-drag-leave" onClick={() => onDragLeave('target-1')}>Drag Leave</button>
      <button data-testid="btn-drop" onClick={() => onDrop('target-1')}>Drop</button>
    </div>
  );
};

describe('DragDropContext', () => {
  const mockOnDropCommit = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderWithProvider = () => {
    return render(
      <TestComponent onDropCommit={mockOnDropCommit}>
        <Consumer />
      </TestComponent>
    );
  };

  it('provides initial state with null values', () => {
    renderWithProvider();
    expect(screen.getByTestId('dragging-id').textContent).toBe('null');
    expect(screen.getByTestId('drop-target-id').textContent).toBe('null');
    expect(screen.getByTestId('dragging-agent').textContent).toBe('null');
  });

  it('sets dragging agent on drag start', () => {
    renderWithProvider();
    fireEvent.click(screen.getByTestId('btn-drag-start'));
    expect(screen.getByTestId('dragging-id').textContent).toBe('agent-1');
    expect(screen.getByTestId('dragging-agent').textContent).toBe('agent-1');
  });

  it('clears state on drag end', () => {
    renderWithProvider();
    fireEvent.click(screen.getByTestId('btn-drag-start'));
    fireEvent.click(screen.getByTestId('btn-drag-end'));
    expect(screen.getByTestId('dragging-id').textContent).toBe('null');
    expect(screen.getByTestId('drop-target-id').textContent).toBe('null');
    expect(screen.getByTestId('dragging-agent').textContent).toBe('null');
  });

  it('sets drop target on drag enter', () => {
    renderWithProvider();
    fireEvent.click(screen.getByTestId('btn-drag-start'));
    fireEvent.click(screen.getByTestId('btn-drag-enter'));
    expect(screen.getByTestId('drop-target-id').textContent).toBe('target-1');
  });

  it('clears drop target on drag leave', () => {
    renderWithProvider();
    fireEvent.click(screen.getByTestId('btn-drag-start'));
    fireEvent.click(screen.getByTestId('btn-drag-enter'));
    fireEvent.click(screen.getByTestId('btn-drag-leave'));
    expect(screen.getByTestId('drop-target-id').textContent).toBe('null');
  });

  it('calls onDropCommit on drop with valid agent', () => {
    renderWithProvider();
    fireEvent.click(screen.getByTestId('btn-drag-start'));
    fireEvent.click(screen.getByTestId('btn-drop'));

    expect(mockOnDropCommit).toHaveBeenCalledTimes(1);
    expect(mockOnDropCommit).toHaveBeenCalledWith(
      expect.objectContaining({ agentium_id: 'agent-1' }),
      'target-1'
    );
  });

  it('does not call onDropCommit if same agent is dropped on itself', () => {
    const ConsumerSelf: React.FC = () => {
      const { onDragStart, onDrop } = useDragDrop();
      return (
        <div>
          <button data-testid="btn-drag-start" onClick={() => onDragStart({ agentium_id: 'agent-1', name: 'Test' } as any)}>Drag Start</button>
          <button data-testid="btn-drop" onClick={() => onDrop('agent-1')}>Drop</button>
        </div>
      );
    };

    render(
      <TestComponent onDropCommit={mockOnDropCommit}>
        <ConsumerSelf />
      </TestComponent>
    );

    fireEvent.click(screen.getByTestId('btn-drag-start'));
    fireEvent.click(screen.getByTestId('btn-drop'));

    expect(mockOnDropCommit).not.toHaveBeenCalled();
  });

  it('does not call onDropCommit if no agent is dragging', () => {
    renderWithProvider();
    fireEvent.click(screen.getByTestId('btn-drop'));
    expect(mockOnDropCommit).not.toHaveBeenCalled();
  });

  it('handles nested drag enter/leave with counter', () => {
    renderWithProvider();
    fireEvent.click(screen.getByTestId('btn-drag-start'));
    fireEvent.click(screen.getByTestId('btn-drag-enter'));
    fireEvent.click(screen.getByTestId('btn-drag-enter')); // nested enter
    fireEvent.click(screen.getByTestId('btn-drag-leave'));
    expect(screen.getByTestId('drop-target-id').textContent).toBe('target-1'); // still set
    fireEvent.click(screen.getByTestId('btn-drag-leave'));
    expect(screen.getByTestId('drop-target-id').textContent).toBe('null'); // now cleared
  });

  it('throws error when used outside provider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    const BadConsumer: React.FC = () => {
      useDragDrop();
      return <div />;
    };

    // The hook throws an error when used outside provider during render
    // Expect the render to throw
    expect(() => {
      render(<BadConsumer />);
    }).toThrow('useDragDrop must be used within a DragDropProvider');

    consoleError.mockRestore();
  });
});