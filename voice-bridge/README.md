# Agentium Voice Bridge

Real-time voice communication bridge for Agentium. Runs on the host machine (outside Docker) and connects to the Agentium backend for STT, chat, and TTS.

## Components

- `main.py` — Core voice bridge: wake-word detection, microphone capture, STT relay, TTS playback, session management, WebSocket server for browser sync
- `ui/` — Desktop HUD companion app (PySide6 + QML): system tray icon, circular waveform overlay, speaking indicator

## Running the Desktop UI

```bash
pip install -r requirements-ui.txt
python run_voice_ui.py
```

Requires PySide6 >= 6.5. The UI auto-connects to the bridge WebSocket at ws://127.0.0.1:9999.

## Cross-Platform Notes

- **Windows:** Tested on Windows 10/11. DWM Acrylic glass effect applied automatically.
- **macOS:** Tested on macOS 12+. NSVisualEffectView glass effect applied automatically.
- **Linux:** Uses Qt Quick MultiEffect as blur fallback. Requires compositor with XDG Shell.
