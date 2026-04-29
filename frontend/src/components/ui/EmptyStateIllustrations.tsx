// ─── Empty State Illustrations ────────────────────────────────────────────────
// Production-grade inline SVG illustrations for contextual empty states.
// Each illustration is 120×100 viewport, using:
//   • SVG <filter> for glow/depth effects (theme-agnostic)
//   • Tailwind className dark: variants for color switching
//   • <animateTransform> / <animateMotion> for smooth, purposeful motion
// ──────────────────────────────────────────────────────────────────────────────

import React from 'react';

// ── Agents: Neural Constellation ─────────────────────────────────────────────
// Three nodes in a triangle — center "head" pulses, signal dots travel the arms.

export const AgentsIllustration: React.FC<{ className?: string }> = ({ className }) => (
    <svg viewBox="0 0 120 100" fill="none" xmlns="http://www.w3.org/2000/svg"
        className={className} aria-hidden="true">
        <defs>
            {/* Soft halo behind glowing elements */}
            <filter id="ag-glow" x="-80%" y="-80%" width="260%" height="260%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                </feMerge>
            </filter>
            <filter id="ag-soft" x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur stdDeviation="1.5" result="blur" />
                <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                </feMerge>
            </filter>
        </defs>

        {/* Ambient radial halo behind center node */}
        <circle cx="60" cy="38" r="26" className="fill-blue-400/8 dark:fill-blue-400/12" />

        {/* Outer orbit ellipse */}
        <ellipse cx="60" cy="57" rx="53" ry="35" strokeWidth="0.75" strokeDasharray="4 3.5"
            className="stroke-slate-200 dark:stroke-slate-700/50" />

        {/* Connection arms */}
        <line x1="60" y1="38" x2="28" y2="76"
            strokeWidth="1.5" strokeLinecap="round"
            className="stroke-slate-200 dark:stroke-slate-600/70" />
        <line x1="60" y1="38" x2="92" y2="76"
            strokeWidth="1.5" strokeLinecap="round"
            className="stroke-slate-200 dark:stroke-slate-600/70" />
        <line x1="28" y1="76" x2="92" y2="76"
            strokeWidth="1.5" strokeLinecap="round"
            className="stroke-slate-200 dark:stroke-slate-600/70" />

        {/* Traveling signal — left arm (top→bottom) */}
        <circle r="2.2" className="fill-blue-400 dark:fill-blue-400">
            <animateMotion dur="2s" repeatCount="indefinite" path="M60,38 L28,76" />
            <animate attributeName="opacity" values="0;1;0" dur="2s" repeatCount="indefinite" />
        </circle>
        {/* Traveling signal — bottom (left→right) */}
        <circle r="2" className="fill-emerald-400 dark:fill-emerald-400">
            <animateMotion dur="2.4s" begin="1.2s" repeatCount="indefinite" path="M28,76 L92,76" />
            <animate attributeName="opacity" values="0;1;0" dur="2.4s" begin="1.2s" repeatCount="indefinite" />
        </circle>
        {/* Traveling signal — right arm (bottom→top) */}
        <circle r="2" className="fill-violet-400 dark:fill-violet-400">
            <animateMotion dur="2s" begin="0.7s" repeatCount="indefinite" path="M92,76 L60,38" />
            <animate attributeName="opacity" values="0;1;0" dur="2s" begin="0.7s" repeatCount="indefinite" />
        </circle>

        {/* ── Head (center) node ── */}
        {/* Expanding pulse ring */}
        <circle cx="60" cy="38" r="14" fill="none" strokeWidth="0.5"
            className="stroke-blue-400/50 dark:stroke-blue-400/40">
            <animate attributeName="r" values="13;19;13" dur="2.6s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.6;0;0.6" dur="2.6s" repeatCount="indefinite" />
        </circle>
        {/* Node body */}
        <circle cx="60" cy="38" r="12" strokeWidth="1.5"
            className="fill-blue-50 dark:fill-blue-950/70 stroke-blue-200 dark:stroke-blue-500/55" />
        {/* Inner glow core */}
        <circle cx="60" cy="38" r="6" filter="url(#ag-glow)"
            className="fill-blue-400 dark:fill-blue-400">
            <animate attributeName="r" values="6;7;6" dur="2.6s" repeatCount="indefinite" />
        </circle>

        {/* ── Left (emerald) node ── */}
        <circle cx="28" cy="76" r="9" strokeWidth="1.5"
            className="fill-emerald-50 dark:fill-emerald-950/60 stroke-emerald-200 dark:stroke-emerald-500/55" />
        <circle cx="28" cy="76" r="4.5" filter="url(#ag-soft)"
            className="fill-emerald-400 dark:fill-emerald-400" />

        {/* ── Right (violet) node ── */}
        <circle cx="92" cy="76" r="9" strokeWidth="1.5"
            className="fill-violet-50 dark:fill-violet-950/60 stroke-violet-200 dark:stroke-violet-500/55" />
        <circle cx="92" cy="76" r="4.5" filter="url(#ag-soft)"
            className="fill-violet-400 dark:fill-violet-400" />

        {/* Ambient micro-particles */}
        <circle cx="11" cy="52" r="2.2" className="fill-slate-200 dark:fill-slate-600">
            <animate attributeName="opacity" values="0.2;0.65;0.2" dur="3.2s" repeatCount="indefinite" />
        </circle>
        <circle cx="109" cy="52" r="1.8" className="fill-slate-200 dark:fill-slate-600">
            <animate attributeName="opacity" values="0.2;0.65;0.2" dur="3.6s" begin="1s" repeatCount="indefinite" />
        </circle>
        <circle cx="60" cy="95" r="2" className="fill-slate-200 dark:fill-slate-600">
            <animate attributeName="opacity" values="0.2;0.65;0.2" dur="2.8s" begin="0.5s" repeatCount="indefinite" />
        </circle>
    </svg>
);

