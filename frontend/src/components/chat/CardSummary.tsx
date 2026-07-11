import type { StructuredInputCardPayload } from '../../types/structuredInput';
import type { QuestionValue } from './CardQuestion';

function answerText(q: StructuredInputCardPayload['questions'][number], v: QuestionValue): string {
  const labels = v.selectedIds.map((id) => q.options.find((o) => o.id === id)?.label ?? id);
  if (v.otherText && v.otherText.trim() !== '') labels.push(v.otherText);
  return labels.length ? labels.join(', ') : '—';
}

export function CardSummary({ card, values, dismissed }: {
  card: StructuredInputCardPayload; values: Record<string, QuestionValue>; dismissed?: boolean;
}) {
  return (
    <div className="my-2 rounded-xl border border-[#1e2535] bg-[#161b27]/60 p-4" role="status" aria-live="polite">
      <p className="text-xs font-medium text-slate-400 mb-2">
        {dismissed ? 'Answered in chat' : 'Your answers'}
      </p>
      <dl className="space-y-1.5">
        {card.questions.map((q) => (
          <div key={q.id} className="flex flex-col">
            <dt className="text-sm text-slate-400">{q.question}</dt>
            <dd className="text-sm text-slate-200">{answerText(q, values[q.id])}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
