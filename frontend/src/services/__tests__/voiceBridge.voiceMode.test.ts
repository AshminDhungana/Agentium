import { voiceBridgeService, VoiceMode } from '@/services/voiceBridge';

describe('VoiceBridgeService.voiceMode', () => {
  beforeEach(() => {
    voiceBridgeService.disconnect();
    (voiceBridgeService as any)._voiceMode = 'system';
  });

  test('default voiceMode is "system"', () => {
    expect(voiceBridgeService.voiceMode).toBe('system');
  });

  test('setVoiceMode updates voiceMode', () => {
    voiceBridgeService.setVoiceMode('chat');
    expect(voiceBridgeService.voiceMode).toBe('chat');

    voiceBridgeService.setVoiceMode('popup');
    expect(voiceBridgeService.voiceMode).toBe('popup');

    voiceBridgeService.setVoiceMode('system');
    expect(voiceBridgeService.voiceMode).toBe('system');
  });

  test('setVoiceMode no-op when same mode', () => {
    voiceBridgeService.setVoiceMode('chat');
    const first = voiceBridgeService.voiceMode;
    voiceBridgeService.setVoiceMode('chat');
    expect(voiceBridgeService.voiceMode).toBe(first);
  });
});