// ── Tasks: Layered Checklist Cards ───────────────────────────────────────────
// Stacked deck of 3 cards; front card shows one completed item + two pending.

export const TasksIllustration: React.FC<{ className?: string }> = ({ className }) => (
    <svg viewBox="0 0 120 100" fill="none" xmlns="http://www.w3.org/2000/svg"
        className={className} aria-hidden="true">
        <defs>
            <filter id="task-glow" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur stdDeviation="2" result="blur" />
                <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                </feMerge>
            </filter>
        </defs>

        {/* Back card — rotated CW */}
        <rect x="32" y="22" width="56" height="62" rx="9"
            transform="rotate(6 60 53)"
            className="fill-slate-100 dark:fill-slate-800/50 stroke-slate-200 dark:stroke-slate-700/50"
            strokeWidth="1" />

        {/* Middle card — slight CCW tilt */}
        <rect x="30" y="20" width="56" height="62" rx="9"
            transform="rotate(-3 60 51)"
            className="fill-slate-50 dark:fill-slate-800/75 stroke-slate-200 dark:stroke-slate-700/70"
            strokeWidth="1" />

        {/* Front card — upright, main surface */}
        <rect x="28" y="18" width="60" height="66" rx="9"
            className="fill-white dark:fill-slate-800 stroke-slate-200 dark:stroke-slate-700"
            strokeWidth="1.5" />

        {/* Card header strip */}
        <rect x="28" y="18" width="60" height="16" rx="9"
            className="fill-blue-50 dark:fill-blue-500/12" />
        {/* Square off bottom of header */}
        <rect x="28" y="26" width="60" height="8"
            className="fill-blue-50 dark:fill-blue-500/12" />
        {/* Header accent dot */}
        <circle cx="39" cy="26" r="4"
            className="fill-blue-400 dark:fill-blue-400" filter="url(#task-glow)" />
        {/* Header label pill */}
        <rect x="48" y="23" width="28" height="6" rx="3"
            className="fill-blue-200/70 dark:fill-blue-500/35" />

        {/* ── Row 1: completed ── */}
        {/* Filled checkbox */}
        <rect x="36" y="41" width="11" height="11" rx="3.5"
            className="fill-emerald-400 dark:fill-emerald-500"
            strokeWidth="0" />
        {/* Checkmark */}
        <path d="M38.5 46.5 L41.5 49 L46 43"
            stroke="white" strokeWidth="1.8"
            strokeLinecap="round" strokeLinejoin="round" />
        {/* Strikethrough text */}
        <rect x="52" y="43" width="26" height="5.5" rx="2.75"
            className="fill-slate-200 dark:fill-slate-600/80" />
        {/* Strikethrough line */}
        <line x1="52" y1="45.75" x2="78" y2="45.75" strokeWidth="1"
            className="stroke-slate-400/60 dark:stroke-slate-500/60" />

        {/* ── Row 2: pending ── */}
        <rect x="36" y="57" width="11" height="11" rx="3.5" fill="none"
            className="stroke-slate-300 dark:stroke-slate-600"
            strokeWidth="1.5" />
        <rect x="52" y="59" width="20" height="5.5" rx="2.75"
            className="fill-slate-100 dark:fill-slate-700" />

        {/* ── Row 3: pending ── */}
        <rect x="36" y="73" width="11" height="11" rx="3.5" fill="none"
            className="stroke-slate-300 dark:stroke-slate-600"
            strokeWidth="1.5" />
        <rect x="52" y="75" width="24" height="5.5" rx="2.75"
            className="fill-slate-100 dark:fill-slate-700" />

        {/* 4-point sparkle — top-right corner */}
        <path d="M98 14 L99.4 17.8 L103.2 19.2 L99.4 20.6 L98 24.4 L96.6 20.6 L92.8 19.2 L96.6 17.8 Z"
            className="fill-yellow-400 dark:fill-yellow-400">
            <animate attributeName="opacity" values="0;1;0.8;0" dur="2.4s" repeatCount="indefinite" />
        </path>
        {/* Small secondary star */}
        <path d="M108 24 L108.8 26.2 L111 27 L108.8 27.8 L108 30 L107.2 27.8 L105 27 L107.2 26.2 Z"
            className="fill-yellow-300 dark:fill-yellow-500">
            <animate attributeName="opacity" values="0;1;0" dur="2.4s" begin="1.2s" repeatCount="indefinite" />
        </path>
    </svg>
);

