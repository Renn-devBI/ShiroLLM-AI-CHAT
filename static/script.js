// DOM Elements
const chatViewport = document.getElementById('chat-viewport');
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const stopBtn = document.getElementById('stop-btn');
const resetBtn = document.getElementById('reset-btn');
const memoryCount = document.getElementById('memory-count');
const status = document.getElementById('status');

// Notifikasi singkat non-blocking (menggantikan alert)
function showToast(message, duration = 2200) {
    const stack = document.getElementById('toast-stack');
    if (!stack) { console.log(message); return; }
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => el.remove(), duration);
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
let attachedDocument = null; // { text: string, filename: string, fileType: string, charCount: number }

// Auto-scroll yang lebih pintar
function scrollToBottom() {
    chatViewport.scrollTo({
        top: chatViewport.scrollHeight,
        behavior: 'smooth'
    });
}

// Format waktu simpel
function getCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Inisialisasi Mermaid.js jika tersedia di browser
if (typeof mermaid !== 'undefined') {
    try {
        mermaid.initialize({
            startOnLoad: false,
            theme: 'dark',
            securityLevel: 'loose',
            themeVariables: {
                darkMode: true,
                background: '#1b1c1f',
                primaryColor: '#232428',
                primaryTextColor: '#e8e8ea',
                primaryBorderColor: '#4a4d54',
                lineColor: '#a3a5ab',
                secondaryColor: '#2b2d31',
                tertiaryColor: '#1b1c1f'
            }
        });
    } catch (e) {
        console.warn('[Mermaid Init Warning]:', e);
    }
}

