/**
 * BrowserTaskPanel.tsx 
 *
 * Displays live browser task progress with periodic screenshot refresh.
 * Uses polling against /api/v1/browser/screenshot to show the current page state.
 *
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';

interface BrowserTask {
  id: string;
  url: string;
  status: 'idle' | 'navigating' | 'capturing' | 'complete' | 'error';
  title: string;
  screenshot: string; // base64 PNG
  startedAt: number;
  error?: string;
}

const API_BASE = '/api/v1';

// Maps each status to a self-contained Tailwind badge class string
const STATUS_BADGE: Record<string, string> = {
  idle:       'bg-gray-500/10 text-gray-500 border-gray-500/50',
  navigating: 'bg-amber-500/10 text-amber-500 border-amber-500/50',
  capturing:  'bg-blue-500/10  text-blue-500  border-blue-500/50',
  complete:   'bg-emerald-500/10 text-emerald-500 border-emerald-500/50',
  error:      'bg-red-500/10   text-red-500   border-red-500/50',
};

const BrowserTaskPanel: React.FC = () => {
  const [task, setTask] = useState<BrowserTask>({
    id: '',
    url: '',
    status: 'idle',
    title: '',
    screenshot: '',
    startedAt: 0,
  });
  const [urlInput, setUrlInput]         = useState('');
  const [autoRefresh, setAutoRefresh]   = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(5);
  const [elapsed, setElapsed]           = useState(0);
  const timerRef   = useRef<ReturnType<typeof setInterval> | null>(null);
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const getAuthHeaders = useCallback((): Record<string, string> => {
    const token = localStorage.getItem('token');
    return token
      ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
      : { 'Content-Type': 'application/json' };
  }, []);

  // Elapsed timer
  useEffect(() => {
    if (task.status === 'navigating' || task.status === 'capturing') {
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - task.startedAt) / 1000));
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [task.status, task.startedAt]);

  // Auto-refresh screenshots
  useEffect(() => {
    if (autoRefresh && task.url && task.status !== 'error') {
      refreshRef.current = setInterval(() => {
        captureScreenshot(task.url);
      }, refreshInterval * 1000);
    } else {
      if (refreshRef.current) clearInterval(refreshRef.current);
    }
    return () => { if (refreshRef.current) clearInterval(refreshRef.current); };
  }, [autoRefresh, task.url, refreshInterval, task.status]);

  const captureScreenshot = async (url: string) => {
    try {
      setTask((prev) => ({ ...prev, status: 'capturing' }));
      const res = await fetch(`${API_BASE}/browser/screenshot`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ url, agent_id: 'browser-ui' }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Screenshot failed' }));
        setTask((prev) => ({ ...prev, status: 'error', error: err.detail || 'Screenshot failed' }));
        return;
      }
      const data = await res.json();
      setTask((prev) => ({ ...prev, screenshot: data.image_base64, status: 'complete' }));
    } catch (err: any) {
      setTask((prev) => ({ ...prev, status: 'error', error: err.message || 'Network error' }));
    }
  };

  const handleNavigate = async () => {
    if (!urlInput.trim()) return;
    const url = urlInput.startsWith('http') ? urlInput : `https://${urlInput}`;
    setTask({ id: Date.now().toString(), url, status: 'navigating', title: '', screenshot: '', startedAt: Date.now() });
    setElapsed(0);

    try {
      const navRes = await fetch(`${API_BASE}/browser/navigate`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ url, agent_id: 'browser-ui' }),
      });
      if (!navRes.ok) {
        const err = await navRes.json().catch(() => ({ detail: 'Navigation failed' }));
        setTask((prev) => ({ ...prev, status: 'error', error: err.detail || 'Navigation failed' }));
        return;
      }
      const navData = await navRes.json();
      setTask((prev) => ({ ...prev, title: navData.title || '', status: 'capturing' }));
      await captureScreenshot(url);
    } catch (err: any) {
      setTask((prev) => ({ ...prev, status: 'error', error: err.message || 'Network error' }));
    }
  };

  const handleStop = () => {
    setAutoRefresh(false);
    setTask((prev) => ({ ...prev, status: 'idle' }));
    if (refreshRef.current) clearInterval(refreshRef.current);
    if (timerRef.current)   clearInterval(timerRef.current);
  };

  const isBusy = task.status === 'navigating' || task.status === 'capturing';

  return (
    <div className="bg-white dark:bg-[#1a1a2e] rounded-xl border border-gray-200 dark:border-violet-500/20 p-5 font-sans text-gray-800 dark:text-slate-200 max-w-4xl">

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-2.5">
          <svg
            width="20" height="20" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth="2"
            className="text-violet-400 shrink-0"
          >
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          <h3 className="m-0 text-base font-semibold text-gray-900 dark:text-slate-100">
            Browser Task Monitor
          </h3>
        </div>
        <span className={`text-[11px] font-bold px-2.5 py-0.5 rounded-md border tracking-wide ${STATUS_BADGE[task.status]}`}>
          {task.status.toUpperCase()}
        </span>
      </div>

      {/* ── URL input bar ─────────────────────────────────────────────────── */}
      <div className="flex gap-2 mb-3">
        <input
          type="text"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleNavigate()}
          placeholder="Enter URL to browse…"
          className="
            flex-1 bg-gray-50 dark:bg-white/5
            border border-gray-300 dark:border-violet-500/30
            rounded-lg px-3.5 py-2.5 text-sm
            text-gray-900 dark:text-slate-200
            placeholder-gray-400 dark:placeholder-gray-500
            outline-none focus:ring-2 focus:ring-violet-500/40
            transition-colors
          "
        />
        <button
          onClick={handleNavigate}
          disabled={isBusy}
          className="
            bg-gradient-to-br from-violet-600 to-violet-700
            hover:from-violet-500 hover:to-violet-600
            disabled:opacity-50 disabled:cursor-not-allowed
            text-white rounded-lg px-4 py-2.5
            text-base font-bold cursor-pointer transition-all
          "
        >
          {isBusy ? '⏳' : '→'}
        </button>
      </div>

      {/* ── Controls ──────────────────────────────────────────────────────── */}
      <div className="flex justify-between items-center mb-3 text-sm text-gray-500 dark:text-slate-400">
        <label className="flex items-center gap-1.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            className="accent-violet-600"
          />
          Auto-refresh every
          <select
            value={refreshInterval}
            onChange={(e) => setRefreshInterval(Number(e.target.value))}
            className="
              ml-1 bg-gray-100 dark:bg-white/5
              border border-gray-300 dark:border-violet-500/30
              rounded px-1.5 py-0.5 text-xs
              text-gray-700 dark:text-slate-200
            "
          >
            <option value={3}>3s</option>
            <option value={5}>5s</option>
            <option value={10}>10s</option>
            <option value={30}>30s</option>
          </select>
        </label>

        {task.status !== 'idle' && (
          <div className="flex items-center gap-2.5">
            <span className="text-violet-500 dark:text-violet-400 tabular-nums font-medium">
              ⏱ {elapsed}s
            </span>
            <button
              onClick={handleStop}
              className="
                bg-red-500/10 border border-red-500/40
                text-red-500 dark:text-red-400
                rounded-md px-3 py-1 text-xs font-semibold
                hover:bg-red-500/20 transition-colors cursor-pointer
              "
            >
              Stop
            </button>
          </div>
        )}
      </div>

      {/* ── Page title ────────────────────────────────────────────────────── */}
      {task.title && (
        <p className="text-sm text-gray-500 dark:text-slate-400 mb-3 truncate">
          <span className="font-semibold text-gray-400 dark:text-slate-500">Page:</span>{' '}
          {task.title}
        </p>
      )}

      {/* ── Screenshot area ───────────────────────────────────────────────── */}
      <div className="
        bg-gray-100 dark:bg-black/30
        rounded-lg border border-gray-200 dark:border-white/5
        min-h-[300px] flex items-center justify-center
        overflow-hidden mb-3
      ">
        {task.screenshot ? (
          <img
            src={`data:image/png;base64,${task.screenshot}`}
            alt="Browser screenshot"
            className="w-full h-auto block rounded-lg"
          />
        ) : task.status === 'error' ? (
          <div className="flex flex-col items-center gap-2 p-10">
            <span className="text-3xl">⚠️</span>
            <p className="text-red-500 dark:text-red-400 text-sm text-center max-w-xs m-0">
              {task.error || 'Unknown error'}
            </p>
          </div>
        ) : isBusy ? (
          <div className="flex flex-col items-center gap-3 p-10">
            {/* Spinner — kept as inline style only for the asymmetric border trick */}
            <div
              className="w-8 h-8 rounded-full animate-spin"
              style={{
                border: '3px solid rgba(139, 92, 246, 0.2)',
                borderTopColor: '#a78bfa',
              }}
            />
            <p className="text-gray-500 dark:text-slate-400 text-sm m-0">
              {task.status === 'navigating' ? 'Navigating…' : 'Capturing screenshot…'}
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 p-10">
            <svg
              width="48" height="48" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth="1.5"
              className="text-gray-300 dark:text-gray-600"
            >
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
              <line x1="8" y1="21" x2="16" y2="21" />
              <line x1="12" y1="17" x2="12" y2="21" />
            </svg>
            <p className="text-gray-400 dark:text-gray-600 text-sm m-0">
              Enter a URL above to start browsing
            </p>
          </div>
        )}
      </div>

      {/* ── Current URL ───────────────────────────────────────────────────── */}
      {task.url && (
        <p className="text-xs text-gray-400 dark:text-slate-500 truncate m-0">
          <span className="font-semibold mr-1">URL:</span>
          <a
            href={task.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-500 dark:text-indigo-400 hover:underline"
          >
            {task.url}
          </a>
        </p>
      )}
    </div>
  );
};

export default BrowserTaskPanel;