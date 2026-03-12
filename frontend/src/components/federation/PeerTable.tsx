// src/components/federation/PeerTable.tsx
// Extracted from FederationPage — renders the peers table with:
//  - Inline delete confirmation (replaces window.confirm)
//  - Editable trust-level select per row (uses PATCH /peers/{id}/trust)
//  - Loading skeleton rows
//  - aria-labels on all icon-only buttons
//  - Status + trust badges sourced from statusColors.ts

import { Globe, ExternalLink, Trash2, CheckCircle, AlertTriangle, XCircle, Clock, Loader2 } from 'lucide-react';
import type { PeerInstance, TrustLevel } from '@/services/federation';
import { getPeerStatusColors } from '@/utils/statusColors';
import { federationService } from '@/services/federation';

// ── Props ─────────────────────────────────────────────────────────────────────

interface PeerTableProps {
    /** Already-filtered list of peers to render. */
    peers: PeerInstance[];
    /** Shows skeleton rows while the initial fetch is in flight. */
    isLoading: boolean;
    /** Whether the parent's search bar has an active query (affects empty-state copy). */
    hasSearch: boolean;
    /**
     * ID of the peer currently pending inline delete confirmation.
     * null means no row is in confirm state.
     */
    deletingPeerId: string | null;
    /** Called when the user clicks the trash icon — sets the row into confirm state. */
    onDeleteRequest: (peerId: string) => void;
    /** Called when the user clicks "Confirm" in the inline confirm UI. */
    onDeleteConfirm: (peerId: string) => void;
    /** Called when the user clicks "Cancel" in the inline confirm UI. */
    onDeleteCancel: () => void;
    /** Called when the user changes the trust-level select. */
    onTrustChange: (peerId: string, level: TrustLevel) => void;
}

// ── Helpers (module-scope — not recreated on every render) ────────────────────

function getPeerStatusIcon(status: string) {
    switch (status) {
        case 'active':
            return <CheckCircle className="w-3.5 h-3.5" aria-hidden="true" />;
        case 'suspended':
            return <AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" />;
        case 'inactive':
            return <XCircle className="w-3.5 h-3.5" aria-hidden="true" />;
        default:
            return <Clock className="w-3.5 h-3.5" aria-hidden="true" />;
    }
}

const TRUST_LEVEL_CLASSES: Record<string, string> = {
    full:      'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20',
    limited:   'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20',
    read_only: 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]',
};

function getTrustLevelClasses(level: string): string {
    return TRUST_LEVEL_CLASSES[level] ?? TRUST_LEVEL_CLASSES['read_only'];
}

// ── Skeleton row ──────────────────────────────────────────────────────────────

