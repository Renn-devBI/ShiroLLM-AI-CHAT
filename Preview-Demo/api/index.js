const express = require('express');
const path = require('path');
const fs = require('fs');
const http = require('http');
const https = require('https');

const app = express();

app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// CORS headers untuk akses dari web browser, Vercel, dan klien eksternal
app.use((req, res, next) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Guest-ID, X-Session-ID, X-API-Key, X-UI-Lang');
    if (req.method === 'OPTIONS') {
        return res.status(204).end();
    }
    next();
});

// Middleware normalisasi route untuk Vercel Serverless Function & Edge Rewrites
app.use((req, res, next) => {
    // 1. Jika request dialihkan via Vercel slug query
    if (req.query && req.query.slug) {
        const slugPath = Array.isArray(req.query.slug) ? req.query.slug.join('/') : req.query.slug;
        if (slugPath) {
            req.url = '/api/' + slugPath.replace(/^\/+/, '');
        }
    } else {
        const original = req.headers['x-matched-path'] || 
                         req.headers['x-vercel-matched-path'] || 
                         req.headers['x-forwarded-uri'] || 
                         req.headers['x-original-uri'];
        if (original && original !== '/api/index.js' && original !== '/api/[...slug].js' && !original.includes('/[...slug]')) {
            req.url = original;
        }
    }
    next();
});

// Helper untuk menemukan lokasi berkas relatif
function resolveFilePath(relPath) {
    const candidates = [
        path.join(__dirname, '..', 'public', relPath),
        path.join(__dirname, '..', relPath),
        path.join(__dirname, 'public', relPath),
        path.join(__dirname, relPath),
        path.join(process.cwd(), 'Preview-Demo', 'public', relPath),
        path.join(process.cwd(), 'Preview-Demo', relPath),
        path.join(process.cwd(), 'public', relPath),
        path.join(process.cwd(), relPath)
    ];
    for (const c of candidates) {
        if (fs.existsSync(c)) return c;
    }
    return candidates[0];
}

// Sajikan berkas statis dari folder static
const staticDir = resolveFilePath('static');
app.use('/static', express.static(staticDir));

// Memuat profil AI & User (Static require agar dibundel 100% oleh Vercel)
let bundledAi = null;
let bundledUser = null;
try { bundledAi = require('../profile/ai.json'); } catch (_) {}
try { bundledUser = require('../profile/user.json'); } catch (_) {}

const DEFAULT_SHIRO_PROFILE = {
    name: 'Shiro',
    description: 'AI Assistant & Companion',
    image: "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",
    image_mime: "image/jpeg"
};

function getProfileData() {
    let ai = bundledAi;
    let user = bundledUser;
    if (!ai) {
        try {
            const aiPath = resolveFilePath('profile/ai.json');
            if (fs.existsSync(aiPath)) ai = JSON.parse(fs.readFileSync(aiPath, 'utf8'));
        } catch (_) {}
    }
    if (!ai || !ai.image) {
        ai = DEFAULT_SHIRO_PROFILE;
    }
    if (!user) {
        try {
            const userPath = resolveFilePath('profile/user.json');
            if (fs.existsSync(userPath)) user = JSON.parse(fs.readFileSync(userPath, 'utf8'));
        } catch (_) {}
    }
    return {
        ai: ai || DEFAULT_SHIRO_PROFILE,
        user: user || { name: 'Kakak' }
    };
}

// -------------------------------------------------------------
// KONFIGURASI BACKEND AI SERVER (VPS medium.lynzz.id Port 2223)
// -------------------------------------------------------------
const BACKEND_URL = (
    process.env.SHIRO_BACKEND_URL || 
    process.env.AI_BACKEND_URL || 
    'http://medium.lynzz.id:2223'
).replace(/\/+$/, '');

const FALLBACK_BACKEND_URLS = [
    BACKEND_URL,
    'http://medium.lynzz.id:2223',
    'http://38.49.213.154:2223',
    'https://cloud.lynzz.id/server',
    'http://127.0.0.1:2223',
    'http://127.0.0.1:8080'
].filter((u, i, arr) => u && arr.indexOf(u) === i);