// Tema mermaid mengikuti warna tema aktif
function applyMermaidTheme() {
    if (typeof mermaid === 'undefined') return;
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    const light = window.ShiroTheme ? window.ShiroTheme.isLight(v('--bg-base') || '#161719') : false;
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

    const codeBlocks = [];

    // 1. Ekstrak Fenced Code Blocks: ```lang ... ```
    let content = text.replace(/```([a-zA-Z0-9_\-\.]*)\s*\n?([\s\S]*?)```/g, function(match, lang, code) {
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
                <div class="code-block-wrapper">
                    <div class="code-block-header">
                        <span class="code-lang-label">${displayLang}</span>
                        <button type="button" class="btn-copy-code" onclick="copyCodeSnippet(this)" title="Salin Kode">
                            <i class="ph ph-copy"></i> <span>Salin</span>
                        </button>
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

    // 3. Parse Markdown Images: ![alt](url) -> Clickable lightbox preview
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

    // 5. Parse plain URL menjadi link yang bisa diklik
    const urlRegex = /(https?:\/\/[^\s<>"']+)/g;
    content = content.replace(urlRegex, function(match) {
        let cleanUrl = match.replace(/[.,;!?)]+$/, '');
        let trailing = match.slice(cleanUrl.length);
        return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="chat-link" title="Buka: ${cleanUrl}">${cleanUrl}</a>${trailing}`;
    });

    // Kembalikan placeholder Markdown links
    mdLinks.forEach((linkHtml, idx) => {
        content = content.replace(`___SHIRO_MD_LINK_${idx}___`, linkHtml);
    });

    // 6. Parse inline code: `code`
    content = content.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    // 7. Parse formatting teks
    content = content.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    content = content.replace(/~~(.+?)~~/g, '<del>$1</del>');
    content = content.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // 8. Parse baris baru menjadi <br>
    content = content.replace(/\r\n/g, '\n').replace(/\n/g, '<br>');

    // 9. Pulihkan blok kode & diagram mermaid
    codeBlocks.forEach((blockHtml, idx) => {
        content = content.replace(`___SHIRO_BLOCK_${idx}___`, blockHtml);
    });

    // 10. Markdown Sanitization via DOMPurify jika tersedia
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

// Global visual attachment state
let attachedImage = null; // { dataUrl: string, name: string }

// Helper Actions: Copy Code, Copy Message, Toggle Mermaid, Toggle Status Card, Edit Prompt, Regenerate
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
        if (span) span.textContent = 'Tersalin';
        if (icon) icon.className = 'ph ph-check';
        setTimeout(() => {
            if (span) span.textContent = oldText || 'Salin';
            if (icon) icon.className = 'ph ph-copy';
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

// Add message ke chat dengan Avatar, Dokumen, Status Card, & Visual Attachment
function addMessage(role, content, imageUrl = null, docName = null, docUrl = null, docType = null, docText = null, agentActionData = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    // Tentukan Avatar berdasarkan Role
    let avatarHTML = '';
    if (role === 'assistant') {
        if (aiProfile && aiProfile.image) {
            avatarHTML = `<div class="avatar shiro-avatar"><img src="data:${aiProfile.image_mime};base64,${aiProfile.image}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;"></div>`;
        } else {
            avatarHTML = `<div class="avatar shiro-avatar">${aiProfile?.name?.[0].toUpperCase() || 'S'}</div>`;
        }
    } else if (role === 'user') {
        if (userProfile && userProfile.image) {
            avatarHTML = `<div class="avatar user-avatar"><img src="data:${userProfile.image_mime};base64,${userProfile.image}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;"></div>`;
        } else {
            avatarHTML = `<div class="avatar user-avatar">${userProfile?.name?.[0].toUpperCase() || 'U'}</div>`;
        }
    }

    // Parse formatting dalam content
    const formattedContent = parseMessageContent(content);

    // Escape content untuk HTML attribute
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
        } else if (['py', 'js', 'json', 'html', 'css', 'sql', 'xml'].includes(ext)) {
            iconClass = 'ph-file-code';
            badgeColor = 'badge-code';
            typeLabel = ext.toUpperCase();
        }

        const safeFilename = (docName || 'document').replace(/"/g, '&quot;');
        const safeDocUrl = docUrl || `/api/files/${encodeURIComponent(docName)}`;
        const jsFilename = (docName || 'document').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        const jsUrl = safeDocUrl.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        const jsType = ext.replace(/\\/g, '\\\\').replace(/'/g, "\\'");

        attachmentHTML += `
            <div class="chat-doc-card ${badgeColor}" onclick="openDocModal('${jsFilename}', '${jsUrl}', '${jsType}')" title="Klik untuk membuka dokumen ${safeFilename}">
                <div class="chat-doc-icon">
                    <i class="ph ${iconClass}"></i>
                    <span class="chat-doc-type">${typeLabel}</span>
                </div>
                <div class="chat-doc-info">
                    <div class="chat-doc-name" title="${safeFilename}">${safeFilename}</div>
                    <div class="chat-doc-meta">
                        <span class="chat-doc-action"><i class="ph ph-eye"></i> Lihat dokumen</span>
                    </div>
                </div>
                <button type="button" class="chat-doc-open-btn" onclick="event.stopPropagation(); window.open('${jsUrl}', '_blank')" title="Buka File Asli di Tab Baru">
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

    // Status Card untuk eksekusi Tool Agent
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

    // Message Actions Bar (Edit & Regenerate & Copy)
    let actionsBarHTML = '';
    if (role === 'user') {
        actionsBarHTML = `
            <div class="msg-actions-bar">
                <button type="button" class="btn-msg-action" onclick="editUserPrompt(this)" title="Edit pesan" aria-label="Edit pesan">
                    <i class="ph ph-pencil-simple"></i>
                </button>
                <button type="button" class="btn-msg-action" onclick="copyMessageText(this)" title="Salin pesan" aria-label="Salin pesan">
                    <i class="ph ph-copy"></i>
                </button>
            </div>
        `;
    } else if (role === 'assistant') {
        actionsBarHTML = `
            <div class="msg-actions-bar">
                <button type="button" class="btn-msg-action" onclick="copyMessageText(this)" title="Salin jawaban" aria-label="Salin jawaban">
                    <i class="ph ph-copy"></i>
                </button>
                <button type="button" class="btn-msg-action" onclick="regenerateLastResponse()" title="Buat ulang jawaban" aria-label="Buat ulang jawaban">
                    <i class="ph ph-arrows-clockwise"></i>
                </button>
            </div>
        `;
    }

    // Render HTML Message
    let innerBubbleHTML = '';
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
    scrollToBottom();

    // Post-processing: Syntax Highlighting via highlight.js
    if (typeof hljs !== 'undefined') {
        messageDiv.querySelectorAll('pre code[class*="language-"]').forEach(block => {
            try {
                hljs.highlightElement(block);
            } catch (e) {
                console.warn('[Highlight Warning]:', e);
            }
        });
    }

    // Post-processing: Mermaid Diagrams rendering
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
}

// Update memory count
function updateMemoryCount() {
    fetch('/api/memory-count')
        .then(res => res.json())
        .then(data => {
            if (memoryCount) memoryCount.textContent = data.count;
            if (sidebarMemoryCount) sidebarMemoryCount.textContent = `${data.count} fakta`;
        })
        .catch(err => console.error("Memory fetch error", err));
}

// Fungsi Toggle Typing Indicator & Sinkronisasi Avatar Shiro
function updateTypingIndicatorAvatar() {
    if (!typingIndicator) return;
    const avatarEl = typingIndicator.querySelector('.avatar');
    if (!avatarEl) return;
    if (aiProfile && aiProfile.image) {
        avatarEl.innerHTML = `<img src="data:${aiProfile.image_mime};base64,${aiProfile.image}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
    } else {
        avatarEl.textContent = aiProfile?.name?.[0].toUpperCase() || 'S';
    }
}

function showTyping(show) {
    if (!typingIndicator) return;
    if (show) {
        updateTypingIndicatorAvatar();
        typingIndicator.classList.remove('hidden');
        // Pastikan indikator berada di dalam chatMessages dan di paling bawah pesan
        if (chatMessages) {
            chatMessages.appendChild(typingIndicator);
        }
        scrollToBottom();
    } else {
        typingIndicator.classList.add('hidden');
    }
}

// Trigger inisiatif Shiro setelah hening lama (Inisiatif natural, bukan spam)
function startTriggerTimer() {
    clearTimeout(triggerTimer);
    
    // Tunggu hening 2.5 - 4 menit (150.000 - 240.000 ms), BUKAN 5 detik!
    const naturalDelay = Math.floor(Math.random() * (240000 - 150000 + 1)) + 150000;
    
    triggerTimer = setTimeout(() => {
        // Jangan ganggu jika sedang generate atau Kakak sedang mengetik pesan
        if (isGenerating || (userInput && userInput.value.trim().length > 0)) return; 

        fetch('/api/trigger', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        })
        .then(res => res.json())
        .then(data => {
            if (data.reply && data.status !== 'idle') {
                addMessage('assistant', data.reply); 
                // Cukup 1 inisiatif sampai Kakak membalas — jangan loop panggil startTriggerTimer lagi!
            }
        })
        .catch(err => console.error("Trigger fetch error:", err));
    }, naturalDelay);
}

// Send message main function (Teks + Visual Gambar/Kamera + Dokumen)
async function sendMessage() {
    const message = userInput.value.trim();
    if ((!message && !attachedImage && !attachedDocument) || isGenerating) return;

    clearTimeout(triggerTimer); 
    isGenerating = true;
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
    
    addMessage(
        'user', 
        displayMsg, 
        currentImgUrl, 
        sendingDoc ? sendingDoc.filename : null,
        sendingDoc ? sendingDoc.url : null,
        sendingDoc ? sendingDoc.file_type : null,
        sendingDoc ? sendingDoc.text : null
    );
    
    status.textContent = 'Shiro sedang berpikir...';
    showTyping(true);
    if (pipelineNavDot) pipelineNavDot.classList.remove('hidden');
    startPipelineAnimation(displayMsg);

    abortController = new AbortController();

    try {
        const payload = { message: message };
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
                    status.textContent = 'Siap';
                    return;
                }
                if (errData.error) errorMsg = errData.error;
            } catch (_) {}
            throw new Error(errorMsg);
        }

        const data = await response.json();
        
        showTyping(false);
        const assistantImg = data.assistant_image_url || null;
        addMessage('assistant', data.reply, assistantImg, null, null, null, null, data.agent_action);
        clearPipelineSimulation();
        
        if (data.pipeline_trace) {
            activePipelineTrace = data.pipeline_trace;
            renderModalPipeline(activePipelineTrace);
        }
        
        updateMemoryCount(); 
        loadSessions(); // Perbarui judul sesi otomatis
        status.textContent = 'Siap';
        startTriggerTimer(); 
        
    } catch (error) {
        clearPipelineSimulation();
        if (error.name === 'AbortError') {
            console.log('Request stopped by user');
            showTyping(false);
            status.textContent = 'Dihentikan';
        } else {
            console.error('Error:', error);
            showTyping(false);
            addErrorMessage(error.message || 'Gagal terhubung ke Shiro.', { message: displayMsg });
            status.textContent = 'Siap';
        }
    } finally {
        clearPipelineSimulation();
        if (pipelineNavDot) pipelineNavDot.classList.add('hidden');
        isGenerating = false;
        userInput.disabled = false;
        sendBtn.disabled = false;
        sendBtn.classList.remove('hidden');
        stopBtn.classList.add('hidden');
        userInput.focus();
    }
}

// Stop generation
function stopGeneration() {
    if (abortController) {
        abortController.abort();
    }
}

// Reset memory logic
async function resetMemory() {
    if (!confirm('Lupakan semua percakapan sebelumnya?')) return;

    const originalIcon = resetBtn.innerHTML;
    resetBtn.innerHTML = '<i class="ph ph-spinner ph-spin"></i>'; // Loading icon

    try {
        const response = await fetch('/api/reset', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            // Reset UI
            clearAttachedDocument();
            clearAttachedImage();
            chatMessages.innerHTML = `
                <div class="message assistant">
                    <div class="avatar shiro-avatar">S</div>
                    <div class="bubble">
                        Halo Kakak. Ada yang bisa Shiro bantu hari ini?
                    </div>
                </div>
            `;
            updateMemoryCount();
            await loadSessions();
            status.textContent = 'Memori dibersihkan';
        }
    } catch (error) {
        console.error('Error:', error);
        status.textContent = 'Gagal reset';
    } finally {
        resetBtn.innerHTML = originalIcon;
    }
}

// Load History
async function loadChatHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        
        chatMessages.innerHTML = '';
        
        if (data.history && data.history.length > 0) {
            // Render riwayat obrolan asli
            data.history.forEach(msg => {
                addMessage(
                    msg.role, 
                    msg.content, 
                    msg.image || null, 
                    msg.document_name || null,
                    msg.document_url || null,
                    msg.document_type || null,
                    msg.document_text || null
                );
            });
        } else {
            // Hanya tampilkan sapaan awal jika riwayat chat benar-benar kosong
            const avatarHtml = aiProfile && aiProfile.image ? 
                `<img src="data:${aiProfile.image_mime};base64,${aiProfile.image}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` : 
                (aiProfile?.name?.[0]?.toUpperCase() || 'S');

            chatMessages.innerHTML = `
                <div class="message assistant">
                    <div class="avatar shiro-avatar">${avatarHtml}</div>
                    <div class="bubble">
                        Halo Kakak. Ada yang bisa Shiro bantu hari ini?
                    </div>
                </div>
            `;
        }
        
        if (typingIndicator && chatMessages) {
            chatMessages.appendChild(typingIndicator);
        }
        
        updateMemoryCount();
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// Session & Sidebar Management Functions (Multi-Session with Persistent Memory)
async function loadSessions() {
    try {
        const res = await fetch('/api/sessions');
        const data = await res.json();
        if (data.sessions) {
            activeSessionId = data.active_session_id;

            // Update legacy select if present in DOM
            if (sessionSelect) {
                sessionSelect.innerHTML = '';
                data.sessions.forEach(s => {
                    const opt = document.createElement('option');
                    opt.value = s.id;
                    opt.textContent = s.title || `Chat ${s.id.slice(0, 6)}`;
                    if (s.id === data.active_session_id) {
                        opt.selected = true;
                    }
                    sessionSelect.appendChild(opt);
                });
            }

            // Render modern collapsible sidebar session list
            if (sidebarSessionList) {
                sidebarSessionList.innerHTML = '';
                if (data.sessions.length === 0) {
                    const emptyTip = document.createElement('div');
                    emptyTip.className = 'session-empty';
                    emptyTip.textContent = 'Belum ada riwayat chat.';
                    sidebarSessionList.appendChild(emptyTip);
                } else {
                    data.sessions.forEach(s => {
                        const item = document.createElement('div');
                        item.className = 'session-item' + (s.id === data.active_session_id ? ' active' : '');
                        item.dataset.sessionId = s.id;

                        const content = document.createElement('div');
                        content.className = 'session-item-content';

                        const icon = document.createElement('i');
                        icon.className = 'ph ph-chat-teardrop-text session-item-icon';

                        const titleSpan = document.createElement('span');
                        titleSpan.className = 'session-item-title';
                        titleSpan.textContent = s.title || `Chat ${s.id.slice(0, 6)}`;

                        content.appendChild(icon);
                        content.appendChild(titleSpan);

                        const delBtn = document.createElement('button');
                        delBtn.type = 'button';
                        delBtn.className = 'session-item-delete';
                        delBtn.title = 'Hapus chat ini';
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
        status.textContent = 'Membuat sesi baru...';
        const res = await fetch('/api/sessions/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: 'Chat Baru' })
        });
        const data = await res.json();
        if (data.success) {
            activeSessionId = data.session_id;
            clearAttachedDocument();
            clearAttachedImage();
            
            const avatarHtml = aiProfile && aiProfile.image ? 
                `<img src="data:${aiProfile.image_mime};base64,${aiProfile.image}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` : 
                (aiProfile?.name?.[0]?.toUpperCase() || 'S');

            chatMessages.innerHTML = `
                <div class="message assistant">
                    <div class="avatar shiro-avatar">${avatarHtml}</div>
                    <div class="bubble">
                        Halo Kakak! Sesi obrolan baru siap. Mau bahas atau tanyakan apa sekarang?
                    </div>
                </div>
            `;
            if (typingIndicator && chatMessages) {
                chatMessages.appendChild(typingIndicator);
            }
            await loadSessions();
            updateMemoryCount();
            status.textContent = 'Sesi baru aktif';
            if (userInput) userInput.focus();
        }
    } catch (e) {
        console.error("Error creating new session:", e);
        status.textContent = 'Gagal membuat sesi baru';
    }
}

async function switchSession(sessionId) {
    if (!sessionId || sessionId === activeSessionId || isGenerating) return;
    try {
        status.textContent = 'Memuat sesi...';
        const res = await fetch('/api/sessions/switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });
        const data = await res.json();
        if (data.success) {
            activeSessionId = sessionId;
            clearAttachedDocument();
            clearAttachedImage();

            chatMessages.innerHTML = '';

            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(msg => {
                    addMessage(
                        msg.role, 
                        msg.content, 
                        msg.image || null, 
                        msg.document_name || null,
                        msg.document_url || null,
                        msg.document_type || null,
                        msg.document_text || null
                    );
                });
            } else {
                const avatarHtml = aiProfile && aiProfile.image ? 
                    `<img src="data:${aiProfile.image_mime};base64,${aiProfile.image}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` : 
                    (aiProfile?.name?.[0]?.toUpperCase() || 'S');

                chatMessages.innerHTML = `
                    <div class="message assistant">
                        <div class="avatar shiro-avatar">${avatarHtml}</div>
                        <div class="bubble">
                            Halo Kakak. Ada yang bisa Shiro bantu?
                        </div>
                    </div>
                `;
            }

            if (typingIndicator && chatMessages) {
                chatMessages.appendChild(typingIndicator);
            }

            await loadSessions();
            updateMemoryCount();
            status.textContent = 'Siap';
        }
    } catch (e) {
        console.error("Error switching session:", e);
        status.textContent = 'Gagal ganti sesi';
    }
}

async function deleteSessionById(sessionId, title) {
    if (isGenerating) return;

    const sessionName = title || 'percakapan ini';
    const confirmDelete = confirm(`Hapus "${sessionName}"?\n\nCatatan:\n• Percakapan di sesi ini akan dihapus.\n• Seluruh data pelatihan (training dataset) dan fakta ingatan Shiro tetap tersimpan aman!`);
    if (!confirmDelete) return;

    try {
        status.textContent = 'Menghapus chat...';
        const res = await fetch(`/api/sessions/${sessionId}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (data.success) {
            activeSessionId = data.active_session_id;
            clearAttachedDocument();
            clearAttachedImage();

            chatMessages.innerHTML = '';

            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(msg => {
                    addMessage(
                        msg.role, 
                        msg.content, 
                        msg.image || null, 
                        msg.document_name || null,
                        msg.document_url || null,
                        msg.document_type || null,
                        msg.document_text || null
                    );
                });
            } else {
                const avatarHtml = aiProfile && aiProfile.image ? 
                    `<img src="data:${aiProfile.image_mime};base64,${aiProfile.image}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` : 
                    (aiProfile?.name?.[0]?.toUpperCase() || 'S');

                chatMessages.innerHTML = `
                    <div class="message assistant">
                        <div class="avatar shiro-avatar">${avatarHtml}</div>
                        <div class="bubble">
                            Halo Kakak. Ada yang bisa Shiro bantu hari ini?
                        </div>
                    </div>
                `;
            }

            if (typingIndicator && chatMessages) {
                chatMessages.appendChild(typingIndicator);
            }

            await loadSessions();
            updateMemoryCount();
            status.textContent = 'Chat dihapus. Data training tetap tersimpan aman!';
        } else {
            status.textContent = 'Gagal menghapus chat';
        }
    } catch (e) {
        console.error("Error deleting session:", e);
        status.textContent = 'Error saat menghapus chat';
    }
}

async function deleteCurrentSession() {
    deleteSessionById(activeSessionId);
}

// Sidebar Controls & State Management
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

// Event Listeners for Chat, Sidebar & Sessions
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

// Auto-resize input textarea saat mengetik atau menekan Shift+Enter
function adjustInputHeight() {
    if (!userInput) return;
    userInput.style.height = 'auto';
    const scrollH = userInput.scrollHeight;
    const targetH = Math.min(Math.max(scrollH, 24), 140);
    userInput.style.height = targetH + 'px';
}

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        // Shift+Enter = baris baru (auto-expand tinggi input)
        if (e.shiftKey) {
            setTimeout(adjustInputHeight, 0);
            return;
        }
        // Enter saja = kirim
        if (!isGenerating) {
            e.preventDefault();
            sendMessage();
        }
    }
});

userInput.addEventListener('input', () => {
    adjustInputHeight();
    // Reset timer jika Kakak sedang aktif mengetik agar tidak diganggu
    clearTimeout(triggerTimer);
    startTriggerTimer();
});

resetBtn.addEventListener('click', resetMemory);

// Decode HTML entities
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
    loadModels();  // Load models saat settings dibuka
}

function closeSettings() {
    settingsModal.classList.add('hidden');
}

// Load existing profiles (untuk settings modal & chat display)
async function loadProfiles() {
    try {
        const response = await fetch('/api/profile');
        const data = await response.json();
        
        // Store globally
        userProfile = data.user;
        aiProfile = data.ai;
        
        // Update form if in settings modal
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
                    preview.innerHTML = `<img src="data:${data.user.image_mime};base64,${data.user.image}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
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
                    preview.innerHTML = `<img src="data:${data.ai.image_mime};base64,${data.ai.image}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
                }
            }
        }
        updateTypingIndicatorAvatar();
    } catch (error) {
        console.error('Error loading profiles:', error);
    }
}

// Save profile
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
            showToast(`${type} profile saved!`);
            // Reload preview
            loadProfiles();
        }
    } catch (error) {
        console.error('Error saving profile:', error);
        showToast('Error saving profile');
    }
}

