/**
 * ToolMarketplacePage.tsx
 * Full frontend coverage for all tool-management routes in tool_creation.py
 *
 * Changes from original:
 *  - useApi hook: stale-closure bug fixed via useRef for fn identity
 *  - callApi inline wrapper removed; toolManagementApi from plugins.ts used instead
 *  - msg string state replaced with react-hot-toast (consistent app-wide UX)
 *  - Per-button pendingAction loading state added to every mutating button
 *  - Inline confirmation step added for destructive actions (yank, deprecate,
 *    execute sunset, rollback)
 *  - Search debounce (300 ms) added to MarketplaceTab
 *  - Pagination auto-resets to page 1 on search/category change
 *  - Analytics days state split per sub-section (report / errors / agent / tool)
 *  - StatusPill and StarRating wrapped in React.memo
 *  - Missing aria-label attributes filled in
 *  - FinalizeImport now sends listing_id alongside staging_id (backend fix)
 *  - Empty-state messages added when lists return zero rows
 *  - Full TypeScript types from toolManagement.ts used throughout
 */

import React, { useState, useEffect, useCallback, useRef } from "react";
import { showToast } from '@/hooks/useToast';
import {
  Search,
  Package,
  Star,
  Download,
  Trash2,
  AlertTriangle,
  CheckCircle,
  Clock,
  BarChart3,
  Plus,
  Play,
  RotateCcw,
  GitCommit,
  GitBranch,
  History,
  Activity,
  Terminal,
  Code2,
  Users,
  RefreshCw,
  } from "lucide-react";

import { toolManagementApi } from "../services/plugins";
import type {
  MarketplaceListing,
  ToolItem,
  ToolVersionRecord,
  AnalyticsReport,
  ToolStats,
  ErrorRecord,
  AgentUsageResponse,
  VoteChoice,
} from "../types/toolManagement";
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ── Shared input className ────────────────────────────────────────────────────
const INPUT =
  "w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all";

const INPUT_SM =
  "px-3 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400";

// ── Shared sub-components ─────────────────────────────────────────────────────

const StatusPill = React.memo(function StatusPill({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    active:
      "bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20",
    pending:
      "bg-yellow-100 dark:bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/20",
    deprecated:
      "bg-orange-100 dark:bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-500/20",
    sunset:
      "bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20",
    voting:
      "bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-500/20",
    yanked:
      "bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20",
    staged:
      "bg-purple-100 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-200 dark:border-purple-500/20",
  };
  const cls =
    colorMap[status] ??
    "bg-gray-100 dark:bg-gray-500/10 text-gray-700 dark:text-gray-400 border-gray-200 dark:border-gray-500/20";
  return (
    <span className={`px-2.5 py-1 text-xs font-medium rounded-full border ${cls}`}>
      {status}
    </span>
  );
});

const StarRating = React.memo(function StarRating({
  value,
  onChange,
}: {
  value: number;
  onChange?: (v: number) => void;
}) {
  return (
    <span className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((s) => (
        <span
          key={s}
          onClick={() => onChange?.(s)}
          className={`text-lg ${onChange ? "cursor-pointer" : "cursor-default"} ${
            s <= value ? "text-yellow-500" : "text-gray-300 dark:text-gray-600"
          }`}
        >
          ★
        </span>
      ))}
    </span>
  );
});

function JsonBox({ data }: { data: unknown }) {
  return (
    <pre className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg p-4 text-xs overflow-auto whitespace-pre-wrap text-gray-700 dark:text-gray-300 font-mono">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="py-10 text-center text-sm text-gray-400 dark:text-gray-500">
      {message}
    </div>
  );
}

/** Inline confirm row rendered below a destructive button. */
function ConfirmRow({
  label,
  onConfirm,
  onCancel,
  isPending,
}: {
  label: string;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  return (
    <div className="flex items-center gap-2 mt-2 p-3 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
      <span className="text-xs text-red-700 dark:text-red-300 flex-1">
        This action is permanent. Are you sure?
      </span>
      <button
        onClick={onCancel}
        className="px-3 py-1 text-xs rounded-md bg-gray-100 dark:bg-[#1e2535] text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-[#2a3347] transition-colors"
      >
        Cancel
      </button>
      <button
        onClick={onConfirm}
        disabled={isPending}
        className="px-3 py-1 text-xs rounded-md bg-red-600 hover:bg-red-700 text-white disabled:opacity-50 flex items-center gap-1 transition-colors"
      >
        {isPending && <LoadingSpinner size="xs" />}
        {label}
      </button>
    </div>
  );
}

// ── Fixed useApi hook ─────────────────────────────────────────────────────────
//
// Original had a stale-closure bug: fn was captured at hook creation and never
// updated because it wasn't listed in the useCallback deps.  We now store the
// latest fn in a ref so the stable `run` callback always calls the current fn.

function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Always holds the latest version of fn without changing run's identity.
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fnRef.current());
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (e as Error)?.message ??
        "Unknown error";
      setError(msg);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
  }, [run]);

  return { data, loading, error, refresh: run };
}

