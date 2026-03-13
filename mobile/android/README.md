# Agentium — Android Client (Kotlin)

> **Status:** Stub project — architecture + API contract defined, native build not yet started.

## Architecture

| Layer       | Technology          | Notes                                             |
|-------------|---------------------|---------------------------------------------------|
| UI          | Jetpack Compose      | Declarative, Material 3 theming                  |
| Navigation  | Navigation Compose   | Single-activity, type-safe routes                |
| Networking  | Retrofit + OkHttp    | All HTTP via `AgentiumApiService`                |
| Push        | FCM (Firebase Cloud Messaging) | Token registered via `/api/v1/mobile/register-device` |
| Auth        | EncryptedSharedPreferences + JWT | Secure token storage, auto-refresh     |
| Offline     | Room Database        | Constitution + task queue cached locally          |
| Voice       | Android SpeechRecognizer | On-device STT, routed to `/api/v1/mobile/voice-command` |

## API Contract (Backend Endpoints)

```
POST   /api/v1/mobile/register-device      — register FCM token
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
# Prerequisites: Android Studio Hedgehog+, JDK 17
# Open this directory as an Android Studio project
# Sync Gradle → Build → Run on emulator or device
```

## Project Structure (Planned)

```
app/src/main/
├── java/com/agentium/
│   ├── AgentiumApp.kt              — Application class (Hilt DI)
│   ├── MainActivity.kt            — Single-activity host
│   ├── ui/
│   │   ├── dashboard/DashboardScreen.kt
│   │   ├── tasks/TaskListScreen.kt
│   │   ├── agents/AgentListScreen.kt
│   │   ├── chat/ChatScreen.kt          — Agent conversational UI
│   │   ├── voting/VotingScreen.kt
│   │   └── settings/SettingsScreen.kt
│   ├── data/
│   │   ├── api/AgentiumApiService.kt   — Retrofit interface
│   │   ├── db/AgentiumDatabase.kt      — Room DB
│   │   └── repository/                  — Repository pattern
│   ├── service/
│   │   ├── FCMService.kt               — Push token refresh
│   │   ├── OfflineSyncWorker.kt        — WorkManager periodic sync
│   │   └── VoiceCommandService.kt
│   └── model/
│       ├── Task.kt
│       ├── Agent.kt
│       └── Vote.kt
└── res/
    └── ...
```

## Notes

- Authentication uses JWT stored in `EncryptedSharedPreferences`.
- FCM token is registered on first launch and refreshed in `FCMService.onNewToken()`.
- Offline mode uses Room DB to cache constitution and task queue; `OfflineSyncWorker` runs a periodic delta sync via `POST /offline/sync`.
- Voice commands use Android's `SpeechRecognizer` API and route to backend.
