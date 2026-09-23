# Settings Page Design Specification

**Date:** 2026-09-23  
**Status:** Approved  
**Author:** AI Assistant  
**Reviewed by:** User

---

## 1. Overview

The Settings Page (`SettingsPage.tsx`) will be expanded from 2 tabs (Account Settings, User Management) to 6 tabs covering all user-configurable aspects of Agentium. The page manages user preferences, appearance, API keys, notifications, and admin user management.

---

## 2. Tab Structure

| Tab | ID | Access | Description |
|-----|----|--------|-------------|
| Account | `account` | All users | Password, avatar, 2FA status, last login, user ID |
| Appearance | `appearance` | All users | Theme (dark/light/system), language, font size, sidebar, animations |
| Preferences | `preferences` | All users | All 9 backend preference categories with appropriate inputs |
| API Keys | `api-keys` | All users | Embedded model config management (add/edit/delete/test) |
| Notifications | `notifications` | All users | Notification channels, sound, per-event toggles |
| User Management | `users` | Admin only | Embedded `UserManagement` component |

---

## 3. Frontend Architecture

### 3.1 New Components

```
frontend/src/
├── components/
│   └── settings/
│       ├── PreferencesTab.tsx       # Main preferences panel with 9 collapsible sections
│       ├── PreferenceSection.tsx    # Single category renderer (category + inputs)
│       ├── PreferenceInput.tsx      # Polymorphic input based on data_type
│       ├── ThemeSelector.tsx        # Theme toggle (dark/light/system)
│       ├── ApiKeysTab.tsx           # Embedded model config management
│       ├── NotificationsTab.tsx     # Notification preferences UI
│       └── SettingsTab.tsx          # Base tab component (optional)
├── hooks/
│   └── useUserPreferences.ts        # Fetch/save preferences hook
├── services/
│   └── preferences.ts               # API client for /api/v1/preferences
└── pages/
    └── SettingsPage.tsx             # Modified: expanded tabs + new panels
```

### 3.2 Component Responsibilities

#### `useUserPreferences` Hook
- Fetches all preferences on mount: `GET /api/v1/preferences`
- Merges with `DEFAULT_PREFERENCES` from backend
- Provides `updatePreference(key, value)` → `PUT /api/v1/preferences/{key}`
- Provides `bulkUpdate(preferences)` → `POST /api/v1/preferences/bulk`
- Handles optimistic updates with rollback on error

#### `PreferencesTab`
- Renders 9 collapsible sections (one per `PreferenceCategory`)
- Sections: General, UI, Chat, Notifications, Agents, Tasks, Models, Tools, Privacy
- Each section uses `PreferenceSection`

#### `PreferenceSection`
- Receives category name + array of preferences
- Renders section header with description
- Maps each preference to `PreferenceInput`

#### `PreferenceInput` (Polymorphic)
| `data_type` | Input Component |
|-------------|-----------------|
| boolean | Toggle switch |
| integer/float | Number input with step |
| string | Text input |
| array | Multi-select or tag input |
| json | Textarea with JSON validation |

#### `ThemeSelector`
- Three options: Light, Dark, System (follows OS)
- On change: calls `setDarkMode()` + persists `ui.theme` preference
- On mount: reads `ui.theme` preference, applies to `document.documentElement`

#### `ApiKeysTab`
- Lists existing model configs (from `useModelConfigs` hook)
- Each row: provider name, default model, status, actions (edit/test/delete/set default)
- "Add Provider" button opens embedded `ModelConfigForm` (step='configure' with provider pre-selected)
- Reuses `modelsApi` service and `ModelConfigForm` logic

#### `NotificationsTab`
- Master toggle: `notifications.enabled`
- Sound toggle: `notifications.sound`
- Channel multi-select: `notifications.channels` (websocket, email)
- Future: per-event toggles (task_complete, agent_error, etc.)

---

## 4. Backend Integration

### 4.1 Existing API (Complete)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/preferences` | GET | List all preferences (with category/scope filters) |
| `/api/v1/preferences/{key}` | GET | Get single preference |
| `/api/v1/preferences` | POST | Create preference |
| `/api/v1/preferences/{key}` | PUT | Update preference |
| `/api/v1/preferences/{key}` | DELETE | Soft-delete preference |
| `/api/v1/preferences/bulk` | POST | Bulk update |
| `/api/v1/preferences/system/defaults` | GET | Get all defaults + category metadata |
| `/api/v1/preferences/system/initialize` | POST | Initialize user defaults |

### 4.2 Default Preferences (51 keys across 9 categories)

| Category | Keys (examples) |
|----------|-----------------|
| GENERAL | — |
| UI | `ui.theme`, `ui.language`, `ui.sidebar_collapsed`, `ui.font_size` |
| CHAT | `chat.history_limit`, `chat.context_window_size`, `chat.auto_save`, `chat.show_typing_indicator`, `chat.prune_*` |
| NOTIFICATIONS | `notifications.enabled`, `notifications.sound`, `notifications.channels` |
| AGENTS | `agents.default_timeout`, `agents.max_concurrent_tasks`, `agents.idle_timeout_minutes` |
| TASKS | `tasks.auto_archive_days`, `tasks.default_priority` |
| MODELS | `models.default_temperature`, `models.default_max_tokens` |
| TOOLS | `tools.max_execution_time`, `tools.auto_retry_failed` |
| PRIVACY | `privacy.share_usage_analytics` |

