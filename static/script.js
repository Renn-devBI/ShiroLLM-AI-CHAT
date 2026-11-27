// DOM Elements
const chatViewport = document.getElementById('chat-viewport');
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const stopBtn = document.getElementById('stop-btn');
const resetBtn = document.getElementById('reset-btn');
const memoryCount = document.getElementById('memory-count');
const status = document.getElementById('status');

// Notifikasi pojok kanan bawah (non-blocking & dapat ditutup)
function _dismissToastEl(el) {
    if (el && el.parentNode) {
        el.remove();
    }
}

function showToast(message, duration = 3000) {
    const stack = document.getElementById('toast-stack');
    if (!stack) { console.log(message); return; }
    const el = document.createElement('div');
    el.className = 'toast';
    el.setAttribute('role', 'status');
    el.innerHTML = `
        <i class="ph ph-info toast-icon" aria-hidden="true"></i>
        <div class="toast-body">
            <div class="toast-subtitle">${escapeHtml(message)}</div>
        </div>
        <button type="button" class="toast-close-btn" title="${escapeHtml(t('close_notif_tooltip'))}" aria-label="${escapeHtml(t('close_notif_tooltip'))}">
            <i class="ph ph-x"></i>
        </button>
    `;
    let timer = null;
    const armTimer = (ms) => {
        if (ms > 0) timer = setTimeout(() => _dismissToastEl(el), ms);
    };
    const closeBtn = el.querySelector('.toast-close-btn');
    if (closeBtn) {
        closeBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            if (timer) clearTimeout(timer);
            _dismissToastEl(el);
        });
    }
    el.addEventListener('mouseenter', () => {
        if (timer) { clearTimeout(timer); timer = null; }
    });
    el.addEventListener('mouseleave', () => armTimer(Math.min(duration, 2000)));
    stack.appendChild(el);
    armTimer(duration);
}

function dismissSessionDoneNotifications(sessionId) {
    const stack = document.getElementById('toast-stack');
    if (!stack || !sessionId) return;
    stack.querySelectorAll('.toast-session-notif').forEach((node) => {
        if (node.dataset.sessionId === sessionId) {
            _dismissToastEl(node);
        }
    });
}

function showSessionDoneNotification({ sessionId, sessionTitle, isError = false, errorText = '' } = {}) {
    if (!notificationsEnabled) return;
    const stack = document.getElementById('toast-stack');
    if (!stack || !sessionId) return;
    dismissSessionDoneNotifications(sessionId);

    const safeTitle = sessionTitle || getSessionTitleById(sessionId);
    const isOtherSession = sessionId !== activeSessionId;
    const titleTxt = isError ? t('session_error_title') : t('session_done_title');
    const subTxt = isError
        ? `${safeTitle}${errorText ? ` — ${errorText}` : ''}`
        : `${safeTitle} · ${t('session_done_desc')}`;

    const el = document.createElement('div');
    el.className = `toast toast-session-notif ${isError ? 'toast-error' : 'toast-done'}`;
    el.dataset.sessionId = sessionId;
    el.setAttribute('role', 'status');
    el.innerHTML = `
        <i class="ph-fill ${isError ? 'ph-warning-circle' : 'ph-check-circle'} toast-icon" aria-hidden="true"></i>
        <div class="toast-body">
            <div class="toast-title">${escapeHtml(titleTxt)}</div>
            <div class="toast-subtitle">${escapeHtml(subTxt)}</div>
        </div>
        <div class="toast-actions">
            ${isOtherSession ? `<button type="button" class="toast-open-btn">${escapeHtml(t('open_session_btn'))}</button>` : ''}
            <button type="button" class="toast-mute-btn" title="${escapeHtml(t('mute_notif_tooltip'))}" aria-label="${escapeHtml(t('mute_notif_tooltip'))}">
                <i class="ph ph-bell-slash"></i>
            </button>
            <button type="button" class="toast-close-btn" title="${escapeHtml(t('close_notif_tooltip'))}" aria-label="${escapeHtml(t('close_notif_tooltip'))}">
                <i class="ph ph-x"></i>
            </button>
        </div>
    `;

    let timer = null;
    const autoCloseMs = isOtherSession ? 0 : 8000;
    const armTimer = (ms) => {
        if (ms > 0) timer = setTimeout(() => _dismissToastEl(el), ms);
    };

    const openBtn = el.querySelector('.toast-open-btn');
    if (openBtn) {
        openBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            if (timer) clearTimeout(timer);
            _dismissToastEl(el);
            switchSession(sessionId);
        });
    }
    const muteBtn = el.querySelector('.toast-mute-btn');
    if (muteBtn) {
        muteBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            if (timer) clearTimeout(timer);
            _dismissToastEl(el);
            toggleNotificationsEnabled(false);
        });
    }
    const closeBtn = el.querySelector('.toast-close-btn');
    if (closeBtn) {
        closeBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            if (timer) clearTimeout(timer);
            _dismissToastEl(el);
        });
    }
    el.addEventListener('mouseenter', () => {
        if (timer) { clearTimeout(timer); timer = null; }
    });
    el.addEventListener('mouseleave', () => {
        if (autoCloseMs > 0) armTimer(3500);
    });

    stack.appendChild(el);
    if (autoCloseMs > 0) armTimer(autoCloseMs);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
const typingIndicator = document.getElementById('typing-indicator');

// Session & Sidebar Controls
const appLayout = document.querySelector('.app-layout');
const newChatBtn = document.getElementById('new-chat-btn');
const sessionSelect = document.getElementById('session-select');
const deleteChatBtn = document.getElementById('delete-chat-btn');
const chatSidebar = document.getElementById('chat-sidebar');
const sidebarBackdrop = document.getElementById('sidebar-backdrop');
const openSidebarBtn = document.getElementById('open-sidebar-btn');
const closeSidebarBtn = document.getElementById('close-sidebar-btn');
const sidebarNewChatBtn = document.getElementById('sidebar-new-chat-btn');
const sidebarSessionList = document.getElementById('sidebar-session-list');
const sidebarMemoryCount = document.getElementById('sidebar-memory-count');
const sidebarPipelineBtn = document.getElementById('sidebar-pipeline-btn');
const sidebarSettingsBtn = document.getElementById('sidebar-settings-btn');

// Document Upload Controls
const uploadDocBtn = document.getElementById('upload-doc-btn');
const docFileInput = document.getElementById('doc-file-input');
const docPreviewBar = document.getElementById('document-preview-bar');
const docPreviewName = document.getElementById('doc-preview-name');
const docPreviewSub = document.getElementById('doc-preview-sub');
const removeDocBtn = document.getElementById('remove-doc-btn');

// Profile data (global)
let userProfile = null;
let aiProfile = null;
let triggerTimer;

// State tracking (per-session concurrent runs, Antigravity-style switching)
const sessionRuns = new Map();
const sessionQueues = new Map();
const unreadDoneSessions = new Set();
let serverRunningSessions = new Set();
let sessionSwitchSeq = 0;

let activeSessionId = 'default';
let attachedDocument = null;
let attachedImage = null;
let attachedDocuments = [];
let attachedImages = [];
let attachedVideos = [];
let pendingUploads = [];
let queuedPanelCollapsed = false;
let inFlightUploadsCount = 0;
let activeUploadPromises = [];
let enableTrainingLogging = true;
let roleplayEnabled = true;
let notificationsEnabled = localStorage.getItem('shiro_notifications_enabled') !== 'false';
let currentLang = localStorage.getItem('shiro_lang') || 'id';
let currentUILang = currentLang;

function getSessionQueue(sid = activeSessionId) {
    const key = sid || 'default';
    if (!sessionQueues.has(key)) {
        sessionQueues.set(key, []);
    }
    return sessionQueues.get(key);
}

function isSessionRunning(sid = activeSessionId) {
    const key = sid || 'default';
    const r = sessionRuns.get(key);
    return Boolean((r && r.isRunning) || serverRunningSessions.has(key));
}

function isActiveSessionGenerating() {
    const r = sessionRuns.get(activeSessionId || 'default');
    return Boolean(r && r.isRunning);
}

function isAnySessionRunning() {
    for (const r of sessionRuns.values()) {
        if (r && r.isRunning) return true;
    }
    return serverRunningSessions.size > 0;
}

function getSessionTitleById(sid) {
    if (!sid) return 'Chat';
    const found = (currentSessionsData || []).find(s => s.id === sid);
    if (found && found.title) return found.title;
    const run = sessionRuns.get(sid);
    if (run && run.sessionTitle) return run.sessionTitle;
    return `Chat ${String(sid).slice(0, 6)}`;
}

function detachRunDOMRefs(run) {
    if (!run) return;
    run.userMsgEl = null;
    run.assistantMsgEl = null;
    run.assistantBubble = null;
    run.assistantTextEl = null;
}

function detachAllRunDOMRefs() {
    for (const run of sessionRuns.values()) {
        detachRunDOMRefs(run);
    }
}

function updateSidebarRunningIndicators() {
    if (sidebarSessionList) {
        sidebarSessionList.querySelectorAll('.session-item[data-session-id]').forEach((item) => {
            const sid = item.dataset.sessionId;
            const running = isSessionRunning(sid);
            const hasUnread = !running && unreadDoneSessions.has(sid) && sid !== activeSessionId;
            item.classList.toggle('is-running', running);
            item.classList.toggle('is-unread-done', hasUnread);
            const content = item.querySelector('.session-item-content');
            if (!content) return;
            const oldRunBadge = content.querySelector('.session-running-badge');
            const oldDoneDot = content.querySelector('.session-done-dot');
            if (running) {
                if (oldDoneDot) oldDoneDot.remove();
                if (!oldRunBadge) {
                    const badge = document.createElement('span');
                    badge.className = 'session-running-badge';
                    badge.title = t('session_running_label');
                    badge.innerHTML = '<span class="ag-spinner-ring" aria-hidden="true"></span>';
                    const pinBadge = content.querySelector('.session-pin-badge');
                    if (pinBadge) content.insertBefore(badge, pinBadge);
                    else content.appendChild(badge);
                }
            } else {
                if (oldRunBadge) oldRunBadge.remove();
                if (hasUnread) {
                    if (!oldDoneDot) {
                        const dot = document.createElement('span');
                        dot.className = 'session-done-dot';
                        dot.title = t('session_done_title');
                        const pinBadge = content.querySelector('.session-pin-badge');
                        if (pinBadge) content.insertBefore(dot, pinBadge);
                        else content.appendChild(dot);
                    }
                } else if (oldDoneDot) {
                    oldDoneDot.remove();
                }
            }
        });
    }
    if (sessionSelect) {
        Array.from(sessionSelect.options).forEach((opt) => {
            const sid = opt.value;
            const found = (currentSessionsData || []).find(s => s.id === sid);
            if (!found) return;
            const baseTxt = (found.pinned ? '📌 ' : '') + (found.title || `Chat ${sid.slice(0, 6)}`);
            if (isSessionRunning(sid)) opt.textContent = `⏳ ${baseTxt}`;
            else if (unreadDoneSessions.has(sid) && sid !== activeSessionId) opt.textContent = `✓ ${baseTxt}`;
            else opt.textContent = baseTxt;
        });
    }
}

function reattachActiveSessionRunDOM(run) {
    if (!run || !run.isRunning || run.sessionId !== activeSessionId) return;
    const hasProgress = Boolean(
        run.streamText
        || run.liveThoughtText
        || (run.liveAgentSteps && run.liveAgentSteps.length)
        || (run.liveArtifacts && run.liveArtifacts.length)
        || run.activeAgentAction
    );
    if (!hasProgress) {
        showTyping(true, run.statusText || t('status_thinking'));
        return;
    }
    showTyping(false);
    const hasAgentProgress = Boolean((run.liveAgentSteps && run.liveAgentSteps.length) || (run.liveThoughtText && run.liveThoughtText.trim()));
    if (!run.assistantMsgEl && chatMessages && run.finalData && run.finalData.assistant_message_id) {
        try {
            const existingSaved = chatMessages.querySelector(`.message.assistant[data-msg-id="${CSS.escape(run.finalData.assistant_message_id)}"]`);
            if (existingSaved) {
                run.assistantMsgEl = existingSaved;
                run.assistantBubble = existingSaved.querySelector('.bubble');
                run.assistantTextEl = existingSaved.querySelector('.msg-text');
                return;
            }
        } catch (_) {}
    }
    if (!run.assistantMsgEl) {
        run.assistantMsgEl = addMessage(
            'assistant',
            run.streamText || '',
            run.activeAssistantImgUrl,
            null,
            null,
            null,
            null,
            run.activeAgentAction,
            null,
            false,
            {
                agent_steps: run.liveAgentSteps,
                thought_content: run.liveThoughtText,
                thought_duration_sec: run.liveThoughtDuration,
                artifacts: run.liveArtifacts,
                is_running: hasAgentProgress
            }
        );
        if (run.assistantMsgEl) {
            run.assistantBubble = run.assistantMsgEl.querySelector('.bubble');
            run.assistantTextEl = run.assistantMsgEl.querySelector('.msg-text');
            if (run.assistantTextEl && run.streamText) {
                let disp = run.streamText;
                if (((disp.match(/```/g) || []).length) % 2 === 1) disp += '\n```';
                run.assistantTextEl.innerHTML = parseMessageContent(disp);
                if (typeof hljs !== 'undefined') {
                    run.assistantMsgEl.querySelectorAll('pre code[class*="language-"]').forEach(block => {
                        try { hljs.highlightElement(block); } catch (_) {}
                    });
                }
                syncQuickCodeDownloadsInMsg(run.assistantMsgEl);
            }
        }
    }
}

function syncActiveSessionUI() {
    const run = sessionRuns.get(activeSessionId || 'default');
    const runningHere = Boolean(run && run.isRunning);
    setInputLock(runningHere);
    renderQueuedMessagesPanel();
    if (pipelineNavDot) {
        pipelineNavDot.classList.toggle('hidden', !runningHere);
    }
    if (runningHere) {
        if (status) status.textContent = run.statusText || t('status_thinking');
        reattachActiveSessionRunDOM(run);
    } else if (isSessionRunning(activeSessionId)) {
        showTyping(true, t('status_thinking'));
        if (status) status.textContent = t('status_thinking');
    } else {
        showTyping(false);
        if (status) status.textContent = t('status_ready');
    }
    updateSidebarRunningIndicators();
}

// State Mode Konteks Antigravity khusus ShiroHaru-Lyra-Agent
const LYRA_DISPLAY_NAME = 'ShiroHaru-Lyra-Agent';
const LYRA_TIER_LABELS = {
    low: 'ShiroHaru-Lyra Low',
    medium: 'ShiroHaru-Lyra Medium',
    high: 'ShiroHaru-Lyra High',
    extra_high: 'ShiroHaru-Lyra Extra High',
    ultra_high: 'ShiroHaru-Lyra Ultra High'
};
let activeLyraTier = 'high';
let isLyraActive = false;
let isSwitchingLyraTier = false;

function isQwen38UncensoredPath(path) {
    if (!path) return false;
    const base = String(path).split('/').pop().split('\\').pop().toLowerCase();
    const hasQwen38 = base.includes('qwen3.8') || base.includes('qwen3_8') || base.includes('qwen38') || base.includes('qwen-3.8');
    const has27b = base.includes('27b');
    const hasUnc = base.includes('uncensored') || base.includes('hauhaucs') || base.includes('abliterated');
    return hasQwen38 && has27b && hasUnc;
}

function getModelDisplayName(path, modelInfoMap = null) {
    if (!path) return '';
    if (path === 'auto') return 'Auto-Detect';
    if (isQwen38UncensoredPath(path)) return LYRA_DISPLAY_NAME;
    if (modelInfoMap && modelInfoMap[path] && modelInfoMap[path].name) {
        return modelInfoMap[path].name;
    }
    return String(path).split('/').pop().split('\\').pop().replace('.gguf', '');
}

// Kamus Bahasa UI (ID & EN)
const SHIRO_I18N = {
    id: {
        new_chat: 'Chat baru',
        close_sidebar: 'Tutup sidebar',
        open_sidebar: 'Buka sidebar',
        chat_history: 'Riwayat percakapan',
        memory_base: 'Basis ingatan',
        memory_facts_tooltip: 'Jumlah fakta yang diingat Shiro',
        facts_unit: 'fakta',
        pipeline_title: 'Alur eksekusi',
        inspector: 'Inspektur',
        settings: 'Pengaturan',
        configuration: 'Konfigurasi',
        connected: 'Terhubung',
        active_model_tooltip: 'Model aktif saat ini',
        pinned_messages_tooltip: 'Pesan yang disematkan (PIN)',
        pinned_short: 'PIN',
        pinned_messages_title: 'Pesan Tersemat di Sesi Ini',
        pinned_empty: 'Belum ada pesan yang disematkan di sesi ini. Klik ikon PIN pada pesan mana pun untuk menyimpannya di sini.',
        pinned_badge: 'Disematkan',
        pin_msg: 'Sematkan pesan (PIN)',
        unpin_msg: 'Lepas sematan (Unpin)',
        msg_pinned_toast: 'Pesan disematkan ke daftar PIN',
        msg_unpinned_toast: 'Sematan pesan dilepas',
        switch_lang_tooltip: 'Ganti Bahasa UI (ID / EN)',
        active_memory_tooltip: 'Jumlah ingatan aktif',
        memory_label: 'Ingatan:',
        reset_session_tooltip: 'Hapus percakapan sesi ini',
        welcome_greeting: 'Halo Kakak. Ada yang bisa Shiro bantu hari ini?',
        new_session_greeting: 'Halo Kakak! Sesi obrolan baru siap. Mau bahas atau tanyakan apa sekarang?',
        latest_messages: 'Pesan terbaru',
        scroll_bottom_tooltip: 'Gulir ke pesan terbaru',
        doc_ready_sub: 'Siap dirangkum atau diperiksa',
        remove_doc: 'Hapus dokumen',
        img_ready_sub: 'Siap dianalisis',
        remove_img: 'Hapus gambar',
        input_placeholder: 'Tulis pesan...',
        doc_input_placeholder: "Ketik perintah (contoh: 'Rangkum isi berkas ini' atau 'Periksa kode ini')...",
        attach_file_tooltip: 'Lampirkan banyak berkas sekaligus (kode, video MP4/WebM/MOV, PDF, Word, ZIP, TXT, dll.)',
        files_btn: 'Berkas',
        attach_img_tooltip: 'Lampirkan gambar',
        images_btn: 'Gambar',
        open_cam_tooltip: 'Ambil foto dengan kamera',
        camera_btn: 'Kamera',
        send_msg_tooltip: 'Kirim pesan (Enter)',
        stop_resp_tooltip: 'Hentikan respons',
        status_ready: 'Siap',
        status_thinking: 'Shiro sedang berpikir...',
        status_typing: 'Shiro sedang mengetik...',
        status_processing: 'Shiro sedang memproses...',
        status_input_locked: 'Shiro sedang memproses... Mohon tunggu sebentar...',
        status_tool_running: 'Sedang mengeksekusi instruksi...',
        status_stopped: 'Dihentikan',
        status_extracting: 'Mengekstrak berkas...',
        status_doc_ready: 'Berkas siap',
        download_code: 'Unduh',
        download_code_tooltip: 'Unduh kode sebagai berkas',
        downloaded_code: 'Tersimpan',
        quick_files_btn: 'Unduh File',
        quick_files_tooltip: 'Unduh cepat berkas & kode dari AI tanpa scroll',
        download_all_files: 'Unduh semua',
        ai_generated_tag: 'Dari AI',
        copy_code: 'Salin',
        copy_code_tooltip: 'Salin kode ke papan klip',
        copied_code: 'Tersalin',
        shortcut_send: 'kirim',
        shortcut_newline: 'baris baru',
        camera_inactive: 'Kamera tidak aktif',
        switch_camera: 'Ganti kamera',
        capture_photo: 'Ambil foto',
        pipeline_sub: 'Geser node untuk menata ulang. Hanya mengubah tampilan, eksekusi tetap sama.',
        fullscreen: 'Layar penuh',
        settings_subtitle: 'Konfigurasi bahasa, privasi training, profil, model inferensi, API, dan tampilan',
        tab_user: 'Anda',
        tab_privacy: 'Privasi',
        tab_model: 'Model',
        tab_theme: 'Tema',
        chat_options: 'Menu opsi percakapan',
        menu_share_chat: 'Bagikan percakapan',
        menu_files_chat: 'File dalam percakapan ini',
        menu_pin_chat: 'Sematkan',
        menu_unpin_chat: 'Lepas sematan',
        menu_rename_chat: 'Ganti nama',
        menu_pinned_msgs: 'Pesan tersemat',
        menu_export_chat: 'Ekspor percakapan',
        menu_lang_switch: 'Ganti Bahasa (ID / EN)',
        rename_chat_title: 'Ganti nama percakapan',
        rename_chat_sub: 'Beri nama yang mudah diingat untuk sesi obrolan ini',
        rename_input_label: 'Judul percakapan baru',
        cancel: 'Batal',
        save: 'Simpan',
        delete: 'Hapus',
        chat_copied_toast: 'Teks percakapan berhasil disalin ke papan klip',
        no_files_in_chat: 'Belum ada file terlampir di percakapan ini',
        session_pinned_toast: 'Percakapan disematkan ke daftar teratas',
        session_unpinned_toast: 'Sematan percakapan dilepas',
        session_renamed_toast: 'Nama percakapan berhasil diubah',
        export_started_toast: 'Mengunduh berkas percakapan...',
        quick_prefs_title: 'Preferensi Bahasa & Data Training',
        ui_language_label: 'Bahasa Antarmuka (UI Language)',
        ui_language_help: 'Pilih bahasa tampilan aplikasi Web UI. Perubahan diterapkan seketika tanpa memuat ulang halaman.',
        privacy_training_header: 'Privasi Memori & Dataset Training',
        training_toggle_title: 'Simpan Data untuk Training Model',
        training_toggle_desc: 'Jika dinonaktifkan (OFF), ingatan hanya berlaku selama 1 sesi aktif dan tidak akan direkam ke dataset training model.',
        training_status_on: 'Status: AKTIF — Percakapan direkam untuk meningkatkan kecerdasan model.',
        training_status_off: 'Status: NONAKTIF (Mode Sesi Privat) — Ingatan hanya disimpan selama 1 sesi aktif, tidak direkam untuk training.',
        training_toast_on: 'Perekaman data training DIAKTIFKAN',
        training_toast_off: 'Mode Privat AKTIF: Hanya mengingat 1 sesi tanpa merekam data training',
        user_photo_label: 'Foto profil Anda',
        user_photo_help: 'Format gambar persegi (JPG, PNG, WEBP) disarankan.',
        user_name_label: 'Nama panggilan',
        user_name_placeholder: 'Nama Anda',
        user_name_help: 'Digunakan Shiro saat menyapa Anda dalam percakapan.',
        user_desc_label: 'Catatan konteks tentang Anda',
        user_desc_placeholder: 'Misalnya bidang pekerjaan, bahasa pemrograman favorit, atau gaya penjelasan yang disukai',
        save_user_profile: 'Simpan profil Anda',
        ai_photo_label: 'Foto avatar asisten',
        ai_photo_help: 'Ditampilkan pada setiap pesan balasan asisten.',
        ai_name_label: 'Nama asisten',
        ai_desc_label: 'Karakter dan instruksi gaya bicara',
        ai_desc_placeholder: 'Tentukan karakter, nada bicara, dan batasan perilaku asisten',
        ai_desc_help: 'Kosongkan untuk kembali ke karakter bawaan Shiro (adik manja). Jika diisi (misal Megumin pemalu), peran bawaan digantikan sesuai karakter yang Anda tentukan secara dinamis.',
        save_ai_profile: 'Simpan profil asisten',
        main_llm_title: 'Model bahasa utama',
        select_gguf_label: 'Pilih berkas model (.gguf)',
        select_gguf_help: 'Berkas .gguf di dalam direktori model/ dipindai secara otomatis.',
        model_folder_hint: 'Salin berkas .gguf baru ke folder model/ lalu buka kembali jendela ini untuk memuatnya.',
        apply_model_btn: 'Terapkan model',
        vision_moe_title: 'Orkestrasi visi (MoE)',
        vision_strategy_label: 'Strategi pemrosesan gambar',
        moe_opt_auto: 'Otomatis: gunakan model visi jika model utama berbasis teks',
        moe_opt_concurrent: 'Berdampingan: model visi tetap di VRAM (GPU kapasitas besar)',
        moe_opt_swap: 'Bergantian: muat model secara bergilir (hemat VRAM)',
        moe_opt_off: 'Nonaktif: hanya ekstraksi OCR lokal',
        vision_moe_help: 'Memasangkan model visi Qwen2.5-VL dengan model percakapan untuk membaca lampiran visual.',
        save_vision_mode: 'Simpan mode visi',
        theme_presets_label: 'Preset skema warna',
        theme_custom_title: 'Penyesuaian warna kustom',
        theme_bg_label: 'Permukaan latar',
        theme_fg_label: 'Teks utama',
        theme_accent_label: 'Aksen fokus & tautan',
        theme_reset_btn: 'Kembalikan ke tema bawaan',
        api_key_title: 'Kunci autentikasi (API Key)',
        active_key_label: 'Kunci aktif',
        copy_btn: 'Salin',
        api_key_help: 'Sertakan pada header Authorization: Bearer <KEY> atau X-API-Key: <KEY> untuk seluruh endpoint di bawah.',
        regen_api_key: 'Buat ulang API key',
        copy_url_btn: 'Salin URL',
        ep_v1_name: 'Persona Bahasa Indonesia',
        ep_v1_desc: 'Persona Shiro berbahasa Indonesia penuh. Siap dihubungkan ke integrasi WhatsApp, Telegram, atau klien eksternal.',
        ep_v2_name: 'VTuber & VoiceVox',
        ep_v2_desc: 'Keluaran bahasa Jepang terformat [Tag] "..." khusus sintesis suara VoiceVox dan pipeline VTuber.',
        ep_v3_name: 'System Prompt Kustom',
        ep_v3_desc: 'Mengikuti instruksi sistem dari klien sepenuhnya tanpa batasan persona bawaan. Cocok untuk otomasi kode dan riset.',
        image_preview: 'Pratinjau gambar',
        doc_preview: 'Pratinjau berkas',
        copy_text_btn: 'Salin teks',
        open_original_btn: 'Buka asli',
        document_tab: 'Dokumen',
        extracted_text_tab: 'Teks hasil ekstraksi',
        view_doc_action: 'Lihat berkas',
        edit_msg: 'Edit pesan',
        copy_msg: 'Salin pesan',
        copy_reply: 'Salin jawaban',
        regen_reply: 'Buat ulang jawaban',
        no_sessions: 'Belum ada riwayat chat.',
        delete_chat_tooltip: 'Hapus chat ini',
        files_in_chat_title: 'File dalam percakapan',
        no_files_title: 'Belum ada file di chat ini',
        no_files_desc: 'File atau gambar yang dikirimkan akan tersimpan dan dapat dilihat atau dilampirkan kembali di sini.',
        upload_new_file: 'Unggah berkas',
        attach_to_chat: 'Lampirkan ke chat',
        view_file: 'Lihat file',
        file_attached_toast: 'Berkas berhasil dilampirkan ke composer!',
        image_attached_toast: 'Gambar berhasil dilampirkan ke composer!',
        share_modal_title: 'Bagikan percakapan',
        share_modal_sub: 'Tautan unik untuk mengakses percakapan ini secara langsung',
        share_link_label: 'Tautan sesi percakapan',
        copy_link_btn: 'Salin Tautan',
        copied: 'Tersalin!',
        choose_file: 'Pilih Berkas',
        no_file_chosen: 'Belum ada berkas dipilih',
        link_copied_toast: 'Tautan percakapan berhasil disalin ke clipboard!',
        session_not_found_toast: 'Sesi percakapan tidak ditemukan.',
        roleplay_panel_title: 'Mode Roleplay Karakter',
        roleplay_toggle_title: 'Aktifkan Roleplay Bawaan (Shiro)',
        roleplay_toggle_desc: 'Jika aktif, asisten menggunakan persona adik manja Shiro. Jika nonaktif, asisten bekerja penuh sebagai AI Agent profesional ShiroHaru tanpa roleplay atau panggilan Kakak.',
        roleplay_status_on: 'Mode Roleplay AKTIF — Asisten merespons dengan persona hangat khas Shiro.',
        roleplay_status_off: 'Mode Roleplay NONAKTIF — Asisten bekerja sebagai AI Agent penuh ShiroHaru (tanpa roleplay/panggilan Kakak).',
        roleplay_toast_on: 'Mode Roleplay Shiro diaktifkan.',
        roleplay_toast_off: 'Mode Full Agent ShiroHaru diaktifkan (tanpa roleplay).',
        uploading_file: 'Mengunggah berkas...',
        uploading_video: 'Mengunggah video...',
        uploading_image: 'Memuat gambar...',
        video_ready_sub: 'Video siap diputar & dianalisis',
        click_to_play_video: 'Klik untuk memutar video',
        video_preview: 'Pratinjau Video',
        image_preview: 'Pratinjau Gambar',
        image_ready_sub: 'Gambar siap',
        queued_title: 'Pesan Terantre',
        queued_subtitle: 'Terkirim otomatis setelah asisten selesai bekerja',
        sources_browser: 'Sumber Browser',
        session_running_label: 'Sedang berjalan',
        session_done_title: 'Sesi selesai diproses',
        session_done_desc: 'Respons selesai dan siap dibaca.',
        session_error_title: 'Sesi berhenti karena kendala',
        open_session_btn: 'Buka',
        close_notif_tooltip: 'Tutup notifikasi',
        mute_notif_tooltip: 'Nonaktifkan notifikasi sesi',
        notifications_panel_title: 'Notifikasi Sesi',
        notifications_toggle_title: 'Aktifkan Notifikasi Selesai',
        notifications_toggle_desc: 'Jika dinonaktifkan (OFF), popup notifikasi pojok kanan bawah saat sesi selesai tidak akan muncul, namun indikator di sidebar tetap aktif.',
        notifications_status_on: 'Status: AKTIF — Notifikasi muncul saat sesi selesai diproses.',
        notifications_status_off: 'Status: NONAKTIF — Popup notifikasi dimatikan agar tidak mengganggu.',
        notifications_toast_on: 'Notifikasi penyelesaian sesi DIAKTIFKAN',
        notifications_toast_off: 'Notifikasi penyelesaian sesi DINONAKTIFKAN'
    },
    en: {
        new_chat: 'New chat',
        close_sidebar: 'Close sidebar',
        open_sidebar: 'Open sidebar',
        chat_history: 'Conversation history',
        memory_base: 'Memory base',
        memory_facts_tooltip: 'Number of facts remembered by Shiro',
        facts_unit: 'facts',
        pipeline_title: 'Execution pipeline',
        inspector: 'Inspector',
        settings: 'Settings',
        configuration: 'Configuration',
        connected: 'Connected',
        active_model_tooltip: 'Currently active model',
        pinned_messages_tooltip: 'Pinned messages (PIN)',
        pinned_short: 'PIN',
        pinned_messages_title: 'Pinned Messages in This Session',
        pinned_empty: 'No pinned messages in this session yet. Click the PIN icon on any message to save it here.',
        pinned_badge: 'Pinned',
        pin_msg: 'Pin message',
        unpin_msg: 'Unpin message',
        msg_pinned_toast: 'Message pinned to list',
        msg_unpinned_toast: 'Message unpinned',
        switch_lang_tooltip: 'Switch UI Language (ID / EN)',
        active_memory_tooltip: 'Active memory turns',
        memory_label: 'Memory:',
        reset_session_tooltip: 'Clear this session conversation',
        welcome_greeting: 'Hello! How can Shiro help you today?',
        new_session_greeting: 'Hello! A fresh chat session is ready. What would you like to discuss?',
        latest_messages: 'Latest messages',
        scroll_bottom_tooltip: 'Scroll to latest messages',
        doc_ready_sub: 'Ready to summarize or inspect',
        remove_doc: 'Remove file',
        img_ready_sub: 'Ready to analyze',
        remove_img: 'Remove image',
        input_placeholder: 'Write a message...',
        doc_input_placeholder: "Type instructions (e.g., 'Summarize this file' or 'Review this code')...",
        attach_file_tooltip: 'Attach multiple files at once (code, video MP4/WebM/MOV, PDF, Word, ZIP, TXT, etc.)',
        files_btn: 'Files',
        attach_img_tooltip: 'Attach image',
        images_btn: 'Images',
        open_cam_tooltip: 'Take photo with camera',
        camera_btn: 'Camera',
        send_msg_tooltip: 'Send message (Enter)',
        stop_resp_tooltip: 'Stop response',
        status_ready: 'Ready',
        status_thinking: 'Shiro is thinking...',
        status_typing: 'Shiro is typing...',
        status_processing: 'Shiro is processing...',
        status_input_locked: 'Shiro is processing... Please wait...',
        status_tool_running: 'Executing instruction...',
        status_stopped: 'Stopped',
        status_extracting: 'Extracting file...',
        status_doc_ready: 'File ready',
        download_code: 'Download',
        download_code_tooltip: 'Download code as file',
        downloaded_code: 'Downloaded',
        quick_files_btn: 'Downloads',
        quick_files_tooltip: 'Quick download AI files & code without scrolling',
        download_all_files: 'Download all',
        ai_generated_tag: 'AI File',
        copy_code: 'Copy',
        copy_code_tooltip: 'Copy code to clipboard',
        copied_code: 'Copied',
        shortcut_send: 'send',
        shortcut_newline: 'new line',
        camera_inactive: 'Camera inactive',
        switch_camera: 'Switch camera',
        capture_photo: 'Capture photo',
        pipeline_sub: 'Drag nodes to rearrange. Visual layout only; execution remains identical.',
        fullscreen: 'Full screen',
        settings_subtitle: 'Configure language, training privacy, profiles, inference models, API, and appearance',
        tab_user: 'You',
        tab_privacy: 'Privacy',
        tab_model: 'Model',
        tab_theme: 'Theme',
        chat_options: 'Conversation options',
        menu_share_chat: 'Share conversation',
        menu_files_chat: 'Files in this chat',
        menu_pin_chat: 'Pin',
        menu_unpin_chat: 'Unpin',
        menu_rename_chat: 'Rename',
        menu_pinned_msgs: 'Pinned messages',
        menu_export_chat: 'Export chat',
        menu_lang_switch: 'Switch Language (ID / EN)',
        rename_chat_title: 'Rename conversation',
        rename_chat_sub: 'Give this conversation a memorable title',
        rename_input_label: 'New conversation title',
        cancel: 'Cancel',
        save: 'Save',
        delete: 'Delete',
        chat_copied_toast: 'Conversation copied to clipboard',
        no_files_in_chat: 'No files attached in this conversation',
        session_pinned_toast: 'Conversation pinned to top',
        session_unpinned_toast: 'Conversation unpinned',
        session_renamed_toast: 'Conversation renamed successfully',
        export_started_toast: 'Downloading conversation file...',
        quick_prefs_title: 'Language & Training Data Preferences',
        ui_language_label: 'Interface Language (Bahasa UI)',
        ui_language_help: 'Choose the display language for the Web UI. Changes apply immediately without page reload.',
        privacy_training_header: 'Memory Privacy & Training Dataset',
        training_toggle_title: 'Save Data for Model Training',
        training_toggle_desc: 'When turned OFF, memory only lasts for 1 active session and will not be recorded into model training datasets.',
        training_status_on: 'Status: ON — Conversations are recorded to improve model intelligence.',
        training_status_off: 'Status: OFF (Session-Only Mode) — Memory only persists for 1 active session; no training data is recorded.',
        training_toast_on: 'Training data recording ENABLED',
        training_toast_off: 'Private Session Mode ON: Session-only memory, training logging disabled',
        user_photo_label: 'Your profile photo',
        user_photo_help: 'Square image format (JPG, PNG, WEBP) recommended.',
        user_name_label: 'Display name',
        user_name_placeholder: 'Your Name',
        user_name_help: 'Used by Shiro when addressing you in conversation.',
        user_desc_label: 'Context notes about you',
        user_desc_placeholder: 'E.g. your profession, favorite programming languages, or preferred explanation style',
        save_user_profile: 'Save your profile',
        ai_photo_label: 'Assistant avatar photo',
        ai_photo_help: 'Displayed next to every assistant reply.',
        ai_name_label: 'Assistant name',
        ai_desc_label: 'Persona and speaking style instructions',
        ai_desc_placeholder: 'Define character traits, tone of voice, and assistant behavior guidelines',
        ai_desc_help: 'Leave blank to use default Shiro persona (affectionate sister). If filled (e.g. Megumin), the default roleplay is dynamically replaced by your custom character.',
        save_ai_profile: 'Save assistant profile',
        main_llm_title: 'Primary language model',
        select_gguf_label: 'Select model file (.gguf)',
        select_gguf_help: '.gguf files inside the model/ directory are scanned automatically.',
        model_folder_hint: 'Copy new .gguf files into the model/ folder and reopen this window to load them.',
        apply_model_btn: 'Apply model',
        vision_moe_title: 'Vision orchestration (MoE)',
        vision_strategy_label: 'Image processing strategy',
        moe_opt_auto: 'Auto: use vision model when primary model is text-only',
        moe_opt_concurrent: 'Concurrent: keep vision model in VRAM (high VRAM GPU)',
        moe_opt_swap: 'Swap: load models alternately (saves VRAM)',
        moe_opt_off: 'Off: local OCR extraction only',
        vision_moe_help: 'Pairs Qwen2.5-VL vision model with the chat model to inspect visual attachments.',
        save_vision_mode: 'Save vision mode',
        theme_presets_label: 'Color scheme presets',
        theme_custom_title: 'Custom color adjustments',
        theme_bg_label: 'Background surface',
        theme_fg_label: 'Primary text',
        theme_accent_label: 'Focus & link accent',
        theme_reset_btn: 'Reset to default theme',
        api_key_title: 'Authentication key (API Key)',
        active_key_label: 'Active key',
        copy_btn: 'Copy',
        api_key_help: 'Include in header Authorization: Bearer <KEY> or X-API-Key: <KEY> for all endpoints below.',
        regen_api_key: 'Regenerate API key',
        copy_url_btn: 'Copy URL',
        ep_v1_name: 'Indonesian Persona',
        ep_v1_desc: 'Full Indonesian Shiro persona. Ready to connect to WhatsApp, Telegram, or external clients.',
        ep_v2_name: 'VTuber & VoiceVox',
        ep_v2_desc: 'Formatted Japanese output [Tag] "..." tailored for VoiceVox speech synthesis and VTuber pipelines.',
        ep_v3_name: 'Custom System Prompt',
        ep_v3_desc: 'Follows client system instructions strictly without default persona constraints. Ideal for code automation and research.',
        image_preview: 'Image preview',
        doc_preview: 'File preview',
        copy_text_btn: 'Copy text',
        open_original_btn: 'Open original',
        document_tab: 'Document',
        extracted_text_tab: 'Extracted text',
        view_doc_action: 'View file',
        edit_msg: 'Edit message',
        copy_msg: 'Copy message',
        copy_reply: 'Copy reply',
        regen_reply: 'Regenerate reply',
        no_sessions: 'No conversation history yet.',
        delete_chat_tooltip: 'Delete this chat',
        files_in_chat_title: 'Files in chat',
        no_files_title: 'No files in this chat yet',
        no_files_desc: 'Files or images uploaded will be saved and can be viewed or re-attached here.',
        upload_new_file: 'Upload file',
        attach_to_chat: 'Attach to chat',
        view_file: 'View file',
        file_attached_toast: 'File attached to composer!',
        image_attached_toast: 'Image attached to composer!',
        share_modal_title: 'Share conversation',
        share_modal_sub: 'Unique link to access this conversation directly',
        share_link_label: 'Conversation session link',
        copy_link_btn: 'Copy Link',
        copied: 'Copied!',
        choose_file: 'Choose File',
        no_file_chosen: 'No file chosen',
        link_copied_toast: 'Conversation link copied to clipboard!',
        session_not_found_toast: 'Conversation session not found.',
        roleplay_panel_title: 'Character Roleplay Mode',
        roleplay_toggle_title: 'Enable Default Roleplay (Shiro)',
        roleplay_toggle_desc: 'When enabled, uses Shiro affectionate sister persona. When disabled, works purely as a professional ShiroHaru AI Agent without roleplay or calling you Kakak.',
        roleplay_status_on: 'Roleplay Mode ON — Assistant responds with Shiro warm sister persona.',
        roleplay_status_off: 'Roleplay Mode OFF — Assistant works as full ShiroHaru AI Agent (no roleplay).',
        roleplay_toast_on: 'Shiro Roleplay mode enabled.',
        roleplay_toast_off: 'Full ShiroHaru Agent mode enabled (roleplay disabled).',
        uploading_file: 'Uploading file...',
        uploading_video: 'Uploading video...',
        uploading_image: 'Loading image...',
        video_ready_sub: 'Video ready to play & analyze',
        click_to_play_video: 'Click to play video',
        video_preview: 'Video Preview',
        image_preview: 'Image Preview',
        image_ready_sub: 'Image ready',
        queued_title: 'Queued Messages',
        queued_subtitle: 'Sends after agent finishes working',
        sources_browser: 'Browser Sources',
        session_running_label: 'Running',
        session_done_title: 'Session completed',
        session_done_desc: 'Response finished and ready to view.',
        session_error_title: 'Session stopped with error',
        open_session_btn: 'Open',
        close_notif_tooltip: 'Dismiss notification',
        mute_notif_tooltip: 'Disable session notifications',
        notifications_panel_title: 'Session Notifications',
        notifications_toggle_title: 'Enable Completion Notifications',
        notifications_toggle_desc: 'When turned OFF, bottom-right completion popups are muted while subtle sidebar indicators remain active.',
        notifications_status_on: 'Status: ON — Notifications appear when a session finishes.',
        notifications_status_off: 'Status: OFF — Completion notification popups are muted.',
        notifications_toast_on: 'Session completion notifications ENABLED',
        notifications_toast_off: 'Session completion notifications DISABLED'
    }
};

function t(key) {
    const dict = SHIRO_I18N[currentLang] || SHIRO_I18N.id;
    return dict[key] || SHIRO_I18N.id[key] || key;
}

function applyI18nToDOM() {
    document.documentElement.lang = currentLang;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (key && SHIRO_I18N[currentLang] && SHIRO_I18N[currentLang][key]) {
            el.textContent = SHIRO_I18N[currentLang][key];
        }
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (key && SHIRO_I18N[currentLang] && SHIRO_I18N[currentLang][key]) {
            el.placeholder = SHIRO_I18N[currentLang][key];
        }
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (key && SHIRO_I18N[currentLang] && SHIRO_I18N[currentLang][key]) {
            el.title = SHIRO_I18N[currentLang][key];
        }
    });

    const navLangCode = document.getElementById('nav-lang-code');
    if (navLangCode) {
        navLangCode.textContent = currentLang.toUpperCase();
    }

    document.querySelectorAll('.lang-btn-id').forEach(btn => btn.classList.toggle('active', currentLang === 'id'));
    document.querySelectorAll('.lang-btn-en').forEach(btn => btn.classList.toggle('active', currentLang === 'en'));

    updateTrainingBannerUI(enableTrainingLogging);
    updateRoleplayModeUI(roleplayEnabled);
    updateNotificationsModeUI(notificationsEnabled);
    updateMemoryCount();
    renderPinnedDrawer();
    renderAttachmentPreviewBars();
    renderQueuedMessagesPanel();
}

async function setUILanguage(lang, syncBackend = true) {
    if (lang !== 'id' && lang !== 'en') return;
    currentLang = lang;
    currentUILang = lang;
    try {
        localStorage.setItem('shiro_lang', lang);
    } catch (e) {}
    applyI18nToDOM();
    if (syncBackend) {
        try {
            await fetch('/api/settings/privacy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ui_language: lang })
            });
        } catch (e) {}
        showToast(lang === 'en' ? 'UI Language switched to English (EN)' : 'Bahasa UI diubah ke Bahasa Indonesia (ID)');
    }
}

function toggleQuickLanguage() {
    const nextLang = currentLang === 'id' ? 'en' : 'id';
    setUILanguage(nextLang, true);
}

function updateTrainingBannerUI(enabled) {
    enableTrainingLogging = Boolean(enabled);
    const t1 = document.getElementById('training-logging-toggle');
    const t2 = document.getElementById('training-logging-toggle-quick');
    if (t1) t1.checked = enableTrainingLogging;
    if (t2) t2.checked = enableTrainingLogging;

    const banner = document.getElementById('training-mode-banner');
    const icon = document.getElementById('training-mode-icon');
    const text = document.getElementById('training-mode-status-text');
    if (banner) {
        banner.classList.toggle('mode-on', enableTrainingLogging);
        banner.classList.toggle('mode-off', !enableTrainingLogging);
    }
    if (icon) {
        icon.className = enableTrainingLogging ? 'ph ph-check-circle' : 'ph ph-lock-key';
    }
    if (text) {
        text.setAttribute('data-i18n', enableTrainingLogging ? 'training_status_on' : 'training_status_off');
        text.textContent = t(enableTrainingLogging ? 'training_status_on' : 'training_status_off');
    }
}

async function toggleTrainingLogging(enabled) {
    updateTrainingBannerUI(enabled);
    try {
        const res = await fetch('/api/settings/privacy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enable_training_logging: Boolean(enabled) })
        });
        const data = await res.json();
        if (data.success) {
            updateTrainingBannerUI(data.enable_training_logging);
            showToast(data.enable_training_logging ? t('training_toast_on') : t('training_toast_off'));
        }
    } catch (e) {
        console.error('Failed to update training logging setting:', e);
    }
}