// Tab switching
document.querySelectorAll('#settings-modal .tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const tab = e.target.closest('.tab-btn').dataset.tab;
        
        // Update active tab button
        document.querySelectorAll('#settings-modal .tab-btn').forEach(b => b.classList.remove('active'));
        e.target.closest('.tab-btn').classList.add('active');
        
        // Update active tab content
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
        showToast('API Key berhasil disalin!');
    }).catch(() => {
        input.select();
        document.execCommand('copy');
        showToast('API Key berhasil disalin!');
    });
}

function copyEndpointUrl(path) {
    const fullUrl = window.location.origin + path;
    navigator.clipboard.writeText(fullUrl).then(() => {
        showToast(`URL ${fullUrl} berhasil disalin!`);
    }).catch(() => {
        prompt('Salin URL:', fullUrl);
    });
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
            showToast('API Key baru berhasil di-generate!');
        } else {
            showToast('Gagal generate API Key');
        }
    } catch (e) {
        console.error('Error regenerating API key:', e);
        showToast('Error: ' + e.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// Image preview on select
document.getElementById('user-image').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
            const preview = document.getElementById('user-preview');
            preview.innerHTML = `<img src="${event.target.result}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
        };
        reader.readAsDataURL(file);
    }
});

document.getElementById('ai-image').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
            const preview = document.getElementById('ai-preview');
            preview.innerHTML = `<img src="${event.target.result}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
        };
        reader.readAsDataURL(file);
    }
});