---

## 5. Data Flow

### 5.1 Initial Load
```
SettingsPage mounts
  → useUserPreferences() fetches GET /api/v1/preferences
  → Merges with DEFAULT_PREFERENCES (system defaults as fallback)
  → ThemeSelector reads ui.theme → applies to document.documentElement
  → All tabs receive merged preferences object
```

### 5.2 Preference Change
```
User toggles input in PreferenceInput
  → Optimistic UI update
  → PUT /api/v1/preferences/{key} with new value
  → On success: confirm
  → On error: rollback + toast error
  → If key === 'ui.theme': also call setDarkMode()
```

### 5.3 Theme Change
```
ThemeSelector selection changes
  → setDarkMode(next) toggles 'dark' class on <html>
  → Persists to localStorage (existing behavior)
  → Dispatches 'agentium:theme-change' event
  → PUT /api/v1/preferences/ui.theme with value
```

### 5.4 API Key Management
```
ApiKeysTab loads
  → useModelConfigs() fetches GET /api/v1/models/configs
  → Renders list with actions
  → "Add Provider" → ModelConfigForm (embedded, step='configure')
  → On save → modelsApi.createConfig() → refresh list
  → On edit → ModelConfigForm with initialConfig → modelsApi.updateConfig()
```

---

## 6. User Management Tab (Admin)

- Reuses existing `UserManagement` component with `embedded=true` prop
- Only renders when `user.is_admin === true`
- Tab badge shows pending user count via `onPendingCountChange` callback
- Already implemented and working

---

## 7. Styling & UX

- **Theme-aware**: All components use existing `dark:` Tailwind classes
- **Transitions**: 240ms theme transition via `theme-transition` class (existing)
- **Responsive**: Grid layouts collapse on mobile
- **Accessibility**: ARIA labels, keyboard navigation, focus management
- **Empty states**: Helpful messages when no configs/preferences exist
- **Loading states**: Skeletons for preferences, spinners for API keys

---

## 8. Error Handling

| Scenario | Handling |
|----------|----------|
| Preference fetch fails | Show error banner, retry button, use defaults |
| Preference save fails | Toast error, rollback optimistic update |
| Theme preference save fails | Keep UI change, toast warning |
| API key test fails | Show inline error in ModelConfigForm |
| Network offline | Queue changes, sync on reconnect (future) |

---

## 9. Testing Strategy

### 9.1 Unit Tests
- `useUserPreferences` hook: fetch, update, bulk update, error cases
- `PreferenceInput`: renders correct input per data_type
- `ThemeSelector`: toggles theme, persists preference
- `ApiKeysTab`: list, add, edit, delete flows

### 9.2 Integration Tests
- Full SettingsPage render with all tabs
- Tab switching preserves state (already implemented via `hidden` class)
- Admin vs non-admin tab visibility
- Theme persistence across reloads

### 9.3 E2E Tests (Playwright)
- Complete user flow: change theme → verify persistence
- Complete user flow: update chat history limit → verify API call
- Complete user flow: add API key → verify appears in list
- Admin flow: access User Management tab

---

## 10. Implementation Order

1. **Hook & Service**: `useUserPreferences.ts`, `preferences.ts`
2. **Core Components**: `PreferenceInput.tsx`, `PreferenceSection.tsx`, `PreferencesTab.tsx`
3. **Appearance Tab**: `ThemeSelector.tsx` + integrate into SettingsPage
4. **Preferences Tab**: Wire up PreferencesTab in SettingsPage
5. **API Keys Tab**: `ApiKeysTab.tsx` (reuse ModelConfigForm)
6. **Notifications Tab**: `NotificationsTab.tsx`
7. **SettingsPage Integration**: Add all tabs, wire up state
8. **Tests**: Unit + integration tests
9. **Polish**: Accessibility audit, responsive check, dark mode verify

---

## 11. Acceptance Criteria

- [ ] All 6 tabs render correctly for appropriate user roles
- [ ] Theme selector works (Light/Dark/System) and persists
- [ ] All 51 default preferences are editable with correct input types
- [ ] Preference changes persist to backend and survive reload
- [ ] API Keys tab shows existing configs, allows add/edit/delete/test
- [ ] Notifications tab controls work and persist
- [ ] User Management tab only visible to admins
- [ ] No console errors, no TypeScript errors
- [ ] All existing SettingsPage functionality preserved (password, avatar)
- [ ] Dark/light mode renders correctly in all tabs

---

## 12. Out of Scope

- Per-event notification toggles (future enhancement)
- Preference import/export
- Preference sharing between users
- Advanced API key scopes/permissions
- Two-factor authentication setup (backend not ready)

---

## 13. Dependencies

- Existing: `useModelConfigs`, `modelsApi`, `ModelConfigForm`, `UserManagement`, `useAuthStore`, `theme.ts` utilities
- No new external dependencies required