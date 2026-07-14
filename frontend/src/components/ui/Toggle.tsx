// src/components/ui/Toggle.tsx
// Shared toggle/switch component extracted from MobilePage.
// Usable across any settings or preferences panel in the app.

/**
 * @description Shared toggle / switch component for settings or preferences panels.
 * Renders an accessible switch with a label and optional description.
 * @example
 * ```tsx
 * import { Toggle } from '@/components/ui/Toggle';
 *
 * <Toggle
 *   checked={enabled}
 *   onChange={setEnabled}
 *   label="Dark mode"
 *   description="Enable dark theme across the app"
 * />
 * ```
 * @param {boolean} props.checked - Whether the toggle is enabled.
 * @param {(value: boolean) => void} props.onChange - Callback fired when the toggle is toggled.
 * @param {string} props.label - Accessible label text for the switch.
 * @param {string} [props.description] - Optional description text shown below the label.
 * @param {boolean} [props.disabled] - Whether the toggle is disabled (default: false).
 */
interface ToggleProps {
    checked: boolean;
    onChange: (value: boolean) => void;
    label: string;
    description?: string;
    disabled?: boolean;
}

export function Toggle({ checked, onChange, label, description, disabled = false }: ToggleProps) {
    return (
        <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-[#0f1117] rounded-lg">
            <div>
                <p className={`text-sm font-medium ${disabled ? 'text-gray-600 dark:text-gray-600' : 'text-gray-900 dark:text-white'}`}>
                    {label}
                </p>
                {description && (
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">{description}</p>
                )}
            </div>
            <button
                type="button"
                role="switch"
                aria-checked={checked}
                aria-label={label}
                disabled={disabled}
                onClick={() => !disabled && onChange(!checked)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-[#161b27] ${
                    disabled
                        ? 'opacity-40 cursor-not-allowed bg-gray-200 dark:bg-[#2a3347]'
                        : checked
                        ? 'bg-emerald-600 cursor-pointer'
                        : 'bg-gray-200 dark:bg-[#2a3347] cursor-pointer'
                }`}
            >
                <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
                        checked ? 'translate-x-6' : 'translate-x-1'
                    }`}
                />
            </button>
        </div>
    );
}

export default Toggle;