function SkeletonRow() {
    return (
        <tr className="animate-pulse">
            <td className="px-6 py-4">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-gray-100 dark:bg-[#1e2535]" />
                    <div className="h-4 w-28 rounded bg-gray-100 dark:bg-[#1e2535]" />
                </div>
            </td>
            <td className="px-6 py-4"><div className="h-4 w-48 rounded bg-gray-100 dark:bg-[#1e2535]" /></td>
            <td className="px-6 py-4"><div className="h-5 w-16 rounded-full bg-gray-100 dark:bg-[#1e2535]" /></td>
            <td className="px-6 py-4"><div className="h-5 w-16 rounded-full bg-gray-100 dark:bg-[#1e2535]" /></td>
            <td className="px-6 py-4"><div className="h-4 w-24 rounded bg-gray-100 dark:bg-[#1e2535]" /></td>
            <td className="px-6 py-4"><div className="h-8 w-20 rounded-lg bg-gray-100 dark:bg-[#1e2535] ml-auto" /></td>
        </tr>
    );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function PeerTable({
    peers,
    isLoading,
    hasSearch,
    deletingPeerId,
    onDeleteRequest,
    onDeleteConfirm,
    onDeleteCancel,
    onTrustChange,
}: PeerTableProps) {

    // ── Empty / loading states ────────────────────────────────────────────────

    const isEmpty = !isLoading && peers.length === 0;

    if (isEmpty) {
        return (
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                <div className="p-16 text-center">
                    <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                        <Globe className="w-6 h-6 text-gray-400 dark:text-gray-500" aria-hidden="true" />
                    </div>
                    <p className="text-gray-900 dark:text-white font-medium mb-1">
                        {hasSearch ? 'No Peers Found' : 'No Peer Instances'}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        {hasSearch
                            ? 'Try a different search term.'
                            : 'Add a peer instance to start federation.'}
                    </p>
                </div>
            </div>
        );
    }

    // ── Table ─────────────────────────────────────────────────────────────────

    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
            <div className="overflow-x-auto">
                <table className="w-full" aria-label="Registered peer instances">
                    <thead className="bg-gray-50 dark:bg-[#0f1117]">
                        <tr>
                            <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Peer</th>
                            <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">URL</th>
                            <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Trust Level</th>
                            <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                            <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Last Heartbeat</th>
                            <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                        {isLoading
                            ? Array.from({ length: 3 }, (_, i) => <SkeletonRow key={i} />)
                            : peers.map((peer) => {
                                const statusColors = getPeerStatusColors(peer.status);
                                const isConfirming = deletingPeerId === peer.id;

                                return (
                                    <tr
                                        key={peer.id}
                                        className="hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                    >
                                        {/* Peer name */}
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-3">
                                                <div className="w-9 h-9 rounded-lg bg-indigo-100 dark:bg-indigo-500/10 flex items-center justify-center flex-shrink-0">
                                                    <Globe className="w-4 h-4 text-indigo-600 dark:text-indigo-400" aria-hidden="true" />
                                                </div>
                                                <div>
                                                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                                                        {peer.name}
                                                    </span>
                                                    {peer.capabilities_shared && peer.capabilities_shared.length > 0 && (
                                                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate max-w-[160px]">
                                                            {peer.capabilities_shared.join(', ')}
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                        </td>

                                        {/* URL */}
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-mono text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] px-2 py-0.5 rounded-md max-w-[200px] truncate">
                                                    {peer.base_url}
                                                </span>
                                                <a
                                                    href={peer.base_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    aria-label={`Open ${peer.name} in new tab`}
                                                    className="text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 flex-shrink-0 transition-colors duration-150"
                                                >
                                                    <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                                                </a>
                                            </div>
                                        </td>

                                        {/* Trust level — inline editable select */}
                                        <td className="px-6 py-4">
                                            <select
                                                value={peer.trust_level}
                                                onChange={(e) => onTrustChange(peer.id, e.target.value as TrustLevel)}
                                                aria-label={`Trust level for ${peer.name}`}
                                                className={`text-xs font-medium px-2.5 py-0.5 rounded-full border cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-colors duration-150 ${getTrustLevelClasses(peer.trust_level)}`}
                                            >
                                                <option value="full">full</option>
                                                <option value="limited">limited</option>
                                                <option value="read_only">read_only</option>
                                            </select>
                                        </td>

                                        {/* Status badge */}
                                        <td className="px-6 py-4">
                                            <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full border ${statusColors.badge}`}>
                                                {getPeerStatusIcon(peer.status)}
                                                {statusColors.label}
                                            </span>
                                        </td>

                                        {/* Last heartbeat */}
                                        <td className="px-6 py-4 text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                                            {federationService.formatHeartbeat(peer.last_heartbeat_at)}
                                        </td>

                                        {/* Actions — inline delete confirm */}
                                        <td className="px-6 py-4">
                                            <div className="flex items-center justify-end gap-1.5">
                                                {isConfirming ? (
                                                    <>
                                                        <button
                                                            onClick={() => onDeleteConfirm(peer.id)}
                                                            aria-label={`Confirm removal of ${peer.name}`}
                                                            className="px-2.5 py-1 text-xs font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors duration-150"
                                                        >
                                                            Confirm
                                                        </button>
                                                        <button
                                                            onClick={onDeleteCancel}
                                                            aria-label="Cancel removal"
                                                            className="px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-[#1e2535] hover:bg-gray-50 dark:hover:bg-[#1e2535] rounded-lg transition-colors duration-150"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </>
                                                ) : (
                                                    <button
                                                        onClick={() => onDeleteRequest(peer.id)}
                                                        aria-label={`Remove peer ${peer.name}`}
                                                        className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors duration-150"
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })
                        }
                    </tbody>
                </table>
            </div>
        </div>
    );
}

export default PeerTable;