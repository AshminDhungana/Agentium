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

// ── 16.3.2 — peer connection/disconnection ───────────────────────────────────

describe('FederationPage — 16.3.2 peer connection/disconnection', () => {
    beforeEach(resetMocks);

    it('registers a new peer through the Add Peer modal', async () => {
        state.registerPeer.mockResolvedValue(PEERS[0]);
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');

        fireEvent.click(screen.getByRole('button', { name: 'Add new peer instance' }));
        fireEvent.change(screen.getByLabelText('Peer Name'), { target: { value: 'Peer Gamma' } });
        fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'http://peer-gamma.local' } });
        fireEvent.change(screen.getByLabelText('Shared Secret'), { target: { value: 's3cret' } });
        fireEvent.change(screen.getByLabelText(/Capabilities/), { target: { value: 'tasks' } });
        fireEvent.click(screen.getByRole('button', { name: 'Add Peer' }));

        await waitFor(() => expect(state.registerPeer).toHaveBeenCalledTimes(1));
        expect(state.registerPeer).toHaveBeenCalledWith(expect.objectContaining({
            name: 'Peer Gamma',
            base_url: 'http://peer-gamma.local',
            shared_secret: 's3cret',
            trust_level: 'limited',
            capabilities: ['tasks'],
        }));
        // list refreshed after successful registration
        expect(state.listPeers.mock.calls.length).toBeGreaterThanOrEqual(2);
    });

    it('shows an error toast and keeps the modal open when registration fails', async () => {
        state.registerPeer.mockRejectedValue(new Error('Failed to register peer: boom'));
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');

        fireEvent.click(screen.getByRole('button', { name: 'Add new peer instance' }));
        fireEvent.change(screen.getByLabelText('Peer Name'), { target: { value: 'Peer Gamma' } });
        fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'http://peer-gamma.local' } });
        fireEvent.change(screen.getByLabelText('Shared Secret'), { target: { value: 's3cret' } });
        fireEvent.click(screen.getByRole('button', { name: 'Add Peer' }));

        await waitFor(() => expect(vi.mocked(showToast.error)).toHaveBeenCalledWith('Failed to register peer: boom'));
        // modal stays open for a retry
        expect(screen.getByLabelText('Peer Name')).toBeInTheDocument();
    });

    it('removes a peer via the inline delete confirmation', async () => {
        state.deletePeer.mockResolvedValue(undefined);
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');

        fireEvent.click(screen.getByRole('button', { name: 'Remove peer Peer Alpha' }));
        fireEvent.click(screen.getByRole('button', { name: 'Confirm removal of Peer Alpha' }));

        await waitFor(() => expect(state.deletePeer).toHaveBeenCalledWith('p1'));
    });

    it('cancelling the inline delete leaves the peer in place', async () => {
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');

        fireEvent.click(screen.getByRole('button', { name: 'Remove peer Peer Alpha' }));
        fireEvent.click(screen.getByRole('button', { name: 'Cancel removal' }));

        expect(state.deletePeer).not.toHaveBeenCalled();
        expect(screen.getByText('Peer Alpha')).toBeInTheDocument();
    });

    it('updates a peer trust level from the row select', async () => {
        state.updatePeerTrust.mockResolvedValue(PEERS[0]);
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');

        fireEvent.change(screen.getByLabelText('Trust level for Peer Alpha'), { target: { value: 'full' } });

        await waitFor(() => expect(state.updatePeerTrust).toHaveBeenCalledWith('p1', 'full'));
    });
});

// ── 16.3.3 — cross-instance task status ───────────────────────────────────────

describe('FederationPage — 16.3.3 cross-instance task status', () => {
    beforeEach(resetMocks);

    const openTasksTab = async () => {
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');
        fireEvent.click(screen.getByRole('tab', { name: /Delegated Tasks/ }));
    };

    it('lists federated tasks with status badges, direction and completion time', async () => {
        await openTasksTab();
        const list = screen.getByLabelText('Federated task list');

        expect(within(list).getByText('T0100')).toBeInTheDocument();
        expect(within(list).getByText('T9900')).toBeInTheDocument();
        expect(within(list).getByText('Completed')).toBeInTheDocument();
        expect(within(list).getByText('Accepted')).toBeInTheDocument();
        // Direction text lives inside a <p> with the date, so match by substring
        expect(within(list).getByText(/↑ Outgoing/)).toBeInTheDocument();
        expect(within(list).getByText(/↓ Incoming/)).toBeInTheDocument();
    });

    it('shows the empty state when there are no federated tasks', async () => {
        state.listFederatedTasks.mockResolvedValue([]);
        await openTasksTab();
        expect(await screen.findByText('No Delegated Tasks')).toBeInTheDocument();
    });

    it('disables Delegate Task when there are no active peers', async () => {
        state.listPeers.mockResolvedValue([PEERS[1]]); // suspended peer only
        render(<FederationPage />);
        await screen.findByText('Peer Beta'); // the only peer in this fixture
        fireEvent.click(screen.getByRole('tab', { name: /Delegated Tasks/ }));
        expect(screen.getByRole('button', { name: 'Delegate a task to a peer' })).toBeDisabled();
    });

    it('delegates a task through the modal', async () => {
        state.delegateTask.mockResolvedValue({ id: 'f9', status: 'pending', message: 'queued' });
        await openTasksTab();

        fireEvent.click(screen.getByRole('button', { name: 'Delegate a task to a peer' }));
        fireEvent.change(screen.getByLabelText('Target Peer'), { target: { value: 'p1' } });
        fireEvent.change(screen.getByLabelText('Original Task ID'), { target: { value: 'T0100' } });
        fireEvent.change(screen.getByLabelText(/Payload/), { target: { value: '{"title": "hello"}' } });
        fireEvent.click(screen.getByRole('button', { name: 'Delegate' }));

        await waitFor(() => expect(state.delegateTask).toHaveBeenCalledWith({
            target_peer_id: 'p1',
            original_task_id: 'T0100',
            payload: { title: 'hello' },
        }));
    });
});