// ── Inbox: Floating Envelope ──────────────────────────────────────────────────
// Open envelope with letter peeking; notification badge + subtle float animation.

export const InboxIllustration: React.FC<{ className?: string }> = ({ className }) => (
    <svg viewBox="0 0 120 100" fill="none" xmlns="http://www.w3.org/2000/svg"
        className={className} aria-hidden="true">
        <defs>
            <filter id="inbox-glow" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur stdDeviation="2.5" result="blur" />
                <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                </feMerge>
            </filter>
        </defs>

        {/* Floating envelope group */}
        <g>
            <animateTransform attributeName="transform" type="translate"
                values="0,0;0,-4;0,0" dur="3s"
                calcMode="spline" keyTimes="0;0.5;1"
                keySplines="0.45 0 0.55 1;0.45 0 0.55 1"
                repeatCount="indefinite" additive="sum" />

            {/* Shadow — subtle blur under envelope */}
            <ellipse cx="60" cy="92" rx="32" ry="4"
                className="fill-slate-900/8 dark:fill-black/20">
                <animate attributeName="rx" values="32;26;32" dur="3s"
                    calcMode="spline" keyTimes="0;0.5;1"
                    keySplines="0.45 0 0.55 1;0.45 0 0.55 1"
                    repeatCount="indefinite" />
            </ellipse>

            {/* Envelope body */}
            <rect x="16" y="36" width="88" height="52" rx="9"
                className="fill-white dark:fill-slate-800 stroke-slate-200 dark:stroke-slate-700"
                strokeWidth="1.5" />

            {/* Letter peeking out (slides gently with envelope) */}
            <rect x="30" y="28" width="60" height="36" rx="5"
                className="fill-white dark:fill-slate-750 stroke-slate-100 dark:stroke-slate-700/60"
                strokeWidth="1">
                <animate attributeName="y" values="28;24;28" dur="3s"
                    calcMode="spline" keyTimes="0;0.5;1"
                    keySplines="0.45 0 0.55 1;0.45 0 0.55 1"
                    repeatCount="indefinite" />
            </rect>
            {/* Letter lines */}
            <rect x="40" y="35" width="40" height="3" rx="1.5"
                className="fill-slate-200 dark:fill-slate-600">
                <animate attributeName="y" values="35;31;35" dur="3s"
                    calcMode="spline" keyTimes="0;0.5;1"
                    keySplines="0.45 0 0.55 1;0.45 0 0.55 1"
                    repeatCount="indefinite" />
            </rect>
            <rect x="40" y="42" width="28" height="3" rx="1.5"
                className="fill-slate-200 dark:fill-slate-600">
                <animate attributeName="y" values="42;38;42" dur="3s"
                    calcMode="spline" keyTimes="0;0.5;1"
                    keySplines="0.45 0 0.55 1;0.45 0 0.55 1"
                    repeatCount="indefinite" />
            </rect>

            {/* Bottom V-fold */}
            <path d="M16 58 L60 78 L104 58" strokeWidth="1.2"
                fill="none" className="stroke-slate-200 dark:stroke-slate-700/80" />

            {/* Open flap (raised, accent-colored) */}
            <path d="M16 36 L60 14 L104 36" strokeWidth="1.5"
                strokeLinecap="round" strokeLinejoin="round" fill="none"
                className="stroke-emerald-400 dark:stroke-emerald-500" />
        </g>

        {/* Notification badge — fixed so it doesn't float with envelope */}
        <circle cx="94" cy="32" r="10" className="fill-white dark:fill-slate-900" />
        <circle cx="94" cy="32" r="8" filter="url(#inbox-glow)"
            className="fill-blue-500 dark:fill-blue-500">
            <animate attributeName="r" values="8;9;8" dur="2s" repeatCount="indefinite" />
        </circle>
        <text x="94" y="36" textAnchor="middle" fontSize="7.5" fill="white"
            fontFamily="system-ui, sans-serif" fontWeight="700">1</text>

        {/* Ambient sparkles */}
        <circle cx="20" cy="24" r="2" className="fill-emerald-400 dark:fill-emerald-400">
            <animate attributeName="opacity" values="0;1;0" dur="1.9s" repeatCount="indefinite" />
        </circle>
        <circle cx="12" cy="38" r="1.5" className="fill-blue-300 dark:fill-blue-500">
            <animate attributeName="opacity" values="0;1;0" dur="2.5s" begin="0.6s" repeatCount="indefinite" />
        </circle>
        <circle cx="28" cy="16" r="1.3" className="fill-teal-300 dark:fill-teal-500">
            <animate attributeName="opacity" values="0;1;0" dur="2.1s" begin="1.1s" repeatCount="indefinite" />
        </circle>
    </svg>
);

