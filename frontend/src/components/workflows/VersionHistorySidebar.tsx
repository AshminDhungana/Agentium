/**
 * @description Sidebar showing version history for a workflow with rollback capability.
 * @example
 * ```tsx
 * import { VersionHistorySidebar } from '@/components/workflows/VersionHistorySidebar';
 *
 * <VersionHistorySidebar workflowId="wf-1" currentVersion={3} onRollback={handleRollback} isExpanded onToggle={toggle} />
 * ```
 * @param {string} props.workflowId - The workflow ID to fetch versions for.
 * @param {number} props.currentVersion - The currently active version number.
 * @param {() => void} props.onRollback - Callback to trigger a rollback.
 * @param {boolean} props.isExpanded - Whether the sidebar is expanded (desktop) or collapsed.
 * @param {() => void} props.onToggle - Callback to toggle sidebar expansion.
 */
import React, { useState, useEffect } from 'react';
import { api } from '@/services/api';
import { showToast } from '@/hooks/useToast';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import {
  History,
  ChevronDown,
  ChevronRight,
  RotateCcw,
  Clock,
  Hash,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

// ── Types ───────────────────────────────────────────────────────────────────

interface WorkflowVersion {
  version: number;
  template_json: unknown;
  created_at: string;
}

interface VersionHistorySidebarProps {
  workflowId: string;
  currentVersion: number;
  onRollback: () => void;
  /** Whether the sidebar is expanded (desktop) or collapsed (tablet) */
  isExpanded: boolean;
  onToggle: () => void;
}

// ── Component ───────────────────────────────────────────────────────────────

export const VersionHistorySidebar: React.FC<VersionHistorySidebarProps> = ({
  workflowId,
  currentVersion,
  onRollback,
  isExpanded,
  onToggle,
}) => {
  const [versions, setVersions] = useState<WorkflowVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedVersion, setExpandedVersion] = useState<number | null>(null);
  const [rolling, setRolling] = useState(false);

  useEffect(() => {
    if (!isExpanded || !workflowId) return;

    setLoading(true);
    api.get(`/api/v1/workflows/${workflowId}/versions`)
      .then(res => setVersions(res.data ?? []))
      .catch(() => showToast.error('Failed to load version history'))
      .finally(() => setLoading(false));
  }, [workflowId, isExpanded, currentVersion]);

  const handleRollback = async (version: number) => {
    if (!window.confirm(`Rollback to version ${version}? This will create a new version.`)) return;
    setRolling(true);
    try {
      await api.post(`/api/v1/workflows/${workflowId}/rollback`, { target_version: version });
      showToast.success(`Rolled back to version ${version}`);
      onRollback();
    } catch {
      showToast.error('Rollback failed');
    } finally {
      setRolling(false);
    }
  };

  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });

  // ── Toggle button (always visible) ────────────────────────────────────────

  if (!isExpanded) {
    return (
      <button
        onClick={onToggle}
        className="
          absolute top-4 right-4 z-10
          flex items-center gap-1.5 px-3 py-2 rounded-xl
          bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535]
          text-gray-600 dark:text-gray-300 text-xs font-medium
          shadow-md hover:shadow-lg transition-all
          hover:border-indigo-300 dark:hover:border-indigo-500/40
        "
        title="Show version history"
      >
        <History className="w-4 h-4 text-indigo-600" />
        <span className="hidden sm:inline">v{currentVersion}</span>
      </button>
    );
  }

  // ── Full sidebar ──────────────────────────────────────────────────────────

  return (
    <div className="w-64 flex-shrink-0 border-l border-gray-200 dark:border-[#1e2535] bg-gray-50/50 dark:bg-[#0f1117]/50 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-[#1e2535]">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-indigo-600" />
          <span className="text-xs font-bold text-gray-600 dark:text-gray-400 uppercase tracking-widest">
            Versions
          </span>
        </div>
        <button
          onClick={onToggle}
          className="p-1 rounded-md text-gray-600 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-200 dark:hover:bg-[#1e2535] transition-colors"
          title="Close version history"
          aria-label="Close version history"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      {/* Version list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <LoadingSpinner size="sm" />
          </div>
        ) : versions.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs text-gray-600 dark:text-gray-500">
            No version history available.
          </div>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
            {versions.map((v) => {
              const isCurrent = v.version === currentVersion;
              const isOpen = expandedVersion === v.version;

              return (
                <div key={v.version} className="group">
                  <button
                    onClick={() => setExpandedVersion(isOpen ? null : v.version)}
                    className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-gray-100 dark:hover:bg-[#1e2535]/50 transition-colors"
                  >
                    <ChevronDown
                      className={`w-3 h-3 text-gray-600 flex-shrink-0 transition-transform ${isOpen ? '' : '-rotate-90'}`}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <Hash className="w-3 h-3 text-gray-600" />
                        <span className="text-sm font-semibold text-gray-900 dark:text-white">
                          v{v.version}
                        </span>
                        {isCurrent && (
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400 uppercase">
                            Current
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1 mt-0.5">
                        <Clock className="w-3 h-3 text-gray-600" />
                        <span className="text-[10px] text-gray-600 dark:text-gray-500">
                          {fmtDate(v.created_at)}
                        </span>
                      </div>
                    </div>
                  </button>

                  {isOpen && (
                    <div className="px-4 pb-3 space-y-2">
                      {/* JSON preview */}
                      <pre className="
                        bg-gray-100 dark:bg-[#0f1117]
                        border border-gray-200 dark:border-[#1e2535]
                        rounded-lg p-3 text-[10px] font-mono
                        text-gray-600 dark:text-gray-400
                        overflow-auto max-h-48
                      ">
                        {JSON.stringify(v.template_json, null, 2)}
                      </pre>

                      {!isCurrent && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleRollback(v.version)}
                          disabled={rolling}
                          className="w-full text-xs border-amber-300 dark:border-amber-500/30 text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-500/10"
                        >
                          <RotateCcw className="w-3 h-3 mr-1.5" />
                          Rollback to v{v.version}
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
