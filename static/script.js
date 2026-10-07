// DOM Elements
const chatViewport = document.getElementById('chat-viewport');
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const stopBtn = document.getElementById('stop-btn');
const resetBtn = document.getElementById('reset-btn');
const memoryCount = document.getElementById('memory-count');
const status = document.getElementById('status');
const typingIndicator = document.getElementById('typing-indicator');

// Profile data (global)
let userProfile = null;
let aiProfile = null;
let triggerTimer;

// State tracking
let isGenerating = false;
let abortController = null;

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

// Parse message formatting
function parseMessageContent(text) {
    // Escape HTML first
    let escaped = document.createElement('div');
    escaped.textContent = text;
    let content = escaped.innerHTML;
    
    // Replace <3 dengan heart emoji
    content = content.replace(/<3/g, '❤️');
    
    // Parse **bold** text
    content = content.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // Parse *italic/action* text
    content = content.replace(/\*(.+?)\*/g, '<em>$1</em>');
    
    return content;
}

// Global visual attachment state
let attachedImage = null; // { dataUrl: string, name: string }

// Add message ke chat dengan Avatar & Visual Attachment
function addMessage(role, content, imageUrl = null) {
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
    const escapedContent = content
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    
    let attachmentHTML = '';
    if (imageUrl) {
        attachmentHTML = `<img src="${imageUrl}" class="chat-img-attachment" alt="Foto Visual">`;
    }

    // Render HTML Message
    messageDiv.innerHTML = `
        ${role === 'assistant' ? avatarHTML : ''}
        <div class="bubble" data-original-text="${escapedContent}">
            ${attachmentHTML}
            ${formattedContent}
        </div>
        ${role === 'user' ? avatarHTML : ''}
    `;
    
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

// Update memory count
function updateMemoryCount() {
    fetch('/api/memory-count')
        .then(res => res.json())
        .then(data => {
            memoryCount.textContent = data.count;
        })
        .catch(err => console.error("Memory fetch error", err));
}

// Fungsi Toggle Typing Indicator
function showTyping(show) {
    if (show) {
        typingIndicator.classList.remove('hidden');
        // Pindahkan indikator ke paling bawah
        chatViewport.appendChild(typingIndicator);
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

// Send message main function (Teks + Visual Gambar/Kamera)
async function sendMessage() {
    const message = userInput.value.trim();
    if ((!message && !attachedImage) || isGenerating) return;

    clearTimeout(triggerTimer); 
    isGenerating = true;
    userInput.disabled = true;
    sendBtn.disabled = true;
    sendBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');
    
    const sendingImage = attachedImage;
    const currentImgUrl = sendingImage ? sendingImage.dataUrl : null;
    
    userInput.value = '';
    clearAttachedImage();
    
    const displayMsg = message || (sendingImage ? 'Kakak memperlihatkan gambar visual ini.' : '');
    addMessage('user', displayMsg, currentImgUrl);
    
    status.textContent = 'Shiro sedang berpikir...';
    showTyping(true);

    abortController = new AbortController();

    try {
        const payload = { message: message };
        if (currentImgUrl) {
            payload.image = currentImgUrl;
        }

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
            signal: abortController.signal
        });

        if (!response.ok) throw new Error('Network error');

        const data = await response.json();
        
        showTyping(false);
        addMessage('assistant', data.reply);
        
        updateMemoryCount(); 
        status.textContent = 'Siap';
        startTriggerTimer(); 
        
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Request stopped by user');
            showTyping(false);
            status.textContent = 'Dihentikan';
        } else {
            console.error('Error:', error);
            showTyping(false);
            addMessage('system', '⚠️ Error: Gagal terhubung ke Shiro.');
            status.textContent = 'Terputus';
        }
    } finally {
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
            chatMessages.innerHTML = `
                <div class="message assistant">
                    <div class="avatar shiro-avatar">S</div>
                    <div class="bubble">
                        Halo Kakak. Ada yang bisa Shiro bantu hari ini?
                    </div>
                </div>
            `;
            updateMemoryCount();
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
        
        // Simpan System Message
        const systemMsg = chatMessages.firstElementChild;
        chatMessages.innerHTML = '';
        if(systemMsg) chatMessages.appendChild(systemMsg);
        
        // Render History
        data.history.forEach(msg => {
            addMessage(msg.role, msg.content);
        });
        
        updateMemoryCount();
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// Event Listeners
sendBtn.addEventListener('click', sendMessage);
stopBtn.addEventListener('click', stopGeneration);

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        // Shift+Enter = baris baru
        if (e.shiftKey) {
            // Biarkan default behavior (insert newline)
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

// Message action buttons (copy, edit) - like Gemini
let currentBubble = null;

document.addEventListener('mouseover', (e) => {
    const bubble = e.target.closest('.bubble');
    
    // Skip jika bukan user message atau sama dengan bubble sebelumnya
    if (!bubble || !bubble.parentElement.classList.contains('user') || bubble === currentBubble) {
        return;
    }
    
    // Remove actions dari bubble lama
    if (currentBubble) {
        const oldActions = currentBubble.querySelector('.message-actions');
        if (oldActions) oldActions.remove();
    }
    
    // Add action buttons ke bubble baru
    let originalText = bubble.getAttribute('data-original-text') || '';
    originalText = decodeHtmlEntities(originalText); // Decode HTML entities
    currentBubble = bubble;
    
    const actions = document.createElement('div');
    actions.className = 'message-actions';
    actions.innerHTML = `
        <button class="action-btn copy-btn" title="Copy" type="button">
            <i class="ph ph-copy"></i>
        </button>
        <button class="action-btn edit-btn" title="Edit" type="button">
            <i class="ph ph-pencil"></i>
        </button>
    `;
    
    // Copy button handler
    const copyBtn = actions.querySelector('.copy-btn');
    copyBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        navigator.clipboard.writeText(originalText).then(() => {
            const toast = document.createElement('div');
            toast.textContent = 'Tersalin';
            toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#1e293b;border:1px solid #334155;color:#f8fafc;padding:8px 14px;border-radius:6px;font-size:12px;z-index:9999;box-shadow:0 4px 6px -1px rgba(0,0,0,0.3);';
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 1500);
        });
    });
    
    // Edit button handler
    const editBtn = actions.querySelector('.edit-btn');
    editBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        userInput.value = originalText;
        userInput.focus();
        userInput.setSelectionRange(userInput.value.length, userInput.value.length);
    });
    
    bubble.appendChild(actions);
});

