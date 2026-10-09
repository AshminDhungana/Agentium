// frontend/src/pages/__tests__/FederationPage.test.tsx
// Behavioral tests for TODO §16.3 (16.3.1 peers display in this block;
// 16.3.2 connection/disconnection and 16.3.3 task status appended by
// later tasks of the implementation plan).

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FederationPage } from '@/pages/FederationPage';
import { showToast } from '@/hooks/useToast';

// ── Shared mutable mock state ─────────────────────────────────────────────────
// vi.hoisted runs before vi.mock factories are hoisted, so the factories
// can close over `state`. Tests mutate `state.user` and per-method vi.fn()s.

const state = vi.hoisted(() => ({
    user: { id: 'u1', name: 'Sovereign', isSovereign: true },
    listPeers: vi.fn(),
    listFederatedTasks: vi.fn(),
    registerPeer: vi.fn(),
    deletePeer: vi.fn(),
    updatePeerTrust: vi.fn(),
    delegateTask: vi.fn(),
}));

vi.mock('@/store/authStore', () => ({
    useAuthStore: () => ({ user: state.user }),
}));

vi.mock('@/hooks/useToast', () => ({
    showToast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock('@/services/federation', async () => {
    // Keep the pure derived helpers real; override only the API methods.
    const actual = await vi.importActual<typeof import('@/services/federation')>('@/services/federation');
    return {
        federationService: {
            ...actual.federationService,
            listPeers: state.listPeers,
            listFederatedTasks: state.listFederatedTasks,
            registerPeer: state.registerPeer,
            deletePeer: state.deletePeer,
            updatePeerTrust: state.updatePeerTrust,
            delegateTask: state.delegateTask,
        },
    };
});

// ── Fixtures ──────────────────────────────────────────────────────────────────

const PEERS = [
    {
        id: 'p1', name: 'Peer Alpha', base_url: 'http://peer-alpha.local',
        status: 'active', trust_level: 'limited', capabilities_shared: ['tasks'],
        last_heartbeat_at: new Date().toISOString(), registered_at: '2026-01-01T00:00:00Z',
    },
    {
        id: 'p2', name: 'Peer Beta', base_url: 'http://peer-beta.local',
        status: 'suspended', trust_level: 'read_only', capabilities_shared: [],
        last_heartbeat_at: null, registered_at: '2026-01-02T00:00:00Z',
    },
];

const TASKS = [
    {
        id: 'f1', original_task_id: 'T0100', local_task_id: 'lt-1',
        source_instance_id: null, target_instance_id: 'p1',
        status: 'completed', direction: 'outgoing',
        delegated_at: '2026-10-09T10:00:00Z', completed_at: '2026-10-09T10:05:00Z',
    },
    {
        id: 'f2', original_task_id: 'T9900',
        source_instance_id: 'ext-1', target_instance_id: null,
        status: 'accepted', direction: 'incoming',
        delegated_at: '2026-10-09T11:00:00Z', completed_at: null,
    },
];

const resetMocks = () => {
    state.user = { id: 'u1', name: 'Sovereign', isSovereign: true };
    vi.clearAllMocks();
    state.listPeers.mockResolvedValue(PEERS);
    state.listFederatedTasks.mockResolvedValue(TASKS);
};

// ── 16.3.1 — displays connected peers ─────────────────────────────────────────

describe('FederationPage — 16.3.1 displays connected peers', () => {
    beforeEach(resetMocks);

    it('renders peer rows with name, URL, trust level and status', async () => {
        render(<FederationPage />);
        const table = await screen.findByLabelText('Registered peer instances');
        const row = within(table).getByText('Peer Alpha').closest('tr')!;
        expect(within(row).getByText('http://peer-alpha.local')).toBeInTheDocument();
        expect(within(row).getByLabelText('Trust level for Peer Alpha')).toHaveValue('limited');
        expect(within(row).getByText('Active')).toBeInTheDocument();
    });

    it('shows the empty state when no peers are registered', async () => {
        state.listPeers.mockResolvedValue([]);
        render(<FederationPage />);
        expect(await screen.findByText('No Peer Instances')).toBeInTheDocument();
    });

    it('filters peers by search query', async () => {
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');
        fireEvent.change(screen.getByLabelText('Search peers'), { target: { value: 'beta' } });
        expect(screen.getByText('Peer Beta')).toBeInTheDocument();
        expect(screen.queryByText('Peer Alpha')).not.toBeInTheDocument();
    });

    it('shows the no-search-results empty state', async () => {
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');
        fireEvent.change(screen.getByLabelText('Search peers'), { target: { value: 'zzz' } });
        expect(screen.getByText('No Peers Found')).toBeInTheDocument();
    });

    it('does not fetch federation data for non-Sovereign users', async () => {
        state.user = { id: 'u2', name: 'Pleb', isSovereign: false };
        render(<FederationPage />);
        expect(screen.getByText('Access Denied')).toBeInTheDocument();
        expect(state.listPeers).not.toHaveBeenCalled();
        expect(state.listFederatedTasks).not.toHaveBeenCalled();
    });
});