function updateRoleplayModeUI(enabled) {
    roleplayEnabled = Boolean(enabled);
    const toggle = document.getElementById('roleplay-enabled-toggle');
    if (toggle) toggle.checked = roleplayEnabled;

    const banner = document.getElementById('roleplay-mode-banner');
    const icon = document.getElementById('roleplay-mode-icon');
    const text = document.getElementById('roleplay-mode-status-text');
    if (banner) {
        banner.classList.toggle('mode-on', roleplayEnabled);
        banner.classList.toggle('mode-off', !roleplayEnabled);
    }
    if (icon) {
        icon.className = roleplayEnabled ? 'ph ph-sparkle' : 'ph ph-terminal-window';
    }
    if (text) {
        text.setAttribute('data-i18n', roleplayEnabled ? 'roleplay_status_on' : 'roleplay_status_off');
        text.textContent = t(roleplayEnabled ? 'roleplay_status_on' : 'roleplay_status_off');
    }
}

async function toggleRoleplayMode(enabled) {
    updateRoleplayModeUI(enabled);
    try {
        const res = await fetch('/api/settings/privacy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ roleplay_enabled: Boolean(enabled) })
        });
        const data = await res.json();
        if (data.success && typeof data.roleplay_enabled === 'boolean') {
            updateRoleplayModeUI(data.roleplay_enabled);
            showToast(data.roleplay_enabled ? t('roleplay_toast_on') : t('roleplay_toast_off'));
        }
    } catch (e) {
        console.error('Failed to update roleplay setting:', e);
    }
}

function updateNotificationsModeUI(enabled) {
    notificationsEnabled = Boolean(enabled);
    try {
        localStorage.setItem('shiro_notifications_enabled', notificationsEnabled ? 'true' : 'false');
    } catch (_) {}
    const toggle = document.getElementById('notifications-enabled-toggle');
    if (toggle) toggle.checked = notificationsEnabled;

    const banner = document.getElementById('notifications-mode-banner');
    const icon = document.getElementById('notifications-mode-icon');
    const text = document.getElementById('notifications-mode-status-text');
    if (banner) {
        banner.classList.toggle('mode-on', notificationsEnabled);
        banner.classList.toggle('mode-off', !notificationsEnabled);
    }
    if (icon) {
        icon.className = notificationsEnabled ? 'ph ph-bell-ringing' : 'ph ph-bell-slash';
    }
    if (text) {
        text.setAttribute('data-i18n', notificationsEnabled ? 'notifications_status_on' : 'notifications_status_off');
        text.textContent = t(notificationsEnabled ? 'notifications_status_on' : 'notifications_status_off');
    }
    if (!notificationsEnabled) {
        const stack = document.getElementById('toast-stack');
        if (stack) {
            stack.querySelectorAll('.toast-session-notif').forEach(node => _dismissToastEl(node));
        }
    }
}

async function toggleNotificationsEnabled(enabled) {
    updateNotificationsModeUI(enabled);
    try {
        const res = await fetch('/api/settings/privacy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notifications_enabled: Boolean(enabled) })
        });
        const data = await res.json();
        if (data.success && typeof data.notifications_enabled === 'boolean') {
            updateNotificationsModeUI(data.notifications_enabled);
            showToast(data.notifications_enabled ? t('notifications_toast_on') : t('notifications_toast_off'));
        }
    } catch (e) {
        console.error('Failed to update notifications setting:', e);
    }
}

async function loadPrivacySettings() {
    try {
        const res = await fetch('/api/settings/privacy');
        if (!res.ok) return;
        const data = await res.json();
        if (typeof data.enable_training_logging === 'boolean') {
            updateTrainingBannerUI(data.enable_training_logging);
        }
        if (typeof data.roleplay_enabled === 'boolean') {
            updateRoleplayModeUI(data.roleplay_enabled);
        }
        if (typeof data.notifications_enabled === 'boolean') {
            updateNotificationsModeUI(data.notifications_enabled);
        } else {
            updateNotificationsModeUI(notificationsEnabled);
        }
        const savedLocalLang = localStorage.getItem('shiro_lang');
        if (!savedLocalLang && data.ui_language && (data.ui_language === 'id' || data.ui_language === 'en')) {
            setUILanguage(data.ui_language, false);
        } else {
            applyI18nToDOM();
        }
    } catch (e) {
        console.error('Error loading privacy settings:', e);
    }
}

// Smart Auto-Scroll State & Controls (ChatGPT-Style)
const scrollBottomBtn = document.getElementById('scroll-bottom-btn');
let isUserScrolledUp = false;
let isProgrammaticScroll = false;

function scrollToBottom(force = false, smooth = true) {
    if (!chatViewport) return;
    if (force) {
        isUserScrolledUp = false;
    }
    if (isUserScrolledUp && !force) {
        return;
    }
    isProgrammaticScroll = true;
    if (smooth) {
        chatViewport.scrollTo({
            top: chatViewport.scrollHeight,
            behavior: 'smooth'
        });
    } else {
        chatViewport.scrollTop = chatViewport.scrollHeight;
    }
}

function updateScrollBottomBtnVisibility() {
    if (!chatViewport || !scrollBottomBtn) return;
    const dist = chatViewport.scrollHeight - chatViewport.scrollTop - chatViewport.clientHeight;
    const shouldShow = dist > 70;
    scrollBottomBtn.classList.toggle('hidden', !shouldShow);
    if (shouldShow && isActiveSessionGenerating()) {
        scrollBottomBtn.classList.add('is-streaming');
    } else if (scrollBottomBtn) {
        scrollBottomBtn.classList.remove('is-streaming');
    }
}

if (chatViewport) {
    // Wheel scroll: jika scroll ke atas, langsung lock userScrolledUp agar streaming tidak menarik layar ke bawah
    chatViewport.addEventListener('wheel', (e) => {
        if (e.deltaY < 0) {
            isUserScrolledUp = true;
            if (scrollBottomBtn) {
                scrollBottomBtn.classList.remove('hidden');
                if (isActiveSessionGenerating()) scrollBottomBtn.classList.add('is-streaming');
            }
        } else if (e.deltaY > 0) {
            const dist = chatViewport.scrollHeight - chatViewport.scrollTop - chatViewport.clientHeight;
            if (dist <= 30) {
                isUserScrolledUp = false;
                if (scrollBottomBtn) {
                    scrollBottomBtn.classList.add('hidden');
                    scrollBottomBtn.classList.remove('is-streaming');
                }
            }
        }
    }, { passive: true });

    // Touch scroll (Android / iOS)
    chatViewport.addEventListener('touchmove', () => {
        const dist = chatViewport.scrollHeight - chatViewport.scrollTop - chatViewport.clientHeight;
        if (dist > 70) {
            isUserScrolledUp = true;
        } else if (dist <= 30) {
            isUserScrolledUp = false;
        }
        updateScrollBottomBtnVisibility();
    }, { passive: true });

    // Scroll event umum (drag scrollbar / key navigation)
    chatViewport.addEventListener('scroll', () => {
        if (isProgrammaticScroll) {
            isProgrammaticScroll = false;
            return;
        }
        const dist = chatViewport.scrollHeight - chatViewport.scrollTop - chatViewport.clientHeight;
        if (dist > 70) {
            isUserScrolledUp = true;
        } else if (dist <= 30) {
            isUserScrolledUp = false;
        }
        updateScrollBottomBtnVisibility();
    }, { passive: true });
}

if (scrollBottomBtn) {
    scrollBottomBtn.addEventListener('click', () => {
        isUserScrolledUp = false;
        scrollBottomBtn.classList.add('hidden');
        scrollBottomBtn.classList.remove('is-streaming');
        scrollToBottom(true, true);
    });
}

function getCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Inisialisasi Mermaid.js
if (typeof mermaid !== 'undefined') {
    try {
        mermaid.initialize({
            startOnLoad: false,
            theme: 'dark',
            securityLevel: 'loose',
            themeVariables: {
                darkMode: true,
                background: '#17181b',
                primaryColor: '#1f2125',
                primaryTextColor: '#ececef',
                primaryBorderColor: '#434750',
                lineColor: '#9ea2ad',
                secondaryColor: '#23252a',
                tertiaryColor: '#17181b'
            }
        });
    } catch (e) {
        console.warn('[Mermaid Init Warning]:', e);
    }
}

function applyMermaidTheme() {
    if (typeof mermaid === 'undefined') return;
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    const light = window.ShiroTheme ? window.ShiroTheme.isLight(v('--bg-base') || '#121315') : false;
    try {
        mermaid.initialize({
            startOnLoad: false,
            theme: light ? 'default' : 'dark',
            securityLevel: 'loose',
            themeVariables: {
                darkMode: !light,
                background: v('--bg-surface'),
                primaryColor: v('--bg-elevated'),
                primaryTextColor: v('--text-primary'),
                primaryBorderColor: v('--border-hover'),
                lineColor: v('--text-secondary'),
                secondaryColor: v('--border-default'),
                tertiaryColor: v('--bg-surface')
            }
        });
    } catch (e) {
        console.warn('[Mermaid Theme Warning]:', e);
    }
}

let mermaidCounter = 0;

