@echo off
:: Agentium Voice Bridge - auto-start on Windows login (single trigger)
:: If already installed, do nothing. Otherwise run the bootstrap
:: (which shows the UAC prompt exactly once).
if exist "%USERPROFILE%\.agentium\voice-installed.marker" exit /b 0
start "" /min cmd /c "%USERPROFILE%\.agentium\bootstrap-voice.cmd"
