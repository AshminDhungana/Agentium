import type { CardQuestion as Q, CardInputType } from '../../types/structuredInput';

export interface QuestionValue { selectedIds: string[]; otherText: string | null; }

interface Props {
  q: Q;
  value: QuestionValue;
  onChange: (next: QuestionValue) => void;
  disabled?: boolean;
}

const OTHER_ID = '__other__';
const OPTION_ROW =
  'flex items-center gap-3 w-full px-3.5 py-2.5 rounded-xl border text-sm transition-colors cursor-pointer min-h-[44px] focus-within:ring-2 focus-within:ring-indigo-500';

export function CardQuestion({ q, value, onChange, disabled }: Props) {
  const isMulti = q.input_type === 'multi_select';
  const otherChecked = value.otherText !== null;

  const toggle = (optId: string) => {
    if (isMulti) {
      const set = new Set(value.selectedIds);
      set.has(optId) ? set.delete(optId) : set.add(optId);
      onChange({ selectedIds: [...set], otherText: value.otherText });
    } else {
      onChange({ selectedIds: [optId], otherText: null });
    }
  };

  const setOther = (text: string) =>
    onChange({ selectedIds: value.selectedIds, otherText: text === '' ? null : text });

  const Wrapper = isMulti ? 'group' : 'radiogroup';
  return (
    <fieldset
      role={Wrapper}
      aria-labelledby={`q-${q.id}-label`}
      className="border-t border-[#1e2535] first:border-t-0 pt-4 first:pt-0"
      disabled={disabled}
    >
      <legend id={`q-${q.id}-label`} className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-2">
        {q.question}
        {q.required && <span className="text-rose-500 ml-1" aria-hidden="true">*</span>}
      </legend>

      {q.options.map((opt) => {
        const checked = value.selectedIds.includes(opt.id);
        return (
          <label key={opt.id}
                 className={`${OPTION_ROW} ${checked
                   ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300'
                   : 'border-slate-200 dark:border-[#1e2535] text-slate-600 dark:text-slate-400 hover:border-indigo-300 dark:hover:border-indigo-500/50'}`}>
            <input type={isMulti ? 'checkbox' : 'radio'} name={q.id} value={opt.id}
                   checked={checked} onChange={() => toggle(opt.id)}
                   className="sr-only" />
            <span className="flex-1">{opt.label}</span>
          </label>
        );
      })}

      {/* implicit "Other / Type your own" */}
      <label className={`${OPTION_ROW} ${otherChecked
        ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300'
        : 'border-slate-200 dark:border-[#1e2535] text-slate-600 dark:text-slate-400 hover:border-indigo-300 dark:hover:border-indigo-500/50'}`}>
        <input type={isMulti ? 'checkbox' : 'radio'} name={q.id} value={OTHER_ID}
               checked={otherChecked} onChange={() => setOther(otherChecked ? '' : ' ')}
               className="sr-only" />
        <span className="flex-1">Other / Type your own</span>
      </label>
      {otherChecked && (
        <input type="text" aria-label={`Other answer for ${q.question}`}
               placeholder="Type your own…"
               value={value.otherText ?? ''}
               onChange={(e) => setOther(e.target.value)}
               className="mt-2 w-full px-3.5 py-2.5 text-sm bg-slate-50 dark:bg-[#0f1117] border border-slate-200 dark:border-[#1e2535] rounded-xl text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
      )}
    </fieldset>
  );
}