function looksLikeCodeFilename(cand) {
    if (!cand) return false;
    const cleaned = String(cand).trim().replace(/^[`"'\(\[]+|[`"'\)\],.;:]+$/g, '');
    if (!cleaned || cleaned.startsWith('http://') || cleaned.startsWith('https://')) return false;
    const base = cleaned.split(/[\/\\]/).pop();
    if (!base) return false;
    if (base === 'Dockerfile' || base === 'Makefile' || base.startsWith('.env')) return true;
    if (!base.includes('.')) return false;
    const ext = base.split('.').pop().toLowerCase();
    if (['com', 'org', 'net', 'io', 'id', 'ai', 'dev'].includes(ext) && !cleaned.includes('/')) return false;
    if (/^\d+$/.test(ext)) return false;
    return ext.length >= 1 && ext.length <= 12 && base.length <= 120;
}

function sanitizeDownloadFilename(name) {
    return String(name || '')
        .trim()
        .replace(/^[`"']+|[`"']+$/g, '')
        .split(/[\/\\]/)
        .pop()
        .replace(/[<>:"|?*]/g, '');
}

function extractFilenameForCodeBlock(fenceInfo, precedingText, rawCode) {
    const info = (fenceInfo || '').trim();
    let cleanLang = '';
    let detectedFile = '';

    // 1. Cek fence header (mis. ```python:login.app, ```login.app, ```html filename="index.html")
    const attrM = info.match(/(?:filename|file|title|name)\s*=\s*["']?([^\s"']+)["']?/i);
    if (attrM && looksLikeCodeFilename(attrM[1])) {
        detectedFile = attrM[1].trim();
        const firstTok = info.split(/\s+/)[0].split(':')[0].toLowerCase();
        cleanLang = firstTok.includes('.') ? '' : firstTok;
    } else if (info.includes(':')) {
        const idxCol = info.indexOf(':');
        const left = info.slice(0, idxCol).trim().toLowerCase();
        const right = info.slice(idxCol + 1).trim();
        if (looksLikeCodeFilename(right)) {
            detectedFile = right;
            cleanLang = left;
        }
    } else if (info) {
        const parts = info.split(/\s+/);
        if (looksLikeCodeFilename(parts[0])) {
            detectedFile = parts[0].trim();
            cleanLang = parts[0].includes('.') ? parts[0].split('.').pop().toLowerCase() : '';
        } else {
            cleanLang = parts[0].toLowerCase();
            if (parts[1] && looksLikeCodeFilename(parts[1])) {
                detectedFile = parts[1].trim();
            }
        }
    }

    // 2. Cek 4 baris teks tepat di atas blok kode (mis. ### File: login.app, `login.app`, **login.app**)
    if (!detectedFile && precedingText) {
        const prevLines = precedingText.split(/\r?\n/).map(l => l.trim()).filter(Boolean).slice(-4);
        for (let i = prevLines.length - 1; i >= 0; i--) {
            const line = prevLines[i];
            const mExplicit = line.match(/(?:SHIRO_FILE|filename|file|berkas|simpan\s+sebagai|save\s+as|nama\s+file)\s*[:=]\s*`?([A-Za-z0-9_.\-\/\\]+)`?/i);
            if (mExplicit && looksLikeCodeFilename(mExplicit[1])) {
                detectedFile = mExplicit[1].trim();
                break;
            }
            const mBacktick = line.match(/`([A-Za-z0-9_.\-\/\\]+?\.[A-Za-z0-9]{1,12}|Dockerfile|Makefile|\.env(?:\.[A-Za-z0-9_]+)?)`/);
            if (mBacktick && looksLikeCodeFilename(mBacktick[1])) {
                detectedFile = mBacktick[1].trim();
                break;
            }
            const mHeading = line.match(/^(?:#{1,6}\s*|(?:\d+[\.\)]\s*)?(?:\*\*|__)?(?:File\s*\d*\s*[:\-]?\s*)?)([A-Za-z0-9_.\-\/\\]+?\.[A-Za-z0-9]{1,12})(?:\*\*|__)?\s*:?\s*$/i);
            if (mHeading && looksLikeCodeFilename(mHeading[1])) {
                detectedFile = mHeading[1].trim();
                break;
            }
        }
    }

    // 3. Cek komentar 5 baris pertama di dalam isi kode
    if (!detectedFile && rawCode) {
        const firstLines = rawCode.split('\n').slice(0, 5).join('\n');
        const fnMatch = firstLines.match(/(?:SHIRO_FILE|filename|file|nama\s+berkas|name)\s*[:=]\s*([a-zA-Z0-9_\-\.\/\\]+)/i)
                     || firstLines.match(/^(?:(?:\/\/|#|<!--|\/\*|--)\s*)([a-zA-Z0-9_\-\/\\]+\.[a-zA-Z0-9]{1,12})(?:\s*(?:-->|\*\/))?\s*$/m);
        if (fnMatch && fnMatch[1] && looksLikeCodeFilename(fnMatch[1])) {
            detectedFile = fnMatch[1].trim();
        }
    }

    return {
        lang: cleanLang,
        filename: detectedFile ? sanitizeDownloadFilename(detectedFile) : ''
    };
}

function isDownloadableCodeBlock(cleanLang, detectedFilename, rawCode) {
    if (detectedFilename) return true;
    const trimmed = String(rawCode || '').trim();
    if (!trimmed) return false;
    const nonEmptyLines = trimmed.split(/\r?\n/).filter(ln => ln.trim().length > 0);
    const langLow = String(cleanLang || '').toLowerCase();
    // Jangan tampilkan tombol Unduh untuk perintah terminal 1 baris tanpa nama berkas eksplisit (mis. "shutdown /a")
    if (nonEmptyLines.length <= 1 && (!langLow || ['bash', 'sh', 'shell', 'zsh', 'bat', 'cmd', 'ps1', 'powershell', 'text', 'plaintext'].includes(langLow))) {
        return false;
    }
    if (nonEmptyLines.length <= 1 && trimmed.length < 72) {
        return false;
    }
    return true;
}

function renderDiffCodeHTML(rawCode) {
    const lines = String(rawCode || '').split(/\r?\n/);
    let oldLine = 1;
    let newLine = 1;
    const rows = lines.map((line) => {
        const esc = escapeHtml(line);
        if (line.startsWith('@@')) {
            const m = line.match(/@@\s*-(\d+)(?:,\d+)?\s*\+(\d+)(?:,\d+)?\s*@@/);
            if (m) {
                oldLine = parseInt(m[1], 10);
                newLine = parseInt(m[2], 10);
            }
            return `<div class="diff-line diff-line-hunk"><span class="diff-gutter"></span><span class="diff-gutter"></span><span>${esc}</span></div>`;
        }
        if (line.startsWith('+') && !line.startsWith('+++')) {
            const gNew = newLine++;
            return `<div class="diff-line diff-line-add"><span class="diff-gutter"></span><span class="diff-gutter">${gNew}</span><span>${esc}</span></div>`;
        }
        if (line.startsWith('-') && !line.startsWith('---')) {
            const gOld = oldLine++;
            return `<div class="diff-line diff-line-del"><span class="diff-gutter">${gOld}</span><span class="diff-gutter"></span><span>${esc}</span></div>`;
        }
        const gOld = oldLine++;
        const gNew = newLine++;
        return `<div class="diff-line"><span class="diff-gutter">${gOld}</span><span class="diff-gutter">${gNew}</span><span>${esc}</span></div>`;
    }).join('');
    return `<pre class="md-diff-pre"><code class="language-diff nohighlight">${rows}</code></pre>`;
}

function isSafeMarkdownUrl(rawUrl) {
    const u = String(rawUrl || '').trim();
    if (!u) return false;
    if (/^(?:javascript|data|vbscript):/i.test(u)) return false;
    return /^(?:https?:\/\/|\/|#)/i.test(u);
}

function copyInlineSymbol(el) {
    if (!el) return;
    const txt = el.getAttribute('data-copy') || el.textContent || '';
    if (!txt) return;
    if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(txt).then(() => {
            if (typeof showToast === 'function') {
                showToast((currentLang === 'en' ? 'Copied: ' : 'Disalin: ') + txt);
            }
        }).catch(() => {});
    }
}

function renderKatexMath(tex, displayMode) {
    const raw = String(tex || '').trim();
    if (!raw) return '';
    if (typeof katex !== 'undefined' && typeof katex.renderToString === 'function') {
        try {
            return katex.renderToString(raw, {
                displayMode: Boolean(displayMode),
                throwOnError: false,
                strict: false,
            });
        } catch (_) {}
    }
    return displayMode
        ? `<div class="md-math-block md-math-block-raw">${escapeHtml(raw)}</div>`
        : `<code class="md-math-inline-raw">${escapeHtml(raw)}</code>`;
}

function renderInlineMarkdown(rawText) {
    if (!rawText) return '';
    let txt = escapeHtml(rawText);

    // 1. Lindungi inline code & inline math lebih dulu agar formatter * / ~ / _ tidak menyentuh isinya
    const inlineSlots = [];
    const stashSlot = (html) => {
        const key = `\u0001SHIROINL${inlineSlots.length}\u0002`;
        inlineSlots.push(html);
        return key;
    };

    txt = txt.replace(/`([^`\n]+)`/g, (_, innerEscaped) => {
        const looksLikePathOrFile = /^(?:[A-Za-z0-9_.\-\/\\]+\.[A-Za-z0-9]{1,10}(?::\d+)?|(?:src|app|shiro|static|templates)\/[^\s]+)$/.test(innerEscaped);
        if (looksLikePathOrFile) {
            return stashSlot(`<button type="button" class="md-file-pill" data-copy="${innerEscaped}" onclick="copyInlineSymbol(this)" title="Salin ${innerEscaped}"><i class="ph ph-file-code"></i><span>${innerEscaped}</span></button>`);
        }
        return stashSlot(`<code>${innerEscaped}</code>`);
    });

    // Inline math $...$ (hindari angka harga seperti $100 atau teks dengan spasi di tepi)
    txt = txt.replace(/\$([^\s$][^$\n]*?[^\s$]|[^\s$\d])\$/g, (_, mathExprEsc) => {
        const rawTex = mathExprEsc.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#039;/g, "'");
        return stashSlot(renderKatexMath(rawTex, false));
    });

    // 2. Gambar ![alt](url) (hanya skema aman)
    txt = txt.replace(/!\[([^\]]*)\]\(([^\s)]+)\)/g, (m, alt, rawUrl) => {
        const cleanUrl = rawUrl.replace(/[.,;!?)]+$/, '');
        if (!isSafeMarkdownUrl(cleanUrl)) return escapeHtml(alt || '');
        const safeAlt = (alt || 'Gambar').replace(/"/g, '&quot;');
        const jsUrl = cleanUrl.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        return stashSlot(`<div class="chat-inline-img-wrap" onclick="openImageLightbox('${jsUrl}', '${safeAlt}')" title="Klik untuk melihat pratinjau penuh"><img src="${cleanUrl}" alt="${safeAlt}" class="chat-img-attachment" loading="lazy" onerror="this.outerHTML='<span class=\\'md-img-fallback\\'><i class=\\'ph ph-image-broken\\'></i> ${safeAlt}</span>'"></div>`);
    });

    // 3. Tautan [label](url) — blokir skema berbahaya (javascript:, data:, vbscript:)
    txt = txt.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, rawUrl) => {
        const cleanUrl = rawUrl.replace(/[.,;!?)]+$/, '');
        if (!isSafeMarkdownUrl(cleanUrl)) {
            return label;
        }
        if (/^\d{1,3}$/.test(label.trim())) {
            return stashSlot(`<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="md-citation-pill" title="Sumber: ${cleanUrl}">${label}</a>`);
        }
        return stashSlot(`<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="chat-link" title="Buka: ${cleanUrl}">${label}</a>`);
    });

    // 4. Autolink URL polos
    txt = txt.replace(/(https?:\/\/[^\s<>"']+)/g, (match) => {
        const cleanUrl = match.replace(/[.,;!?)]+$/, '');
        const trailing = match.slice(cleanUrl.length);
        return stashSlot(`<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="chat-link" title="Buka: ${cleanUrl}">${cleanUrl}</a>`) + trailing;
    });

    // 5. Formatting tebal, coret, miring
    txt = txt.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    txt = txt.replace(/__(.+?)__/g, '<strong>$1</strong>');
    txt = txt.replace(/~~(.+?)~~/g, '<del>$1</del>');
    txt = txt.replace(/(^|[^\w])\*([^*\n]+?)\*(?!\w)/g, '$1<em>$2</em>');

    for (let i = 0; i < inlineSlots.length; i++) {
        txt = txt.replace(`\u0001SHIROINL${i}\u0002`, inlineSlots[i]);
    }
    return txt;
}

function splitMarkdownTableCells(rowStr) {
    let s = String(rowStr || '').trim();
    if (s.startsWith('|')) s = s.slice(1);
    if (s.endsWith('|')) s = s.slice(0, -1);
    const cells = [];
    let cur = '';
    let inBacktick = false;
    for (let i = 0; i < s.length; i++) {
        const ch = s[i];
        if (ch === '`' && s[i - 1] !== '\\') {
            inBacktick = !inBacktick;
            cur += ch;
        } else if (ch === '\\' && s[i + 1] === '|') {
            cur += '|';
            i++;
        } else if (ch === '|' && !inBacktick) {
            cells.push(cur.trim());
            cur = '';
        } else {
            cur += ch;
        }
    }
    cells.push(cur.trim());
    return cells;
}

function isGfmTableSeparatorLine(line) {
    const t = String(line || '').trim();
    if (!t.includes('-')) return false;
    const cells = splitMarkdownTableCells(t);
    return cells.length >= 1 && cells.every(c => /^:?-{2,}:?$/.test(c.replace(/\s+/g, '')));
}

function renderGfmTableHTML(headerLine, sepLine, bodyLines) {
    const headers = splitMarkdownTableCells(headerLine);
    const sepCells = splitMarkdownTableCells(sepLine);
    const aligns = headers.map((_, idx) => {
        const sc = (sepCells[idx] || '').trim();
        if (sc.startsWith(':') && sc.endsWith(':')) return 'center';
        if (sc.endsWith(':')) return 'right';
        return 'left';
    });

    const thHTML = headers.map((h, i) => `<th style="text-align:${aligns[i]}">${renderInlineMarkdown(h)}</th>`).join('');
    const bodyHTML = bodyLines.map((rowLn) => {
        const cols = splitMarkdownTableCells(rowLn);
        const tds = headers.map((_, i) => `<td style="text-align:${aligns[i]}">${renderInlineMarkdown(cols[i] || '')}</td>`).join('');
        return `<tr>${tds}</tr>`;
    }).join('');

    return `<div class="md-table-wrap"><table class="md-table"><thead><tr>${thHTML}</tr></thead><tbody>${bodyHTML}</tbody></table></div>`;
}

function renderCalloutOrQuoteHTML(quoteLines) {
    if (!quoteLines.length) return '';
    const first = quoteLines[0].trim();
    const mCall = first.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)$/i);
    if (mCall) {
        const kind = mCall[1].toUpperCase();
        const kindCls = kind.toLowerCase();
        const iconMap = {
            NOTE: 'ph-info',
            TIP: 'ph-lightbulb',
            IMPORTANT: 'ph-sparkle',
            WARNING: 'ph-warning',
            CAUTION: 'ph-warning-octagon'
        };
        const restLines = [];
        if (mCall[2]) restLines.push(mCall[2]);
        for (let i = 1; i < quoteLines.length; i++) restLines.push(quoteLines[i]);
        const bodyHtml = restLines.map(ln => ln.trim() ? renderInlineMarkdown(ln) : '').filter(Boolean).join('<br>');
        return `<div class="md-callout callout-${kindCls}"><div class="md-callout-head"><i class="ph-fill ${iconMap[kind] || 'ph-info'}"></i><span>${kind}</span></div><div class="md-callout-body">${bodyHtml}</div></div>`;
    }
    const innerHtml = quoteLines.map(ln => renderInlineMarkdown(ln)).join('<br>');
    return `<blockquote class="md-quote">${innerHtml}</blockquote>`;
}

function renderListBlockHTML(listLines) {
    if (!listLines.length) return '';
    let doneTasks = 0;
    let totalTasks = 0;
    const parsedItems = listLines.map((raw) => {
        const m = raw.match(/^(\s*)([-*+]|\d+[\.\)])\s+(.*)$/);
        if (!m) return null;
        const indent = m[1].replace(/\t/g, '  ').length;
        const ordered = /^\d/.test(m[2]);
        let content = m[3];
        let isTask = false;
        let checked = false;
        const mTask = content.match(/^\[([ xX])\]\s*(.*)$/);
        if (mTask) {
            isTask = true;
            checked = mTask[1].toLowerCase() === 'x';
            totalTasks++;
            if (checked) doneTasks++;
            content = mTask[2];
        }
        return { indent, ordered, content, isTask, checked };
    }).filter(Boolean);

    if (!parsedItems.length) return '';

    const buildTree = (startIdx, minIndent) => {
        const first = parsedItems[startIdx];
        const tag = first.ordered ? 'ol' : 'ul';
        const isTaskList = parsedItems.some(it => it.isTask && it.indent === first.indent);
        const cls = isTaskList ? 'md-list md-task-list' : 'md-list';
        let html = `<${tag} class="${cls}">`;
        let i = startIdx;
        while (i < parsedItems.length) {
            const it = parsedItems[i];
            if (it.indent < minIndent) break;
            if (it.indent > minIndent) {
                i++;
                continue;
            }
            if (it.ordered !== first.ordered && it.indent === minIndent) {
                break;
            }
            let liInner = it.isTask
                ? `<input type="checkbox" class="md-task-checkbox" disabled${it.checked ? ' checked' : ''}><span>${renderInlineMarkdown(it.content)}</span>`
                : renderInlineMarkdown(it.content);
            const liCls = it.isTask ? ' class="md-task-item"' : '';
            let nextIdx = i + 1;
            if (nextIdx < parsedItems.length && parsedItems[nextIdx].indent > it.indent) {
                const sub = buildTree(nextIdx, parsedItems[nextIdx].indent);
                liInner += sub.html;
                nextIdx = sub.nextIdx;
            }
            html += `<li${liCls}>${liInner}</li>`;
            i = nextIdx;
        }
        html += `</${tag}>`;
        return { html, nextIdx: i };
    };

    let out = '';
    if (totalTasks > 0) {
        const pct = Math.round((doneTasks / totalTasks) * 100);
        out += `<div class="md-task-progress"><span>${doneTasks}/${totalTasks}</span><span class="md-task-bar"><span class="md-task-bar-fill" style="width:${pct}%"></span></span></div>`;
    }
    let idx = 0;
    while (idx < parsedItems.length) {
        const res = buildTree(idx, parsedItems[idx].indent);
        out += res.html;
        idx = res.nextIdx > idx ? res.nextIdx : idx + 1;
    }
    return out;
}

// Parse message formatting: GFM + KaTeX + Callouts + Diff + Mermaid + XSS Sanitization (Antigravity-Style)
function parseMessageContent(text) {
    if (!text) return '';

    // Auto-heal unclosed code fence / display math agar streaming tidak merusak layout
    let normalizedText = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const fenceMatches = normalizedText.match(/```/g);
    if (fenceMatches && fenceMatches.length % 2 === 1) {
        normalizedText += '\n```';
    }
    const mathFenceMatches = normalizedText.match(/\$\$/g);
    if (mathFenceMatches && mathFenceMatches.length % 2 === 1) {
        normalizedText += '\n$$';
    }

    const codeBlocks = [];

    // 1. Ekstrak Fenced Code Blocks (Mermaid, Diff, dan Code Block dengan Download Kondisional)
    let content = normalizedText.replace(/```([^\n`]*)\n([\s\S]*?)```|```([a-zA-Z0-9_\-\.:\/]*)\s*([\s\S]*?)```/g, function(match, info1, code1, info2, code2, offset) {
        const fenceInfo = (info1 !== undefined ? info1 : (info2 || '')).trim();
        const rawCode = (info1 !== undefined ? (code1 || '') : (code2 || '')).trim();
        const precedingSlice = normalizedText.slice(Math.max(0, (offset || 0) - 420), offset || 0);
        const extractedMeta = extractFilenameForCodeBlock(fenceInfo, precedingSlice, rawCode);
        const cleanLang = extractedMeta.lang || '';
        const detectedFilename = extractedMeta.filename || '';
        const placeholder = `\u0001SHIROBLK${codeBlocks.length}\u0002`;

        if (cleanLang === 'mermaid') {
            const escapedCode = escapeHtml(rawCode);
            const mId = `mermaid_${Date.now()}_${++mermaidCounter}`;
            codeBlocks.push(`
                <div class="mermaid-container" id="${mId}">
                    <div class="mermaid-toolbar">
                        <span class="mermaid-badge"><i class="ph ph-tree-structure"></i> Diagram</span>
                        <button type="button" class="btn-toggle-mermaid-code" onclick="toggleMermaidCode(this)">
                            <i class="ph ph-code"></i> Lihat kode
                        </button>
                    </div>
                    <div class="mermaid-diagram-render" id="render_${mId}">
                        <pre class="mermaid-raw-source">${escapedCode}</pre>
                    </div>
                    <pre class="mermaid-raw-code hidden"><code>${escapedCode}</code></pre>
                </div>
            `);
        } else {
            const canDownload = isDownloadableCodeBlock(cleanLang, detectedFilename, rawCode);
            const displayLang = cleanLang || (detectedFilename.includes('.') ? detectedFilename.split('.').pop().toLowerCase() : 'kode');
            const langClass = cleanLang ? `language-${cleanLang}` : 'nohighlight';
            const headerLabelHTML = detectedFilename
                ? `<span class="code-filename-badge" title="${escapeHtml(detectedFilename)}">${escapeHtml(detectedFilename)}</span>${cleanLang && cleanLang !== detectedFilename.toLowerCase() ? `<span class="code-lang-sub">${escapeHtml(cleanLang)}</span>` : ''}`
                : `${escapeHtml(displayLang)}`;
            const dlBtnHTML = canDownload
                ? `<button type="button" class="btn-code-action btn-download-code" onclick="downloadCodeSnippet(this)" title="${t('download_code_tooltip')}" aria-label="Unduh Berkas Kode"><i class="ph ph-download-simple"></i> <span>${t('download_code')}</span></button>`
                : '';
            const codeInnerHTML = (cleanLang === 'diff')
                ? renderDiffCodeHTML(rawCode)
                : `<pre><code class="${langClass}">${escapeHtml(rawCode)}</code></pre>`;
            codeBlocks.push(`
                <div class="code-block-wrapper" data-lang="${escapeHtml(cleanLang || 'txt')}" data-filename="${escapeHtml(detectedFilename)}" data-downloadable="${canDownload ? 'true' : 'false'}">
                    <div class="code-block-header">
                        <span class="code-lang-label">${headerLabelHTML}</span>
                        <div class="code-block-actions">
                            ${dlBtnHTML}
                            <button type="button" class="btn-code-action btn-copy-code" onclick="copyCodeSnippet(this)" title="${t('copy_code_tooltip')}" aria-label="Salin Kode">
                                <i class="ph ph-copy"></i> <span>${t('copy_code')}</span>
                            </button>
                        </div>
                    </div>
                    ${codeInnerHTML}
                </div>
            `);
        }
        return `\n${placeholder}\n`;
    });

    // 1b. Ekstrak Display Math Blocks $$...$$
    content = content.replace(/\$\$([\s\S]+?)\$\$/g, (_, mathBody) => {
        const placeholder = `\u0001SHIROBLK${codeBlocks.length}\u0002`;
        codeBlocks.push(`<div class="md-math-block">${renderKatexMath(mathBody, true)}</div>`);
        return `\n${placeholder}\n`;
    });

    // 2. Block-Level Markdown Parser (Heading, HR, GFM Table, Callout/Blockquote, Nested List & Task List, Paragraph)
    const lines = content.split('\n');
    const htmlBlocks = [];
    let i = 0;
    const isListLine = (ln) => /^\s*(?:[-*+]|\d+[\.\)])\s+/.test(ln || '');

    while (i < lines.length) {
        const ln = lines[i];
        const trimmed = ln.trim();
        if (!trimmed) {
            i++;
            continue;
        }
        const mSlot = trimmed.match(/^\u0001SHIROBLK(\d+)\u0002$/);
        if (mSlot) {
            htmlBlocks.push(trimmed);
            i++;
            continue;
        }
        // Horizontal rule
        if (/^(?:---+|\*\*\*+|___+)$/.test(trimmed)) {
            htmlBlocks.push('<hr class="md-hr">');
            i++;
            continue;
        }
        // Heading (# .. ######)
        const mHead = trimmed.match(/^(#{1,6})\s+(.+)$/);
        if (mHead) {
            const lvl = mHead[1].length;
            htmlBlocks.push(`<h${lvl} class="md-h${lvl}">${renderInlineMarkdown(mHead[2])}</h${lvl}>`);
            i++;
            continue;
        }
        // GFM Table
        if (trimmed.includes('|') && i + 1 < lines.length && isGfmTableSeparatorLine(lines[i + 1])) {
            const headerLine = trimmed;
            const sepLine = lines[i + 1].trim();
            i += 2;
            const bodyRows = [];
            while (i < lines.length) {
                const rowT = lines[i].trim();
                if (!rowT || !rowT.includes('|') || /^\u0001SHIROBLK\d+\u0002$/.test(rowT)) break;
                bodyRows.push(rowT);
                i++;
            }
            htmlBlocks.push(renderGfmTableHTML(headerLine, sepLine, bodyRows));
            continue;
        }
        // Blockquote / GitHub Callout (> [!NOTE|TIP|IMPORTANT|WARNING|CAUTION])
        if (trimmed.startsWith('>')) {
            const qLines = [];
            while (i < lines.length && lines[i].trim().startsWith('>')) {
                qLines.push(lines[i].trim().replace(/^>\s?/, ''));
                i++;
            }
            htmlBlocks.push(renderCalloutOrQuoteHTML(qLines));
            continue;
        }
        // Lists & Task Lists
        if (isListLine(ln)) {
            const lLines = [];
            while (i < lines.length && isListLine(lines[i])) {
                lLines.push(lines[i]);
                i++;
            }
            htmlBlocks.push(renderListBlockHTML(lLines));
            continue;
        }
        // Paragraph (stops cleanly at block starters)
        const pLines = [];
        while (i < lines.length) {
            const cur = lines[i];
            const curT = cur.trim();
            if (!curT) break;
            if (/^\u0001SHIROBLK\d+\u0002$/.test(curT)) break;
            if (/^(?:---+|\*\*\*+|___+)$/.test(curT)) break;
            if (/^#{1,6}\s+/.test(curT)) break;
            if (curT.startsWith('>')) break;
            if (isListLine(cur)) break;
            if (curT.includes('|') && i + 1 < lines.length && isGfmTableSeparatorLine(lines[i + 1])) break;
            pLines.push(renderInlineMarkdown(cur));
            i++;
        }
        if (pLines.length) {
            htmlBlocks.push(`<p class="md-p">${pLines.join('<br>')}</p>`);
        }
    }

    let rendered = htmlBlocks.join('\n');

    // 3. Pulihkan blok kode, math, & diagram mermaid
    codeBlocks.forEach((blockHtml, idx) => {
        rendered = rendered.replace(`\u0001SHIROBLK${idx}\u0002`, blockHtml);
    });

    // 4. Sanitasi Anti-XSS Ketat via DOMPurify
    if (typeof DOMPurify !== 'undefined') {
        try {
            rendered = DOMPurify.sanitize(rendered, {
                ADD_TAGS: ['svg', 'path', 'marker', 'g', 'rect', 'circle', 'line', 'polygon', 'text', 'tspan', 'style', 'defs', 'details', 'summary', 'hr', 'input', 'math', 'semantics', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'mtable', 'mtr', 'mtd', 'annotation'],
                ADD_ATTR: ['target', 'rel', 'onclick', 'data-*', 'data-filename', 'data-lang', 'data-downloadable', 'data-copy', 'download', 'class', 'id', 'd', 'fill', 'stroke', 'viewBox', 'width', 'height', 'style', 'title', 'type', 'disabled', 'checked', 'aria-hidden'],
                ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|\/|#)/i,
            });
        } catch (pErr) {
            console.warn('[DOMPurify Warning]:', pErr);
        }
    }

    return rendered;
}

function renderAvatarContent(profile, fallbackChar) {
    if (profile && profile.image) {
        return `<img src="data:${profile.image_mime};base64,${profile.image}" alt="${profile.name || fallbackChar}">`;
    }
    return profile?.name?.[0]?.toUpperCase() || fallbackChar;
}

const CODE_LANG_EXT_MAP = {
    'html': 'html',
    'htm': 'html',
    'xhtml': 'html',
    'css': 'css',
    'scss': 'scss',
    'sass': 'sass',
    'less': 'less',
    'js': 'js',
    'javascript': 'js',
    'jsx': 'jsx',
    'ts': 'ts',
    'typescript': 'ts',
    'tsx': 'tsx',
    'vue': 'vue',
    'svelte': 'svelte',
    'astro': 'astro',
    'py': 'py',
    'python': 'py',
    'pyw': 'py',
    'ipynb': 'ipynb',
    'json': 'json',
    'jsonl': 'jsonl',
    'json5': 'json5',
    'xml': 'xml',
    'yaml': 'yaml',
    'yml': 'yaml',
    'toml': 'toml',
    'sql': 'sql',
    'prisma': 'prisma',
    'graphql': 'graphql',
    'gql': 'graphql',
    'c': 'c',
    'cpp': 'cpp',
    'c++': 'cpp',
    'cc': 'cpp',
    'cxx': 'cpp',
    'h': 'h',
    'hpp': 'hpp',
    'hh': 'hpp',
    'cs': 'cs',
    'csharp': 'cs',
    'java': 'java',
    'kt': 'kt',
    'kotlin': 'kt',
    'kts': 'kts',
    'rs': 'rs',
    'rust': 'rs',
    'go': 'go',
    'golang': 'go',
    'php': 'php',
    'rb': 'rb',
    'ruby': 'rb',
    'sh': 'sh',
    'bash': 'sh',
    'zsh': 'sh',
    'ps1': 'ps1',
    'powershell': 'ps1',
    'bat': 'bat',
    'cmd': 'cmd',
    'r': 'r',
    'dart': 'dart',
    'swift': 'swift',
    'lua': 'lua',
    'pl': 'pl',
    'pm': 'pm',
    'dockerfile': 'dockerfile',
    'docker': 'dockerfile',
    'makefile': 'mk',
    'make': 'mk',
    'cmake': 'cmake',
    'proto': 'proto',
    'ini': 'ini',
    'cfg': 'cfg',
    'conf': 'conf',
    'properties': 'properties',
    'env': 'env',
    'markdown': 'md',
    'md': 'md',
    'txt': 'txt',
    'text': 'txt'
};

function resolveCodeBlockMeta(wrapper) {
    if (!wrapper) return null;
    const codeEl = wrapper.querySelector('code');
    if (!codeEl) return null;
    const text = codeEl.innerText || codeEl.textContent;
    if (!text) return null;

    const rawLang = (wrapper.dataset.lang || '').trim().toLowerCase();
    const ext = CODE_LANG_EXT_MAP[rawLang] || (rawLang && /^[a-z0-9]+$/.test(rawLang) ? rawLang : 'txt');

    let filename = sanitizeDownloadFilename(wrapper.dataset.filename || '');
    if (!filename) {
        const firstLines = text.split('\n').slice(0, 5).join('\n');
        const fnMatch = firstLines.match(/(?:SHIRO_FILE|filename|file|nama\s+berkas|name)\s*[:=]\s*([a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+)/i)
                     || firstLines.match(/^(?:(?:\/\/|#|<!--|\/\*|--)\s*)([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)/m);
        if (fnMatch && fnMatch[1]) {
            filename = sanitizeDownloadFilename(fnMatch[1]);
        }
    }
    if (!filename && looksLikeCodeFilename(rawLang)) {
        filename = sanitizeDownloadFilename(rawLang);
    }

    if (!filename) {
        if (ext === 'html') filename = 'index.html';
        else if (ext === 'css') filename = 'style.css';
        else if (ext === 'js') filename = 'script.js';
        else if (ext === 'ts') filename = 'main.ts';
        else if (ext === 'jsx') filename = 'App.jsx';
        else if (ext === 'tsx') filename = 'App.tsx';
        else if (ext === 'vue') filename = 'App.vue';
        else if (ext === 'py') filename = 'main.py';
        else if (ext === 'json') filename = 'data.json';
        else if (ext === 'sql') filename = 'query.sql';
        else if (ext === 'sh') filename = 'script.sh';
        else if (ext === 'ps1') filename = 'script.ps1';
        else if (ext === 'cpp' || ext === 'c' || ext === 'cs' || ext === 'java' || ext === 'go' || ext === 'rs') filename = `main.${ext}`;
        else if (ext === 'dockerfile') filename = 'Dockerfile';
        else filename = `shiro_${rawLang || 'code'}.${ext}`;
    }

    const mimeTypes = {
        'html': 'text/html;charset=utf-8',
        'css': 'text/css;charset=utf-8',
        'js': 'text/javascript;charset=utf-8',
        'ts': 'text/typescript;charset=utf-8',
        'py': 'text/x-python;charset=utf-8',
        'json': 'application/json;charset=utf-8',
        'xml': 'application/xml;charset=utf-8',
        'md': 'text/markdown;charset=utf-8',
        'sql': 'text/plain;charset=utf-8',
        'sh': 'application/x-sh;charset=utf-8',
        'ps1': 'text/plain;charset=utf-8',
        'txt': 'text/plain;charset=utf-8'
    };
    const mimeType = mimeTypes[ext] || 'text/plain;charset=utf-8';
    return { text, filename, mimeType, ext, lang: rawLang };
}

function downloadCodeFromWrapper(wrapper, feedbackBtn = null, silent = false) {
    const meta = resolveCodeBlockMeta(wrapper);
    if (!meta) return null;
    try {
        const blob = new Blob([meta.text], { type: meta.mimeType });
        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = blobUrl;
        link.download = meta.filename;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(() => URL.revokeObjectURL(blobUrl), 1500);

        if (feedbackBtn) {
            const span = feedbackBtn.querySelector('span');
            const icon = feedbackBtn.querySelector('i');
            const oldText = span ? span.textContent : '';
            const origIconCls = icon ? icon.className : 'ph ph-download-simple';
            if (span && feedbackBtn.classList.contains('btn-download-code')) {
                span.textContent = t('downloaded_code') || 'Tersimpan';
            }
            if (icon) icon.className = 'ph ph-check';
            feedbackBtn.classList.add('download-success');
            setTimeout(() => {
                if (span && feedbackBtn.classList.contains('btn-download-code')) {
                    span.textContent = oldText || t('download_code') || 'Unduh';
                }
                if (icon) icon.className = origIconCls;
                feedbackBtn.classList.remove('download-success');
            }, 2000);
        }

        if (!silent && typeof showToast === 'function') {
            const toastMsg = currentLang === 'en'
                ? `File "${meta.filename}" downloaded`
                : `Berkas "${meta.filename}" berhasil diunduh`;
            showToast(toastMsg);
        }
        return meta.filename;
    } catch (err) {
        console.error('Error downloading code snippet:', err);
        if (!silent && typeof showToast === 'function') {
            showToast(currentLang === 'en' ? 'Download failed' : 'Gagal mengunduh berkas');
        }
        return null;
    }
}

function downloadCodeSnippet(btn) {
    const wrapper = btn ? btn.closest('.code-block-wrapper') : null;
    if (!wrapper) return;
    downloadCodeFromWrapper(wrapper, btn, false);
}

function syncQuickCodeDownloadsInMsg(msgEl) {
    if (!msgEl || !msgEl.classList.contains('assistant')) return;
    const container = msgEl.querySelector('.bubble-container');
    if (!container) return;
    const wrappers = Array.from(container.querySelectorAll('.code-block-wrapper')).filter(
        wr => wr.dataset.downloadable !== 'false'
    );
    const existingBar = container.querySelector('.msg-quick-downloads');
    if (!wrappers.length) {
        if (existingBar) existingBar.remove();
        return;
    }

    const bar = existingBar || document.createElement('div');
    bar.className = 'msg-quick-downloads';
    bar.innerHTML = '';

    wrappers.forEach((wr) => {
        const meta = resolveCodeBlockMeta(wr);
        if (!meta) return;
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'msg-quick-dl-chip';
        chip.title = `${t('download_code')}: ${meta.filename}`;
        chip.innerHTML = `<i class="ph ph-download-simple"></i> <span>${escapeHtml(meta.filename)}</span>`;
        chip.addEventListener('click', () => downloadCodeFromWrapper(wr, chip, false));
        bar.appendChild(chip);
    });

    if (wrappers.length > 1) {
        const allBtn = document.createElement('button');
        allBtn.type = 'button';
        allBtn.className = 'msg-quick-dl-all';
        allBtn.title = t('download_all_files');
        allBtn.innerHTML = `<i class="ph ph-download-simple"></i> <span>${escapeHtml(t('download_all_files'))} (${wrappers.length})</span>`;
        allBtn.addEventListener('click', () => {
            const downloaded = [];
            wrappers.forEach((wr, idx) => {
                setTimeout(() => {
                    const nm = downloadCodeFromWrapper(wr, idx === 0 ? allBtn : null, true);
                    if (nm) downloaded.push(nm);
                    if (idx === wrappers.length - 1 && downloaded.length && typeof showToast === 'function') {
                        showToast(
                            currentLang === 'en'
                                ? `Downloaded ${downloaded.length} files`
                                : `${downloaded.length} berkas berhasil diunduh`
                        );
                    }
                }, idx * 180);
            });
        });
        bar.appendChild(allBtn);
    }

    if (!existingBar) {
        const anchor = container.querySelector('.ag-artifacts-wrap') || container.querySelector('.msg-actions-bar');
        if (anchor) container.insertBefore(bar, anchor);
        else container.appendChild(bar);
    }
    updateQuickFilesBadge();
}

function copyCodeSnippet(btn) {
    const wrapper = btn.closest('.code-block-wrapper');
    if (!wrapper) return;
    const codeEl = wrapper.querySelector('code');
    if (!codeEl) return;
    const text = codeEl.innerText || codeEl.textContent;
    navigator.clipboard.writeText(text).then(() => {
        const span = btn.querySelector('span');
        const icon = btn.querySelector('i');
        const oldText = span ? span.textContent : '';
        if (span) span.textContent = t('copied_code') || 'Tersalin';
        if (icon) icon.className = 'ph ph-check';
        btn.classList.add('copy-success');
        setTimeout(() => {
            if (span) span.textContent = oldText || t('copy_code') || 'Salin';
            if (icon) icon.className = 'ph ph-copy';
            btn.classList.remove('copy-success');
        }, 2000);
    });
}

function copyMessageText(btn) {
    const bubble = btn.closest('.message').querySelector('.bubble');
    if (!bubble) return;
    const orig = bubble.getAttribute('data-original-text') || bubble.innerText;
    navigator.clipboard.writeText(orig).then(() => {
        const oldHTML = btn.innerHTML;
        btn.innerHTML = '<i class="ph ph-check"></i>';
        setTimeout(() => { btn.innerHTML = oldHTML; }, 1500);
    });
}

function toggleMermaidCode(btn) {
    const container = btn.closest('.mermaid-container');
    if (!container) return;
    const rawCode = container.querySelector('.mermaid-raw-code');
    if (!rawCode) return;
    rawCode.classList.toggle('hidden');
    const isHidden = rawCode.classList.contains('hidden');
    btn.innerHTML = isHidden ? '<i class="ph ph-code"></i> Lihat kode' : '<i class="ph ph-eye-slash"></i> Sembunyikan kode';
}

function toggleStatusCard(header) {
    const card = header.closest('.agent-status-card');
    if (!card) return;
    const body = card.querySelector('.status-card-body');
    const caret = card.querySelector('.status-card-caret');
    if (body) {
        body.classList.toggle('hidden');
        if (caret) {
            caret.className = body.classList.contains('hidden') ? 'ph ph-caret-down status-card-caret' : 'ph ph-caret-up status-card-caret';
        }
    }
}

function editUserPrompt(btn) {
    const bubble = btn.closest('.message').querySelector('.bubble');
    if (!bubble) return;
    const orig = bubble.getAttribute('data-original-text') || bubble.innerText;
    userInput.value = orig;
    adjustInputHeight();
    userInput.focus();
    const inputCard = document.querySelector('.input-card');
    if (inputCard) {
        inputCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function regenerateLastResponse() {
    if (isActiveSessionGenerating()) return;
    const userMessages = document.querySelectorAll('.message.user .bubble');
    if (userMessages.length === 0) return;
    const lastUserBubble = userMessages[userMessages.length - 1];
    const lastPrompt = lastUserBubble.getAttribute('data-original-text') || lastUserBubble.innerText;
    if (lastPrompt) {
        userInput.value = lastPrompt;
        sendMessage();
    }
}

let lastFailedPayload = null;
function retryLastFailedMessage() {
    if (lastFailedPayload && lastFailedPayload.message) {
        userInput.value = lastFailedPayload.message;
        sendMessage();
    }
}

function addErrorMessage(errorMsg, failedPayload = null) {
    lastFailedPayload = failedPayload;
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message system';
    messageDiv.innerHTML = `
        <div class="error-retry-card">
            <div class="error-retry-card-msg">
                <i class="ph ph-warning-circle"></i>
                <span>${errorMsg}</span>
            </div>
            <button type="button" class="btn-retry-action" onclick="retryLastFailedMessage()">
                <i class="ph ph-arrows-clockwise"></i> Coba lagi
            </button>
        </div>
    `;
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

const CODE_EXTENSIONS_SET = new Set([
    'py', 'pyw', 'pyi', 'ipynb', 'js', 'jsx', 'mjs', 'cjs', 'ts', 'tsx', 'vue', 'svelte', 'astro',
    'html', 'htm', 'css', 'scss', 'sass', 'less', 'java', 'c', 'cpp', 'cc', 'cxx', 'h', 'hpp', 'hh',
    'cs', 'go', 'rs', 'php', 'rb', 'swift', 'kt', 'kts', 'scala', 'dart', 'lua', 'pl', 'pm', 'r', 'jl',
    'zig', 'nim', 'sh', 'bash', 'zsh', 'fish', 'ps1', 'psm1', 'bat', 'cmd', 'awk', 'sed', 'dockerfile',
    'sql', 'prisma', 'graphql', 'gql', 'json', 'jsonl', 'json5', 'yaml', 'yml', 'toml', 'xml',
    'ini', 'cfg', 'conf', 'config', 'properties', 'env', 'proto', 'makefile', 'cmake'
]);

function toggleAgThought(btn) {
    const block = btn ? btn.closest('.ag-thought-block') : null;
    if (!block) return;
    block.dataset.userToggled = 'true';
    block.classList.toggle('is-open');
}

function buildAgentStepsHTML(steps) {
    if (!Array.isArray(steps) || !steps.length) return '';
    return steps.map(st => {
        const statusVal = st.status || 'done';
        let iconHTML = '<i class="ph ph-check-circle"></i>';
        if (statusVal === 'running') iconHTML = '<span class="ag-spinner-ring" aria-hidden="true"></span>';
        else if (statusVal === 'failed') iconHTML = '<i class="ph ph-x-circle"></i>';
        const titleStr = escapeHtml(st.title || '');
        const fbStr = st.feedback ? `<div class="ag-trace-step-feedback">${escapeHtml(st.feedback)}</div>` : '';
        return `
            <div class="ag-trace-step status-${escapeHtml(statusVal)}">
                <span class="ag-trace-step-icon">${iconHTML}</span>
                <div class="ag-trace-step-content">
                    <div class="ag-trace-step-title">${titleStr}</div>
                    ${fbStr}
                </div>
            </div>
        `;
    }).join('');
}

function renderAgentThoughtHTML(meta) {
    if (!meta) return '';
    const steps = Array.isArray(meta.agent_steps) ? meta.agent_steps : [];
    const thoughtText = (meta.thought_content || '').trim();
    const isRunning = Boolean(meta.is_running);
    if (!steps.length && !thoughtText) return '';

    const isOpen = isRunning || Boolean(meta.force_open);
    const dur = meta.thought_duration_sec;
    let titleLabel = 'Analyzing request...';
    if (!isRunning) {
        if (dur !== null && dur !== undefined) {
            titleLabel = `Thought for ${dur}s${steps.length ? ` · ${steps.length} steps` : ''}`;
        } else if (steps.length) {
            titleLabel = `Agent analysis · ${steps.length} step${steps.length > 1 ? 's' : ''}`;
        } else {
            titleLabel = 'Agent analysis';
        }
    } else if (steps.length) {
        const runningStep = steps.find(s => s.status === 'running') || steps[steps.length - 1];
        if (runningStep && runningStep.title) {
            titleLabel = runningStep.title + '...';
        }
    }

    const iconHtml = isRunning
        ? '<span class="ag-spinner-ring" aria-hidden="true"></span>'
        : '<i class="ph ph-sparkle"></i>';

    const reasoningHTML = thoughtText ? `
        <div class="ag-thought-reasoning">
            <div class="ag-thought-reasoning-label">AGENT ANALYSIS · EN</div>
            <div class="ag-thought-reasoning-text">${escapeHtml(thoughtText)}</div>
        </div>
    ` : '';

    return `
        <div class="ag-thought-block ${isOpen ? 'is-open' : ''} ${isRunning ? 'is-running' : 'is-done'}">
            <button type="button" class="ag-thought-toggle" onclick="toggleAgThought(this)">
                <span class="ag-thought-rule"></span>
                <span class="ag-thought-pill">
                    ${iconHtml}
                    <span class="ag-thought-title">${escapeHtml(titleLabel)}</span>
                    <i class="ph ph-caret-down ag-thought-caret"></i>
                </span>
                <span class="ag-thought-rule"></span>
            </button>
            <div class="ag-thought-body">
                <div class="ag-trace-steps">${buildAgentStepsHTML(steps)}</div>
                ${reasoningHTML}
            </div>
        </div>
    `;
}

function syncAgThoughtInMsg(msgEl, meta) {
    if (!msgEl || !meta) return;
    const container = msgEl.querySelector('.bubble-container');
    if (!container) return;
    const existing = container.querySelector('.ag-thought-block');
    const prevUserToggled = existing ? existing.dataset.userToggled === 'true' : false;
    const prevWasOpen = existing ? existing.classList.contains('is-open') : false;

    const wrapper = document.createElement('div');
    wrapper.innerHTML = renderAgentThoughtHTML(meta);
    const nextBlock = wrapper.firstElementChild;
    if (!nextBlock) {
        if (existing) existing.remove();
        return;
    }

    if (prevUserToggled) {
        nextBlock.dataset.userToggled = 'true';
        if (prevWasOpen) nextBlock.classList.add('is-open');
        else nextBlock.classList.remove('is-open');
    }

    const rBox = nextBlock.querySelector('.ag-thought-reasoning-text');
    if (existing) {
        existing.replaceWith(nextBlock);
    } else {
        const bubble = container.querySelector('.bubble');
        if (bubble) container.insertBefore(nextBlock, bubble);
        else container.prepend(nextBlock);
    }
    if (rBox) rBox.scrollTop = rBox.scrollHeight;
}

function renderArtifactsHTML(artifacts) {
    if (!Array.isArray(artifacts) || !artifacts.length) return '';
    const cards = artifacts.map(art => {
        if (!art || !art.filename || !art.download_url) return '';
        const isArch = art.kind === 'archive';
        const isVideo = art.kind === 'video';
        const iconCls = isArch ? 'ph-file-zip' : (isVideo ? 'ph-film-strip' : 'ph-file-code');
        const fmtBadge = (art.format || 'file').toUpperCase();
        const countStr = isArch && art.file_count ? ` · ${art.file_count} berkas` : (isVideo && art.duration_sec ? ` · ${art.duration_sec}s · ${art.resolution || ''}` : '');
        const metaLine = `${fmtBadge} · ${art.size_label || ''}${countStr}`;
        const safeName = escapeHtml(art.filename);
        const safeUrl = escapeHtml(art.download_url);
        const videoPlayerHTML = isVideo ? `
            <video class="ag-artifact-video-player" controls playsinline preload="metadata" src="${escapeHtml(art.video_url || (art.download_url + '?inline=1'))}"></video>
        ` : '';

        let subFilesHTML = '';
        if (isArch && Array.isArray(art.individual_files) && art.individual_files.length) {
            const links = art.individual_files.map(sf => `
                <a class="ag-artifact-subfile-link" href="${escapeHtml(sf.download_url)}" download="${escapeHtml(sf.filename)}" title="Unduh ${escapeHtml(sf.rel_path || sf.filename)}">
                    <i class="ph ph-download-simple"></i>
                    <span>${escapeHtml(sf.rel_path || sf.filename)}</span>
                </a>
            `).join('');
            subFilesHTML = `
                <details class="ag-artifact-files-details">
                    <summary>Lihat &amp; unduh berkas di dalam (${art.individual_files.length})</summary>
                    <div class="ag-artifact-files-list">${links}</div>
                </details>
            `;
        }
        const noteHTML = art.note ? `<div class="ag-artifact-note"><i class="ph ph-info"></i> ${escapeHtml(art.note)}</div>` : '';

        return `
            <div class="ag-artifact-card">
                ${videoPlayerHTML}
                <div class="ag-artifact-main">
                    <div class="ag-artifact-info">
                        <span class="ag-artifact-icon"><i class="ph ${iconCls}"></i></span>
                        <div class="ag-artifact-meta">
                            <div class="ag-artifact-name">${safeName}</div>
                            <div class="ag-artifact-sub">${escapeHtml(metaLine)}</div>
                        </div>
                    </div>
                    <a class="ag-artifact-dl-btn" href="${safeUrl}" download="${safeName}">
                        <i class="ph ph-download-simple"></i>
                        <span>Unduh ${safeName}</span>
                    </a>
                </div>
                ${subFilesHTML}
                ${noteHTML}
            </div>
        `;
    }).filter(Boolean).join('');

    return cards ? `<div class="ag-artifacts-wrap">${cards}</div>` : '';
}

function syncArtifactsInMsg(msgEl, artifacts) {
    if (!msgEl || !Array.isArray(artifacts) || !artifacts.length) return;
    const container = msgEl.querySelector('.bubble-container');
    if (!container) return;
    const oldWrap = container.querySelector('.ag-artifacts-wrap');
    const holder = document.createElement('div');
    holder.innerHTML = renderArtifactsHTML(artifacts);
    const nextWrap = holder.firstElementChild;
    if (!nextWrap) return;
    if (oldWrap) {
        oldWrap.replaceWith(nextWrap);
    } else {
        const actionsBar = container.querySelector('.msg-actions-bar');
        if (actionsBar) container.insertBefore(nextWrap, actionsBar);
        else container.appendChild(nextWrap);
    }
}

function renderWebSourcesHTML(agentActionData) {
    if (!agentActionData || typeof agentActionData !== 'object') return '';
    const details = (agentActionData.details && typeof agentActionData.details === 'object') ? agentActionData.details : {};
    const rawSources = Array.isArray(agentActionData.sources) && agentActionData.sources.length
        ? agentActionData.sources
        : (Array.isArray(details.sources) ? details.sources : []);
    const rawImages = Array.isArray(agentActionData.web_images) && agentActionData.web_images.length
        ? agentActionData.web_images
        : (Array.isArray(details.images) ? details.images : []);

    const sources = rawSources.filter(s => s && s.url && /^https?:\/\//i.test(s.url));
    const webImages = rawImages.filter(im => im && im.url && /^https?:\/\//i.test(im.url));
    if (!sources.length && !webImages.length) return '';

    const chipsHTML = sources.slice(0, 6).map(s => {
        const label = escapeHtml(s.title || s.domain || s.url);
        const safeUrl = escapeHtml(s.url);
        return `
            <a class="ag-source-chip" href="${safeUrl}" target="_blank" rel="noopener noreferrer" title="${safeUrl}">
                <i class="ph ph-link"></i>
                <span>${label}</span>
            </a>
        `;
    }).join('');

    const imgsHTML = webImages.slice(0, 4).map((im, idx) => {
        const safeUrl = escapeHtml(im.url);
        const safeTitle = escapeHtml(im.title || `Gambar Web #${idx + 1}`);
        const jsUrl = String(im.url).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        const jsTitle = String(im.title || `Gambar Web #${idx + 1}`).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        return `
            <div class="ag-web-img-card" onclick="openImageLightbox('${jsUrl}', '${jsTitle}')" title="${safeTitle}">
                <img src="${safeUrl}" alt="${safeTitle}" loading="lazy">
            </div>
        `;
    }).join('');

    return `
        <div class="ag-sources-wrap">
            ${sources.length ? `<div class="ag-sources-title"><i class="ph ph-globe"></i> <span>${escapeHtml(t('sources_browser'))} (${sources.length})</span></div><div class="ag-sources-chips">${chipsHTML}</div>` : ''}
            ${webImages.length ? `<div class="ag-web-images-row">${imgsHTML}</div>` : ''}
        </div>
    `;
}

function syncWebSourcesInMsg(msgEl, agentActionData) {
    if (!msgEl || !agentActionData) return;
    const container = msgEl.querySelector('.bubble-container');
    if (!container) return;
    const oldWrap = container.querySelector('.ag-sources-wrap');
    const holder = document.createElement('div');
    holder.innerHTML = renderWebSourcesHTML(agentActionData);
    const nextWrap = holder.firstElementChild;
    if (!nextWrap) return;
    if (oldWrap) {
        oldWrap.replaceWith(nextWrap);
    } else {
        const anchor = container.querySelector('.ag-artifacts-wrap') || container.querySelector('.msg-actions-bar');
        if (anchor) container.insertBefore(nextWrap, anchor);
        else container.appendChild(nextWrap);
    }
}

// Add message ke chat
function addMessage(role, content, imageUrl = null, docName = null, docUrl = null, docType = null, docText = null, agentActionData = null, msgId = null, isPinned = false, meta = null) {
    const hasText = content !== null && content !== undefined && String(content).trim().length > 0;
    const hasMultiAttach = Boolean(meta && ((meta.documents && meta.documents.length) || (meta.images && meta.images.length) || (meta.videos && meta.videos.length)));
    const hasMeta = Boolean(hasMultiAttach || (meta && ((meta.agent_steps && meta.agent_steps.length) || meta.thought_content || (meta.artifacts && meta.artifacts.length) || meta.is_running)));
    if (!hasText && !imageUrl && !docName && !docText && !agentActionData && !hasMeta) {
        // Jangan pernah merender pesan hantu atau bubble kosong tanpa konten
        return null;
    }

    const resolvedId = msgId || `msg-local-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
    const pinnedState = Boolean(isPinned);

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}${pinnedState ? ' is-pinned' : ''}`;
    messageDiv.dataset.msgId = resolvedId;
    messageDiv.dataset.role = role;
    messageDiv.dataset.pinned = pinnedState ? 'true' : 'false';
    
    let avatarHTML = '';
    if (role === 'assistant') {
        avatarHTML = `<div class="avatar shiro-avatar">${renderAvatarContent(aiProfile, 'S')}</div>`;
    } else if (role === 'user') {
        avatarHTML = `<div class="avatar user-avatar">${renderAvatarContent(userProfile, 'U')}</div>`;
    }

    const formattedContent = parseMessageContent(content);

    const escapedContent = (content || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    
    let attachmentHTML = '';
    const renderDocCardItem = (dName, dUrl, dType) => {
        const ext = (dName.split('.').pop() || '').toLowerCase();
        let iconClass = 'ph-file-text';
        let badgeColor = 'badge-txt';
        let typeLabel = (dType || ext).toUpperCase() || 'DOC';
        if (ext === 'pdf') { iconClass = 'ph-file-pdf'; badgeColor = 'badge-pdf'; typeLabel = 'PDF'; }
        else if (['doc', 'docx'].includes(ext)) { iconClass = 'ph-file-doc'; badgeColor = 'badge-doc'; typeLabel = 'WORD'; }
        else if (['csv', 'tsv'].includes(ext)) { iconClass = 'ph-file-csv'; badgeColor = 'badge-csv'; typeLabel = 'CSV'; }
        else if (CODE_EXTENSIONS_SET.has(ext) || CODE_EXTENSIONS_SET.has((dType || '').toLowerCase())) {
            iconClass = 'ph-file-code'; badgeColor = 'badge-code'; typeLabel = (ext || dType || 'CODE').toUpperCase();
        }
        const safeFilename = (dName || 'document').replace(/"/g, '&quot;');
        const safeDocUrl = dUrl || `/api/files/${encodeURIComponent(dName)}`;
        const jsFilename = (dName || 'document').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        const jsUrl = safeDocUrl.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        const jsType = ext.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        return `
            <div class="chat-doc-card ${badgeColor}" onclick="openDocModal('${jsFilename}', '${jsUrl}', '${jsType}')" title="Klik untuk membuka ${safeFilename}">
                <div class="chat-doc-icon">
                    <i class="ph ${iconClass}"></i>
                    <span class="chat-doc-type">${typeLabel}</span>
                </div>
                <div class="chat-doc-info">
                    <div class="chat-doc-name" title="${safeFilename}">${safeFilename}</div>
                    <div class="chat-doc-meta">
                        <span class="chat-doc-action"><i class="ph ph-eye"></i> <span data-i18n="view_doc_action">${t('view_doc_action')}</span></span>
                    </div>
                </div>
                <button type="button" class="chat-doc-open-btn" onclick="event.stopPropagation(); window.open('${jsUrl}', '_blank')" title="Buka di Tab Baru">
                    <i class="ph ph-arrow-square-out"></i>
                </button>
            </div>
        `;
    };

    const metaDocs = (meta && Array.isArray(meta.documents) && meta.documents.length) ? meta.documents : null;
    if (metaDocs) {
        metaDocs.forEach(dItem => {
            if (dItem && dItem.filename) {
                attachmentHTML += renderDocCardItem(dItem.filename, dItem.url || `/api/files/${encodeURIComponent(dItem.filename)}`, dItem.file_type || '');
            }
        });
    } else if (docName) {
        attachmentHTML += renderDocCardItem(docName, docUrl, docType);
    }

    const metaVideos = (meta && Array.isArray(meta.videos) && meta.videos.length) ? meta.videos : null;
    if (metaVideos) {
        metaVideos.forEach(vItem => {
            if (!vItem || !vItem.filename) return;
            const vUrl = vItem.blobUrl || vItem.url || '';
            const metaTxt = `${vItem.filename}${vItem.duration_sec ? ` · ${Number(vItem.duration_sec).toFixed(1)}s` : ''}${vItem.resolution ? ` · ${vItem.resolution}` : ''}`;
            const jsVidUrl = String(vUrl).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            const jsVidName = String(vItem.filename).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            attachmentHTML += `
                <div class="chat-video-wrap">
                    ${vUrl ? `<video class="chat-video-player" controls playsinline preload="metadata" src="${escapeHtml(vUrl)}"></video>` : ''}
                    <div class="chat-video-caption ${vUrl ? 'is-clickable' : ''}" ${vUrl ? `onclick="openVideoLightbox('${jsVidUrl}', '${jsVidName}')" title="${escapeHtml(t('click_to_play_video'))}"` : ''}><i class="ph-fill ph-play-circle"></i> <span>${escapeHtml(metaTxt)}</span></div>
                </div>
            `;
        });
    }

    const metaImages = (meta && Array.isArray(meta.images) && meta.images.length) ? meta.images : null;
    if (metaImages && metaImages.length > 1) {
        attachmentHTML += `<div class="chat-multi-img-grid">${metaImages.map((u, idx) => {
            const jsImgUrl = String(u).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            return `<div class="chat-img-wrapper" onclick="openImageLightbox('${jsImgUrl}', 'Gambar #${idx + 1}')" title="Klik untuk membuka gambar"><img src="${escapeHtml(u)}" class="chat-img-attachment" alt="Foto #${idx + 1}" loading="lazy"></div>`;
        }).join('')}</div>`;
    } else if (imageUrl) {
        const jsImgUrl = imageUrl.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        attachmentHTML += `
            <div class="chat-img-wrapper" onclick="openImageLightbox('${jsImgUrl}', 'Foto Lampiran Chat')" title="Klik untuk membuka gambar">
                <img src="${imageUrl}" class="chat-img-attachment" alt="Foto Visual" loading="lazy">
            </div>
        `;
    }

    let statusCardHTML = '';
    if (role === 'assistant' && agentActionData && agentActionData.tool) {
        const tool = agentActionData.tool;
        const isSuccess = agentActionData.status === 'success';
        const dur = agentActionData.execution_time_sec ? `${agentActionData.execution_time_sec}s` : '';
        let toolIcon = 'ph-gear-six';
        let toolTitle = 'Eksekusi Tool';
        
        if (tool === 'weather_sat_check') {
            toolIcon = 'ph-cloud-sun';
            toolTitle = 'Satelit Cuaca';
        } else if (tool === 'google_web_search') {
            toolIcon = 'ph-magnifying-glass';
            toolTitle = 'Google Search';
        } else if (tool === 'web_browser_reader') {
            toolIcon = 'ph-globe';
            toolTitle = 'Web Browser Reader';
        } else if (tool === 'web_screenshot') {
            toolIcon = 'ph-camera';
            toolTitle = 'Tangkapan Layar Web';
        } else if (tool === 'powershell_terminal') {
            toolIcon = 'ph-terminal';
            toolTitle = 'PowerShell Terminal PC';
        } else if (tool === 'safe_calculator') {
            toolIcon = 'ph-calculator';
            toolTitle = 'Kalkulator Presisi';
        } else if (tool === 'realtime_clock') {
            toolIcon = 'ph-clock';
            toolTitle = 'Jam Dunia';
        } else if (tool === 'archive_packager') {
            toolIcon = 'ph-file-zip';
            toolTitle = 'Agent Archive Packager';
        } else if (tool === 'video_renderer') {
            toolIcon = 'ph-film-strip';
            toolTitle = 'Agent Video Renderer';
        } else if (tool === 'local_autonomous_agent') {
            toolIcon = 'ph-terminal-window';
            toolTitle = 'Antigravity Local Agent';
        }
        
        const obsText = agentActionData.observation || JSON.stringify(agentActionData.details || {}, null, 2);
        const escapedObs = (obsText || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const descText = (agentActionData.description || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        
        statusCardHTML = `
            <div class="agent-status-card ${isSuccess ? 'status-success' : 'status-error'}">
                <div class="status-card-header" onclick="toggleStatusCard(this)" title="Klik untuk melihat detail eksekusi">
                    <div class="status-card-title-group">
                        <span class="status-card-icon"><i class="ph ${toolIcon}"></i></span>
                        <span class="status-card-title">${toolTitle}: ${descText}</span>
                    </div>
                    <div class="status-card-end">
                        <span class="status-card-badge ${isSuccess ? 'status-badge-success' : 'status-badge-error'}">
                            <i class="ph ${isSuccess ? 'ph-check-circle' : 'ph-x-circle'}"></i> ${isSuccess ? 'Berhasil' : 'Gagal'}${dur ? ' · ' + dur : ''}
                        </span>
                        <i class="ph ph-caret-down status-card-caret"></i>
                    </div>
                </div>
                <div class="status-card-body hidden">
                    <pre class="status-code-pre"><code>${escapedObs}</code></pre>
                </div>
            </div>
        `;
    }

    const pinBtnHTML = `
        <button type="button" class="btn-msg-action pin-btn ${pinnedState ? 'pinned' : ''}" onclick="togglePinMessage(this)" title="${pinnedState ? t('unpin_msg') : t('pin_msg')}" aria-label="PIN">
            <i class="ph ${pinnedState ? 'ph-push-pin-slash' : 'ph-push-pin'}"></i>
        </button>
    `;

    let actionsBarHTML = '';
    if (role === 'user') {
        actionsBarHTML = `
            <div class="msg-actions-bar">
                ${pinBtnHTML}
                <button type="button" class="btn-msg-action" onclick="editUserPrompt(this)" title="${t('edit_msg')}" data-i18n-title="edit_msg" aria-label="Edit pesan">
                    <i class="ph ph-pencil-simple"></i>
                </button>
                <button type="button" class="btn-msg-action" onclick="copyMessageText(this)" title="${t('copy_msg')}" data-i18n-title="copy_msg" aria-label="Salin pesan">
                    <i class="ph ph-copy"></i>
                </button>
            </div>
        `;
    } else if (role === 'assistant') {
        actionsBarHTML = `
            <div class="msg-actions-bar">
                ${pinBtnHTML}
                <button type="button" class="btn-msg-action" onclick="copyMessageText(this)" title="${t('copy_reply')}" data-i18n-title="copy_reply" aria-label="Salin jawaban">
                    <i class="ph ph-copy"></i>
                </button>
                <button type="button" class="btn-msg-action" onclick="regenerateLastResponse()" title="${t('regen_reply')}" data-i18n-title="regen_reply" aria-label="Buat ulang jawaban">
                    <i class="ph ph-arrows-clockwise"></i>
                </button>
            </div>
        `;
    }

    let agThoughtHTML = '';
    let sourcesHTML = '';
    let artifactsHTML = '';
    if (role === 'assistant') {
        if (meta) {
            agThoughtHTML = renderAgentThoughtHTML(meta);
            artifactsHTML = renderArtifactsHTML(meta.artifacts);
        }
        const actionObj = agentActionData || (meta && meta.agent_action) || null;
        if (actionObj) {
            sourcesHTML = renderWebSourcesHTML(actionObj);
        }
    }

    let innerBubbleHTML = '';
    innerBubbleHTML += `<div class="msg-pin-indicator ${pinnedState ? '' : 'hidden'}"><i class="ph-fill ph-push-pin"></i> <span data-i18n="pinned_badge">${t('pinned_badge')}</span></div>`;
    if (attachmentHTML) {
        innerBubbleHTML += `<div class="msg-attachment-wrap">${attachmentHTML}</div>`;
    }
    innerBubbleHTML += `<div class="msg-text">${formattedContent || ''}</div>`;

    messageDiv.innerHTML = `
        ${role === 'assistant' ? avatarHTML : ''}
        <div class="bubble-container">
            ${statusCardHTML}
            ${agThoughtHTML}
            <div class="bubble${!hasText && !attachmentHTML ? ' hidden' : ''}" data-original-text="${escapedContent}">${innerBubbleHTML}</div>
            ${sourcesHTML}
            ${artifactsHTML}
            ${actionsBarHTML}
        </div>
        ${role === 'user' ? avatarHTML : ''}
    `;
    
    chatMessages.appendChild(messageDiv);
    if (role === 'user') {
        scrollToBottom(true, true);
    } else {
        scrollToBottom(false, false);
    }

    if (typeof hljs !== 'undefined') {
        messageDiv.querySelectorAll('pre code[class*="language-"]').forEach(block => {
            try {
                hljs.highlightElement(block);
            } catch (e) {
                console.warn('[Highlight Warning]:', e);
            }
        });
    }

    if (typeof mermaid !== 'undefined') {
        messageDiv.querySelectorAll('.mermaid-container').forEach(async (container) => {
            const rawSource = container.querySelector('.mermaid-raw-source');
            const renderTarget = container.querySelector('.mermaid-diagram-render');
            if (rawSource && renderTarget) {
                const code = rawSource.textContent.trim();
                const renderId = `diag_${Date.now()}_${Math.floor(Math.random()*10000)}`;
                try {
                    const { svg } = await mermaid.render(renderId, code);
                    renderTarget.innerHTML = svg;
                } catch (mErr) {
                    console.warn('[Mermaid Render Error]:', mErr);
                    renderTarget.innerHTML = `<div class="mermaid-error"><i class="ph ph-warning"></i> Diagram tidak valid. Pilih "Lihat kode" untuk melihat sintaks aslinya.</div>`;
                }
            }
        });
    }

    if (role === 'assistant') {
        syncQuickCodeDownloadsInMsg(messageDiv);
    }
    updateQuickFilesBadge();

    return messageDiv;
}

// --- Sistem PIN Chat & Pinned Messages Drawer ---
async function togglePinMessage(btn) {
    const msgEl = btn.closest('.message');
    if (!msgEl) return;

    const msgId = msgEl.dataset.msgId || '';
    const bubble = msgEl.querySelector('.bubble');
    const rawContent = bubble ? decodeHtmlEntities(bubble.getAttribute('data-original-text') || '') : '';
    const currentlyPinned = msgEl.dataset.pinned === 'true';
    const nextPinned = !currentlyPinned;

    // Optimistic UI update
    applyPinStateToElement(msgEl, nextPinned);
    renderPinnedDrawer();

    try {
        const res = await fetch('/api/chat/pin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message_id: msgId,
                pinned: nextPinned,
                content: rawContent
            })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            if (data.message && data.message.id) {
                msgEl.dataset.msgId = data.message.id;
            }
            applyPinStateToElement(msgEl, data.pinned);
            renderPinnedDrawer();
            showToast(data.pinned ? t('msg_pinned_toast') : t('msg_unpinned_toast'));
        }
    } catch (e) {
        console.error('Error toggling pin:', e);
    }
}

function applyPinStateToElement(msgEl, isPinned) {
    if (!msgEl) return;
    const pinned = Boolean(isPinned);
    msgEl.dataset.pinned = pinned ? 'true' : 'false';
    msgEl.classList.toggle('is-pinned', pinned);

    const indicator = msgEl.querySelector('.msg-pin-indicator');
    if (indicator) {
        indicator.classList.toggle('hidden', !pinned);
    }

    const pinBtn = msgEl.querySelector('.pin-btn');
    if (pinBtn) {
        pinBtn.classList.toggle('pinned', pinned);
        pinBtn.title = pinned ? t('unpin_msg') : t('pin_msg');
        pinBtn.innerHTML = `<i class="ph ${pinned ? 'ph-push-pin-slash' : 'ph-push-pin'}"></i>`;
    }
}

function renderPinnedDrawer() {
    const badge = document.getElementById('pinned-count-badge');
    const navBtn = document.getElementById('pinned-messages-btn');
    const listEl = document.getElementById('pinned-drawer-list');
    if (!chatMessages) return;

    const pinnedEls = Array.from(chatMessages.querySelectorAll('.message.is-pinned'));
    const count = pinnedEls.length;

    if (badge) {
        badge.textContent = String(count);
        badge.classList.toggle('hidden', count === 0);
    }
    if (navBtn) {
        navBtn.classList.toggle('has-pins', count > 0);
    }

    if (!listEl) return;
    listEl.innerHTML = '';

    if (count === 0) {
        const emptyDiv = document.createElement('div');
        emptyDiv.className = 'session-empty';
        emptyDiv.style.padding = '8px 4px';
        emptyDiv.textContent = t('pinned_empty');
        listEl.appendChild(emptyDiv);
        return;
    }

    pinnedEls.forEach(msgEl => {
        const msgId = msgEl.dataset.msgId;
        const role = msgEl.dataset.role === 'user' ? t('tab_user') : 'Shiro';
        const bubble = msgEl.querySelector('.bubble');
        const rawText = bubble ? decodeHtmlEntities(bubble.getAttribute('data-original-text') || '') : '';
        const cleanSnippet = rawText.replace(/\s+/g, ' ').trim() || '[Media / Lampiran]';

        const item = document.createElement('div');
        item.className = 'pinned-drawer-item';
        item.onclick = () => scrollToPinnedMessage(msgId);

        const left = document.createElement('div');
        left.className = 'pinned-item-left';

        const roleTag = document.createElement('span');
        roleTag.className = 'pinned-role-tag';
        roleTag.textContent = role;

        const textSpan = document.createElement('span');
        textSpan.className = 'pinned-item-text';
        textSpan.textContent = cleanSnippet.slice(0, 120) + (cleanSnippet.length > 120 ? '...' : '');

        left.appendChild(roleTag);
        left.appendChild(textSpan);

        const unpinBtn = document.createElement('button');
        unpinBtn.type = 'button';
        unpinBtn.className = 'pinned-unpin-btn';
        unpinBtn.title = t('unpin_msg');
        unpinBtn.innerHTML = '<i class="ph ph-push-pin-slash"></i>';
        unpinBtn.onclick = (e) => {
            e.stopPropagation();
            const pinBtnInMsg = msgEl.querySelector('.pin-btn');
            if (pinBtnInMsg) {
                togglePinMessage(pinBtnInMsg);
            }
        };

        item.appendChild(left);
        item.appendChild(unpinBtn);
        listEl.appendChild(item);
    });
}

function togglePinnedDrawer(forceState = null) {
    const drawer = document.getElementById('pinned-drawer');
    if (!drawer) return;
    renderPinnedDrawer();
    if (typeof forceState === 'boolean') {
        drawer.classList.toggle('hidden', !forceState);
    } else {
        drawer.classList.toggle('hidden');
    }
}

function scrollToPinnedMessage(msgId) {
    if (!chatMessages) return;
    const target = chatMessages.querySelector(`.message[data-msg-id="${msgId}"]`);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.remove('pin-jump-highlight');
    void target.offsetWidth;
    target.classList.add('pin-jump-highlight');
    setTimeout(() => target.classList.remove('pin-jump-highlight'), 1500);
}

function updateMemoryCount() {
    fetch('/api/memory-count')
        .then(res => res.json())
        .then(data => {
            if (memoryCount) memoryCount.textContent = data.count;
            if (sidebarMemoryCount) sidebarMemoryCount.textContent = `${data.count} ${t('facts_unit')}`;
        })
        .catch(err => console.error("Memory fetch error", err));
}

function updateTypingIndicatorAvatar() {
    if (!typingIndicator) return;
    const avatarEl = typingIndicator.querySelector('.avatar');
    if (!avatarEl) return;
    avatarEl.innerHTML = renderAvatarContent(aiProfile, 'S');
}

function updateTypingStatus(statusText) {
    if (!typingIndicator || !statusText) return;
    const textEl = typingIndicator.querySelector('#typing-status-text') || typingIndicator.querySelector('.typing-status-text');
    if (textEl) {
        textEl.textContent = statusText;
    }
}

function showTyping(show, statusText = null) {
    if (!typingIndicator) return;
    if (show) {
        updateTypingIndicatorAvatar();
        updateTypingStatus(statusText || t('status_thinking') || 'Shiro sedang berpikir...');
        typingIndicator.classList.remove('hidden');
        if (chatMessages && typingIndicator.parentElement !== chatMessages) {
            chatMessages.appendChild(typingIndicator);
        } else if (chatMessages) {
            // Pastikan selalu berada di elemen paling bawah
            chatMessages.appendChild(typingIndicator);
        }
        scrollToBottom(true, true);
    } else {
        typingIndicator.classList.add('hidden');
    }
}

function hasComposerDraftContent() {
    const hasText = Boolean(userInput && userInput.value.trim());
    return Boolean(
        hasText
        || attachedImages.length
        || attachedDocuments.length
        || attachedVideos.length
        || inFlightUploadsCount > 0
    );
}

function updateComposerSendButton() {
    if (!sendBtn) return;
    if (isActiveSessionGenerating()) {
        sendBtn.disabled = false;
        sendBtn.classList.add('is-queue-mode');
        if (hasComposerDraftContent()) {
            sendBtn.classList.remove('hidden');
            sendBtn.title = currentLang === 'en'
                ? 'Queue message (sends after Shiro finishes)'
                : 'Antrekan pesan (dikirim otomatis setelah Shiro selesai)';
        } else {
            sendBtn.classList.add('hidden');
        }
    } else {
        sendBtn.disabled = false;
        sendBtn.classList.remove('hidden', 'is-queue-mode');
        sendBtn.title = t('send_msg_tooltip') || 'Kirim pesan (Enter)';
    }
}

function toggleQueuedMessagesPanel() {
    queuedPanelCollapsed = !queuedPanelCollapsed;
    renderQueuedMessagesPanel();
}

function renderQueuedMessagesPanel() {
    const panel = document.getElementById('queued-messages-panel');
    if (!panel) return;
    const queuedMessages = getSessionQueue(activeSessionId);
    if (!Array.isArray(queuedMessages) || queuedMessages.length === 0) {
        panel.classList.add('hidden');
        panel.innerHTML = '';
        return;
    }

    panel.classList.remove('hidden');
    panel.classList.toggle('is-collapsed', queuedPanelCollapsed);

    const subtitleTxt = t('queued_subtitle');

    const itemsHTML = queuedMessages.map((qItem, idx) => {
        const qImgs = Array.isArray(qItem.images) ? qItem.images : [];
        const qDocs = Array.isArray(qItem.documents) ? qItem.documents : [];
        const qVids = Array.isArray(qItem.videos) ? qItem.videos : [];

        let mediaHTML = '';
        if (qImgs.length || qDocs.length || qVids.length) {
            const thumbs = qImgs.slice(0, 2).map((im, ti) => (
                `<img class="queued-item-thumb" src="${escapeHtml(im.dataUrl)}" alt="img-${ti + 1}">`
            )).join('');
            const extraImg = qImgs.length > 2 ? `<span class="queued-item-badge">+${qImgs.length - 2}</span>` : '';
            const docBadge = qDocs.length ? `<span class="queued-item-badge" title="${qDocs.length} berkas"><i class="ph ph-file-text"></i></span>` : '';
            const vidBadge = qVids.length ? `<span class="queued-item-badge" title="${qVids.length} video"><i class="ph ph-film-strip"></i></span>` : '';
            mediaHTML = `<div class="queued-item-media">${thumbs}${extraImg}${docBadge}${vidBadge}</div>`;
        }

        const attachSummaryParts = [];
        if (qDocs.length) attachSummaryParts.push(`${qDocs.length} file`);
        if (qImgs.length) attachSummaryParts.push(`${qImgs.length} img`);
        if (qVids.length) attachSummaryParts.push(`${qVids.length} video`);
        const attachMeta = attachSummaryParts.length
            ? `<div class="queued-item-meta">${escapeHtml(attachSummaryParts.join(' · '))}</div>`
            : '';

        const textPreview = (qItem.message || '').trim()
            || (attachSummaryParts.length ? `[${attachSummaryParts.join(' + ')}]` : '(Pesan kosong)');

        return `
            <div class="queued-item" data-queue-idx="${idx}">
                ${mediaHTML}
                <div class="queued-item-body">
                    <div class="queued-item-text">${escapeHtml(textPreview)}</div>
                    ${attachMeta}
                </div>
                <div class="queued-item-actions">
                    <button type="button" class="queued-act-btn" onclick="promoteQueuedMessage(${idx})" title="${currentLang === 'en' ? 'Prioritize next' : 'Prioritaskan berikutnya'}">
                        <i class="ph ph-arrow-right"></i>
                    </button>
                    <button type="button" class="queued-act-btn" onclick="editQueuedMessage(${idx})" title="${currentLang === 'en' ? 'Edit in composer' : 'Ubah di kolom input'}">
                        <i class="ph ph-pencil-simple"></i>
                    </button>
                    <button type="button" class="queued-act-btn is-delete" onclick="removeQueuedMessage(${idx})" title="${currentLang === 'en' ? 'Remove from queue' : 'Hapus dari antrean'}">
                        <i class="ph ph-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');

    panel.innerHTML = `
        <div class="queued-panel-header" onclick="toggleQueuedMessagesPanel()">
            <div class="queued-header-left">
                <span class="queued-title" data-i18n="queued_title">${escapeHtml(t('queued_title'))}</span>
                <span class="queued-count-badge">${queuedMessages.length}</span>
                <span class="queued-subtitle">${escapeHtml(subtitleTxt)}</span>
            </div>
            <i class="ph ph-caret-down queued-header-caret"></i>
        </div>
        <div class="queued-panel-list">${itemsHTML}</div>
    `;
}

function promoteQueuedMessage(idx) {
    const queuedMessages = getSessionQueue(activeSessionId);
    if (idx < 0 || idx >= queuedMessages.length) return;
    if (!isActiveSessionGenerating()) {
        const [item] = queuedMessages.splice(idx, 1);
        renderQueuedMessagesPanel();
        sendMessage(item, activeSessionId);
        return;
    }
    if (idx > 0) {
        const [item] = queuedMessages.splice(idx, 1);
        queuedMessages.unshift(item);
        renderQueuedMessagesPanel();
    }
}

function editQueuedMessage(idx) {
    const queuedMessages = getSessionQueue(activeSessionId);
    if (idx < 0 || idx >= queuedMessages.length) return;
    const [item] = queuedMessages.splice(idx, 1);
    renderQueuedMessagesPanel();

    if (userInput) {
        userInput.value = item.message || '';
        adjustInputHeight();
        userInput.focus();
    }
    (item.images || []).forEach(im => setAttachedImage(im.dataUrl, im.name));
    (item.documents || []).forEach(doc => setAttachedDocument(doc));
    (item.videos || []).forEach(vid => setAttachedVideo(vid));
    updateComposerSendButton();
}

function removeQueuedMessage(idx) {
    const queuedMessages = getSessionQueue(activeSessionId);
    if (idx < 0 || idx >= queuedMessages.length) return;
    queuedMessages.splice(idx, 1);
    renderQueuedMessagesPanel();
}

async function enqueueCurrentComposer(targetSid = activeSessionId) {
    if (typeof activeUploadPromises !== 'undefined' && activeUploadPromises.length > 0) {
        if (status) {
            status.textContent = currentLang === 'en'
                ? 'Waiting for file upload to finish before queueing...'
                : 'Menunggu proses upload selesai lalu mengantrekan pesan...';
        }
        try {
            await Promise.allSettled([...activeUploadPromises]);
        } catch (_) {}
    }

    const msgText = userInput ? userInput.value.trim() : '';
    if (!msgText && !attachedImages.length && !attachedDocuments.length && !attachedVideos.length) {
        return;
    }

    const queuedMessages = getSessionQueue(targetSid || activeSessionId);
    queuedMessages.push({
        message: msgText,
        images: [...attachedImages],
        documents: [...attachedDocuments],
        videos: [...attachedVideos],
    });
    queuedPanelCollapsed = false;

    if (userInput) {
        userInput.value = '';
        adjustInputHeight();
    }
    clearAttachedImage();
    clearAttachedDocument();
    clearAttachedVideo();
    renderQueuedMessagesPanel();
    updateComposerSendButton();
    if (status) {
        status.textContent = currentLang === 'en'
            ? `Queued (${queuedMessages.length}) · Sends when Shiro finishes`
            : `Masuk antrean (${queuedMessages.length}) · Terkirim setelah Shiro selesai`;
    }
}

// Global input lock manager (tetap izinkan mengetik, upload file/gambar/video, & antrean selama AI bekerja)
function setInputLock(locked) {
    if (userInput) {
        userInput.disabled = false;
        userInput.removeAttribute('readonly');
        if (locked) {
            if (!userInput.dataset.prevPlaceholder) {
                userInput.dataset.prevPlaceholder = userInput.placeholder;
            }
            userInput.placeholder = currentLang === 'en'
                ? 'Write a follow-up or attach files to queue while Shiro responds...'
                : 'Ketik pesan lanjutan atau unggah berkas ke antrean selagi Shiro bekerja...';
        } else {
            userInput.placeholder = userInput.dataset.prevPlaceholder || t('input_placeholder') || 'Tulis pesan...';
        }
    }
    if (uploadDocBtn) uploadDocBtn.disabled = false;
    if (uploadImageBtn) uploadImageBtn.disabled = false;
    if (openCameraBtn) openCameraBtn.disabled = false;
    if (docFileInput) docFileInput.disabled = false;
    if (imageFileInput) imageFileInput.disabled = false;

    const lyraBtn = document.getElementById('lyra-tier-btn');
    if (lyraBtn) {
        lyraBtn.disabled = locked;
    }
    if (locked && typeof toggleLyraTierMenu === 'function') {
        toggleLyraTierMenu(false);
    }
    if (stopBtn) {
        if (locked) {
            stopBtn.classList.remove('hidden');
        } else {
            stopBtn.classList.add('hidden');
        }
    }

    const inputCard = document.querySelector('.input-card');
    if (inputCard) {
        if (locked) {
            inputCard.classList.add('is-loading');
        } else {
            inputCard.classList.remove('is-loading');
        }
    }
    const inputSection = document.querySelector('.input-section');
    if (inputSection) {
        if (locked) {
            inputSection.classList.add('is-generating');
        } else {
            inputSection.classList.remove('is-generating');
        }
    }
    updateComposerSendButton();
}

function startTriggerTimer() {
    clearTimeout(triggerTimer);
    const naturalDelay = Math.floor(Math.random() * (240000 - 150000 + 1)) + 150000;
    
    triggerTimer = setTimeout(() => {
        if (isAnySessionRunning() || (userInput && userInput.value.trim().length > 0)) return; 
        const triggerSessionId = activeSessionId;

        fetch('/api/trigger', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        })
        .then(res => res.json())
        .then(data => {
            if (activeSessionId === triggerSessionId && data.reply && data.status !== 'idle') {
                addMessage('assistant', data.reply, null, null, null, null, null, null, data.assistant_message_id || null, false); 
            }
        })
        .catch(err => console.error("Trigger fetch error:", err));
    }, naturalDelay);
}

// Send message main function (isolated per session so switching chats never interrupts or blocks background runs)
async function sendMessage(overridePayload = null, explicitSessionId = null) {
    if (overridePayload && ((typeof Event !== 'undefined' && overridePayload instanceof Event) || typeof overridePayload !== 'object' || ('isTrusted' in overridePayload && !('message' in overridePayload)))) {
        overridePayload = null;
    }
    if (typeof explicitSessionId !== 'string') {
        explicitSessionId = null;
    }
    const targetSessionId = explicitSessionId || activeSessionId || 'default';
    if (!overridePayload && isSessionRunning(targetSessionId)) {
        await enqueueCurrentComposer(targetSessionId);
        return;
    }

    const message = overridePayload
        ? String(overridePayload.message || '').trim()
        : (userInput ? userInput.value.trim() : '');
    const sendingImages = overridePayload
        ? [...(overridePayload.images || [])]
        : [...attachedImages];
    const sendingDocs = overridePayload
        ? [...(overridePayload.documents || [])]
        : [...attachedDocuments];
    const sendingVideos = overridePayload
        ? [...(overridePayload.videos || [])]
        : [...attachedVideos];

    if ((!message && !sendingImages.length && !sendingDocs.length && !sendingVideos.length) || isSessionRunning(targetSessionId)) return;

    clearTimeout(triggerTimer);
    unreadDoneSessions.delete(targetSessionId);

    const run = {
        sessionId: targetSessionId,
        sessionTitle: getSessionTitleById(targetSessionId),
        isRunning: true,
        aborted: false,
        abortController: new AbortController(),
        statusText: t('status_thinking'),
        serverStatusReceived: false,
        streamText: '',
        liveThoughtText: '',
        liveThoughtDuration: null,
        liveAgentSteps: [],
        liveArtifacts: [],
        activeAgentAction: null,
        activeAssistantImgUrl: null,
        userMsgEl: null,
        assistantMsgEl: null,
        assistantBubble: null,
        assistantTextEl: null,
        userMsgId: null,
        lastAgentTaskId: null,
        awaitingApproval: false,
        finalData: null,
        typingProgressInterval: null,
        hadError: false,
        errorText: ''
    };
    sessionRuns.set(targetSessionId, run);

    const isMounted = () => activeSessionId === targetSessionId;
    const syncRunTitle = (newTitle) => {
        if (!newTitle) return;
        run.sessionTitle = newTitle;
        const found = (currentSessionsData || []).find(s => s.id === targetSessionId);
        if (found) found.title = newTitle;
    };

    if (isMounted()) {
        isUserScrolledUp = false;
        if (scrollBottomBtn) {
            scrollBottomBtn.classList.add('hidden');
            scrollBottomBtn.classList.remove('is-streaming');
        }
        setInputLock(true);
    }
    updateSidebarRunningIndicators();

    const sendingImage = sendingImages[0] || null;
    const currentImgUrl = sendingImage ? sendingImage.dataUrl : null;
    const sendingDoc = sendingDocs[0] || null;

    if (!overridePayload && isMounted()) {
        if (userInput) {
            userInput.value = '';
            adjustInputHeight();
        }
        clearAttachedImage();
        clearAttachedDocument();
        clearAttachedVideo();
    }
    if (isMounted()) updateComposerSendButton();
    
    let displayMsg = message;
    if (!displayMsg) {
        const partsDesc = [];
        if (sendingVideos.length) partsDesc.push(`${sendingVideos.length} video (${sendingVideos.map(v => v.filename).join(', ')})`);
        if (sendingImages.length) partsDesc.push(`${sendingImages.length} gambar`);
        if (sendingDocs.length) partsDesc.push(`${sendingDocs.length} berkas (${sendingDocs.map(d => d.filename).slice(0, 4).join(', ')}${sendingDocs.length > 4 ? ', ...' : ''})`);
        displayMsg = `Kakak melampirkan ${partsDesc.join(' + ')}. Shiro, tolong pelajari semuanya ya!`;
    }
    
    if (isMounted()) {
        run.userMsgEl = addMessage(
            'user', 
            displayMsg, 
            currentImgUrl, 
            sendingDoc ? sendingDoc.filename : null,
            sendingDoc ? sendingDoc.url : null,
            sendingDoc ? sendingDoc.file_type : null,
            sendingDoc ? sendingDoc.text : null,
            null,
            null,
            false,
            {
                documents: sendingDocs,
                images: sendingImages.map(im => im.dataUrl),
                videos: sendingVideos,
            }
        );
        if (status) status.textContent = run.statusText;
        showTyping(true, run.statusText);
        if (pipelineNavDot) pipelineNavDot.classList.remove('hidden');
        startPipelineAnimation(displayMsg);
    }

    let elapsedSec = 0;
    run.typingProgressInterval = setInterval(() => {
        elapsedSec++;
        if (!run.isRunning) {
            clearInterval(run.typingProgressInterval);
            return;
        }
        if (run.serverStatusReceived) return;
        let nextMsg = null;
        if (elapsedSec === 4) {
            nextMsg = t('status_processing') || 'Shiro sedang menganalisis pesan...';
        } else if (elapsedSec === 8) {
            nextMsg = 'Shiro sedang menyusun jawaban...';
        } else if (elapsedSec === 15) {
            nextMsg = 'Sedang memproses instruksi mendalam...';
        }
        if (nextMsg) {
            run.statusText = nextMsg;
            if (isMounted()) {
                updateTypingStatus(nextMsg);
                if (status) status.textContent = nextMsg;
            }
        }
    }, 1000);

    try {
        const payload = { 
            message: message,
            session_id: targetSessionId,
            stream: true 
        };
        if (isLyraActive && activeLyraTier) {
            payload.lyra_tier = activeLyraTier;
        }
        if (sendingImages.length) {
            payload.image = sendingImages[0].dataUrl;
            payload.images = sendingImages.map(im => im.dataUrl);
        }
        if (sendingDocs.length) {
            payload.documents = sendingDocs.map(d => ({
                filename: d.filename,
                text: d.text,
                file_type: d.file_type,
                char_count: d.char_count,
                url: d.url
            }));
            payload.document_text = sendingDocs[0].text;
            payload.document_name = sendingDocs[0].filename;
        }
        if (sendingVideos.length) {
            payload.videos = sendingVideos.map(({ blobUrl, ...rest }) => rest);
        }

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream, application/json'
            },
            body: JSON.stringify(payload),
            signal: run.abortController.signal
        });

        if (!response.ok) {
            let errorMsg = 'Gagal terhubung ke Shiro.';
            try {
                const errData = await response.json();
                if (errData.reply) {
                    if (isMounted()) {
                        showTyping(false);
                        addMessage('assistant', errData.reply);
                        if (status) status.textContent = t('status_ready');
                    }
                    return;
                }
                if (errData.error) errorMsg = errData.error;
            } catch (_) {}
            throw new Error(errorMsg);
        }

        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('text/event-stream')) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let lastRenderTime = 0;
            let lastThoughtRenderTime = 0;

            const upsertLiveStep = (stepObj) => {
                if (!stepObj || !stepObj.id) return;
                const idx = run.liveAgentSteps.findIndex(s => s.id === stepObj.id);
                if (idx >= 0) {
                    run.liveAgentSteps[idx] = { ...run.liveAgentSteps[idx], ...stepObj };
                } else {
                    run.liveAgentSteps.push(stepObj);
                }
            };

            const ensureAssistantMsgEl = () => {
                if (!isMounted()) return null;
                if (!run.assistantMsgEl) {
                    run.assistantMsgEl = addMessage(
                        'assistant',
                        '',
                        run.activeAssistantImgUrl,
                        null,
                        null,
                        null,
                        null,
                        run.activeAgentAction,
                        run.finalData ? run.finalData.assistant_message_id : null,
                        false,
                        {
                            agent_steps: run.liveAgentSteps,
                            thought_content: run.liveThoughtText,
                            thought_duration_sec: run.liveThoughtDuration,
                            artifacts: run.liveArtifacts,
                            is_running: Boolean(run.liveAgentSteps.length || (run.liveThoughtText && run.liveThoughtText.trim()))
                        }
                    );
                    if (run.assistantMsgEl) {
                        showTyping(false);
                        run.assistantBubble = run.assistantMsgEl.querySelector('.bubble');
                        run.assistantTextEl = run.assistantMsgEl.querySelector('.msg-text');
                    }
                }
                return run.assistantMsgEl;
            };

            const updateAssistantUI = (text, isDone = false) => {
                if (!isMounted()) return;
                const trimmedText = (text || '').trim();
                if (!run.assistantMsgEl) {
                    if (!trimmedText && !isDone) {
                        return;
                    }
                    ensureAssistantMsgEl();
                }
                if (run.assistantBubble && (trimmedText || run.activeAssistantImgUrl || isDone)) {
                    run.assistantBubble.classList.remove('hidden');
                }
                if (!run.assistantTextEl && run.assistantBubble) {
                    let existingTextEl = run.assistantBubble.querySelector('.msg-text');
                    if (!existingTextEl) {
                        existingTextEl = document.createElement('div');
                        existingTextEl.className = 'msg-text';
                        run.assistantBubble.appendChild(existingTextEl);
                    }
                    run.assistantTextEl = existingTextEl;
                }
                if (run.assistantTextEl) {
                    let displayContent = text;
                    const codeBlockCount = (displayContent.match(/```/g) || []).length;
                    if (codeBlockCount % 2 === 1) {
                        displayContent += '\n```';
                    }

                    const prevScrollTop = chatViewport ? chatViewport.scrollTop : 0;
                    const distFromBottom = chatViewport ? (chatViewport.scrollHeight - chatViewport.scrollTop - chatViewport.clientHeight) : 0;
                    const isAtBottom = distFromBottom <= 60;

                    run.assistantTextEl.innerHTML = parseMessageContent(displayContent);
                    if (run.assistantBubble) {
                        run.assistantBubble.setAttribute('data-original-text', text);

                        if (run.activeAssistantImgUrl && !run.assistantBubble.querySelector('.chat-img-wrapper')) {
                            const jsImgUrl = run.activeAssistantImgUrl.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                            const imgWrap = document.createElement('div');
                            imgWrap.className = 'chat-img-wrapper';
                            imgWrap.onclick = () => openImageLightbox(jsImgUrl, 'Foto Lampiran Chat');
                            imgWrap.innerHTML = `<img src="${run.activeAssistantImgUrl}" class="chat-img-attachment" alt="Foto Visual" loading="lazy">`;
                            run.assistantBubble.prepend(imgWrap);
                        }
                    }

                    if (chatViewport) {
                        if (isUserScrolledUp) {
                            isProgrammaticScroll = true;
                            chatViewport.scrollTop = prevScrollTop;
                            if (scrollBottomBtn) {
                                scrollBottomBtn.classList.remove('hidden');
                                scrollBottomBtn.classList.add('is-streaming');
                            }
                        } else if (isAtBottom || !isDone) {
                            isProgrammaticScroll = true;
                            chatViewport.scrollTop = chatViewport.scrollHeight;
                        }
                    }
                }
            };

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || trimmed.startsWith(':')) {
                        continue;
                    }
                    if (trimmed.startsWith('data:')) {
                        const jsonStr = trimmed.slice(5).trim();
                        if (!jsonStr) continue;
                        try {
                            const evData = JSON.parse(jsonStr);
                            if (evData.type === 'init') {
                                run.userMsgId = evData.user_message_id || run.userMsgId;
                                if (evData.session_title) syncRunTitle(evData.session_title);
                                if (isMounted() && run.userMsgEl && evData.user_message_id) {
                                    run.userMsgEl.dataset.msgId = evData.user_message_id;
                                }
                            } else if (evData.type === 'status') {
                                if (evData.status) {
                                    run.serverStatusReceived = true;
                                    run.statusText = evData.status;
                                    if (isMounted()) {
                                        updateTypingStatus(evData.status);
                                        if (status) status.textContent = evData.status;
                                    }
                                }
                            } else if (evData.type === 'agent_trace_step') {
                                if (evData.step) {
                                    run.serverStatusReceived = true;
                                    upsertLiveStep(evData.step);
                                    if (evData.step.title) {
                                        run.statusText = evData.step.title + '...';
                                    }
                                    if (isMounted()) {
                                        ensureAssistantMsgEl();
                                        syncAgThoughtInMsg(run.assistantMsgEl, {
                                            agent_steps: run.liveAgentSteps,
                                            thought_content: run.liveThoughtText,
                                            thought_duration_sec: run.liveThoughtDuration,
                                            is_running: true
                                        });
                                        if (evData.step.title && status) {
                                            status.textContent = evData.step.title + '...';
                                        }
                                        scrollToBottom(false);
                                    }
                                }
                            } else if (evData.type === 'thought') {
                                run.serverStatusReceived = true;
                                run.liveThoughtText += (evData.token || '');
                                if (isMounted()) {
                                    ensureAssistantMsgEl();
                                    const nowTh = Date.now();
                                    if (nowTh - lastThoughtRenderTime > 55) {
                                        lastThoughtRenderTime = nowTh;
                                        syncAgThoughtInMsg(run.assistantMsgEl, {
                                            agent_steps: run.liveAgentSteps,
                                            thought_content: run.liveThoughtText,
                                            thought_duration_sec: run.liveThoughtDuration,
                                            is_running: true
                                        });
                                        scrollToBottom(false);
                                    }
                                }
                            } else if (evData.type === 'thought_done') {
                                if (evData.duration_sec !== undefined) {
                                    run.liveThoughtDuration = evData.duration_sec;
                                }
                                if (isMounted() && run.assistantMsgEl) {
                                    syncAgThoughtInMsg(run.assistantMsgEl, {
                                        agent_steps: run.liveAgentSteps,
                                        thought_content: run.liveThoughtText,
                                        thought_duration_sec: run.liveThoughtDuration,
                                        is_running: true
                                    });
                                }
                            } else if (evData.type === 'artifacts') {
                                if (Array.isArray(evData.artifacts) && evData.artifacts.length) {
                                    run.liveArtifacts = evData.artifacts;
                                    if (isMounted()) {
                                        ensureAssistantMsgEl();
                                        syncArtifactsInMsg(run.assistantMsgEl, run.liveArtifacts);
                                        scrollToBottom(false);
                                    }
                                }
                            } else if (evData.type === 'agent_plan') {
                                run.lastAgentTaskId = evData.task_id;
                                run.statusText = 'Rencana siap · Memulai eksekusi...';
                                if (isMounted()) {
                                    createOrUpdateAgentWorkspaceCard(evData.task_id, evData.plan, null, null);
                                    updateTypingStatus(run.statusText);
                                }
                            } else if (evData.type === 'agent_step') {
                                run.lastAgentTaskId = evData.task_id;
                                run.statusText = `Langkah ${evData.step_index}: ${evData.tool} (${evData.status})...`;
                                if (isMounted()) {
                                    createOrUpdateAgentWorkspaceCard(evData.task_id, evData.plan, evData, null);
                                    updateTypingStatus(run.statusText);
                                }
                            } else if (evData.type === 'approval_required') {
                                run.awaitingApproval = true;
                                run.lastAgentTaskId = evData.task_id;
                                run.statusText = 'Menunggu persetujuan Anda...';
                                if (isMounted()) {
                                    createOrUpdateAgentWorkspaceCard(evData.task_id, evData.plan, null, evData.pending_action);
                                    if (status) status.textContent = run.statusText;
                                    updateTypingStatus('Menunggu persetujuan pengguna...');
                                }
                            } else if (evData.type === 'reset_stream') {
                                run.streamText = '';
                                if (isMounted() && run.assistantTextEl) {
                                    run.assistantTextEl.innerHTML = '';
                                }
                            } else if (evData.type === 'agent_action') {
                                run.activeAgentAction = evData.agent_action;
                                if (run.activeAgentAction && run.activeAgentAction.image_url) {
                                    run.activeAssistantImgUrl = run.activeAgentAction.image_url;
                                }
                                const toolTitle = run.activeAgentAction ? (run.activeAgentAction.tool || 'eksekusi') : 'eksekusi';
                                run.statusText = `Selesai menjalankan ${toolTitle} · Menyusun jawaban...`;
                                if (isMounted()) {
                                    if (run.assistantMsgEl && run.activeAgentAction) {
                                        syncWebSourcesInMsg(run.assistantMsgEl, run.activeAgentAction);
                                    }
                                    updateTypingStatus(run.statusText);
                                }
                            } else if (evData.type === 'token') {
                                const chunkTok = evData.token || '';
                                const isFirstVisible = !run.streamText && Boolean(chunkTok.trim());
                                if (isFirstVisible) {
                                    run.statusText = t('status_typing');
                                    if (isMounted() && status) status.textContent = run.statusText;
                                    if (isMounted() && run.assistantMsgEl) {
                                        const thBlk = run.assistantMsgEl.querySelector('.ag-thought-block');
                                        if (thBlk && thBlk.dataset.userToggled !== 'true') {
                                            thBlk.classList.remove('is-open');
                                        }
                                    }
                                }
                                run.streamText += chunkTok;
                                if (isMounted()) {
                                    const now = Date.now();
                                    if (now - lastRenderTime > 35) {
                                        lastRenderTime = now;
                                        updateAssistantUI(run.streamText, false);
                                    }
                                }
                            } else if (evData.type === 'error') {
                                console.warn('[Stream Error Event]:', evData.error);
                                run.hadError = true;
                                const errMsg = evData.error || 'Terjadi gangguan koneksi pada server.';
                                run.errorText = errMsg;
                                if (!run.streamText) {
                                    run.streamText = `Maaf, ada kendala teknis: ${errMsg}`;
                                } else {
                                    run.streamText += `\n\n(Koneksi terganggu: ${errMsg})`;
                                }
                                if (isMounted()) updateAssistantUI(run.streamText, false);
                            } else if (evData.type === 'done') {
                                run.finalData = evData;
                                if (evData.session_title) syncRunTitle(evData.session_title);
                                if (evData.reply && !run.streamText) {
                                    run.streamText = evData.reply;
                                }
                                if (evData.assistant_image_url) {
                                    run.activeAssistantImgUrl = evData.assistant_image_url;
                                }
                                if (evData.agent_action) {
                                    run.activeAgentAction = evData.agent_action;
                                }
                                if (evData.thought_content) {
                                    run.liveThoughtText = evData.thought_content;
                                }
                                if (evData.thought_duration_sec !== undefined && evData.thought_duration_sec !== null) {
                                    run.liveThoughtDuration = evData.thought_duration_sec;
                                }
                                if (Array.isArray(evData.agent_steps) && evData.agent_steps.length) {
                                    run.liveAgentSteps = evData.agent_steps;
                                }
                                if (Array.isArray(evData.artifacts) && evData.artifacts.length) {
                                    run.liveArtifacts = evData.artifacts;
                                }
                            }
                        } catch (errParse) {
                            console.warn('[Stream JSON Parse Error]:', errParse, jsonStr);
                        }
                    }
                }
            }

            if (run.typingProgressInterval) clearInterval(run.typingProgressInterval);
            if (isMounted()) showTyping(false);

            if (run.awaitingApproval && !run.streamText && !run.finalData) {
                if (isMounted()) {
                    clearPipelineSimulation();
                    if (status) status.textContent = 'Menunggu persetujuan Anda...';
                    scrollToBottom(true);
                }
                return;
            }
            if (run.finalData && run.finalData.reply && run.finalData.reply.trim()) {
                run.streamText = run.finalData.reply.trim();
            } else if (!run.streamText && run.finalData && run.finalData.reply) {
                run.streamText = run.finalData.reply;
            }
            if (!run.streamText) {
                run.hadError = true;
                run.streamText = 'Maaf, server tidak memberikan respons lengkap (koneksi terputus atau gagal memuat jawaban).';
            }
            if (isMounted()) {
                if (run.lastAgentTaskId && run.finalData && run.finalData.plan) {
                    createOrUpdateAgentWorkspaceCard(run.lastAgentTaskId, run.finalData.plan, null, null, run.finalData.status || 'completed');
                }
                updateAssistantUI(run.streamText, true);
                if (run.assistantMsgEl) {
                    if (run.liveAgentSteps.length || (run.liveThoughtText && run.liveThoughtText.trim())) {
                        run.liveAgentSteps = run.liveAgentSteps.map(s => s.status === 'running' ? { ...s, status: 'done' } : s);
                        syncAgThoughtInMsg(run.assistantMsgEl, {
                            agent_steps: run.liveAgentSteps,
                            thought_content: run.liveThoughtText,
                            thought_duration_sec: run.liveThoughtDuration,
                            is_running: false,
                            force_open: false
                        });
                    } else {
                        run.assistantMsgEl.querySelectorAll('.ag-thought-block').forEach(el => el.remove());
                    }
                    const finalActionObj = (run.finalData && run.finalData.agent_action) || run.activeAgentAction;
                    if (finalActionObj) {
                        syncWebSourcesInMsg(run.assistantMsgEl, finalActionObj);
                    }
                    if (run.liveArtifacts && run.liveArtifacts.length) {
                        syncArtifactsInMsg(run.assistantMsgEl, run.liveArtifacts);
                    }
                    if (run.finalData && run.finalData.assistant_message_id) {
                        run.assistantMsgEl.dataset.msgId = run.finalData.assistant_message_id;
                    }
                    if (run.finalData && run.finalData.assistant_image_url) {
                        let bubble = run.assistantMsgEl.querySelector('.bubble');
                        if (bubble && !bubble.querySelector('.chat-img-wrapper')) {
                            const jsImgUrl = run.finalData.assistant_image_url.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                            const imgWrap = document.createElement('div');
                            imgWrap.className = 'chat-img-wrapper';
                            imgWrap.onclick = () => openImageLightbox(jsImgUrl, 'Foto Lampiran Chat');
                            imgWrap.innerHTML = `<img src="${run.finalData.assistant_image_url}" class="chat-img-attachment" alt="Foto Visual" loading="lazy">`;
                            bubble.prepend(imgWrap);
                        }
                    }
                    if (typeof hljs !== 'undefined') {
                        run.assistantMsgEl.querySelectorAll('pre code[class*="language-"]').forEach(block => {
                            try { hljs.highlightElement(block); } catch (_) {}
                        });
                    }
                    if (typeof mermaid !== 'undefined') {
                        run.assistantMsgEl.querySelectorAll('.mermaid-container').forEach(async (container) => {
                            const rawSource = container.querySelector('.mermaid-raw-source');
                            const renderTarget = container.querySelector('.mermaid-diagram-render');
                            if (rawSource && renderTarget) {
                                const code = rawSource.textContent.trim();
                                const renderId = `diag_${Date.now()}_${Math.floor(Math.random()*10000)}`;
                                try {
                                    const { svg } = await mermaid.render(renderId, code);
                                    renderTarget.innerHTML = svg;
                                } catch (_) {
                                    renderTarget.innerHTML = `<div class="mermaid-error"><i class="ph ph-warning"></i> Diagram tidak valid. Pilih "Lihat kode" untuk melihat sintaks aslinya.</div>`;
                                }
                            }
                        });
                    }
                }
                clearPipelineSimulation();
                syncQuickCodeDownloadsInMsg(run.assistantMsgEl);
                updateQuickFilesBadge();
                if (run.finalData && run.finalData.pipeline_trace) {
                    activePipelineTrace = run.finalData.pipeline_trace;
                    renderModalPipeline(activePipelineTrace);
                }
            }

            if (run.finalData && run.finalData.session_title) {
                syncRunTitle(run.finalData.session_title);
            }
            if (!isMounted()) {
                unreadDoneSessions.add(targetSessionId);
            }
            showSessionDoneNotification({
                sessionId: targetSessionId,
                sessionTitle: run.sessionTitle || getSessionTitleById(targetSessionId),
                isError: run.hadError,
                errorText: run.errorText
            });

            updateMemoryCount();
            await loadSessions();
            if (isMounted() && status) status.textContent = t('status_ready');
            startTriggerTimer();

        } else {
            // Non-streaming fallback
            const data = await response.json();
            if (data.session_title) syncRunTitle(data.session_title);
            if (isMounted()) {
                if (run.userMsgEl && data.user_message_id) {
                    run.userMsgEl.dataset.msgId = data.user_message_id;
                }
                showTyping(false);
                const assistantImg = data.assistant_image_url || null;
                addMessage(
                    'assistant',
                    data.reply || 'Maaf, server tidak memberikan jawaban teks.',
                    assistantImg,
                    null,
                    null,
                    null,
                    null,
                    data.agent_action,
                    data.assistant_message_id || null,
                    false,
                    {
                        thought_content: data.thought_content || null,
                        thought_duration_sec: data.thought_duration_sec ?? null,
                        agent_steps: data.agent_steps || [],
                        artifacts: data.artifacts || [],
                        is_running: false
                    }
                );
                clearPipelineSimulation();
                if (data.pipeline_trace) {
                    activePipelineTrace = data.pipeline_trace;
                    renderModalPipeline(activePipelineTrace);
                }
                if (status) status.textContent = t('status_ready');
            } else {
                unreadDoneSessions.add(targetSessionId);
            }

            showSessionDoneNotification({
                sessionId: targetSessionId,
                sessionTitle: run.sessionTitle || getSessionTitleById(targetSessionId),
                isError: false
            });
            updateMemoryCount(); 
            await loadSessions();
            startTriggerTimer(); 
        }

    } catch (error) {
        if (run.typingProgressInterval) {
            clearInterval(run.typingProgressInterval);
        }
        if (isMounted()) clearPipelineSimulation();
        if (error.name === 'AbortError') {
            run.aborted = true;
            console.log('Request stopped by user for session:', targetSessionId);
            if (isMounted()) {
                showTyping(false);
                if (status) status.textContent = t('status_stopped');
                const lastAssistantMsg = run.assistantMsgEl || (chatMessages ? chatMessages.querySelector('.message.assistant:last-child') : null);
                if (lastAssistantMsg) {
                    const runningThought = lastAssistantMsg.querySelector('.ag-thought-block.is-running');
                    if (runningThought) {
                        const hasStepsOrText = Boolean(runningThought.querySelector('.ag-trace-step') || runningThought.querySelector('.ag-thought-reasoning'));
                        if (!hasStepsOrText) {
                            runningThought.remove();
                        } else {
                            runningThought.classList.remove('is-running');
                            runningThought.classList.add('is-done');
                            runningThought.querySelectorAll('.ph-spinner, .ag-spinner-ring').forEach(ic => {
                                const sp = document.createElement('i');
                                sp.className = 'ph ph-sparkle';
                                ic.replaceWith(sp);
                            });
                            const titleSp = runningThought.querySelector('.ag-thought-title');
                            if (titleSp) titleSp.textContent = 'Analysis stopped';
                        }
                    }
                    const lastBubble = lastAssistantMsg.querySelector('.bubble');
                    if (lastBubble && lastBubble.classList.contains('hidden')) {
                        lastBubble.classList.remove('hidden');
                        const mt = lastBubble.querySelector('.msg-text');
                        if (mt && !mt.textContent.trim()) {
                            mt.innerHTML = parseMessageContent('*Respons dihentikan oleh pengguna.*');
                        }
                    }
                } else {
                    addMessage('assistant', '*Respons dihentikan oleh pengguna.*');
                }
                if (lastAssistantMsg && typeof hljs !== 'undefined') {
                    lastAssistantMsg.querySelectorAll('pre code[class*="language-"]').forEach(block => {
                        try { hljs.highlightElement(block); } catch (_) {}
                    });
                }
            }
            try {
                updateMemoryCount();
                loadSessions();
            } catch (_) {}
        } else {
            console.error('Error:', error);
            run.hadError = true;
            run.errorText = error.message || 'Gagal terhubung ke server.';
            if (isMounted()) {
                showTyping(false);
                addErrorMessage(run.errorText, { message: displayMsg });
                if (status) status.textContent = t('status_ready');
            } else {
                unreadDoneSessions.add(targetSessionId);
            }
            showSessionDoneNotification({
                sessionId: targetSessionId,
                sessionTitle: run.sessionTitle || getSessionTitleById(targetSessionId),
                isError: true,
                errorText: run.errorText
            });
        }
    } finally {
        if (run.typingProgressInterval) {
            clearInterval(run.typingProgressInterval);
        }
        run.isRunning = false;
        if (sessionRuns.get(targetSessionId) === run) {
            sessionRuns.delete(targetSessionId);
        }
        serverRunningSessions.delete(targetSessionId);
        detachRunDOMRefs(run);
        updateSidebarRunningIndicators();

        if (isMounted()) {
            clearPipelineSimulation();
            if (pipelineNavDot) pipelineNavDot.classList.add('hidden');
            if (scrollBottomBtn) {
                scrollBottomBtn.classList.remove('is-streaming');
                updateScrollBottomBtnVisibility();
            }
            setInputLock(isActiveSessionGenerating());
        }

        const qForSession = getSessionQueue(targetSessionId);
        if (!run.aborted && qForSession.length > 0) {
            const nextQueued = qForSession.shift();
            if (isMounted()) renderQueuedMessagesPanel();
            setTimeout(() => {
                sendMessage(nextQueued, targetSessionId);
            }, 80);
        } else if (isMounted() && userInput) {
            userInput.focus();
        }
    }
}

