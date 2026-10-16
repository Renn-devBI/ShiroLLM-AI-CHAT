// DOM Elements
const chatViewport = document.getElementById('chat-viewport');
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const stopBtn = document.getElementById('stop-btn');
const resetBtn = document.getElementById('reset-btn');
const memoryCount = document.getElementById('memory-count');
const status = document.getElementById('status');

// Notifikasi singkat non-blocking
function showToast(message, duration = 2200) {
    const stack = document.getElementById('toast-stack');
    if (!stack) { console.log(message); return; }
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => el.remove(), duration);
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

// State tracking
let isGenerating = false;
let abortController = null;
let activeSessionId = 'default';
let attachedDocument = null;
let attachedImage = null;
let enableTrainingLogging = true;
let currentLang = localStorage.getItem('shiro_lang') || 'id';
let currentUILang = currentLang;

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
        attach_file_tooltip: 'Lampirkan berkas atau kode (.js, .py, .ts, .cpp, PDF, Word, TXT, CSV, MD, dll.)',
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
        status_stopped: 'Dihentikan',
        status_extracting: 'Mengekstrak berkas...',
        status_doc_ready: 'Berkas siap',
        download_code: 'Unduh',
        download_code_tooltip: 'Unduh kode sebagai berkas',
        downloaded_code: 'Tersimpan',
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
        session_not_found_toast: 'Sesi percakapan tidak ditemukan.'
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
        attach_file_tooltip: 'Attach file or source code (.js, .py, .ts, .cpp, PDF, Word, TXT, CSV, MD, etc.)',
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
        status_stopped: 'Stopped',
        status_extracting: 'Extracting file...',
        status_doc_ready: 'File ready',
        download_code: 'Download',
        download_code_tooltip: 'Download code as file',
        downloaded_code: 'Downloaded',
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
        session_not_found_toast: 'Conversation session not found.'
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
    updateMemoryCount();
    renderPinnedDrawer();
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