// --- Media & Real-Time Camera Management ---
const imageFileInput = document.getElementById('image-file-input');
const uploadImageBtn = document.getElementById('upload-image-btn');
const openCameraBtn = document.getElementById('open-camera-btn');
const imagePreviewBar = document.getElementById('image-preview-bar');
const imagePreviewThumb = document.getElementById('image-preview-thumb');
const imagePreviewName = document.getElementById('image-preview-name');
const removeImageBtn = document.getElementById('remove-image-btn');

// Camera Elements
const cameraModal = document.getElementById('camera-modal');
const closeCameraModalBtn = document.getElementById('close-camera-modal');
const cameraVideo = document.getElementById('camera-video');
const cameraCanvas = document.getElementById('camera-canvas');
const capturePhotoBtn = document.getElementById('capture-photo-btn');
const switchCameraBtn = document.getElementById('switch-camera-btn');
const cameraPlaceholder = document.getElementById('camera-placeholder');

let cameraStream = null;
let currentCameraFacing = 'user'; // 'user' atau 'environment'

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
        docPreviewSub.textContent = `${docData.file_type ? docData.file_type.toUpperCase() : 'Dokumen'} • ${chars} karakter • Siap dirangkum/diperbaiki`;
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
    if (userInput) userInput.placeholder = "Ketik pesan...";
}