function stopGeneration(targetSessionId = activeSessionId) {
    const sid = (typeof targetSessionId === 'string' && targetSessionId) ? targetSessionId : (activeSessionId || 'default');
    const run = sessionRuns.get(sid);
    if (run && run.abortController) {
        run.abortController.abort();
    }
}

// ==========================================================================
// In-App Modern Confirmation Dialog System (Zero native alert/confirm popups)
// ==========================================================================
let pendingConfirmResolve = null;

function showConfirmDialog({
    title = 'Konfirmasi Tindakan',
    subtitle = 'Tindakan ini tidak dapat dibatalkan',
    message = 'Apakah Anda yakin ingin melanjutkan tindakan ini?',
    notes = [],
    confirmText = 'Lanjutkan',
    cancelText = 'Batal',
    isDanger = true,
    icon = 'ph-warning'
} = {}) {
    return new Promise((resolve) => {
        if (typeof pendingConfirmResolve === 'function') {
            pendingConfirmResolve(false);
            pendingConfirmResolve = null;
        }
        pendingConfirmResolve = resolve;

        const modal = document.getElementById('confirm-modal');
        const titleEl = document.getElementById('confirm-modal-title');
        const subEl = document.getElementById('confirm-modal-subtitle');
        const msgEl = document.getElementById('confirm-modal-msg');
        const notesEl = document.getElementById('confirm-modal-notes');
        const badgeEl = document.getElementById('confirm-modal-badge');
        const iconEl = document.getElementById('confirm-modal-icon');
        const okBtn = document.getElementById('confirm-modal-ok-btn');
        const cancelBtn = document.getElementById('confirm-modal-cancel-btn');

        if (!modal) {
            resolve(false);
            return;
        }

        if (titleEl) titleEl.textContent = title;
        if (subEl) subEl.textContent = subtitle;
        if (msgEl) msgEl.textContent = message;

        if (badgeEl) {
            badgeEl.className = isDanger ? 'confirm-icon-badge is-danger' : 'confirm-icon-badge is-info';
        }
        if (iconEl) {
            iconEl.className = `ph ${icon}`;
        }
        if (okBtn) {
            okBtn.textContent = confirmText;
            okBtn.className = isDanger ? 'btn-danger-confirm' : 'btn-primary';
        }
        if (cancelBtn) {
            cancelBtn.textContent = cancelText;
        }

        if (notesEl) {
            if (notes && notes.length > 0) {
                notesEl.innerHTML = notes.map(n => `
                    <div class="confirm-note-item">
                        <i class="ph ph-info"></i>
                        <span>${escapeHtml(n)}</span>
                    </div>
                `).join('');
                notesEl.classList.remove('hidden');
            } else {
                notesEl.innerHTML = '';
                notesEl.classList.add('hidden');
            }
        }

        modal.classList.remove('hidden');
    });
}