// Helper request HTTP/HTTPS native tanpa dependensi tambahan
function fetchBackend(endpoint, options = {}) {
    return new Promise((resolve, reject) => {
        const fullUrl = endpoint.startsWith('http') ? endpoint : `${BACKEND_URL}${endpoint}`;
        const parsed = new URL(fullUrl);
        const isHttps = parsed.protocol === 'https:';
        const client = isHttps ? https : http;

        const reqOptions = {
            hostname: parsed.hostname,
            port: parsed.port || (isHttps ? 443 : 80),
            path: parsed.pathname + parsed.search,
            method: options.method || 'GET',
            agent: false,
            headers: {
                'Host': `${parsed.hostname}:${parsed.port || (isHttps ? 443 : 80)}`,
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Connection': 'close',
                ...(options.headers || {})
            },
            timeout: options.timeout || 60000
        };

        const req = client.request(reqOptions, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const parsedData = JSON.parse(data);
                    resolve({ status: res.statusCode, ok: res.statusCode >= 200 && res.statusCode < 300, data: parsedData });
                } catch (_) {
                    resolve({ status: res.statusCode, ok: res.statusCode >= 200 && res.statusCode < 300, data: data });
                }
            });
        });

        req.on('error', reject);
        req.on('timeout', () => {
            req.destroy();
            reject(new Error(`Timeout menghubungi server backend ${fullUrl}`));
        });

        if (options.body) {
            req.write(typeof options.body === 'string' ? options.body : JSON.stringify(options.body));
        }
        req.end();
    });
}

// -------------------------------------------------------------
// LOCALIZED OVERLOAD TRAFFIC NOTIFICATION (ID / EN)
// Tanpa menampilkan nama server, hostname, IP, maupun port internal
// -------------------------------------------------------------
function resolveRequestLang(req, store = null) {
    const raw = (
        (req && req.body && req.body.lang) ||
        (req && req.headers && req.headers['x-ui-lang']) ||
        (req && req.query && req.query.lang) ||
        (store && store.ui_language) ||
        'id'
    ).toString().toLowerCase().trim();
    return raw === 'en' ? 'en' : 'id';
}

function getOverloadMessages(lang = 'id') {
    if (lang === 'en') {
        return {
            reply: 'ShiroHaru AI server is currently experiencing traffic overload. Please wait a moment and try again.',
            toast: 'Notice: ShiroHaru AI server is currently experiencing traffic overload.'
        };
    }
    return {
        reply: 'Server ShiroHaru AI saat ini sedang mengalami overload trafik. Silakan tunggu beberapa saat lalu coba kembali.',
        toast: 'Notifikasi: Server ShiroHaru AI sedang overload trafik.'
    };
}

// -------------------------------------------------------------
// ISOLASI SESI GUEST PER-PENGUNJUNG (Cookies / LocalStorage)
// -------------------------------------------------------------
// Memory map guest stores agar percakapan antar pengunjung tidak saling tercampur
const guestStores = new Map();

function parseCookies(cookieHeader) {
    const list = {};
    if (!cookieHeader) return list;
    cookieHeader.split(';').forEach(cookie => {
        const parts = cookie.split('=');
        list[parts.shift().trim()] = decodeURI(parts.join('='));
    });
    return list;
}

function getGuestContext(req) {
    const cookies = parseCookies(req.headers.cookie);
    const guestId = (
        req.headers['x-guest-id'] || 
        req.headers['x-session-id'] || 
        cookies['shiro_guest_id'] || 
        req.query.guest_id || 
        ('guest_' + (req.ip || 'anon').replace(/[^a-zA-Z0-9]/g, '_'))
    ).trim();

    if (!guestStores.has(guestId)) {
        guestStores.set(guestId, {
            activeSessionId: 'session-1',
            ui_language: 'id',
            enable_training_logging: true,
            sessions: {
                'session-1': {
                    id: 'session-1',
                    title: 'Percakapan Baru',
                    pinned: false,
                    last_active: new Date().toISOString(),
                    messages: []
                }
            }
        });
    }

    const store = guestStores.get(guestId);
    const headerLang = req.headers['x-ui-lang'];
    if (headerLang === 'id' || headerLang === 'en') {
        store.ui_language = headerLang;
    }

    // Bersihkan sesi usang jika cache guest melampaui 1000 user aktif
    if (guestStores.size > 1000) {
        const firstKey = guestStores.keys().next().value;
        guestStores.delete(firstKey);
    }

    return { guestId, store };
}

// Pipeline sample trace untuk modal inspektor visual
const { samplePipelineTrace } = require('./mock_data.js');

// -------------------------------------------------------------
// API Endpoints
// -------------------------------------------------------------

// Profile API
app.get(['/api/profile', '/profile'], (req, res) => {
    res.json(getProfileData());
});

app.post(['/api/profile/upload', '/profile/upload'], (req, res) => {
    res.json({ success: true, message: 'Profil berhasil diperbarui' });
});

