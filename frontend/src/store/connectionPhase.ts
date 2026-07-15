export type ConnectionPhase =
  | 'offline'
  | 'connecting'
  | 'waiting_for_key'
  | 'genesis_running'
  | 'genesis_failed'
  | 'active';

export type PhaseEvent =
  | { type: 'connect_start' }
  | { type: 'system' }
  | { type: 'system_not_ready'; genesisTriggered: boolean }
  | { type: 'poll'; status: 'complete' | 'failed' | 'running' | 'not_started' }
  | { type: 'notify_key_added' }
  | { type: 'socket_close'; code: number };

export const GENESIS_GRACE_ATTEMPTS = 5;

export interface NextPhaseOpts {
  /** Number of consecutive not_started poll responses so far. */
  graceCount?: number;
}

export function nextPhase(
  current: ConnectionPhase,
  event: PhaseEvent,
  opts: NextPhaseOpts = {},
): ConnectionPhase {
  switch (event.type) {
    case 'connect_start':
      return 'connecting';
    case 'system':
      return 'active';
    case 'system_not_ready':
      return event.genesisTriggered ? 'genesis_running' : 'waiting_for_key';
    case 'poll':
      if (event.status === 'complete') return 'connecting';
      if (event.status === 'failed') return 'genesis_failed';
      if (event.status === 'not_started') {
        const grace = opts.graceCount ?? 0;
        return grace < GENESIS_GRACE_ATTEMPTS ? 'genesis_running' : 'waiting_for_key';
      }
      return 'genesis_running';
    case 'notify_key_added':
      return current === 'waiting_for_key' ? 'connecting' : current;
    case 'socket_close':
      if (event.code === 1013) return current === 'genesis_running' ? 'genesis_running' : current;
      if (event.code === 4001) return 'genesis_failed';
      // 1000 clean close / 1006 lost / default -> offline (reconnect path decides next).
      return 'offline';
  }
}

export function isActive(phase: ConnectionPhase): boolean {
  return phase === 'active';
}
export function isConnectingPhase(phase: ConnectionPhase): boolean {
  return phase === 'connecting';
}
export function isGenesisProgress(phase: ConnectionPhase): boolean {
  return phase === 'genesis_running';
}
export function canReconnect(phase: ConnectionPhase): boolean {
  return phase === 'offline' || phase === 'genesis_failed';
}

export function phaseFromGenesisStatus(
  status: 'complete' | 'failed' | 'running' | 'not_started',
): ConnectionPhase {
  switch (status) {
    case 'complete': return 'connecting';
    case 'failed': return 'genesis_failed';
    case 'running': return 'genesis_running';
    case 'not_started': return 'genesis_running'; // grace window handled by store
  }
}
