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
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Guest-ID, X-Session-ID, X-API-Key');
    if (req.method === 'OPTIONS') {
        return res.status(204).end();
    }
    next();
});

// Middleware normalisasi route untuk Vercel Serverless Function & Edge Rewrites
app.use((req, res, next) => {
    const original = req.headers['x-matched-path'] || 
                     req.headers['x-vercel-matched-path'] || 
                     req.headers['x-forwarded-uri'] || 
                     req.headers['x-original-uri'];
    if (original && (req.url === '/api/index.js' || req.url.startsWith('/api/index.js') || req.url === '/api/[...slug].js')) {
        req.url = original;
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

function getProfileData() {
    let ai = bundledAi;
    let user = bundledUser;
    if (!ai) {
        try {
            const aiPath = resolveFilePath('profile/ai.json');
            if (fs.existsSync(aiPath)) ai = JSON.parse(fs.readFileSync(aiPath, 'utf8'));
        } catch (_) {}
    }
    if (!user) {
        try {
            const userPath = resolveFilePath('profile/user.json');
            if (fs.existsSync(userPath)) user = JSON.parse(fs.readFileSync(userPath, 'utf8'));
        } catch (_) {}
    }
    return {
        ai: ai || { name: 'Shiro', description: 'AI Assistant & Companion' },
        user: user || { name: 'Kakak' }
    };
}

// -------------------------------------------------------------
// KONFIGURASI BACKEND AI SERVER (VPS / Pterodactyl Port 2223)
// -------------------------------------------------------------
const BACKEND_URL = (
    process.env.SHIRO_BACKEND_URL || 
    process.env.AI_BACKEND_URL || 
    'https://cloud.lynzz.id/server'
).replace(/\/+$/, '');

const FALLBACK_BACKEND_URLS = [
    BACKEND_URL,
    'https://cloud.lynzz.id/server',
    'http://cloud.lynzz.id:2223',
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
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
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

    // Bersihkan sesi usang jika cache guest melampaui 1000 user aktif
    if (guestStores.size > 1000) {
        const firstKey = guestStores.keys().next().value;
        guestStores.delete(firstKey);
    }

    return { guestId, store: guestStores.get(guestId) };
}

// Pipeline sample trace untuk modal inspektor visual
const { samplePipelineTrace } = require('./mock_data.js');

// -------------------------------------------------------------
// API Endpoints
// -------------------------------------------------------------

// Profile API
app.get('/api/profile', (req, res) => {
    res.json(getProfileData());
});

app.post('/api/profile/upload', (req, res) => {
    res.json({ success: true, message: 'Profil berhasil diperbarui' });
});

// Privacy & Settings API
app.get('/api/settings/privacy', (req, res) => {
    res.json({
        enable_training_logging: true,
        ui_language: 'id'
    });
});

app.post('/api/settings/privacy', (req, res) => {
    res.json({ success: true });
});

// Memory Count & Stats API
app.get('/api/memory-count', (req, res) => {
    const { store } = getGuestContext(req);
    const totalMsgs = Object.values(store.sessions).reduce((acc, s) => acc + (s.messages || []).length, 0);
    res.json({
        count: Math.max(12, totalMsgs * 2),
        unit: 'fakta'
    });
});

app.get('/api/stats', (req, res) => {
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
        size: '1.05 GB',
        quantization: 'Q4_K_M',
        description: 'ShiroHaru-0.1-Agent (Cognitive Reasoning & Companion Engine) - Dikunci oleh Developer'
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
        message: `Model AI dikunci oleh Master Server pada: ${MASKED_MODEL_NAME}`
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
            message: 'Model AI dikunci oleh Master Server (Pergantian model dari client dinonaktifkan).'
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

app.get('/api/history', (req, res) => {
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

app.get('/api/sessions', (req, res) => {
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

app.post('/api/sessions/new', (req, res) => {
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

app.post('/api/sessions/switch', (req, res) => {
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

app.get('/api/sessions/:id', (req, res) => {
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

app.delete('/api/sessions/:id', (req, res) => {
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

app.post('/api/sessions/:id/rename', (req, res) => {
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

app.post('/api/sessions/:id/pin', (req, res) => {
    const { store } = getGuestContext(req);
    const sess = store.sessions[req.params.id];
    if (sess) {
        sess.pinned = !sess.pinned;
        res.json({ success: true, pinned: sess.pinned });
    } else {
        res.status(404).json({ error: 'Session not found' });
    }
});

app.post('/api/chat/pin', (req, res) => {
    res.json({ success: true, message: 'Status pin pesan diperbarui' });
});

app.post('/api/reset', (req, res) => {
    const { store } = getGuestContext(req);
    const sess = store.sessions[store.activeSessionId];
    if (sess) sess.messages = [];
    res.json({ success: true, message: 'Memori sesi telah di-reset.' });
});

app.post('/api/trigger', (req, res) => {
    res.json({ success: true });
});

// -------------------------------------------------------------
// API KEY MANAGEMENT & GENERATOR (/api/key)
// -------------------------------------------------------------
let dynamicApiKey = `sk-shiro-preview-${Date.now().toString(36)}`;

app.get('/api/key', (req, res) => {
    res.json({ api_key: dynamicApiKey });
});

app.post('/api/key/regenerate', (req, res) => {
    dynamicApiKey = `sk-shiro-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 8)}`;
    res.json({ success: true, api_key: dynamicApiKey });
});

// Pipeline Latest & Events
app.get('/api/pipeline/latest', (req, res) => {
    res.json(samplePipelineTrace);
});

app.get('/api/pipeline/events', (req, res) => {
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
app.post('/api/chat', async (req, res) => {
    const { message, stream = true, image = null, document_text = null } = req.body || {};
    const userMessage = (message || '').trim();
    const { guestId, store } = getGuestContext(req);

    const sess = store.sessions[store.activeSessionId] || Object.values(store.sessions)[0];
    const userMsgId = `msg-u-${Date.now()}`;
    const assistantMsgId = `msg-a-${Date.now()}`;

    // Catat pesan user ke memori guest browser
    let formattedUserMsg = userMessage || 'Kirim pesan ke Shiro';
    if (document_text) {
        formattedUserMsg += `\n\n[Dokumen Terlampir]:\n${document_text.slice(0, 1000)}`;
    }

    sess.messages.push({
        id: userMsgId,
        role: 'user',
        content: formattedUserMsg,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });

    // Susun histori untuk AI
    const historyPayload = sess.messages.slice(-10).map(m => ({
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

        const aiReq = client.request({
            hostname: parsed.hostname,
            port: parsed.port || (isHttps ? 443 : 80),
            path: parsed.pathname,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(aiReqPayload),
                'Accept': 'text/event-stream'
            },
            timeout: 120000
        }, (aiRes) => {
            let buffer = '';

            aiRes.on('data', (chunk) => {
                buffer += chunk.toString('utf8');
                const lines = buffer.split('\n');
                buffer = lines.pop(); // simpan sisa baris belum lengkap

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || trimmed === 'data: [DONE]' || trimmed.startsWith(':')) continue;
                    if (trimmed.startsWith('data: ')) {
                        try {
                            const json = JSON.parse(trimmed.slice(6));
                            const delta = json.choices?.[0]?.delta?.content || '';
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
            });

            aiRes.on('end', () => {
                if (!fullReply) {
                    fullReply = '*tersenyum manis dan memeluk Kakak* "Halo Kakak! Shiro sudah aktif terhubung langsung ke server AI lokal Kakak~ Ada yang bisa Shiro bantu?"';
                    res.write(`data: ${JSON.stringify({ type: 'token', token: fullReply })}\n\n`);
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
                if (sess.title === 'Chat baru' || sess.title === 'Percakapan Baru') {
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

        aiReq.on('error', (err) => {
            console.error('[Preview-Demo AI Error]:', err.message);
            // Fallback interaktif jika VPS offline atau sedang memuat model
            fullReply = `*menatap cemas sambil memegang tangan Kakak*\n\n"Umm Kakak, server AI lokal sedang bersiap atau memuat model di latar belakang (\`${err.message}\`). Mohon tunggu sebentar ya Kak, nanti coba chat Shiro lagi!"`;
            res.write(`data: ${JSON.stringify({ type: 'token', token: fullReply })}\n\n`);
            res.write(`data: ${JSON.stringify({
                type: 'done',
                reply: fullReply,
                assistant_message_id: assistantMsgId,
                session_title: sess.title,
                pipeline_trace: samplePipelineTrace
            })}\n\n`);
            res.end();
        });

        aiReq.on('timeout', () => {
            aiReq.destroy();
            res.write(`data: ${JSON.stringify({ type: 'token', token: 'Waktu tunggu respon server AI habis.' })}\n\n`);
            res.write(`data: ${JSON.stringify({ type: 'done', reply: 'Timeout' })}\n\n`);
            res.end();
        });

        aiReq.write(aiReqPayload);
        aiReq.end();

        req.on('close', () => {
            try { aiReq.destroy(); } catch (_) {}
        });

    } catch (e) {
        console.error('[Preview-Demo Chat Exception]:', e.message);
        res.write(`data: ${JSON.stringify({ type: 'error', error: e.message })}\n\n`);
        res.end();
    }
});

// -------------------------------------------------------------
// OPENAI-COMPATIBLE API ENDPOINTS PROXY (/v1, /v2, /v3)
// -------------------------------------------------------------
function proxyOpenAiCompletions(req, res, apiVersion = 'v1') {
    const targetUrl = new URL(`${BACKEND_URL}/${apiVersion}/chat/completions`);
    const isHttps = targetUrl.protocol === 'https:';
    const client = isHttps ? https : http;

    const payloadStr = JSON.stringify(req.body || {});

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
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payloadStr),
            'Accept': req.headers['accept'] || '*/*'
        },
        timeout: 120000
    }, (proxyRes) => {
        res.status(proxyRes.statusCode);
        for (const [key, val] of Object.entries(proxyRes.headers)) {
            if (key.toLowerCase() === 'content-length') continue;
            res.setHeader(key, val);
        }
        proxyRes.pipe(maskModelTransform).pipe(res);
    });

    proxyReq.on('error', (err) => {
        res.status(502).json({
            error: {
                message: `Gagal meneruskan request ke server AI: ${err.message}`,
                type: 'bad_gateway',
                code: 'upstream_unavailable'
            }
        });
    });

    proxyReq.write(payloadStr);
    proxyReq.end();

    req.on('close', () => {
        try { proxyReq.destroy(); } catch (_) {}
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