function resolveConfirmDialog(confirmed) {
    const modal = document.getElementById('confirm-modal');
    if (modal) modal.classList.add('hidden');
    if (typeof pendingConfirmResolve === 'function') {
        const res = pendingConfirmResolve;
        pendingConfirmResolve = null;
        res(Boolean(confirmed));
    }
}

function handleConfirmBackdropClick(e) {
    if (e.target && e.target.id === 'confirm-modal') {
        resolveConfirmDialog(false);
    }
}

async function resetMemory() {
    const isEnglish = currentLang === 'en';
    const confirmed = await showConfirmDialog({
        title: isEnglish ? 'Clear conversation history?' : 'Lupakan percakapan?',
        subtitle: isEnglish ? 'Active session memory reset' : 'Reset riwayat sesi aktif',
        message: isEnglish 
            ? 'Clear all previous messages in this active chat window?' 
            : 'Lupakan semua percakapan sebelumnya dan mulai kembali dari pesan awal?',
        notes: isEnglish ? [
            'Chat bubbles in the active window will be cleared.',
            'Long-term learned facts in settings memory will remain intact.'
        ] : [
            'Semua pesan pada jendela obrolan aktif akan dibersihkan.',
            'Memori fakta jangka panjang Shiro tetap tersimpan aman di pengaturan.'
        ],
        confirmText: isEnglish ? 'Clear' : 'Lupakan',
        cancelText: isEnglish ? 'Cancel' : 'Batal',
        isDanger: true,
        icon: 'ph-trash'
    });

    if (!confirmed) return;

    const originalIcon = resetBtn.innerHTML;
    resetBtn.innerHTML = '<i class="ph ph-spinner ph-spin"></i>';

    try {
        const response = await fetch('/api/reset', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            clearAttachedDocument();
            clearAttachedImage();
            clearAttachedVideo();
            stopGeneration(activeSessionId);
            sessionQueues.delete(activeSessionId);
            unreadDoneSessions.delete(activeSessionId);
            dismissSessionDoneNotifications(activeSessionId);
            renderQueuedMessagesPanel();
            updateComposerSendButton();
            chatMessages.innerHTML = `
                <div class="message assistant">
                    <div class="avatar shiro-avatar">${renderAvatarContent(aiProfile, 'S')}</div>
                    <div class="bubble" data-i18n="welcome_greeting">
                        ${t('welcome_greeting')}
                    </div>
                </div>
            `;
            renderPinnedDrawer();
            updateMemoryCount();
            await loadSessions();
            status.textContent = t('status_ready');
        }
    } catch (error) {
        console.error('Error:', error);
        status.textContent = 'Error';
    } finally {
        resetBtn.innerHTML = originalIcon;
    }
}

function renderMessagesList(messages) {
    if (!chatMessages) return;
    chatMessages.innerHTML = '';
    const validMessages = (messages || []).filter(msg => {
        const hasContent = msg.content !== null && msg.content !== undefined && String(msg.content).trim().length > 0;
        const hasArtifacts = Array.isArray(msg.artifacts) && msg.artifacts.length > 0;
        const hasMultiMedia = (Array.isArray(msg.images) && msg.images.length > 0)
            || (Array.isArray(msg.videos) && msg.videos.length > 0)
            || (Array.isArray(msg.documents) && msg.documents.length > 0);
        return Boolean(hasContent || msg.image || msg.document_name || msg.document_text || hasArtifacts || hasMultiMedia);
    });
    if (validMessages.length > 0) {
        validMessages.forEach(msg => {
            addMessage(
                msg.role, 
                msg.content, 
                msg.image || null, 
                msg.document_name || null,
                msg.document_url || null,
                msg.document_type || null,
                msg.document_text || null,
                null,
                msg.id || null,
                Boolean(msg.pinned),
                {
                    thought_content: msg.thought_content || null,
                    thought_duration_sec: msg.thought_duration_sec ?? null,
                    agent_steps: msg.agent_steps || [],
                    artifacts: msg.artifacts || [],
                    agent_action: msg.agent_action || null,
                    documents: msg.documents || [],
                    images: msg.images || [],
                    videos: msg.videos || [],
                    is_running: false
                }
            );
        });
    } else {
        chatMessages.innerHTML = `
            <div class="message assistant">
                <div class="avatar shiro-avatar">${renderAvatarContent(aiProfile, 'S')}</div>
                <div class="bubble" data-i18n="welcome_greeting">
                    ${t('welcome_greeting')}
                </div>
            </div>
        `;
    }
    
    if (typingIndicator && chatMessages) {
        chatMessages.appendChild(typingIndicator);
    }
    
    renderPinnedDrawer();
    updateQuickFilesBadge();
    const drawer = document.getElementById('chat-files-drawer');
    if (drawer && !drawer.classList.contains('hidden')) {
        renderChatFilesList();
    }
    isUserScrolledUp = false;
    if (scrollBottomBtn) {
        scrollBottomBtn.classList.add('hidden');
        scrollBottomBtn.classList.remove('is-streaming');
    }
    scrollToBottom(true, false);
}

async function loadChatHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        
        if (typeof data.enable_training_logging === 'boolean') {
            updateTrainingBannerUI(data.enable_training_logging);
        }
        if (typeof data.roleplay_enabled === 'boolean') {
            updateRoleplayModeUI(data.roleplay_enabled);
        }
        if (typeof data.notifications_enabled === 'boolean') {
            updateNotificationsModeUI(data.notifications_enabled);
        }

        renderMessagesList(data.history || []);
        updateMemoryCount();
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

let currentSessionsData = [];

function highlightActiveSessionInList(targetId = activeSessionId) {
    if (sidebarSessionList) {
        sidebarSessionList.querySelectorAll('.session-item[data-session-id]').forEach((item) => {
            const isTarget = item.dataset.sessionId === targetId;
            item.classList.toggle('active', isTarget);
            if (isTarget) item.classList.remove('is-unread-done');
        });
    }
    if (sessionSelect && targetId) {
        sessionSelect.value = targetId;
    }
}

function applySessionsListUI(sessions, runningSessions = [], activeIdOverride = null) {
    if (!Array.isArray(sessions)) return;
    currentSessionsData = sessions;
    const displayActiveId = activeIdOverride || activeSessionId || 'default';
    serverRunningSessions = new Set(Array.isArray(runningSessions) ? runningSessions : []);
    sessions.forEach(s => {
        if (s && s.is_running) serverRunningSessions.add(s.id);
    });

    const activeSession = sessions.find(s => s.id === displayActiveId);
    const isCurrentSessionPinned = activeSession ? Boolean(activeSession.pinned) : false;
    updateChatMenuPinState(isCurrentSessionPinned);

    if (activeSession && activeSession.title && activeSession.title !== 'New chat' && activeSession.title !== 'Chat baru') {
        document.title = `${activeSession.title} · Shiro`;
    } else {
        document.title = 'Shiro · AI Assistant';
    }

    if (sessionSelect) {
        sessionSelect.innerHTML = '';
        sessions.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.id;
            const baseLabel = (s.pinned ? '📌 ' : '') + (s.title || `Chat ${s.id.slice(0, 6)}`);
            const running = isSessionRunning(s.id);
            const hasUnread = !running && unreadDoneSessions.has(s.id) && s.id !== displayActiveId;
            opt.textContent = running ? `⏳ ${baseLabel}` : (hasUnread ? `✓ ${baseLabel}` : baseLabel);
            if (s.id === displayActiveId) {
                opt.selected = true;
            }
            sessionSelect.appendChild(opt);
        });
    }

    if (sidebarSessionList) {
        sidebarSessionList.innerHTML = '';
        if (sessions.length === 0) {
            const emptyTip = document.createElement('div');
            emptyTip.className = 'session-empty';
            emptyTip.textContent = t('no_sessions');
            sidebarSessionList.appendChild(emptyTip);
        } else {
            sessions.forEach(s => {
                const running = isSessionRunning(s.id);
                const hasUnread = !running && unreadDoneSessions.has(s.id) && s.id !== displayActiveId;
                const item = document.createElement('div');
                item.className = 'session-item'
                    + (s.id === displayActiveId ? ' active' : '')
                    + (s.pinned ? ' is-pinned' : '')
                    + (running ? ' is-running' : '')
                    + (hasUnread ? ' is-unread-done' : '');
                item.dataset.sessionId = s.id;

                const content = document.createElement('div');
                content.className = 'session-item-content';

                const icon = document.createElement('i');
                icon.className = 'ph ph-chat-teardrop-text session-item-icon';

                const titleSpan = document.createElement('span');
                titleSpan.className = 'session-item-title';
                const sessionFullTitle = s.title || `Chat ${s.id.slice(0, 6)}`;
                titleSpan.textContent = sessionFullTitle;
                item.title = sessionFullTitle;
                titleSpan.title = sessionFullTitle;

                content.appendChild(icon);
                content.appendChild(titleSpan);

                if (running) {
                    const runBadge = document.createElement('span');
                    runBadge.className = 'session-running-badge';
                    runBadge.title = t('session_running_label');
                    runBadge.innerHTML = '<span class="ag-spinner-ring" aria-hidden="true"></span>';
                    content.appendChild(runBadge);
                } else if (hasUnread) {
                    const doneDot = document.createElement('span');
                    doneDot.className = 'session-done-dot';
                    doneDot.title = t('session_done_title');
                    content.appendChild(doneDot);
                }

                if (s.pinned) {
                    const pinBadge = document.createElement('span');
                    pinBadge.className = 'session-pin-badge';
                    pinBadge.title = t('pinned_badge');
                    pinBadge.innerHTML = '<i class="ph-fill ph-push-pin"></i>';
                    content.appendChild(pinBadge);
                }

                const delBtn = document.createElement('button');
                delBtn.type = 'button';
                delBtn.className = 'session-item-delete';
                delBtn.title = t('delete_chat_tooltip');
                delBtn.innerHTML = '<i class="ph ph-trash"></i>';
                delBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    deleteSessionById(s.id, s.title);
                });

                item.appendChild(content);
                item.appendChild(delBtn);

                item.addEventListener('click', () => {
                    switchSession(s.id);
                    if (window.innerWidth <= 768) {
                        closeSidebar();
                    }
                });

                sidebarSessionList.appendChild(item);
            });
        }
    }
}

async function loadSessions(options = {}) {
    const { syncActive = false, renderMessages = false } = options || {};
    const seqAtStart = sessionSwitchSeq;
    try {
        const res = await fetch('/api/sessions');
        const data = await res.json();
        if (seqAtStart !== sessionSwitchSeq) return;
        if (data.sessions) {
            if (syncActive && data.active_session_id) {
                activeSessionId = data.active_session_id;
            }
            const displayId = activeSessionId || data.active_session_id || 'default';
            if (renderMessages && data.active_session_id === displayId && Array.isArray(data.messages) && !isActiveSessionGenerating()) {
                const existingMsgs = chatMessages ? chatMessages.querySelectorAll('.message:not(#typing-indicator)') : [];
                const isOnlyGreeting = existingMsgs.length === 1 && existingMsgs[0].querySelector('[data-i18n="welcome_greeting"]');
                if (existingMsgs.length === 0 || isOnlyGreeting) {
                    renderMessagesList(data.messages);
                }
            }
            applySessionsListUI(data.sessions, data.running_sessions || [], displayId);
        }
    } catch (e) {
        console.error("Error loading sessions:", e);
    }
}

async function createNewSession() {
    const seq = ++sessionSwitchSeq;
    detachAllRunDOMRefs();
    showTyping(false);
    if (chatMessages) chatMessages.classList.add('is-switching');
    try {
        if (status) status.textContent = '...';
        const res = await fetch('/api/sessions/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: t('new_chat') })
        });
        const data = await res.json();
        if (seq !== sessionSwitchSeq) return;
        if (data.success) {
            activeSessionId = data.session_id;
            unreadDoneSessions.delete(activeSessionId);
            try {
                window.history.pushState(null, '', '/chat/' + data.session_id);
            } catch (e) {}

            clearAttachedDocument();
            clearAttachedImage();
            clearAttachedVideo();

            chatMessages.innerHTML = `
                <div class="message assistant">
                    <div class="avatar shiro-avatar">${renderAvatarContent(aiProfile, 'S')}</div>
                    <div class="bubble" data-i18n="new_session_greeting">
                        ${t('new_session_greeting')}
                    </div>
                </div>
            `;
            if (typingIndicator && chatMessages) {
                chatMessages.appendChild(typingIndicator);
            }
            renderPinnedDrawer();
            updateQuickFilesBadge();
            const drawer = document.getElementById('chat-files-drawer');
            if (drawer && !drawer.classList.contains('hidden')) {
                renderChatFilesList();
            }
            if (Array.isArray(data.sessions)) {
                applySessionsListUI(data.sessions, data.running_sessions || [], activeSessionId);
            } else {
                await loadSessions({ syncActive: false, renderMessages: false });
            }
            syncActiveSessionUI();
            updateMemoryCount();
            if (userInput) userInput.focus();
        }
    } catch (e) {
        console.error("Error creating new session:", e);
        if (status) status.textContent = 'Error';
    } finally {
        if (chatMessages && seq === sessionSwitchSeq) chatMessages.classList.remove('is-switching');
    }
}

