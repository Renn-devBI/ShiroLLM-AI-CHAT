const express = require('express');
const path = require('path');
const fs = require('fs');

const app = express();

app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Helper untuk menemukan lokasi berkas relatif
function resolveFilePath(relPath) {
    const candidates = [
        path.join(__dirname, '..', relPath),
        path.join(__dirname, relPath),
        path.join(process.cwd(), 'Preview-Demo', relPath),
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

// Memuat profil AI & User
function getProfileData() {
    let ai = null;
    let user = null;
    try {
        const aiPath = resolveFilePath('profile/ai.json');
        if (fs.existsSync(aiPath)) ai = JSON.parse(fs.readFileSync(aiPath, 'utf8'));
    } catch (_) {}
    try {
        const userPath = resolveFilePath('profile/user.json');
        if (fs.existsSync(userPath)) user = JSON.parse(fs.readFileSync(userPath, 'utf8'));
    } catch (_) {}
    return {
        ai: ai || { name: 'Shiro', description: '' },
        user: user || { name: 'Kakak' }
    };
}

// In-memory data store untuk demo interaktif (sama persis dengan tampilan running app.py)
let activeSessionId = 'session-1';

const initialFolderStructureCode = 
`garukura-py/
├── app.py                  # Entry point Flask + server start
├── config.py               # Konfigurasi aplikasi
├── requirements.txt        # Dependencies (Flask)
├── routes/
│   ├── __init__.py         # Blueprint registration
│   └── main_routes.py      # Page & API endpoints
└── data/
    ├── __init__.py         # Data exports ke app
    ├── characters.py       # 5 anggota Togenashi Togeari + bio
    ├── series_info.py      # Production details (studio, director, dll)
    └── media_list.py       # Multi-media resources`;

const sessionsStore = {
    'session-1': {
        id: 'session-1',
        title: 'Shiro Buatin Website Dari...',
        pinned: false,
        last_active: new Date().toISOString(),
        messages: [
            {
                id: 'msg-u-1',
                role: 'user',
                content: 'Shiro tolong buatin website dan file struktur lengkap untuk proyek garukura!',
                timestamp: '01:25'
            },
            {
                id: 'msg-a-1',
                role: 'assistant',
                content: `*memegang laptop Kakak sambil ngetik cepat dengan jari-jari kecilnya*\n\nOke Kak! Shiro lanjutin semua file lengkap dari awal sampai akhir~ UI-nya clean, dark theme tanpa emoji, glow subtle banget kayak yang Kakak mau sebelumnya. Data di-render dynamic via Jinja2 loop biar rapi dan gampang ditambah nanti.\n\nStruktur folder:\n\n\`\`\`kode\n${initialFolderStructureCode}\n\`\`\``,
                timestamp: '01:26'
            }
        ]
    },
    'session-2': {
        id: 'session-2',
        title: 'Shiro Sedang Apa',
        pinned: false,
        last_active: new Date(Date.now() - 3600000).toISOString(),
        messages: [
            {
                id: 'msg-u-2',
                role: 'user',
                content: 'Shiro lagi ngapain sekarang?',
                timestamp: '00:30'
            },
            {
                id: 'msg-a-2',
                role: 'assistant',
                content: '*tersenyum manis sambil melirik Kakak* Shiro lagi nungguin Kakak ngajak ngobrol atau ngoding bareng! Kakak mau bikin program apa hari ini?',
                timestamp: '00:31'
            }
        ]
    }
};

// -------------------------------------------------------------
// API Endpoints (Mock Identik Shiro Backend)
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
    res.json({
        count: 26,
        unit: 'fakta'
    });
});

app.get('/api/stats', (req, res) => {
    res.json({
        total_turns: 14,
        memory_facts: 26,
        uptime_seconds: 7474
    });
});

// Models API (Hanya 1 Model: ShiroAI-v2-Agent)
app.get('/api/models', (req, res) => {
    res.json({
        models: [
            {
                id: 'ShiroAI-v2-Agent',
                name: 'ShiroAI-v2-Agent',
                display_name: 'ShiroAI-v2-Agent',
                family: 'Shiro Cognitive',
                active: true,
                description: 'Model Utama Penalaran Kognitif & Agentic (v2)'
            }
        ],
        active_model: 'ShiroAI-v2-Agent'
    });
});

app.post(['/api/models/switch', '/v1/models/switch', '/v2/models/switch'], (req, res) => {
    res.json({
        success: true,
        active_model: 'ShiroAI-v2-Agent'
    });
});

