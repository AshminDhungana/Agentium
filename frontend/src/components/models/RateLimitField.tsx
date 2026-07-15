interface RateLimitFieldProps {
    value: number;
    onChange: (v: number) => void;
}

/**
 * Requests-per-minute input with a live per-second helper.
 *
 * The stored/displayed unit is always requests/minute (whole integer). The
 * per-second line is read-only, computed client-side (value / 60), and exists
 * purely so the user can sanity-check against how their provider documents
 * its limit. It is never sent to the backend.
 */
export function RateLimitField({ value, onChange }: RateLimitFieldProps) {
    const safe = Number.isFinite(value) && value > 0 ? value : 0;
    const perSecond = safe / 60;
    let perSecondText = '';
    if (perSecond >= 1) {
        // Whole or one-decimal rate, but never show a trailing ".0" (e.g. 60/min → "≈ 1", 120/min → "≈ 2").
        perSecondText = Number.isInteger(perSecond) ? String(perSecond) : perSecond.toFixed(1);
    } else {
        // Sub-1 rates: up to two decimals, trimmed of trailing zeros (e.g. 30/min → "≈ 0.5").
        perSecondText = perSecond.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
    }
    const perSecondLabel = perSecond > 0 ? `≈ ${perSecondText} requests/second` : '';

    return (
        <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Rate limit (requests per minute)
            </label>
            <input
                type="number"
                min={1}
                value={value ?? 60}
                onChange={(e) => onChange(parseInt(e.target.value, 10) || 60)}
                className="mt-1 block w-full px-4 py-2.5 text-sm rounded-lg border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                check your provider's plan page — e.g. 1 request every 2 seconds = 30/min.
            </p>
            {perSecondLabel && (
                <p className="mt-1 text-xs text-indigo-500 dark:text-indigo-400">{perSecondLabel}</p>
            )}
        </div>
    );
}

export default RateLimitField;
