/**
 * ToolMarketplacePage.tsx
 * Full frontend coverage for all tool-management routes in tool_creation.py
 * Updated to use Tailwind CSS with dark/light mode support
 * Now supports embedded mode for use inside SovereignDashboard
 */

import { useState, useEffect, useCallback } from "react";
import { api } from "../services/api";
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
  ChevronLeft,
  ChevronRight,
  Plus,
  Save,
  Play,
  RotateCcw,
  GitCommit,
  GitBranch,
  History,
  Activity,
  Terminal,
  Code2,
  Users,
  Zap,
  Filter,
  RefreshCw,
  X,
  ChevronDown,
  ChevronUp,
  MoreVertical,
  Edit3,
  ExternalLink
} from "lucide-react";

// ── helpers ──────────────────────────────────────────────────────────────────
const BASE = "/api/v1/tool-management";
const mkt = (path = "") => `${BASE}/marketplace${path}`;
const tool = (name: string, path = "") => `${BASE}/${name}${path}`;

function StatusPill({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    active: "bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20",
    pending: "bg-yellow-100 dark:bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/20",
    deprecated: "bg-orange-100 dark:bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-500/20",
    sunset: "bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20",
    voting: "bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-500/20",
    yanked: "bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20",
    staged: "bg-purple-100 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-200 dark:border-purple-500/20",
  };
  
  const colorClass = colorMap[status] || "bg-gray-100 dark:bg-gray-500/10 text-gray-700 dark:text-gray-400 border-gray-200 dark:border-gray-500/20";
  
  return (
    <span className={`px-2.5 py-1 text-xs font-medium rounded-full border ${colorClass}`}>
      {status}
    </span>
  );
}

function StarRating({ value, onChange }: { value: number; onChange?: (v: number) => void }) {
  return (
    <span className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((s) => (
        <span
          key={s}
          onClick={() => onChange?.(s)}
          className={`text-lg cursor-${onChange ? "pointer" : "default"} ${
            s <= value ? "text-yellow-500" : "text-gray-300 dark:text-gray-600"
          }`}
        >
          ★
        </span>
      ))}
    </span>
  );
}

function JsonBox({ data }: { data: unknown }) {
  return (
    <pre className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg p-4 text-xs overflow-auto whitespace-pre-wrap text-gray-700 dark:text-gray-300 font-mono">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fn());
    } catch (e: any) {
      setError(e.response?.data?.detail ?? e.message);
    }
    setLoading(false);
  }, deps);
  
  useEffect(() => {
    run();
  }, [run]);
  
  return { data, loading, error, refresh: run };
}

async function callApi(method: "get" | "post" | "delete", url: string, body?: unknown) {
  const res = await api[method](url, body as any);
  return res.data;
}

