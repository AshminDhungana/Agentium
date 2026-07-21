# Voice Bridge UI Redesign Plan

## Overview
Redesign the Voice Bridge UI in the Agentium frontend to provide a modern, polished voice interaction experience with real-time visual feedback, smooth animations, and intuitive controls.

## Objectives
1. Redesign the Voice Bridge UI component with modern, polished visual design
2. Implement real-time audio visualization (waveform, frequency bars, orb)
- WebSocket streaming visualization
- Real-time audio level visualization
- Microphone activity indicator
3. Implement smooth, performant animations using Motion.dev (Framer Motion)
3. Create intuitive voice controls (record, stop, mute, settings)
4. Add connection status indicator with WebSocket status
4. Ensure accessibility (WCAG AA) and reduced motion support
5. Integrate with existing Voice Bridge WebSocket backend
5. Follow Agentium design system (design tokens, Tailwind, Zustand)

## Scope
- Frontend only: `frontend/src/components/voice-bridge/` and related components
- Integration with existing Voice Bridge WebSocket backend (`voice-bridge/` service)
- No backend changes required
- Follow Agentium design system (Tailwind, design tokens, Zustand state)

## Technical Stack
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Zustand
- **Animations**: Motion.dev (Framer Motion) - spring animations, layout animations, layoutId
- **Visualization**: Canvas-based audio visualization (waveform, frequency bars, orb)
- **State Management**: Zustand (existing Agentium store)
- **WebSocket**: Existing Voice Bridge WebSocket client in `frontend/src/services/voice-bridge.ts`

## Design Requirements
Refer to `docs/superpowers/specs/2026-07-21-voice-bridge-ui-redesign-design.md` for detailed design specifications.

### Visual Design
- Dark theme with glassmorphism/glassmorphism cards
- Accent color: Agentium primary (blue/purple gradient)
- Glassmorphism cards with backdrop blur
- Subtle glow effects on active states
- Typography: Inter font, clear hierarchy
- Spacing: 8px base unit, consistent spacing scale

### Components to Build
1. **VoiceBridgeContainer** - Main container, WebSocket connection management
2. **VoiceOrb** - Animated orb visualization (idle, listening, speaking, processing states)
3. **WaveformVisualizer** - Real-time waveform visualization (Canvas)
4. **FrequencyBars** - Frequency bar visualization (Canvas)
5. **VoiceControls** - Record, stop, mute, settings buttons with Motion.dev animations
6. **ConnectionStatus** - WebSocket connection status indicator
5. **MicrophoneLevel** - Microphone input level indicator
5. **VoiceSettings** - Settings panel (model, voice, language, VAD sensitivity)
6. **TranscriptDisplay** - Real-time transcript display with streaming text
7. **VoiceBridgeContainer** - Main container orchestrating all components

### Animations (Motion.dev)
- Orb: Spring animations for state transitions (idle ↔ listening ↔ speaking ↔ processing)
- Buttons: Scale on tap, hover scale, focus ring
- Waveform/Frequency bars: Smooth spring animations, staggered
- Transcript: Smooth text reveal, auto-scroll
- Settings panel: Slide/fade in/out with spring
- Respect `prefers-reduced-motion`

### Accessibility
- WCAG AA contrast ratios
- Keyboard navigation (Tab, Enter, Space, Escape)
- ARIA labels and roles
- `prefers-reduced-motion` support
- Screen reader announcements for state changes
- Focus visible outlines

## Integration Points
- **WebSocket Service**: `frontend/src/services/voice-bridge.ts` - existing WebSocket client
- **State Management**: Zustand store (extend existing voice store or create new)
- **Design Tokens**: Use Agentium design tokens (colors, spacing, typography)
- **WebSocket Service**: `frontend/src/services/voice-bridge.ts` (existing)

## Files to Create/Modify
### New Components (`frontend/src/components/voice-bridge/`)
- `VoiceBridgeContainer.tsx` - Main container
- `VoiceOrb.tsx` - Animated orb visualization
- `WaveformVisualizer.tsx` - Canvas waveform
- `FrequencyBars.tsx` - Frequency bars visualization
- `VoiceControls.tsx` - Control buttons
- `ConnectionStatus.tsx` - Connection status indicator
- `MicrophoneLevel.tsx` - Microphone level indicator
- `VoiceSettings.tsx` - Settings panel
- `TranscriptDisplay.tsx` - Transcript display
- `index.ts` - Barrel export
- `types.ts` - TypeScript types
- `hooks/` - Custom hooks (useVoiceBridge, useAudioVisualization, useVoiceSettings)

