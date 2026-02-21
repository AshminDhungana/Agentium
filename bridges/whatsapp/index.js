'use strict';

const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion,
    makeCacheableSignalKeyStore,
    isJidBroadcast,
} = require('@whiskeysockets/baileys');
const { Boom }   = require('@hapi/boom');
const WebSocket  = require('ws');
const express    = require('express');
const pino       = require('pino');

// ── Config ────────────────────────────────────────────────────────────────────
const PORT         = parseInt(process.env.PORT        || '3001', 10);
const BRIDGE_TOKEN = process.env.BRIDGE_TOKEN         || null;   // null = no auth
const AUTH_DIR     = process.env.AUTH_DIR             || './auth_info';
const LOG_LEVEL    = process.env.LOG_LEVEL            || 'info';

const logger = pino({ level: LOG_LEVEL, transport: { target: 'pino-pretty' } });
const baileysLogger = pino({ level: 'silent' }); // suppress Baileys internal logs

// ── State ─────────────────────────────────────────────────────────────────────
/** @type {Set<WebSocket>} Connected Python backend clients */
const clients = new Set();

let sock            = null;
let currentQR       = null;
let qrExpiresAt     = null;
let isConnected     = false;
let isAuthenticated = false;
let reconnectTimer  = null;

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Normalise a phone number or JID into a full WhatsApp JID */
function toJid(recipient) {
    if (recipient.includes('@')) return recipient;              // already a JID
    return recipient.replace(/[^0-9]/g, '') + '@s.whatsapp.net';
}

/** Send a JSON event to every connected backend client */
function broadcast(event, payload = {}) {
    const msg = JSON.stringify({ event, ...payload });
    for (const ws of clients) {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(msg);
        }
    }
}

/** Build the current status snapshot */
function statusSnapshot() {
    return {
        event:          'status',
        connected:      isConnected,
        authenticated:  isAuthenticated,
        qr_code:        currentQR,
        qr_expires_at:  qrExpiresAt,
    };
}

// ── Baileys WhatsApp connection ───────────────────────────────────────────────

async function startWhatsApp() {
    clearTimeout(reconnectTimer);

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version }          = await fetchLatestBaileysVersion();

    logger.info({ version }, '[Bridge] Starting WhatsApp connection');

    sock = makeWASocket({
        version,
        logger:          baileysLogger,
        auth:            {
            creds: state.creds,
            keys:  makeCacheableSignalKeyStore(state.keys, baileysLogger),
        },
        browser:         ['Agentium', 'Chrome', '120.0.0'],
        printQRInTerminal: true,   // handy for debugging via docker logs
        generateHighQualityLinkPreview: false,
        syncFullHistory: false,
    });

    // ── Persist credentials whenever they change ───────────────────────────
    sock.ev.on('creds.update', saveCreds);

    // ── Connection lifecycle ───────────────────────────────────────────────
    sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {

        if (qr) {
            currentQR       = qr;
            qrExpiresAt     = new Date(Date.now() + 60_000).toISOString();
            isAuthenticated = false;
            logger.info('[Bridge] QR code ready — scan with WhatsApp');
            broadcast('qr', { qr_code: qr, qr_expires_at: qrExpiresAt });
        }

        if (connection === 'open') {
            currentQR       = null;
            qrExpiresAt     = null;
            isConnected     = true;
            isAuthenticated = true;
            logger.info('[Bridge] ✅ WhatsApp connected & authenticated');
            broadcast('authenticated', { connected: true, authenticated: true });
        }

        if (connection === 'close') {
            isConnected     = false;
            isAuthenticated = false;
            const statusCode = (lastDisconnect?.error instanceof Boom)
                ? lastDisconnect.error.output.statusCode
                : 0;
            const loggedOut = statusCode === DisconnectReason.loggedOut;

            logger.warn({ statusCode, loggedOut }, '[Bridge] Connection closed');
            broadcast('disconnected', { connected: false, authenticated: false, status_code: statusCode });

            if (loggedOut) {
                // Auth is no longer valid — clear QR state so UI re-prompts
                currentQR   = null;
                qrExpiresAt = null;
                logger.warn('[Bridge] Logged out — auth cleared. Reconnecting for fresh QR…');
            }

            // Always attempt to reconnect (fresh QR if logged out, resume if transient)
            reconnectTimer = setTimeout(startWhatsApp, 5_000);
        }
    });

    // ── Forward inbound messages to backend ───────────────────────────────
    sock.ev.on('messages.upsert', ({ messages, type }) => {
        if (type !== 'notify') return;

        for (const msg of messages) {
            if (msg.key.fromMe)              continue;  // ignore self
            if (isJidBroadcast(msg.key.remoteJid)) continue;  // ignore broadcast lists

            const text =
                msg.message?.conversation                     ||
                msg.message?.extendedTextMessage?.text        ||
                msg.message?.imageMessage?.caption            ||
                msg.message?.videoMessage?.caption            ||
                msg.message?.documentMessage?.caption         ||
                '[non-text message]';

            const payload = {
                event:        'message',
                sender_id:    msg.key.remoteJid,
                sender_name:  msg.pushName || msg.key.remoteJid,
                content:      text,
                message_type: 'text',
                timestamp:    msg.messageTimestamp
                    ? new Date(Number(msg.messageTimestamp) * 1000).toISOString()
                    : new Date().toISOString(),
            };

            logger.debug({ from: payload.sender_id }, '[Bridge] Inbound message');
            broadcast('message', payload);
        }
    });
}

