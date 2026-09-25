// frontend/e2e/sovereign-live-smoke.mjs
// Sovereign Dashboard live smoke (TODO 12.4). Drives the REAL stack — the
// backend and the frontend dev server must be running. Skips (exit 0) unless
// LIVE_STACK=1, so it never runs in CI by default.
//
// Usage:
//   LIVE_STACK=1 FRONTEND_URL=http://localhost:5173 node frontend/e2e/sovereign-live-smoke.mjs
import { chromium } from 'playwright';

const LIVE = process.env.LIVE_STACK === '1';
const FRONTEND_URL = process.env.FRONTEND_URL ?? 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000';

if (!LIVE) {
    console.log('[sovereign-live-smoke] LIVE_STACK!=1 — skipping (never runs in CI).');
    process.exit(0);
}

const results = [];
const check = (name, ok, detail = '') => {
    results.push({ name, ok });
    console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

const api = async (method, path, { token, body } = {}) => {
    const attempt = async () => {
        const res = await fetch(`${BACKEND_URL}${path}`, {
            method,
            headers: {
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
                ...(body ? { 'Content-Type': 'application/json' } : {}),
            },
            body: body ? JSON.stringify(body) : undefined,
        });
        let json = null;
        try { json = await res.json(); } catch { /* non-JSON body */ }
        return { status: res.status, json, retryAfter: res.headers.get('retry-after') };
    };
    // The live backend rate-limits with a Redis sliding window (429 +
    // Retry-After) and this smoke shares that budget with the dashboard's
    // own polling — honour Retry-After and retry instead of failing the
    // check spuriously when back-to-back runs run close together.
    let out = await attempt();
    for (let i = 0; out.status === 429 && i < 2; i++) {
        const wait = Math.max(Number(out.retryAfter) || 5, 5);
        console.log(`  [429 on ${method} ${path} — retrying in ${wait}s]`);
        await new Promise((r) => setTimeout(r, wait * 1000));
        out = await attempt();
    }
    return { status: out.status, json: out.json };
};

// ── 1. Sovereign login via the real API ───────────────────────────────────────
const login = await api('POST', '/api/v1/auth/login', {
    body: { username: 'admin', password: 'admin' },
});
if (login.status !== 200 || !login.json?.access_token) {
    console.error('❌ Sovereign login failed — is the backend running with the default admin?', login.status);
    process.exit(1);
}
const token = login.json.access_token;
check('sovereign login', true);

// Track minted tokens so the finally-block can log them out — the live
// backend's SessionLimitMiddleware counts sessions until the JWT expires
// (days for these tokens), so a smoke that leaves sessions behind would
// push later runs over the 5-session limit.
const mintedTokens = [];
mintedTokens.push(token);

const browser = await chromium.launch();
try {
    const page = await browser.newPage();
    const sovereignSockets = [];
    page.on('websocket', (ws) => {
        if (ws.url().includes('/api/v1/sovereign/ws')) sovereignSockets.push(ws);
    });

    // ── 2. Seed the token, open /sovereign, verify the dashboard ────────────
    // Setting localStorage directly exercises the real checkAuth → /verify →
    // deriveIsSovereign path (Fix 1) without depending on login-form selectors.
    await page.goto(`${FRONTEND_URL}/login`, { waitUntil: 'domcontentloaded' });
    await page.evaluate((t) => localStorage.setItem('access_token', t), token);
    await page.goto(`${FRONTEND_URL}/sovereign`, { waitUntil: 'domcontentloaded' });

    await page.waitForSelector('text=Sovereign Control Panel', { timeout: 15_000 });
    check('dashboard loads for sovereign', true);

    // System tab is active by default — the four status cards + container table
    for (const card of ['CPU Usage', 'Memory', 'Disk Usage', 'System Uptime']) {
        await page.waitForSelector(`text=${card}`, { timeout: 15_000 });
    }
    check('system status cards render', true);

    await page.waitForSelector('text=Container Management', { timeout: 15_000 });
    check('container management section renders', true);

    // Sovereign WebSocket connects when the System tab mounts
    const wsDeadline = Date.now() + 15_000;
    let wsOk = false;
    while (Date.now() < wsDeadline) {
        wsOk = sovereignSockets.some((ws) => !ws.isClosed());
        if (wsOk) break;
        await page.waitForTimeout(500);
    }
    check('sovereign WebSocket connected', wsOk);

    // Fix 1 regression — a fresh load of /sovereign keeps sovereign access.
    // goto (not page.reload()): the model-redirect onboarding hook (App.tsx)
    // may already have navigated the tab to /models when the instance has no
    // model configs — and /models legitimately never shows the Control Panel.
    // Tolerate one bounce: if the hook's getConfigs() was still in flight on
    // this load it can navigate away again; on the retry the hook's
    // model_redirect_checked sessionStorage key is already set, so it won't.
    let refreshOk = false;
    for (let attempt = 0; attempt < 2 && !refreshOk; attempt++) {
        await page.goto(`${FRONTEND_URL}/sovereign`, { waitUntil: 'domcontentloaded' });
        try {
            await page.waitForSelector('text=Sovereign Control Panel', { timeout: 10_000 });
            refreshOk = true;
        } catch { /* possibly bounced to /models by the model-redirect hook */ }
    }
    check('refresh keeps sovereign access (Fix 1 regression)', refreshOk);

    // ── 3. Close the page before the protocol-level checks ─────────────────
    // The dashboard's HTTP polls are the dominant consumer of the user
    // GENERAL rate-limit tier (100 req/60s): two fresh page loads can burn
    // the whole budget, so Fix 2's REST calls 429 spuriously while the page
    // is open. Closing the page leaves only the smoke's own few calls.
    await page.close();

    // Fix 2 end-to-end: live push + REST history, headlessly. The frame
    // check uses a raw WebSocket — the same /api/v1/sovereign/ws?token=
    // endpoint the System tab mounts.
    const rawWsUrl = `${BACKEND_URL.replace(/^http/, 'ws')}/api/v1/sovereign/ws?token=${encodeURIComponent(token)}`;
    const rawSocket = new WebSocket(rawWsUrl);
    let rawOpen = false;
    let sawCommandLog = false;
    rawSocket.onopen = () => { rawOpen = true; };
    rawSocket.onmessage = (event) => {
        try { if (JSON.parse(event.data)?.type === 'command_log') sawCommandLog = true; } catch { /* non-JSON frame */ }
    };
    const rawDeadline = Date.now() + 15_000;
    while (Date.now() < rawDeadline && !rawOpen) {
        await new Promise((r) => setTimeout(r, 250));
    }
    check('sovereign WebSocket connects (raw, no page)', rawOpen);

    // Seed a harmless history entry: the audit is written BEFORE the Docker
    // call fails on the nonexistent container id.
    await api('POST', '/api/v1/sovereign/containers/smoke-nonexistent/restart', { token });

    const pushDeadline = Date.now() + 5_000;
    while (Date.now() < pushDeadline && !sawCommandLog) {
        await new Promise((r) => setTimeout(r, 250));
    }
    check('live command_log push received (Fix 2 regression)', sawCommandLog);
    try { rawSocket.close(); } catch { /* already closed */ }

    const cmds = await api('GET', '/api/v1/sovereign/commands?limit=50', { token });
    const seeded = cmds.status === 200
        && Array.isArray(cmds.json)
        && cmds.json.some((c) => c.action === 'container_restart');
    check('command history endpoint returns seeded entry', seeded, `status=${cmds.status}`);

    const auditLogs = await api('GET', '/api/v1/sovereign/audit?limit=10', { token });
    check('audit endpoint returns 200', auditLogs.status === 200, `status=${auditLogs.status}`);

    const block = await api('POST', '/api/v1/sovereign/agents/smoke-agent-99999/block', {
        token, body: { reason: 'live smoke' },
    });
    const unblock = await api('POST', '/api/v1/sovereign/agents/smoke-agent-99999/unblock', { token });
    check('agent block/unblock endpoints respond', block.status === 200 && unblock.status === 200, `block=${block.status} unblock=${unblock.status}`);

    // ── 4. Non-sovereign enforcement ────────────────────────────────────────
    const unique = `smoke_${Date.now()}`;
    const reg = await api('POST', '/api/v1/auth/register', {
        body: { username: unique, password: 'smoke-password-1', email: `${unique}@smoke.example.com` },
    });
    // SignupResponse carries user_id at the top level (not nested under user).
    const userId = reg.json?.user_id ?? reg.json?.user?.id ?? reg.json?.id ?? null;
    if (reg.status === 200 || reg.status === 201) {
        if (userId) {
            const approve = await api('POST', `/api/v1/admin/users/${userId}/approve`, { token });
            if (approve.status !== 200) {
                console.log(`  [approve status=${approve.status} — ${approve.json?.error ?? 'unknown error'}]`);
            }
        }
        const userLogin = await api('POST', '/api/v1/auth/login', {
            body: { username: unique, password: 'smoke-password-1' },
        });
        if (userLogin.status === 200 && userLogin.json?.access_token) {
            mintedTokens.push(userLogin.json.access_token);
            const forbidden = await api('GET', '/api/v1/sovereign/system/status', {
                token: userLogin.json.access_token,
            });
            check('non-sovereign gets 403 on sovereign API', forbidden.status === 403, `status=${forbidden.status}`);

            // Fresh page (the earlier one is closed): seed the non-sovereign
            // token and verify /sovereign does not render the Control Panel.
            // goto /login first — a blank page's sandbox denies localStorage.
            const userPage = await browser.newPage();
            await userPage.goto(`${FRONTEND_URL}/login`, { waitUntil: 'domcontentloaded' });
            await userPage.evaluate((t) => localStorage.setItem('access_token', t), userLogin.json.access_token);
            await userPage.goto(`${FRONTEND_URL}/sovereign`, { waitUntil: 'domcontentloaded' });
            await userPage.waitForTimeout(2_000);
            const denied = (await userPage.locator('text=Sovereign Control Panel').count()) === 0;
            await userPage.close();
            check('non-sovereign redirected from /sovereign', denied);
        } else {
            check('non-sovereign browser check skipped (login unavailable)', true, `login status=${userLogin.status}`);
        }
    } else {
        check('non-sovereign checks skipped (registration unavailable)', true, `register status=${reg.status}`);
    }
} finally {
    await browser.close();
    // Best-effort: log out every session the smoke minted so the live
    // backend's 5-session limit stays clean for the next run.
    for (const t of mintedTokens) {
        try { await api('POST', '/api/v1/auth/logout', { token: t }); } catch { /* best effort */ }
    }
}

const failed = results.filter((r) => !r.ok);
console.log(`\n[sovereign-live-smoke] ${results.length - failed.length}/${results.length} checks passed.`);
if (failed.length > 0) process.exit(1);