async function uploadDocumentFile(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);

    status.textContent = 'Mengekstrak dokumen...';
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
            status.textContent = 'Dokumen siap';
        } else {
            showToast(`Gagal membaca berkas: ${data.error || 'Format tidak didukung'}`);
            clearAttachedDocument();
            status.textContent = 'Siap';
        }
    } catch (err) {
        console.error("Document upload error:", err);
        showToast("Gagal mengunggah dokumen: " + (err.message || "Koneksi bermasalah"));
        clearAttachedDocument();
        status.textContent = 'Siap';
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

// --- Claude-Style Auto-Convert Pasted Code/Text to Document Attachment & Clipboard Image Paste ---
function detectPastedSnippetMeta(text) {
    const trimmed = text.trim();
    const lower = trimmed.toLowerCase();
    
    // HTML detection
    if (lower.startsWith('<!doctype html') || lower.startsWith('<html') || 
        (lower.includes('<div') && lower.includes('</div>')) || 
        (lower.includes('<body') && lower.includes('</body>')) ||
        (lower.includes('<head') && lower.includes('</head>'))) {
        return { filename: 'snippet.html', ext: 'html' };
    }
    // SVG detection
    if (lower.startsWith('<svg') || (lower.includes('<svg') && lower.includes('</svg>'))) {
        return { filename: 'image.svg', ext: 'svg' };
    }
    // JSON detection
    if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
        try {
            JSON.parse(trimmed);
            return { filename: 'data.json', ext: 'json' };
        } catch (_) {}
    }
    // Python detection
    if (/^\s*(import\s+\w+|from\s+\w+\s+import|def\s+\w+\s*\(|class\s+\w+[\s:(]|if\s+__name__\s*==\s*['"]__main__['"])/m.test(trimmed)) {
        return { filename: 'script.py', ext: 'py' };
    }
    // CSS detection
    if (/^\s*([.#][\w-]+\s*\{|@media|@keyframes|:root\s*\{)/m.test(trimmed) && trimmed.includes('{') && trimmed.includes('}')) {
        return { filename: 'style.css', ext: 'css' };
    }
    // JavaScript / TypeScript detection
    if (/^\s*(const\s+\w+\s*=|let\s+\w+\s*=|var\s+\w+\s*=|function\s+\w*\s*\(|console\.(log|error|warn)\(|export\s+(default\s+)?(function|class|const))/m.test(trimmed) || /=>\s*\{/.test(trimmed)) {
        return { filename: 'script.js', ext: 'js' };
    }
    // SQL detection
    if (/^\s*(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE)\s+/i.test(trimmed)) {
        return { filename: 'query.sql', ext: 'sql' };
    }
    // Markdown detection
    if (/^#+\s+.+/m.test(trimmed) || (trimmed.includes('```') && trimmed.includes('\n'))) {
        return { filename: 'document.md', ext: 'md' };
    }
    // Default plain text
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
        // 1. Cek apakah ada file gambar dari clipboard (misal tangkapan layar / Win+Shift+S)
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

        // 2. Claude-style auto-convert: Jika paste teks panjang (>= 1200 karakter atau >= 25 baris dengan panjang >= 400 karakter)
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

if (openCameraBtn) {
    openCameraBtn.addEventListener('click', startCamera);
}

if (closeCameraModalBtn) {
    closeCameraModalBtn.addEventListener('click', closeCamera);
}

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
        
        console.log('Models loaded:', data);
        
        const getModelName = (path) => {
            return path.split('/').pop().replace('.gguf', '');
        };
        
        // Update current model badge & topbar pill
        const badge = document.getElementById('current-model-badge');
        const navPill = document.querySelector('.model-pill');
        if (data.current_model) {
            const modelName = getModelName(data.current_model);
            if (badge) badge.textContent = modelName;
            if (navPill) navPill.textContent = modelName;
        }
        
        // Populate dropdown & description
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
    } catch (error) {
        console.error('Error loading models:', error);
        const badge = document.getElementById('current-model-badge');
        if (badge) {
            badge.textContent = 'Error loading';
        }
    }
}

// Switch model function
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
            status.textContent = 'Model berhasil dialihkan!';
            
            // Reload models to update UI
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

// Settings event listeners
settingsBtn.addEventListener('click', openSettings);
closeSettingsBtn.addEventListener('click', closeSettings);
settingsModal.addEventListener('click', (e) => {
    if (e.target === settingsModal) closeSettings();
});

// --- Neural Workflow Modal (n8n Real-Time Pipeline Inspector) ---
const pipelineBtn = document.getElementById('pipeline-btn');
const pipelineModal = document.getElementById('pipeline-modal');
const closePipelineModalBtn = document.getElementById('close-pipeline-modal');
const pipelineNavDot = document.getElementById('pipeline-nav-dot');
const pipelineTotalTime = document.getElementById('pipeline-total-time');
const pipelineFrame = document.getElementById('pipeline-frame');

let activePipelineTrace = null;
let pipelineFrameReady = false;
let pipelineSimTimers = [];

// Kirim trace terbaru ke editor kanvas (iframe). Editor hanya memperbarui
// status node, posisi dan sambungan yang diatur pengguna tidak disentuh.
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
    
    // Create an initial active simulated trace
    activePipelineTrace = {
        total_duration_ms: 0,
        nodes: [
            { id: "node_input", name: "Input Ingestion", type: "trigger", icon: "ph-chat-circle-dots", color: "#3b82f6", status: "running", duration_ms: 0, summary: "Menerima input chat...", data_in: { message: userInputText }, data_out: {} },
            { id: "node_emotion", name: "Emotion & Tone Classifier", type: "analyzer", icon: "ph-heartbeat", color: "#ec4899", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_memory", name: "Cognitive Memory & RDF Retrieval", type: "database", icon: "ph-brain", color: "#8b5cf6", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_prompt", name: "Dynamic Prompt Synthesizer", type: "transform", icon: "ph-brackets-curly", color: "#06b6d4", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_llm", name: "Neural Inference Engine", type: "ai_model", icon: "ph-cpu", color: "#f59e0b", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_filter", name: "Anti-Hallucination & CoT Filter", type: "filter", icon: "ph-shield-check", color: "#10b981", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_state", name: "State & Persistence Sync", type: "persistence", icon: "ph-database", color: "#6366f1", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} },
            { id: "node_output", name: "Response Delivery Stream", type: "output", icon: "ph-paper-plane-right", color: "#3b82f6", status: "idle", duration_ms: 0, summary: "Menunggu...", data_in: {}, data_out: {} }
        ]
    };
    renderModalPipeline(activePipelineTrace);

    // Step 1: Input ingestion finishes
    pipelineSimTimers.push(setTimeout(() => {
        if (!activePipelineTrace || !activePipelineTrace.nodes) return;
        activePipelineTrace.nodes[0].status = 'success';
        activePipelineTrace.nodes[0].duration_ms = 14;
        activePipelineTrace.nodes[0].summary = `${(userInputText || '').length} Karakter`;
        activePipelineTrace.nodes[1].status = 'running';
        activePipelineTrace.nodes[1].summary = 'Menganalisis emosi & tone...';
        renderModalPipeline(activePipelineTrace);
    }, 120));

    // Step 2: Emotion finishes
    pipelineSimTimers.push(setTimeout(() => {
        if (!activePipelineTrace || !activePipelineTrace.nodes) return;
        activePipelineTrace.nodes[1].status = 'success';
        activePipelineTrace.nodes[1].duration_ms = 10;
        activePipelineTrace.nodes[1].summary = 'Tone terklasifikasi';
        activePipelineTrace.nodes[2].status = 'running';
        activePipelineTrace.nodes[2].summary = 'Mengambil memori...';
        renderModalPipeline(activePipelineTrace);
    }, 280));

    // Step 3: Memory finishes
    pipelineSimTimers.push(setTimeout(() => {
        if (!activePipelineTrace || !activePipelineTrace.nodes) return;
        activePipelineTrace.nodes[2].status = 'success';
        activePipelineTrace.nodes[2].duration_ms = 28;
        activePipelineTrace.nodes[2].summary = 'Memori dimuat';
        activePipelineTrace.nodes[3].status = 'running';
        activePipelineTrace.nodes[3].summary = 'Menyusun prompt...';
        renderModalPipeline(activePipelineTrace);
    }, 480));

    // Step 4: Prompt finishes, LLM begins running
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
        pipelineFrame.src = '/pipeline?embed=1';   // dimuat sekali, state kanvas tetap hidup
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

// Pipeline modal event listeners
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
    if (docModalSub) docModalSub.textContent = `Pratinjau Berkas (${ext.toUpperCase()})`;
    
    const fileUrl = url || `/api/files/${encodeURIComponent(filename)}`;
    if (docModalDownloadLink) {
        docModalDownloadLink.href = fileUrl;
    }

    if (docModalIcon) {
        if (ext === 'pdf') {
            docModalIcon.className = 'ph ph-file-pdf';
        } else if (['doc', 'docx'].includes(ext)) {
            docModalIcon.className = 'ph ph-file-doc';
        } else if (['csv', 'tsv'].includes(ext)) {
            docModalIcon.className = 'ph ph-file-csv';
        } else if (['py', 'js', 'json', 'html', 'css', 'sql'].includes(ext)) {
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

    if (docModalTextDisplay) {
        docModalTextDisplay.textContent = "Sedang membaca isi berkas...";
    }

    // Jika berkas adalah lampiran yang teksnya tersimpan langsung di memori (misal dari hasil Paste kode Claude-style)
    if (attachedDocument && attachedDocument.filename === filename && attachedDocument.text) {
        currentDocModalContent = attachedDocument.text;
        if (docModalTextDisplay) {
            docModalTextDisplay.textContent = currentDocModalContent;
        }
        if (docModalSub) {
            docModalSub.textContent = `${ext.toUpperCase()} • ${currentDocModalContent.length.toLocaleString()} karakter • Teks Terlampir`;
        }
        docViewerModal.classList.remove('hidden');
        return;
    }
    
    try {
        const res = await fetch(`/api/document/preview?filename=${encodeURIComponent(filename)}`);
        if (res.ok) {
            const data = await res.json();
            currentDocModalContent = data.text || "// Dokumen kosong atau tidak memiliki teks yang dapat diekstrak.";
            if (docModalTextDisplay) {
                docModalTextDisplay.textContent = currentDocModalContent;
            }
            if (docModalSub) {
                const chars = data.char_count || currentDocModalContent.length;
                docModalSub.textContent = `${ext.toUpperCase()} • ${chars.toLocaleString()} karakter • ${data.page_count ? data.page_count + ' halaman' : 'Teks terurai'}`;
            }
        } else {
            if (docModalTextDisplay) {
                docModalTextDisplay.textContent = `Dokumen '${filename}' siap diunduh atau dibuka langsung.\nKlik 'Buka Asli' untuk membuka file lengkap.`;
            }
        }
    } catch (err) {
        if (docModalTextDisplay) {
            docModalTextDisplay.textContent = `Gagal memuat teks: ${err.message || 'Error koneksi'}`;
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
            copyBtn.innerHTML = '<i class="ph ph-check"></i> Tersalin!';
            setTimeout(() => { copyBtn.innerHTML = oldHtml; }, 2000);
        }
    } catch (err) {
        console.error("Gagal menyalin teks:", err);
    }
}

if (closeDocModalBtn) closeDocModalBtn.addEventListener('click', closeDocModal);

// Global Keyboard Shortcuts (Escape to close any open modal)
window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (imageLightboxModal && !imageLightboxModal.classList.contains('hidden')) {
            closeImageLightbox();
        } else if (docViewerModal && !docViewerModal.classList.contains('hidden')) {
            closeDocModal();
        } else if (pipelineModal && !pipelineModal.classList.contains('hidden')) {
            closePipelineModal();
        } else if (settingsModal && !settingsModal.classList.contains('hidden')) {
            closeSettings();
        }
    }
});

// Click listener on image preview thumbnail before sending
if (imagePreviewThumb) {
    imagePreviewThumb.style.cursor = 'pointer';
    imagePreviewThumb.title = 'Klik untuk melihat pratinjau gambar';
    imagePreviewThumb.addEventListener('click', () => {
        if (attachedImage && attachedImage.dataUrl) {
            openImageLightbox(attachedImage.dataUrl, attachedImage.name || 'Pratinjau Lampiran Gambar');
        }
    });
}

// Click listener on doc preview card before sending
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
document.addEventListener('DOMContentLoaded', () => {
    initSidebarState();
    loadProfiles().then(() => {
        loadChatHistory();
        loadSessions(); // Load daftar sesi percakapan
        loadModels(); // Load model awal agar badge dan model pill terisi
        userInput.focus();
    });
});

// --- Pengaturan tema (tab "Tema") ---
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