async function switchSession(sessionId, force = false) {
    if (!sessionId || (sessionId === activeSessionId && !force)) return;
    const prevSessionId = activeSessionId;
    const seq = ++sessionSwitchSeq;
    activeSessionId = sessionId;
    detachAllRunDOMRefs();
    showTyping(false);
    unreadDoneSessions.delete(sessionId);
    dismissSessionDoneNotifications(sessionId);
    highlightActiveSessionInList(sessionId);
    if (chatMessages) chatMessages.classList.add('is-switching');
    try {
        if (status) status.textContent = '...';
        const res = await fetch('/api/sessions/switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });
        const data = await res.json();
        if (seq !== sessionSwitchSeq) return;
        if (data.success) {
            try {
                if (window.location.pathname !== '/chat/' + sessionId) {
                    window.history.pushState(null, '', '/chat/' + sessionId);
                }
            } catch (e) {}

            clearAttachedDocument();
            clearAttachedImage();
            clearAttachedVideo();

            renderMessagesList(data.messages || []);
            if (Array.isArray(data.sessions)) {
                applySessionsListUI(data.sessions, data.running_sessions || [], sessionId);
            } else {
                await loadSessions({ syncActive: false, renderMessages: false });
            }
            syncActiveSessionUI();
            updateMemoryCount();
            if (userInput) userInput.focus();
        } else {
            activeSessionId = prevSessionId;
            highlightActiveSessionInList(prevSessionId);
            syncActiveSessionUI();
        }
    } catch (e) {
        console.error("Error switching session:", e);
        if (seq === sessionSwitchSeq) {
            activeSessionId = prevSessionId;
            highlightActiveSessionInList(prevSessionId);
            if (status) status.textContent = 'Error';
        }
    } finally {
        if (chatMessages && seq === sessionSwitchSeq) chatMessages.classList.remove('is-switching');
    }
}

async function deleteSessionById(sessionId, title) {
    const sessionName = title || (currentLang === 'en' ? 'this conversation' : 'percakapan ini');
    const isEnglish = currentLang === 'en';

    const dialogTitle = isEnglish ? 'Delete conversation?' : 'Hapus percakapan?';
    const dialogSubtitle = `"${sessionName}"`;
    const dialogMessage = isEnglish
        ? 'Are you sure you want to delete this conversation session?'
        : 'Apakah Anda yakin ingin menghapus sesi percakapan ini?';

    const dialogNotes = isEnglish ? [
        enableTrainingLogging
            ? 'Visible messages in this session will be removed.'
            : 'Private Session Mode is active (Training Logging OFF).',
        enableTrainingLogging
            ? 'Training dataset & previously learned memories remain safely preserved.'
            : 'This session will be permanently erased without saving to training data.'
    ] : [
        enableTrainingLogging
            ? 'Percakapan di sesi ini akan dihapus.'
            : 'Mode Sesi Privat aktif (Simpan Data Training: OFF).',
        enableTrainingLogging
            ? 'Seluruh data pelatihan (training dataset) dan fakta ingatan Shiro tetap tersimpan aman.'
            : 'Percakapan sesi ini akan dihapus permanen tanpa direkam ke dataset training.'
    ];

    const confirmed = await showConfirmDialog({
        title: dialogTitle,
        subtitle: dialogSubtitle,
        message: dialogMessage,
        notes: dialogNotes,
        confirmText: isEnglish ? 'Delete' : 'Hapus',
        cancelText: isEnglish ? 'Cancel' : 'Batal',
        isDanger: true,
        icon: 'ph-trash'
    });

    if (!confirmed) return;

    const seq = ++sessionSwitchSeq;
    const runningTarget = sessionRuns.get(sessionId);
    if (runningTarget && runningTarget.isRunning && runningTarget.abortController) {
        runningTarget.aborted = true;
        runningTarget.abortController.abort();
    }
    sessionQueues.delete(sessionId);
    unreadDoneSessions.delete(sessionId);
    dismissSessionDoneNotifications(sessionId);

    try {
        if (status) status.textContent = '...';
        const res = await fetch(`/api/sessions/${sessionId}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (seq !== sessionSwitchSeq) return;
        if (data.success) {
            activeSessionId = data.active_session_id;
            detachAllRunDOMRefs();
            clearAttachedDocument();
            clearAttachedImage();
            clearAttachedVideo();

            renderMessagesList(data.messages || []);
            if (Array.isArray(data.sessions)) {
                applySessionsListUI(data.sessions, data.running_sessions || [], activeSessionId);
            } else {
                await loadSessions({ syncActive: false, renderMessages: false });
            }
            syncActiveSessionUI();
            updateMemoryCount();
        } else if (status) {
            status.textContent = 'Error';
        }
    } catch (e) {
        console.error("Error deleting session:", e);
        status.textContent = 'Error';
    }
}

async function deleteCurrentSession() {
    deleteSessionById(activeSessionId);
}

// --- Gemini-Style 3-Dots Dropdown Actions & Session Management ---
function updateChatMenuPinState(isPinned) {
    const pinIcon = document.getElementById('action-pin-icon');
    const pinLabel = document.getElementById('action-pin-label');
    const pinItem = document.getElementById('action-pin-chat');
    if (pinIcon) {
        pinIcon.className = isPinned ? 'ph-fill ph-push-pin' : 'ph ph-push-pin';
    }
    if (pinLabel) {
        pinLabel.setAttribute('data-i18n', isPinned ? 'menu_unpin_chat' : 'menu_pin_chat');
        pinLabel.textContent = t(isPinned ? 'menu_unpin_chat' : 'menu_pin_chat');
    }
    if (pinItem) {
        pinItem.classList.toggle('item-active', Boolean(isPinned));
    }
}

function toggleChatActionsMenu(forceState) {
    const menu = document.getElementById('chat-actions-menu');
    const btn = document.getElementById('chat-actions-btn');
    if (!menu) return;
    const shouldOpen = forceState !== undefined ? Boolean(forceState) : menu.classList.contains('hidden');
    if (shouldOpen) {
        menu.classList.remove('hidden');
        if (btn) {
            btn.classList.add('active');
            btn.setAttribute('aria-expanded', 'true');
        }
    } else {
        menu.classList.add('hidden');
        if (btn) {
            btn.classList.remove('active');
            btn.setAttribute('aria-expanded', 'false');
        }
    }
}

document.addEventListener('click', (e) => {
    const menu = document.getElementById('chat-actions-menu');
    const btn = document.getElementById('chat-actions-btn');
    if (menu && !menu.classList.contains('hidden')) {
        if (!e.target.closest('#chat-actions-menu') && !e.target.closest('#chat-actions-btn')) {
            toggleChatActionsMenu(false);
        }
    }
});

async function togglePinActiveSession() {
    toggleChatActionsMenu(false);
    try {
        const res = await fetch(`/api/sessions/${activeSessionId}/pin`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        if (data.success) {
            updateChatMenuPinState(data.pinned);
            await loadSessions();
            showToast(data.pinned ? t('session_pinned_toast') : t('session_unpinned_toast'));
        } else {
            showToast(data.error || 'Gagal mengubah status sematan');
        }
    } catch (e) {
        console.error("Error pinning session:", e);
        showToast('Error koneksi saat menyematkan obrolan');
    }
}

// Rename Session Modal Handlers
function openRenameModal() {
    toggleChatActionsMenu(false);
    const modal = document.getElementById('rename-modal');
    const input = document.getElementById('rename-input');
    if (!modal || !input) return;

    const currentSession = currentSessionsData.find(s => s.id === activeSessionId);
    input.value = currentSession ? (currentSession.title || '') : '';
    modal.classList.remove('hidden');
    setTimeout(() => {
        input.focus();
        input.select();
    }, 50);
}

function closeRenameModal() {
    const modal = document.getElementById('rename-modal');
    if (modal) modal.classList.add('hidden');
}

function handleRenameBackdropClick(e) {
    const modal = document.getElementById('rename-modal');
    if (e.target === modal) {
        closeRenameModal();
    }
}

async function saveRenameSession() {
    const input = document.getElementById('rename-input');
    if (!input) return;
    const newTitle = input.value.trim();
    if (!newTitle) {
        showToast(currentLang === 'en' ? 'Conversation title cannot be empty' : 'Judul percakapan tidak boleh kosong');
        input.focus();
        return;
    }

    try {
        const res = await fetch(`/api/sessions/${activeSessionId}/rename`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle })
        });
        const data = await res.json();
        if (data.success) {
            closeRenameModal();
            await loadSessions();
            showToast(t('session_renamed_toast'));
        } else {
            showToast(data.error || 'Gagal mengubah nama percakapan');
        }
    } catch (e) {
        console.error("Error renaming session:", e);
        showToast('Error koneksi saat mengubah nama obrolan');
    }
}

// ==========================================================================
// Claude-Style Share Conversation Link
// ==========================================================================
function openShareModal() {
    const shareModal = document.getElementById('share-modal');
    if (!shareModal) return;
    const shareUrl = `${window.location.origin}/chat/${activeSessionId}`;
    const input = document.getElementById('share-link-input');
    if (input) input.value = shareUrl;
    
    const currentSession = currentSessionsData.find(s => s.id === activeSessionId);
    const sessionTitle = currentSession ? (currentSession.title || 'Obrolan') : 'Obrolan';
    const titleEl = document.getElementById('share-session-title');
    if (titleEl) titleEl.textContent = sessionTitle;
    const metaEl = document.getElementById('share-session-meta');
    if (metaEl) metaEl.textContent = `ID: ${activeSessionId}`;

    shareModal.classList.remove('hidden');
    if (input) {
        input.focus();
        input.select();
    }
}

function closeShareModal() {
    const shareModal = document.getElementById('share-modal');
    if (shareModal) shareModal.classList.add('hidden');
}

function handleShareBackdropClick(e) {
    if (e.target && e.target.id === 'share-modal') {
        closeShareModal();
    }
}

async function copyShareLink() {
    const shareUrl = `${window.location.origin}/chat/${activeSessionId}`;
    try {
        await navigator.clipboard.writeText(shareUrl);
    } catch (e) {
        const input = document.getElementById('share-link-input');
        if (input) {
            input.select();
            document.execCommand('copy');
        }
    }
    const copyText = document.getElementById('share-copy-text');
    const copyIcon = document.getElementById('share-copy-icon');
    if (copyText) copyText.textContent = t('copied') || 'Tersalin!';
    if (copyIcon) copyIcon.className = 'ph ph-check';
    showToast(t('link_copied_toast'));
    setTimeout(() => {
        if (copyText) copyText.textContent = t('copy_link_btn') || 'Salin';
        if (copyIcon) copyIcon.className = 'ph ph-copy';
    }, 2000);
}

// Share Conversation (Generate and copy unique Claude-style URL, then open dialog)
async function shareCurrentChat() {
    toggleChatActionsMenu(false);
    const shareUrl = `${window.location.origin}/chat/${activeSessionId}`;
    try {
        await navigator.clipboard.writeText(shareUrl);
        showToast(t('link_copied_toast'));
    } catch (e) {
        console.warn('Clipboard write error:', e);
    }
    openShareModal();
}

// Export Conversation (.md file download)
function exportCurrentChat() {
    toggleChatActionsMenu(false);
    const msgEls = document.querySelectorAll('#chat-messages .message:not(.typing-indicator)');
    if (!msgEls || msgEls.length === 0) {
        showToast(t('no_sessions'));
        return;
    }

    const currentSession = currentSessionsData.find(s => s.id === activeSessionId);
    const sessionTitle = currentSession ? (currentSession.title || 'chat') : 'chat';
    const safeTitle = sessionTitle.replace(/[^\w\s-]/gi, '').trim().replace(/\s+/g, '_') || 'shiro_chat';

    const lines = [];
    lines.push(`# ${sessionTitle}`);
    lines.push(`Sesi: ${activeSessionId} | Waktu Ekspor: ${new Date().toISOString()}\n`);

    msgEls.forEach(el => {
        const isUser = el.classList.contains('user');
        const role = isUser ? 'User' : 'Assistant (Shiro)';
        const bubble = el.querySelector('.bubble');
        if (bubble && !bubble.classList.contains('typing-bubble') && !el.classList.contains('typing-indicator')) {
            const text = bubble.innerText.trim();
            if (text && text !== '...' && !text.startsWith('Sedang memproses')) {
                lines.push(`**${role}:**\n${text}\n`);
            }
        }
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${safeTitle}_${Date.now()}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(t('export_started_toast'));
}

// ==========================================================================
// ChatGPT-Style "Files in Chat" Drawer Panel
// ==========================================================================
function openChatFilesDrawer() {
    const drawer = document.getElementById('chat-files-drawer');
    if (!drawer) return;
    renderChatFilesList();
    drawer.classList.remove('hidden');
}

function closeChatFilesDrawer() {
    const drawer = document.getElementById('chat-files-drawer');
    if (drawer) drawer.classList.add('hidden');
}

function toggleChatFilesDrawer() {
    const drawer = document.getElementById('chat-files-drawer');
    if (!drawer) return;
    if (drawer.classList.contains('hidden')) {
        openChatFilesDrawer();
    } else {
        closeChatFilesDrawer();
    }
}

function triggerDocUploadFromDrawer() {
    const input = document.getElementById('doc-file-input');
    if (input) input.click();
}

function showChatFiles() {
    toggleChatActionsMenu(false);
    openChatFilesDrawer();
}

function collectSessionDownloadableFiles() {
    const files = [];
    const seen = new Set();

    // 1. Artifact & blok kode dari AI (terbaru di atas agar langsung terlihat tanpa scroll)
    const assistantMsgs = Array.from(document.querySelectorAll('#chat-messages .message.assistant')).reverse();
    assistantMsgs.forEach((el) => {
        el.querySelectorAll('.ag-artifact-card').forEach((card) => {
            const dlLink = card.querySelector('.ag-artifact-dl-btn');
            const nameEl = card.querySelector('.ag-artifact-name');
            const subEl = card.querySelector('.ag-artifact-sub');
            const fname = (nameEl && nameEl.textContent ? nameEl.textContent.trim() : '') || (dlLink ? dlLink.getAttribute('download') : '');
            const url = dlLink ? dlLink.getAttribute('href') : '';
            if (!fname || !url) return;
            const key = `art_${fname}_${url}`;
            if (!seen.has(key)) {
                seen.add(key);
                files.push({
                    type: 'artifact',
                    filename: fname,
                    url: url,
                    metaText: subEl ? subEl.textContent.trim() : '',
                    sourceLabel: t('ai_generated_tag'),
                    targetEl: card,
                });
            }
        });

        const wrappers = Array.from(el.querySelectorAll('.code-block-wrapper'))
            .filter(wr => wr.dataset.downloadable !== 'false')
            .reverse();
        wrappers.forEach((wr, idx) => {
            const meta = resolveCodeBlockMeta(wr);
            if (!meta) return;
            const key = `code_${meta.filename}_${meta.text.length}_${idx}`;
            files.push({
                type: 'ai_code',
                filename: meta.filename,
                fileType: meta.ext || meta.lang || 'txt',
                sourceLabel: t('ai_generated_tag'),
                wrapperEl: wr,
            });
        });
    });

    // 2. Lampiran aktif di composer
    if (attachedDocument && attachedDocument.filename) {
        const key = 'doc_' + attachedDocument.filename;
        if (!seen.has(key)) {
            seen.add(key);
            files.push({
                type: 'doc',
                filename: attachedDocument.filename,
                url: attachedDocument.url || '',
                fileType: attachedDocument.file_type || 'dokumen',
                textContent: attachedDocument.text_content || '',
                activeAttached: true
            });
        }
    }
    if (attachedImage && attachedImage.filename) {
        const key = 'img_' + attachedImage.filename;
        if (!seen.has(key)) {
            seen.add(key);
            files.push({
                type: 'image',
                filename: attachedImage.filename,
                url: attachedImage.url || attachedImage.data_url || '',
                activeAttached: true
            });
        }
    }

    // 3. Dokumen & gambar unggahan pada riwayat chat
    const msgEls = document.querySelectorAll('#chat-messages .message');
    msgEls.forEach(el => {
        el.querySelectorAll('.chat-doc-card').forEach(card => {
            const nameEl = card.querySelector('.chat-doc-name');
            const fname = nameEl ? nameEl.textContent.trim() : '';
            const key = 'doc_' + fname;
            if (fname && !seen.has(key)) {
                seen.add(key);
                files.push({
                    type: 'doc',
                    filename: fname,
                    url: `/api/files/${encodeURIComponent(fname)}`,
                    fileType: fname.split('.').pop() || ''
                });
            }
        });
        const imgEl = el.querySelector('.chat-img-attachment');
        if (imgEl) {
            const src = imgEl.getAttribute('src');
            const fname = imgEl.getAttribute('alt') || 'gambar.png';
            const key = 'img_' + (src || fname);
            if (src && !seen.has(key)) {
                seen.add(key);
                files.push({
                    type: 'image',
                    filename: fname,
                    url: src
                });
            }
        }
    });

    return files;
}

function updateQuickFilesBadge() {
    const btn = document.getElementById('quick-files-btn');
    const cntEl = document.getElementById('quick-files-count');
    if (!btn || !cntEl) return;
    const aiCount = document.querySelectorAll('#chat-messages .message.assistant .code-block-wrapper[data-downloadable="true"], #chat-messages .message.assistant .ag-artifact-card').length;
    const totalCount = aiCount || collectSessionDownloadableFiles().length;
    if (totalCount > 0) {
        cntEl.textContent = String(totalCount);
        btn.classList.remove('hidden');
    } else {
        cntEl.textContent = '0';
        btn.classList.add('hidden');
    }
    const drawer = document.getElementById('chat-files-drawer');
    if (drawer && !drawer.classList.contains('hidden')) {
        renderChatFilesList();
    }
}

function renderChatFilesList() {
    const listContainer = document.getElementById('chat-files-list');
    const emptyState = document.getElementById('chat-files-empty');
    if (!listContainer) return;
    listContainer.innerHTML = '';

    const files = collectSessionDownloadableFiles();

    if (files.length === 0) {
        if (emptyState) emptyState.classList.remove('hidden');
        return;
    }

    if (emptyState) emptyState.classList.add('hidden');

    files.forEach(f => {
        const item = document.createElement('div');
        item.className = 'chat-file-card';

        let iconHtml = '';
        const ext = (f.filename.split('.').pop() || '').toLowerCase();
        const isCodeExt = ['py', 'js', 'ts', 'jsx', 'tsx', 'cpp', 'c', 'cs', 'go', 'rs', 'php', 'html', 'css', 'json', 'yaml', 'yml', 'sql', 'sh', 'bat', 'ps1'].includes(ext);

        if (f.type === 'image') {
            if (f.url) {
                iconHtml = `<img src="${escapeHtml(f.url)}" class="chat-file-thumb-img" alt="${escapeHtml(f.filename)}" />`;
            } else {
                iconHtml = `<div class="chat-file-card-icon is-image"><i class="ph ph-image"></i></div>`;
            }
        } else if (f.type === 'artifact') {
            iconHtml = `<div class="chat-file-card-icon is-code"><i class="ph ph-file-zip"></i></div>`;
        } else if (isCodeExt || f.type === 'ai_code') {
            iconHtml = `<div class="chat-file-card-icon is-code"><i class="ph ph-file-code"></i></div>`;
        } else {
            iconHtml = `<div class="chat-file-card-icon is-doc"><i class="ph ph-file-text"></i></div>`;
        }

        const typeLabel = ext ? ext.toUpperCase() : (f.type === 'image' ? 'IMG' : 'DOC');

        if (f.type === 'ai_code' || f.type === 'artifact') {
            item.innerHTML = `
                ${iconHtml}
                <div class="chat-file-card-info">
                    <span class="chat-file-card-name" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</span>
                    <span class="chat-file-card-meta">
                        <span class="file-ext-tag">${escapeHtml(typeLabel)}</span>
                        • ${escapeHtml(f.sourceLabel || t('ai_generated_tag'))}${f.metaText ? ` · ${escapeHtml(f.metaText)}` : ''}
                    </span>
                </div>
                <div class="chat-file-card-actions">
                    <button type="button" class="btn-file-action download-btn" title="${escapeHtml(t('download_code'))} ${escapeHtml(f.filename)}" data-action="download">
                        <i class="ph ph-download-simple"></i>
                    </button>
                </div>
            `;
            const dlBtn = item.querySelector('.btn-file-action.download-btn');
            if (dlBtn) {
                dlBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (f.type === 'ai_code' && f.wrapperEl) {
                        downloadCodeFromWrapper(f.wrapperEl, dlBtn, false);
                    } else if (f.url) {
                        const a = document.createElement('a');
                        a.href = f.url;
                        a.download = f.filename;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                    }
                });
            }
            item.addEventListener('click', () => {
                if (f.wrapperEl) {
                    f.wrapperEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                } else if (f.targetEl) {
                    f.targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            });
            listContainer.appendChild(item);
            return;
        }

        item.innerHTML = `
            ${iconHtml}
            <div class="chat-file-card-info">
                <span class="chat-file-card-name" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</span>
                <span class="chat-file-card-meta">
                    <span class="file-ext-tag">${escapeHtml(typeLabel)}</span>
                    ${f.activeAttached ? '• Terpasang di composer' : ''}
                </span>
            </div>
            <div class="chat-file-card-actions">
                <button type="button" class="btn-file-action attach-btn" title="${t('attach_to_chat')}" data-action="attach">
                    <i class="ph ph-paperclip"></i>
                </button>
                <button type="button" class="btn-file-action view-btn" title="${t('view_file')}" data-action="view">
                    <i class="ph ph-arrow-square-out"></i>
                </button>
            </div>
        `;

        // Click on "Attach"
        const attachBtn = item.querySelector('.btn-file-action.attach-btn');
        if (attachBtn) {
            attachBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (f.type === 'image') {
                    attachImageFromExisting(f.filename, f.url);
                } else {
                    attachDocumentFromExisting(f.filename, f.url, f.fileType, f.textContent);
                }
            });
        }

        // Click on "View" or item card
        const viewBtn = item.querySelector('.btn-file-action.view-btn');
        if (viewBtn) {
            viewBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                openFilePreview(f);
            });
        }

        item.addEventListener('click', () => {
            openFilePreview(f);
        });

        listContainer.appendChild(item);
    });
}

function openFilePreview(f) {
    if (f.type === 'image') {
        openImageLightbox(f.url, f.filename);
    } else {
        openDocModal(f.filename, f.url, f.fileType || '', f.textContent || '');
    }
}

function attachDocumentFromExisting(filename, url, fileType, textContent) {
    attachedDocument = {
        filename: filename,
        url: url,
        file_type: fileType || 'dokumen',
        text_content: textContent || ''
    };
    if (docPreviewName) docPreviewName.textContent = filename;
    if (docPreviewBar) docPreviewBar.classList.remove('hidden');
    if (userInput) userInput.focus();
    showToast(t('file_attached_toast'));
}

function attachImageFromExisting(filename, url) {
    attachedImage = {
        filename: filename,
        url: url,
        data_url: url
    };
    if (imagePreviewName) imagePreviewName.textContent = filename;
    if (imagePreviewThumb) imagePreviewThumb.src = url;
    if (imagePreviewBar) imagePreviewBar.classList.remove('hidden');
    if (userInput) userInput.focus();
    showToast(t('image_attached_toast'));
}

// Sidebar Controls
function isSidebarCollapsed() {
    if (!chatSidebar) return false;
    return chatSidebar.classList.contains('collapsed');
}

function openSidebar() {
    if (!chatSidebar) return;
    chatSidebar.classList.remove('collapsed');
    if (appLayout) {
        appLayout.classList.remove('sidebar-collapsed');
    }
    if (sidebarBackdrop) {
        sidebarBackdrop.classList.remove('hidden');
    }
    try {
        localStorage.setItem('shiro_sidebar_collapsed', 'false');
    } catch (e) {}
}

function closeSidebar() {
    if (!chatSidebar) return;
    chatSidebar.classList.add('collapsed');
    if (appLayout) {
        appLayout.classList.add('sidebar-collapsed');
    }
    if (sidebarBackdrop) {
        sidebarBackdrop.classList.add('hidden');
    }
    try {
        localStorage.setItem('shiro_sidebar_collapsed', 'true');
    } catch (e) {}
}

function toggleSidebar() {
    if (isSidebarCollapsed()) {
        openSidebar();
    } else {
        closeSidebar();
    }
}

function initSidebarState() {
    if (!chatSidebar) return;
    try {
        const saved = localStorage.getItem('shiro_sidebar_collapsed');
        if (saved === 'true') {
            closeSidebar();
        } else if (saved === 'false') {
            openSidebar();
        } else {
            if (window.innerWidth <= 768) {
                closeSidebar();
            } else {
                openSidebar();
            }
        }
    } catch (e) {
        if (window.innerWidth <= 768) {
            closeSidebar();
        }
    }
}

function initSidebarResizer() {
    const resizer = document.getElementById('sidebar-resizer');
    const sidebar = document.getElementById('chat-sidebar');
    if (!resizer || !sidebar) return;

    try {
        const savedWidth = localStorage.getItem('shiro_sidebar_width');
        if (savedWidth) {
            const w = parseInt(savedWidth, 10);
            if (w >= 220 && w <= 520) {
                document.documentElement.style.setProperty('--sidebar-width', `${w}px`);
                sidebar.style.width = `${w}px`;
            }
        }
    } catch (e) {}

    let isDragging = false;
    let startX = 0;
    let startWidth = 260;

    const onMouseDown = (e) => {
        if (window.innerWidth <= 768 || sidebar.classList.contains('collapsed')) return;
        isDragging = true;
        startX = e.clientX;
        startWidth = sidebar.getBoundingClientRect().width;
        resizer.classList.add('is-dragging');
        document.body.classList.add('sidebar-resizing');
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        e.preventDefault();
    };

    const onMouseMove = (e) => {
        if (!isDragging) return;
        const deltaX = e.clientX - startX;
        const newWidth = Math.min(Math.max(startWidth + deltaX, 220), 520);
        document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
        sidebar.style.width = `${newWidth}px`;
    };

    const onMouseUp = () => {
        if (!isDragging) return;
        isDragging = false;
        resizer.classList.remove('is-dragging');
        document.body.classList.remove('sidebar-resizing');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);

        try {
            const currentW = Math.round(sidebar.getBoundingClientRect().width);
            localStorage.setItem('shiro_sidebar_width', currentW);
        } catch (e) {}
    };

    resizer.addEventListener('mousedown', onMouseDown);

    // Double-click to reset width to default 260px
    resizer.addEventListener('dblclick', () => {
        document.documentElement.style.setProperty('--sidebar-width', '260px');
        sidebar.style.width = '260px';
        try {
            localStorage.removeItem('shiro_sidebar_width');
        } catch (e) {}
        showToast(currentLang === 'en' ? 'Sidebar width reset to 260px' : 'Lebar sidebar di-reset ke 260px');
    });

    // Touch dragging for hybrid laptops / tablets
    resizer.addEventListener('touchstart', (e) => {
        if (window.innerWidth <= 768 || sidebar.classList.contains('collapsed')) return;
        const touch = e.touches[0];
        isDragging = true;
        startX = touch.clientX;
        startWidth = sidebar.getBoundingClientRect().width;
        resizer.classList.add('is-dragging');
        document.body.classList.add('sidebar-resizing');
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
        if (!isDragging) return;
        const touch = e.touches[0];
        const deltaX = touch.clientX - startX;
        const newWidth = Math.min(Math.max(startWidth + deltaX, 220), 520);
        document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
        sidebar.style.width = `${newWidth}px`;
    }, { passive: true });

    window.addEventListener('touchend', () => {
        if (!isDragging) return;
        isDragging = false;
        resizer.classList.remove('is-dragging');
        document.body.classList.remove('sidebar-resizing');
        try {
            const currentW = Math.round(sidebar.getBoundingClientRect().width);
            localStorage.setItem('shiro_sidebar_width', currentW);
        } catch (e) {}
    });
}

function initModalTabsScroll() {
    const tabsContainer = document.getElementById('settings-modal-tabs') || document.querySelector('.modal-tabs');
    if (!tabsContainer) return;
    if (tabsContainer.scrollWidth <= tabsContainer.clientWidth + 2) return;

    let isDown = false;
    let startX = 0;
    let scrollLeft = 0;

    tabsContainer.addEventListener('mousedown', (e) => {
        isDown = true;
        tabsContainer.classList.add('is-dragging');
        startX = e.pageX - tabsContainer.offsetLeft;
        scrollLeft = tabsContainer.scrollLeft;
    });

    tabsContainer.addEventListener('mouseleave', () => {
        isDown = false;
        tabsContainer.classList.remove('is-dragging');
    });

    tabsContainer.addEventListener('mouseup', () => {
        isDown = false;
        tabsContainer.classList.remove('is-dragging');
    });

    tabsContainer.addEventListener('mousemove', (e) => {
        if (!isDown) return;
        e.preventDefault();
        const x = e.pageX - tabsContainer.offsetLeft;
        const walk = (x - startX) * 1.5;
        tabsContainer.scrollLeft = scrollLeft - walk;
    });

    tabsContainer.addEventListener('wheel', (e) => {
        if (e.deltaY !== 0) {
            e.preventDefault();
            tabsContainer.scrollLeft += e.deltaY;
        }
    }, { passive: false });
}

// Event Listeners
sendBtn.addEventListener('click', () => sendMessage());
stopBtn.addEventListener('click', () => stopGeneration());
if (newChatBtn) newChatBtn.addEventListener('click', createNewSession);
if (sidebarNewChatBtn) {
    sidebarNewChatBtn.addEventListener('click', () => {
        createNewSession();
        if (window.innerWidth <= 768) closeSidebar();
    });
}
if (openSidebarBtn) openSidebarBtn.addEventListener('click', toggleSidebar);
if (closeSidebarBtn) closeSidebarBtn.addEventListener('click', closeSidebar);
if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', closeSidebar);

if (sidebarPipelineBtn) {
    sidebarPipelineBtn.addEventListener('click', () => {
        if (typeof openPipelineModal === 'function') openPipelineModal();
        if (window.innerWidth <= 768) closeSidebar();
    });
}
if (sidebarSettingsBtn) {
    sidebarSettingsBtn.addEventListener('click', () => {
        if (typeof openSettings === 'function') openSettings();
        if (window.innerWidth <= 768) closeSidebar();
    });
}

if (sessionSelect) sessionSelect.addEventListener('change', (e) => switchSession(e.target.value));
if (deleteChatBtn) deleteChatBtn.addEventListener('click', deleteCurrentSession);

// Gemini 3-Dots Menu & Rename Modal Listeners
const chatActionsBtn = document.getElementById('chat-actions-btn');
if (chatActionsBtn) {
    chatActionsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleChatActionsMenu();
    });
}

const actionShareChat = document.getElementById('action-share-chat');
if (actionShareChat) actionShareChat.addEventListener('click', shareCurrentChat);

const actionFilesChat = document.getElementById('action-files-chat');
if (actionFilesChat) actionFilesChat.addEventListener('click', showChatFiles);

const actionPinChat = document.getElementById('action-pin-chat');
if (actionPinChat) actionPinChat.addEventListener('click', togglePinActiveSession);

const actionRenameChat = document.getElementById('action-rename-chat');
if (actionRenameChat) actionRenameChat.addEventListener('click', openRenameModal);

const actionPinnedMsgs = document.getElementById('action-pinned-msgs');
if (actionPinnedMsgs) {
    actionPinnedMsgs.addEventListener('click', () => {
        toggleChatActionsMenu(false);
        togglePinnedDrawer();
    });
}

const actionExportChat = document.getElementById('action-export-chat');
if (actionExportChat) actionExportChat.addEventListener('click', exportCurrentChat);

const actionSettingsChat = document.getElementById('action-settings-chat');
if (actionSettingsChat) {
    actionSettingsChat.addEventListener('click', () => {
        toggleChatActionsMenu(false);
        openSettings();
    });
}

const actionLangToggle = document.getElementById('action-lang-toggle');
if (actionLangToggle) {
    actionLangToggle.addEventListener('click', () => {
        toggleChatActionsMenu(false);
        toggleQuickLanguage();
    });
}

const actionPipelineChat = document.getElementById('action-pipeline-chat');
if (actionPipelineChat) {
    actionPipelineChat.addEventListener('click', () => {
        toggleChatActionsMenu(false);
        openPipelineModal();
    });
}

const actionDeleteChat = document.getElementById('action-delete-chat');
if (actionDeleteChat) {
    actionDeleteChat.addEventListener('click', () => {
        toggleChatActionsMenu(false);
        deleteCurrentSession();
    });
}

const closeRenameModalBtn = document.getElementById('close-rename-modal');
if (closeRenameModalBtn) closeRenameModalBtn.addEventListener('click', closeRenameModal);

const btnCancelRename = document.getElementById('btn-cancel-rename');
if (btnCancelRename) btnCancelRename.addEventListener('click', closeRenameModal);

const btnSaveRename = document.getElementById('btn-save-rename');
if (btnSaveRename) btnSaveRename.addEventListener('click', saveRenameSession);

const renameInput = document.getElementById('rename-input');
if (renameInput) {
    renameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            saveRenameSession();
        } else if (e.key === 'Escape') {
            closeRenameModal();
        }
    });
}

function adjustInputHeight() {
    if (!userInput) return;
    userInput.style.height = 'auto';
    const scrollH = userInput.scrollHeight;
    const targetH = Math.min(Math.max(scrollH, 24), 140);
    userInput.style.height = targetH + 'px';
}

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        if (e.shiftKey) {
            setTimeout(adjustInputHeight, 0);
            return;
        }
        e.preventDefault();
        sendMessage();
    }
});

userInput.addEventListener('input', () => {
    adjustInputHeight();
    updateComposerSendButton();
    clearTimeout(triggerTimer);
    startTriggerTimer();
});

resetBtn.addEventListener('click', resetMemory);

function decodeHtmlEntities(text) {
    const textarea = document.createElement('textarea');
    textarea.innerHTML = text;
    return textarea.value;
}

// Settings Modal Functions
const settingsModal = document.getElementById('settings-modal');
const settingsBtn = document.getElementById('settings-btn');
const closeSettingsBtn = document.getElementById('close-settings');

function openSettings(defaultTab) {
    settingsModal.classList.remove('hidden');
    if (typeof defaultTab === 'string' && defaultTab) {
        const targetBtn = document.querySelector(`#settings-modal .tab-btn[data-tab="${defaultTab}"]`);
        const targetPanel = document.getElementById(`${defaultTab}-tab`);
        if (targetBtn && targetPanel) {
            document.querySelectorAll('#settings-modal .tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('#settings-modal .tab-content').forEach(c => c.classList.remove('active'));
            targetBtn.classList.add('active');
            targetPanel.classList.add('active');
            if (defaultTab === 'api') loadApiKey();
        }
    }
    loadProfiles();
    loadModels();
    loadPrivacySettings();
    loadMoeSettings();
    loadAgentSettings();
    setTimeout(() => {
        initModalTabsScroll();
    }, 40);
}

function closeSettings() {
    settingsModal.classList.add('hidden');
}

async function loadProfiles() {
    try {
        const response = await fetch('/api/profile');
        const data = await response.json();
        
        userProfile = data.user;
        aiProfile = data.ai;
        
        if (data.user) {
            const userNameInput = document.getElementById('user-name');
            if (userNameInput) {
                userNameInput.value = data.user.name || 'Kakak';
            }
            const userDescInput = document.getElementById('user-desc');
            if (userDescInput) {
                userDescInput.value = data.user.description || '';
            }
            if (data.user.image) {
                const preview = document.getElementById('user-preview');
                if (preview) {
                    preview.innerHTML = `<img src="data:${data.user.image_mime};base64,${data.user.image}" alt="Profil Pengguna">`;
                }
            }
        }
        
        if (data.ai) {
            const aiNameInput = document.getElementById('ai-name');
            if (aiNameInput) {
                aiNameInput.value = data.ai.name || 'Shiro';
            }
            const aiDescInput = document.getElementById('ai-desc');
            if (aiDescInput) {
                aiDescInput.value = data.ai.description || '';
            }
            if (data.ai.image) {
                const preview = document.getElementById('ai-preview');
                if (preview) {
                    preview.innerHTML = `<img src="data:${data.ai.image_mime};base64,${data.ai.image}" alt="Profil Shiro">`;
                }
            }
        }
        updateTypingIndicatorAvatar();
    } catch (error) {
        console.error('Error loading profiles:', error);
    }
}

async function saveProfile(type) {
    const formData = new FormData();
    formData.append('type', type);
    
    if (type === 'user') {
        formData.append('name', document.getElementById('user-name').value);
        formData.append('description', document.getElementById('user-desc').value);
        const imageFile = document.getElementById('user-image').files[0];
        if (imageFile) {
            formData.append('image', imageFile);
            formData.append('image_mime', imageFile.type);
        }
    } else {
        formData.append('name', document.getElementById('ai-name').value);
        formData.append('description', document.getElementById('ai-desc').value);
        const imageFile = document.getElementById('ai-image').files[0];
        if (imageFile) {
            formData.append('image', imageFile);
            formData.append('image_mime', imageFile.type);
        }
    }
    
    try {
        const response = await fetch('/api/profile/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        if (data.success) {
            showToast(`Profil ${type === 'user' ? 'Anda' : 'Shiro'} disimpan.`);
            loadProfiles();
        }
    } catch (error) {
        console.error('Error saving profile:', error);
        showToast('Gagal menyimpan profil');
    }
}

document.querySelectorAll('#settings-modal .tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const tab = e.target.closest('.tab-btn').dataset.tab;
        
        document.querySelectorAll('#settings-modal .tab-btn').forEach(b => b.classList.remove('active'));
        e.target.closest('.tab-btn').classList.add('active');
        
        document.querySelectorAll('#settings-modal .tab-content').forEach(c => c.classList.remove('active'));
        document.getElementById(`${tab}-tab`).classList.add('active');

        if (tab === 'api') {
            loadApiKey();
        }
    });
});

