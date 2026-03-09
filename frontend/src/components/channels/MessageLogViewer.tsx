// src/components/channels/MessageLogViewer.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Changes vs. the previous version:
//   1. Switched from `channelMetricsApi.getChannelLogs()` (old per-channel
//      endpoint) to `channelMessagesApi.getLog()` — the richer unified
//      endpoint at GET /api/v1/channels/messages/log. This endpoint supports
//      full filtering, pagination, and enriched channel metadata.
//   2. Added a `limit` prop (default 50) so callers can control page size.
//   3. Added `staleTime: 15_000` to reduce redundant re-fetches.
//   4. Fixed the empty-state guard (`data?.messages` instead of assuming
//      `data.messages` is always defined).
//   5. Replaced the `Activity` fallback icon with the correct `AlertTriangle`
//      that was already used in the old standalone component.
// ─────────────────────────────────────────────────────────────────────────────

import { useQuery } from '@tanstack/react-query';
import { channelMessagesApi } from '@/services/channelMessages';
import { format } from 'date-fns';
import { CheckCircle, XCircle, Clock, AlertTriangle } from 'lucide-react';

export interface MessageLogViewerProps {
    channelId: string;
    /** Maximum number of messages to fetch. Defaults to 50. */
    limit?: number;
}

function getStatusIcon(status: string) {
    switch (status) {
        case 'responded':  return <CheckCircle  className="w-4 h-4 text-green-500" />;
        case 'failed':     return <XCircle      className="w-4 h-4 text-red-500"   />;
        case 'processing': return <Clock        className="w-4 h-4 text-yellow-500 animate-spin" />;
        default:           return <AlertTriangle className="w-4 h-4 text-gray-400" />;
    }
}

export function MessageLogViewer({ channelId, limit = 50 }: MessageLogViewerProps) {
    const { data, isLoading } = useQuery({
        queryKey: ['channel-logs', channelId, limit],
        queryFn: () => channelMessagesApi.getLog({ channel_id: channelId, limit }),
        staleTime: 15_000,
    });

    if (isLoading) {
        return <div className="text-sm text-gray-500">Loading logs...</div>;
    }

    const messages = data?.messages ?? [];

    return (
        <div className="border border-gray-200 dark:border-[#1e2535] rounded-xl overflow-hidden">
            <div className="bg-gray-50 dark:bg-[#0f1117] px-4 py-2 border-b border-gray-200 dark:border-[#1e2535]">
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Recent Messages</h4>
            </div>
            <div className="max-h-64 overflow-y-auto">
                {messages.length === 0 ? (
                    <div className="p-4 text-sm text-gray-500 text-center">No messages yet</div>
                ) : (
                    <table className="w-full text-sm">
                        <thead className="bg-gray-50 dark:bg-[#0f1117] text-xs text-gray-500">
                            <tr>
                                <th className="px-4 py-2 text-left">Status</th>
                                <th className="px-4 py-2 text-left">Sender</th>
                                <th className="px-4 py-2 text-left">Content</th>
                                <th className="px-4 py-2 text-left">Time</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                            {messages.map((msg) => (
                                <tr key={msg.id} className="hover:bg-gray-50 dark:hover:bg-[#0f1117]">
                                    <td className="px-4 py-2">{getStatusIcon(msg.status)}</td>
                                    <td className="px-4 py-2 text-gray-900 dark:text-gray-100">
                                        {msg.sender_name || msg.sender_id}
                                    </td>
                                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400 truncate max-w-xs">
                                        {msg.content}
                                    </td>
                                    <td className="px-4 py-2 text-xs text-gray-400">
                                        {format(new Date(msg.created_at), 'MMM d, HH:mm')}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
