import { render, screen, fireEvent } from '@testing-library/react';
import { vi, beforeEach } from 'vitest';
import { useState } from 'react';
import { CardQuestion } from './CardQuestion';
import { StructuredInputCard } from './StructuredInputCard';
import { useChatStore } from '../../store/chatStore';
import type { CardQuestion as Q } from '../../types/structuredInput';
import type { StructuredInputCardPayload } from '../../types/structuredInput';
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

const card: StructuredInputCardPayload = {
  card_id: 'card-1',
  questions: [
    { id: 'q1', question: 'Where?', input_type: 'single_select', required: true,
      options: [{ id: 'a', label: 'Tokyo', value: 'tokyo' }] },
    { id: 'q2', question: 'Budget?', input_type: 'multi_select', required: false,
      options: [{ id: 'x', label: 'Low', value: 'low' }] },
  ],
};

// The chat store is a module-level singleton; reset card lifecycle between tests
// so one test's "confirmed" status doesn't leak into another test.
beforeEach(() => {
  useChatStore.setState({ cardStatus: {}, activeCardId: null });
});

test('counter shows answered count', () => {
  render(<StructuredInputCard card={card} onSubmit={vi.fn()} />);
  expect(screen.getByText('0 of 2 answered')).toBeInTheDocument();
});

test('Confirm disabled until required answered', () => {
  render(<StructuredInputCard card={card} onSubmit={vi.fn()} />);
  const btn = screen.getByRole('button', { name: /confirm/i }) as HTMLButtonElement;
  expect(btn.disabled).toBe(true);
});

test('confirming collapses to summary', () => {
  const onSubmit = vi.fn();
  render(<StructuredInputCard card={card} onSubmit={onSubmit} />);
  fireEvent.click(screen.getByLabelText('Tokyo'));
  const btn = screen.getByRole('button', { name: /confirm/i }) as HTMLButtonElement;
  expect(btn.disabled).toBe(false);
  fireEvent.click(btn);
  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ card_id: 'card-1' }));
});

test('expired card disables inputs', () => {
  const past = new Date(Date.now() - 1000).toISOString();
  render(<StructuredInputCard card={{ ...card, expires_at: past }} onSubmit={vi.fn()} />);
  expect(screen.getByText(/expired/i)).toBeInTheDocument();
});