async function loadApiKey() {
    const input = document.getElementById('active-api-key-input');
    if (!input) return;
    try {
        const res = await fetch('/api/key');
        if (res.ok) {
            const data = await res.json();
            input.value = data.api_key || '';
            const origin = window.location.origin;
            const elV1 = document.getElementById('endpoint-v1-url');
            const elV2 = document.getElementById('endpoint-v2-url');
            const elV3 = document.getElementById('endpoint-v3-url');
            if (elV1) elV1.textContent = `${origin}/v1`;
            if (elV2) elV2.textContent = `${origin}/v2`;
            if (elV3) elV3.textContent = `${origin}/v3`;
        }
    } catch (e) {
        console.error('Error loading API key:', e);
    }
}

function copyApiKey() {
    const input = document.getElementById('active-api-key-input');
    if (!input || !input.value) return;
    navigator.clipboard.writeText(input.value).then(() => {
        showToast('API Key berhasil disalin');
    }).catch(() => {
        input.select();
        document.execCommand('copy');
        showToast('API Key berhasil disalin');
    });
}

function copyEndpointUrl(path) {
    const fullUrl = window.location.origin + path;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(fullUrl).then(() => {
            showToast(`URL ${fullUrl} berhasil disalin`);
        }).catch(() => {
            fallbackCopyEndpoint(fullUrl);
        });
    } else {
        fallbackCopyEndpoint(fullUrl);
    }
}

function fallbackCopyEndpoint(fullUrl) {
    const tempInput = document.createElement('input');
    tempInput.value = fullUrl;
    document.body.appendChild(tempInput);
    tempInput.select();
    try {
        document.execCommand('copy');
        showToast(`URL ${fullUrl} berhasil disalin`);
    } catch (e) {
        showToast(`URL: ${fullUrl}`);
    }
    document.body.removeChild(tempInput);
}

async function regenerateApiKey() {
    const btn = document.getElementById('btn-regen-key');
    const input = document.getElementById('active-api-key-input');
    if (btn) btn.disabled = true;
    try {
        const res = await fetch('/api/key/regenerate', { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            if (input) input.value = data.api_key;
            showToast('API Key baru berhasil dibuat');
        } else {
            showToast('Gagal membuat API Key');
        }
    } catch (e) {
        console.error('Error regenerating API key:', e);
        showToast('Error: ' + e.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

const userImageEl = document.getElementById('user-image');
if (userImageEl) {
    userImageEl.addEventListener('change', (e) => {
        const file = e.target.files[0];
        const filenameEl = document.getElementById('user-image-filename');
        if (file) {
            if (filenameEl) {
                filenameEl.textContent = file.name;
                filenameEl.style.color = 'var(--text-primary)';
            }
            const reader = new FileReader();
            reader.onload = (event) => {
                const preview = document.getElementById('user-preview');
                if (preview) preview.innerHTML = `<img src="${event.target.result}" alt="Pratinjau Profil">`;
            };
            reader.readAsDataURL(file);
        } else {
            if (filenameEl) {
                filenameEl.textContent = t('no_file_chosen') || 'Belum ada berkas dipilih';
                filenameEl.style.color = 'var(--text-muted)';
            }
        }
    });
}

const aiImageEl = document.getElementById('ai-image');
if (aiImageEl) {
    aiImageEl.addEventListener('change', (e) => {
        const file = e.target.files[0];
        const filenameEl = document.getElementById('ai-image-filename');
        if (file) {
            if (filenameEl) {
                filenameEl.textContent = file.name;
                filenameEl.style.color = 'var(--text-primary)';
            }
            const reader = new FileReader();
            reader.onload = (event) => {
                const preview = document.getElementById('ai-preview');
                if (preview) preview.innerHTML = `<img src="${event.target.result}" alt="Pratinjau Avatar">`;
            };
            reader.readAsDataURL(file);
        } else {
            if (filenameEl) {
                filenameEl.textContent = t('no_file_chosen') || 'Belum ada berkas dipilih';
                filenameEl.style.color = 'var(--text-muted)';
            }
        }
    });
}

// --- Media & Real-Time Camera Management ---
const imageFileInput = document.getElementById('image-file-input');
const uploadImageBtn = document.getElementById('upload-image-btn');
const openCameraBtn = document.getElementById('open-camera-btn');
const imagePreviewBar = document.getElementById('image-preview-bar');
const imagePreviewThumb = document.getElementById('image-preview-thumb');
const imagePreviewName = document.getElementById('image-preview-name');
const removeImageBtn = document.getElementById('remove-image-btn');

const cameraModal = document.getElementById('camera-modal');
const closeCameraModalBtn = document.getElementById('close-camera-modal');
const cameraVideo = document.getElementById('camera-video');
const cameraCanvas = document.getElementById('camera-canvas');
const capturePhotoBtn = document.getElementById('capture-photo-btn');
const switchCameraBtn = document.getElementById('switch-camera-btn');
const cameraPlaceholder = document.getElementById('camera-placeholder');

let cameraStream = null;
let currentCameraFacing = 'user';

const MULTI_IMAGE_EXTS = new Set(['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff']);
const MULTI_VIDEO_EXTS = new Set(['.mp4', '.webm', '.mov', '.mkv', '.avi', '.flv', '.wmv', '.m4v', '.mpeg', '.mpg', '.gif']);

function getFileExtLower(filename) {
    const name = String(filename || '').toLowerCase();
    const dot = name.lastIndexOf('.');
    return dot >= 0 ? name.slice(dot) : '';
}

function isImageFileObj(file) {
    if (!file) return false;
    const ext = getFileExtLower(file.name);
    if (MULTI_IMAGE_EXTS.has(ext)) return true;
    const mime = String(file.type || '').toLowerCase();
    return mime.startsWith('image/') && ext !== '.gif';
}

function isVideoFileObj(file, preferVideo = false) {
    if (!file) return false;
    const ext = getFileExtLower(file.name);
    if (MULTI_VIDEO_EXTS.has(ext)) return true;
    const mime = String(file.type || '').toLowerCase();
    if (mime.startsWith('video/')) return true;
    return preferVideo && mime.startsWith('image/gif');
}

function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (ev) => resolve(ev.target.result);
        reader.onerror = () => reject(new Error(`Gagal membaca ${file.name}`));
        reader.readAsDataURL(file);
    });
}

function renderAttachmentChipList(barEl, items, kind) {
    if (!barEl) return;
    const uploadingItems = pendingUploads.filter((u) => u.kind === kind);
    const hasItems = Array.isArray(items) && items.length > 0;
    if (!hasItems && uploadingItems.length === 0) {
        barEl.classList.add('hidden');
        barEl.innerHTML = '';
        return;
    }

    barEl.classList.remove('hidden');
    barEl.innerHTML = '';

    const strip = document.createElement('div');
    strip.className = 'multi-attach-strip';

    uploadingItems.forEach((uItem) => {
        const chip = document.createElement('div');
        chip.className = `attach-chip attach-chip-${kind} is-uploading`;

        const icon = document.createElement('span');
        icon.className = 'attach-chip-icon';
        icon.innerHTML = '<span class="ag-spinner-ring" aria-hidden="true"></span>';
        chip.appendChild(icon);

        const info = document.createElement('div');
        info.className = 'attach-chip-info';

        const title = document.createElement('span');
        title.className = 'attach-chip-name';
        title.textContent = uItem.name || 'file';
        title.title = title.textContent;
        info.appendChild(title);

        const sub = document.createElement('span');
        sub.className = 'attach-chip-sub';
        sub.textContent = uItem.kind === 'video'
            ? t('uploading_video')
            : (uItem.kind === 'image' ? t('uploading_image') : t('uploading_file'));
        info.appendChild(sub);
        chip.appendChild(info);

        const bar = document.createElement('div');
        bar.className = 'attach-upload-progress';
        chip.appendChild(bar);
        strip.appendChild(chip);
    });

    (items || []).forEach((item, idx) => {
        const chip = document.createElement('div');
        const playUrl = kind === 'video' ? (item.blobUrl || item.url || '') : (kind === 'image' ? (item.dataUrl || '') : '');
        const isPlayable = Boolean(playUrl && (kind === 'video' || kind === 'image'));
        chip.className = `attach-chip attach-chip-${kind}${isPlayable ? ' is-clickable' : ''}`;
        if (kind === 'video' && playUrl) {
            chip.title = t('click_to_play_video');
            chip.addEventListener('click', () => openVideoLightbox(playUrl, item.filename || item.name || t('video_preview')));
        } else if (kind === 'image' && item.dataUrl) {
            chip.addEventListener('click', () => openImageLightbox(item.dataUrl, item.name || t('image_preview')));
        }

        if (kind === 'image' && item.dataUrl) {
            const thumb = document.createElement('img');
            thumb.className = 'attach-chip-thumb';
            thumb.src = item.dataUrl;
            thumb.alt = item.name || `image-${idx + 1}`;
            chip.appendChild(thumb);
        } else {
            const icon = document.createElement('span');
            icon.className = 'attach-chip-icon';
            icon.innerHTML = kind === 'video'
                ? '<i class="ph-fill ph-play-circle"></i>'
                : '<i class="ph-fill ph-file-text"></i>';
            chip.appendChild(icon);
        }

        const info = document.createElement('div');
        info.className = 'attach-chip-info';

        const title = document.createElement('span');
        title.className = 'attach-chip-name';
        title.textContent = item.filename || item.name || `${kind}-${idx + 1}`;
        title.title = title.textContent;
        info.appendChild(title);

        const sub = document.createElement('span');
        sub.className = 'attach-chip-sub';
        if (kind === 'document') {
            const chars = item.char_count || (item.text ? item.text.length : 0);
            const ftype = item.file_type ? String(item.file_type).toUpperCase() : 'FILE';
            sub.textContent = `${ftype} · ${chars} chars`;
        } else if (kind === 'video') {
            const extLabel = getFileExtLower(item.filename || item.name || '').replace('.', '').toUpperCase();
            const dur = item.duration_sec ? `${Number(item.duration_sec).toFixed(1)}s` : '';
            const res = item.resolution || '';
            sub.textContent = [extLabel, dur, res].filter(Boolean).join(' · ') || t('video_ready_sub');
        } else {
            sub.textContent = t('image_ready_sub');
        }
        info.appendChild(sub);
        chip.appendChild(info);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'attach-chip-remove';
        removeBtn.title = currentLang === 'en' ? 'Remove attachment' : 'Hapus lampiran';
        removeBtn.textContent = '×';
        removeBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            if (kind === 'image') removeAttachedImage(idx);
            else if (kind === 'document') removeAttachedDocument(idx);
            else if (kind === 'video') removeAttachedVideo(idx);
        });
        chip.appendChild(removeBtn);

        strip.appendChild(chip);
    });

    if ((items || []).length > 1) {
        const clearBtn = document.createElement('button');
        clearBtn.type = 'button';
        clearBtn.className = 'attach-clear-all-btn';
        clearBtn.textContent = currentLang === 'en' ? `Clear all (${items.length})` : `Hapus semua (${items.length})`;
        clearBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            if (kind === 'image') clearAttachedImage();
            else if (kind === 'document') clearAttachedDocument();
            else if (kind === 'video') clearAttachedVideo();
        });
        strip.appendChild(clearBtn);
    }

    barEl.appendChild(strip);
}

function renderAttachmentPreviewBars() {
    renderAttachmentChipList(imagePreviewBar, attachedImages, 'image');
    renderAttachmentChipList(docPreviewBar, attachedDocuments, 'document');
    renderAttachmentChipList(document.getElementById('video-preview-bar'), attachedVideos, 'video');
    updateComposerSendButton();
}

function setAttachedImage(dataUrl, name = 'visual_input.jpg') {
    if (!dataUrl) return;
    const exists = attachedImages.some((img) => img.dataUrl === dataUrl && img.name === name);
    if (!exists) {
        attachedImages.push({ dataUrl, name });
    }
    attachedImage = attachedImages[0] || null;
    renderAttachmentPreviewBars();
}

function removeAttachedImage(index) {
    if (index < 0 || index >= attachedImages.length) return;
    attachedImages.splice(index, 1);
    attachedImage = attachedImages[0] || null;
    if (attachedImages.length === 0 && imageFileInput) imageFileInput.value = '';
    renderAttachmentPreviewBars();
}

function clearAttachedImage() {
    attachedImages = [];
    attachedImage = null;
    if (imagePreviewThumb) imagePreviewThumb.src = '';
    if (imageFileInput) imageFileInput.value = '';
    renderAttachmentPreviewBars();
}

if (removeImageBtn) {
    removeImageBtn.addEventListener('click', clearAttachedImage);
}

// --- Document Management & Multi-File Extraction ---
function setAttachedDocument(docData) {
    if (!docData) return;
    const fname = docData.filename || 'document.txt';
    const existingIdx = attachedDocuments.findIndex((d) => d.filename === fname);
    if (existingIdx >= 0) {
        attachedDocuments[existingIdx] = docData;
    } else {
        attachedDocuments.push(docData);
    }
    attachedDocument = attachedDocuments[0] || null;
    renderAttachmentPreviewBars();
    if (userInput && !userInput.value.trim()) {
        userInput.placeholder = currentLang === 'en'
            ? "Describe what to analyze or fix across all uploaded files..."
            : "Ketik perintah (Shiro akan membaca semua berkas & merancang rencana sebelum memperbaiki)...";
    }
}

function removeAttachedDocument(index) {
    if (index < 0 || index >= attachedDocuments.length) return;
    attachedDocuments.splice(index, 1);
    attachedDocument = attachedDocuments[0] || null;
    if (attachedDocuments.length === 0) {
        if (docFileInput) docFileInput.value = '';
        if (userInput) userInput.placeholder = t('input_placeholder');
    }
    renderAttachmentPreviewBars();
}

function clearAttachedDocument() {
    attachedDocuments = [];
    attachedDocument = null;
    if (docFileInput) docFileInput.value = '';
    if (userInput) userInput.placeholder = t('input_placeholder');
    renderAttachmentPreviewBars();
}

function setAttachedVideo(videoData) {
    if (!videoData) return;
    const fname = videoData.filename || 'video.mp4';
    const existingIdx = attachedVideos.findIndex((v) => v.filename === fname);
    if (existingIdx >= 0) {
        attachedVideos[existingIdx] = videoData;
    } else {
        attachedVideos.push(videoData);
    }
    renderAttachmentPreviewBars();
    if (userInput && !userInput.value.trim()) {
        userInput.placeholder = currentLang === 'en'
            ? "Ask Shiro to analyze the video alongside your files..."
            : "Tanyakan analisis isi video atau bandingkan dengan kode yang diunggah...";
    }
}

function removeAttachedVideo(index) {
    if (index < 0 || index >= attachedVideos.length) return;
    attachedVideos.splice(index, 1);
    renderAttachmentPreviewBars();
}

function clearAttachedVideo() {
    attachedVideos = [];
    renderAttachmentPreviewBars();
}

async function uploadMixedFiles(fileList, { preferVideo = false } = {}) {
    const files = Array.from(fileList || []).filter(Boolean);
    if (files.length === 0) return;

    const uploadTaskPromise = (async () => {
        inFlightUploadsCount += 1;
        updateComposerSendButton();
        const localImages = [];
        const serverFiles = [];
        const localVideoBlobMap = new Map();
        const taskPendingEntries = [];

        for (const file of files) {
            const isImg = !preferVideo && isImageFileObj(file);
            const isVid = isVideoFileObj(file, preferVideo);
            const pKind = isImg ? 'image' : (isVid ? 'video' : 'document');
            const pEntry = {
                id: `${Date.now()}_${Math.random()}`,
                name: file.name,
                kind: pKind,
            };
            taskPendingEntries.push(pEntry);
            pendingUploads.push(pEntry);
            if (isImg) {
                localImages.push({ file, pendingEntry: pEntry });
            } else {
                if (isVid && typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function') {
                    try {
                        localVideoBlobMap.set(file.name, URL.createObjectURL(file));
                    } catch (_) {}
                }
                serverFiles.push(file);
            }
        }
        renderAttachmentPreviewBars();

        const removePendingEntry = (entry) => {
            const pIdx = pendingUploads.indexOf(entry);
            if (pIdx >= 0) pendingUploads.splice(pIdx, 1);
        };

        try {
            if (localImages.length > 0) {
                status.textContent = currentLang === 'en'
                    ? `Loading ${localImages.length} image(s)...`
                    : `Memuat ${localImages.length} gambar...`;
                for (const { file: imgFile, pendingEntry } of localImages) {
                    try {
                        const dataUrl = await readFileAsDataUrl(imgFile);
                        removePendingEntry(pendingEntry);
                        setAttachedImage(dataUrl, imgFile.name);
                    } catch (err) {
                        removePendingEntry(pendingEntry);
                        renderAttachmentPreviewBars();
                        console.error('Image read error:', err);
                        showToast(`${imgFile.name}: ${err.message || 'Gagal membaca gambar'}`);
                    }
                }
            }

            if (serverFiles.length > 0) {
                const formData = new FormData();
                serverFiles.forEach((file) => formData.append('files', file));

                const hasVideo = serverFiles.some((f) => isVideoFileObj(f, preferVideo));
                status.textContent = hasVideo
                    ? (currentLang === 'en' ? `Uploading video & files (${serverFiles.length})...` : `Mengunggah video & ${serverFiles.length} berkas...`)
                    : (currentLang === 'en' ? `Uploading ${serverFiles.length} file(s)...` : `Mengunggah ${serverFiles.length} berkas...`);

                try {
                    const res = await fetch('/api/upload/documents', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    taskPendingEntries.forEach(removePendingEntry);
                    if (data.success) {
                        (data.documents || []).forEach((doc) => setAttachedDocument(doc));
                        (data.images || []).forEach((img) => {
                            if (img && (img.dataUrl || img.data_url)) {
                                setAttachedImage(img.dataUrl || img.data_url, img.name || img.filename || 'image.png');
                            }
                        });
                        (data.videos || []).forEach((vid) => {
                            const blobUrl = localVideoBlobMap.get(vid.filename);
                            if (blobUrl) vid.blobUrl = blobUrl;
                            setAttachedVideo(vid);
                        });
                        if (Array.isArray(data.errors) && data.errors.length > 0) {
                            const previewErr = data.errors.slice(0, 2).join('; ');
                            showToast((currentLang === 'en' ? 'Some files could not be read: ' : 'Sebagian berkas gagal dibaca: ') + previewErr);
                        }
                    } else {
                        renderAttachmentPreviewBars();
                        showToast(`${currentLang === 'en' ? 'Upload failed' : 'Gagal mengunggah berkas'}: ${data.error || 'Format tidak didukung'}`);
                    }
                } catch (err) {
                    taskPendingEntries.forEach(removePendingEntry);
                    renderAttachmentPreviewBars();
                    console.error('Multi-file upload error:', err);
                    showToast((currentLang === 'en' ? 'Failed to upload files: ' : 'Gagal mengunggah berkas: ') + (err.message || 'Koneksi bermasalah'));
                }
            }
        } finally {
            taskPendingEntries.forEach(removePendingEntry);
            inFlightUploadsCount = Math.max(0, inFlightUploadsCount - 1);
            renderAttachmentPreviewBars();
            const totalCount = attachedDocuments.length + attachedImages.length + attachedVideos.length;
            if (!isActiveSessionGenerating() && status) {
                status.textContent = totalCount > 0
                    ? (currentLang === 'en' ? `${totalCount} attachment(s) ready` : `${totalCount} lampiran siap`)
                    : t('status_ready');
            }
            updateComposerSendButton();
        }
    })();

    activeUploadPromises.push(uploadTaskPromise);
    try {
        await uploadTaskPromise;
    } finally {
        const idxP = activeUploadPromises.indexOf(uploadTaskPromise);
        if (idxP >= 0) activeUploadPromises.splice(idxP, 1);
    }
}

async function uploadDocumentFile(file) {
    if (!file) return;
    await uploadMixedFiles([file]);
}

if (uploadDocBtn && docFileInput) {
    uploadDocBtn.addEventListener('click', () => {
        docFileInput.click();
    });

    docFileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files && files.length > 0) {
            uploadMixedFiles(files).finally(() => {
                docFileInput.value = '';
            });
        }
    });
}

if (removeDocBtn) {
    removeDocBtn.addEventListener('click', clearAttachedDocument);
}

// --- Auto-Convert Pasted Code/Text to Document Attachment & Clipboard Image Paste ---
function detectPastedSnippetMeta(text) {
    const trimmed = text.trim();
    const lower = trimmed.toLowerCase();
    
    if (lower.startsWith('<!doctype html') || lower.startsWith('<html') || 
        (lower.includes('<div') && lower.includes('</div>')) || 
        (lower.includes('<body') && lower.includes('</body>')) ||
        (lower.includes('<head') && lower.includes('</head>'))) {
        return { filename: 'snippet.html', ext: 'html' };
    }
    if (lower.startsWith('<svg') || (lower.includes('<svg') && lower.includes('</svg>'))) {
        return { filename: 'image.svg', ext: 'svg' };
    }
    if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
        try {
            JSON.parse(trimmed);
            return { filename: 'data.json', ext: 'json' };
        } catch (_) {}
    }
    if (/^\s*(#include\s+<[\w.]+>|int\s+main\s*\()/m.test(trimmed)) {
        return { filename: 'main.cpp', ext: 'cpp' };
    }
    if (/^\s*(package\s+main|func\s+\w+\s*\(|import\s+\()/m.test(trimmed)) {
        return { filename: 'main.go', ext: 'go' };
    }
    if (/^\s*(fn\s+main\s*\(|use\s+std::|pub\s+struct\s+\w+|impl\s+\w+)/m.test(trimmed)) {
        return { filename: 'main.rs', ext: 'rs' };
    }
    if (/^\s*(public\s+class\s+\w+|public\s+static\s+void\s+main)/m.test(trimmed)) {
        return { filename: 'Main.java', ext: 'java' };
    }
    if (/^\s*(<\?php|namespace\s+[\w\\]+;)/m.test(trimmed)) {
        return { filename: 'script.php', ext: 'php' };
    }
    if (/^\s*(interface\s+\w+\s*\{|type\s+\w+\s*=|export\s+interface\s+\w+)/m.test(trimmed)) {
        return { filename: 'module.ts', ext: 'ts' };
    }
    if (/^\s*(import\s+\w+|from\s+\w+\s+import|def\s+\w+\s*\(|class\s+\w+[\s:(]|if\s+__name__\s*==\s*['"]__main__['"])/m.test(trimmed)) {
        return { filename: 'script.py', ext: 'py' };
    }
    if (/^\s*([.#][\w-]+\s*\{|@media|@keyframes|:root\s*\{)/m.test(trimmed) && trimmed.includes('{') && trimmed.includes('}')) {
        return { filename: 'style.css', ext: 'css' };
    }
    if (/^\s*(const\s+\w+\s*=|let\s+\w+\s*=|var\s+\w+\s*=|function\s+\w*\s*\(|console\.(log|error|warn)\(|export\s+(default\s+)?(function|class|const))/m.test(trimmed) || /=>\s*\{/.test(trimmed)) {
        return { filename: 'script.js', ext: 'js' };
    }
    if (/^\s*(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE)\s+/i.test(trimmed)) {
        return { filename: 'query.sql', ext: 'sql' };
    }
    if (/^#+\s+.+/m.test(trimmed) || (trimmed.includes('```') && trimmed.includes('\n'))) {
        return { filename: 'document.md', ext: 'md' };
    }
    return { filename: 'pasted-text.txt', ext: 'txt' };
}

function handleLongPaste(text) {
    const meta = detectPastedSnippetMeta(text);
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    
    setAttachedDocument({
        filename: meta.filename,
        text: text,
        file_type: meta.ext,
        char_count: text.length,
        url: url
    });

    status.textContent = `Teks ${text.length.toLocaleString()} karakter otomatis dijadikan lampiran (${meta.filename}).`;
    setTimeout(() => {
        if (!isActiveSessionGenerating() && status && status.textContent.includes('otomatis dijadikan lampiran')) {
            status.textContent = 'Siap';
        }
    }, 4000);
}

if (userInput) {
    userInput.addEventListener('paste', (e) => {
        const items = (e.clipboardData || window.clipboardData)?.items;
        if (items) {
            for (let i = 0; i < items.length; i++) {
                if (items[i].type && items[i].type.indexOf('image') !== -1) {
                    const blob = items[i].getAsFile();
                    if (blob) {
                        e.preventDefault();
                        const reader = new FileReader();
                        reader.onload = (event) => {
                            setAttachedImage(event.target.result, `clipboard_image_${Date.now()}.png`);
                            status.textContent = 'Gambar dari clipboard berhasil dilampirkan.';
                        };
                        reader.readAsDataURL(blob);
                        return;
                    }
                }
            }
        }

        const pastedText = (e.clipboardData || window.clipboardData)?.getData('text');
        if (pastedText) {
            const lineCount = pastedText.split('\n').length;
            if (pastedText.length >= 1200 || (lineCount >= 25 && pastedText.length >= 400)) {
                e.preventDefault();
                handleLongPaste(pastedText);
            }
        }
    });
}

if (uploadImageBtn && imageFileInput) {
    uploadImageBtn.addEventListener('click', () => {
        imageFileInput.click();
    });

    imageFileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files && files.length > 0) {
            uploadMixedFiles(files).finally(() => {
                imageFileInput.value = '';
            });
        }
    });
}

// Drag & Drop multi-file / image / video upload support (aktif juga saat Shiro sedang bekerja)
const composerInputCard = document.getElementById('composer-input-card');
[composerInputCard, chatViewport].filter(Boolean).forEach((dropZone) => {
    let dragCounter = 0;
    dropZone.addEventListener('dragenter', (e) => {
        if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) {
            e.preventDefault();
            dragCounter += 1;
            if (composerInputCard) composerInputCard.classList.add('is-drag-over');
        }
    });
    dropZone.addEventListener('dragover', (e) => {
        if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
            if (composerInputCard) composerInputCard.classList.add('is-drag-over');
        }
    });
    dropZone.addEventListener('dragleave', (e) => {
        if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) {
            dragCounter = Math.max(0, dragCounter - 1);
            if (dragCounter === 0 && composerInputCard) {
                composerInputCard.classList.remove('is-drag-over');
            }
        }
    });
    dropZone.addEventListener('drop', (e) => {
        dragCounter = 0;
        if (composerInputCard) composerInputCard.classList.remove('is-drag-over');
        const files = e.dataTransfer && e.dataTransfer.files;
        if (files && files.length > 0) {
            e.preventDefault();
            uploadMixedFiles(files);
        }
    });
});

// Camera handlers
async function startCamera() {
    if (cameraStream) {
        stopCamera();
    }
    
    if (cameraModal) cameraModal.classList.remove('hidden');
    if (cameraPlaceholder) cameraPlaceholder.classList.remove('hidden');
    if (cameraVideo) cameraVideo.classList.add('hidden');
    
    try {
        const constraints = {
            video: {
                facingMode: currentCameraFacing,
                width: { ideal: 1280 },
                height: { ideal: 720 }
            },
            audio: false
        };
        cameraStream = await navigator.mediaDevices.getUserMedia(constraints);
        if (cameraVideo) {
            cameraVideo.srcObject = cameraStream;
            cameraVideo.classList.remove('hidden');
            if (cameraPlaceholder) cameraPlaceholder.classList.add('hidden');
        }
    } catch (err) {
        console.error("Camera access error:", err);
        showToast("Tidak dapat mengakses kamera: " + (err.message || "Izin kamera ditolak."));
        closeCamera();
    }
}

function stopCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
    }
    if (cameraVideo) {
        cameraVideo.srcObject = null;
    }
}

function closeCamera() {
    stopCamera();
    if (cameraModal) cameraModal.classList.add('hidden');
}

if (openCameraBtn) openCameraBtn.addEventListener('click', () => {
    startCamera();
});
if (closeCameraModalBtn) closeCameraModalBtn.addEventListener('click', closeCamera);

if (switchCameraBtn) {
    switchCameraBtn.addEventListener('click', () => {
        currentCameraFacing = currentCameraFacing === 'user' ? 'environment' : 'user';
        startCamera();
    });
}

if (capturePhotoBtn && cameraVideo && cameraCanvas) {
    capturePhotoBtn.addEventListener('click', () => {
        if (!cameraStream) return;
        const video = cameraVideo;
        const canvas = cameraCanvas;
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        setAttachedImage(dataUrl, `kamera_${new Date().toISOString().slice(11,19).replace(/:/g,'-')}.jpg`);
        closeCamera();
    });
}

function syncLyraTierUI(enabled, tierId = null) {
    isLyraActive = Boolean(enabled);
    if (tierId && LYRA_TIER_LABELS[tierId]) {
        activeLyraTier = tierId;
    }

    const picker = document.getElementById('lyra-tier-picker');
    const btn = document.getElementById('lyra-tier-btn');
    const labelEl = document.getElementById('lyra-tier-current-label');
    if (picker) {
        picker.classList.toggle('hidden', !isLyraActive);
    }
    if (btn) {
        btn.disabled = Boolean(isAnySessionRunning());
        btn.classList.remove('is-loading');
    }
    if (labelEl) {
        labelEl.textContent = LYRA_TIER_LABELS[activeLyraTier] || LYRA_TIER_LABELS.high;
    }
    document.querySelectorAll('#lyra-tier-menu .lyra-tier-option').forEach((opt) => {
        const isSel = opt.dataset.tier === activeLyraTier;
        opt.classList.toggle('active', isSel);
        opt.setAttribute('aria-selected', isSel ? 'true' : 'false');
    });
    if (!isLyraActive) {
        toggleLyraTierMenu(false);
    }
}

function toggleLyraTierMenu(forceState = null) {
    const menu = document.getElementById('lyra-tier-menu');
    const btn = document.getElementById('lyra-tier-btn');
    if (!menu || !btn) return;
    const isCurrentlyOpen = !menu.classList.contains('hidden');
    const shouldOpen = typeof forceState === 'boolean' ? forceState : !isCurrentlyOpen;
    menu.classList.toggle('hidden', !shouldOpen);
    btn.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
}

function selectLyraTier(tierId) {
    if (!tierId || !LYRA_TIER_LABELS[tierId]) return;
    if (isAnySessionRunning()) {
        showToast(currentLang === 'en' ? 'Wait until active session finishes' : 'Tunggu hingga sesi yang sedang berjalan selesai');
        toggleLyraTierMenu(false);
        return;
    }

    toggleLyraTierMenu(false);
    const changed = tierId !== activeLyraTier;
    activeLyraTier = tierId;
    try {
        localStorage.setItem('shiro_lyra_tier', tierId);
    } catch (_) {}
    syncLyraTierUI(true, tierId);

    if (changed) {
        showToast(`Mode dipilih: ${LYRA_TIER_LABELS[tierId]}`);
    }

    // Simpan preferensi secara non-blocking di background tanpa mengunci tombol
    fetch('/api/models/context-tier', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tier: tierId, defer_reload: true })
    }).catch((err) => {
        console.warn('[Lyra Tier] Background sync failed:', err);
    });
}

function initLyraTierPicker() {
    const picker = document.getElementById('lyra-tier-picker');
    const btn = document.getElementById('lyra-tier-btn');
    if (!picker || !btn || picker.dataset.bound === '1') return;
    picker.dataset.bound = '1';

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (btn.disabled) return;
        toggleLyraTierMenu();
    });

    picker.querySelectorAll('.lyra-tier-option').forEach((opt) => {
        opt.addEventListener('click', (e) => {
            e.stopPropagation();
            selectLyraTier(opt.dataset.tier);
        });
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('#lyra-tier-picker')) {
            toggleLyraTierMenu(false);
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            toggleLyraTierMenu(false);
        }
    });
}

// Load models for dropdown
async function loadModels() {
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        
        const badge = document.getElementById('current-model-badge');
        const navPill = document.querySelector('.model-pill');
        if (data.current_model) {
            const modelName = data.current_model_display_name || getModelDisplayName(data.current_model, data.model_info);
            if (badge) badge.textContent = modelName;
            if (navPill) navPill.textContent = modelName;
        }
        
        const select = document.getElementById('model-select');
        const modelDescText = document.getElementById('model-desc-text');
        
        if (select) {
            select.innerHTML = '';
            
            // Opsi Auto-Detect: Otomatis memilih model terbaik tanpa terikat default kaku
            const autoOpt = document.createElement('option');
            autoOpt.value = 'auto';
            autoOpt.textContent = '⚡ Auto-Detect (Otomatis Deteksi)';
            if (data.current_model === 'auto') {
                autoOpt.selected = true;
                if (modelDescText) {
                    modelDescText.textContent = 'Mode Auto-Detect: Shiro akan secara otomatis mendeteksi dan memilih model terbaik di folder model/.';
                }
            }
            select.appendChild(autoOpt);

            if (!data.available_models || data.available_models.length === 0) {
                const option = document.createElement('option');
                option.textContent = 'Tidak ada model ditemukan di folder model/';
                option.disabled = true;
                select.appendChild(option);
            } else {
                data.available_models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    const info = data.model_info?.[model] || {};
                    const displayName = getModelDisplayName(model, data.model_info);
                    const sizeStr = info.size ? ` (${info.size})` : '';
                    option.textContent = `${displayName}${sizeStr}`;
                    
                    if (model === data.current_model) {
                        option.selected = true;
                        if (modelDescText) {
                            modelDescText.textContent = info.description || `Model aktif: ${displayName}`;
                        }
                    }
                    select.appendChild(option);
                });
            }
            
            select.onchange = () => {
                const sel = select.value;
                if (sel === 'auto') {
                    if (modelDescText) {
                        modelDescText.textContent = 'Mode Auto-Detect: Otomatis mendeteksi dan memilih model terbaik di folder model/.';
                    }
                    return;
                }
                const info = data.model_info?.[sel] || {};
                if (modelDescText) {
                    modelDescText.textContent = info.description || `Model terpilih: ${getModelDisplayName(sel, data.model_info)}`;
                }
            };
        }

        const lyraEnabled = typeof data.is_lyra_active === 'boolean'
            ? data.is_lyra_active
            : isQwen38UncensoredPath(data.current_model);
        let resolvedTier = data.lyra_tier;
        if (!resolvedTier || !LYRA_TIER_LABELS[resolvedTier]) {
            try {
                resolvedTier = localStorage.getItem('shiro_lyra_tier') || activeLyraTier;
            } catch (_) {
                resolvedTier = activeLyraTier;
            }
        }
        syncLyraTierUI(lyraEnabled, resolvedTier);

        loadMoeSettings();
    } catch (error) {
        console.error('Error loading models:', error);
        const badge = document.getElementById('current-model-badge');
        if (badge) {
            badge.textContent = 'Gagal memuat';
        }
    }
}

async function loadMoeSettings() {
    try {
        const res = await fetch('/api/moe');
        if (!res.ok) return;
        const data = await res.json();
        const select = document.getElementById('moe-mode-select');
        const desc = document.getElementById('moe-desc-text');
        if (select && data.mode) {
            select.value = data.mode;
        }
        if (desc) {
            const expertName = data.vision_expert_path ? data.vision_expert_path.split('/').pop().replace('.gguf', '') : 'Belum terdeteksi di folder model/';
            const loadedBadge = data.vision_expert_loaded ? ' (Dimuat di VRAM)' : ' (Standby)';
            desc.innerHTML = `<strong>Mode:</strong> <code>${data.mode}</code> · Visual Expert: <strong>${expertName}</strong>${data.vision_expert_loaded ? loadedBadge : ''}`;
        }
    } catch (e) {
        console.error('Error loading MoE settings:', e);
    }
}

