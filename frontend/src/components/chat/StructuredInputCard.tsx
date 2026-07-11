import { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import type { StructuredInputCardPayload, StructuredInputAnswer, CardAnswerQuestion } from '../../types/structuredInput';
import { useChatStore } from '../../store/chatStore';
import { CardQuestion, type QuestionValue } from './CardQuestion';
import { CardSummary } from './CardSummary';

const CONTAINER =
  'my-2 max-w-full rounded-xl border border-[#1e2535] bg-[#161b27] p-4 shadow-sm transition-all duration-200 motion-reduce:transition-none';
const CONFIRM_BTN =
  'flex items-center gap-2 px-5 py-2 bg-indigo-600 dark:bg-indigo-500 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 dark:hover:bg-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-md shadow-indigo-500/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[#161b27]';

function isAnswered(q: StructuredInputCardPayload['questions'][number], v: QuestionValue): boolean {
  if (v.otherText && v.otherText.trim() !== '') return true;
  return v.selectedIds.length > 0;
}

export function StructuredInputCard({ card, onSubmit }: { card: StructuredInputCardPayload; onSubmit: (a: StructuredInputAnswer) => void }) {
  const status = useChatStore((s) => s.cardStatus[card.card_id]);
  const confirmCard = useChatStore((s) => s.confirmCard);
  const expireCard = useChatStore((s) => s.expireCard);

  const [values, setValues] = useState<Record<string, QuestionValue>>(
    () => Object.fromEntries(card.questions.map((q) => [q.id, { selectedIds: [], otherText: null }]))
  );

  // expiration → expired state
  useEffect(() => {
    if (!card.expires_at) return;
    const ms = new Date(card.expires_at).getTime() - Date.now();
    if (ms <= 0) { expireCard(card.card_id); return; }
    const t = setTimeout(() => expireCard(card.card_id), ms);
    return () => clearTimeout(t);
  }, [card.expires_at, card.card_id, expireCard]);

  if (status === 'confirmed' || status === 'dismissed') {
    return <CardSummary card={card} values={values} dismissed={status === 'dismissed'} />;
  }
  if (status === 'expired') {
    return (
      <div className={CONTAINER} aria-disabled="true">
        <p className="text-sm text-slate-400">This question expired and can no longer be answered.</p>
      </div>
    );
  }

  const answeredCount = card.questions.filter((q) => isAnswered(q, values[q.id])).length;
  const allRequiredAnswered = card.questions.filter((q) => q.required).every((q) => isAnswered(q, values[q.id]));
  const canConfirm = allRequiredAnswered;

  const buildAnswer = (): StructuredInputAnswer => ({
    card_id: card.card_id,
    card_group_id: card.card_group_id ?? null,
    answers: card.questions.map<CardAnswerQuestion>((q) => ({
      question_id: q.id,
      selected_option_ids: values[q.id].selectedIds,
      other_text: values[q.id].otherText,
    })),
  });

  const handleConfirm = () => {
    if (!canConfirm) return;
    onSubmit(buildAnswer());
    confirmCard(card.card_id);
  };

  return (
    <div className={CONTAINER} role="group" aria-label={card.title ?? 'Question card'}>
      <div className="flex items-center justify-between mb-3" aria-live="polite">
        <span className="text-xs font-medium text-slate-400">{answeredCount} of {card.questions.length} answered</span>
        {card.title && <span className="text-sm font-semibold text-slate-200">{card.title}</span>}
      </div>
      {card.questions.map((q) => (
        <CardQuestion key={q.id} q={q} value={values[q.id]}
                      onChange={(v) => setValues((prev) => ({ ...prev, [q.id]: v }))} />
      ))}
      <div className="mt-4 flex items-center gap-2">
        <button type="button" className={CONFIRM_BTN} disabled={!canConfirm} onClick={handleConfirm}>
          <Check size={16} /> Confirm
        </button>
      </div>
    </div>
  );
}
