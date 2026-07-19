import { describe, it, expect } from 'vitest';
import {
  nextPhase, isActive, isConnectingPhase, canReconnect, isGenesisProgress,
  phaseFromGenesisStatus,
} from './connectionPhase';

describe('connectionPhase reducer', () => {
  it('connect start -> connecting', () => {
    expect(nextPhase('offline', { type: 'connect_start' })).toBe('connecting');
  });
  it('system message -> active', () => {
    expect(nextPhase('connecting', { type: 'system' })).toBe('active');
  });
  it('system_not_ready with key -> genesis_running', () => {
    expect(nextPhase('connecting', { type: 'system_not_ready', genesisTriggered: true })).toBe('genesis_running');
  });
  it('system_not_ready without key -> waiting_for_key', () => {
    expect(nextPhase('connecting', { type: 'system_not_ready', genesisTriggered: false })).toBe('waiting_for_key');
  });
  it('poll complete -> connecting', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'complete' })).toBe('connecting');
  });
  it('poll failed -> genesis_failed', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'failed' })).toBe('genesis_failed');
  });
  it('poll running stays genesis_running', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'running' })).toBe('genesis_running');
  });
  it('poll not_started within grace window stays genesis_running (P5)', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'not_started' }, { graceCount: 2 })).toBe('genesis_running');
  });
  it('poll awaiting_name from genesis_running stays genesis_running (todo 4.1)', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'awaiting_name' })).toBe('genesis_running');
  });
  it('poll awaiting_name does not regress an active phase (todo 4.1)', () => {
    expect(nextPhase('active', { type: 'poll', status: 'awaiting_name' })).toBe('active');
    expect(nextPhase('connecting', { type: 'poll', status: 'awaiting_name' })).toBe('connecting');
  });
  it('poll not_started after grace window -> waiting_for_key (P5)', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'not_started' }, { graceCount: 5 })).toBe('waiting_for_key');
  });
  it('notifyApiKeyAdded leaves waiting_for_key -> connecting', () => {
    expect(nextPhase('waiting_for_key', { type: 'notify_key_added' })).toBe('connecting');
  });
  it('socket close from genesis_running stays genesis_running (poll owns reconnect)', () => {
    expect(nextPhase('genesis_running', { type: 'socket_close', code: 1013 })).toBe('genesis_running');
  });
  it('socket close (1000) -> offline', () => {
    expect(nextPhase('active', { type: 'socket_close', code: 1000 })).toBe('offline');
  });
  it('socket close (4001) -> genesis_failed (terminal auth error)', () => {
    expect(nextPhase('connecting', { type: 'socket_close', code: 4001 })).toBe('genesis_failed');
  });
});

describe('derived predicates', () => {
  it('isActive', () => {
    expect(isActive('active')).toBe(true);
    expect(isActive('connecting')).toBe(false);
  });
  it('isConnectingPhase', () => {
    expect(isConnectingPhase('connecting')).toBe(true);
    expect(isConnectingPhase('genesis_running')).toBe(false);
  });
  it('canReconnect only in offline/genesis_failed', () => {
    expect(canReconnect('offline')).toBe(true);
    expect(canReconnect('genesis_failed')).toBe(true);
    expect(canReconnect('connecting')).toBe(false);
    expect(canReconnect('genesis_running')).toBe(false);
  });
  it('isGenesisProgress only in genesis_running', () => {
    expect(isGenesisProgress('genesis_running')).toBe(true);
    expect(isGenesisProgress('genesis_failed')).toBe(false);
  });
  it('phaseFromGenesisStatus maps statuses', () => {
    expect(phaseFromGenesisStatus('complete')).toBe('connecting');
    expect(phaseFromGenesisStatus('failed')).toBe('genesis_failed');
    expect(phaseFromGenesisStatus('running')).toBe('genesis_running');
    expect(phaseFromGenesisStatus('not_started')).toBe('genesis_running');
  });
});