// ── Knowledge: Open Book with Floating Page ───────────────────────────────────
// Classic open book with highlighted text + an animated page card floating above.

export const KnowledgeIllustration: React.FC<{ className?: string }> = ({ className }) => (
    <svg viewBox="0 0 120 100" fill="none" xmlns="http://www.w3.org/2000/svg"
        className={className} aria-hidden="true">
        <defs>
            <filter id="know-glow" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur stdDeviation="2" result="blur" />
                <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                </feMerge>
            </filter>
        </defs>

        {/* Book shadow */}
        <ellipse cx="60" cy="88" rx="38" ry="4"
            className="fill-slate-900/6 dark:fill-black/20" />

        {/* ── Left page ── */}
        <path d="M20 28 Q38 22 60 26 L60 82 Q38 78 20 80 Z"
            className="fill-white dark:fill-slate-800 stroke-slate-200 dark:stroke-slate-700"
            strokeWidth="1.5" />
        {/* Left page lines */}
        <rect x="28" y="40" width="22" height="2.5" rx="1.25"
            className="fill-slate-200 dark:fill-slate-600" />
        <rect x="28" y="48" width="18" height="2.5" rx="1.25"
            className="fill-slate-200 dark:fill-slate-600" />
        <rect x="28" y="56" width="20" height="2.5" rx="1.25"
            className="fill-slate-200 dark:fill-slate-600" />
        <rect x="28" y="64" width="13" height="2.5" rx="1.25"
            className="fill-slate-100 dark:fill-slate-700" />

        {/* ── Right page ── */}
        <path d="M100 28 Q82 22 60 26 L60 82 Q82 78 100 80 Z"
            className="fill-white dark:fill-slate-800 stroke-slate-200 dark:stroke-slate-700"
            strokeWidth="1.5" />
        {/* Right page lines — one row highlighted in blue to suggest active knowledge */}
        <rect x="68" y="40" width="22" height="2.5" rx="1.25"
            className="fill-slate-200 dark:fill-slate-600" />
        <rect x="68" y="48" width="17" height="2.5" rx="1.25"
            className="fill-blue-200 dark:fill-blue-500/50" />
        <rect x="68" y="56" width="20" height="2.5" rx="1.25"
            className="fill-slate-200 dark:fill-slate-600" />
        <rect x="68" y="64" width="13" height="2.5" rx="1.25"
            className="fill-blue-100 dark:fill-blue-500/28" />

        {/* Book spine */}
        <line x1="60" y1="26" x2="60" y2="82" strokeWidth="2" strokeLinecap="round"
            className="stroke-slate-300 dark:stroke-slate-600" />

        {/* ── Floating knowledge card (animates up and down) ── */}
        <g>
            <animateTransform attributeName="transform" type="translate"
                values="0,0;0,-5;0,0" dur="2.9s"
                calcMode="spline" keyTimes="0;0.5;1"
                keySplines="0.45 0 0.55 1;0.45 0 0.55 1"
                repeatCount="indefinite" additive="sum" />
            <rect x="70" y="10" width="24" height="18" rx="4"
                className="fill-blue-50 dark:fill-blue-500/15 stroke-blue-200 dark:stroke-blue-500/45"
                strokeWidth="1" transform="rotate(7 82 19)" />
            <rect x="74" y="14" width="14" height="2.5" rx="1.25"
                className="fill-blue-300 dark:fill-blue-400/60"
                transform="rotate(7 82 19)" />
            <rect x="74" y="19" width="10" height="2.5" rx="1.25"
                className="fill-blue-200 dark:fill-blue-500/40"
                transform="rotate(7 82 19)" />
        </g>

        {/* Glow sparkles */}
        <circle cx="100" cy="12" r="2.2"
            className="fill-blue-400 dark:fill-blue-400" filter="url(#know-glow)">
            <animate attributeName="opacity" values="0;1;0" dur="2s" repeatCount="indefinite" />
        </circle>
        <circle cx="108" cy="22" r="1.6"
            className="fill-sky-300 dark:fill-sky-500">
            <animate attributeName="opacity" values="0;1;0" dur="2.6s" begin="0.7s" repeatCount="indefinite" />
        </circle>
        <circle cx="96" cy="6" r="1.3"
            className="fill-indigo-300 dark:fill-indigo-400">
            <animate attributeName="opacity" values="0;1;0" dur="1.8s" begin="1.3s" repeatCount="indefinite" />
        </circle>
    </svg>
);

