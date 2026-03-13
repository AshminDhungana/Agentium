/**
 * BrowserTaskPanel.tsx — Phase 10.1 Frontend
 *
 * Displays live browser task progress with periodic screenshot refresh.
 * Uses polling against /api/v1/browser/screenshot to show the current page state.
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

const BrowserTaskPanel: React.FC = () => {
  const [task, setTask] = useState<BrowserTask>({
    id: '',
    url: '',
    status: 'idle',
    title: '',
    screenshot: '',
    startedAt: 0,
  });
  const [urlInput, setUrlInput] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(5);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Get auth token from localStorage
  const getAuthHeaders = useCallback((): Record<string, string> => {
    const token = localStorage.getItem('token');
    return token
      ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
      : { 'Content-Type': 'application/json' };
  }, []);

  // Start elapsed timer
  useEffect(() => {
    if (task.status === 'navigating' || task.status === 'capturing') {
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - task.startedAt) / 1000));
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
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
    return () => {
      if (refreshRef.current) clearInterval(refreshRef.current);
    };
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
        setTask((prev) => ({
          ...prev,
          status: 'error',
          error: err.detail || 'Screenshot failed',
        }));
        return;
      }
      const data = await res.json();
      setTask((prev) => ({
        ...prev,
        screenshot: data.image_base64,
        status: 'complete',
      }));
    } catch (err: any) {
      setTask((prev) => ({
        ...prev,
        status: 'error',
        error: err.message || 'Network error',
      }));
    }
  };

  const handleNavigate = async () => {
    if (!urlInput.trim()) return;

    const url = urlInput.startsWith('http') ? urlInput : `https://${urlInput}`;
    setTask({
      id: Date.now().toString(),
      url,
      status: 'navigating',
      title: '',
      screenshot: '',
      startedAt: Date.now(),
    });
    setElapsed(0);

    try {
      // First navigate to get page info
      const navRes = await fetch(`${API_BASE}/browser/navigate`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ url, agent_id: 'browser-ui' }),
      });

      if (!navRes.ok) {
        const err = await navRes.json().catch(() => ({ detail: 'Navigation failed' }));
        setTask((prev) => ({
          ...prev,
          status: 'error',
          error: err.detail || 'Navigation failed',
        }));
        return;
      }

      const navData = await navRes.json();
      setTask((prev) => ({
        ...prev,
        title: navData.title || '',
        status: 'capturing',
      }));

      // Then capture screenshot
      await captureScreenshot(url);
    } catch (err: any) {
      setTask((prev) => ({
        ...prev,
        status: 'error',
        error: err.message || 'Network error',
      }));
    }
  };

  const handleStop = () => {
    setAutoRefresh(false);
    setTask((prev) => ({ ...prev, status: 'idle' }));
    if (refreshRef.current) clearInterval(refreshRef.current);
    if (timerRef.current) clearInterval(timerRef.current);
  };

  const statusColor: Record<string, string> = {
    idle: '#6b7280',
    navigating: '#f59e0b',
    capturing: '#3b82f6',
    complete: '#10b981',
    error: '#ef4444',
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          <h3 style={styles.title}>Browser Task Monitor</h3>
        </div>
        <div
          style={{
            ...styles.statusBadge,
            backgroundColor: `${statusColor[task.status]}20`,
            color: statusColor[task.status],
            borderColor: statusColor[task.status],
          }}
        >
          {task.status.toUpperCase()}
        </div>
      </div>

      {/* URL Input Bar */}
      <div style={styles.inputBar}>
        <input
          type="text"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleNavigate()}
          placeholder="Enter URL to browse…"
          style={styles.urlInput}
        />
        <button
          onClick={handleNavigate}
          disabled={task.status === 'navigating' || task.status === 'capturing'}
          style={{
            ...styles.goButton,
            opacity: task.status === 'navigating' || task.status === 'capturing' ? 0.5 : 1,
          }}
        >
          {task.status === 'navigating' || task.status === 'capturing' ? '⏳' : '→'}
        </button>
      </div>

      {/* Controls */}
      <div style={styles.controls}>
        <label style={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            style={styles.checkbox}
          />
          Auto-refresh every
          <select
            value={refreshInterval}
            onChange={(e) => setRefreshInterval(Number(e.target.value))}
            style={styles.select}
          >
            <option value={3}>3s</option>
            <option value={5}>5s</option>
            <option value={10}>10s</option>
            <option value={30}>30s</option>
          </select>
        </label>
        {task.status !== 'idle' && (
          <div style={styles.taskInfo}>
            <span style={styles.elapsed}>⏱ {elapsed}s</span>
            <button onClick={handleStop} style={styles.stopButton}>
              Stop
            </button>
          </div>
        )}
      </div>

      {/* Page Title */}
      {task.title && (
        <div style={styles.pageTitle}>
          <span style={styles.pageTitleLabel}>Page:</span> {task.title}
        </div>
      )}

      {/* Screenshot Display */}
      <div style={styles.screenshotContainer}>
        {task.screenshot ? (
          <img
            src={`data:image/png;base64,${task.screenshot}`}
            alt="Browser screenshot"
            style={styles.screenshot}
          />
        ) : task.status === 'error' ? (
          <div style={styles.errorBox}>
            <span style={styles.errorIcon}>⚠️</span>
            <p style={styles.errorText}>{task.error || 'Unknown error'}</p>
          </div>
        ) : task.status === 'navigating' || task.status === 'capturing' ? (
          <div style={styles.loadingBox}>
            <div style={styles.spinner} />
            <p style={styles.loadingText}>
              {task.status === 'navigating' ? 'Navigating…' : 'Capturing screenshot…'}
            </p>
          </div>
        ) : (
          <div style={styles.placeholder}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#4b5563" strokeWidth="1.5">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
              <line x1="8" y1="21" x2="16" y2="21" />
              <line x1="12" y1="17" x2="12" y2="21" />
            </svg>
            <p style={styles.placeholderText}>Enter a URL above to start browsing</p>
          </div>
        )}
      </div>

      {/* URL display */}
      {task.url && (
        <div style={styles.urlDisplay}>
          <span style={styles.urlLabel}>URL:</span>
          <a href={task.url} target="_blank" rel="noopener noreferrer" style={styles.urlLink}>
            {task.url}
          </a>
        </div>
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    background: 'linear-gradient(135deg, #1e1b2e 0%, #1a1a2e 100%)',
    borderRadius: '12px',
    border: '1px solid rgba(139, 92, 246, 0.2)',
    padding: '20px',
    fontFamily: "'Inter', -apple-system, sans-serif",
    color: '#e2e8f0',
    maxWidth: '900px',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  title: {
    margin: 0,
    fontSize: '16px',
    fontWeight: 600,
    color: '#f1f5f9',
  },
  statusBadge: {
    fontSize: '11px',
    fontWeight: 700,
    padding: '3px 10px',
    borderRadius: '6px',
    border: '1px solid',
    letterSpacing: '0.5px',
  },
  inputBar: {
    display: 'flex',
    gap: '8px',
    marginBottom: '12px',
  },
  urlInput: {
    flex: 1,
    background: 'rgba(255, 255, 255, 0.05)',
    border: '1px solid rgba(139, 92, 246, 0.3)',
    borderRadius: '8px',
    padding: '10px 14px',
    color: '#e2e8f0',
    fontSize: '14px',
    outline: 'none',
  },
  goButton: {
    background: 'linear-gradient(135deg, #7c3aed, #6d28d9)',
    border: 'none',
    borderRadius: '8px',
    color: 'white',
    padding: '10px 16px',
    fontSize: '16px',
    cursor: 'pointer',
    fontWeight: 700,
  },
  controls: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
    fontSize: '13px',
    color: '#94a3b8',
  },
  checkboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    cursor: 'pointer',
  },
  checkbox: {
    accentColor: '#7c3aed',
  },
  select: {
    background: 'rgba(255, 255, 255, 0.05)',
    border: '1px solid rgba(139, 92, 246, 0.3)',
    borderRadius: '4px',
    color: '#e2e8f0',
    padding: '2px 6px',
    marginLeft: '4px',
    fontSize: '12px',
  },
  taskInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  elapsed: {
    color: '#a78bfa',
    fontVariantNumeric: 'tabular-nums',
    fontWeight: 500,
  },
  stopButton: {
    background: 'rgba(239, 68, 68, 0.15)',
    border: '1px solid rgba(239, 68, 68, 0.4)',
    borderRadius: '6px',
    color: '#f87171',
    padding: '4px 12px',
    fontSize: '12px',
    cursor: 'pointer',
    fontWeight: 600,
  },
  pageTitle: {
    fontSize: '13px',
    color: '#94a3b8',
    marginBottom: '12px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  pageTitleLabel: {
    color: '#64748b',
    fontWeight: 600,
  },
  screenshotContainer: {
    background: 'rgba(0, 0, 0, 0.3)',
    borderRadius: '8px',
    border: '1px solid rgba(255, 255, 255, 0.05)',
    minHeight: '300px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    marginBottom: '12px',
  },
  screenshot: {
    width: '100%',
    height: 'auto',
    display: 'block',
    borderRadius: '8px',
  },
  placeholder: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: '12px',
    padding: '40px',
  },
  placeholderText: {
    color: '#4b5563',
    fontSize: '14px',
    margin: 0,
  },
  loadingBox: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: '12px',
    padding: '40px',
  },
  spinner: {
    width: '32px',
    height: '32px',
    border: '3px solid rgba(139, 92, 246, 0.2)',
    borderTop: '3px solid #a78bfa',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  loadingText: {
    color: '#94a3b8',
    fontSize: '14px',
    margin: 0,
  },
  errorBox: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: '8px',
    padding: '40px',
  },
  errorIcon: {
    fontSize: '28px',
  },
  errorText: {
    color: '#f87171',
    fontSize: '14px',
    margin: 0,
    textAlign: 'center' as const,
    maxWidth: '300px',
  },
  urlDisplay: {
    fontSize: '12px',
    color: '#64748b',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  urlLabel: {
    fontWeight: 600,
    marginRight: '4px',
  },
  urlLink: {
    color: '#818cf8',
    textDecoration: 'none',
  },
};

export default BrowserTaskPanel;