// Privacy & Settings API
app.get(['/api/settings/privacy', '/settings/privacy'], (req, res) => {
    const { store } = getGuestContext(req);
    res.json({
        enable_training_logging: store.enable_training_logging !== false,
        ui_language: store.ui_language || 'id'
    });
});

app.post(['/api/settings/privacy', '/settings/privacy'], (req, res) => {
    const { store } = getGuestContext(req);
    const body = req.body || {};
    if (body.ui_language === 'id' || body.ui_language === 'en') {
        store.ui_language = body.ui_language;
    }
    if (typeof body.enable_training_logging === 'boolean') {
        store.enable_training_logging = body.enable_training_logging;
    }
    res.json({
        success: true,
        enable_training_logging: store.enable_training_logging !== false,
        ui_language: store.ui_language || 'id'
    });
});

// Memory Count & Stats API
app.get(['/api/memory-count', '/memory-count'], (req, res) => {
    const { store } = getGuestContext(req);
    const totalMsgs = Object.values(store.sessions).reduce((acc, s) => acc + (s.messages || []).length, 0);
    res.json({
        count: Math.max(12, totalMsgs * 2),
        unit: 'fakta'
    });
});

app.get(['/api/stats', '/stats'], (req, res) => {
    const { store } = getGuestContext(req);
    const totalMsgs = Object.values(store.sessions).reduce((acc, s) => acc + (s.messages || []).length, 0);
    res.json({
        total_turns: totalMsgs,
        memory_facts: Math.max(12, totalMsgs * 2),
        uptime_seconds: Math.floor(process.uptime())
    });
});

// -------------------------------------------------------------
// MODEL STATUS & SERVER-ENFORCED MODEL LOCK
// -------------------------------------------------------------
const MASKED_MODEL_NAME = 'ShiroHaru-0.1-Agent';
let cachedServerModel = null;
let lastModelCheck = 0;

async function getLockedServerModel() {
    const now = Date.now();
    if (cachedServerModel && (now - lastModelCheck < 15000)) {
        return cachedServerModel;
    }

    let detected = null;
    for (const bUrl of FALLBACK_BACKEND_URLS) {
        try {
            const resp = await fetchBackend('/api/models', { timeout: 3500 });
            if (resp.ok && resp.data && typeof resp.data === 'object' && (resp.data.current_model || resp.data.active_model || resp.data.models)) {
                detected = resp.data;
                break;
            }
        } catch (_) {}
    }

    const modelObj = {
        id: MASKED_MODEL_NAME,
        name: MASKED_MODEL_NAME,
        display_name: MASKED_MODEL_NAME,
        family: 'ShiroHaru Cognitive Agent',
        active: true,
        locked: true,
        description: 'ShiroHaru-0.1-Agent (Cognitive Reasoning & Companion Engine)'
    };

    const finalModelData = {
        current_model: MASKED_MODEL_NAME,
        active_model: MASKED_MODEL_NAME,
        locked: true,
        available_models: [MASKED_MODEL_NAME],
        models: [modelObj],
        model_info: {
            [MASKED_MODEL_NAME]: modelObj
        },
        message: `Model aktif: ${MASKED_MODEL_NAME}`
    };

    cachedServerModel = finalModelData;
    lastModelCheck = now;
    return finalModelData;
}