// Hide actions saat mouse leave dari message area
document.addEventListener('mouseleave', (e) => {
    const bubble = e.target.closest('.bubble');
    if (bubble && currentBubble === bubble) {
        const actions = bubble.querySelector('.message-actions');
        if (actions) actions.remove();
        currentBubble = null;
    }
}, true);

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
            alert(`✓ ${type} profile saved!`);
            // Reload preview
            loadProfiles();
        }
    } catch (error) {
        console.error('Error saving profile:', error);
        alert('Error saving profile');
    }
}

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const tab = e.target.closest('.tab-btn').dataset.tab;
        
        // Update active tab button
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        e.target.closest('.tab-btn').classList.add('active');
        
        // Update active tab content
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.getElementById(`${tab}-tab`).classList.add('active');
    });
});

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
        alert("Tidak dapat mengakses kamera: " + (err.message || "Izin kamera ditolak."));
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
        alert('Silakan pilih model terlebih dahulu');
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
            const visionTag = data.has_vision ? ' (Multimodal Vision Aktif 👁️)' : '';
            alert(`✓ Model berhasil dialihkan ke ${modelName}${visionTag}`);
            status.textContent = 'Model berhasil dialihkan!';
            
            // Reload models to update UI
            setTimeout(() => {
                loadModels();
                status.textContent = 'Siap';
            }, 600);
        } else {
            alert(`Error: ${data.error}`);
            status.textContent = 'Gagal beralih model';
        }
    } catch (error) {
        console.error('Error switching model:', error);
        alert(`Error: ${error.message}`);
        status.textContent = 'Error';
    }
}

// Settings event listeners
settingsBtn.addEventListener('click', openSettings);
closeSettingsBtn.addEventListener('click', closeSettings);
settingsModal.addEventListener('click', (e) => {
    if (e.target === settingsModal) closeSettings();
});

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadProfiles().then(() => {
        loadChatHistory();
        loadModels(); // Load model awal agar badge dan model pill terisi
        userInput.focus();
    });
});