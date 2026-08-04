import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SearchableModelSelect } from '../ModelConfigForm';

describe('SearchableModelSelect auto-scroll', () => {
  const models = Array.from({ length: 30 }, (_, i) => `model-${i + 1}`);

  it('renders and handles keyboard navigation', async () => {
    const onChange = vi.fn();
    render(<SearchableModelSelect models={models} value="model-1" onChange={onChange} inputCls="" />);

    const input = screen.getByRole('combobox');

    // Focus first to trigger the onFocus handler which opens dropdown and sets query to ''
    fireEvent.focus(input);

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    // First press moves highlight from model-1 to model-2
    fireEvent.keyDown(input, { key: 'ArrowDown' });

    await waitFor(() => {
      const highlightedItem = screen.getByRole('option', { name: 'model-2' });
      expect(highlightedItem).toBeInTheDocument();
      // The highlighted item gets the highlight style (blue background)
      expect(highlightedItem).toHaveClass('bg-blue-50');
    });

    // Scroll down to model-15
    for (let i = 0; i < 13; i++) {
      fireEvent.keyDown(input, { key: 'ArrowDown' });
      await waitFor(() => {}, { timeout: 100 });
    }

    const farItem = screen.getByRole('option', { name: 'model-15' });
    expect(farItem).toBeInTheDocument();
    expect(farItem).toHaveClass('bg-blue-50');
  });

  it('handles ArrowUp navigation', async () => {
    const onChange = vi.fn();
    // Start with a simpler test - use model-5 as initial value so we know the starting point
    render(<SearchableModelSelect models={models} value="model-5" onChange={onChange} inputCls="" />);

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    // Navigate up from model-5 (index 4) to model-1 (index 0) - 4 ArrowUp presses
    for (let i = 0; i < 4; i++) {
      fireEvent.keyDown(input, { key: 'ArrowUp' });
      await waitFor(() => {}, { timeout: 100 });
    }

    const upItem = screen.getByRole('option', { name: 'model-1' });
    expect(upItem).toBeInTheDocument();
    expect(upItem).toHaveClass('bg-blue-50');
  });

  it('handles mouse hover highlighting', async () => {
    const onChange = vi.fn();
    render(<SearchableModelSelect models={models} value="model-1" onChange={onChange} inputCls="" />);

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    // Hover over model-5
    const item5 = screen.getByRole('option', { name: 'model-5' });
    fireEvent.mouseEnter(item5);

    await waitFor(() => {
      expect(item5).toHaveClass('bg-blue-50');
    });
  });
});