### Modified Files
- `frontend/src/stores/voiceStore.ts` - Extend or create voice store (Zustand)
- `frontend/src/services/voice-bridge.ts` - Ensure WebSocket integration works
- `frontend/src/pages/VoiceBridgePage.tsx` - Main page component (create or update)
- `frontend/src/App.tsx` - Add route if needed
- `frontend/src/index.css` - Add any global styles/CSS variables needed

### Design Tokens
- Ensure Agentium design tokens are used (colors, spacing, typography, shadows, border-radius)
- CSS variables for dynamic theming (orb colors per state)

## Implementation Phases

### Phase 1: Foundation & Types
- [ ] Create type definitions (`types.ts`)
- [ ] Create/update Zustand voice store (`voiceStore.ts`)
- [ ] Create custom hooks (`hooks/useVoiceBridge.ts`, `hooks/useAudioVisualization.ts`, `hooks/useVoiceSettings.ts`)
- [ ] Set up WebSocket service integration (`voice-bridge.ts`)

### Phase 2: Core Visual Components
- [ ] Create `VoiceOrb` component with Motion.dev animations
- [ ] Create `WaveformVisualizer` (Canvas-based)
- [ ] Create `FrequencyBars` (Canvas-based)
- [ ] Create `MicrophoneLevel` indicator

### Phase 3: Control Components
- [ ] Create `VoiceControls` with Motion.dev animations
- [ ] Create `ConnectionStatus` indicator
- [ ] Create `MicrophoneLevel` indicator
- [ ] Create `VoiceSettings` panel

### Phase 4: Transcript & Container
- [ ] Create `TranscriptDisplay` with streaming text animation
- [ ] Create `ConnectionStatus` indicator
- [ ] Create `VoiceBridgeContainer` orchestrating all components
- [ ] Create `VoiceBridgePage` page component

### Phase 5: Integration & Polish
- [ ] Integrate with `voice-bridge.ts` WebSocket service
- [ ] Wire up Zustand store
- [ ] Add VoiceBridgePage to routing
- [ ] Add global styles/CSS variables
- [ ] Accessibility audit (WCAG AA, keyboard nav, ARIA, reduced motion)
- [ ] Performance optimization (Canvas optimization, Motion.dev optimization)
- [ ] Testing and polish

## Acceptance Criteria
- [ ] Voice Bridge page accessible at `/voice-bridge` route
- [ ] WebSocket connects to Voice Bridge backend (ws://localhost:8000/ws/voice)
- [ ] Real-time audio visualization works (orb, waveform, frequency bars)
- [ ] Voice controls work (record, stop, mute, settings)
- [ ] Connection status shows WebSocket state
- [ ] Microphone level indicator works
- [ ] Settings panel opens/closes with animation
- [ ] Transcript displays streaming text smoothly
- [ ] All animations respect `prefers-reduced-motion`
- [ ] Keyboard navigation works (Tab, Enter, Space, Escape)
- [ ] ARIA labels and roles present
- [ ] WCAG AA contrast ratios met
- [ ] `prefers-reduced-motion` respected (animations disabled)
- [ ] Focus visible outlines present
- [ ] Screen reader announcements for state changes
- [ ] Performance: 60fps animations, Canvas optimized
- [ ] Integrated with Voice Bridge WebSocket backend (ws://localhost:8000/ws/voice)
- [ ] Integrated with Agentium Zustand store
- [ ] Route accessible at `/voice-bridge`
- [ ] Design tokens used consistently (colors, spacing, typography)
- [ ] Glassmorphism/glassmorphism design applied
- [ ] Smooth 60fps animations with Motion.dev
- [ ] `prefers-reduced-motion` respected

## Dependencies
- `framer-motion` (Motion.dev) - already in package.json
- `frontend/src/services/voice-bridge.ts` - existing WebSocket service
- `frontend/src/stores/` - Zustand store
- Agentium design tokens (Tailwind config)

## Timeline
- Phase 1: Foundation & Types - 1 day
- Phase 2: Core Visual Components - 2 days
- Phase 3: Control Components - 1.5 days
- Phase 4: Transcript & Container - 1.5 days
- Phase 5: Integration & Polish - 2 days
- **Total: ~8 days**

## Success Criteria
- Voice Bridge page accessible at `/voice-bridge`
- Real-time audio visualization working (60fps)
- All controls functional with WebSocket backend
- WCAG AA compliant
- `prefers-reduced-motion` respected
- 60fps animations
- Integrated with Agentium design system
- Accessible at `/voice-bridge` route