// ── Workflows: Three-Stage Pipeline ──────────────────────────────────────────
// Trigger → Process → Output blocks with signal pulses on the connectors.

export const WorkflowsIllustration: React.FC<{ className?: string }> = ({ className }) => (
    <svg viewBox="0 0 120 100" fill="none" xmlns="http://www.w3.org/2000/svg"
        className={className} aria-hidden="true">
        <defs>
            <filter id="wf-glow" x="-80%" y="-80%" width="260%" height="260%">
                <feGaussianBlur stdDeviation="2.5" result="blur" />
                <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                </feMerge>
            </filter>
        </defs>

        {/* ── Connectors ── */}
        {/* Stage 1 → 2 */}
        <line x1="40" y1="50" x2="52" y2="50" strokeWidth="1.5"
            strokeDasharray="2.5 2" strokeLinecap="round"
            className="stroke-slate-300 dark:stroke-slate-600" />
        <path d="M50 47.5 L53.5 50 L50 52.5" strokeWidth="1.2" fill="none"
            strokeLinecap="round" strokeLinejoin="round"
            className="stroke-slate-400 dark:stroke-slate-500" />

        {/* Stage 2 → 3 */}
        <line x1="68" y1="50" x2="80" y2="50" strokeWidth="1.5"
            strokeDasharray="2.5 2" strokeLinecap="round"
            className="stroke-slate-300 dark:stroke-slate-600" />
        <path d="M78 47.5 L81.5 50 L78 52.5" strokeWidth="1.2" fill="none"
            strokeLinecap="round" strokeLinejoin="round"
            className="stroke-slate-400 dark:stroke-slate-500" />

        {/* Animated signal dots */}
        <circle r="2.2" className="fill-indigo-400 dark:fill-indigo-400">
            <animateMotion dur="1.5s" repeatCount="indefinite" path="M40,50 L52,50" />
            <animate attributeName="opacity" values="0;1;0" dur="1.5s" repeatCount="indefinite" />
        </circle>
        <circle r="2.2" className="fill-emerald-400 dark:fill-emerald-400">
            <animateMotion dur="1.5s" begin="0.75s" repeatCount="indefinite" path="M68,50 L80,50" />
            <animate attributeName="opacity" values="0;1;0" dur="1.5s" begin="0.75s" repeatCount="indefinite" />
        </circle>

        {/* ── Stage 1: Trigger (Indigo) ── */}
        {/* Outer pulse ring */}
        <rect x="8" y="33" width="32" height="34" rx="9" fill="none"
            className="stroke-indigo-400 dark:stroke-indigo-400"
            strokeWidth="1">
            <animate attributeName="opacity" values="0;0.5;0" dur="2.2s" repeatCount="indefinite" />
            <animate attributeName="stroke-width" values="1;3;1" dur="2.2s" repeatCount="indefinite" />
        </rect>
        {/* Node body */}
        <rect x="8" y="33" width="32" height="34" rx="9"
            className="fill-indigo-50 dark:fill-indigo-500/12 stroke-indigo-300 dark:stroke-indigo-500/60"
            strokeWidth="1.5" />
        {/* Play icon */}
        <path d="M19 43 L19 57 L31 50 Z"
            className="fill-indigo-400 dark:fill-indigo-400" filter="url(#wf-glow)" />

        {/* ── Stage 2: Process (Slate) ── */}
        <rect x="52" y="33" width="16" height="34" rx="6"
            className="fill-slate-50 dark:fill-slate-800/80 stroke-slate-300 dark:stroke-slate-600"
            strokeWidth="1.5" />
        {/* Spinning gear ring */}
        <circle cx="60" cy="45" r="5" fill="none"
            className="stroke-slate-400 dark:stroke-slate-500"
            strokeWidth="1.4">
            <animateTransform attributeName="transform" type="rotate"
                from="0 60 45" to="360 60 45" dur="4s" repeatCount="indefinite" />
        </circle>
        <circle cx="60" cy="45" r="2.2"
            className="fill-slate-300 dark:fill-slate-600">
            <animateTransform attributeName="transform" type="rotate"
                from="0 60 45" to="360 60 45" dur="4s" repeatCount="indefinite" />
        </circle>
        {/* Lines below gear */}
        <rect x="55" y="55" width="10" height="2" rx="1"
            className="fill-slate-200 dark:fill-slate-700" />
        <rect x="56.5" y="59" width="7" height="2" rx="1"
            className="fill-slate-200 dark:fill-slate-700" />

        {/* ── Stage 3: Output (Emerald) ── */}
        <rect x="80" y="33" width="32" height="34" rx="9"
            className="fill-emerald-50 dark:fill-emerald-500/12 stroke-emerald-300 dark:stroke-emerald-500/60"
            strokeWidth="1.5" />
        {/* Large checkmark */}
        <path d="M87 50 L93 57 L104 42"
            strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none"
            className="stroke-emerald-400 dark:stroke-emerald-400" filter="url(#wf-glow)" />

        {/* ── Label pills above nodes ── */}
        {/* Trigger label */}
        <rect x="10" y="22" width="28" height="8" rx="4"
            className="fill-indigo-50 dark:fill-indigo-500/10" />
        <rect x="14" y="25" width="20" height="2.5" rx="1.25"
            className="fill-indigo-200 dark:fill-indigo-500/35" />
        {/* Process label */}
        <rect x="53.5" y="22" width="13" height="8" rx="4"
            className="fill-slate-100 dark:fill-slate-700/60" />
        <rect x="56" y="25" width="8" height="2.5" rx="1.25"
            className="fill-slate-200 dark:fill-slate-600" />
        {/* Output label */}
        <rect x="82" y="22" width="28" height="8" rx="4"
            className="fill-emerald-50 dark:fill-emerald-500/10" />
        <rect x="86" y="25" width="20" height="2.5" rx="1.25"
            className="fill-emerald-200 dark:fill-emerald-500/35" />
    </svg>
);

// ── Illustration map ─────────────────────────────────────────────────────────

export const ILLUSTRATION_MAP: Record<string, React.FC<{ className?: string }>> = {
    agents:    AgentsIllustration,
    tasks:     TasksIllustration,
    inbox:     InboxIllustration,
    knowledge: KnowledgeIllustration,
    workflows: WorkflowsIllustration,
};