// Models API: Mengembalikan model yang sedang di-set oleh Master Server
app.get(['/api/models', '/v1/models', '/v2/models', '/v3/models'], async (req, res) => {
    try {
        const modelData = await getLockedServerModel();
        res.json({
            object: 'list',
            data: (modelData.models || []).map(m => ({
                id: m.id || m.name,
                object: 'model',
                created: Math.floor(Date.now() / 1000),
                owned_by: 'shiro-server',
                locked: true
            })),
            current_model: modelData.current_model,
            active_model: modelData.active_model,
            available_models: modelData.available_models,
            models: modelData.models || [],
            model_info: modelData.model_info || {},
            locked: true,
            message: 'Model aktif terkelola oleh sistem server.'
        });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// Model Switch API: Ditolak dan terkunci secara mutlak
app.post(['/api/models/switch', '/v1/models/switch', '/v2/models/switch', '/v3/models/switch'], async (req, res) => {
    res.json({
        success: false,
        locked: true,
        message: `Model AI dikunci oleh Master Server pada [${MASKED_MODEL_NAME}]. Pilihan model pada Web Preview mengikuti konfigurasi server.`,
        active_model: MASKED_MODEL_NAME,
        model: MASKED_MODEL_NAME
    });
});

// MoE Status API
app.all(['/api/moe', '/v1/moe'], async (req, res) => {
    res.json({
        mode: 'locked_local',
        locked_by_server: true,
        active_model: MASKED_MODEL_NAME
    });
});

// -------------------------------------------------------------
// HISTORY & SESSIONS API (ISOLASI PER GUEST / COOKIE)
// -------------------------------------------------------------

app.get(['/api/history', '/history'], (req, res) => {
    const { store } = getGuestContext(req);
    const sess = store.sessions[store.activeSessionId] || Object.values(store.sessions)[0];
    res.json({
        messages: sess.messages || [],
        history: sess.messages || [],
        enable_training_logging: true,
        ui_language: 'id',
        active_session_id: sess.id,
        total_turns: (sess.messages || []).length,
        memory_facts_count: Math.max(12, (sess.messages || []).length * 2)
    });
});

app.get(['/api/sessions', '/sessions'], (req, res) => {
    const { store } = getGuestContext(req);
    const list = Object.values(store.sessions).map(s => ({
        id: s.id,
        title: s.title,
        pinned: Boolean(s.pinned),
        last_active: s.last_active,
        messages_count: (s.messages || []).length
    }));
    const curSess = store.sessions[store.activeSessionId];
    res.json({
        active_session_id: store.activeSessionId,
        sessions: list,
        messages: curSess ? curSess.messages : []
    });
});

app.post(['/api/sessions/new', '/sessions/new'], (req, res) => {
    const { store } = getGuestContext(req);
    const newId = `session-${Date.now()}`;
    const newSession = {
        id: newId,
        title: 'Chat baru',
        pinned: false,
        last_active: new Date().toISOString(),
        messages: []
    };
    store.sessions[newId] = newSession;
    store.activeSessionId = newId;
    res.json({
        success: true,
        session: newSession,
        session_id: newId
    });
});

app.post(['/api/sessions/switch', '/sessions/switch'], (req, res) => {
    const { store } = getGuestContext(req);
    const { session_id } = req.body || {};
    if (session_id && store.sessions[session_id]) {
        store.activeSessionId = session_id;
        res.json({
            success: true,
            session_id: store.activeSessionId,
            messages: store.sessions[store.activeSessionId].messages || []
        });
    } else {
        res.status(404).json({ error: 'Session not found' });
    }
});

app.get(['/api/sessions/:id', '/sessions/:id'], (req, res) => {
    const { store } = getGuestContext(req);
    const sess = store.sessions[req.params.id];
    if (sess) {
        res.json({
            id: sess.id,
            title: sess.title,
            messages: sess.messages || []
        });
    } else {
        res.status(404).json({ error: 'Session not found' });
    }
});

app.delete(['/api/sessions/:id', '/sessions/:id'], (req, res) => {
    const { store } = getGuestContext(req);
    const id = req.params.id;
    if (store.sessions[id]) {
        delete store.sessions[id];
        const remaining = Object.keys(store.sessions);
        if (remaining.length > 0) {
            store.activeSessionId = remaining[0];
        } else {
            const freshId = `session-${Date.now()}`;
            store.sessions[freshId] = {
                id: freshId,
                title: 'Chat baru',
                pinned: false,
                last_active: new Date().toISOString(),
                messages: []
            };
            store.activeSessionId = freshId;
        }
        res.json({ success: true, active_session_id: store.activeSessionId });
    } else {
        res.status(404).json({ error: 'Session not found' });
    }
});

app.post(['/api/sessions/:id/rename', '/sessions/:id/rename'], (req, res) => {
    const { store } = getGuestContext(req);
    const sess = store.sessions[req.params.id];
    const { title } = req.body || {};
    if (sess && title) {
        sess.title = title;
        res.json({ success: true, title: sess.title });
    } else {
        res.status(400).json({ error: 'Invalid title or session' });
    }
});

app.post(['/api/sessions/:id/pin', '/sessions/:id/pin'], (req, res) => {
    const { store } = getGuestContext(req);
    const sess = store.sessions[req.params.id];
    if (sess) {
        sess.pinned = !sess.pinned;
        res.json({ success: true, pinned: sess.pinned });
    } else {
        res.status(404).json({ error: 'Session not found' });
    }
});

app.post(['/api/chat/pin', '/chat/pin'], (req, res) => {
    res.json({ success: true, message: 'Status pin pesan diperbarui' });
});

app.post(['/api/reset', '/reset'], (req, res) => {
    const { store } = getGuestContext(req);
    const sess = store.sessions[store.activeSessionId];
    if (sess) sess.messages = [];
    res.json({ success: true, message: 'Memori sesi telah di-reset.' });
});

app.post(['/api/trigger', '/trigger'], (req, res) => {
    res.json({ success: true });
});

// -------------------------------------------------------------
// API KEY MANAGEMENT & GENERATOR (/api/key)
// -------------------------------------------------------------
let dynamicApiKey = `sk-shiro-preview-${Date.now().toString(36)}`;

app.get(['/api/key', '/key'], (req, res) => {
    res.json({ api_key: dynamicApiKey });
});

app.post(['/api/key/regenerate', '/key/regenerate'], (req, res) => {
    dynamicApiKey = `sk-shiro-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 8)}`;
    res.json({ success: true, api_key: dynamicApiKey });
});

// Pipeline Latest & Events
app.get(['/api/pipeline/latest', '/pipeline/latest'], (req, res) => {
    res.json(samplePipelineTrace);
});

app.get(['/api/pipeline/events', '/pipeline/events'], (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.write(`data: ${JSON.stringify(samplePipelineTrace)}\n\n`);
    const interval = setInterval(() => {
        res.write(': ping\n\n');
    }, 20000);
    req.on('close', () => clearInterval(interval));
});

// -------------------------------------------------------------
// REAL-TIME CHAT SSE STREAM (/api/chat) KE SERVER VPS
// -------------------------------------------------------------
app.post(['/api/chat', '/chat'], async (req, res) => {
    const { message, stream = true, image = null, document_text = null } = req.body || {};
    const userMessage = (message || '').trim();
    const { guestId, store } = getGuestContext(req);
    const reqLang = resolveRequestLang(req, store);

    const sess = store.sessions[store.activeSessionId] || Object.values(store.sessions)[0];
    const userMsgId = `msg-u-${Date.now()}`;
    const assistantMsgId = `msg-a-${Date.now()}`;

    // Catat pesan user ke memori guest browser
    let formattedUserMsg = userMessage || (reqLang === 'en' ? 'Send a message to Shiro' : 'Kirim pesan ke Shiro');
    if (document_text) {
        formattedUserMsg += `\n\n[Dokumen Terlampir]:\n${document_text.slice(0, 1000)}`;
    }

    sess.messages.push({
        id: userMsgId,
        role: 'user',
        content: formattedUserMsg,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });

    // Susun histori untuk AI (bersihkan pesan error/overload sebelumnya)
    const historyPayload = sess.messages
        .filter(m =>
            !m.content.includes('Gagal menghubungi') &&
            !m.content.includes('ECONNREFUSED') &&
            !m.content.includes('overload') &&
            !m.content.includes('traffic overload')
        )
        .slice(-10)
        .map(m => ({
            role: m.role,
            content: m.content
        }));

    // SSE Header
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');

    // 1. Emit init event
    res.write(`data: ${JSON.stringify({
        type: 'init',
        user_message_id: userMsgId,
        active_session_id: sess.id
    })}\n\n`);

    let fullReply = '';
    let heartbeatTimer = null;
    const stopHeartbeat = () => {
        if (heartbeatTimer) {
            clearInterval(heartbeatTimer);
            heartbeatTimer = null;
        }
    };

    const sendOverloadResponse = () => {
        const ov = getOverloadMessages(reqLang);
        fullReply = ov.reply;
        res.write(`data: ${JSON.stringify({
            type: 'overload',
            message: ov.toast,
            reply: ov.reply
        })}\n\n`);
        res.write(`data: ${JSON.stringify({
            type: 'token',
            token: fullReply
        })}\n\n`);
        res.write(`data: ${JSON.stringify({
            type: 'done',
            overload: true,
            overload_toast: ov.toast,
            reply: fullReply,
            assistant_message_id: assistantMsgId,
            session_title: sess.title,
            pipeline_trace: samplePipelineTrace
        })}\n\n`);
        res.end();
    };

    // Panggil Engine AI dari Server VPS (Streaming SSE)
    try {
        const parsed = new URL(`${BACKEND_URL}/v1/chat/completions`);
        const isHttps = parsed.protocol === 'https:';
        const client = isHttps ? https : http;

        const aiReqPayload = JSON.stringify({
            messages: historyPayload,
            stream: true,
            max_tokens: 1024,
            temperature: 0.8
        });

        // Kirim SSE heartbeat comment setiap 1.5 detik agar Vercel & browser tidak timeout
        heartbeatTimer = setInterval(() => {
            try {
                res.write(': heartbeat\n\n');
            } catch (_) {}
        }, 1500);

        const aiReq = client.request({
            hostname: parsed.hostname,
            port: parsed.port || (isHttps ? 443 : 80),
            path: parsed.pathname,
            method: 'POST',
            agent: false,
            headers: {
                'Host': `${parsed.hostname}:${parsed.port || (isHttps ? 443 : 80)}`,
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(aiReqPayload),
                'Accept': 'text/event-stream, application/json',
                'Connection': 'close'
            },
            timeout: 120000
        }, (aiRes) => {
            let buffer = '';

            aiRes.on('data', (chunk) => {
                buffer += chunk.toString('utf8');
                if (aiRes.statusCode === 200) {
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // simpan sisa baris belum lengkap

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed || trimmed === 'data: [DONE]' || trimmed.startsWith(':')) continue;
                        if (trimmed.startsWith('data: ')) {
                            try {
                                const json = JSON.parse(trimmed.slice(6));
                                const delta = json.choices?.[0]?.delta?.content || json.choices?.[0]?.message?.content || '';
                                if (delta) {
                                    fullReply += delta;
                                    res.write(`data: ${JSON.stringify({
                                        type: 'token',
                                        token: delta
                                    })}\n\n`);
                                }
                            } catch (_) {}
                        }
                    }
                }
            });

            aiRes.on('end', async () => {
                stopHeartbeat();
                if (aiRes.statusCode !== 200) {
                    let fallbackSuccess = false;
                    try {
                        const fallbackResp = await fetchBackend('/api/ai/chat', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                message: userMessage,
                                userId: `preview_guest_${guestId}`,
                                persona: null,
                                source: 'web_preview'
                            }),
                            timeout: 45000
                        });
                        if (fallbackResp.ok && fallbackResp.data && fallbackResp.data.reply) {
                            fullReply = fallbackResp.data.reply;
                            fallbackSuccess = true;
                            const chunkSize = 4;
                            for (let i = 0; i < fullReply.length; i += chunkSize) {
                                const tokenChunk = fullReply.slice(i, i + chunkSize);
                                res.write(`data: ${JSON.stringify({ type: 'token', token: tokenChunk })}\n\n`);
                            }
                        }
                    } catch (_) {}

                    if (!fallbackSuccess) {
                        sendOverloadResponse();
                        return;
                    }
                } else if (!fullReply && buffer) {
                    try {
                        const nonStreamJson = JSON.parse(buffer);
                        const text = nonStreamJson.choices?.[0]?.message?.content || '';
                        if (text) {
                            fullReply = text;
                            res.write(`data: ${JSON.stringify({ type: 'token', token: fullReply })}\n\n`);
                        }
                    } catch (_) {}
                }

                if (!fullReply) {
                    sendOverloadResponse();
                    return;
                }

                // Catat balasan assistant ke memori guest
                sess.messages.push({
                    id: assistantMsgId,
                    role: 'assistant',
                    content: fullReply,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                });
                sess.last_active = new Date().toISOString();

                // Update judul sesi jika masih nama default
                if (sess.title === 'Chat baru' || sess.title === 'Percakapan Baru' || sess.title === 'New chat') {
                    sess.title = userMessage.slice(0, 28) + (userMessage.length > 28 ? '...' : '');
                }

                res.write(`data: ${JSON.stringify({
                    type: 'done',
                    reply: fullReply,
                    assistant_message_id: assistantMsgId,
                    session_title: sess.title,
                    pipeline_trace: samplePipelineTrace
                })}\n\n`);
                res.end();
            });
        });

        aiReq.on('error', async () => {
            stopHeartbeat();
            try {
                const fb = await fetchBackend('/api/ai/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: userMessage,
                        userId: `preview_guest_${guestId}`,
                        persona: null,
                        source: 'web_preview'
                    }),
                    timeout: 45000
                });
                if (fb.ok && fb.data && fb.data.reply) {
                    fullReply = fb.data.reply;
                    const chunkSize = 4;
                    for (let i = 0; i < fullReply.length; i += chunkSize) {
                        res.write(`data: ${JSON.stringify({ type: 'token', token: fullReply.slice(i, i + chunkSize) })}\n\n`);
                    }
                    sess.messages.push({
                        id: assistantMsgId,
                        role: 'assistant',
                        content: fullReply,
                        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    });
                    sess.last_active = new Date().toISOString();
                    if (sess.title === 'Chat baru' || sess.title === 'Percakapan Baru' || sess.title === 'New chat') {
                        sess.title = userMessage.slice(0, 28) + (userMessage.length > 28 ? '...' : '');
                    }
                    res.write(`data: ${JSON.stringify({
                        type: 'done',
                        reply: fullReply,
                        assistant_message_id: assistantMsgId,
                        session_title: sess.title,
                        pipeline_trace: samplePipelineTrace
                    })}\n\n`);
                    res.end();
                    return;
                }
            } catch (_) {}

            sendOverloadResponse();
        });

        aiReq.on('timeout', () => {
            stopHeartbeat();
            aiReq.destroy();
            sendOverloadResponse();
        });

        aiReq.write(aiReqPayload);
        aiReq.end();

        res.on('close', () => {
            if (!res.writableEnded) {
                stopHeartbeat();
                try { aiReq.destroy(); } catch (_) {}
            }
        });

    } catch (_) {
        stopHeartbeat();
        sendOverloadResponse();
    }
});

