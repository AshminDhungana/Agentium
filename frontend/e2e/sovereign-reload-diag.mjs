// One-off diagnostic (not committed): reproduce the post-reload failure and
// capture console/pageerror/response evidence.
import { chromium } from 'playwright';

const FRONTEND_URL = process.env.FRONTEND_URL ?? 'http://localhost:3000';
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000';

const login = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin' }),
});
const token = (await login.json())?.access_token;
if (!token) { console.error('login failed', login.status); process.exit(1); }

const browser = await chromium.launch();
try {
    const page = await browser.newPage();
    page.on('console', (m) => {
        if (['error', 'warning'].includes(m.type())) console.log(`[console.${m.type()}] ${m.text()}`);
    });
    page.on('pageerror', (e) => console.log(`[pageerror] ${e.message}\n${e.stack ?? ''}`));
    page.on('response', (r) => {
        if (r.status() >= 400) console.log(`[response ${r.status()}] ${r.request().method()} ${r.url()}`);
    });

    await page.goto(`${FRONTEND_URL}/login`, { waitUntil: 'domcontentloaded' });
    await page.evaluate((t) => localStorage.setItem('access_token', t), token);
    await page.goto(`${FRONTEND_URL}/sovereign`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('text=Sovereign Control Panel', { timeout: 15_000 });
    console.log('first load: OK');

    await page.reload({ waitUntil: 'domcontentloaded' });
    try {
        await page.waitForSelector('text=Sovereign Control Panel', { timeout: 20_000 });
        console.log('reload: OK');
    } catch {
        console.log('reload: FAILED to show Control Panel');
        console.log('url:', page.url());
        const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 1500));
        console.log('body text:\n' + bodyText);
        await page.screenshot({ path: 'E:/Ongoing Projects/Agentium/frontend/e2e/reload-fail.png', fullPage: true });
        console.log('screenshot saved');
    }
} finally {
    await browser.close();
}