// ── WebSocket server (Python backend connects here) ───────────────────────────

const app = express();
app.use(express.json());

const wss = new WebSocket.Server({ noServer: true });

wss.on('connection', (ws, req) => {
    // ── Optional token auth ────────────────────────────────────────────────
    if (BRIDGE_TOKEN) {
        const url   = new URL(req.url, `http://localhost:${PORT}`);
        const token = url.searchParams.get('token')
            || (req.headers['authorization'] || '').replace('Bearer ', '').trim();

        if (token !== BRIDGE_TOKEN) {
            logger.warn('[Bridge] Rejected unauthorised connection');
            ws.close(4001, 'Unauthorized');
            return;
        }
    }

    logger.info('[Bridge] Backend client connected');
    clients.add(ws);

    // Send current state immediately so the backend can update channel status
    ws.send(JSON.stringify(statusSnapshot()));

    // ── Handle commands from Python backend ────────────────────────────────
    ws.on('message', async (raw) => {
        let cmd;
        try {
            cmd = JSON.parse(raw);
        } catch {
            ws.send(JSON.stringify({ event: 'error', message: 'Invalid JSON' }));
            return;
        }

        // ── action: status — return current state ──────────────────────────
        if (cmd.action === 'status') {
            ws.send(JSON.stringify(statusSnapshot()));
            return;
        }

        // ── action: send — send a WhatsApp message ─────────────────────────
        if (cmd.action === 'send') {
            if (!sock || !isAuthenticated) {
                ws.send(JSON.stringify({ event: 'send_error', message: 'Not authenticated' }));
                return;
            }
            try {
                const jid = toJid(cmd.recipient);
                await sock.sendMessage(jid, { text: cmd.content });
                ws.send(JSON.stringify({ event: 'send_ok', recipient: cmd.recipient }));
                logger.debug({ to: jid }, '[Bridge] Message sent');
            } catch (err) {
                logger.error({ err }, '[Bridge] Send failed');
                ws.send(JSON.stringify({ event: 'send_error', message: err.message }));
            }
            return;
        }

        ws.send(JSON.stringify({ event: 'error', message: `Unknown action: ${cmd.action}` }));
    });

    ws.on('close', () => {
        clients.delete(ws);
        logger.info('[Bridge] Backend client disconnected');
    });

    ws.on('error', (err) => {
        logger.error({ err }, '[Bridge] WebSocket error');
        clients.delete(ws);
    });
});

// ── HTTP endpoints ────────────────────────────────────────────────────────────

/** Health check — used by Docker healthcheck */
app.get('/health', (_req, res) => res.json({ ok: true }));

/** Current bridge status */
app.get('/status', (_req, res) => {
    res.json({
        connected:     isConnected,
        authenticated: isAuthenticated,
        has_qr:        !!currentQR,
        qr_expires_at: qrExpiresAt,
    });
});

// ── Start server ──────────────────────────────────────────────────────────────

const server = app.listen(PORT, () => {
    logger.info(`[Bridge] Listening on port ${PORT}`);
    startWhatsApp().catch((err) => {
        logger.error({ err }, '[Bridge] Fatal startup error');
        process.exit(1);
    });
});

// Upgrade HTTP → WebSocket
server.on('upgrade', (req, socket, head) => {
    wss.handleUpgrade(req, socket, head, (ws) => {
        wss.emit('connection', ws, req);
    });
});

// Graceful shutdown
process.on('SIGTERM', () => {
    logger.info('[Bridge] SIGTERM received — shutting down');
    server.close(() => process.exit(0));
});