// ═══════════════════════════════════════════════════════════════
// TAB 1 — Marketplace
// ═══════════════════════════════════════════════════════════════
function MarketplaceTab() {
  // Search input is debounced 300 ms before it drives the browse call.
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<{
    total: number;
    listings?: MarketplaceListing[];
    tools?: MarketplaceListing[];
  } | null>(null);
  const [browsing, setBrowsing] = useState(false);

  // Publish form
  const [pub, setPub] = useState({ tool_name: "", display_name: "", category: "", tags: "" });
  // Rate
  const [rateId, setRateId] = useState("");
  const [rateVal, setRateVal] = useState(4);
  // Yank — with confirm step
  const [yankId, setYankId] = useState("");
  const [yankReason, setYankReason] = useState("");
  const [yankConfirm, setYankConfirm] = useState(false);
  // Import
  const [listingId, setListingId] = useState("");
  const [stagingId, setStagingId] = useState("");
  const [finalizeListingId, setFinalizeListingId] = useState("");

  // Per-button pending tracking
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  // Debounce searchInput → search, reset page to 1
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Reset page when category changes
  useEffect(() => {
    setPage(1);
  }, [category]);

  const browse = useCallback(async () => {
    setBrowsing(true);
    try {
      const data = await toolManagementApi.browseMarketplace({
        page,
        page_size: 12,
        ...(search ? { search } : {}),
        ...(category ? { category } : {}),
      });
      setResult(data);
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (e as Error)?.message ??
        "Browse failed";
      showToast.error(msg);
    }
    setBrowsing(false);
  }, [search, category, page]);

  useEffect(() => {
    browse();
  }, [browse]);

  const act = async (key: string, fn: () => Promise<unknown>, successMsg: string) => {
    setPendingAction(key);
    try {
      await fn();
      showToast.success(successMsg);
      browse();
    } catch (e: unknown) {
      showToast.error(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          `${key} failed`,
      );
    } finally {
      setPendingAction(null);
    }
  };

  const listings = result?.listings ?? result?.tools ?? [];

  return (
    <div className="space-y-6">
      {/* Browse */}
      <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
            <Search className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          </div>
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">Browse Marketplace</h3>
        </div>

        <div className="flex gap-3 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
            <input
              aria-label="Search marketplace"
              className="w-full pl-10 pr-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
              placeholder="Search tools…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>
          <input
            aria-label="Category filter"
            className="w-48 px-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
            placeholder="Category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
          <button
            onClick={browse}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
          >
            Search
          </button>
        </div>

        {browsing && <div className="text-gray-500 dark:text-gray-400 text-sm">Loading…</div>}

        {result && !browsing && (
          <>
            <div className="text-gray-500 dark:text-gray-400 text-xs mb-4">
              {result.total ?? listings.length} listing(s) · page {page}
            </div>

            {listings.length === 0 ? (
              <EmptyState message="No listings found. Try a different search or category." />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {listings.map((l) => (
                  <div
                    key={l.id ?? l.tool_name}
                    className="bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-200 dark:border-[#2a3347] p-4 hover:border-gray-300 dark:hover:border-[#3a4357] transition-all"
                  >
                    <div className="flex justify-between items-start mb-2">
                      <span className="font-semibold text-gray-900 dark:text-white">
                        {l.display_name ?? l.tool_name}
                      </span>
                      <StatusPill status={l.status ?? "active"} />
                    </div>
                    <div className="text-gray-500 dark:text-gray-400 text-xs mb-2">
                      {l.category} · {(l.tags ?? []).join(", ")}
                    </div>
                    <StarRating value={Math.round(l.average_rating ?? 0)} />
                    <div className="text-gray-500 dark:text-gray-400 text-xs mt-2">
                      {l.download_count ?? 0} imports
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="flex gap-3 mt-4 items-center">
              <button
                onClick={() => setPage((p) => p - 1)}
                disabled={page <= 1}
                className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                ← Prev
              </button>
              <span className="text-gray-500 dark:text-gray-400 text-xs">Page {page}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={listings.length < 12}
                className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next →
              </button>
            </div>
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Publish */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
              <Plus className="w-4 h-4 text-green-600 dark:text-green-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Publish Tool</h3>
          </div>

          <div className="space-y-4">
            {(
              [
                ["tool_name", "Tool Name"],
                ["display_name", "Display Name"],
                ["category", "Category"],
              ] as const
            ).map(([k, label]) => (
              <div key={k}>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  {label}
                </label>
                <input
                  aria-label={label}
                  className={INPUT}
                  value={pub[k]}
                  onChange={(e) => setPub((p) => ({ ...p, [k]: e.target.value }))}
                />
              </div>
            ))}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Tags (comma-separated)
              </label>
              <input
                aria-label="Tags (comma-separated)"
                className={INPUT}
                value={pub.tags}
                onChange={(e) => setPub((p) => ({ ...p, tags: e.target.value }))}
              />
            </div>
            <button
              disabled={pendingAction === "Publish"}
              onClick={() =>
                act(
                  "Publish",
                  () =>
                    toolManagementApi.publishTool({
                      ...pub,
                      tags: pub.tags
                        .split(",")
                        .map((t) => t.trim())
                        .filter(Boolean),
                    }),
                  "Tool published successfully",
                )
              }
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {pendingAction === "Publish" && <LoadingSpinner size="sm" />}
              Publish →
            </button>
          </div>
        </div>

        {/* Import */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
              <Download className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Import from Marketplace</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Listing ID
              </label>
              <input
                aria-label="Listing ID"
                className={INPUT}
                value={listingId}
                onChange={(e) => setListingId(e.target.value)}
                placeholder="listing-uuid"
              />
            </div>
            <button
              disabled={pendingAction === "StageImport"}
              onClick={() =>
                act("StageImport", () => toolManagementApi.stageImport(listingId), "Import staged — await council approval")
              }
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {pendingAction === "StageImport" && <LoadingSpinner size="sm" />}
              Stage Import
            </button>

            <div className="border-t border-gray-200 dark:border-[#1e2535] pt-4 space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Listing ID (to finalize)
                </label>
                <input
                  aria-label="Listing ID to finalize"
                  className={INPUT}
                  value={finalizeListingId}
                  onChange={(e) => setFinalizeListingId(e.target.value)}
                  placeholder="listing-uuid"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Staging ID (to finalize)
                </label>
                <input
                  aria-label="Staging ID to finalize"
                  className={INPUT}
                  value={stagingId}
                  onChange={(e) => setStagingId(e.target.value)}
                  placeholder="staging-uuid"
                />
              </div>
              <button
                disabled={pendingAction === "FinalizeImport"}
                onClick={() =>
                  act(
                    "FinalizeImport",
                    () =>
                      toolManagementApi.finalizeImport({
                        listing_id: finalizeListingId,
                        staging_id: stagingId,
                      }),
                    "Import finalized",
                  )
                }
                className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {pendingAction === "FinalizeImport" && <LoadingSpinner size="sm" />}
                Finalize Import ✓
              </button>
            </div>
          </div>
        </div>

        {/* Rate */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center">
              <Star className="w-4 h-4 text-yellow-600 dark:text-yellow-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Rate a Listing</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Listing ID
              </label>
              <input
                aria-label="Listing ID to rate"
                className={INPUT}
                value={rateId}
                onChange={(e) => setRateId(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Rating
              </label>
              <div className="flex items-center gap-3">
                <StarRating value={rateVal} onChange={setRateVal} />
                <span className="text-gray-500 dark:text-gray-400 text-sm">{rateVal} / 5</span>
              </div>
            </div>
            <button
              disabled={pendingAction === "Rate"}
              onClick={() =>
                act("Rate", () => toolManagementApi.rateTool(rateId, { rating: rateVal }), "Rating submitted")
              }
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {pendingAction === "Rate" && <LoadingSpinner size="sm" />}
              Submit Rating
            </button>
          </div>
        </div>

        {/* Yank — with confirmation */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
              <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Yank Listing</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Listing ID
              </label>
              <input
                aria-label="Listing ID to yank"
                className={INPUT}
                value={yankId}
                onChange={(e) => setYankId(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Reason
              </label>
              <input
                aria-label="Reason for yanking"
                className={INPUT}
                value={yankReason}
                onChange={(e) => setYankReason(e.target.value)}
              />
            </div>

            {!yankConfirm ? (
              <button
                onClick={() => setYankConfirm(true)}
                className="w-full px-4 py-2 bg-red-600 hover:bg-red-700 dark:hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                Yank Listing ✗
              </button>
            ) : (
              <ConfirmRow
                label="Confirm Yank"
                isPending={pendingAction === "Yank"}
                onCancel={() => setYankConfirm(false)}
                onConfirm={() => {
                  setYankConfirm(false);
                  act("Yank", () => toolManagementApi.yankTool(yankId, { reason: yankReason }), "Listing yanked");
                }}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB 2 — Tools
// ═══════════════════════════════════════════════════════════════
function ToolsTab() {
  const [statusFilter, setStatusFilter] = useState("");
  const { data: toolsData, loading, refresh } = useApi(
    () => toolManagementApi.listTools(statusFilter || undefined),
    [statusFilter],
  );

  const [propose, setPropose] = useState({
    name: "",
    description: "",
    code: "",
    created_by_agentium_id: "",
    authorized_tiers: "",
  });
  const [vote, setVote] = useState({ tool_name: "", vote: "for" as VoteChoice });
  const [exec, setExec] = useState({ tool_name: "", kwargs: "", task_id: "" });
  const [dep, setDep] = useState({
    tool_name: "",
    reason: "",
    replacement: "",
    sunset_days: "",
  });
  const [depConfirm, setDepConfirm] = useState(false);
  const [restore, setRestore] = useState({ tool_name: "", reason: "" });
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const act = async (key: string, fn: () => Promise<unknown>, successMsg: string) => {
    setPendingAction(key);
    try {
      await fn();
      showToast.success(successMsg);
      refresh();
    } catch (e: unknown) {
      showToast.error(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          `${key} failed`,
      );
    } finally {
      setPendingAction(null);
    }
  };

  const rows: ToolItem[] = toolsData?.tools
    ? toolsData.tools
    : Array.isArray(toolsData)
    ? (toolsData as ToolItem[])
    : [];

  return (
    <div className="space-y-6">
      {/* Tool list */}
      <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
              <Package className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">All Tools</h3>
          </div>
          <div className="flex gap-3">
            <select
              aria-label="Status filter"
              className={INPUT_SM}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All statuses</option>
              {["active", "pending", "deprecated", "sunset", "voting"].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <button
              aria-label="Refresh tools"
              onClick={refresh}
              className="px-3 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {loading && <div className="text-gray-500 dark:text-gray-400 text-sm">Loading…</div>}

        {!loading && rows.length === 0 && (
          <EmptyState message="No tools found." />
        )}

        {rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-gray-500 dark:text-gray-400 text-left border-b border-gray-200 dark:border-[#1e2535]">
                  {["Name", "Description", "Status", "Version", "Tiers", "Actions"].map((h) => (
                    <th key={h} className="py-3 px-2 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const name = row.tool_name ?? row.name ?? "";
                  return (
                    <tr
                      key={name}
                      className="border-b border-gray-100 dark:border-[#1e2535] hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors"
                    >
                      <td className="py-3 px-2 font-semibold text-gray-900 dark:text-white">
                        {name}
                      </td>
                      <td className="py-3 px-2 text-gray-500 dark:text-gray-400 max-w-xs truncate">
                        {row.description ?? "—"}
                      </td>
                      <td className="py-3 px-2">
                        <StatusPill status={row.status ?? "active"} />
                      </td>
                      <td className="py-3 px-2 text-gray-500 dark:text-gray-400">
                        v{row.version ?? row.current_version ?? 1}
                      </td>
                      <td className="py-3 px-2 text-gray-500 dark:text-gray-400 text-xs">
                        {(row.authorized_tiers ?? []).join(", ")}
                      </td>
                      <td className="py-3 px-2">
                        <button
                          onClick={() => setExec((x) => ({ ...x, tool_name: name }))}
                          className="px-3 py-1.5 text-xs font-medium bg-gray-100 dark:bg-[#1e2535] text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-[#2a3347] rounded-lg transition-colors"
                        >
                          Run
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Propose */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
              <Plus className="w-4 h-4 text-green-600 dark:text-green-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Propose New Tool</h3>
          </div>

          <div className="space-y-4">
            {(
              [
                ["name", "Tool Name"],
                ["description", "Description"],
                ["created_by_agentium_id", "Agent ID"],
                ["authorized_tiers", "Authorized Tiers (comma)"],
              ] as const
            ).map(([k, label]) => (
              <div key={k}>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  {label}
                </label>
                <input
                  aria-label={label}
                  className={INPUT}
                  value={propose[k]}
                  onChange={(e) => setPropose((p) => ({ ...p, [k]: e.target.value }))}
                />
              </div>
            ))}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Code
              </label>
              <textarea
                aria-label="Tool code"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all resize-none font-mono"
                rows={4}
                value={propose.code}
                onChange={(e) => setPropose((p) => ({ ...p, code: e.target.value }))}
                placeholder="def my_tool(...): ..."
              />
            </div>
            <button
              disabled={pendingAction === "Propose"}
              onClick={() =>
                act(
                  "Propose",
                  () =>
                    toolManagementApi.proposeTool({
                      name: propose.name,
                      description: propose.description,
                      code: propose.code,
                      created_by_agentium_id: propose.created_by_agentium_id,
                      authorized_tiers: propose.authorized_tiers
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    }),
                  "Tool proposed",
                )
              }
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {pendingAction === "Propose" && <LoadingSpinner size="sm" />}
              Propose Tool
            </button>
          </div>
        </div>

        {/* Vote */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center">
              <Users className="w-4 h-4 text-yellow-600 dark:text-yellow-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Vote on Proposal</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Tool Name
              </label>
              <input
                aria-label="Tool name to vote on"
                className={INPUT}
                value={vote.tool_name}
                onChange={(e) => setVote((v) => ({ ...v, tool_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Vote
              </label>
              <div className="flex gap-2">
                {(["for", "against", "abstain"] as VoteChoice[]).map((v) => (
                  <button
                    key={v}
                    onClick={() => setVote((x) => ({ ...x, vote: v }))}
                    className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      vote.vote === v
                        ? "bg-blue-600 text-white"
                        : "bg-gray-100 dark:bg-[#1e2535] text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-[#2a3347]"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <button
              disabled={pendingAction === "Vote"}
              onClick={() =>
                act(
                  "Vote",
                  () => toolManagementApi.voteOnTool(vote.tool_name, { vote: vote.vote }),
                  "Vote cast",
                )
              }
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {pendingAction === "Vote" && <LoadingSpinner size="sm" />}
              Cast Vote
            </button>
          </div>
        </div>

        {/* Execute */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
              <Play className="w-4 h-4 text-green-600 dark:text-green-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Execute Tool</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Tool Name
              </label>
              <input
                aria-label="Tool name to execute"
                className={INPUT}
                value={exec.tool_name}
                onChange={(e) => setExec((x) => ({ ...x, tool_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                kwargs (JSON)
              </label>
              <textarea
                aria-label="Tool kwargs JSON"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all resize-none font-mono"
                rows={3}
                value={exec.kwargs}
                onChange={(e) => setExec((x) => ({ ...x, kwargs: e.target.value }))}
                placeholder='{"param":"value"}'
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Task ID (optional)
              </label>
              <input
                aria-label="Task ID"
                className={INPUT}
                value={exec.task_id}
                onChange={(e) => setExec((x) => ({ ...x, task_id: e.target.value }))}
              />
            </div>
            <button
              disabled={pendingAction === "Execute"}
              onClick={() =>
                act(
                  "Execute",
                  () =>
                    toolManagementApi.executeTool(exec.tool_name, {
                      kwargs: exec.kwargs ? JSON.parse(exec.kwargs) : {},
                      task_id: exec.task_id || undefined,
                    }),
                  "Tool executed",
                )
              }
              className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {pendingAction === "Execute" && <LoadingSpinner size="sm" />}
              ▶ Execute
            </button>
          </div>
        </div>

        {/* Deprecate — with confirmation */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
              <AlertTriangle className="w-4 h-4 text-orange-600 dark:text-orange-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Deprecate Tool</h3>
          </div>

          <div className="space-y-4">
            {(
              [
                ["tool_name", "Tool Name"],
                ["reason", "Reason"],
                ["replacement", "Replacement Tool (optional)"],
              ] as const
            ).map(([k, label]) => (
              <div key={k}>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  {label}
                </label>
                <input
                  aria-label={label}
                  className={INPUT}
                  value={dep[k]}
                  onChange={(e) => setDep((d) => ({ ...d, [k]: e.target.value }))}
                />
              </div>
            ))}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Sunset Days (optional)
              </label>
              <input
                aria-label="Sunset days"
                type="number"
                className={INPUT}
                value={dep.sunset_days}
                onChange={(e) => setDep((d) => ({ ...d, sunset_days: e.target.value }))}
              />
            </div>

            {!depConfirm ? (
              <button
                onClick={() => setDepConfirm(true)}
                className="w-full px-4 py-2 bg-orange-600 hover:bg-orange-700 dark:hover:bg-orange-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                ⚠ Deprecate
              </button>
            ) : (
              <ConfirmRow
                label="Confirm Deprecate"
                isPending={pendingAction === "Deprecate"}
                onCancel={() => setDepConfirm(false)}
                onConfirm={() => {
                  setDepConfirm(false);
                  act(
                    "Deprecate",
                    () =>
                      toolManagementApi.deprecateTool(dep.tool_name, {
                        reason: dep.reason,
                        replacement_tool_name: dep.replacement || undefined,
                        sunset_days: dep.sunset_days ? Number(dep.sunset_days) : undefined,
                      }),
                    "Tool deprecated",
                  );
                }}
              />
            )}
          </div>

          <div className="border-t border-gray-200 dark:border-[#1e2535] mt-6 pt-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-8 h-8 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                <RotateCcw className="w-4 h-4 text-green-600 dark:text-green-400" />
              </div>
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">Restore Tool</h3>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Tool Name
                </label>
                <input
                  aria-label="Tool name to restore"
                  className={INPUT}
                  value={restore.tool_name}
                  onChange={(e) => setRestore((r) => ({ ...r, tool_name: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Reason
                </label>
                <input
                  aria-label="Reason for restore"
                  className={INPUT}
                  value={restore.reason}
                  onChange={(e) => setRestore((r) => ({ ...r, reason: e.target.value }))}
                />
              </div>
              <button
                disabled={pendingAction === "Restore"}
                onClick={() =>
                  act(
                    "Restore",
                    () => toolManagementApi.restoreTool(restore.tool_name, { reason: restore.reason }),
                    "Tool restored",
                  )
                }
                className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {pendingAction === "Restore" && <LoadingSpinner size="sm" />}
                ↺ Restore
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB 3 — Versions
// ═══════════════════════════════════════════════════════════════
function VersionsTab() {
  const [toolName, setToolName] = useState("");
  const [changelog, setChangelog] = useState<{
    versions?: ToolVersionRecord[];
    history?: ToolVersionRecord[];
  } | null>(null);
  const [diff, setDiff] = useState<unknown>(null);
  const [diffA, setDiffA] = useState(1);
  const [diffB, setDiffB] = useState(2);
  const [proposeUpd, setProposeUpd] = useState({ new_code: "", change_summary: "" });
  const [approveUpd, setApproveUpd] = useState({
    pending_version_id: "",
    approved_by_voting_id: "",
  });
  const [rollback, setRollback] = useState({ target_version_number: 1, reason: "" });
  const [rollbackConfirm, setRollbackConfirm] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const act = async (key: string, fn: () => Promise<unknown>, successMsg: string) => {
    setPendingAction(key);
    try {
      await fn();
      showToast.success(successMsg);
    } catch (e: unknown) {
      showToast.error(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          `${key} failed`,
      );
    } finally {
      setPendingAction(null);
    }
  };

  const versions = changelog?.versions ?? changelog?.history ?? [];

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
            <GitBranch className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          </div>
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">Tool Version Explorer</h3>
        </div>

        <div className="flex gap-3">
          <input
            aria-label="Tool name for changelog"
            className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
            placeholder="Tool name"
            value={toolName}
            onChange={(e) => setToolName(e.target.value)}
          />
          <button
            disabled={pendingAction === "Changelog"}
            onClick={() =>
              act("Changelog", async () => {
                const r = await toolManagementApi.getChangelog(toolName);
                setChangelog(r);
                return r;
              }, "Changelog loaded")
            }
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center gap-2"
          >
            {pendingAction === "Changelog" && <LoadingSpinner size="sm" />}
            Load Changelog
          </button>
        </div>
      </div>

      {changelog && (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
              <History className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
              Changelog — {toolName}
            </h3>
          </div>

          {versions.length === 0 ? (
            <EmptyState message="No versions found for this tool." />
          ) : (
            <div className="space-y-3">
              {versions.map((v, i) => (
                <div
                  key={i}
                  className="bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-200 dark:border-[#2a3347] p-4"
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="font-semibold text-gray-900 dark:text-white">
                      v{v.version_number ?? v.version ?? i + 1}
                    </span>
                    <StatusPill status={v.status ?? "active"} />
                  </div>
                  <div className="text-gray-500 dark:text-gray-400 text-xs mb-1">
                    {v.change_summary ?? v.summary ?? "—"}
                  </div>
                  <div className="text-gray-500 dark:text-gray-400 text-xs">
                    By {v.proposed_by ?? v.created_by ?? "—"} · {v.created_at ?? ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Diff */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
              <Code2 className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Version Diff</h3>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Version A
              </label>
              <input
                aria-label="Version A"
                type="number"
                className={INPUT}
                value={diffA}
                onChange={(e) => setDiffA(Number(e.target.value))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Version B
              </label>
              <input
                aria-label="Version B"
                type="number"
                className={INPUT}
                value={diffB}
                onChange={(e) => setDiffB(Number(e.target.value))}
              />
            </div>
          </div>
          <button
            disabled={pendingAction === "Diff"}
            onClick={() =>
              act("Diff", async () => {
                const r = await toolManagementApi.getVersionDiff(toolName, diffA, diffB);
                setDiff(r);
                return r;
              }, "Diff loaded")
            }
            className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {pendingAction === "Diff" && <LoadingSpinner size="sm" />}
            Get Diff
          </button>
          {diff != null && (
            <div className="mt-4">
              <JsonBox data={diff} />
            </div>
          )}
        </div>

        {/* Propose Update */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center">
              <GitCommit className="w-4 h-4 text-yellow-600 dark:text-yellow-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Propose Code Update</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                New Code
              </label>
              <textarea
                aria-label="New code"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all resize-none font-mono"
                rows={4}
                value={proposeUpd.new_code}
                onChange={(e) => setProposeUpd((p) => ({ ...p, new_code: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Change Summary
              </label>
              <input
                aria-label="Change summary"
                className={INPUT}
                value={proposeUpd.change_summary}
                onChange={(e) =>
                  setProposeUpd((p) => ({ ...p, change_summary: e.target.value }))
                }
              />
            </div>
            <button
              disabled={pendingAction === "ProposeUpdate"}
              onClick={() =>
                act(
                  "ProposeUpdate",
                  () => toolManagementApi.proposeUpdate(toolName, proposeUpd),
                  "Update proposed",
                )
              }
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {pendingAction === "ProposeUpdate" && <LoadingSpinner size="sm" />}
              Propose Update
            </button>
          </div>
        </div>

        {/* Approve Update */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
              <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Approve Pending Update</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Pending Version ID
              </label>
              <input
                aria-label="Pending version ID"
                className={INPUT}
                value={approveUpd.pending_version_id}
                onChange={(e) =>
                  setApproveUpd((a) => ({ ...a, pending_version_id: e.target.value }))
                }
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Voting ID (optional)
              </label>
              <input
                aria-label="Voting ID"
                className={INPUT}
                value={approveUpd.approved_by_voting_id}
                onChange={(e) =>
                  setApproveUpd((a) => ({ ...a, approved_by_voting_id: e.target.value }))
                }
              />
            </div>
            <button
              disabled={pendingAction === "ApproveUpdate"}
              onClick={() =>
                act(
                  "ApproveUpdate",
                  () => toolManagementApi.approveUpdate(toolName, approveUpd),
                  "Update approved",
                )
              }
              className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {pendingAction === "ApproveUpdate" && <LoadingSpinner size="sm" />}
              ✓ Approve Update
            </button>
          </div>
        </div>

        {/* Rollback — with confirmation */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
              <RotateCcw className="w-4 h-4 text-orange-600 dark:text-orange-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Rollback to Version</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Target Version Number
              </label>
              <input
                aria-label="Target version number"
                type="number"
                className={INPUT}
                value={rollback.target_version_number}
                onChange={(e) =>
                  setRollback((r) => ({ ...r, target_version_number: Number(e.target.value) }))
                }
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Reason
              </label>
              <input
                aria-label="Reason for rollback"
                className={INPUT}
                value={rollback.reason}
                onChange={(e) => setRollback((r) => ({ ...r, reason: e.target.value }))}
              />
            </div>

            {!rollbackConfirm ? (
              <button
                onClick={() => setRollbackConfirm(true)}
                className="w-full px-4 py-2 bg-orange-600 hover:bg-orange-700 dark:hover:bg-orange-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                ↺ Rollback
              </button>
            ) : (
              <ConfirmRow
                label="Confirm Rollback"
                isPending={pendingAction === "Rollback"}
                onCancel={() => setRollbackConfirm(false)}
                onConfirm={() => {
                  setRollbackConfirm(false);
                  act(
                    "Rollback",
                    () => toolManagementApi.rollback(toolName, rollback),
                    "Rollback successful",
                  );
                }}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB 4 — Sunset
// ═══════════════════════════════════════════════════════════════
function SunsetTab() {
  const { data: deprecated, loading, refresh } = useApi(
    () => toolManagementApi.listDeprecated(),
    [],
  );
  const [toolName, setToolName] = useState("");
  const [sunsetDays, setSunsetDays] = useState(30);
  const [force, setForce] = useState(false);
  const [executeSunsetConfirm, setExecuteSunsetConfirm] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const act = async (key: string, fn: () => Promise<unknown>, successMsg: string) => {
    setPendingAction(key);
    try {
      await fn();
      showToast.success(successMsg);
      refresh();
    } catch (e: unknown) {
      showToast.error(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          `${key} failed`,
      );
    } finally {
      setPendingAction(null);
    }
  };

  const rows =
    (deprecated as { tools?: unknown[]; deprecated?: unknown[] } | null)?.tools ??
    (deprecated as { tools?: unknown[]; deprecated?: unknown[] } | null)?.deprecated ??
    [];

  return (
    <div className="space-y-6">
      {/* Deprecated list */}
      <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
              <Clock className="w-4 h-4 text-red-600 dark:text-red-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
              Deprecated & Sunset Tools
            </h3>
          </div>
          <div className="flex gap-3">
            <button
              aria-label="Refresh deprecated tools"
              onClick={refresh}
              className="px-3 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              disabled={pendingAction === "SunsetCleanup"}
              onClick={() =>
                act("SunsetCleanup", () => toolManagementApi.runSunsetCleanup(), "Sunset cleanup complete")
              }
              className="px-4 py-2 bg-orange-600 hover:bg-orange-700 dark:hover:bg-orange-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center gap-2"
            >
              {pendingAction === "SunsetCleanup" && <LoadingSpinner size="sm" />}
              Run Sunset Cleanup
            </button>
          </div>
        </div>

        {loading && <div className="text-gray-500 dark:text-gray-400 text-sm">Loading…</div>}

        {!loading && rows.length === 0 && (
          <EmptyState message="No deprecated or sunset tools." />
        )}

        {rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-gray-500 dark:text-gray-400 text-left border-b border-gray-200 dark:border-[#1e2535]">
                  {["Tool", "Status", "Deprecated By", "Sunset Date", "Reason", "Replacement"].map(
                    (h) => (
                      <th key={h} className="py-3 px-2 font-medium">
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {(rows as ToolItem[]).map((t, i) => (
                  <tr
                    key={i}
                    className="border-b border-gray-100 dark:border-[#1e2535] hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors"
                  >
                    <td className="py-3 px-2 font-semibold text-gray-900 dark:text-white">
                      {t.tool_name ?? t.name}
                    </td>
                    <td className="py-3 px-2">
                      <StatusPill status={t.status ?? "deprecated"} />
                    </td>
                    <td className="py-3 px-2 text-gray-500 dark:text-gray-400">
                      {(t as { deprecated_by?: string }).deprecated_by ?? "—"}
                    </td>
                    <td className="py-3 px-2 text-gray-500 dark:text-gray-400">
                      {(t as { sunset_date?: string }).sunset_date ?? "—"}
                    </td>
                    <td className="py-3 px-2 text-gray-500 dark:text-gray-400">
                      {t.reason ?? "—"}
                    </td>
                    <td className="py-3 px-2 text-blue-600 dark:text-blue-400">
                      {t.replacement_tool_name ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Schedule Sunset */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
              <Clock className="w-4 h-4 text-orange-600 dark:text-orange-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Schedule Sunset</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Tool Name
              </label>
              <input
                aria-label="Tool name for sunset"
                className={INPUT}
                value={toolName}
                onChange={(e) => setToolName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Sunset Days (min 7)
              </label>
              <input
                aria-label="Sunset days (min 7)"
                type="number"
                min={7}
                className={INPUT}
                value={sunsetDays}
                onChange={(e) => setSunsetDays(Number(e.target.value))}
              />
            </div>
            <button
              disabled={pendingAction === "ScheduleSunset"}
              onClick={() =>
                act(
                  "ScheduleSunset",
                  () => toolManagementApi.scheduleSunset(toolName, { sunset_days: sunsetDays }),
                  "Sunset scheduled",
                )
              }
              className="w-full px-4 py-2 bg-orange-600 hover:bg-orange-700 dark:hover:bg-orange-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {pendingAction === "ScheduleSunset" && <LoadingSpinner size="sm" />}
              Schedule Sunset
            </button>
          </div>
        </div>

        {/* Execute Sunset — with confirmation */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
              <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
              Execute Sunset (Hard Remove)
            </h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Tool Name
              </label>
              <input
                aria-label="Tool name to sunset"
                className={INPUT}
                value={toolName}
                onChange={(e) => setToolName(e.target.value)}
              />
            </div>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={force}
                onChange={(e) => setForce(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-red-600 focus:ring-red-500"
              />
              <span className="text-red-600 dark:text-red-400 text-sm font-medium">
                Force (Head only — bypasses sunset date)
              </span>
            </label>

            {!executeSunsetConfirm ? (
              <button
                onClick={() => setExecuteSunsetConfirm(true)}
                className="w-full px-4 py-2 bg-red-600 hover:bg-red-700 dark:hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                ☠ Execute Sunset
              </button>
            ) : (
              <ConfirmRow
                label="Confirm Execute Sunset"
                isPending={pendingAction === "ExecuteSunset"}
                onCancel={() => setExecuteSunsetConfirm(false)}
                onConfirm={() => {
                  setExecuteSunsetConfirm(false);
                  act(
                    "ExecuteSunset",
                    () => toolManagementApi.executeSunset(toolName, { force }),
                    "Tool sunset executed",
                  );
                }}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB 5 — Analytics
// ═══════════════════════════════════════════════════════════════
function AnalyticsTab() {
  // Each sub-section has its own independent days counter.
  const [reportDays, setReportDays] = useState(30);
  const [agentDays, setAgentDays] = useState(30);
  const [toolDays, setToolDays] = useState(30);

  const [errorTool, setErrorTool] = useState("");
  const [errorLimit, setErrorLimit] = useState(50);
  const [agentId, setAgentId] = useState("");
  const [perTool, setPerTool] = useState("");

  const [report, setReport] = useState<AnalyticsReport | null>(null);
  const [errors, setErrors] = useState<{ errors?: ErrorRecord[]; items?: ErrorRecord[]; error?: string } | null>(null);
  const [agentUsage, setAgentUsage] = useState<AgentUsageResponse | { error?: string } | null>(null);
  const [toolStats, setToolStats] = useState<ToolStats | { error?: string } | null>(null);
  const [pendingSection, setPendingSection] = useState<string | null>(null);

  const fetchSection = async (
    key: string,
    fn: () => Promise<unknown>,
    setter: (v: unknown) => void,
  ) => {
    setPendingSection(key);
    try {
      setter(await fn());
    } catch (e: unknown) {
      setter({
        error:
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (e as Error)?.message ??
          "Request failed",
      });
    }
    setPendingSection(null);
  };

  function MetricCard({
    label,
    value,
    color = "text-blue-600 dark:text-blue-400",
  }: {
    label: string;
    value: React.ReactNode;
    color?: string;
  }) {
    return (
      <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 text-center shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
        <div className={`text-2xl font-bold ${color} tabular-nums`}>{value ?? "—"}</div>
        <div className="text-gray-500 dark:text-gray-400 text-xs mt-1 uppercase tracking-wider">
          {label}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Full Report */}
      <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
              <BarChart3 className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Analytics Report</h3>
          </div>
          <div className="flex gap-3 items-center">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">Days:</span>
              <input
                aria-label="Report days"
                type="number"
                className="w-20 px-3 py-1.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
                value={reportDays}
                onChange={(e) => setReportDays(Number(e.target.value))}
              />
            </div>
            <button
              disabled={pendingSection === "report"}
              onClick={() =>
                fetchSection(
                  "report",
                  () => toolManagementApi.getAnalyticsReport(reportDays),
                  setReport as (v: unknown) => void,
                )
              }
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center gap-2"
            >
              {pendingSection === "report" && <LoadingSpinner size="sm" />}
              {pendingSection === "report" ? "Loading…" : "Load Report"}
            </button>
          </div>
        </div>

        {report && !(report as { error?: string }).error && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <MetricCard
                label="Total Calls"
                value={report.total_calls ?? report.summary?.total_calls}
              />
              <MetricCard
                label="Success Rate"
                value={
                  report.success_rate != null
                    ? `${(report.success_rate * 100).toFixed(1)}%`
                    : report.summary?.success_rate
                }
                color="text-green-600 dark:text-green-400"
              />
              <MetricCard
                label="Avg Latency"
                value={report.avg_latency_ms != null ? `${report.avg_latency_ms}ms` : "—"}
                color="text-yellow-600 dark:text-yellow-400"
              />
              <MetricCard
                label="Active Tools"
                value={report.active_tool_count ?? report.summary?.active_tools}
              />
            </div>
            <JsonBox data={report} />
          </>
        )}
        {(report as { error?: string } | null)?.error && (
          <div className="text-red-600 dark:text-red-400">
            {(report as { error?: string }).error}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Errors */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
              <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Recent Errors</h3>
          </div>

          <div className="flex gap-3 mb-4">
            <input
              aria-label="Tool name filter for errors"
              className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
              placeholder="Tool name (optional)"
              value={errorTool}
              onChange={(e) => setErrorTool(e.target.value)}
            />
            <input
              aria-label="Error limit"
              type="number"
              className="w-20 px-3 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
              value={errorLimit}
              onChange={(e) => setErrorLimit(Number(e.target.value))}
            />
            <button
              disabled={pendingSection === "errors"}
              onClick={() =>
                fetchSection(
                  "errors",
                  () => toolManagementApi.getRecentErrors(errorTool || undefined, errorLimit),
                  setErrors as (v: unknown) => void,
                )
              }
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center gap-2"
            >
              {pendingSection === "errors" && <LoadingSpinner size="sm" />}
              Fetch
            </button>
          </div>

          {errors && !errors.error && (
            <div className="max-h-80 overflow-y-auto space-y-3">
              {(errors.errors ?? errors.items ?? []).length === 0 ? (
                <EmptyState message="No errors found." />
              ) : (
                (errors.errors ?? errors.items ?? []).map((e, i) => (
                  <div
                    key={i}
                    className="bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-200 dark:border-[#2a3347] p-3"
                  >
                    <div className="flex justify-between items-start">
                      <span className="font-semibold text-red-600 dark:text-red-400 text-sm">
                        {e.tool_name}
                      </span>
                      <span className="text-gray-500 dark:text-gray-400 text-xs">
                        {e.timestamp ?? e.called_at}
                      </span>
                    </div>
                    <div className="text-gray-500 dark:text-gray-400 text-xs mt-1">
                      {e.error_message ?? e.error}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
          {errors?.error && (
            <div className="text-red-600 dark:text-red-400">{errors.error}</div>
          )}
        </div>

        {/* Per-Agent Usage */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
              <Users className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Per-Agent Tool Usage</h3>
          </div>

          <div className="flex gap-3 mb-4">
            <input
              aria-label="Agent ID"
              className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
              placeholder="Agent ID"
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
            />
            <input
              aria-label="Agent usage days"
              type="number"
              className="w-20 px-3 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
              value={agentDays}
              onChange={(e) => setAgentDays(Number(e.target.value))}
            />
            <button
              disabled={pendingSection === "agent"}
              onClick={() =>
                fetchSection(
                  "agent",
                  () => toolManagementApi.getAgentToolUsage(agentId, agentDays),
                  setAgentUsage as (v: unknown) => void,
                )
              }
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center gap-2"
            >
              {pendingSection === "agent" && <LoadingSpinner size="sm" />}
              Fetch
            </button>
          </div>

          {agentUsage && !(agentUsage as { error?: string }).error && (
            <JsonBox data={agentUsage} />
          )}
          {(agentUsage as { error?: string } | null)?.error && (
            <div className="text-red-600 dark:text-red-400">
              {(agentUsage as { error?: string }).error}
            </div>
          )}
        </div>

        {/* Per-Tool Stats */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] lg:col-span-2">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
              <Activity className="w-4 h-4 text-green-600 dark:text-green-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Per-Tool Analytics</h3>
          </div>

          <div className="flex gap-3 mb-4">
            <input
              aria-label="Tool name for analytics"
              className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
              placeholder="Tool name"
              value={perTool}
              onChange={(e) => setPerTool(e.target.value)}
            />
            <input
              aria-label="Tool analytics days"
              type="number"
              className="w-20 px-3 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
              value={toolDays}
              onChange={(e) => setToolDays(Number(e.target.value))}
            />
            <button
              disabled={pendingSection === "tool"}
              onClick={() =>
                fetchSection(
                  "tool",
                  () => toolManagementApi.getToolStats(perTool, toolDays),
                  setToolStats as (v: unknown) => void,
                )
              }
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50 flex items-center gap-2"
            >
              {pendingSection === "tool" && <LoadingSpinner size="sm" />}
              Fetch Stats
            </button>
          </div>

          {toolStats && !(toolStats as { error?: string }).error && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
                {(
                  [
                    ["Calls", (toolStats as ToolStats).total_calls, "text-blue-600 dark:text-blue-400"],
                    ["Successes", (toolStats as ToolStats).success_count, "text-green-600 dark:text-green-400"],
                    ["Failures", (toolStats as ToolStats).failure_count, "text-red-600 dark:text-red-400"],
                    [
                      "Avg Latency",
                      (toolStats as ToolStats).avg_latency_ms != null
                        ? `${(toolStats as ToolStats).avg_latency_ms}ms`
                        : "—",
                      "text-yellow-600 dark:text-yellow-400",
                    ],
                    ["Unique Agents", (toolStats as ToolStats).unique_agents, "text-gray-900 dark:text-white"],
                  ] as [string, unknown, string][]
                ).map(([l, v, c]) => (
                  <div
                    key={l}
                    className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 text-center shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]"
                  >
                    <div className={`text-2xl font-bold ${c} tabular-nums`}>{(v as React.ReactNode) ?? "—"}</div>
                    <div className="text-gray-500 dark:text-gray-400 text-xs mt-1 uppercase tracking-wider">
                      {l}
                    </div>
                  </div>
                ))}
              </div>
              <JsonBox data={toolStats} />
            </>
          )}
          {(toolStats as { error?: string } | null)?.error && (
            <div className="text-red-600 dark:text-red-400">
              {(toolStats as { error?: string }).error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// ROOT
// ═══════════════════════════════════════════════════════════════
const TABS = ["Marketplace", "Tools", "Versions", "Sunset", "Analytics"];

interface ToolMarketplacePageProps {
  embedded?: boolean;
}

export default function ToolMarketplacePage({ embedded = false }: ToolMarketplacePageProps) {
  const [active, setActive] = useState(0);

  return (
    <div
      className={`bg-gray-50 dark:bg-[#0f1117] transition-colors duration-200 ${
        embedded ? "" : "min-h-screen"
      }`}
    >
      {/* Header — hidden when embedded */}
      {!embedded && (
        <div className="bg-white dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] px-6 py-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
            <Terminal className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">Tool Management</h1>
            <span className="text-xs font-medium bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 px-2 py-0.5 rounded-full border border-blue-200 dark:border-blue-500/20">
              Phase 6.8
            </span>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div
        className={`bg-white dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] ${
          embedded ? "" : "px-6"
        }`}
      >
        <div className="flex gap-1">
          {TABS.map((t, i) => (
            <button
              key={t}
              onClick={() => setActive(i)}
              className={`px-5 py-3 text-sm font-medium transition-all border-b-2 ${
                active === i
                  ? "text-blue-600 dark:text-blue-400 border-blue-600 dark:border-blue-400"
                  : "text-gray-500 dark:text-gray-400 border-transparent hover:text-gray-700 dark:hover:text-gray-300"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className={embedded ? "" : "p-6"}>
        {active === 0 && <MarketplaceTab />}
        {active === 1 && <ToolsTab />}
        {active === 2 && <VersionsTab />}
        {active === 3 && <SunsetTab />}
        {active === 4 && <AnalyticsTab />}
      </div>
    </div>
  );
}