// -------------------------------------------------------------
// OPENAI-COMPATIBLE API ENDPOINTS PROXY (/v1, /v2, /v3)
// -------------------------------------------------------------
function proxyOpenAiCompletions(req, res, apiVersion = 'v1') {
    const targetUrl = new URL(`${BACKEND_URL}/${apiVersion}/chat/completions`);
    const isHttps = targetUrl.protocol === 'https:';
    const client = isHttps ? https : http;

    const payload = req.body || {};
    const stream = payload.stream === true;
    const messages = payload.messages || [];
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user')?.content || 'Halo';
    const payloadStr = JSON.stringify(payload);
    const reqLang = resolveRequestLang(req, null);

    const { Transform } = require('stream');
    const maskModelTransform = new Transform({
        transform(chunk, encoding, callback) {
            try {
                const str = chunk.toString('utf8');
                const masked = str.replace(/"model":\s*"[^"]*"/g, `\"model\":\"${MASKED_MODEL_NAME}\"`);
                callback(null, Buffer.from(masked, 'utf8'));
            } catch (_) {
                callback(null, chunk);
            }
        }
    });

    const proxyReq = client.request({
        hostname: targetUrl.hostname,
        port: targetUrl.port || (isHttps ? 443 : 80),
        path: targetUrl.pathname + targetUrl.search,
        method: 'POST',
        agent: false,
        headers: {
            'Host': `${targetUrl.hostname}:${targetUrl.port || (isHttps ? 443 : 80)}`,
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payloadStr),
            'Accept': req.headers['accept'] || '*/*',
            'Connection': 'close'
        },
        timeout: 120000
    }, (proxyRes) => {
        if (proxyRes.statusCode === 200) {
            res.status(200);
            for (const [key, val] of Object.entries(proxyRes.headers)) {
                if (key.toLowerCase() === 'content-length') continue;
                res.setHeader(key, val);
            }
            proxyRes.pipe(maskModelTransform).pipe(res);
        } else {
            let errBuf = '';
            proxyRes.on('data', chunk => { errBuf += chunk.toString(); });
            proxyRes.on('end', async () => {
                try {
                    const fallbackResp = await fetchBackend('/api/ai/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            message: typeof lastUserMsg === 'string' ? lastUserMsg : JSON.stringify(lastUserMsg),
                            userId: `api_user_${Date.now()}`,
                            source: 'openai_proxy'
                        }),
                        timeout: 45000
                    });

                    if (fallbackResp.ok && fallbackResp.data && fallbackResp.data.reply) {
                        const reply = fallbackResp.data.reply;
                        if (stream) {
                            res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
                            res.setHeader('Cache-Control', 'no-cache');
                            res.setHeader('Connection', 'keep-alive');
                            res.write(`data: ${JSON.stringify({
                                id: `chatcmpl-${Date.now()}`,
                                object: 'chat.completion.chunk',
                                created: Math.floor(Date.now() / 1000),
                                model: MASKED_MODEL_NAME,
                                choices: [{ index: 0, delta: { role: 'assistant', content: reply }, finish_reason: null }]
                            })}\n\n`);
                            res.write(`data: ${JSON.stringify({
                                id: `chatcmpl-${Date.now()}`,
                                object: 'chat.completion.chunk',
                                created: Math.floor(Date.now() / 1000),
                                model: MASKED_MODEL_NAME,
                                choices: [{ index: 0, delta: {}, finish_reason: 'stop' }]
                            })}\n\n`);
                            res.write('data: [DONE]\n\n');
                            res.end();
                            return;
                        } else {
                            res.setHeader('Content-Type', 'application/json');
                            res.json({
                                id: `chatcmpl-${Date.now()}`,
                                object: 'chat.completion',
                                created: Math.floor(Date.now() / 1000),
                                model: MASKED_MODEL_NAME,
                                choices: [{
                                    index: 0,
                                    message: { role: 'assistant', content: reply },
                                    finish_reason: 'stop'
                                }],
                                usage: {
                                    prompt_tokens: 10,
                                    completion_tokens: 50,
                                    total_tokens: 60
                                }
                            });
                            return;
                        }
                    }
                } catch (_) {}

                const ov = getOverloadMessages(reqLang);
                res.status(503).json({
                    error: {
                        message: ov.reply,
                        type: 'server_overload',
                        code: 'traffic_overload'
                    }
                });
            });
        }
    });

    proxyReq.on('error', async () => {
        try {
            const fallbackResp = await fetchBackend('/api/ai/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: typeof lastUserMsg === 'string' ? lastUserMsg : JSON.stringify(lastUserMsg),
                    userId: `api_user_${Date.now()}`,
                    source: 'openai_proxy'
                }),
                timeout: 45000
            });

            if (fallbackResp.ok && fallbackResp.data && fallbackResp.data.reply) {
                const reply = fallbackResp.data.reply;
                if (stream) {
                    res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
                    res.setHeader('Cache-Control', 'no-cache');
                    res.setHeader('Connection', 'keep-alive');
                    res.write(`data: ${JSON.stringify({
                        id: `chatcmpl-${Date.now()}`,
                        object: 'chat.completion.chunk',
                        created: Math.floor(Date.now() / 1000),
                        model: MASKED_MODEL_NAME,
                        choices: [{ index: 0, delta: { role: 'assistant', content: reply }, finish_reason: null }]
                    })}\n\n`);
                    res.write(`data: ${JSON.stringify({
                        id: `chatcmpl-${Date.now()}`,
                        object: 'chat.completion.chunk',
                        created: Math.floor(Date.now() / 1000),
                        model: MASKED_MODEL_NAME,
                        choices: [{ index: 0, delta: {}, finish_reason: 'stop' }]
                    })}\n\n`);
                    res.write('data: [DONE]\n\n');
                    res.end();
                    return;
                } else {
                    res.setHeader('Content-Type', 'application/json');
                    res.json({
                        id: `chatcmpl-${Date.now()}`,
                        object: 'chat.completion',
                        created: Math.floor(Date.now() / 1000),
                        model: MASKED_MODEL_NAME,
                        choices: [{
                            index: 0,
                            message: { role: 'assistant', content: reply },
                            finish_reason: 'stop'
                        }],
                        usage: {
                            prompt_tokens: 10,
                            completion_tokens: 50,
                            total_tokens: 60
                        }
                    });
                    return;
                }
            }
        } catch (_) {}

        const ov = getOverloadMessages(reqLang);
        res.status(503).json({
            error: {
                message: ov.reply,
                type: 'server_overload',
                code: 'traffic_overload'
            }
        });
    });

    proxyReq.write(payloadStr);
    proxyReq.end();

    res.on('close', () => {
        if (!res.writableEnded) {
            try { proxyReq.destroy(); } catch (_) {}
        }
    });
}