// MoE Orchestrator Status API
app.all(['/api/moe', '/v1/moe'], (req, res) => {
    res.json({
        mode: 'auto',
        vision_expert_loaded: true,
        vision_expert_path: 'Qwen2.5-VL-7B'
    });
});

// History API (Mengembalikan pesan sesi aktif saat ini)
app.get('/api/history', (req, res) => {
    const sess = sessionsStore[activeSessionId] || sessionsStore['session-1'];
    res.json({
        messages: sess.messages || [],
        enable_training_logging: true,
        ui_language: 'id',
        active_session_id: sess.id,
        total_turns: 14,
        memory_facts_count: 26
    });
});

// Sessions API
app.get('/api/sessions', (req, res) => {
    const list = Object.values(sessionsStore).map(s => ({
        id: s.id,
        title: s.title,
        pinned: Boolean(s.pinned),
        last_active: s.last_active,
        messages_count: (s.messages || []).length
    }));
    res.json({
        active_session_id: activeSessionId,
        sessions: list
    });
});

app.post('/api/sessions/new', (req, res) => {
    const newId = `session-${Date.now()}`;
    const newSession = {
        id: newId,
        title: 'New Chat',
        pinned: false,
        last_active: new Date().toISOString(),
        messages: []
    };
    sessionsStore[newId] = newSession;
    activeSessionId = newId;
    res.json({
        success: true,
        session: newSession,
        session_id: newId
    });
});

app.post('/api/sessions/switch', (req, res) => {
    const { session_id } = req.body || {};
    if (session_id && sessionsStore[session_id]) {
        activeSessionId = session_id;
        res.json({
            success: true,
            session_id: activeSessionId,
            messages: sessionsStore[activeSessionId].messages || []
        });
    } else {
        res.status(404).json({ error: 'Session not found' });
    }
});

app.get('/api/sessions/:id', (req, res) => {
    const sess = sessionsStore[req.params.id];
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
    const id = req.params.id;
    if (sessionsStore[id]) {
        delete sessionsStore[id];
        const remaining = Object.keys(sessionsStore);
        if (remaining.length > 0) {
            activeSessionId = remaining[0];
        }
        res.json({ success: true, active_session_id: activeSessionId });
    } else {
        res.status(404).json({ error: 'Session not found' });
    }
});

app.post('/api/sessions/:id/rename', (req, res) => {
    const sess = sessionsStore[req.params.id];
    const { title } = req.body || {};
    if (sess && title) {
        sess.title = title;
        res.json({ success: true, title: sess.title });
    } else {
        res.status(400).json({ error: 'Invalid title or session' });
    }
});