async function loadPrivacySettings() {
    try {
        const res = await fetch('/api/settings/privacy');
        if (!res.ok) return;
        const data = await res.json();
        if (typeof data.enable_training_logging === 'boolean') {
            updateTrainingBannerUI(data.enable_training_logging);
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
    if (shouldShow && isGenerating) {
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
                if (isGenerating) scrollBottomBtn.classList.add('is-streaming');
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

// Parse message formatting: Markdown, Syntax Highlighting, Mermaid, Sanitization
function parseMessageContent(text) {
    if (!text) return '';

    // Auto-heal unclosed code fence agar potongan kode yang sedang di-generate atau terpotong tetap di-render utuh
    let normalizedText = text;
    const fenceMatches = normalizedText.match(/```/g);
    if (fenceMatches && fenceMatches.length % 2 === 1) {
        normalizedText += '\n```';
    }

    const codeBlocks = [];

    // 1. Ekstrak Fenced Code Blocks: ```lang ... ```
    let content = normalizedText.replace(/```([a-zA-Z0-9_\-\.]*)\s*\n?([\s\S]*?)```/g, function(match, lang, code) {
        const cleanLang = (lang || '').trim().toLowerCase();
        const rawCode = (code || '').trim();
        const placeholder = `___SHIRO_BLOCK_${codeBlocks.length}___`;

        const escapedCode = rawCode
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');

        if (cleanLang === 'mermaid') {
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
            const displayLang = cleanLang || 'kode';
            const langClass = cleanLang ? `language-${cleanLang}` : 'nohighlight';
            codeBlocks.push(`
                <div class="code-block-wrapper" data-lang="${cleanLang || 'txt'}">
                    <div class="code-block-header">
                        <span class="code-lang-label">${displayLang}</span>
                        <div class="code-block-actions">
                            <button type="button" class="btn-code-action btn-download-code" onclick="downloadCodeSnippet(this)" title="${t('download_code_tooltip')}" aria-label="Unduh Berkas Kode">
                                <i class="ph ph-download-simple"></i> <span>${t('download_code')}</span>
                            </button>
                            <button type="button" class="btn-code-action btn-copy-code" onclick="copyCodeSnippet(this)" title="${t('copy_code_tooltip')}" aria-label="Salin Kode">
                                <i class="ph ph-copy"></i> <span>${t('copy_code')}</span>
                            </button>
                        </div>
                    </div>
                    <pre><code class="${langClass}">${escapedCode}</code></pre>
                </div>
            `);
        }
        return placeholder;
    });

    // 2. Escape teks non-kode untuk sanitasi awal
    let div = document.createElement('div');
    div.textContent = content;
    content = div.innerHTML;

    // 3. Parse Markdown Images
    content = content.replace(/!\[([^\]]*)\]\((https?:\/\/[^\s<>"'\)]+|\/[^\s<>"'\)]+)\)/g, function(match, alt, rawUrl) {
        let cleanUrl = rawUrl.replace(/[.,;!?)]+$/, '');
        let safeAlt = (alt || 'Gambar').replace(/"/g, '&quot;');
        let jsUrl = cleanUrl.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        return `<div class="chat-inline-img-wrap" onclick="openImageLightbox('${jsUrl}', '${safeAlt}')" title="Klik untuk melihat pratinjau penuh"><img src="${cleanUrl}" alt="${safeAlt}" class="chat-img-attachment" loading="lazy"></div>`;
    });

    // 4. Parse Markdown links [text](url)
    const mdLinks = [];
    content = content.replace(/\[([^\]]+)\]\((https?:\/\/[^\s<>"']+)\)/g, function(match, label, rawUrl) {
        let cleanUrl = rawUrl.replace(/[.,;!?)]+$/, '');
        let placeholder = `___SHIRO_MD_LINK_${mdLinks.length}___`;
        mdLinks.push(`<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="chat-link" title="Buka: ${cleanUrl}">${label}</a>`);
        return placeholder;
    });

    // 5. Parse plain URL
    const urlRegex = /(https?:\/\/[^\s<>"']+)/g;
    content = content.replace(urlRegex, function(match) {
        let cleanUrl = match.replace(/[.,;!?)]+$/, '');
        let trailing = match.slice(cleanUrl.length);
        return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="chat-link" title="Buka: ${cleanUrl}">${cleanUrl}</a>${trailing}`;
    });

    mdLinks.forEach((linkHtml, idx) => {
        content = content.replace(`___SHIRO_MD_LINK_${idx}___`, linkHtml);
    });

    // 6. Parse inline code
    content = content.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    // 7. Parse formatting teks
    content = content.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    content = content.replace(/~~(.+?)~~/g, '<del>$1</del>');
    content = content.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // 8. Parse baris baru
    content = content.replace(/\r\n/g, '\n').replace(/\n/g, '<br>');

    // 9. Pulihkan blok kode & diagram mermaid
    codeBlocks.forEach((blockHtml, idx) => {
        content = content.replace(`___SHIRO_BLOCK_${idx}___`, blockHtml);
    });

    // 10. Markdown Sanitization via DOMPurify
    if (typeof DOMPurify !== 'undefined') {
        try {
            content = DOMPurify.sanitize(content, {
                ADD_TAGS: ['svg', 'path', 'marker', 'g', 'rect', 'circle', 'line', 'polygon', 'text', 'tspan', 'style', 'defs'],
                ADD_ATTR: ['target', 'rel', 'onclick', 'data-*', 'class', 'id', 'd', 'fill', 'stroke', 'viewBox', 'width', 'height', 'style', 'title']
            });
        } catch (pErr) {
            console.warn('[DOMPurify Warning]:', pErr);
        }
    }

    return content;
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

function downloadCodeSnippet(btn) {
    const wrapper = btn.closest('.code-block-wrapper');
    if (!wrapper) return;
    const codeEl = wrapper.querySelector('code');
    if (!codeEl) return;
    const text = codeEl.innerText || codeEl.textContent;
    if (!text) return;

    const rawLang = (wrapper.dataset.lang || '').trim().toLowerCase();
    const ext = CODE_LANG_EXT_MAP[rawLang] || (rawLang && /^[a-z0-9]+$/.test(rawLang) ? rawLang : 'txt');

    // 1. Deteksi nama berkas dari komentar baris pertama (misal: // index.html atau <!-- file: App.vue -->)
    let filename = '';
    const firstLines = text.split('\n').slice(0, 4).join('\n');
    const fnMatch = firstLines.match(/(?:filename|file|nama berkas|name)\s*[:=]\s*([a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+)/i)
                 || firstLines.match(/^(?:(?:\/\/|#|<!--|\/\*)\s*)([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)/m);

    if (fnMatch && fnMatch[1]) {
        filename = fnMatch[1].split(/[\/\\]/).pop().trim();
    }

    // 2. Default nama file ala ChatGPT
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

    // 3. Tentukan MIME Type
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

    // 4. Unduh berkas langsung di browser via Blob
    try {
        const blob = new Blob([text], { type: mimeType });
        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = blobUrl;
        link.download = filename;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(() => URL.revokeObjectURL(blobUrl), 1500);

        // Feedback visual tombol
        const span = btn.querySelector('span');
        const icon = btn.querySelector('i');
        const oldText = span ? span.textContent : '';
        if (span) span.textContent = t('downloaded_code') || 'Tersimpan';
        if (icon) icon.className = 'ph ph-check';
        btn.classList.add('download-success');

        setTimeout(() => {
            if (span) span.textContent = oldText || t('download_code') || 'Unduh';
            if (icon) icon.className = 'ph ph-download-simple';
            btn.classList.remove('download-success');
        }, 2000);

        if (typeof showToast === 'function') {
            const toastMsg = currentLang === 'en'
                ? `File "${filename}" downloaded`
                : `Berkas "${filename}" berhasil diunduh`;
            showToast(toastMsg);
        }
    } catch (err) {
        console.error('Error downloading code snippet:', err);
        if (typeof showToast === 'function') {
            showToast(currentLang === 'en' ? 'Download failed' : 'Gagal mengunduh berkas');
        }
    }
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
    if (isGenerating) return;
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

// Add message ke chat
function addMessage(role, content, imageUrl = null, docName = null, docUrl = null, docType = null, docText = null, agentActionData = null, msgId = null, isPinned = false) {
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
    if (docName) {
        const ext = (docName.split('.').pop() || '').toLowerCase();
        let iconClass = 'ph-file-text';
        let badgeColor = 'badge-txt';
        let typeLabel = (docType || ext).toUpperCase() || 'DOC';
        
        if (ext === 'pdf') {
            iconClass = 'ph-file-pdf';
            badgeColor = 'badge-pdf';
            typeLabel = 'PDF';
        } else if (['doc', 'docx'].includes(ext)) {
            iconClass = 'ph-file-doc';
            badgeColor = 'badge-doc';
            typeLabel = 'WORD';
        } else if (['csv', 'tsv'].includes(ext)) {
            iconClass = 'ph-file-csv';
            badgeColor = 'badge-csv';
            typeLabel = 'CSV';
        } else if (CODE_EXTENSIONS_SET.has(ext) || CODE_EXTENSIONS_SET.has((docType || '').toLowerCase())) {
            iconClass = 'ph-file-code';
            badgeColor = 'badge-code';
            typeLabel = (ext || docType || 'CODE').toUpperCase();
        }

        const safeFilename = (docName || 'document').replace(/"/g, '&quot;');
        const safeDocUrl = docUrl || `/api/files/${encodeURIComponent(docName)}`;
        const jsFilename = (docName || 'document').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        const jsUrl = safeDocUrl.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        const jsType = ext.replace(/\\/g, '\\\\').replace(/'/g, "\\'");

        attachmentHTML += `
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
    }

    if (imageUrl) {
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

    let innerBubbleHTML = '';
    innerBubbleHTML += `<div class="msg-pin-indicator ${pinnedState ? '' : 'hidden'}"><i class="ph-fill ph-push-pin"></i> <span data-i18n="pinned_badge">${t('pinned_badge')}</span></div>`;
    if (attachmentHTML) {
        innerBubbleHTML += `<div class="msg-attachment-wrap">${attachmentHTML}</div>`;
    }
    if (formattedContent) {
        innerBubbleHTML += `<div class="msg-text">${formattedContent}</div>`;
    }

    messageDiv.innerHTML = `
        ${role === 'assistant' ? avatarHTML : ''}
        <div class="bubble-container">
            ${statusCardHTML}
            <div class="bubble" data-original-text="${escapedContent}">${innerBubbleHTML}</div>
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

function showTyping(show) {
    if (!typingIndicator) return;
    if (show) {
        updateTypingIndicatorAvatar();
        typingIndicator.classList.remove('hidden');
        if (chatMessages) {
            chatMessages.appendChild(typingIndicator);
        }
        scrollToBottom();
    } else {
        typingIndicator.classList.add('hidden');
    }
}

function startTriggerTimer() {
    clearTimeout(triggerTimer);
    const naturalDelay = Math.floor(Math.random() * (240000 - 150000 + 1)) + 150000;
    
    triggerTimer = setTimeout(() => {
        if (isGenerating || (userInput && userInput.value.trim().length > 0)) return; 

        fetch('/api/trigger', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        })
        .then(res => res.json())
        .then(data => {
            if (data.reply && data.status !== 'idle') {
                addMessage('assistant', data.reply, null, null, null, null, null, null, data.assistant_message_id || null, false); 
            }
        })
        .catch(err => console.error("Trigger fetch error:", err));
    }, naturalDelay);
}

// Send message main function
async function sendMessage() {
    const message = userInput.value.trim();
    if ((!message && !attachedImage && !attachedDocument) || isGenerating) return;

    clearTimeout(triggerTimer); 
    isGenerating = true;
    isUserScrolledUp = false;
    if (scrollBottomBtn) {
        scrollBottomBtn.classList.add('hidden');
        scrollBottomBtn.classList.remove('is-streaming');
    }
    userInput.disabled = true;
    sendBtn.disabled = true;
    sendBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');
    
    const sendingImage = attachedImage;
    const currentImgUrl = sendingImage ? sendingImage.dataUrl : null;
    const sendingDoc = attachedDocument;
    
    userInput.value = '';
    adjustInputHeight();
    clearAttachedImage();
    clearAttachedDocument();
    
    let displayMsg = message;
    if (!displayMsg) {
        if (sendingDoc && sendingImage) {
            displayMsg = `Kakak memperlihatkan gambar dan melampirkan berkas ${sendingDoc.filename}.`;
        } else if (sendingDoc) {
            displayMsg = `Kakak melampirkan berkas dokumen: ${sendingDoc.filename}. Shiro, tolong rangkum atau periksa ya!`;
        } else if (sendingImage) {
            displayMsg = 'Kakak memperlihatkan gambar visual ini.';
        }
    }
    
    const userMsgEl = addMessage(
        'user', 
        displayMsg, 
        currentImgUrl, 
        sendingDoc ? sendingDoc.filename : null,
        sendingDoc ? sendingDoc.url : null,
        sendingDoc ? sendingDoc.file_type : null,
        sendingDoc ? sendingDoc.text : null
    );
    
    status.textContent = t('status_thinking');
    showTyping(true);
    if (pipelineNavDot) pipelineNavDot.classList.remove('hidden');
    startPipelineAnimation(displayMsg);

    abortController = new AbortController();

    try {
        const payload = { 
            message: message,
            stream: true 
        };
        if (currentImgUrl) {
            payload.image = currentImgUrl;
        }
        if (sendingDoc) {
            payload.document_text = sendingDoc.text;
            payload.document_name = sendingDoc.filename;
        }

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream, application/json'
            },
            body: JSON.stringify(payload),
            signal: abortController.signal
        });

        if (!response.ok) {
            let errorMsg = 'Gagal terhubung ke Shiro.';
            try {
                const errData = await response.json();
                if (errData.reply) {
                    showTyping(false);
                    addMessage('assistant', errData.reply);
                    status.textContent = t('status_ready');
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
            let streamText = '';
            let assistantMsgEl = null;
            let assistantBubble = null;
            let assistantTextEl = null;
            let finalData = null;
            let lastRenderTime = 0;

            const updateAssistantUI = (text, isDone = false) => {
                if (!assistantMsgEl) {
                    showTyping(false);
                    assistantMsgEl = addMessage(
                        'assistant',
                        text || '...',
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        false
                    );
                    assistantBubble = assistantMsgEl ? assistantMsgEl.querySelector('.bubble') : null;
                    assistantTextEl = assistantMsgEl ? assistantMsgEl.querySelector('.msg-text') : null;
                }
                if (assistantTextEl) {
                    let displayContent = text;
                    const codeBlockCount = (displayContent.match(/```/g) || []).length;
                    if (codeBlockCount % 2 === 1) {
                        displayContent += '\n```';
                    }

                    // Kunci scroll viewport agar layar tidak bergeser atau berkedip saat re-render innerHTML
                    const prevScrollTop = chatViewport.scrollTop;
                    const distFromBottom = chatViewport.scrollHeight - chatViewport.scrollTop - chatViewport.clientHeight;
                    const isAtBottom = distFromBottom <= 60;

                    assistantTextEl.innerHTML = parseMessageContent(displayContent);
                    if (assistantBubble) {
                        assistantBubble.setAttribute('data-original-text', text);
                    }

                    if (isUserScrolledUp) {
                        // User sedang membaca chat sebelumnya di atas: pertahankan posisi scroll user!
                        isProgrammaticScroll = true;
                        chatViewport.scrollTop = prevScrollTop;
                        if (scrollBottomBtn) {
                            scrollBottomBtn.classList.remove('hidden');
                            scrollBottomBtn.classList.add('is-streaming');
                        }
                    } else if (isAtBottom || !isDone) {
                        // User berada di dasar: auto-follow seketika (non-smooth) agar streaming tidak lag
                        isProgrammaticScroll = true;
                        chatViewport.scrollTop = chatViewport.scrollHeight;
                    }
                }
            };

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // pertahankan baris parsial dalam buffer

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || trimmed.startsWith(':')) {
                        // Heartbeat ping SSE (: ping) atau komentar, abaikan
                        continue;
                    }
                    if (trimmed.startsWith('data:')) {
                        const jsonStr = trimmed.slice(5).trim();
                        if (!jsonStr) continue;
                        try {
                            const evData = JSON.parse(jsonStr);
                            if (evData.type === 'init') {
                                if (userMsgEl && evData.user_message_id) {
                                    userMsgEl.dataset.msgId = evData.user_message_id;
                                }
                                if (evData.active_session_id) {
                                    activeSessionId = evData.active_session_id;
                                    try {
                                        if (window.location.pathname !== '/chat/' + evData.active_session_id) {
                                            window.history.pushState(null, '', '/chat/' + evData.active_session_id);
                                        }
                                    } catch (_) {}
                                }
                            } else if (evData.type === 'token') {
                                if (!streamText) {
                                    status.textContent = t('status_typing');
                                }
                                streamText += evData.token || '';
                                const now = Date.now();
                                if (now - lastRenderTime > 35) {
                                    lastRenderTime = now;
                                    updateAssistantUI(streamText, false);
                                }
                            } else if (evData.type === 'agent_action') {
                                // Eksekusi tool/agent action
                            } else if (evData.type === 'error') {
                                console.warn('[Stream Error Event]:', evData.error);
                            } else if (evData.type === 'done') {
                                finalData = evData;
                                if (evData.reply) {
                                    streamText = evData.reply;
                                }
                            }
                        } catch (errParse) {
                            console.warn('[Stream JSON Parse Error]:', errParse, jsonStr);
                        }
                    }
                }
            }

            // Render final setelah pembacaan stream tuntas
            showTyping(false);
            if (streamText || finalData) {
                updateAssistantUI(streamText, true);
                if (assistantMsgEl) {
                    if (finalData && finalData.assistant_message_id) {
                        assistantMsgEl.dataset.msgId = finalData.assistant_message_id;
                    }
                    if (finalData && finalData.assistant_image_url) {
                        let bubble = assistantMsgEl.querySelector('.bubble');
                        if (bubble && !bubble.querySelector('.chat-img-wrapper')) {
                            const jsImgUrl = finalData.assistant_image_url.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                            const imgWrap = document.createElement('div');
                            imgWrap.className = 'chat-img-wrapper';
                            imgWrap.onclick = () => openImageLightbox(jsImgUrl, 'Foto Lampiran Chat');
                            imgWrap.innerHTML = `<img src="${finalData.assistant_image_url}" class="chat-img-attachment" alt="Foto Visual" loading="lazy">`;
                            bubble.prepend(imgWrap);
                        }
                    }
                    if (typeof hljs !== 'undefined') {
                        assistantMsgEl.querySelectorAll('pre code[class*="language-"]').forEach(block => {
                            try { hljs.highlightElement(block); } catch (_) {}
                        });
                    }
                    if (typeof mermaid !== 'undefined') {
                        assistantMsgEl.querySelectorAll('.mermaid-container').forEach(async (container) => {
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
            }

            clearPipelineSimulation();

            if (finalData && finalData.pipeline_trace) {
                activePipelineTrace = finalData.pipeline_trace;
                renderModalPipeline(activePipelineTrace);
            }
            if (finalData && finalData.session_title) {
                const currentSession = currentSessionsData.find(s => s.id === activeSessionId);
                if (currentSession) currentSession.title = finalData.session_title;
            }

            updateMemoryCount();
            await loadSessions();
            status.textContent = t('status_ready');
            startTriggerTimer();

        } else {
            // Non-streaming fallback
            const data = await response.json();
            if (userMsgEl && data.user_message_id) {
                userMsgEl.dataset.msgId = data.user_message_id;
            }
            
            showTyping(false);
            const assistantImg = data.assistant_image_url || null;
            addMessage(
                'assistant',
                data.reply,
                assistantImg,
                null,
                null,
                null,
                null,
                data.agent_action,
                data.assistant_message_id || null,
                false
            );
            clearPipelineSimulation();
            
            if (data.pipeline_trace) {
                activePipelineTrace = data.pipeline_trace;
                renderModalPipeline(activePipelineTrace);
            }
            
            if (data.session_title) {
                const currentSession = currentSessionsData.find(s => s.id === activeSessionId);
                if (currentSession) currentSession.title = data.session_title;
            }
            updateMemoryCount(); 
            await loadSessions();
            status.textContent = t('status_ready');
            startTriggerTimer(); 
        }

    } catch (error) {
        clearPipelineSimulation();
        if (error.name === 'AbortError') {
            console.log('Request stopped by user');
            showTyping(false);
            status.textContent = t('status_stopped');
            const lastAssistantMsg = chatMessages ? chatMessages.querySelector('.message.assistant:last-child') : null;
            if (lastAssistantMsg && typeof hljs !== 'undefined') {
                lastAssistantMsg.querySelectorAll('pre code[class*="language-"]').forEach(block => {
                    try { hljs.highlightElement(block); } catch (_) {}
                });
            }
            try {
                updateMemoryCount();
                loadSessions();
            } catch (_) {}
        } else {
            console.error('Error:', error);
            showTyping(false);
            addErrorMessage(error.message || 'Gagal terhubung ke Shiro.', { message: displayMsg });
            status.textContent = t('status_ready');
        }
    } finally {
        clearPipelineSimulation();
        if (pipelineNavDot) pipelineNavDot.classList.add('hidden');
        isGenerating = false;
        if (scrollBottomBtn) {
            scrollBottomBtn.classList.remove('is-streaming');
            updateScrollBottomBtnVisibility();
        }
        userInput.disabled = false;
        sendBtn.disabled = false;
        sendBtn.classList.remove('hidden');
        stopBtn.classList.add('hidden');
        userInput.focus();
    }
}

function stopGeneration() {
    if (abortController) {
        abortController.abort();
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
    if (messages && messages.length > 0) {
        messages.forEach(msg => {
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
                Boolean(msg.pinned)
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

        renderMessagesList(data.history || []);
        updateMemoryCount();
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

let currentSessionsData = [];

async function loadSessions() {
    try {
        const res = await fetch('/api/sessions');
        const data = await res.json();
        if (data.sessions) {
            currentSessionsData = data.sessions;
            activeSessionId = data.active_session_id;

            const activeSession = data.sessions.find(s => s.id === data.active_session_id);
            const isCurrentSessionPinned = activeSession ? Boolean(activeSession.pinned) : false;
            updateChatMenuPinState(isCurrentSessionPinned);

            if (activeSession && activeSession.title && activeSession.title !== 'New chat' && activeSession.title !== 'Chat baru') {
                document.title = `${activeSession.title} · Shiro`;
            } else {
                document.title = 'Shiro · AI Assistant';
            }

            // Segera render data.messages jika ada dan layar belum memiliki pesan obrolan aktif
            if (Array.isArray(data.messages)) {
                const existingMsgs = chatMessages ? chatMessages.querySelectorAll('.message:not(#typing-indicator)') : [];
                const isOnlyGreeting = existingMsgs.length === 1 && existingMsgs[0].querySelector('[data-i18n="welcome_greeting"]');
                if (existingMsgs.length === 0 || isOnlyGreeting) {
                    renderMessagesList(data.messages);
                }
            }

            if (sessionSelect) {
                sessionSelect.innerHTML = '';
                data.sessions.forEach(s => {
                    const opt = document.createElement('option');
                    opt.value = s.id;
                    opt.textContent = (s.pinned ? '📌 ' : '') + (s.title || `Chat ${s.id.slice(0, 6)}`);
                    if (s.id === data.active_session_id) {
                        opt.selected = true;
                    }
                    sessionSelect.appendChild(opt);
                });
            }

            if (sidebarSessionList) {
                sidebarSessionList.innerHTML = '';
                if (data.sessions.length === 0) {
                    const emptyTip = document.createElement('div');
                    emptyTip.className = 'session-empty';
                    emptyTip.textContent = t('no_sessions');
                    sidebarSessionList.appendChild(emptyTip);
                } else {
                    data.sessions.forEach(s => {
                        const item = document.createElement('div');
                        item.className = 'session-item' + (s.id === data.active_session_id ? ' active' : '') + (s.pinned ? ' is-pinned' : '');
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
    } catch (e) {
        console.error("Error loading sessions:", e);
    }
}

async function createNewSession() {
    if (isGenerating) return;
    try {
        status.textContent = '...';
        const res = await fetch('/api/sessions/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: t('new_chat') })
        });
        const data = await res.json();
        if (data.success) {
            activeSessionId = data.session_id;
            try {
                window.history.pushState(null, '', '/chat/' + data.session_id);
            } catch (e) {}

            clearAttachedDocument();
            clearAttachedImage();

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
            const drawer = document.getElementById('chat-files-drawer');
            if (drawer && !drawer.classList.contains('hidden')) {
                renderChatFilesList();
            }
            await loadSessions();
            updateMemoryCount();
            status.textContent = t('status_ready');
            if (userInput) userInput.focus();
        }
    } catch (e) {
        console.error("Error creating new session:", e);
        status.textContent = 'Error';
    }
}

async function switchSession(sessionId, force = false) {
    if (!sessionId || (sessionId === activeSessionId && !force) || isGenerating) return;
    try {
        status.textContent = '...';
        const res = await fetch('/api/sessions/switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });
        const data = await res.json();
        if (data.success) {
            activeSessionId = sessionId;
            try {
                if (window.location.pathname !== '/chat/' + sessionId) {
                    window.history.pushState(null, '', '/chat/' + sessionId);
                }
            } catch (e) {}

            clearAttachedDocument();
            clearAttachedImage();

            renderMessagesList(data.messages || []);
            await loadSessions();
            updateMemoryCount();
            status.textContent = t('status_ready');
            if (userInput) userInput.focus();
        }
    } catch (e) {
        console.error("Error switching session:", e);
        status.textContent = 'Error';
    }
}

async function deleteSessionById(sessionId, title) {
    if (isGenerating) return;

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

    try {
        status.textContent = '...';
        const res = await fetch(`/api/sessions/${sessionId}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (data.success) {
            activeSessionId = data.active_session_id;
            clearAttachedDocument();
            clearAttachedImage();

            renderMessagesList(data.messages || []);
            await loadSessions();
            updateMemoryCount();
            status.textContent = t('status_ready');
        } else {
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
    const msgEls = document.querySelectorAll('#chat-messages .message');
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
        if (bubble) {
            const text = bubble.innerText.trim();
            if (text) {
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

function renderChatFilesList() {
    const listContainer = document.getElementById('chat-files-list');
    const emptyState = document.getElementById('chat-files-empty');
    if (!listContainer) return;
    listContainer.innerHTML = '';

    // Collect all files from current session attachments & messages
    const files = [];
    const seen = new Set();

    // 1. Current active attachments
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

    // 2. Scan all messages in DOM
    const msgEls = document.querySelectorAll('#chat-messages .message');
    msgEls.forEach(el => {
        // Document badge
        const docBadge = el.querySelector('.msg-attachment-badge');
        if (docBadge) {
            const fname = docBadge.getAttribute('data-filename') || docBadge.textContent.trim();
            const furl = docBadge.getAttribute('data-doc-url') || '';
            const ftype = docBadge.getAttribute('data-file-type') || '';
            const ftext = docBadge.getAttribute('data-doc-text') || '';
            const key = 'doc_' + fname;
            if (fname && !seen.has(key)) {
                seen.add(key);
                files.push({
                    type: 'doc',
                    filename: fname,
                    url: furl,
                    fileType: ftype,
                    textContent: ftext
                });
            }
        }
        // Image attachment
        const imgEl = el.querySelector('.msg-image-thumb');
        if (imgEl) {
            const src = imgEl.getAttribute('data-full-src') || imgEl.getAttribute('src');
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
        } else if (isCodeExt) {
            iconHtml = `<div class="chat-file-card-icon is-code"><i class="ph ph-file-code"></i></div>`;
        } else {
            iconHtml = `<div class="chat-file-card-icon is-doc"><i class="ph ph-file-text"></i></div>`;
        }

        const typeLabel = ext ? ext.toUpperCase() : (f.type === 'image' ? 'IMG' : 'DOC');

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
sendBtn.addEventListener('click', sendMessage);
stopBtn.addEventListener('click', stopGeneration);
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
        if (!isGenerating) {
            e.preventDefault();
            sendMessage();
        }
    }
});

userInput.addEventListener('input', () => {
    adjustInputHeight();
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

function openSettings() {
    settingsModal.classList.remove('hidden');
    loadProfiles();
    loadModels();
    loadPrivacySettings();
    loadMoeSettings();
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

function setAttachedImage(dataUrl, name = 'visual_input.jpg') {
    attachedImage = { dataUrl, name };
    if (imagePreviewThumb) imagePreviewThumb.src = dataUrl;
    if (imagePreviewName) imagePreviewName.textContent = name;
    if (imagePreviewBar) imagePreviewBar.classList.remove('hidden');
}

function clearAttachedImage() {
    attachedImage = null;
    if (imagePreviewBar) imagePreviewBar.classList.add('hidden');
    if (imagePreviewThumb) imagePreviewThumb.src = '';
    if (imageFileInput) imageFileInput.value = '';
}

if (removeImageBtn) {
    removeImageBtn.addEventListener('click', clearAttachedImage);
}

// --- Document Management & Text Extraction ---
function setAttachedDocument(docData) {
    attachedDocument = docData;
    if (docPreviewName) docPreviewName.textContent = docData.filename;
    if (docPreviewSub) {
        const chars = docData.char_count || docData.text.length;
        docPreviewSub.textContent = `${docData.file_type ? docData.file_type.toUpperCase() : 'Dokumen'} · ${chars} karakter · Siap dirangkum/diperbaiki`;
    }
    if (docPreviewBar) docPreviewBar.classList.remove('hidden');
    if (userInput && !userInput.value.trim()) {
        userInput.placeholder = "Ketik perintah (contoh: 'Rangkum isi dokumen ini' atau 'Perbaiki tata bahasanya')...";
    }
}

function clearAttachedDocument() {
    attachedDocument = null;
    if (docPreviewBar) docPreviewBar.classList.add('hidden');
    if (docFileInput) docFileInput.value = '';
    if (userInput) userInput.placeholder = t('input_placeholder');
}

async function uploadDocumentFile(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);

    status.textContent = currentLang === 'en' ? 'Extracting file...' : 'Mengekstrak dokumen...';
    try {
        const res = await fetch('/api/upload/document', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            setAttachedDocument({
                text: data.text,
                filename: data.filename,
                file_type: data.file_type,
                char_count: data.char_count,
                url: data.url
            });
            status.textContent = currentLang === 'en' ? 'File ready' : 'Dokumen siap';
        } else {
            showToast(`${currentLang === 'en' ? 'Failed to read file' : 'Gagal membaca berkas'}: ${data.error || 'Format tidak didukung'}`);
            clearAttachedDocument();
            status.textContent = t('status_ready');
        }
    } catch (err) {
        console.error("Document upload error:", err);
        showToast((currentLang === 'en' ? "Failed to upload file: " : "Gagal mengunggah dokumen: ") + (err.message || "Koneksi bermasalah"));
        clearAttachedDocument();
        status.textContent = t('status_ready');
    }
}

if (uploadDocBtn && docFileInput) {
    uploadDocBtn.addEventListener('click', () => {
        docFileInput.click();
    });

    docFileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            uploadDocumentFile(file);
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
        if (status.textContent.includes('otomatis dijadikan lampiran')) {
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
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
                setAttachedImage(event.target.result, file.name);
            };
            reader.readAsDataURL(file);
        }
    });
}

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

if (openCameraBtn) openCameraBtn.addEventListener('click', startCamera);
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

// Load models for dropdown
async function loadModels() {
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        
        const getModelName = (path) => {
            return path.split('/').pop().replace('.gguf', '');
        };
        
        const badge = document.getElementById('current-model-badge');
        const navPill = document.querySelector('.model-pill');
        if (data.current_model) {
            const modelName = getModelName(data.current_model);
            if (badge) badge.textContent = modelName;
            if (navPill) navPill.textContent = modelName;
        }
        
        const select = document.getElementById('model-select');
        const modelDescText = document.getElementById('model-desc-text');
        
        if (select) {
            select.innerHTML = '';
            if (!data.available_models || data.available_models.length === 0) {
                const option = document.createElement('option');
                option.textContent = 'Tidak ada model ditemukan';
                option.disabled = true;
                select.appendChild(option);
            } else {
                data.available_models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    const info = data.model_info?.[model] || {};
                    const displayName = info.name || getModelName(model);
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
                const info = data.model_info?.[sel] || {};
                if (modelDescText) {
                    modelDescText.textContent = info.description || `Model terpilih: ${getModelName(sel)}`;
                }
            };
        }
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
    
    const getModelName = (path) => {
        return path.split('/').pop().replace('.gguf', '');
    };
    
    const modelName = getModelName(selectedModel);
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
            const visionTag = data.has_vision ? ' (Vision Aktif)' : '';
            showToast(`Model berhasil dialihkan ke ${modelName}${visionTag}`);
            status.textContent = 'Model berhasil dialihkan';
            
            setTimeout(() => {
                loadModels();
                status.textContent = 'Siap';
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

// --- Image Lightbox Modal Controller ---
const imageLightboxModal = document.getElementById('image-lightbox-modal');
const lightboxImg = document.getElementById('lightbox-img');
const lightboxTitle = document.getElementById('lightbox-title');
const lightboxOpenNewtab = document.getElementById('lightbox-open-newtab');
const lightboxDownloadBtn = document.getElementById('lightbox-download-btn');
const closeLightboxBtn = document.getElementById('close-lightbox-btn');

function openImageLightbox(src, title = 'Pratinjau Gambar') {
    if (!imageLightboxModal || !lightboxImg) return;
    lightboxImg.src = src;
    if (lightboxTitle) lightboxTitle.textContent = title;
    if (lightboxOpenNewtab) lightboxOpenNewtab.href = src;
    if (lightboxDownloadBtn) {
        lightboxDownloadBtn.href = src;
        lightboxDownloadBtn.download = `shiro_img_${Date.now()}.jpg`;
    }
    imageLightboxModal.classList.remove('hidden');
}

function closeImageLightbox() {
    if (!imageLightboxModal) return;
    imageLightboxModal.classList.add('hidden');
    if (lightboxImg) lightboxImg.src = '';
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

    // 1. Muat profil, privasi, dan model terlebih dahulu agar avatar & nama sudah siap saat chat di-render
    try {
        await Promise.allSettled([
            loadProfiles(),
            loadPrivacySettings(),
            loadModels()
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
        await loadSessions();
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
                await loadSessions();
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