// ═══════════════════════════════════════════════════════════════
// TAB 1 — Marketplace
// ═══════════════════════════════════════════════════════════════
function MarketplaceTab() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  // publish form
  const [pub, setPub] = useState({ tool_name: "", display_name: "", category: "", tags: "" });
  // rate
  const [rateId, setRateId] = useState("");
  const [rateVal, setRateVal] = useState(4);
  // yank
  const [yankId, setYankId] = useState("");
  const [yankReason, setYankReason] = useState("");
  // import
  const [importId, setImportId] = useState("");
  const [stagingId, setStagingId] = useState("");
  const [msg, setMsg] = useState("");

  const browse = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "12" });
      if (search) params.set("search", search);
      if (category) params.set("category", category);
      const res = await api.get(`${mkt()}?${params}`);
      setResult(res.data);
    } catch {}
    setLoading(false);
  }, [search, category, page]);

  useEffect(() => {
    browse();
  }, [browse]);

  const act = async (label: string, fn: () => Promise<any>) => {
    try {
      const r = await fn();
      setMsg(`✓ ${label}: ${JSON.stringify(r).slice(0, 120)}`);
    } catch (e: any) {
      setMsg(`✗ ${label}: ${e.response?.data?.detail ?? e.message}`);
    }
  };

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
              className="w-full pl-10 pr-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
              placeholder="Search tools..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <input
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
        
        {loading && <div className="text-gray-500 dark:text-gray-400 text-sm">Loading…</div>}
        
        {result && (
          <>
            <div className="text-gray-500 dark:text-gray-400 text-xs mb-4">
              {result.total ?? result.listings?.length ?? 0} listing(s) · page {page}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {(result.listings ?? result.tools ?? []).map((l: any) => (
                <div
                  key={l.listing_id ?? l.tool_name}
                  className="bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-200 dark:border-[#2a3347] p-4 hover:border-gray-300 dark:hover:border-[#3a4357] transition-all"
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="font-semibold text-gray-900 dark:text-white">{l.display_name ?? l.tool_name}</span>
                    <StatusPill status={l.status ?? "active"} />
                  </div>
                  <div className="text-gray-500 dark:text-gray-400 text-xs mb-2">
                    {l.category} · {(l.tags ?? []).join(", ")}
                  </div>
                  <StarRating value={Math.round(l.average_rating ?? 0)} />
                  <div className="text-gray-500 dark:text-gray-400 text-xs mt-2">
                    {l.import_count ?? 0} imports
                  </div>
                </div>
              ))}
            </div>
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
                className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
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
            {[
              ["tool_name", "Tool Name"],
              ["display_name", "Display Name"],
              ["category", "Category"],
            ].map(([k, label]) => (
              <div key={k}>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  {label}
                </label>
                <input
                  className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                  value={(pub as any)[k]}
                  onChange={(e) => setPub((p) => ({ ...p, [k]: e.target.value }))}
                />
              </div>
            ))}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Tags (comma-separated)
              </label>
              <input aria-label="Tags (comma-separated)"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={pub.tags}
                onChange={(e) => setPub((p) => ({ ...p, tags: e.target.value }))}
              />
            </div>
            <button
              onClick={() =>
                act("Publish", () =>
                  callApi("post", mkt("/publish"), {
                    ...pub,
                    tags: pub.tags.split(",").map((t) => t.trim()).filter(Boolean),
                  })
                )
              }
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
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
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={importId}
                onChange={(e) => setImportId(e.target.value)}
                placeholder="listing-uuid"
              />
            </div>
            <button
              onClick={() => act("Stage Import", () => callApi("post", mkt(`/${importId}/import`)))}
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              Stage Import
            </button>
            
            <div className="border-t border-gray-200 dark:border-[#1e2535] pt-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Staging ID (to finalize)
              </label>
              <input aria-label="Staging ID (to finalize)"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={stagingId}
                onChange={(e) => setStagingId(e.target.value)}
              />
              <button
                onClick={() =>
                  act("Finalize Import", () => callApi("post", mkt("/finalize-import"), { staging_id: stagingId }))
                }
                className="w-full mt-3 px-4 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
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
              <input aria-label="Listing ID"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
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
              onClick={() => act("Rate", () => callApi("post", mkt(`/${rateId}/rate`), { rating: rateVal }))}
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              Submit Rating
            </button>
          </div>
        </div>

        {/* Yank */}
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
              <input aria-label="Listing ID"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={yankId}
                onChange={(e) => setYankId(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Reason
              </label>
              <input aria-label="Reason"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={yankReason}
                onChange={(e) => setYankReason(e.target.value)}
              />
            </div>
            <button
              onClick={() => act("Yank", () => callApi("post", mkt(`/${yankId}/yank`), { reason: yankReason }))}
              className="w-full px-4 py-2 bg-red-600 hover:bg-red-700 dark:hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              Yank Listing ✗
            </button>
          </div>
        </div>
      </div>

      {msg && (
        <div
          className={`rounded-xl border p-4 ${
            msg.startsWith("✓")
              ? "bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20 text-green-700 dark:text-green-400"
              : "bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400"
          }`}
        >
          {msg}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB 2 — Tools
// ═══════════════════════════════════════════════════════════════
function ToolsTab() {
  const [statusFilter, setStatusFilter] = useState("");
  const { data: tools, loading, refresh } = useApi(() => {
    const p = statusFilter ? `?status_filter=${statusFilter}` : "";
    return callApi("get", `${BASE}/${p}`);
  }, [statusFilter]);

  const [propose, setPropose] = useState({ name: "", description: "", code: "", created_by_agentium_id: "", authorized_tiers: "" });
  const [vote, setVote] = useState({ tool_name: "", vote: "for" });
  const [exec, setExec] = useState({ tool_name: "", kwargs: "", task_id: "" });
  const [dep, setDep] = useState({ tool_name: "", reason: "", replacement: "", sunset_days: "" });
  const [restore, setRestore] = useState({ tool_name: "", reason: "" });
  const [msg, setMsg] = useState("");

  const act = async (label: string, fn: () => Promise<any>) => {
    try {
      const r = await fn();
      setMsg(`✓ ${label}: ${JSON.stringify(r).slice(0, 160)}`);
      refresh();
    } catch (e: any) {
      setMsg(`✗ ${label}: ${e.response?.data?.detail ?? e.message}`);
    }
  };

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
            <select aria-label="Status filter"
              className="px-3 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
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
            <button aria-label="Refresh tools"
              onClick={refresh}
              className="px-3 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
        
        {loading && <div className="text-gray-500 dark:text-gray-400 text-sm">Loading…</div>}
        
        {tools && (
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
                {(tools.tools ?? Object.entries(tools)).map((t: any) => {
                  const row = Array.isArray(t) ? t[1] : t;
                  const name = Array.isArray(t) ? t[0] : t.tool_name ?? t.name;
                  return (
                    <tr key={name} className="border-b border-gray-100 dark:border-[#1e2535] hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors">
                      <td className="py-3 px-2 font-semibold text-gray-900 dark:text-white">{name}</td>
                      <td className="py-3 px-2 text-gray-500 dark:text-gray-400 max-w-xs truncate">
                        {row.description ?? "—"}
                      </td>
                      <td className="py-3 px-2">
                        <StatusPill status={row.status ?? "active"} />
                      </td>
                      <td className="py-3 px-2 text-gray-500 dark:text-gray-400">v{row.version ?? row.current_version ?? 1}</td>
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
            {[
              ["name", "Tool Name"],
              ["description", "Description"],
              ["created_by_agentium_id", "Agent ID"],
              ["authorized_tiers", "Authorized Tiers (comma)"],
            ].map(([k, label]) => (
              <div key={k}>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  {label}
                </label>
                <input aria-label={label}
                  className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                  value={(propose as any)[k]}
                  onChange={(e) => setPropose((p) => ({ ...p, [k]: e.target.value }))}
                />
              </div>
            ))}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Code
              </label>
              <textarea
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all resize-none font-mono"
                rows={4}
                value={propose.code}
                onChange={(e) => setPropose((p) => ({ ...p, code: e.target.value }))}
                placeholder="def my_tool(...): ..."
              />
            </div>
            <button
              onClick={() =>
                act("Propose", () =>
                  callApi("post", `${BASE}/propose`, {
                    ...propose,
                    authorized_tiers: propose.authorized_tiers.split(",").map((s) => s.trim()),
                  })
                )
              }
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
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
              <input aria-label="Tool Name"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={vote.tool_name}
                onChange={(e) => setVote((v) => ({ ...v, tool_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Vote
              </label>
              <div className="flex gap-2">
                {["for", "against", "abstain"].map((v) => (
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
              onClick={() => act("Vote", () => callApi("post", tool(vote.tool_name, "/vote"), { vote: vote.vote }))}
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
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
              <input aria-label="Tool Name"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={exec.tool_name}
                onChange={(e) => setExec((x) => ({ ...x, tool_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                kwargs (JSON)
              </label>
              <textarea
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
              <input aria-label="Task ID"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={exec.task_id}
                onChange={(e) => setExec((x) => ({ ...x, task_id: e.target.value }))}
              />
            </div>
            <button
              onClick={() =>
                act("Execute", () =>
                  callApi("post", tool(exec.tool_name, "/execute"), {
                    kwargs: exec.kwargs ? JSON.parse(exec.kwargs) : {},
                    task_id: exec.task_id || undefined,
                  })
                )
              }
              className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              ▶ Execute
            </button>
          </div>
        </div>

        {/* Deprecate */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
              <AlertTriangle className="w-4 h-4 text-orange-600 dark:text-orange-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Deprecate Tool</h3>
          </div>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Tool Name
              </label>
              <input aria-label="Tool Name"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={dep.tool_name}
                onChange={(e) => setDep((d) => ({ ...d, tool_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Reason
              </label>
              <input aria-label="Reason"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={dep.reason}
                onChange={(e) => setDep((d) => ({ ...d, reason: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Replacement Tool (optional)
              </label>
              <input aria-label="Replacement Tool"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={dep.replacement}
                onChange={(e) => setDep((d) => ({ ...d, replacement: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Sunset Days (optional)
              </label>
              <input aria-label="Sunset Days"
                type="number"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={dep.sunset_days}
                onChange={(e) => setDep((d) => ({ ...d, sunset_days: e.target.value }))}
              />
            </div>
            <button
              onClick={() =>
                act("Deprecate", () =>
                  callApi("post", tool(dep.tool_name, "/deprecate"), {
                    reason: dep.reason,
                    replacement_tool_name: dep.replacement || undefined,
                    sunset_days: dep.sunset_days ? Number(dep.sunset_days) : undefined,
                  })
                )
              }
              className="w-full px-4 py-2 bg-orange-600 hover:bg-orange-700 dark:hover:bg-orange-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              ⚠ Deprecate
            </button>
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
                <input aria-label="Tool Name"
                  className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                  value={restore.tool_name}
                  onChange={(e) => setRestore((r) => ({ ...r, tool_name: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Reason
                </label>
                <input aria-label="Reason"
                  className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                  value={restore.reason}
                  onChange={(e) => setRestore((r) => ({ ...r, reason: e.target.value }))}
                />
              </div>
              <button
                onClick={() => act("Restore", () => callApi("post", tool(restore.tool_name, "/restore"), { reason: restore.reason }))}
                className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                ↺ Restore
              </button>
            </div>
          </div>
        </div>
      </div>

      {msg && (
        <div
          className={`rounded-xl border p-4 ${
            msg.startsWith("✓")
              ? "bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20 text-green-700 dark:text-green-400"
              : "bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400"
          }`}
        >
          {msg}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB 3 — Versions
// ═══════════════════════════════════════════════════════════════
function VersionsTab() {
  const [toolName, setToolName] = useState("");
  const [changelog, setChangelog] = useState<any>(null);
  const [diff, setDiff] = useState<any>(null);
  const [diffA, setDiffA] = useState(1);
  const [diffB, setDiffB] = useState(2);
  const [proposeUpd, setProposeUpd] = useState({ new_code: "", change_summary: "" });
  const [approveUpd, setApproveUpd] = useState({ pending_version_id: "", approved_by_voting_id: "" });
  const [rollback, setRollback] = useState({ target_version_number: 1, reason: "" });
  const [msg, setMsg] = useState("");

  const act = async (label: string, fn: () => Promise<any>) => {
    try {
      const r = await fn();
      setMsg(`✓ ${label}: ${JSON.stringify(r).slice(0, 200)}`);
    } catch (e: any) {
      setMsg(`✗ ${label}: ${e.response?.data?.detail ?? e.message}`);
    }
  };

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
            className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
            placeholder="Tool name"
            value={toolName}
            onChange={(e) => setToolName(e.target.value)}
          />
          <button
            onClick={() =>
              act("Changelog", async () => {
                const r = await callApi("get", tool(toolName, "/versions/changelog"));
                setChangelog(r);
                return r;
              })
            }
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
          >
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
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Changelog — {toolName}</h3>
          </div>
          
          <div className="space-y-3">
            {(changelog.versions ?? changelog.history ?? [changelog]).map((v: any, i: number) => (
              <div
                key={i}
                className="bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-200 dark:border-[#2a3347] p-4"
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="font-semibold text-gray-900 dark:text-white">v{v.version_number ?? v.version ?? i + 1}</span>
                  <StatusPill status={v.status ?? "active"} />
                </div>
                <div className="text-gray-500 dark:text-gray-400 text-xs mb-1">{v.change_summary ?? v.summary ?? "—"}</div>
                <div className="text-gray-500 dark:text-gray-400 text-xs">
                  By {v.proposed_by ?? v.created_by ?? "—"} · {v.created_at ?? ""}
                </div>
              </div>
            ))}
          </div>
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
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Version A</label>
              <input aria-label="Version A"
                type="number"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={diffA}
                onChange={(e) => setDiffA(Number(e.target.value))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Version B</label>
              <input aria-label="Version B"
                type="number"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={diffB}
                onChange={(e) => setDiffB(Number(e.target.value))}
              />
            </div>
          </div>
          <button
            onClick={() =>
              act("Diff", async () => {
                const r = await callApi("get", `${BASE}/${toolName}/versions/diff?version_a=${diffA}&version_b=${diffB}`);
                setDiff(r);
                return r;
              })
            }
            className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
          >
            Get Diff
          </button>
          {diff && <div className="mt-4"><JsonBox data={diff} /></div>}
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
              <textarea aria-label="New Code"
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
              <input aria-label="Change Summary"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={proposeUpd.change_summary}
                onChange={(e) => setProposeUpd((p) => ({ ...p, change_summary: e.target.value }))}
              />
            </div>
            <button
              onClick={() => act("Propose Update", () => callApi("post", tool(toolName, "/versions/propose-update"), proposeUpd))}
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
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
              <input aria-label="Pending Version ID"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={approveUpd.pending_version_id}
                onChange={(e) => setApproveUpd((a) => ({ ...a, pending_version_id: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Voting ID (optional)
              </label>
              <input aria-label="Voting ID (optional)"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={approveUpd.approved_by_voting_id}
                onChange={(e) => setApproveUpd((a) => ({ ...a, approved_by_voting_id: e.target.value }))}
              />
            </div>
            <button
              onClick={() => act("Approve Update", () => callApi("post", tool(toolName, "/versions/approve-update"), approveUpd))}
              className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              ✓ Approve Update
            </button>
          </div>
        </div>

        {/* Rollback */}
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
              <input aria-label="Target Version Number"
                type="number"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={rollback.target_version_number}
                onChange={(e) => setRollback((r) => ({ ...r, target_version_number: Number(e.target.value) }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Reason
              </label>
              <input aria-label="Reason"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={rollback.reason}
                onChange={(e) => setRollback((r) => ({ ...r, reason: e.target.value }))}
              />
            </div>
            <button
              onClick={() => act("Rollback", () => callApi("post", tool(toolName, "/versions/rollback"), rollback))}
              className="w-full px-4 py-2 bg-orange-600 hover:bg-orange-700 dark:hover:bg-orange-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              ↺ Rollback
            </button>
          </div>
        </div>
      </div>

      {msg && (
        <div
          className={`rounded-xl border p-4 ${
            msg.startsWith("✓")
              ? "bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20 text-green-700 dark:text-green-400"
              : "bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400"
          }`}
        >
          {msg}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB 4 — Sunset
// ═══════════════════════════════════════════════════════════════
function SunsetTab() {
  const { data: deprecated, loading, refresh } = useApi(() => callApi("get", `${BASE}/deprecated`));
  const [toolName, setToolName] = useState("");
  const [sunsetDays, setSunsetDays] = useState(30);
  const [force, setForce] = useState(false);
  const [msg, setMsg] = useState("");

  const act = async (label: string, fn: () => Promise<any>) => {
    try {
      const r = await fn();
      setMsg(`✓ ${label}: ${JSON.stringify(r).slice(0, 200)}`);
      refresh();
    } catch (e: any) {
      setMsg(`✗ ${label}: ${e.response?.data?.detail ?? e.message}`);
    }
  };

  return (
    <div className="space-y-6">
      {/* Deprecated list */}
      <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
              <Clock className="w-4 h-4 text-red-600 dark:text-red-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Deprecated & Sunset Tools</h3>
          </div>
          <div className="flex gap-3">
            <button aria-label="Refresh"
              onClick={refresh}
              className="px-3 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={() => act("Sunset Cleanup", () => callApi("post", `${BASE}/run-sunset-cleanup`))}
              className="px-4 py-2 bg-orange-600 hover:bg-orange-700 dark:hover:bg-orange-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              Run Sunset Cleanup
            </button>
          </div>
        </div>
        
        {loading && <div className="text-gray-500 dark:text-gray-400 text-sm">Loading…</div>}
        
        {deprecated && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-gray-500 dark:text-gray-400 text-left border-b border-gray-200 dark:border-[#1e2535]">
                  {["Tool", "Status", "Deprecated By", "Sunset Date", "Reason", "Replacement"].map((h) => (
                    <th key={h} className="py-3 px-2 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(deprecated.tools ?? deprecated.deprecated ?? []).map((t: any, i: number) => (
                  <tr key={i} className="border-b border-gray-100 dark:border-[#1e2535] hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors">
                    <td className="py-3 px-2 font-semibold text-gray-900 dark:text-white">{t.tool_name ?? t.name}</td>
                    <td className="py-3 px-2">
                      <StatusPill status={t.status ?? "deprecated"} />
                    </td>
                    <td className="py-3 px-2 text-gray-500 dark:text-gray-400">{t.deprecated_by ?? "—"}</td>
                    <td className="py-3 px-2 text-gray-500 dark:text-gray-400">{t.sunset_date ?? "—"}</td>
                    <td className="py-3 px-2 text-gray-500 dark:text-gray-400">{t.reason ?? "—"}</td>
                    <td className="py-3 px-2 text-blue-600 dark:text-blue-400">{t.replacement_tool_name ?? "—"}</td>
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
              <input aria-label="Tool Name"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={toolName}
                onChange={(e) => setToolName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Sunset Days (min 7)
              </label>
              <input aria-label="Sunset Days (min 7)"
                type="number"
                min={7}
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                value={sunsetDays}
                onChange={(e) => setSunsetDays(Number(e.target.value))}
              />
            </div>
            <button
              onClick={() =>
                act("Schedule Sunset", () => callApi("post", tool(toolName, "/schedule-sunset"), { sunset_days: sunsetDays }))
              }
              className="w-full px-4 py-2 bg-orange-600 hover:bg-orange-700 dark:hover:bg-orange-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              🕐 Schedule Sunset
            </button>
          </div>
        </div>

        {/* Execute Sunset */}
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
              <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">Execute Sunset (Hard Remove)</h3>
          </div>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Tool Name
              </label>
              <input aria-label="Tool Name"
                className="w-full px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
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
              <span className="text-red-600 dark:text-red-400 text-sm font-medium">Force (Head only — bypasses sunset date)</span>
            </label>
            <button
              onClick={() => act("Execute Sunset", () => callApi("post", tool(toolName, "/execute-sunset"), { force }))}
              className="w-full px-4 py-2 bg-red-600 hover:bg-red-700 dark:hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              ☠ Execute Sunset
            </button>
          </div>
        </div>
      </div>

      {msg && (
        <div
          className={`rounded-xl border p-4 ${
            msg.startsWith("✓")
              ? "bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20 text-green-700 dark:text-green-400"
              : "bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400"
          }`}
        >
          {msg}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB 5 — Analytics
// ═══════════════════════════════════════════════════════════════
function AnalyticsTab() {
  const [days, setDays] = useState(30);
  const [errorTool, setErrorTool] = useState("");
  const [errorLimit, setErrorLimit] = useState(50);
  const [agentId, setAgentId] = useState("");
  const [perTool, setPerTool] = useState("");
  const [report, setReport] = useState<any>(null);
  const [errors, setErrors] = useState<any>(null);
  const [agentUsage, setAgentUsage] = useState<any>(null);
  const [toolStats, setToolStats] = useState<any>(null);
  const [loading, setLoading] = useState("");

  const fetch = async (key: string, fn: () => Promise<any>, setter: (v: any) => void) => {
    setLoading(key);
    try {
      setter(await fn());
    } catch (e: any) {
      setter({ error: e.response?.data?.detail ?? e.message });
    }
    setLoading("");
  };

  const MetricCard = ({ label, value, color = "text-blue-600 dark:text-blue-400" }: { label: string; value: any; color?: string }) => (
    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 text-center shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
      <div className={`text-2xl font-bold ${color} tabular-nums`}>{value ?? "—"}</div>
      <div className="text-gray-500 dark:text-gray-400 text-xs mt-1 uppercase tracking-wider">{label}</div>
    </div>
  );

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
              <input aria-label="Days"
                type="number"
                className="w-20 px-3 py-1.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              />
            </div>
            <button
              onClick={() => fetch("report", () => callApi("get", `${BASE}/analytics/report?days=${days}`), setReport)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              {loading === "report" ? "Loading…" : "Load Report"}
            </button>
          </div>
        </div>
        
        {report && !report.error && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <MetricCard
                label="Total Calls"
                value={report.total_calls ?? report.summary?.total_calls}
              />
              <MetricCard
                label="Success Rate"
                value={report.success_rate != null ? `${(report.success_rate * 100).toFixed(1)}%` : report.summary?.success_rate}
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
        {report?.error && <div className="text-red-600 dark:text-red-400">{report.error}</div>}
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
              className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
              placeholder="Tool name (optional)"
              value={errorTool}
              onChange={(e) => setErrorTool(e.target.value)}
            />
            <input aria-label="Error Limit"
              type="number"
              className="w-20 px-3 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
              value={errorLimit}
              onChange={(e) => setErrorLimit(Number(e.target.value))}
            />
            <button
              onClick={() =>
                fetch("errors", () => callApi("get", `${BASE}/analytics/errors?${errorTool ? `tool_name=${errorTool}&` : ""}limit=${errorLimit}`), setErrors)
              }
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              {loading === "errors" ? "…" : "Fetch"}
            </button>
          </div>
          
          {errors && !errors.error && (
            <div className="max-h-80 overflow-y-auto space-y-3">
              {(errors.errors ?? errors.items ?? []).map((e: any, i: number) => (
                <div key={i} className="bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-200 dark:border-[#2a3347] p-3">
                  <div className="flex justify-between items-start">
                    <span className="font-semibold text-red-600 dark:text-red-400 text-sm">{e.tool_name}</span>
                    <span className="text-gray-500 dark:text-gray-400 text-xs">{e.timestamp ?? e.called_at}</span>
                  </div>
                  <div className="text-gray-500 dark:text-gray-400 text-xs mt-1">{e.error_message ?? e.error}</div>
                </div>
              ))}
              {(errors.errors ?? errors.items ?? []).length === 0 && (
                <div className="text-gray-500 dark:text-gray-400 text-sm">No errors found.</div>
              )}
            </div>
          )}
          {errors?.error && <div className="text-red-600 dark:text-red-400">{errors.error}</div>}
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
              className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
              placeholder="Agent ID"
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
            />
            <button
              onClick={() => fetch("agent", () => callApi("get", `${BASE}/analytics/agent/${agentId}?days=${days}`), setAgentUsage)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              {loading === "agent" ? "…" : "Fetch"}
            </button>
          </div>
          
          {agentUsage && !agentUsage.error && <JsonBox data={agentUsage} />}
          {agentUsage?.error && <div className="text-red-600 dark:text-red-400">{agentUsage.error}</div>}
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
              className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
              placeholder="Tool name"
              value={perTool}
              onChange={(e) => setPerTool(e.target.value)}
            />
            <input aria-label="Days"
              type="number"
              className="w-20 px-3 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
            <button
              onClick={() => fetch("tool", () => callApi("get", `${BASE}/${perTool}/analytics?days=${days}`), setToolStats)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              {loading === "tool" ? "…" : "Fetch Stats"}
            </button>
          </div>
          
          {toolStats && !toolStats.error && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
                {[
                  ["Calls", toolStats.total_calls, "text-blue-600 dark:text-blue-400"],
                  ["Successes", toolStats.success_count, "text-green-600 dark:text-green-400"],
                  ["Failures", toolStats.failure_count, "text-red-600 dark:text-red-400"],
                  ["Avg Latency", toolStats.avg_latency_ms != null ? `${toolStats.avg_latency_ms}ms` : "—", "text-yellow-600 dark:text-yellow-400"],
                  ["Unique Agents", toolStats.unique_agents, "text-gray-900 dark:text-white"],
                ].map(([l, v, c]) => (
                  <MetricCard key={String(l)} label={String(l)} value={v} color={String(c)} />
                ))}
              </div>
              <JsonBox data={toolStats} />
            </>
          )}
          {toolStats?.error && <div className="text-red-600 dark:text-red-400">{toolStats.error}</div>}
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
    <div className={`bg-gray-50 dark:bg-[#0f1117] transition-colors duration-200 ${embedded ? '' : 'min-h-screen'}`}>
      {/* Header - Hidden when embedded */}
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
      <div className={`bg-white dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] ${embedded ? '' : 'px-6'}`}>
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
      <div className={embedded ? '' : 'p-6'}>
        {active === 0 && <MarketplaceTab />}
        {active === 1 && <ToolsTab />}
        {active === 2 && <VersionsTab />}
        {active === 3 && <SunsetTab />}
        {active === 4 && <AnalyticsTab />}
      </div>
    </div>
  );
}