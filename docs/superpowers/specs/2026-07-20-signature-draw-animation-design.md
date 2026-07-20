# Signature Draw-On Animation — Design

- **Date:** 2026-07-20
- **Status:** approved
- **Scope:** Animate the login/signup background signature with a one-time "slow signing" reveal.

## Goal

When the auth page loads, the signature watermark in the bottom-right of
`FlatMapAuthBackground` should reveal itself **once**, left → right, like a
person slowly signing. It must remain the faint, theme-aware watermark already
shipped (dark in light mode, white in dark mode; ~0.3 opacity; bottom-right
placement; sized `w-44`).

## Approach

**Directional reveal via Framer Motion `clip-path` inset animation** (chosen
over SVG-mask and CSS-only alternatives — see Alternatives).

The signature is a *filled* SVG, not pen strokes, so a true `pathLength`
stroke-draw is not applicable without converting the artwork. A left-to-right
`clip-path` sweep reveals the real signature pixels directly over the live
Three.js map background, which is exactly the "being written" feel the user
asked for and avoids an overlay rectangle that would clash with the animated
background.

## Files & Changes

### `frontend/src/components/SignatureMark.tsx` (unchanged)

Stays a pure, static inline SVG using `fill="currentColor"` so the parent
controls color via `text-gray-900 dark:text-white`. No animation logic here.

### `frontend/src/components/FlatMapAuthBackground.tsx` (edit)

Wrap the existing signature `<SignatureMark>` in a `motion.div` (from
`framer-motion`, already a dependency at `^12.34.3`):

- `initial`: `{ clipPath: 'inset(0 100% 0 0)', opacity: 0 }`
- `animate`: `{ clipPath: 'inset(0 0% 0 0)', opacity: 0.3 }`
- `transition`: `{ duration: 1.4, ease: [0.22, 1, 0.36, 1], delay: 0.3 }`
- Mount-only (no `whileInView`, no loop) → plays once on page load.

Reduced-motion handling:

- Use `useReducedMotion()` from `framer-motion`.
- When reduced motion is preferred, set `initial` === `animate` (full signature,
  `opacity: 0.3`) so it appears instantly with no sweep.

The wrapper keeps the current positioning classes
(`absolute bottom-1 right-8 pointer-events-none z-10 opacity-30` is replaced by
the motion div carrying equivalent positioning + the animated opacity). The
theme color class (`text-gray-900 dark:text-white`) stays on `SignatureMark`.

## Behavior Spec

| Aspect | Value |
|--------|-------|
| Trigger | Page load / component mount |
| Repeats | No (one-shot) |
| Direction | Left → right reveal |
| Duration | 1.4s |
| Easing | `[0.22, 1, 0.36, 1]` (ease-out, Apple-style) |
| Start delay | 0.3s |
| Opacity | 0 → 0.3 (faint watermark preserved) |
| Reduced motion | Instant full reveal, no animation |
| Position / size / color | Unchanged from current shipped state |

## Fidelity Note

The signature's viewBox currently contains empty horizontal padding on its
right (and the second path starts partway across), so the sweep reveals the ink
across roughly the first ~60% of the timeline, with the remainder revealing
empty space. This is acceptable and matches a natural "writing" sweep. If the
user later wants the wipe to track the ink exactly, the viewBox can be
tightened horizontally — but that changes on-screen size and is out of scope
unless requested.

## Error Handling

- No async, no network, no user input → no failure modes beyond the animation
  not playing. If `framer-motion` fails to load, the element still renders the
  static signature (the SVG is always in the DOM); worst case is no animation.
- Reduced-motion path guarantees the signature is always visible regardless of
  animation support.

## Testing

- `tsc --noEmit` passes (type-check the `motion.div` props).
- `npm run lint` passes (no `text--600` regressions; existing lint config).
- Manual: load `/login` (and `/signup`) → signature reveals left→right once on
  load; reload → replays once. Toggle OS "reduce motion" → signature appears
  instantly, no sweep. Confirm light mode shows dark signature, dark mode shows
  white. Confirm placement/size unchanged from the approved static version.

## Alternatives Considered

1. **SVG `<mask>` + animated `<rect>`** — Same visual result, more code; only
   useful for a future curved/non-linear wipe. Rejected as overkill.
2. **CSS-only `@keyframes` clip-path** — Lighter, but harder to coordinate
   reduced-motion and inconsistent with the project's `framer-motion` usage.
   Rejected.
3. **True pen-stroke draw (`pathLength`/`stroke-dashoffset`)** — Requires
   converting the filled artwork to a stroked outline; would trace the contour
   rather than fill the signature. Rejected because the SVG is filled and the
   user selected the directional-reveal style.

## Out of Scope

- Replaying the animation on theme toggle or other events.
- Tightening the viewBox horizontally to make the wipe track the ink exactly.
- Applying the animation to any other logo/branding element.
