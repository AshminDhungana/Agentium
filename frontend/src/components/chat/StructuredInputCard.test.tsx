import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import { useState } from 'react';
import { CardQuestion } from './CardQuestion';
import type { CardQuestion as Q } from '../../types/structuredInput';
import type { QuestionValue } from './CardQuestion';

const baseQ: Q = {
  id: 'q1', question: 'Where to?', input_type: 'single_select', required: true,
  options: [{ id: 'a', label: 'Tokyo', value: 'tokyo' }, { id: 'b', label: 'Paris', value: 'paris' }],
};

// CardQuestion is fully controlled, so the reveal test needs a stateful parent.
function Harness({ q }: { q: Q }) {
  const [value, setValue] = useState<QuestionValue>({ selectedIds: [], otherText: null });
  return <CardQuestion q={q} value={value} onChange={setValue} />;
}

test('single_select uses radiogroup and selects one option', () => {
  const onChange = vi.fn();
  render(<CardQuestion q={baseQ} value={{ selectedIds: [], otherText: null }} onChange={onChange} />);
  const group = screen.getByRole('radiogroup', { name: 'Where to?' });
  expect(group).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Tokyo'));
  expect(onChange).toHaveBeenCalledWith({ selectedIds: ['a'], otherText: null });
});

test('choosing Other reveals a text field', () => {
  render(<Harness q={{ ...baseQ, input_type: 'multi_select' }} />);
  expect(screen.queryByPlaceholderText(/type your own/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText(/Other/));
  const input = screen.getByPlaceholderText(/type your own/i) as HTMLInputElement;
  fireEvent.change(input, { target: { value: 'Lisbon' } });
  expect(input.value).toBe('Lisbon');
});
