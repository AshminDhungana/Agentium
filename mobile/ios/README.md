# Agentium — iOS Client (Swift)

> **Status:** Stub project — architecture + API contract defined, native build not yet started.

## Architecture

| Layer       | Technology          | Notes                                             |
|-------------|---------------------|---------------------------------------------------|
| UI          | SwiftUI             | Declarative, composable views                     |
| Navigation  | NavigationStack      | iOS 16+ push / modal routing                     |
| Networking  | URLSession + async/await | All HTTP via `AgentiumAPIClient`             |
| Push        | APNs + UserNotifications | Token registered via `/api/v1/mobile/register-device` |
| Auth        | Keychain + JWT       | Secure token storage, auto-refresh               |
| Offline     | Core Data            | Constitution + task queue cached locally          |
| Voice       | SFSpeechRecognizer   | On-device STT, routed to `/api/v1/mobile/voice-command` |

## API Contract (Backend Endpoints)

```
POST   /api/v1/mobile/register-device      — register APNs token
DELETE /api/v1/mobile/register-device/{tok} — unregister token
GET    /api/v1/mobile/dashboard             — condensed dashboard
GET    /api/v1/mobile/tasks                 — paginated task list
GET    /api/v1/mobile/agents                — active agent list
GET    /api/v1/mobile/votes/active          — active votes
GET    /api/v1/mobile/offline/constitution   — offline constitution
GET    /api/v1/mobile/offline/task-queue     — offline task queue
POST   /api/v1/mobile/offline/sync          — delta sync
POST   /api/v1/mobile/voice-command         — voice command bridge
GET    /api/v1/mobile/notifications/preferences
PUT    /api/v1/mobile/notifications/preferences
```

## Build Instructions

```bash
# Prerequisites: Xcode 15+, iOS 17 SDK
open Agentium.xcodeproj
# Select target → iPhone simulator or physical device
# Cmd+R to build & run
```

## Project Structure (Planned)

```
Agentium/
├── App/
│   ├── AgentiumApp.swift          — Entry point
│   └── ContentView.swift          — Root navigation
├── Views/
│   ├── DashboardView.swift
│   ├── TaskListView.swift
│   ├── AgentListView.swift
│   ├── ChatView.swift             — Agent conversational UI
│   ├── VotingView.swift
│   └── SettingsView.swift
├── Services/
│   ├── AgentiumAPIClient.swift    — REST client
│   ├── PushNotificationManager.swift
│   ├── OfflineSyncManager.swift
│   └── VoiceCommandManager.swift
├── Models/
│   ├── Task.swift
│   ├── Agent.swift
│   └── Vote.swift
└── Persistence/
    └── CoreDataStack.swift
```

## Notes

- Authentication uses JWT stored in iOS Keychain.
- Push notification token is registered on first launch and refreshed on every app activation.
- Offline mode caches the constitution and pending task queue; syncs deltas on reconnect via `POST /offline/sync`.
- Voice commands use on-device speech recognition and send transcribed text to the backend.