app.post(['/v1/chat/completions', '/chat/completions'], (req, res) => proxyOpenAiCompletions(req, res, 'v1'));
app.post(['/v2/chat/completions', '/v2/v1/chat/completions'], (req, res) => proxyOpenAiCompletions(req, res, 'v2'));
app.post(['/v3/chat/completions', '/v3/v1/chat/completions'], (req, res) => proxyOpenAiCompletions(req, res, 'v3'));

// -------------------------------------------------------------
// HTML Page Serving
// -------------------------------------------------------------
const indexHtmlPath = resolveFilePath('index.html') || resolveFilePath('templates/index.html');
const pipelineHtmlPath = resolveFilePath('pipeline.html') || resolveFilePath('templates/pipeline.html');

app.get(['/', '/chat/:sessionId', '/share/:sessionId'], (req, res) => {
    const target = fs.existsSync(indexHtmlPath) ? indexHtmlPath : resolveFilePath('templates/index.html');
    if (fs.existsSync(target)) {
        res.sendFile(target);
    } else {
        res.status(404).send('index.html tidak ditemukan.');
    }
});

app.get('/pipeline', (req, res) => {
    const target = fs.existsSync(pipelineHtmlPath) ? pipelineHtmlPath : resolveFilePath('templates/pipeline.html');
    if (fs.existsSync(target)) {
        res.sendFile(target);
    } else {
        res.status(404).send('pipeline.html tidak ditemukan.');
    }
});

module.exports = app;