app.post('/api/sessions/:id/pin', (req, res) => {
    const sess = sessionsStore[req.params.id];
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

// Reset Memory API
app.post('/api/reset', (req, res) => {
    const sess = sessionsStore[activeSessionId];
    if (sess) sess.messages = [];
    res.json({ success: true, message: 'Memori sesi telah di-reset.' });
});

// Trigger API
app.post('/api/trigger', (req, res) => {
    res.json({ success: true });
});

// API Key Management
app.get('/api/key', (req, res) => {
    res.json({ api_key: 'sk-shiro-preview-demo-key-7474' });
});

app.post('/api/key/regenerate', (req, res) => {
    res.json({ success: true, api_key: `sk-shiro-${Date.now()}` });
});

// Pipeline Latest & Events (Inspector Modal)
const samplePipelineTrace = {
    id: 'trace-demo-latest',
    timestamp: new Date().toISOString(),
    status: 'success',
    total_duration_ms: 248.5,
    user_input: 'Shiro tolong buatin website dan file struktur lengkap untuk proyek garukura!',
    reply: 'Struktur proyek garukura-py berhasil dibuat.',
    nodes: [
        {
            id: 'node_context',
            name: 'Memory & Context Retrieval',
            type: 'input',
            icon: 'ph-brain',
            color: '#8b5cf6',
            status: 'success',
            duration_ms: 12.4,
            summary: '2 Sesi • 26 Fakta Aktif'
        },
        {
            id: 'node_emotion',
            name: 'Emotion & Tone Classifier',
            type: 'analyzer',
            icon: 'ph-heartbeat',
            color: '#ec4899',
            status: 'success',
            duration_ms: 18.2,
            summary: 'Semangat • Permintaan Coding'
        },
        {
            id: 'node_prompt',
            name: 'Dynamic Prompt Synthesizer',
            type: 'transform',
            icon: 'ph-brackets-curly',
            color: '#06b6d4',
            status: 'success',
            duration_ms: 8.5,
            summary: 'ShiroAI-v2-Agent Persona'
        },
        {
            id: 'node_llm',
            name: 'Neural Inference Engine',
            type: 'ai_model',
            icon: 'ph-cpu',
            color: '#f59e0b',
            status: 'success',
            duration_ms: 195.1,
            summary: 'ShiroAI-v2-Agent • 100% Selesai'
        },
        {
            id: 'node_filter',
            name: 'Neural Output Filter',
            type: 'filter',
            icon: 'ph-shield-check',
            color: '#10b981',
            status: 'success',
            duration_ms: 14.3,
            summary: 'Output Terlindungi & Bersih'
        }
    ]
};

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

// Real-Time Chat SSE Stream (/api/chat)
app.post('/api/chat', (req, res) => {
    const { message, stream = true } = req.body || {};
    const userMessage = (message || '').trim();

    const sess = sessionsStore[activeSessionId] || sessionsStore['session-1'];
    const userMsgId = `msg-u-${Date.now()}`;
    const assistantMsgId = `msg-a-${Date.now()}`;

    // Catat pesan user
    sess.messages.push({
        id: userMsgId,
        role: 'user',
        content: userMessage || 'Kirim permintaan ke ShiroAI-v2-Agent',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });

    const replyContent = 
`*tersenyum hangat dan mengangguk ceria*

Halo Kakak! Sebagai **ShiroAI-v2-Agent**, Shiro sudah menyelesaikan permintaan: "${userMessage || 'tugas pemrograman'}".

Berikut kode program solusi yang sudah Shiro siapkan:

\`\`\`javascript
// Solusi Otomatis ShiroAI-v2-Agent
function jalankanSolusiShiro(taskName) {
    console.log("[Shiro AI] Menjalankan tugas:", taskName);
    return {
        status: "sukses",
        model: "ShiroAI-v2-Agent",
        timestamp: new Date().toISOString(),
        pesan: "Kode siap dijalankan dan diunduh langsung!"
    };
}

jalankanSolusiShiro("${(userMessage || 'Proyek Kakak').replace(/"/g, '')}");
\`\`\`

Kakak bisa langsung menekan tombol **Unduh** di pojok kanan atas blok kode untuk menyimpan berkas ini secara langsung tanpa perlu repot salin-tempel!`;

    // Catat pesan assistant ke memori sesi
    sess.messages.push({
        id: assistantMsgId,
        role: 'assistant',
        content: replyContent,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });
    sess.last_active = new Date().toISOString();

    if (!stream) {
        return res.json({
            reply: replyContent,
            user_message_id: userMsgId,
            assistant_message_id: assistantMsgId,
            active_session_id: sess.id,
            session_title: sess.title,
            pipeline_trace: samplePipelineTrace
        });
    }

    // Server-Sent Events (SSE) Streaming
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    // 1. Init event
    res.write(`data: ${JSON.stringify({
        type: 'init',
        user_message_id: userMsgId,
        active_session_id: sess.id
    })}\n\n`);

    // 2. Stream tokens secara bertahap
    const chunks = replyContent.match(/.{1,8}/g) || [replyContent];
    let idx = 0;
    const streamInterval = setInterval(() => {
        if (idx < chunks.length) {
            res.write(`data: ${JSON.stringify({
                type: 'token',
                token: chunks[idx]
            })}\n\n`);
            idx++;
        } else {
            clearInterval(streamInterval);
            res.write(`data: ${JSON.stringify({
                type: 'done',
                reply: replyContent,
                assistant_message_id: assistantMsgId,
                session_title: sess.title,
                pipeline_trace: samplePipelineTrace
            })}\n\n`);
            res.end();
        }
    }, 20);

    req.on('close', () => {
        clearInterval(streamInterval);
    });
});

// -------------------------------------------------------------
// HTML Page Serving (100% Identik dengan app.py)
// -------------------------------------------------------------
const indexHtmlPath = resolveFilePath('templates/index.html');

app.get(['/', '/chat/:sessionId', '/share/:sessionId'], (req, res) => {
    if (fs.existsSync(indexHtmlPath)) {
        res.sendFile(indexHtmlPath);
    } else {
        res.status(404).send('templates/index.html tidak ditemukan.');
    }
});

module.exports = app;