async function saveMoeSettings() {
    const select = document.getElementById('moe-mode-select');
    if (!select) return;
    const mode = select.value;
    try {
        const res = await fetch('/api/moe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
        const data = await res.json();
        if (res.ok && (data.success || data.mode)) {
            const modeName = data.mode || mode;
            showToast(currentLang === 'en' ? `Vision MoE mode saved: ${modeName}` : `Mode MoE berhasil disimpan: ${modeName}`);
            loadMoeSettings();
        } else {
            showToast((currentLang === 'en' ? 'Failed to save MoE: ' : 'Gagal menyimpan MoE: ') + (data.error || 'Unknown error'));
        }
    } catch (e) {
        showToast(`Error: ${e.message}`);
    }
}

async function switchModel() {
    const select = document.getElementById('model-select');
    const selectedModel = select.value;
    
    if (!selectedModel) {
        showToast('Silakan pilih model terlebih dahulu');
        return;
    }
    
    const modelName = getModelDisplayName(selectedModel);
    const status = document.getElementById('status');
    status.textContent = 'Sedang memuat model...';
    
    try {
        const response = await fetch('/api/models/switch', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ model: selectedModel })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const shownName = data.display_name || modelName;
            const visionTag = data.has_vision ? ' (Vision Aktif)' : '';
            showToast(`Model berhasil dialihkan ke ${shownName}${visionTag}`);
            status.textContent = 'Model berhasil dialihkan';
            
            setTimeout(() => {
                loadModels();
                if (!isActiveSessionGenerating() && status) {
                    status.textContent = 'Siap';
                }
            }, 600);
        } else {
            showToast(`Error: ${data.error}`);
            status.textContent = 'Gagal beralih model';
        }
    } catch (error) {
        console.error('Error switching model:', error);
        showToast(`Error: ${error.message}`);
        status.textContent = 'Error';
    }
}

settingsBtn.addEventListener('click', openSettings);
closeSettingsBtn.addEventListener('click', closeSettings);
settingsModal.addEventListener('click', (e) => {
    if (e.target === settingsModal) closeSettings();
});

// --- Neural Workflow Modal (Real-Time Pipeline Inspector) ---
const pipelineBtn = document.getElementById('pipeline-btn');
const pipelineModal = document.getElementById('pipeline-modal');
const closePipelineModalBtn = document.getElementById('close-pipeline-modal');
const pipelineNavDot = document.getElementById('pipeline-nav-dot');
const pipelineTotalTime = document.getElementById('pipeline-total-time');
const pipelineFrame = document.getElementById('pipeline-frame');

let activePipelineTrace = null;
let pipelineFrameReady = false;
let pipelineSimTimers = [];

function postTraceToFrame() {
    if (!pipelineFrame || !pipelineFrameReady || !activePipelineTrace) return;
    try {
        pipelineFrame.contentWindow.postMessage(
            { type: 'shiro:trace', trace: activePipelineTrace },
            window.location.origin
        );
    } catch (e) {
        console.warn('Gagal mengirim trace ke editor:', e);
    }
}

if (pipelineFrame) {
    pipelineFrame.addEventListener('load', () => {
        pipelineFrameReady = true;
        postTraceToFrame();
    });
}

function clearPipelineSimulation() {
    pipelineSimTimers.forEach(t => clearTimeout(t));
    pipelineSimTimers = [];
}

function startPipelineAnimation(userInputText) {
    clearPipelineSimulation();
    
    // Palet warna node kalem dan bebas warna ungu terang
    activePipelineTrace = {
        total_duration_ms: 0,
        nodes: [
            { id: "node_input", name: "Input Ingestion", type: "trigger", icon: "ph-chat-circle-dots", color: "#6488a8", status: "running", duration_ms: 0, summary: "Menerima input chat...", data_in: { message: userInputText }, data_out: {} },
            { id: "node_emotion", name: "Emotion & Tone Classifier", type: "analyzer", icon: "ph-heartbeat", color: "#b87366", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_memory", name: "Cognitive Memory & RDF Retrieval", type: "database", icon: "ph-brain", color: "#788896", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_prompt", name: "Dynamic Prompt Synthesizer", type: "transform", icon: "ph-brackets-curly", color: "#569499", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_llm", name: "Neural Inference Engine", type: "ai_model", icon: "ph-cpu", color: "#c8913b", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_filter", name: "Anti-Hallucination & CoT Filter", type: "filter", icon: "ph-shield-check", color: "#4d9e78", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_state", name: "State & Persistence Sync", type: "persistence", icon: "ph-database", color: "#6e7f91", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_output", name: "Response Delivery Stream", type: "output", icon: "ph-paper-plane-right", color: "#6488a8", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} }
        ]
    };
    renderModalPipeline(activePipelineTrace);

    pipelineSimTimers.push(setTimeout(() => {
        if (!activePipelineTrace || !activePipelineTrace.nodes) return;
        activePipelineTrace.nodes[0].status = 'success';
        activePipelineTrace.nodes[0].duration_ms = 14;
        activePipelineTrace.nodes[0].summary = `${(userInputText || '').length} Karakter`;
        activePipelineTrace.nodes[1].status = 'running';
        activePipelineTrace.nodes[1].summary = 'Menganalisis emosi & tone...';
        renderModalPipeline(activePipelineTrace);
    }, 120));

    pipelineSimTimers.push(setTimeout(() => {
        if (!activePipelineTrace || !activePipelineTrace.nodes) return;
        activePipelineTrace.nodes[1].status = 'success';
        activePipelineTrace.nodes[1].duration_ms = 10;
        activePipelineTrace.nodes[1].summary = 'Tone terklasifikasi';
        activePipelineTrace.nodes[2].status = 'running';
        activePipelineTrace.nodes[2].summary = 'Mengambil memori...';
        renderModalPipeline(activePipelineTrace);
    }, 280));

    pipelineSimTimers.push(setTimeout(() => {
        if (!activePipelineTrace || !activePipelineTrace.nodes) return;
        activePipelineTrace.nodes[2].status = 'success';
        activePipelineTrace.nodes[2].duration_ms = 28;
        activePipelineTrace.nodes[2].summary = 'Memori dimuat';
        activePipelineTrace.nodes[3].status = 'running';
        activePipelineTrace.nodes[3].summary = 'Menyusun prompt...';
        renderModalPipeline(activePipelineTrace);
    }, 480));

    pipelineSimTimers.push(setTimeout(() => {
        if (!activePipelineTrace || !activePipelineTrace.nodes) return;
        activePipelineTrace.nodes[3].status = 'success';
        activePipelineTrace.nodes[3].duration_ms = 18;
        activePipelineTrace.nodes[3].summary = 'Prompt siap';
        activePipelineTrace.nodes[4].status = 'running';
        activePipelineTrace.nodes[4].summary = 'Inferensi model...';
        renderModalPipeline(activePipelineTrace);
    }, 700));
}

function openPipelineModal() {
    if (!pipelineModal) return;
    pipelineModal.classList.remove('hidden');
    if (pipelineFrame && !pipelineFrame.getAttribute('src')) {
        pipelineFrame.src = '/pipeline?embed=1';
    } else {
        postTraceToFrame();
    }
}

function closePipelineModal() {
    if (!pipelineModal) return;
    pipelineModal.classList.add('hidden');
}

async function fetchLatestPipelineTrace() {
    try {
        const res = await fetch('/api/pipeline/latest');
        if (res.ok) {
            const data = await res.json();
            activePipelineTrace = data;
            renderModalPipeline(data);
        }
    } catch (err) {
        console.error("Fetch pipeline error:", err);
    }
}

function renderModalPipeline(trace) {
    if (!trace) return;
    if (trace.total_duration_ms && pipelineTotalTime) {
        pipelineTotalTime.textContent = `${Math.round(trace.total_duration_ms)} ms`;
    }
    postTraceToFrame();
}

if (pipelineBtn) pipelineBtn.addEventListener('click', openPipelineModal);
if (closePipelineModalBtn) closePipelineModalBtn.addEventListener('click', closePipelineModal);
if (pipelineModal) {
    pipelineModal.addEventListener('click', (e) => {
        if (e.target === pipelineModal) closePipelineModal();
    });
}

// --- Image & Video Lightbox Modal Controller ---
const imageLightboxModal = document.getElementById('image-lightbox-modal');
const lightboxImg = document.getElementById('lightbox-img');
const lightboxVideo = document.getElementById('lightbox-video');
const lightboxTitle = document.getElementById('lightbox-title');
const lightboxOpenNewtab = document.getElementById('lightbox-open-newtab');
const lightboxDownloadBtn = document.getElementById('lightbox-download-btn');
const closeLightboxBtn = document.getElementById('close-lightbox-btn');

function openImageLightbox(src, title = 'Pratinjau Gambar') {
    if (!imageLightboxModal || !lightboxImg) return;
    if (lightboxVideo) {
        try { lightboxVideo.pause(); } catch (_) {}
        lightboxVideo.src = '';
        lightboxVideo.classList.add('hidden');
    }
    lightboxImg.classList.remove('hidden');
    lightboxImg.src = src;
    if (lightboxTitle) lightboxTitle.textContent = title;
    if (lightboxOpenNewtab) lightboxOpenNewtab.href = src;
    if (lightboxDownloadBtn) {
        lightboxDownloadBtn.href = src;
        lightboxDownloadBtn.download = `shiro_img_${Date.now()}.jpg`;
    }
    imageLightboxModal.classList.remove('hidden');
}

function openVideoLightbox(src, title = 'Pratinjau Video') {
    if (!imageLightboxModal || !lightboxVideo) return;
    if (lightboxImg) {
        lightboxImg.src = '';
        lightboxImg.classList.add('hidden');
    }
    lightboxVideo.classList.remove('hidden');
    lightboxVideo.src = src;
    if (lightboxTitle) lightboxTitle.textContent = title || t('video_preview');
    if (lightboxOpenNewtab) lightboxOpenNewtab.href = src;
    if (lightboxDownloadBtn) {
        lightboxDownloadBtn.href = src;
        lightboxDownloadBtn.download = title || `shiro_video_${Date.now()}.mp4`;
    }
    imageLightboxModal.classList.remove('hidden');
    try { lightboxVideo.play().catch(() => {}); } catch (_) {}
}

function closeImageLightbox() {
    if (!imageLightboxModal) return;
    imageLightboxModal.classList.add('hidden');
    if (lightboxImg) lightboxImg.src = '';
    if (lightboxVideo) {
        try { lightboxVideo.pause(); } catch (_) {}
        lightboxVideo.src = '';
        lightboxVideo.classList.add('hidden');
    }
}

function handleLightboxBackdropClick(e) {
    if (e.target === imageLightboxModal) {
        closeImageLightbox();
    }
}

if (closeLightboxBtn) closeLightboxBtn.addEventListener('click', closeImageLightbox);

// --- Document Viewer Modal Controller ---
const docViewerModal = document.getElementById('doc-viewer-modal');
const docModalFilename = document.getElementById('doc-modal-filename');
const docModalSub = document.getElementById('doc-modal-sub');
const docModalIconBadge = document.getElementById('doc-modal-icon-badge');
const docModalIcon = document.getElementById('doc-modal-icon');
const docModalDownloadLink = document.getElementById('doc-modal-download-link');
const docModalTabs = document.getElementById('doc-modal-tabs');
const tabBtnDocFrame = document.getElementById('tab-btn-doc-frame');
const tabBtnDocText = document.getElementById('tab-btn-doc-text');
const docModalIframe = document.getElementById('doc-modal-iframe');
const docModalTextWrapper = document.getElementById('doc-modal-text-wrapper');
const docModalTextDisplay = document.getElementById('doc-modal-text-display');
const closeDocModalBtn = document.getElementById('close-doc-modal');

let currentDocModalContent = "";
let currentDocViewMode = "frame";

async function openDocModal(filename, url, ext = "") {
    if (!docViewerModal) return;

    if (!ext) {
        ext = (filename.split('.').pop() || '').toLowerCase();
    }

    if (docModalFilename) docModalFilename.textContent = filename;
    if (docModalSub) docModalSub.textContent = `${currentLang === 'en' ? 'File Preview' : 'Pratinjau Berkas'} (${ext.toUpperCase()})`;
    
    const fileUrl = url || `/api/files/${encodeURIComponent(filename)}`;
    if (docModalDownloadLink) {
        docModalDownloadLink.href = fileUrl;
    }

    const isCodeExt = CODE_EXTENSIONS_SET.has(ext);

    if (docModalIcon) {
        if (ext === 'pdf') {
            docModalIcon.className = 'ph ph-file-pdf';
        } else if (['doc', 'docx'].includes(ext)) {
            docModalIcon.className = 'ph ph-file-doc';
        } else if (['csv', 'tsv'].includes(ext)) {
            docModalIcon.className = 'ph ph-file-csv';
        } else if (isCodeExt) {
            docModalIcon.className = 'ph ph-file-code';
        } else {
            docModalIcon.className = 'ph ph-file-text';
        }
    }

    const isPdf = ext === 'pdf';

    if (docModalIframe) {
        if (isPdf) {
            docModalIframe.src = fileUrl;
            docModalIframe.classList.remove('hidden');
        } else {
            docModalIframe.src = '';
            docModalIframe.classList.add('hidden');
        }
    }

    if (isPdf) {
        if (docModalTabs) docModalTabs.style.display = 'flex';
        switchDocViewMode('frame');
    } else {
        if (docModalTabs) docModalTabs.style.display = 'none';
        switchDocViewMode('text');
    }

    const renderDocTextContent = (textContent) => {
        if (!docModalTextDisplay) return;
        docModalTextDisplay.removeAttribute('data-highlighted');
        docModalTextDisplay.className = 'doc-modal-pre';
        docModalTextDisplay.textContent = textContent;
        if (isCodeExt && typeof hljs !== 'undefined') {
            try {
                hljs.highlightElement(docModalTextDisplay);
            } catch (_) {}
        }
    };

    if (docModalTextDisplay) {
        docModalTextDisplay.textContent = currentLang === 'en' ? "Reading file content..." : "Sedang membaca isi berkas...";
    }

    if (attachedDocument && attachedDocument.filename === filename && attachedDocument.text) {
        currentDocModalContent = attachedDocument.text;
        renderDocTextContent(currentDocModalContent);
        if (docModalSub) {
            docModalSub.textContent = `${ext.toUpperCase()} · ${currentDocModalContent.length.toLocaleString()} ${currentLang === 'en' ? 'chars · Attached' : 'karakter · Teks Terlampir'}`;
        }
        docViewerModal.classList.remove('hidden');
        return;
    }
    
    try {
        const res = await fetch(`/api/document/preview?filename=${encodeURIComponent(filename)}`);
        if (res.ok) {
            const data = await res.json();
            currentDocModalContent = data.text || (currentLang === 'en' ? "// Empty file or no extractable text." : "// Dokumen kosong atau tidak memiliki teks yang dapat diekstrak.");
            renderDocTextContent(currentDocModalContent);
            if (docModalSub) {
                const chars = data.char_count || currentDocModalContent.length;
                docModalSub.textContent = `${ext.toUpperCase()} · ${chars.toLocaleString()} ${currentLang === 'en' ? 'chars' : 'karakter'} · ${data.page_count ? data.page_count + (currentLang === 'en' ? ' pages' : ' halaman') : (currentLang === 'en' ? 'Parsed text' : 'Teks terurai')}`;
            }
        } else {
            if (docModalTextDisplay) {
                docModalTextDisplay.textContent = currentLang === 'en'
                    ? `File '${filename}' is ready to download or open.\nClick 'Open original' to view the full file.`
                    : `Dokumen '${filename}' siap diunduh atau dibuka langsung.\nKlik 'Buka asli' untuk membuka berkas lengkap.`;
            }
        }
    } catch (err) {
        if (docModalTextDisplay) {
            docModalTextDisplay.textContent = `${currentLang === 'en' ? 'Failed to load text' : 'Gagal memuat teks'}: ${err.message || 'Error'}`;
        }
    }

    docViewerModal.classList.remove('hidden');
}

function closeDocModal() {
    if (!docViewerModal) return;
    docViewerModal.classList.add('hidden');
    if (docModalIframe) docModalIframe.src = '';
    currentDocModalContent = "";
}

function handleDocModalBackdropClick(e) {
    if (e.target === docViewerModal) {
        closeDocModal();
    }
}

function switchDocViewMode(mode) {
    currentDocViewMode = mode;
    if (tabBtnDocFrame) tabBtnDocFrame.classList.toggle('active', mode === 'frame');
    if (tabBtnDocText) tabBtnDocText.classList.toggle('active', mode === 'text');

    if (mode === 'frame') {
        if (docModalIframe) docModalIframe.classList.remove('hidden');
        if (docModalTextWrapper) docModalTextWrapper.classList.add('hidden');
    } else {
        if (docModalIframe) docModalIframe.classList.add('hidden');
        if (docModalTextWrapper) docModalTextWrapper.classList.remove('hidden');
    }
}

async function copyDocModalContent() {
    if (!currentDocModalContent) return;
    try {
        await navigator.clipboard.writeText(currentDocModalContent);
        const copyBtn = document.getElementById('doc-modal-copy-btn');
        if (copyBtn) {
            const oldHtml = copyBtn.innerHTML;
            copyBtn.innerHTML = `<i class="ph ph-check"></i> ${t('copied_toast')}`;
            setTimeout(() => { copyBtn.innerHTML = oldHtml; }, 2000);
        }
    } catch (err) {
        console.error("Gagal menyalin teks:", err);
    }
}

if (closeDocModalBtn) closeDocModalBtn.addEventListener('click', closeDocModal);

// Global Keyboard Shortcuts
window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const confirmModal = document.getElementById('confirm-modal');
        if (confirmModal && !confirmModal.classList.contains('hidden')) {
            resolveConfirmDialog(false);
            return;
        }
        const shareModal = document.getElementById('share-modal');
        if (shareModal && !shareModal.classList.contains('hidden')) {
            closeShareModal();
            return;
        }
        const chatFilesDrawer = document.getElementById('chat-files-drawer');
        if (chatFilesDrawer && !chatFilesDrawer.classList.contains('hidden')) {
            closeChatFilesDrawer();
            return;
        }
        if (imageLightboxModal && !imageLightboxModal.classList.contains('hidden')) {
            closeImageLightbox();
        } else if (docViewerModal && !docViewerModal.classList.contains('hidden')) {
            closeDocModal();
        } else if (pipelineModal && !pipelineModal.classList.contains('hidden')) {
            closePipelineModal();
        } else if (settingsModal && !settingsModal.classList.contains('hidden')) {
            closeSettings();
        } else if (document.getElementById('rename-modal') && !document.getElementById('rename-modal').classList.contains('hidden')) {
            closeRenameModal();
        } else if (document.getElementById('chat-actions-menu') && !document.getElementById('chat-actions-menu').classList.contains('hidden')) {
            toggleChatActionsMenu(false);
        } else if (pinnedDrawer && !pinnedDrawer.classList.contains('hidden')) {
            togglePinnedDrawer(false);
        }
    }
});

if (imagePreviewThumb) {
    imagePreviewThumb.style.cursor = 'pointer';
    imagePreviewThumb.title = 'Klik untuk melihat pratinjau gambar';
    imagePreviewThumb.addEventListener('click', () => {
        if (attachedImage && attachedImage.dataUrl) {
            openImageLightbox(attachedImage.dataUrl, attachedImage.name || 'Pratinjau Lampiran Gambar');
        }
    });
}

const docPreviewCardEl = document.querySelector('.doc-preview-card');
if (docPreviewCardEl) {
    docPreviewCardEl.style.cursor = 'pointer';
    docPreviewCardEl.title = 'Klik untuk melihat pratinjau dokumen';
    docPreviewCardEl.addEventListener('click', (e) => {
        if (e.target.closest('#remove-doc-btn')) return;
        if (attachedDocument) {
            openDocModal(attachedDocument.filename, attachedDocument.url || '', attachedDocument.file_type || '');
        }
    });
}

// Init
document.addEventListener('DOMContentLoaded', async () => {
    try {
        applyI18nToDOM();
    } catch (e) {
        console.error('i18n error:', e);
    }
    try {
        initSidebarState();
    } catch (e) {
        console.error('sidebar error:', e);
    }
    try {
        initSidebarResizer();
    } catch (e) {
        console.error('sidebar resizer error:', e);
    }
    try {
        initModalTabsScroll();
    } catch (e) {
        console.error('modal tabs scroll error:', e);
    }
    try {
        initLyraTierPicker();
    } catch (e) {
        console.error('lyra tier picker error:', e);
    }

    // 1. Muat profil, privasi, dan model terlebih dahulu agar avatar & nama sudah siap saat chat di-render
    try {
        await Promise.allSettled([
            loadProfiles(),
            loadPrivacySettings(),
            loadModels(),
            loadAgentSettings()
        ]);
    } catch (e) {
        console.error('Profiles/models error:', e);
    }

    // 2. Deteksi URL langsung ala Claude: /chat/<session_id> atau /share/<session_id>
    const pathParts = window.location.pathname.split('/');
    let targetSessionId = null;
    if ((pathParts[1] === 'chat' || pathParts[1] === 'share') && pathParts[2]) {
        targetSessionId = pathParts[2].trim();
    }

    // 3. Muat sesi percakapan & pesan
    try {
        await loadSessions({ syncActive: !targetSessionId, renderMessages: !targetSessionId });
        if (targetSessionId) {
            try {
                await switchSession(targetSessionId, true);
            } catch (err) {
                console.warn('Direct session switch fallback:', err);
                await loadChatHistory();
            }
        } else {
            // Periksa apakah pesan sudah dirender langsung oleh loadSessions()
            const existingMsgs = chatMessages ? chatMessages.querySelectorAll('.message:not(#typing-indicator)') : [];
            const isOnlyGreeting = existingMsgs.length === 1 && existingMsgs[0].querySelector('[data-i18n="welcome_greeting"]');
            if (existingMsgs.length === 0 || isOnlyGreeting) {
                await loadChatHistory();
            }
        }
    } catch (e) {
        console.error('Session/Chat history init error:', e);
        try { await loadChatHistory(); } catch (_) {}
    }

    // 4. Retry pengaman jika server baru restart dan daftar sesi sempat belum termuat
    if (!currentSessionsData || currentSessionsData.length === 0) {
        setTimeout(async () => {
            if (!currentSessionsData || currentSessionsData.length === 0) {
                console.log('[Init] Retrying loadSessions after slight delay...');
                await loadSessions({ syncActive: false, renderMessages: false });
            }
        }, 1200);
    }

    window.addEventListener('popstate', () => {
        const parts = window.location.pathname.split('/');
        if ((parts[1] === 'chat' || parts[1] === 'share') && parts[2]) {
            if (parts[2] !== activeSessionId) {
                switchSession(parts[2], true);
            }
        }
    });

    if (userInput) {
        userInput.focus();
    }
});

// --- Pengaturan Tema ---
(function initThemeUi() {
    const ST = window.ShiroTheme;
    const grid = document.getElementById('theme-grid');
    if (!ST || !grid) return;

    const inputs = {
        bg: document.getElementById('theme-bg'),
        fg: document.getElementById('theme-fg'),
        accent: document.getElementById('theme-accent')
    };
    const contrastEl = document.getElementById('theme-contrast');
    const swatches = {};

    function makeSwatch(id, name) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'theme-swatch';
        btn.dataset.id = id;
        btn.innerHTML = '<span class="theme-swatch-name"></span><span class="theme-swatch-bars"><span></span><span></span><span class="accent"></span></span>';
        btn.querySelector('.theme-swatch-name').textContent = name;
        btn.addEventListener('click', () => {
            const cur = ST.get();
            ST.set({ preset: id, custom: cur.custom });
            refresh();
        });
        grid.appendChild(btn);
        swatches[id] = btn;
    }

    function paintSwatch(id, c) {
        const b = swatches[id];
        b.style.setProperty('--sw-bg', c.bg);
        b.style.setProperty('--sw-fg', c.fg);
        b.style.setProperty('--sw-accent', c.accent);
    }

    ST.presets.forEach((p) => makeSwatch(p.id, p.name));
    makeSwatch('custom', 'Kustom');

    function refresh() {
        const theme = ST.get();
        ST.presets.forEach((p) => paintSwatch(p.id, p));
        paintSwatch('custom', theme.custom);
        Object.keys(swatches).forEach((id) => swatches[id].classList.toggle('active', id === theme.preset));

        const c = ST.resolve(theme);
        ['bg', 'fg', 'accent'].forEach((k) => {
            inputs[k].value = c[k];
            document.getElementById('theme-' + k + '-hex').textContent = c[k].toUpperCase();
        });

        const ratio = ST.contrast(c.bg, c.fg);
        const low = ratio < 4.5;
        contrastEl.classList.toggle('low', low);
        contrastEl.textContent = low
            ? 'Kontras teks rendah (' + ratio.toFixed(1) + ':1). Teks mungkin sulit dibaca.'
            : 'Kontras teks ' + (ratio >= 7 ? 'sangat baik' : 'baik') + ' (' + ratio.toFixed(1) + ':1).';

        applyMermaidTheme();
    }

    Object.keys(inputs).forEach((k) => {
        inputs[k].addEventListener('input', () => {
            ST.set({
                preset: 'custom',
                custom: { bg: inputs.bg.value, fg: inputs.fg.value, accent: inputs.accent.value }
            });
            refresh();
        });
    });

    document.getElementById('theme-reset').addEventListener('click', () => {
        ST.set(ST.defaults());
        refresh();
        showToast('Tema dikembalikan ke default');
    });

    refresh();
})();


// ============================================================================
// Antigravity Local PC Agent Controls & Live Plan Card
// ============================================================================

async function loadAgentSettings() {
    try {
        const res = await fetch('/api/agent/settings');
        if (!res.ok) return;
        const data = await res.json();

        const banner = document.getElementById('agent-env-banner');
        const bannerText = document.getElementById('agent-env-status-text');
        if (banner && bannerText) {
            if (data.is_local_pc) {
                banner.classList.remove('is-colab');
                const adminTxt = data.is_os_admin ? 'Hak OS: Administrator' : 'Hak OS: User Standar (UAC On-Demand)';
                bannerText.textContent = `PC Lokal (${data.os_name || 'PC'}) • ${adminTxt} • Status: ${data.effective_enabled ? 'AKTIF' : 'NONAKTIF'}`;
            } else {
                banner.classList.add('is-colab');
                bannerText.textContent = 'Lingkungan Google Colab terdeteksi: Mode Agent PC Lokal otomatis dinonaktifkan (hanya aktif di PC lokal).';
            }
        }

        const enabledEl = document.getElementById('agent-enabled-toggle');
        const modeEl = document.getElementById('agent-approval-mode');
        const adminEl = document.getElementById('agent-allow-admin-toggle');
        const wsEl = document.getElementById('agent-workspace-input');
        const stepsEl = document.getElementById('agent-max-steps-input');

        if (enabledEl) enabledEl.checked = Boolean(data.enabled);
        if (modeEl && data.approval_mode) modeEl.value = data.approval_mode;
        if (adminEl) adminEl.checked = Boolean(data.allow_admin);
        if (wsEl) wsEl.value = data.workspace_root || '';
        if (stepsEl && data.max_steps) stepsEl.value = data.max_steps;
    } catch (e) {
        console.error('Error loading Local Agent settings:', e);
    }
}

async function saveAgentSettings() {
    const enabledEl = document.getElementById('agent-enabled-toggle');
    const modeEl = document.getElementById('agent-approval-mode');
    const adminEl = document.getElementById('agent-allow-admin-toggle');
    const wsEl = document.getElementById('agent-workspace-input');
    const stepsEl = document.getElementById('agent-max-steps-input');

    const payload = {
        enabled: enabledEl ? enabledEl.checked : true,
        approval_mode: modeEl ? modeEl.value : 'ask',
        allow_admin: adminEl ? adminEl.checked : false,
        workspace_root: wsEl ? wsEl.value.trim() : '',
        max_steps: stepsEl ? parseInt(stepsEl.value || '12', 10) : 12
    };

    try {
        const res = await fetch('/api/agent/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast('Pengaturan Agent PC Lokal berhasil disimpan');
            loadAgentSettings();
        } else {
            showToast('Gagal menyimpan pengaturan Agent: ' + (data.error || 'Error'));
        }
    } catch (e) {
        showToast('Error menyimpan pengaturan Agent: ' + e.message);
    }
}

function createOrUpdateAgentWorkspaceCard(taskId, plan, stepEvent = null, approvalEvent = null, overrideStatus = null) {
    if (!taskId || !chatMessages) return null;
    const cardId = `ag-card-${taskId}`;
    let card = document.getElementById(cardId);

    if (!card) {
        card = document.createElement('div');
        card.id = cardId;
        card.className = 'antigravity-plan-card';
        card.innerHTML = `
            <div class="ag-plan-header">
                <div class="ag-plan-title">
                    <i class="ph ph-terminal-window"></i>
                    <span class="ag-goal-text">Menyusun rencana...</span>
                </div>
                <span class="ag-plan-badge">Merencanakan</span>
            </div>
            <ul class="ag-step-list"></ul>
            <div class="ag-step-logs"></div>
            <div class="ag-approval-slot"></div>
        `;
        chatMessages.appendChild(card);
    }

    const goalEl = card.querySelector('.ag-goal-text');
    const badgeEl = card.querySelector('.ag-plan-badge');
    const listEl = card.querySelector('.ag-step-list');
    const logsEl = card.querySelector('.ag-step-logs');
    const approvalSlot = card.querySelector('.ag-approval-slot');

    if (plan && goalEl) {
        goalEl.textContent = plan.goal || 'Tugas Otonom PC Lokal';
    }

    let badgeStatus = overrideStatus || (approvalEvent ? 'awaiting_approval' : 'running');
    const badgeLabels = {
        planning: 'Merencanakan',
        running: 'Menjalankan',
        awaiting_approval: 'Menunggu Persetujuan',
        completed: 'Selesai',
        rejected: 'Dibatalkan'
    };
    if (badgeEl) {
        badgeEl.className = `ag-plan-badge status-${badgeStatus}`;
        badgeEl.textContent = badgeLabels[badgeStatus] || 'Menjalankan';
    }

    if (plan && Array.isArray(plan.steps) && listEl) {
        listEl.innerHTML = plan.steps.map((st, idx) => {
            const stStatus = st.status || 'pending';
            let icon = 'ph-circle';
            if (stStatus === 'done') icon = 'ph-check-circle';
            else if (stStatus === 'in_progress') icon = 'ph-spinner';
            else if (stStatus === 'awaiting_approval') icon = 'ph-shield-warning';
            else if (stStatus === 'failed') icon = 'ph-x-circle';
            else if (stStatus === 'skipped') icon = 'ph-minus-circle';

            const risk = st.risk || 'exec';
            const riskLabel = risk === 'admin' ? 'ADMIN / UAC' : risk;
            return `
                <li class="ag-step-item step-${escapeHtml(stStatus)}">
                    <i class="ph ${icon}"></i>
                    <span>${idx + 1}. ${escapeHtml(st.title || '')}</span>
                    <span class="ag-risk-badge risk-${escapeHtml(risk)}">${escapeHtml(riskLabel)}</span>
                </li>
            `;
        }).join('');
    }

    if (stepEvent && logsEl) {
        const entry = document.createElement('div');
        entry.className = 'ag-log-entry';
        const argsStr = stepEvent.args ? JSON.stringify(stepEvent.args, null, 2) : '{}';
        const outStr = stepEvent.output || stepEvent.summary || '';
        const riskTag = stepEvent.risk === 'admin' ? ' [ADMIN / UAC]' : '';
        entry.innerHTML = `
            <details>
                <summary>${escapeHtml(stepEvent.status === 'done' ? '✓' : '✗')} Langkah ${stepEvent.step_index}: ${escapeHtml(stepEvent.tool)}${riskTag}</summary>
                <pre>Args: ${escapeHtml(argsStr)}\n\nHasil:\n${escapeHtml(outStr)}</pre>
            </details>
        `;
        logsEl.appendChild(entry);
    }

    if (approvalSlot) {
        if (approvalEvent) {
            const isAdmin = approvalEvent.risk === 'admin';
            const argsPretty = JSON.stringify(approvalEvent.args || {}, null, 2);
            const adminNotice = isAdmin
                ? '<span class="ag-risk-badge risk-admin">ADMIN / UAC</span>'
                : `<span class="ag-risk-badge risk-${escapeHtml(approvalEvent.risk || 'exec')}">${escapeHtml(approvalEvent.risk || 'exec')}</span>`;
            const approveAllLabel = isAdmin ? 'Izinkan Admin (Sesi Ini)' : 'Setujui Semua (Sesi Ini)';
            const approveAllDecision = isAdmin ? 'approve_admin' : 'approve_all';

            approvalSlot.innerHTML = `
                <div class="ag-approval-box ${isAdmin ? 'is-admin' : ''}">
                    <div class="ag-approval-head">
                        <span><i class="ph ph-shield-warning"></i> Konfirmasi Diperlukan: <code>${escapeHtml(approvalEvent.tool)}</code></span>
                        ${adminNotice}
                    </div>
                    <div style="font-size:0.82rem;opacity:0.9;">${escapeHtml(approvalEvent.reason || '')}</div>
                    <pre class="ag-approval-preview">${escapeHtml(argsPretty)}</pre>
                    <div class="ag-approval-actions">
                        <button type="button" class="btn-primary btn-sm" onclick="approveAgentTask('${escapeHtml(taskId)}', 'approve', this)">
                            <i class="ph ph-check"></i> Setujui &amp; Jalankan
                        </button>
                        <button type="button" class="btn-secondary btn-sm" onclick="approveAgentTask('${escapeHtml(taskId)}', '${approveAllDecision}', this)">
                            <i class="ph ph-checks"></i> ${approveAllLabel}
                        </button>
                        <button type="button" class="btn-secondary btn-sm" onclick="approveAgentTask('${escapeHtml(taskId)}', 'reject', this)">
                            <i class="ph ph-x"></i> Tolak
                        </button>
                    </div>
                </div>
            `;
        } else if (overrideStatus === 'completed' || overrideStatus === 'rejected') {
            approvalSlot.innerHTML = '';
        }
    }

    scrollToBottom(false);
    return card;
}

async function approveAgentTask(taskId, decision, triggerBtn) {
    if (!taskId || !decision) return;
    const card = document.getElementById(`ag-card-${taskId}`);
    if (card) {
        card.querySelectorAll('.ag-approval-actions button').forEach((btn) => {
            btn.disabled = true;
        });
        const slot = card.querySelector('.ag-approval-slot');
        if (slot) {
            slot.innerHTML = `<div style="font-size:0.83rem;opacity:0.85;margin-top:8px;"><i class="ph ph-spinner"></i> Memproses keputusan (${escapeHtml(decision)})...</div>`;
        }
    } else if (triggerBtn) {
        triggerBtn.disabled = true;
    }

    showTyping(true, 'Melanjutkan eksekusi Agen PC...');
    status.textContent = 'Melanjutkan eksekusi Agen PC...';

    try {
        const res = await fetch('/api/agent/approve', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream, application/json'
            },
            body: JSON.stringify({ task_id: taskId, decision: decision, stream: true })
        });

        const contentType = res.headers.get('content-type') || '';
        if (!contentType.includes('text/event-stream')) {
            const data = await res.json();
            showTyping(false);
            if (data.status === 'awaiting_approval' && data.pending_action) {
                createOrUpdateAgentWorkspaceCard(taskId, data.plan, null, data.pending_action);
                status.textContent = 'Menunggu persetujuan Anda...';
            } else {
                createOrUpdateAgentWorkspaceCard(taskId, data.plan, null, null, data.status || 'completed');
                if (data.reply) {
                    addMessage('assistant', data.reply, null, null, null, null, null, data.agent_action || null, data.assistant_message_id || null, false);
                }
                status.textContent = t('status_ready');
            }
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let finalReply = '';
        let finalData = null;
        let finalAction = null;
        let nextApproval = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed.startsWith('data:')) continue;
                const jsonStr = trimmed.slice(5).trim();
                if (!jsonStr) continue;
                try {
                    const ev = JSON.parse(jsonStr);
                    if (ev.type === 'status') {
                        status.textContent = ev.status || '';
                        updateTypingStatus(ev.status || '');
                    } else if (ev.type === 'agent_step') {
                        createOrUpdateAgentWorkspaceCard(taskId, ev.plan, ev, null);
                    } else if (ev.type === 'approval_required') {
                        nextApproval = true;
                        createOrUpdateAgentWorkspaceCard(taskId, ev.plan, null, ev.pending_action);
                        status.textContent = 'Menunggu persetujuan Anda...';
                    } else if (ev.type === 'agent_action') {
                        finalAction = ev.agent_action;
                    } else if (ev.type === 'token') {
                        finalReply += ev.token || '';
                    } else if (ev.type === 'error') {
                        showToast('Error Agent: ' + (ev.error || 'Unknown'));
                    } else if (ev.type === 'done') {
                        finalData = ev;
                        if (ev.reply) finalReply = ev.reply;
                        if (ev.agent_action) finalAction = ev.agent_action;
                    }
                } catch (_) {}
            }
        }

        showTyping(false);
        if (nextApproval && !finalData) {
            scrollToBottom(true);
            return;
        }

        if (finalData) {
            createOrUpdateAgentWorkspaceCard(taskId, finalData.plan, null, null, finalData.status || 'completed');
        }
        if (finalReply) {
            addMessage(
                'assistant',
                finalReply,
                null,
                null,
                null,
                null,
                null,
                finalAction,
                finalData ? finalData.assistant_message_id : null,
                false
            );
        }
        updateMemoryCount();
        await loadSessions();
        status.textContent = t('status_ready');
    } catch (err) {
        showTyping(false);
        showToast('Gagal melanjutkan tugas Agent: ' + err.message);
        status.textContent = t('status_ready');
    }
}
