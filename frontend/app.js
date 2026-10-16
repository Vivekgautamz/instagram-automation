/* ══════════════════════════════════════════════════════════════════════════
   Instagram Automation Dashboard — Frontend Application
   ══════════════════════════════════════════════════════════════════════════ */

const API = (typeof window !== 'undefined' && window.location.origin && window.location.origin.startsWith('http')) ? '' : 'http://127.0.0.1:8501';
let currentPage = 'dashboard';
let ws = null;
let logEntries = [];
let autoPostStatus = { running: false };
let selectedAutoPostAccount = '';
let selectedAutoPostMode = 'all'; // 'all' (Images + Reels), 'images', 'reels'
let autoPostAccountsList = [];

// ── Mobile Navigation Helpers ────────────────────────────────────────────────
function toggleMobileSidebar() {
    const sb = document.getElementById("sidebar");
    const bd = document.getElementById("sidebar-backdrop");
    if (!sb) return;
    const isOpen = sb.classList.toggle("open");
    if (bd) bd.classList.toggle("open", isOpen);
}
function closeMobileSidebar() {
    const sb = document.getElementById("sidebar");
    const bd = document.getElementById("sidebar-backdrop");
    if (sb) sb.classList.remove("open");
    if (bd) bd.classList.remove("open");
}
function toggleMobileMoreMenu() {
    const sheet = document.getElementById("mobile-more-sheet");
    const bd = document.getElementById("mobile-more-backdrop");
    if (!sheet) return;
    const isOpen = sheet.classList.toggle("open");
    if (bd) bd.classList.toggle("open", isOpen);
}
function closeMobileMoreMenu() {
    const sheet = document.getElementById("mobile-more-sheet");
    const bd = document.getElementById("mobile-more-backdrop");
    if (sheet) sheet.classList.remove("open");
    if (bd) bd.classList.remove("open");
}
window.toggleMobileSidebar = toggleMobileSidebar;
window.closeMobileSidebar = closeMobileSidebar;
window.toggleMobileMoreMenu = toggleMobileMoreMenu;
window.closeMobileMoreMenu = closeMobileMoreMenu;

// ── API Helpers ──────────────────────────────────────────────────────────────

async function api(path, options = {}) {
    const url = `${API}${path}`;
    const opts = { headers: { 'Content-Type': 'application/json' }, ...options };
    if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
        opts.body = JSON.stringify(opts.body);
    }
    if (opts.body instanceof FormData) {
        delete opts.headers['Content-Type'];
    }
    const res = await fetch(url, opts);
    if (!res.ok) {
        const errText = await res.text();
        let message = errText;
        try {
            const parsed = JSON.parse(errText);
            message = parsed.detail || parsed.message || errText;
        } catch (_) {}
        throw new Error(message);
    }
    return res.json();
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toString();
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

function toast(message, type = 'info') {
    const container = document.getElementById('toasts');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

function copyPathToClipboard(path) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(path).then(() => {
            toast('Copied full path to clipboard!', 'info');
        }).catch(() => {
            toast(path, 'info');
        });
    } else {
        toast(path, 'info');
    }
}

// ── WebSocket ────────────────────────────────────────────────────────────────

function connectWebSocket() {
    const isSamePort = (typeof window !== 'undefined' && window.location.origin && window.location.origin.startsWith('http') && window.location.port === '8501');
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const targetHost = isSamePort ? location.host : '127.0.0.1:8501';
    ws = new WebSocket(`${proto}//${targetHost}/ws/logs`);
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'log') {
            logEntries.unshift(data);
            if (logEntries.length > 500) logEntries.pop();
            updateLogViewer();
            if (data.level === 'success') toast(data.message, 'success');
            if (data.level === 'error') toast(data.message, 'error');
        }
        if (data.type === 'progress') {
            autoPostStatus.progress = data;
            updateProgressUI(data);
        }
        if (data.type === 'auto_post_done') {
            autoPostStatus.running = false;
            if (currentPage === 'auto-post') navigate('auto-post');
            if (currentPage === 'dashboard') navigate('dashboard');
            toast(`Auto-post complete! Posted: ${data.posted}, Failed: ${data.failed}`, 'success');
        }
    };
    ws.onclose = () => setTimeout(connectWebSocket, 3000);
    ws.onerror = () => ws.close();
}

// ── Router ───────────────────────────────────────────────────────────────────

function navigate(page) {
    currentPage = page;
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.page === page);
    });
    document.querySelectorAll('.mobile-nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.page === page);
    });
    closeMobileMoreMenu();
    closeMobileSidebar();
    const titles = {
        'dashboard': 'Dashboard',
        'auto-post': 'Auto Post',
        'bot': 'Interactive Viral Reel Bot',
        'post-image': 'Post Image',
        'post-reel': 'Post Reel',
        'download': 'Download Media',
        'queue': 'Media Queue',
        'posted': 'Posted Media',
        'logs': 'Activity Log',
        'settings': 'Settings',
    };
    document.getElementById('page-title').textContent = titles[page] || 'Dashboard';
    const content = document.getElementById('page-content');

    const renderers = {
        'dashboard': renderDashboard,
        'auto-post': renderAutoPost,
        'bot': renderInteractiveBot,
        'post-image': renderPostImage,
        'post-reel': renderPostReel,
        'download': renderDownload,
        'queue': renderQueue,
        'posted': renderPosted,
        'logs': renderLogs,
        'settings': renderSettings,
    };

    const renderer = renderers[page] || renderDashboard;
    renderer(content);
}

// ── Pages ────────────────────────────────────────────────────────────────────

async function renderDashboard(el) {
    const activeUname = currentActiveUser || (document.getElementById('active-account')?.textContent || '').replace('@', '').trim() || 'poetghazipur61';
    el.innerHTML = `
        <div class="mobile-dashboard-welcome">
            <div class="mobile-welcome-badge">✨ InstaBot Automation</div>
            <div class="mobile-welcome-title">Welcome Back, @${escapeHtml(activeUname)}</div>
            <div class="mobile-welcome-sub">Let's grow your Instagram audience!</div>
        </div>
        <div class="stat-grid" id="stat-grid">
            <div class="stat-card"><div class="stat-label">Images Waiting</div><div class="stat-value accent" id="s-img-wait">—</div></div>
            <div class="stat-card"><div class="stat-label">Reels Waiting</div><div class="stat-value accent" id="s-reel-wait">—</div></div>
            <div class="stat-card"><div class="stat-label">Images Posted</div><div class="stat-value success" id="s-img-posted">—</div></div>
            <div class="stat-card"><div class="stat-label">Reels Posted</div><div class="stat-value success" id="s-reel-posted">—</div></div>
            <div class="stat-card stat-card-failed"><div class="stat-label">Failed</div><div class="stat-value error" id="s-failed">—</div></div>
        </div>
        <div class="section-card">
            <div class="flex-between" style="margin-bottom:12px">
                <div class="section-title" style="margin-bottom:0">📋 Recent Activity</div>
                <button class="btn btn-ghost" style="padding:4px 10px;font-size:12px" onclick="navigate('logs')">View All &gt;</button>
            </div>
            <div class="log-viewer" id="dashboard-log">${renderLogEntries(logEntries.slice(0, 15))}</div>
        </div>`;
    try {
        const stats = await api('/api/stats');
        document.getElementById('s-img-wait').textContent = formatNumber(stats.images_waiting);
        document.getElementById('s-reel-wait').textContent = formatNumber(stats.reels_waiting);
        document.getElementById('s-img-posted').textContent = formatNumber(stats.images_posted);
        document.getElementById('s-reel-posted').textContent = formatNumber(stats.reels_posted);
        document.getElementById('s-failed').textContent = formatNumber(stats.failed);
    } catch (e) {
        toast('Failed to load stats', 'error');
    }
}

function formatModeLabel(mode) {
    if (mode === 'images') return 'Images only';
    if (mode === 'reels') return 'Reels only';
    return 'Images + Reels';
}

function renderAutoPostAccountItems() {
    if (!autoPostAccountsList || autoPostAccountsList.length === 0) {
        const u = selectedAutoPostAccount || 'poetghazipur61';
        return `
            <div class="ap-account-item selected" onclick="selectAutoPostAccount('${u}')">
                <span class="ap-account-item-left">
                    <span class="ap-cam-icon">📸</span>
                    <span class="ap-item-uname">@${u}</span>
                </span>
                <span class="ap-checkmark">✓</span>
            </div>`;
    }

    return autoPostAccountsList.map(a => {
        const uname = typeof a === 'string' ? a : a.username;
        const isSelected = (uname === selectedAutoPostAccount);
        return `
            <div class="ap-account-item ${isSelected ? 'selected' : ''}" onclick="selectAutoPostAccount('${uname}')">
                <span class="ap-account-item-left">
                    <span class="ap-cam-icon">📸</span>
                    <span class="ap-item-uname">@${uname}</span>
                </span>
                ${isSelected ? '<span class="ap-checkmark">✓</span>' : ''}
            </div>
        `;
    }).join('');
}

function toggleAutoPostAccountMenu(event) {
    if (event) event.stopPropagation();
    const menu = document.getElementById('ap-account-menu');
    const chevron = document.getElementById('ap-account-chevron');
    if (!menu) return;
    const isOpen = menu.classList.contains('show');
    if (isOpen) {
        menu.classList.remove('show');
        if (chevron) chevron.textContent = '▼';
    } else {
        menu.classList.add('show');
        if (chevron) chevron.textContent = '▲';
    }
}

async function selectAutoPostAccount(username) {
    selectedAutoPostAccount = username;
    const triggerText = document.getElementById('ap-selected-account-text');
    if (triggerText) triggerText.textContent = `@${username}`;

    const itemsList = document.getElementById('ap-account-items-list');
    if (itemsList) itemsList.innerHTML = renderAutoPostAccountItems();

    const menu = document.getElementById('ap-account-menu');
    const chevron = document.getElementById('ap-account-chevron');
    if (menu) menu.classList.remove('show');
    if (chevron) chevron.textContent = '▼';

    // Fetch and dynamically update unposted ready counts for this specific account
    try {
        const imgReady = document.getElementById('ap-images-ready');
        const reelReady = document.getElementById('ap-reels-ready');
        if (imgReady) imgReady.textContent = '...';
        if (reelReady) reelReady.textContent = '...';

        const stats = await api(`/api/stats?account=${encodeURIComponent(username)}`);
        if (imgReady) imgReady.textContent = formatNumber(stats.images_waiting);
        if (reelReady) reelReady.textContent = formatNumber(stats.reels_waiting);
    } catch (_) {}
}

function selectAutoPostMode(mode) {
    selectedAutoPostMode = mode;
    document.querySelectorAll('.ap-mode-option').forEach(el => {
        const radio = el.querySelector('input');
        if (radio && radio.value === mode) {
            el.classList.add('active');
            radio.checked = true;
        } else {
            el.classList.remove('active');
            if (radio) radio.checked = false;
        }
    });
}

function openAddAccountModal(event) {
    if (event) event.stopPropagation();
    const menu = document.getElementById('ap-account-menu');
    const chevron = document.getElementById('ap-account-chevron');
    if (menu) menu.classList.remove('show');
    if (chevron) chevron.textContent = '▼';

    const modal = document.getElementById('ap-add-account-modal');
    if (modal) {
        modal.style.display = 'flex';
        const input = document.getElementById('ap-new-username');
        if (input) { input.value = ''; input.focus(); }
        const display = document.getElementById('ap-new-display');
        if (display) display.value = '';
        const session = document.getElementById('ap-new-session');
        if (session) session.value = '';
        const status = document.getElementById('ap-modal-status');
        if (status) { status.style.display = 'none'; status.innerHTML = ''; }
    }
}

function closeAddAccountModal() {
    const modal = document.getElementById('ap-add-account-modal');
    if (modal) modal.style.display = 'none';
}

function autoFillSessionPath(val) {
    const clean = val.trim().replace(/^@/, '');
    const sessionInput = document.getElementById('ap-new-session');
    if (sessionInput) {
        if (clean) {
            sessionInput.value = `sessions/${clean}.json`;
        } else {
            sessionInput.value = '';
        }
    }
}

async function submitQuickAddAccount() {
    const usernameEl = document.getElementById('ap-new-username');
    const displayEl = document.getElementById('ap-new-display');
    const sessionEl = document.getElementById('ap-new-session');
    const statusEl = document.getElementById('ap-modal-status');
    const btn = document.getElementById('btn-save-new-account');
    if (!usernameEl) return;

    const username = usernameEl.value.trim().replace(/^@/, '');
    if (!username) { toast('Enter an Instagram username', 'warning'); return; }
    const display_name = displayEl ? displayEl.value.trim() : '';
    const session_file = sessionEl ? sessionEl.value.trim() : `sessions/${username}.json`;

    btn.disabled = true;
    btn.textContent = 'Saving...';
    if (statusEl) {
        statusEl.style.display = 'block';
        statusEl.innerHTML = '<span style="color:var(--accent)">Adding account...</span>';
    }

    try {
        const res = await api('/api/account/add', {
            method: 'POST',
            body: { username, display_name, session_file, set_active: false }
        });
        toast(`Account @${res.username} added!`, 'success');
        closeAddAccountModal();

        // Refresh topbar and global account list
        await loadAccount();

        // Refresh local accounts list
        const accData = await api('/api/accounts');
        autoPostAccountsList = accData.accounts || [];

        // Select the newly added account
        await selectAutoPostAccount(username);
    } catch (e) {
        if (statusEl) {
            statusEl.innerHTML = `<span style="color:var(--error)">Failed: ${e.message || e}</span>`;
        }
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save & Select';
    }
}

function handleAutoPostOutsideClick(e) {
    const dropdown = document.getElementById('ap-account-dropdown');
    if (dropdown && !dropdown.contains(e.target)) {
        const menu = document.getElementById('ap-account-menu');
        const chevron = document.getElementById('ap-account-chevron');
        if (menu && menu.classList.contains('show')) {
            menu.classList.remove('show');
            if (chevron) chevron.textContent = '▼';
        }
    }
}

function setupAutoPostListeners() {
    document.removeEventListener('click', handleAutoPostOutsideClick);
    document.addEventListener('click', handleAutoPostOutsideClick);
}

async function renderAutoPost(el) {
    const status = await api('/api/auto-post/status').catch(() => ({ running: false }));
    autoPostStatus = status;

    if (status.running) {
        const activeAcc = status.account || selectedAutoPostAccount || currentActiveUser || 'poetghazipur61';
        const modeLabel = formatModeLabel(status.mode || selectedAutoPostMode || 'all');
        el.innerHTML = `
            <div class="section-card auto-post-hero">
                <h2>🚀 Auto Post Running</h2>
                <div class="ap-active-meta">
                    <span class="ap-account-badge">📸 @${activeAcc}</span>
                    <span class="ap-mode-badge">${modeLabel}</span>
                </div>
                <p>Processing your media queue automatically. Unposted items are processed sequentially with AI-generated captions.</p>
                <div class="progress-container" id="ap-progress">
                    <div class="progress-header">
                        <span id="ap-file">Initializing...</span>
                        <span id="ap-pct">0%</span>
                    </div>
                    <div class="progress-bar"><div class="progress-fill" id="ap-fill" style="width:0%"></div></div>
                    <div class="progress-detail" id="ap-detail"></div>
                </div>
                <button class="btn btn-danger btn-lg" onclick="stopAutoPost()">⬛ STOP AUTO POST</button>
            </div>
            <div class="section-card">
                <div class="section-title">📝 Live Activity Log</div>
                <div class="log-viewer" id="live-log">${renderLogEntries(logEntries.slice(0, 30))}</div>
            </div>`;
        if (status.progress) updateProgressUI(status.progress);
        return;
    }

    // Load available accounts
    try {
        const accData = await api('/api/accounts');
        autoPostAccountsList = accData.accounts || [];
        if (!selectedAutoPostAccount) {
            selectedAutoPostAccount = accData.active || (autoPostAccountsList[0] ? (typeof autoPostAccountsList[0] === 'string' ? autoPostAccountsList[0] : autoPostAccountsList[0].username) : 'poetghazipur61');
        }
    } catch (_) {
        if (!selectedAutoPostAccount) selectedAutoPostAccount = currentActiveUser || 'poetghazipur61';
        autoPostAccountsList = [{ username: selectedAutoPostAccount }];
    }

    // Fetch stats for the selected account
    let stats = { images_waiting: 0, reels_waiting: 0 };
    try {
        stats = await api(`/api/stats?account=${encodeURIComponent(selectedAutoPostAccount)}`);
    } catch (_) {}

    el.innerHTML = `
        <div class="section-card auto-post-hero">
            <h2>🚀 Auto Post</h2>
            <p>Automatically post all media in your queue. Images and Reels will be processed sequentially with AI-generated captions.</p>

            <div class="stat-grid ap-stat-grid" style="max-width:440px;margin:0 auto 28px">
                <div class="stat-card">
                    <div class="stat-label">IMAGES READY</div>
                    <div class="stat-value accent" id="ap-images-ready">${formatNumber(stats.images_waiting)}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">REELS READY</div>
                    <div class="stat-value accent" id="ap-reels-ready">${formatNumber(stats.reels_waiting)}</div>
                </div>
            </div>

            <div class="ap-form-container">
                <!-- Account Selector -->
                <div class="ap-field-group">
                    <div class="ap-group-title">POST TO INSTAGRAM</div>
                    <div class="ap-account-dropdown-wrapper" id="ap-account-dropdown">
                        <button type="button" class="ap-account-btn" id="ap-account-trigger" onclick="toggleAutoPostAccountMenu(event)">
                            <span class="ap-account-btn-content">
                                <span class="ap-cam-icon">📸</span>
                                <span class="ap-account-name" id="ap-selected-account-text">@${selectedAutoPostAccount}</span>
                            </span>
                            <span class="ap-chevron" id="ap-account-chevron">▼</span>
                        </button>
                        <div class="ap-account-menu" id="ap-account-menu">
                            <div class="ap-account-items-list" id="ap-account-items-list">
                                ${renderAutoPostAccountItems()}
                            </div>
                            <div class="ap-account-menu-divider"></div>
                            <button type="button" class="ap-account-add-item" onclick="openAddAccountModal(event)">
                                <span class="ap-add-icon">➕</span>
                                <span>Add Instagram Account</span>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Post Mode Selector -->
                <div class="ap-field-group">
                    <div class="ap-group-title">POST MODE</div>
                    <div class="ap-mode-selector">
                        <label class="ap-mode-option ${selectedAutoPostMode === 'all' ? 'active' : ''}" onclick="selectAutoPostMode('all')">
                            <input type="radio" name="ap-post-mode" value="all" ${selectedAutoPostMode === 'all' ? 'checked' : ''} style="display:none">
                            <span class="ap-radio-dot"></span>
                            <span class="ap-mode-label">Images + Reels</span>
                        </label>
                        <label class="ap-mode-option ${selectedAutoPostMode === 'images' ? 'active' : ''}" onclick="selectAutoPostMode('images')">
                            <input type="radio" name="ap-post-mode" value="images" ${selectedAutoPostMode === 'images' ? 'checked' : ''} style="display:none">
                            <span class="ap-radio-dot"></span>
                            <span class="ap-mode-label">Images only</span>
                        </label>
                        <label class="ap-mode-option ${selectedAutoPostMode === 'reels' ? 'active' : ''}" onclick="selectAutoPostMode('reels')">
                            <input type="radio" name="ap-post-mode" value="reels" ${selectedAutoPostMode === 'reels' ? 'checked' : ''} style="display:none">
                            <span class="ap-radio-dot"></span>
                            <span class="ap-mode-label">Reels only</span>
                        </label>
                    </div>
                </div>

                <button class="btn btn-primary btn-lg ap-start-btn" onclick="startAutoPost()">
                    ▶ START AUTO POST
                </button>
            </div>
        </div>

        <!-- Quick Add Account Modal -->
        <div id="ap-add-account-modal" class="ap-modal-backdrop" style="display:none" onclick="if(event.target===this)closeAddAccountModal()">
            <div class="ap-modal-box">
                <div class="ap-modal-header">
                    <h3>➕ Add Instagram Account</h3>
                    <button type="button" class="ap-modal-close" onclick="closeAddAccountModal()">&times;</button>
                </div>
                <div class="ap-modal-body">
                    <p class="ap-modal-desc">Add a new Instagram account to post to. Session file will be automatically linked.</p>
                    <div class="form-group" style="text-align:left">
                        <label>Instagram Username</label>
                        <input type="text" id="ap-new-username" class="form-input" placeholder="e.g. psychology.yaarr" oninput="autoFillSessionPath(this.value)">
                    </div>
                    <div class="form-group" style="text-align:left">
                        <label>Display Name (optional)</label>
                        <input type="text" id="ap-new-display" class="form-input" placeholder="e.g. Psychology Yaarr">
                    </div>
                    <div class="form-group" style="text-align:left">
                        <label>Session File Path</label>
                        <input type="text" id="ap-new-session" class="form-input" placeholder="sessions/username.json">
                    </div>
                    <div id="ap-modal-status" style="display:none;margin-top:10px"></div>
                </div>
                <div class="ap-modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="closeAddAccountModal()">Cancel</button>
                    <button type="button" class="btn btn-primary" id="btn-save-new-account" onclick="submitQuickAddAccount()">Save & Select</button>
                </div>
            </div>
        </div>
    `;

    setupAutoPostListeners();
}

// ── Interactive Bot (Repost As-Is & AI Generate Modes) ─────────────────────

let botJob = null;
let botPollTimer = null;
let botEditingCaption = false;
let botEditingHashtags = false;
let currentActiveUser = '';
let botMode = 'repost_as_is'; // 'repost_as_is' | 'ai_generate'
let botAccountsList = [];
let botSelectedAccount = '';
let botSlideIndex = 0;
let botForceDuplicate = false;
let botAutoPost = localStorage.getItem('bot_auto_post') === '1';
let botMainUrl = '';

function toggleBotAutoPost() {
    botAutoPost = !botAutoPost;
    localStorage.setItem('bot_auto_post', botAutoPost ? '1' : '0');
    toast(`Switched to ${botAutoPost ? 'Automatic (Auto Download & Post)' : 'Manual Review'} Mode`, 'info');
    if (currentPage === 'bot') {
        renderInteractiveBot(document.getElementById('page-content'));
    }
}

function syncBotUrls(val) {
    botMainUrl = val;
    const mainInput = document.getElementById('bot-url-input');
    const manualInput = document.getElementById('bot-manual-url-input');
    if (mainInput && mainInput.value !== val) mainInput.value = val;
    if (manualInput && manualInput.value !== val) manualInput.value = val;
}

function handleBotUrlPaste(e) {
    const pasted = (e.clipboardData || window.clipboardData)?.getData('text');
    if (!pasted) return;
    const url = pasted.trim();
    syncBotUrls(url);
    if (botAutoPost && (url.includes('instagram.com/reel/') || url.includes('instagram.com/p/') || url.includes('instagram.com/tv/'))) {
        setTimeout(() => {
            startBotWorkflow(true);
        }, 150);
    }
}

function triggerBotSubmit() {
    const val = botMainUrl || document.getElementById('bot-url-input')?.value?.trim() || document.getElementById('bot-manual-url-input')?.value?.trim() || '';
    if (!val) {
        toast('Please paste an Instagram Reel, Photo, or Carousel URL', 'warning');
        return;
    }
    syncBotUrls(val);
    if (botAutoPost) {
        startBotWorkflow(true);
    } else {
        startBotWorkflow(false);
    }
}

function resetBot() {
    if (botPollTimer) {
        clearInterval(botPollTimer);
        botPollTimer = null;
    }
    botJob = null;
    botMainUrl = '';
    botSlideIndex = 0;
    botForceDuplicate = false;
    botEditingCaption = false;
    botEditingHashtags = false;
    if (currentPage === 'bot') {
        renderInteractiveBot(document.getElementById('page-content'));
    }
}

function setBotMode(mode) {
    botMode = mode;
    if (botJob && botJob.candidate) {
        if (mode === 'repost_as_is') {
            botJob.customCaption = botJob.candidate.original_caption || '';
            botJob.customHashtags = botJob.candidate.original_hashtags || '';
        } else if (botJob.analysis && !botJob.analysis.is_repost_as_is) {
            botJob.customCaption = botJob.analysis.caption || '';
            botJob.customHashtags = botJob.analysis.hashtags || '';
        }
    }
    if (currentPage === 'bot') {
        renderInteractiveBot(document.getElementById('page-content'));
    }
}

function selectBotSlide(idx) {
    botSlideIndex = idx;
    if (currentPage === 'bot') {
        renderInteractiveBot(document.getElementById('page-content'));
    }
}

function setBotAccount(uname) {
    botSelectedAccount = uname;
    currentActiveUser = uname;
    botForceDuplicate = false;
    if (currentPage === 'bot') {
        renderInteractiveBot(document.getElementById('page-content'));
    }
}

function getBotDisplayCaption() {
    if (!botJob) return '';
    if (botJob.customCaption !== undefined) return botJob.customCaption;
    if (botMode === 'repost_as_is') {
        return (botJob.candidate && botJob.candidate.original_caption) || (botJob.analysis && botJob.analysis.caption) || '';
    }
    return (botJob.analysis && botJob.analysis.caption) || (botJob.candidate && botJob.candidate.original_caption) || '';
}

function getBotDisplayHashtags() {
    if (!botJob) return '';
    if (botJob.customHashtags !== undefined) return botJob.customHashtags;
    if (botMode === 'repost_as_is') {
        return (botJob.candidate && botJob.candidate.original_hashtags) || (botJob.analysis && botJob.analysis.hashtags) || '';
    }
    return (botJob.analysis && botJob.analysis.hashtags) || (botJob.candidate && botJob.candidate.original_hashtags) || '';
}

function renderBotAudioSection(candidate, download, isAnalyzing, isDownloading) {
    if (isAnalyzing) {
        return `
            <div class="bot-audio-box checking mt-12">
                <div class="bot-audio-header">
                    <span class="bot-audio-icon pulse">🎵</span>
                    <strong>Audio Track:</strong>
                    <span class="audio-badge checking">Checking source...</span>
                </div>
                <div class="bot-audio-sub">
                    Detecting original audio and music metadata from Instagram...
                </div>
            </div>
        `;
    }

    if (!candidate) return '';

    const postType = (download && download.post_type) ? download.post_type : (candidate.post_type || (candidate.is_video ? 'reel' : 'image'));
    const audio = (download && download.audio_info) ? download.audio_info : (candidate.audio_info || null);
    const hasDownload = Boolean(download && download.filename);

    const isDetected = Boolean(audio && audio.detected);
    const trackName = (audio && audio.track_name) || (isDetected ? 'Original audio' : '');
    const artistName = (audio && audio.artist_name) || (isDetected ? ('@' + (candidate.creator || 'creator')) : '');
    const isEmbedded = Boolean(audio && audio.is_embedded);

    // ── CASE 1: Carousel / Single Image Post ──────────────────────────────────
    if (postType === 'carousel' || postType === 'image') {
        if (!isDetected) {
            return `
                <div class="bot-audio-box neutral mt-12">
                    <div class="bot-audio-header">
                        <span class="bot-audio-icon">🎵</span>
                        <strong>Audio Track:</strong>
                        <span class="audio-badge neutral">No audio detected</span>
                    </div>
                    <div class="bot-audio-sub">
                        Original post has no associated audio track.
                    </div>
                </div>
            `;
        }

        // Audio detected on photo/carousel
        return `
            <div class="bot-audio-box success mt-12">
                <div class="bot-audio-header">
                    <span class="bot-audio-icon">🎵</span>
                    <strong>Audio Track:</strong>
                    <span class="audio-badge success">
                        ${hasDownload ? `Original audio detected — <code>${escapeHtml(trackName)}</code>` : 'Original audio detected'}
                    </span>
                </div>
                <div class="audio-details-table">
                    <div class="audio-detail-row">
                        <span class="detail-label">Track:</span>
                        <span class="detail-val"><strong>${escapeHtml(trackName)}</strong></span>
                    </div>
                    ${artistName ? `
                    <div class="audio-detail-row">
                        <span class="detail-label">Artist:</span>
                        <span class="detail-val">${escapeHtml(artistName)}</span>
                    </div>
                    ` : ''}
                    <div class="audio-detail-row">
                        <span class="detail-label">Status:</span>
                        <span class="detail-val text-success" style="font-weight:600">Available for repost</span>
                    </div>
                </div>
                ${hasDownload ? `
                <div class="audio-sub-checks">
                    <div><span class="check">✓</span> Audio information captured</div>
                    <div><span class="check">✓</span> Embedded audio preserved when present</div>
                </div>
                ` : ''}
                <div class="audio-notice-muted">
                    ℹ Note: Instagram audio catalog licensing is separate for photos/carousels. Original track info preserved.
                </div>
            </div>
        `;
    }

    // ── CASE 2: Reel / Video Post ─────────────────────────────────────────────
    if (!isDetected) {
        return `
            <div class="bot-audio-box neutral mt-12">
                <div class="bot-audio-header">
                    <span class="bot-audio-icon">🎵</span>
                    <strong>Audio Track:</strong>
                    <span class="audio-badge neutral">No audio detected</span>
                </div>
                <div class="bot-audio-sub">
                    No active audio stream detected on source media.
                </div>
            </div>
        `;
    }

    // Reel with audio
    if (hasDownload) {
        if (isEmbedded) {
            return `
                <div class="bot-audio-box success mt-12">
                    <div class="bot-audio-header">
                        <span class="bot-audio-icon">🎵</span>
                        <strong>Audio Track:</strong>
                        <span class="audio-badge success">Detected</span>
                    </div>
                    <div class="audio-details-table">
                        <div class="audio-detail-row">
                            <span class="detail-label">🎧 Original audio / Song name:</span>
                            <span class="detail-val"><strong>${escapeHtml(trackName)}</strong></span>
                        </div>
                        <div class="audio-detail-row">
                            <span class="detail-label">👤 Artist / Creator:</span>
                            <span class="detail-val">${escapeHtml(artistName || ('@' + (candidate.creator || 'creator')))}</span>
                        </div>
                    </div>
                    <div class="audio-notice-embedded">
                        <span class="check">✓</span> <strong>Audio embedded in downloaded video</strong>
                    </div>
                    <div class="audio-sub-checks">
                        <div><span class="check">✓</span> Audio information captured</div>
                        <div><span class="check">✓</span> Embedded audio preserved when present</div>
                    </div>
                </div>
            `;
        } else {
            // Audio detected on source, BUT NOT embedded in downloaded media
            return `
                <div class="bot-audio-box warning mt-12">
                    <div class="bot-audio-header">
                        <span class="bot-audio-icon">🎵</span>
                        <strong>Audio Track:</strong>
                        <span class="audio-badge warning">Detected on source</span>
                    </div>
                    <div class="audio-details-table">
                        <div class="audio-detail-row">
                            <span class="detail-label">Track:</span>
                            <span class="detail-val"><strong>${escapeHtml(trackName)}</strong></span>
                        </div>
                        ${artistName ? `
                        <div class="audio-detail-row">
                            <span class="detail-label">Artist:</span>
                            <span class="detail-val">${escapeHtml(artistName)}</span>
                        </div>
                        ` : ''}
                    </div>
                    <div class="audio-warning-notice">
                        <span>⚠</span> <strong>Audio is not embedded in downloaded media</strong>
                    </div>
                    <div class="audio-notice-muted">
                        ℹ Instagram audio selection may be required
                    </div>
                </div>
            `;
        }
    } else {
        // Pre-download preview state
        return `
            <div class="bot-audio-box success mt-12">
                <div class="bot-audio-header">
                    <span class="bot-audio-icon">🎵</span>
                    <strong>Audio Track:</strong>
                    <span class="audio-badge success">Detected</span>
                </div>
                <div class="audio-details-table">
                    <div class="audio-detail-row">
                        <span class="detail-label">🎧 Original audio / Song name:</span>
                        <span class="detail-val"><strong>${escapeHtml(trackName)}</strong></span>
                    </div>
                    <div class="audio-detail-row">
                        <span class="detail-label">👤 Artist / Creator:</span>
                        <span class="detail-val">${escapeHtml(artistName || ('@' + (candidate.creator || 'creator')))}</span>
                    </div>
                </div>
                <div class="bot-audio-sub">
                    ✓ Audio stream detected on source (will be verified & preserved upon download)
                </div>
            </div>
        `;
    }
}

async function renderInteractiveBot(el) {
    // Load accounts list and active account
    if (!botAccountsList || botAccountsList.length === 0 || !botSelectedAccount) {
        try {
            const accData = await api('/api/accounts');
            botAccountsList = accData.accounts || [];
            if (!botSelectedAccount) {
                botSelectedAccount = accData.active || (botAccountsList[0] ? (typeof botAccountsList[0] === 'string' ? botAccountsList[0] : botAccountsList[0].username) : 'psychology.yaarr');
            }
            currentActiveUser = botSelectedAccount;
        } catch (_) {
            if (!botSelectedAccount) botSelectedAccount = 'psychology.yaarr';
            botAccountsList = [{ username: botSelectedAccount }];
            currentActiveUser = botSelectedAccount;
        }
    }

    const job = botJob;
    const isAnalyzing = job && (job.status === 'analyzing');
    const isDownloading = job && (job.status === 'downloading' || job.status === 'analyzing_video');
    const isPublishing = job && (job.status === 'publishing');
    const hasCandidate = job && job.candidate;
    const hasDownload = job && job.download;
    const hasAnalysis = job && job.analysis;
    const isPublished = job && job.status === 'published' && job.publish;

    const candidate = job ? job.candidate : null;
    const postType = candidate ? (candidate.post_type || (candidate.is_video ? 'reel' : 'image')) : 'reel';
    const isCarousel = postType === 'carousel';

    // Duplicate check for selected account
    const postedAccounts = candidate ? (candidate.posted_accounts || []) : [];
    const isAlreadyPostedToSelected = postedAccounts.map(a => a.toLowerCase()).includes((botSelectedAccount || currentActiveUser).toLowerCase());

    const selAccountObj = (botAccountsList || []).find(a => (typeof a === 'string' ? a : a.username).toLowerCase() === (botSelectedAccount || currentActiveUser || '').toLowerCase());
    const isSelectedExpired = Boolean(selAccountObj && (selAccountObj.is_authenticated === false || (selAccountObj.status || '').toLowerCase().includes('expired') || (selAccountObj.status || '').toLowerCase() === 'not authenticated' || (selAccountObj.status || '').toLowerCase() === 'session_expired'));
    const isSelectedRestricted = Boolean(selAccountObj && (selAccountObj.status || '').toLowerCase() === 'publishing_restricted');
    const isAuthRequired = Boolean(job && (job.status === 'auth_required' || (job.error && (job.error.includes('login_required') || job.error.includes('AUTHENTICATION_REQUIRED') || job.error.includes('upload_settings')))));

    const getStepStatus = (stepKey) => {
        if (!job) return 'pending';
        const order = [
            'url_received',
            'searching',
            'candidate_found',
            'downloading',
            'analyzing_video',
            'generating_caption',
            'generating_hashtags',
            'ready_to_publish',
            'published'
        ];
        const curIdx = order.indexOf(job.step || 'url_received');
        const targetIdx = order.indexOf(stepKey);
        if (job.status === 'published') return 'done';
        if (job.status === 'failed' && curIdx === targetIdx) return 'failed';
        if (curIdx > targetIdx) return 'done';
        if (curIdx === targetIdx) return 'active';
        return 'pending';
    };

    const getStepIcon = (status) => {
        if (status === 'done') return '✓';
        if (status === 'active') return '⏳';
        if (status === 'failed') return '❌';
        return '○';
    };

    el.innerHTML = `
        <!-- Top Banner -->
        <div class="bot-top-banner">
            <div class="bot-top-title">
                <h2>🤖 Interactive Bot</h2>
                <p>Repost original Instagram content as-is (Carousels 1..N, Photos, Reels) or generate AI captions with verified publishing</p>
            </div>
            <div class="account-pill">
                <span class="dot"></span>
                <span>@${(botSelectedAccount || currentActiveUser).toUpperCase()}</span>
            </div>
        </div>

        <!-- Auto Download & Post Toggle Card -->
        <div class="bot-toggle-card">
            <div class="bot-toggle-header">
                <button type="button" class="btn-bot-toggle ${botAutoPost ? 'on' : 'off'}" onclick="toggleBotAutoPost()" title="Click to switch between Automatic and Manual modes">
                    <span class="toggle-dot"></span>
                    <span>${botAutoPost ? '🟢 ON — Automatic' : '🔴 OFF — Manual'}</span>
                </button>
                <span class="bot-toggle-title">Auto Download & Post</span>
                <span class="bot-toggle-acc">@${botSelectedAccount || currentActiveUser}</span>
            </div>

            <div class="bot-url-label">🔗 REEL / CAROUSEL / PHOTO URL</div>
            <div class="bot-main-url-container">
                <input 
                    type="url" 
                    id="bot-url-input" 
                    class="bot-main-url-input" 
                    placeholder="📋 Paste Instagram URL (Reel, Photo, Carousel 1..N)" 
                    value="${escapeHtml(botMainUrl || (job ? (job.url || '') : ''))}" 
                    oninput="syncBotUrls(this.value)" 
                    onpaste="handleBotUrlPaste(event)" 
                    onkeydown="if(event.key === 'Enter') triggerBotSubmit()" 
                    ${isAnalyzing || isDownloading || isPublishing ? 'disabled' : ''}
                />
            </div>

            <div class="bot-mode-hint">
                ${botAutoPost 
                    ? `⚡ <strong>Automatic Mode:</strong> Paste URL → Automatically analyzes, downloads &amp; publishes to <strong>@${botSelectedAccount || currentActiveUser}</strong>` 
                    : `👉 <strong>Manual Mode:</strong> Paste URL → Click 'Analyze Post' below → Edit details &amp; Publish`}
            </div>

            <div class="bot-action-bar">
                <button class="btn-bot-action-refresh" onclick="${job ? 'resetBot()' : 'triggerBotSubmit()'}" title="${job ? 'Reset URL' : (botAutoPost ? 'Execute Auto Download & Post' : 'Check URL')}">
                    <span class="action-icon">🔄</span>
                </button>
            </div>
        </div>

        <!-- Target Content Review Card (Manual Mode) -->
        ${!botAutoPost ? `
        <div class="bot-review-card">
            <div class="bot-review-header">
                <h3>🔍 Target Content Review (Manual Mode)</h3>
                <p>Analyze post metadata before downloading or publishing</p>
            </div>
            <div class="bot-review-input-group">
                <input 
                    type="url" 
                    id="bot-manual-url-input" 
                    class="form-input" 
                    placeholder="https://www.instagram.com/p/... or https://www.instagram.com/reel/..." 
                    value="${escapeHtml(botMainUrl || (job ? (job.url || '') : ''))}" 
                    oninput="syncBotUrls(this.value)" 
                    onkeydown="if(event.key === 'Enter') startBotWorkflow(false)" 
                    ${isAnalyzing || isDownloading || isPublishing ? 'disabled' : ''}
                />
                <button 
                    class="btn btn-analyze-white" 
                    id="bot-analyze-btn" 
                    onclick="startBotWorkflow(false)" 
                    ${isAnalyzing || isDownloading || isPublishing ? 'disabled' : ''}
                >
                    ${isAnalyzing ? '⏳ Analyzing...' : '🔍 Analyze Post'}
                </button>
            </div>
        </div>
        ` : ''}

        <!-- Repost Mode Selection Card -->
        <div class="bot-mode-card">
            <div class="section-title" style="margin-bottom:6px">🔄 REPOST MODE</div>
            <div class="bot-mode-options">
                <div class="bot-mode-option ${botMode === 'repost_as_is' ? 'active' : ''}" onclick="setBotMode('repost_as_is')">
                    <input type="radio" class="bot-mode-radio" name="bot-mode-choice" value="repost_as_is" ${botMode === 'repost_as_is' ? 'checked' : ''}>
                    <div>
                        <div class="bot-mode-title">⚡ Repost As-Is (Recommended)</div>
                        <div class="bot-mode-desc">Preserve original media (Carousels 1..N in order), copy exact original caption &amp; hashtags without AI rewriting, and preserve audio.</div>
                    </div>
                </div>
                <div class="bot-mode-option ${botMode === 'ai_generate' ? 'active' : ''}" onclick="setBotMode('ai_generate')">
                    <input type="radio" class="bot-mode-radio" name="bot-mode-choice" value="ai_generate" ${botMode === 'ai_generate' ? 'checked' : ''}>
                    <div>
                        <div class="bot-mode-title">✨ AI Caption + Hashtags</div>
                        <div class="bot-mode-desc">Analyze visual media and generate a brand-new, customized viral caption and trending hashtags using AI.</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Workflow Checklist (visible when job exists) -->
        ${job ? `
        <div class="workflow-card">
            <div class="flex-between">
                <div class="section-title" style="margin-bottom:0">📊 PROCESSING WORKFLOW</div>
                <span style="font-size:12px;color:var(--accent);font-weight:600">${job.progress || 0}%</span>
            </div>
            <div class="progress-bar mt-16" style="margin-bottom:14px">
                <div class="progress-fill" style="width:${job.progress || 0}%"></div>
            </div>
            <div class="workflow-steps">
                <div class="wf-step ${getStepStatus('url_received')}">
                    <span>${getStepIcon(getStepStatus('url_received'))}</span>
                    <span>URL received</span>
                </div>
                <div class="wf-step ${getStepStatus('searching')}">
                    <span>${getStepIcon(getStepStatus('searching'))}</span>
                    <span>Searching Instagram</span>
                </div>
                <div class="wf-step ${getStepStatus('candidate_found')}">
                    <span>${getStepIcon(getStepStatus('candidate_found'))}</span>
                    <span>Post detected</span>
                </div>
                <div class="wf-step ${getStepStatus('downloading')}">
                    <span>${getStepIcon(getStepStatus('downloading'))}</span>
                    <span>Downloading media</span>
                </div>
                ${botMode === 'ai_generate' ? `
                <div class="wf-step ${getStepStatus('analyzing_video')}">
                    <span>${getStepIcon(getStepStatus('analyzing_video'))}</span>
                    <span>Analyzing content</span>
                </div>
                <div class="wf-step ${getStepStatus('generating_caption')}">
                    <span>${getStepIcon(getStepStatus('generating_caption'))}</span>
                    <span>Generating caption</span>
                </div>
                ` : `
                <div class="wf-step ${getStepStatus('downloading') === 'done' || getStepStatus('ready_to_publish') === 'done' || getStepStatus('ready_to_publish') === 'active' ? 'done' : 'pending'}">
                    <span>✓</span>
                    <span>Preserving original text</span>
                </div>
                `}
                <div class="wf-step ${getStepStatus('ready_to_publish')}">
                    <span>${getStepIcon(getStepStatus('ready_to_publish'))}</span>
                    <span>Ready to publish</span>
                </div>
            </div>
            ${isAnalyzing && !hasCandidate ? renderBotAudioSection(null, null, true, false) : ''}
            ${job.error ? `<div class="log-entry error mt-16" style="border-radius:var(--radius-sm)"><span class="log-msg">❌ ${job.error}</span></div>` : ''}
        </div>
        ` : ''}

        <!-- Published Success Card -->
        ${isPublished ? `
        <div class="bot-published-card">
            <h3>✓ ${postType.toUpperCase()} REPOSTED SUCCESSFULLY</h3>
            <p style="color:var(--text-secondary);font-size:13px;margin-bottom:14px">Published to verified account: <strong>@${job.publish.account}</strong></p>
            <div class="meta-row" style="max-width:540px;margin:0 auto;background:var(--bg-main);padding:10px 16px;border-radius:var(--radius-sm)">
                <span class="meta-label">Instagram URL</span>
                <span class="meta-val"><a href="${job.publish.instagram_url}" target="_blank" style="color:var(--accent)">${job.publish.instagram_url}</a></span>
            </div>
            <div class="btn-group-actions">
                <a class="btn btn-primary" href="${job.publish.instagram_url}" target="_blank">🔗 Open on Instagram</a>
                <button class="btn btn-ghost" onclick="navigate('posted')">📋 View in Posted</button>
                <button class="btn btn-primary" onclick="resetBot()">🔄 Repost Another Item</button>
            </div>
        </div>
        ` : ''}

        <!-- Publishing Restricted Banner -->
        ${job && job.status === 'publishing_restricted' ? `
        <div class="section-card" style="border:1.5px solid #f59e0b;background:rgba(245,158,11,0.08)">
            <div style="display:flex;align-items:flex-start;gap:14px">
                <span style="font-size:28px;line-height:1">⚠️</span>
                <div style="flex:1">
                    <div style="font-weight:700;font-size:15px;color:#f59e0b;margin-bottom:6px">INSTAGRAM ACTION RESTRICTED for @${botSelectedAccount || currentActiveUser}</div>
                    <div style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">
                        Instagram has temporarily restricted posting activity for this account.<br>
                        <strong style="color:var(--text)">This is an Instagram-side restriction — not a session or login problem.</strong>
                    </div>
                    <div style="font-size:12.5px;color:var(--text-muted);line-height:1.7">
                        ${job.error ? `<div style="background:rgba(0,0,0,0.2);border-radius:6px;padding:8px 12px;margin-bottom:10px;font-family:monospace;font-size:11px;word-break:break-word">${escapeHtml(job.error)}</div>` : ''}
                        <strong>What to do:</strong><br>
                        • Wait <strong>24–48 hours</strong> before retrying on @${botSelectedAccount || currentActiveUser}<br>
                        • Try posting via the <strong>official Instagram app</strong> in the meantime<br>
                        • Switch to a different account that isn't restricted<br>
                        • Open the Instagram app to check for any security prompts
                    </div>
                    <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
                        <button class="btn btn-ghost" onclick="setBotAccount('${botSelectedAccount || currentActiveUser}'); navigate('settings')">⚙️ Manage Accounts</button>
                        <button class="btn btn-primary" onclick="resetBot()">🔄 Try Another URL</button>
                    </div>
                </div>
            </div>
        </div>
        ` : ''}

        <!-- Candidate Result Card -->
        ${hasCandidate && !isPublished ? `
        <div class="candidate-card">
            <div class="flex-between">
                <div class="section-title" style="margin-bottom:0">🎬 Post Details</div>
                <div>
                    ${isCarousel ? `
                        <span class="post-type-badge carousel">🖼️ Carousel • ${candidate.item_count || (candidate.items_preview ? candidate.items_preview.length : 1)} items</span>
                    ` : (postType === 'image' ? `
                        <span class="post-type-badge image">📸 Single Image</span>
                    ` : `
                        <span class="post-type-badge reel">🎬 Reel / Video</span>
                    `)}
                </div>
            </div>

            <!-- Carousel Slide Thumbnails (if multiple items) -->
            ${isCarousel ? `
            <div style="margin-top:14px">
                <div style="font-size:12px;font-weight:700;color:var(--text-secondary);letter-spacing:0.5px">
                    ORIGINAL MEDIA (1..${candidate.item_count || 1} IN ORDER)
                </div>
                <div class="carousel-slides-bar">
                    ${(candidate.items_preview || []).map((slide, idx) => `
                        <div class="carousel-slide-thumb ${botSlideIndex === idx ? 'active' : ''}" onclick="selectBotSlide(${idx})" title="Slide ${slide.index}">
                            ${slide.thumbnail ? `<img src="${slide.thumbnail}" alt="Slide ${slide.index}">` : `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#fff;font-size:11px">[${slide.index}]</div>`}
                            <span class="carousel-slide-badge">[${slide.index}]</span>
                        </div>
                    `).join('')}
                </div>
            </div>
            ` : ''}

            <div class="candidate-grid mt-16">
                <!-- Preview Box -->
                <div class="candidate-preview-box">
                    ${hasDownload ? (
                        (job.download.post_type === 'carousel' || job.download.media_type === 'image') ? `
                            <img 
                                src="/api/media/file/images/new/${(job.download.media_filenames && job.download.media_filenames[botSlideIndex]) ? job.download.media_filenames[botSlideIndex] : job.download.filename}" 
                                style="max-height:380px;width:100%;object-fit:contain;border-radius:var(--radius-sm);" 
                                alt="Slide ${botSlideIndex + 1}" 
                            />
                        ` : `
                            <video src="/api/media/file/reels/new/${job.download.filename}" controls playsinline preload="metadata"></video>
                        `
                    ) : (
                        (candidate.items_preview && candidate.items_preview[botSlideIndex] && candidate.items_preview[botSlideIndex].thumbnail) ? `
                            <img src="${candidate.items_preview[botSlideIndex].thumbnail}" alt="Slide Preview" style="max-height:380px;width:100%;object-fit:contain;border-radius:var(--radius-sm);" />
                        ` : (candidate.thumbnail ? `
                            <img src="${candidate.thumbnail}" alt="Thumbnail" style="max-height:380px;width:100%;object-fit:contain;border-radius:var(--radius-sm);" />
                        ` : `
                            <div style="color:var(--text-muted);text-align:center;padding:20px">
                                <div style="font-size:42px;margin-bottom:8px">📸</div>
                                <span>Media Preview Ready</span>
                            </div>
                        `)
                    )}
                </div>

                <!-- Meta Details -->
                <div class="candidate-info">
                    <div class="meta-table">
                        <div class="meta-row">
                            <span class="meta-label">Original Creator</span>
                            <span class="meta-val">@${candidate.creator || 'creator'}</span>
                        </div>
                        <div class="meta-row">
                            <span class="meta-label">Post Type</span>
                            <span class="meta-val"><strong>${isCarousel ? `Carousel (${candidate.item_count} items)` : (postType === 'image' ? 'Single Image' : 'Reel')}</strong></span>
                        </div>
                        <div class="meta-row">
                            <span class="meta-label">Likes / Views</span>
                            <span class="meta-val">${candidate.likes_formatted || '0'} likes • ${candidate.views_formatted || '0'} views</span>
                        </div>
                        <div class="meta-row">
                            <span class="meta-label">Original URL</span>
                            <span class="meta-val"><a href="${candidate.url}" target="_blank" style="color:var(--accent)">${candidate.url}</a></span>
                        </div>
                        ${hasDownload ? `
                        <div class="meta-row">
                            <span class="meta-label">Total Size</span>
                            <span class="meta-val">${job.download.size_formatted}</span>
                        </div>
                        <div class="meta-row">
                            <span class="meta-label">Download State</span>
                            <span class="ai-status-pill">✓ All ${job.download.item_count || 1} original items downloaded</span>
                        </div>
                        ` : ''}
                    </div>

                    ${!hasDownload ? `
                        <div class="mt-16">
                            <button 
                                class="btn btn-primary btn-lg" 
                                style="width:100%" 
                                onclick="startBotDownload('${job.job_id}')"
                                ${isDownloading ? 'disabled' : ''}
                            >
                                ${isDownloading ? '⏳ Downloading Original Media...' : (botMode === 'repost_as_is' ? '⬇️ Download Media & Prepare Repost' : '⬇️ Download & Analyze Media')}
                            </button>
                        </div>
                    ` : ''}
                </div>
            </div>

            <!-- Repost Integrity Guarantees & Audio Track Check -->
            <div class="bot-preservation-card">
                <div style="font-weight:700;font-size:13px;color:#10b981;display:flex;align-items:center;gap:6px;margin-bottom:12px">
                    <span>🛡️ REPOST INTEGRITY & WATERMARK PRESERVATION</span>
                </div>
                <div class="bot-preservation-grid">
                    <div class="bot-preservation-item">
                        <span class="check">✓</span>
                        <span>Original order preserved (${candidate.item_count || 1} item${candidate.item_count === 1 ? '' : 's'})</span>
                    </div>
                    <div class="bot-preservation-item">
                        <span class="check">✓</span>
                        <span>Original caption copied</span>
                    </div>
                    <div class="bot-preservation-item">
                        <span class="check">✓</span>
                        <span>Original hashtags copied</span>
                    </div>
                    <div class="bot-preservation-item">
                        <span class="check">✓</span>
                        <span>Embedded watermark / text preserved as-is</span>
                    </div>
                    <div class="bot-preservation-item">
                        <span class="check">✓</span>
                        <span>${((job && job.download && job.download.audio_info ? job.download.audio_info.detected : (candidate.audio_info ? candidate.audio_info.detected : false))) ? 'Audio detected' : 'Audio checked (No audio on source)'}</span>
                    </div>
                    <div class="bot-preservation-item">
                        <span class="check">✓</span>
                        <span>Audio availability checked</span>
                    </div>
                </div>

                ${renderBotAudioSection(candidate, job ? job.download : null, isAnalyzing, isDownloading)}
            </div>
        </div>
        ` : ''}

        <!-- Caption & Hashtags Section -->
        ${(hasDownload || hasAnalysis) && !isPublished ? `
        <div class="section-card">
            <div class="flex-between">
                <div class="section-title">
                    ${botMode === 'repost_as_is' ? '📋 ORIGINAL CAPTION & HASHTAGS (AS-IS)' : '🧠 AI GENERATED CAPTION & HASHTAGS'}
                </div>
                <span class="ai-status-pill">${botMode === 'repost_as_is' ? '⚡ Repost As-Is' : '✨ AI Generated'}</span>
            </div>

            <!-- Caption Display/Edit -->
            <div style="margin-top:14px">
                <div class="flex-between">
                    <label style="font-weight:600;font-size:13px;color:var(--text-secondary)">CAPTION</label>
                    <button class="btn btn-ghost" style="padding:4px 10px;font-size:12px" onclick="toggleEditCaption()">
                        ${botEditingCaption ? 'Done' : '✏️ Edit'}
                    </button>
                </div>
                ${botEditingCaption ? `
                    <textarea id="bot-caption-edit" class="box-textarea" rows="4" oninput="updateCustomCaption(this.value)">${getBotDisplayCaption()}</textarea>
                ` : `
                    <div class="box-display" style="white-space:pre-wrap">${getBotDisplayCaption() || '<span style="color:var(--text-muted);font-style:italic">No caption text</span>'}</div>
                `}
            </div>

            <!-- Hashtags Display/Edit -->
            <div style="margin-top:16px">
                <div class="flex-between">
                    <label style="font-weight:600;font-size:13px;color:var(--text-secondary)">HASHTAGS</label>
                    <button class="btn btn-ghost" style="padding:4px 10px;font-size:12px" onclick="toggleEditHashtags()">
                        ${botEditingHashtags ? 'Done' : '✏️ Edit'}
                    </button>
                </div>
                ${botEditingHashtags ? `
                    <textarea id="bot-hashtags-edit" class="box-textarea" rows="3" oninput="updateCustomHashtags(this.value)">${getBotDisplayHashtags()}</textarea>
                ` : `
                    <div class="box-display" style="color:var(--accent);white-space:pre-wrap">${getBotDisplayHashtags() || '<span style="color:var(--text-muted);font-style:italic">No hashtags</span>'}</div>
                `}
            </div>

            <!-- Destination Account Selector & Duplicate Repost Check -->
            <div class="bot-dest-card">
                <div class="flex-between">
                    <label style="font-size:12.5px;font-weight:700;color:var(--text-secondary)">POST TO INSTAGRAM ACCOUNT</label>
                    ${isSelectedExpired || isAuthRequired ? `
                        <span style="font-size:12px;color:#ef4444;font-weight:700">⚠️ Session Expired (login_required)</span>
                    ` : (isSelectedRestricted ? `
                        <span style="font-size:12px;color:#f59e0b;font-weight:700">⚠️ Action Restricted</span>
                    ` : `
                        <span style="font-size:12px;color:#10b981;font-weight:600">✓ Account verified</span>
                    `)}
                </div>
                <select class="form-input mt-8" id="bot-account-select" onchange="setBotAccount(this.value)" ${isPublishing ? 'disabled' : ''}>
                    ${botAccountsList.map(a => {
                        const uname = typeof a === 'string' ? a : a.username;
                        const isExp = (typeof a === 'object') && (a.is_authenticated === false || (a.status || '').toLowerCase().includes('expired'));
                        return `<option value="${uname}" ${uname === (botSelectedAccount || currentActiveUser) ? 'selected' : ''}>@${uname} ${isExp ? '(Expired)' : ''}</option>`;
                    }).join('')}
                </select>

                ${(isSelectedExpired || isAuthRequired) ? `
                <div class="auth-warning-alert" style="background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.35);border-radius:10px;padding:12px 14px;margin-top:12px;display:flex;gap:12px;align-items:center">
                    <span style="font-size:22px">🔑</span>
                    <div style="flex:1">
                        <strong style="color:#ef4444;font-size:13px">Authentication Required for @${botSelectedAccount || currentActiveUser}</strong>
                        <div style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;line-height:1.4">
                            The Instagram session token has expired or been revoked (HTTP 403: login_required). Re-authenticate with your password, 2FA code, or session ID before publishing.
                        </div>
                    </div>
                    <button class="btn btn-primary" style="padding:7px 14px;font-size:12px;white-space:nowrap;background:#ef4444;border-color:#ef4444;color:#fff" onclick="openAccountReconnect('${botSelectedAccount || currentActiveUser}')">
                        🔑 Reconnect Account
                    </button>
                </div>
                ` : ''}

                ${isAlreadyPostedToSelected ? `
                <div class="duplicate-alert">
                    <span style="font-size:18px">⚠️</span>
                    <div style="flex:1">
                        <strong>Already published to @${botSelectedAccount || currentActiveUser}!</strong>
                        <div style="margin-top:2px;font-size:11.5px">This post was already published to this account. You can select another account from the dropdown, or confirm duplicate repost below.</div>
                        <label style="display:flex;align-items:center;gap:6px;margin-top:8px;cursor:pointer;font-weight:600">
                            <input type="checkbox" id="bot-force-dup-cb" onchange="botForceDuplicate = this.checked; renderInteractiveBot(document.getElementById('page-content'))" ${botForceDuplicate ? 'checked' : ''}>
                            <span>Yes, confirm repost to @${botSelectedAccount || currentActiveUser}</span>
                        </label>
                    </div>
                </div>
                ` : ''}

                <button 
                    class="btn-publish mt-16" 
                    id="bot-publish-btn" 
                    onclick="${(isSelectedExpired || isAuthRequired) ? `openAccountReconnect('${botSelectedAccount || currentActiveUser}')` : `publishBotContent('${job.job_id}')`}"
                    ${isPublishing || (isAlreadyPostedToSelected && !botForceDuplicate) ? 'disabled' : ''}
                    style="${(isSelectedExpired || isAuthRequired) ? 'background:#ef4444;border-color:#ef4444;cursor:pointer' : ''}"
                >
                    ${isPublishing ? '⏳ Publishing to Instagram...' : 
                        ((isSelectedExpired || isAuthRequired) ? `🔑 RE-AUTHENTICATE @${botSelectedAccount || currentActiveUser} TO PUBLISH` : 
                        (botMode === 'repost_as_is' ? `✅ ACCEPT & REPOST AS-IS TO @${botSelectedAccount || currentActiveUser}` : `✅ ACCEPT & POST TO @${botSelectedAccount || currentActiveUser}`))}
                </button>
            </div>
        </div>
        ` : ''}

        <!-- Live Activity Log -->
        <div class="section-card">
            <div class="section-title">📝 BOT ACTIVITY</div>
            <div class="log-viewer" id="bot-activity-log" style="max-height:220px">
                ${renderBotLogs(job ? job.logs : [])}
            </div>
        </div>
    `;
}

async function startBotWorkflow(isAuto) {
    const autoMode = (typeof isAuto === 'boolean') ? isAuto : botAutoPost;
    const inputVal = botMainUrl || document.getElementById('bot-url-input')?.value?.trim() || document.getElementById('bot-manual-url-input')?.value?.trim() || '';
    if (!inputVal) {
        toast('Enter an Instagram post, carousel, or reel URL', 'warning');
        return;
    }

    toast(autoMode ? '⚡ Auto Download & Post: Processing content...' : 'Searching & analyzing Instagram content...', 'info');
    botSlideIndex = 0;
    botForceDuplicate = false;
    try {
        const res = await api('/api/bot/analyze', { 
            method: 'POST', 
            body: { 
                url: inputVal, 
                account: botSelectedAccount || currentActiveUser, 
                mode: botMode,
                auto_post: autoMode
            } 
        });
        botJob = {
            job_id: res.job_id,
            url: inputVal,
            mode: botMode,
            status: 'analyzing',
            step: 'url_received',
            auto_post: autoMode,
            progress: 20,
            message: 'URL received',
            logs: [{ timestamp: new Date().toLocaleTimeString(), message: `URL received (${autoMode ? 'Automatic Mode' : 'Manual Mode'})` }]
        };
        startPollingBot(res.job_id);
        if (currentPage === 'bot') {
            renderInteractiveBot(document.getElementById('page-content'));
        }
    } catch (e) {
        toast(`Workflow failed: ${e.message || e}`, 'error');
    }
}

function startBotAnalysis(isAuto = false) {
    return startBotWorkflow(isAuto);
}

function startPollingBot(jobId) {
    if (botPollTimer) clearInterval(botPollTimer);

    botPollTimer = setInterval(async () => {
        try {
            const data = await api(`/api/bot/result/${jobId}`);
            if (data && botJob && botJob.job_id === jobId) {
                const prevCustomCap = botJob.customCaption;
                const prevCustomHash = botJob.customHashtags;

                let defaultCap = prevCustomCap;
                let defaultHash = prevCustomHash;

                if (defaultCap === undefined) {
                    if (botMode === 'repost_as_is') {
                        defaultCap = (data.candidate && data.candidate.original_caption) || (data.analysis && data.analysis.caption);
                    } else {
                        defaultCap = (data.analysis && data.analysis.caption) || (data.candidate && data.candidate.original_caption);
                    }
                }

                if (defaultHash === undefined) {
                    if (botMode === 'repost_as_is') {
                        defaultHash = (data.candidate && data.candidate.original_hashtags) || (data.analysis && data.analysis.hashtags);
                    } else {
                        defaultHash = (data.analysis && data.analysis.hashtags) || (data.candidate && data.candidate.original_hashtags);
                    }
                }

                botJob = {
                    ...botJob,
                    ...data,
                    customCaption: defaultCap,
                    customHashtags: defaultHash
                };

                if (currentPage === 'bot') {
                    renderInteractiveBot(document.getElementById('page-content'));
                }

                if (data.status === 'candidate_found' || data.status === 'ready_to_publish' || data.status === 'published' || data.status === 'failed' || data.status === 'publishing_restricted') {
                    if (data.status === 'published' || data.status === 'failed' || data.status === 'publishing_restricted') {
                        clearInterval(botPollTimer);
                        botPollTimer = null;
                    }
                }
            }
        } catch (_) {}
    }, 1500);
}

async function startBotDownload(jobId) {
    if (!jobId) return;
    const isRepost = (botMode === 'repost_as_is');
    toast(isRepost ? 'Downloading original media as-is...' : 'Downloading & analyzing content...', 'info');
    try {
        if (botJob) {
            botJob.status = 'downloading';
            botJob.step = 'downloading';
            botJob.progress = 65;
            if (currentPage === 'bot') {
                renderInteractiveBot(document.getElementById('page-content'));
            }
        }
        await api(`/api/bot/download/${jobId}`, { 
            method: 'POST', 
            body: { mode: botMode } 
        });
        startPollingBot(jobId);
    } catch (e) {
        toast(`Download failed: ${e.message || e}`, 'error');
    }
}

async function publishBotContent(jobId) {
    if (!jobId || !botJob) return;
    const btn = document.getElementById('bot-publish-btn');
    if (btn) btn.disabled = true;

    const targetAccount = botSelectedAccount || currentActiveUser;
    const caption = getBotDisplayCaption();
    const hashtags = getBotDisplayHashtags();
    const postType = botJob.download?.post_type || botJob.candidate?.post_type || 'reel';
    const typeLabel = postType === 'carousel' ? 'Carousel' : (postType === 'image' ? 'Photo Post' : 'Reel');

    toast(`Publishing ${typeLabel} to @${targetAccount}...`, 'info');
    botJob.status = 'publishing';
    botJob.step = 'publishing';
    if (currentPage === 'bot') {
        renderInteractiveBot(document.getElementById('page-content'));
    }

    try {
        const res = await api(`/api/bot/publish/${jobId}`, {
            method: 'POST',
            body: { 
                caption, 
                hashtags, 
                account: targetAccount, 
                mode: botMode,
                force: botForceDuplicate 
            }
        });
        botJob.status = 'published';
        botJob.step = 'published';
        botJob.publish = res;
        toast(`${typeLabel} published to @${res.account}!`, 'success');
        if (currentPage === 'bot') {
            renderInteractiveBot(document.getElementById('page-content'));
        }
    } catch (e) {
        const errMsg = e.message || String(e);
        const isAuth = errMsg.includes('AUTHENTICATION_REQUIRED') || errMsg.toLowerCase().includes('login_required') || errMsg.toLowerCase().includes('upload_settings');
        const isRestricted = errMsg.includes('PUBLISHING_RESTRICTED') || errMsg.toLowerCase().includes('restrict');
        if (isAuth) {
            toast(`🔑 Authentication Required for @${targetAccount}. Please re-authenticate in Settings.`, 'error');
            if (botJob) {
                botJob.status = 'auth_required';
                botJob.step = 'auth_required';
                botJob.error = errMsg.replace('AUTHENTICATION_REQUIRED: ', '');
            }
        } else if (isRestricted) {
            toast(`⚠️ Instagram has restricted posting for @${targetAccount}. Wait 24–48 hours.`, 'error');
            if (botJob) {
                botJob.status = 'publishing_restricted';
                botJob.step = 'publishing_restricted';
                botJob.error = errMsg.replace('PUBLISHING_RESTRICTED: ', '');
            }
        } else {
            toast(`Publishing failed: ${errMsg}`, 'error');
            if (botJob) {
                botJob.status = 'ready_to_publish';
                botJob.error = errMsg;
            }
        }
        if (currentPage === 'bot') {
            renderInteractiveBot(document.getElementById('page-content'));
        }
    }
}

const publishBotReel = publishBotContent;

function toggleEditCaption() {
    botEditingCaption = !botEditingCaption;
    if (currentPage === 'bot') {
        renderInteractiveBot(document.getElementById('page-content'));
    }
}

function updateCustomCaption(val) {
    if (botJob) {
        botJob.customCaption = val;
    }
}

function toggleEditHashtags() {
    botEditingHashtags = !botEditingHashtags;
    if (currentPage === 'bot') {
        renderInteractiveBot(document.getElementById('page-content'));
    }
}

function updateCustomHashtags(val) {
    if (botJob) {
        botJob.customHashtags = val;
    }
}

function resetBot() {
    if (botPollTimer) {
        clearInterval(botPollTimer);
        botPollTimer = null;
    }
    botJob = null;
    botEditingCaption = false;
    botEditingHashtags = false;
    botSlideIndex = 0;
    botForceDuplicate = false;
    if (currentPage === 'bot') {
        renderInteractiveBot(document.getElementById('page-content'));
    }
}

function renderBotLogs(logs) {
    if (!logs || logs.length === 0) {
        return '<div style="color:var(--text-muted);text-align:center;padding:16px">No bot activity yet</div>';
    }
    return logs.map(e =>
        `<div class="log-entry ${e.level || 'info'}"><span class="log-time">[${e.timestamp || ''}]</span><span class="log-msg">${e.message || ''}</span></div>`
    ).join('');
}

async function renderPostImage(el) {
    el.innerHTML = `
        <div class="section-card">
            <div class="section-title">🖼️ Upload Image</div>
            <div class="upload-zone" id="img-upload-zone" onclick="document.getElementById('media-file-input').click()">
                <div class="upload-icon">📁</div>
                <p style="font-weight:600;font-size:15px">Click to upload or drag media here</p>
                <div style="font-size:12px;color:var(--text-secondary);margin-top:8px;line-height:1.6">
                    <div><strong>Images:</strong> .jpg .jpeg .png .webp</div>
                    <div><strong>Reels:</strong> .mp4 .mov .webm</div>
                </div>
                <input type="file" id="media-file-input" multiple accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.m4v" onchange="handleMultipleUploads(this.files)">
            </div>
            <div id="upload-progress-container"></div>
        </div>
        <div class="section-card">
            <div class="section-title">📂 Or Select from Queue</div>
            <div class="tabs" style="margin-bottom:16px">
                <button class="tab" data-filter="all" onclick="filterQueueSection('all', this, 'queue-table-container')">All</button>
                <button class="tab active" data-filter="images" onclick="filterQueueSection('images', this, 'queue-table-container')">Images</button>
                <button class="tab" data-filter="reels" onclick="filterQueueSection('reels', this, 'queue-table-container')">Reels</button>
            </div>
            <div id="queue-table-container">Loading...</div>
        </div>`;
    setupDragAndDrop('img-upload-zone');
    await loadQueueTable('images', 'queue-table-container');
}

async function renderPostReel(el) {
    el.innerHTML = `
        <div class="section-card">
            <div class="section-title">🎬 Upload Reel</div>
            <div class="upload-zone" id="reel-upload-zone" onclick="document.getElementById('media-file-input').click()">
                <div class="upload-icon">📁</div>
                <p style="font-weight:600;font-size:15px">Click to upload or drag media here</p>
                <div style="font-size:12px;color:var(--text-secondary);margin-top:8px;line-height:1.6">
                    <div><strong>Images:</strong> .jpg .jpeg .png .webp</div>
                    <div><strong>Reels:</strong> .mp4 .mov .webm</div>
                </div>
                <input type="file" id="media-file-input" multiple accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.m4v" onchange="handleMultipleUploads(this.files)">
            </div>
            <div id="upload-progress-container"></div>
        </div>
        <div class="section-card">
            <div class="section-title">📂 Or Select from Queue</div>
            <div class="tabs" style="margin-bottom:16px">
                <button class="tab" data-filter="all" onclick="filterQueueSection('all', this, 'queue-table-container')">All</button>
                <button class="tab" data-filter="images" onclick="filterQueueSection('images', this, 'queue-table-container')">Images</button>
                <button class="tab active" data-filter="reels" onclick="filterQueueSection('reels', this, 'queue-table-container')">Reels</button>
            </div>
            <div id="queue-table-container">Loading...</div>
        </div>`;
    setupDragAndDrop('reel-upload-zone');
    await loadQueueTable('reels', 'queue-table-container');
}

function renderDownload(el) {
    el.innerHTML = `
        <div class="section-card">
            <div class="section-title">⬇️ Download Instagram Media</div>
            <div class="form-group">
                <label>Instagram URL (Reel, Post, or Carousel)</label>
                <input type="url" class="form-input" id="download-url" placeholder="https://www.instagram.com/p/... or https://www.instagram.com/reel/...">
            </div>
            <button class="btn btn-primary" onclick="downloadMedia()">⬇️ Download</button>
        </div>
        <div class="section-card">
            <div class="section-title">📝 Download Log</div>
            <div class="log-viewer" id="download-log">${renderLogEntries(logEntries.filter(l => l.message && l.message.includes('ownload')).slice(0, 10))}</div>
        </div>`;
}

async function renderQueue(el) {
    el.innerHTML = `
        <div class="section-card">
            <div class="section-title">📁 Quick Upload to Queue</div>
            <div class="upload-zone" id="global-upload-zone" onclick="document.getElementById('media-file-input').click()">
                <div class="upload-icon">📁</div>
                <p style="font-weight:600;font-size:15px">Click to upload or drag media here</p>
                <div style="font-size:12px;color:var(--text-secondary);margin-top:8px;line-height:1.6">
                    <div><strong>Images:</strong> .jpg .jpeg .png .webp</div>
                    <div><strong>Reels:</strong> .mp4 .mov .webm</div>
                </div>
                <input type="file" id="media-file-input" multiple accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.m4v" onchange="handleMultipleUploads(this.files)">
            </div>
            <div id="upload-progress-container"></div>
        </div>
        <div class="section-card">
            <div class="flex-between" style="margin-bottom:16px">
                <div class="section-title" style="margin-bottom:0">📋 Pending Media Queue</div>
                <div class="tabs" style="margin-bottom:0;border-bottom:none">
                    <button class="tab active" data-filter="all" onclick="filterQueueSection('all', this, 'global-queue-content')">All</button>
                    <button class="tab" data-filter="images" onclick="filterQueueSection('images', this, 'global-queue-content')">Images</button>
                    <button class="tab" data-filter="reels" onclick="filterQueueSection('reels', this, 'global-queue-content')">Reels</button>
                </div>
            </div>
            <div id="global-queue-content">Loading...</div>
        </div>`;
    setupDragAndDrop('global-upload-zone');
    await loadQueueTable('all', 'global-queue-content');
}

let activeQueueFilter = 'all';

async function loadQueueTable(filter = 'all', containerId = 'queue-table-container') {
    activeQueueFilter = filter;
    const container = document.getElementById(containerId);
    if (!container) return;

    try {
        const queueData = await api('/api/queue');
        if (queueData.active_account) {
            currentActiveUser = queueData.active_account;
        }
        let items = queueData.items || [];
        if (filter === 'images') items = queueData.images || [];
        if (filter === 'reels') items = queueData.reels || [];

        if (items.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📭</div>
                    <p>No ${filter === 'all' ? 'media' : filter} currently in queue.</p>
                    <p style="font-size:12px;color:var(--text-muted);margin-top:4px">Drop files in the upload box above to add them automatically.</p>
                </div>`;
            return;
        }

        container.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th style="width:54px">Preview</th>
                        <th>Filename & History</th>
                        <th>Type</th>
                        <th>Local Path</th>
                        <th>Size</th>
                        <th>Status for @${currentActiveUser}</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map(item => `
                        <tr>
                            <td>
                                ${item.media_type === 'image' ? `
                                    <img 
                                        src="${item.preview_url}" 
                                        class="thumb-small" 
                                        alt="thumbnail"
                                        onclick="openPreviewModal('${item.preview_url}', 'image', '${item.filename}')"
                                        title="Click to preview image"
                                    />
                                ` : `
                                    <video 
                                        src="${item.preview_url}" 
                                        class="thumb-small" 
                                        preload="metadata"
                                        onclick="openPreviewModal('${item.preview_url}', 'reel', '${item.filename}')"
                                        title="Click to preview video"
                                    ></video>
                                `}
                            </td>
                            <td>
                                <div style="font-weight:500">${item.filename}</div>
                                ${item.posted_accounts && item.posted_accounts.length > 0 ? `
                                    <div style="font-size:11px;color:var(--text-muted);margin-top:3px">
                                        Posted to: ${item.posted_accounts.map(a => `<span style="color:${a === currentActiveUser ? '#10b981' : 'var(--text-secondary)'};font-weight:${a === currentActiveUser ? '600' : '400'}">@${a}</span>`).join(', ')}
                                    </div>
                                ` : `
                                    <div style="font-size:11px;color:var(--text-muted);margin-top:3px">Shared asset · Not posted yet</div>
                                `}
                            </td>
                            <td><span class="badge badge-${item.media_type}">${item.media_type}</span></td>
                            <td>
                                <div 
                                    class="path-badge" 
                                    title="${(item.full_path || item.local_path || '').replace(/"/g, '&quot;')}"
                                    onclick="copyPathToClipboard('${(item.full_path || item.local_path || '').replace(/\\/g, '\\\\')}')"
                                >
                                    <span>📁</span>
                                    <span>${item.local_path || item.filename}</span>
                                </div>
                            </td>
                            <td class="size-col">${item.size_formatted}</td>
                            <td>
                                ${item.is_posted_for_active ? `
                                    <span class="badge badge-success" style="font-size:11.5px">✓ Posted to @${currentActiveUser}</span>
                                ` : `
                                    <span class="badge badge-waiting" style="font-size:11.5px">Ready for @${currentActiveUser}</span>
                                `}
                            </td>
                            <td>
                                ${item.is_posted_for_active ? `
                                    <button 
                                        class="btn btn-ghost" 
                                        disabled 
                                        style="opacity:0.55;cursor:not-allowed;font-size:12px;padding:6px 12px"
                                        title="Already posted to @${currentActiveUser}. You can switch accounts to post there."
                                    >
                                        Already Posted
                                    </button>
                                ` : `
                                    <button 
                                        class="btn btn-primary" 
                                        id="btn-post-${item.filename.replace(/[^a-zA-Z0-9]/g, '_')}"
                                        onclick="postMediaItem('${item.filename}', '${item.media_type}')"
                                        style="font-size:12px;padding:6px 14px"
                                    >
                                        Post
                                    </button>
                                `}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>`;
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><p style="color:var(--error)">Failed to load queue: ${e.message || e}</p></div>`;
    }
}

function filterQueueSection(filter, btn, containerId) {
    const parent = btn.parentElement;
    if (parent) {
        parent.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    }
    btn.classList.add('active');
    loadQueueTable(filter, containerId);
}

function setupDragAndDrop(zoneId) {
    const zone = document.getElementById(zoneId);
    if (!zone) return;

    ['dragenter', 'dragover'].forEach(name => {
        zone.addEventListener(name, (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(name => {
        zone.addEventListener(name, (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('dragover');
        });
    });

    zone.addEventListener('drop', (e) => {
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleMultipleUploads(e.dataTransfer.files);
        }
    });
}

async function handleMultipleUploads(fileList) {
    if (!fileList || fileList.length === 0) return;
    const files = Array.from(fileList);
    const progressContainer = document.getElementById('upload-progress-container');

    if (progressContainer) {
        progressContainer.innerHTML = `
            <div class="upload-progress-box">
                <div class="flex-between" style="margin-bottom:8px">
                    <strong style="font-size:13px">${files.length} file(s) selected</strong>
                    <span id="upload-batch-status" style="font-size:12px;color:var(--accent)">Uploading 0 / ${files.length}...</span>
                </div>
                <div class="progress-bar mb-8"><div class="progress-fill" id="upload-batch-fill" style="width:0%"></div></div>
                <div id="upload-items-list">
                    ${files.map((f, i) => `
                        <div class="upload-progress-item" id="up-item-${i}">
                            <span>${f.name}</span>
                            <span style="color:var(--text-muted)" id="up-status-${i}">Pending...</span>
                        </div>
                    `).join('')}
                </div>
            </div>`;
    }

    let successCount = 0;
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const statusEl = document.getElementById(`up-status-${i}`);
        const batchStatus = document.getElementById('upload-batch-status');
        const batchFill = document.getElementById('upload-batch-fill');

        if (statusEl) statusEl.innerHTML = '<span style="color:var(--accent)">Uploading...</span>';
        if (batchStatus) batchStatus.textContent = `Uploading ${i + 1} / ${files.length}...`;

        const formData = new FormData();
        formData.append('file', file);

        try {
            await api('/api/upload', { method: 'POST', body: formData });
            if (statusEl) statusEl.innerHTML = '<span style="color:var(--success)">100% ✓</span>';
            successCount++;
        } catch (e) {
            if (statusEl) statusEl.innerHTML = `<span style="color:var(--error)">Failed: ${e.message || 'Error'}</span>`;
        }

        const pct = Math.round(((i + 1) / files.length) * 100);
        if (batchFill) batchFill.style.width = `${pct}%`;
    }

    toast(`✓ ${successCount} file(s) added to Queue`, 'success');

    // Refresh Queue automatically without page refresh
    if (document.getElementById('queue-table-container')) {
        await loadQueueTable(activeQueueFilter, 'queue-table-container');
    }
    if (document.getElementById('global-queue-content')) {
        await loadQueueTable(activeQueueFilter, 'global-queue-content');
    }
}

async function postMediaItem(filename, mediaType) {
    const btnId = `btn-post-${filename.replace(/[^a-zA-Z0-9]/g, '_')}`;
    const btn = document.getElementById(btnId);
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Posting...';
    }

    toast(`[*] Preparing to post ${filename} to @${currentActiveUser}...`, 'info');

    try {
        const endpoint = mediaType === 'image' ? '/api/post/image' : '/api/post/reel';
        await api(endpoint, {
            method: 'POST',
            body: { filename }
        });
        toast(`Publishing started for ${filename}!`, 'info');

        // Give a short moment and refresh queue
        setTimeout(async () => {
            if (document.getElementById('queue-table-container')) {
                await loadQueueTable(activeQueueFilter, 'queue-table-container');
            }
            if (document.getElementById('global-queue-content')) {
                await loadQueueTable(activeQueueFilter, 'global-queue-content');
            }
        }, 1200);
    } catch (e) {
        toast(`[!] Failed to post ${filename}: ${e.message || e}`, 'error');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Post';
        }
    }
}

function openPreviewModal(url, mediaType, filename) {
    // Remove existing modal if any
    closePreviewModal();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.id = 'media-preview-modal';
    overlay.onclick = (e) => {
        if (e.target === overlay) closePreviewModal();
    };

    overlay.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <span style="font-weight:600">${filename}</span>
                <button class="modal-close-btn" onclick="closePreviewModal()">✕</button>
            </div>
            <div class="modal-body">
                ${mediaType === 'image' ? `
                    <img src="${url}" alt="${filename}">
                ` : `
                    <video src="${url}" controls autoplay playsinline style="max-height:70vh"></video>
                `}
            </div>
        </div>`;

    document.body.appendChild(overlay);

    const escHandler = (e) => {
        if (e.key === 'Escape') {
            closePreviewModal();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);
}

function closePreviewModal() {
    const modal = document.getElementById('media-preview-modal');
    if (modal) modal.remove();
}

async function renderPosted(el) {
    el.innerHTML = '<div class="section-card" id="posted-content">Loading...</div>';
    try {
        const data = await api('/api/history');
        const container = document.getElementById('posted-content');
        if (!data.history || data.history.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><p>No posted media yet</p></div>';
            return;
        }
        container.innerHTML = `<table class="data-table"><thead><tr>
            <th>Filename</th><th>Type</th><th>Account</th><th>Posted</th><th>Status</th><th>Link</th>
        </tr></thead><tbody>${data.history.map(h => `<tr>
            <td>${h.filename}</td>
            <td><span class="badge badge-${h.type}">${h.type}</span></td>
            <td>@${h.account}</td>
            <td class="size-col">${new Date(h.posted_at).toLocaleString()}</td>
            <td><span class="badge badge-success">Published</span></td>
            <td>${h.instagram_url ? `<a href="${h.instagram_url}" target="_blank" style="color:var(--accent)">View</a>` : '—'}</td>
        </tr>`).join('')}</tbody></table>`;
    } catch (e) { toast('Failed to load history', 'error'); }
}

function renderLogs(el) {
    el.innerHTML = `
        <div class="flex-between mb-8">
            <div class="section-title" style="margin-bottom:0">📝 Activity Log</div>
            <button class="btn btn-ghost" onclick="logEntries=[];renderLogs(document.getElementById('page-content'))">Clear</button>
        </div>
        <div class="log-viewer" id="main-log" style="max-height:calc(100vh - 200px)">${renderLogEntries(logEntries)}</div>`;
}

async function renderSettings(el) {
    let settings = {};
    let accountsData = { active: '', accounts: [] };
    try { settings = await api('/api/settings'); } catch (_) {}
    try { accountsData = await api('/api/accounts'); } catch (_) {}

    const accounts = accountsData.accounts || [];
    const activeUser = accountsData.active || '';

    el.innerHTML = `
        <div id="accounts-dashboard-container" class="mb-24">
            ${renderAccountsList(accounts, activeUser)}
        </div>

        <!-- ── Posting Settings ──────────────────────────────────────────── -->
        <div class="section-card">
            <div class="section-title">⚙️ Posting Settings</div>
            <div class="setting-row">
                <div><div class="setting-label">Posting Delay</div><div class="setting-desc">Seconds between each post</div></div>
                <input type="number" class="form-input" style="width:80px" id="set-delay" value="${settings.posting_delay || 30}" min="5" max="300">
            </div>
            <div class="setting-row">
                <div><div class="setting-label">Automatic Caption</div><div class="setting-desc">AI-generated captions for each post</div></div>
                <div class="toggle ${settings.auto_caption !== false ? 'on' : ''}" onclick="this.classList.toggle('on')" id="set-caption"></div>
            </div>
            <div class="setting-row">
                <div><div class="setting-label">Automatic Hashtags</div><div class="setting-desc">AI-generated hashtags for reach</div></div>
                <div class="toggle ${settings.auto_hashtags !== false ? 'on' : ''}" onclick="this.classList.toggle('on')" id="set-hashtags"></div>
            </div>
            <div class="setting-row">
                <div><div class="setting-label">Duplicate Protection</div><div class="setting-desc">Skip files that were already posted</div></div>
                <div class="toggle ${settings.duplicate_protection !== false ? 'on' : ''}" onclick="this.classList.toggle('on')" id="set-dup"></div>
            </div>
            <div class="setting-row">
                <div><div class="setting-label">Auto Archive</div><div class="setting-desc">Move posted files to posted/ folder</div></div>
                <div class="toggle ${settings.auto_archive !== false ? 'on' : ''}" onclick="this.classList.toggle('on')" id="set-archive"></div>
            </div>
            <div class="mt-16">
                <button class="btn btn-primary" onclick="saveSettings()">Save Settings</button>
            </div>
        </div>`;
}

function renderAccountsList(accounts, activeUser) {
    if (!accounts || accounts.length === 0) {
        return `
        <div class="accounts-dashboard-header">
            <div>
                <h2 class="accounts-dash-title">Connected Accounts (0)</h2>
                <div class="accounts-dash-desc">Authenticated Instagram accounts ready for automated and interactive posting.</div>
            </div>
            <button class="btn btn-white-pill" onclick="openSessionManagerModal()">
                ＋ Add Account
            </button>
        </div>
        <div class="empty-state" style="padding:36px;background:#0d121f;border:1px solid #1e293b;border-radius:16px">
            <div class="empty-icon">📱</div>
            <p style="font-weight:700;font-size:16px">No Instagram accounts connected yet</p>
            <p style="font-size:12.5px;color:var(--text-muted);margin-top:6px">Connect your first account via session cookie, credentials, or session JSON.</p>
            <button class="btn btn-white-pill mt-16" onclick="openSessionManagerModal()">＋ Add Instagram Account</button>
        </div>`;
    }

    // Find active account or default to first
    const activeAcc = accounts.find(a => a.is_active || a.username.toLowerCase() === (activeUser || '').toLowerCase()) || accounts[0];
    const otherAccounts = accounts.filter(a => a.username.toLowerCase() !== activeAcc.username.toLowerCase());

    const activeIsExpired = (activeAcc.status || '').toLowerCase().includes('expired') || (activeAcc.status || '').toLowerCase() === 'session_expired';
    const activeIsRestricted = (activeAcc.status || '').toLowerCase() === 'publishing_restricted';
    const activeIsAuth = !activeIsExpired && activeAcc.is_authenticated !== false && (activeAcc.status === 'Connected' || activeAcc.status === 'connected');
    
    let activeStatusBadgeClass = 'status-pill-lg connected';
    let activeStatusBadgeText = '🟢 CONNECTED';
    if (activeIsRestricted) {
        activeStatusBadgeClass = 'status-pill-lg restricted';
        activeStatusBadgeText = '⚠️ ACTION RESTRICTED';
    } else if (activeIsExpired) {
        activeStatusBadgeClass = 'status-pill-lg expired';
        activeStatusBadgeText = '🔴 EXPIRED';
    } else if (!activeIsAuth) {
        activeStatusBadgeClass = 'status-pill-lg expired';
        activeStatusBadgeText = '🔴 DISCONNECTED';
    }

    const isPublishingPaused = activeAcc.publishing_enabled === false;

    return `
    <div class="accounts-dashboard-header">
        <div>
            <h2 class="accounts-dash-title">Connected Accounts (${accounts.length})</h2>
            <div class="accounts-dash-desc">Authenticated Instagram accounts ready for automated and interactive posting.</div>
        </div>
        <button class="btn btn-white-pill" onclick="openSessionManagerModal()">
            ＋ Add Account
        </button>
    </div>

    <!-- ── Hero Active Account Card (Screenshot 1) ── -->
    <div class="active-account-card">
        <div class="active-card-top">
            <div class="active-account-profile">
                <div class="ig-gradient-avatar">
                    <span class="avatar-icon">📷</span>
                </div>
                <div>
                    <div class="active-username">@${activeAcc.username}</div>
                    <div class="active-auth-type">Auth: ${activeAcc.auth_type || 'Instagram Login'}</div>
                </div>
            </div>
            <div class="active-card-status">
                <span class="${activeStatusBadgeClass}">${activeStatusBadgeText}</span>
            </div>
        </div>

        <!-- Inner specs grid box -->
        <div class="active-specs-box">
            <div class="specs-row">
                <div class="spec-item">
                    <span class="spec-label">👤 Authentication</span>
                    <span class="spec-val ${activeIsAuth ? 'val-good' : 'val-bad'}">
                        ● ${activeIsAuth ? 'Verified' : 'Unverified'}
                    </span>
                </div>
                <div class="spec-item">
                    <span class="spec-label">🛡️ 2FA</span>
                    <span class="spec-val ${activeAcc.two_factor ? 'val-good' : 'val-warn'}">
                        ● ${activeAcc.two_factor ? 'Instagram Protected' : 'Standard'}
                    </span>
                </div>
            </div>
            <div class="specs-row">
                <div class="spec-item">
                    <span class="spec-label">🖌️ Publishing</span>
                    <span class="spec-val ${!isPublishingPaused ? 'val-good' : 'val-warn'}">
                        ● ${!isPublishingPaused ? 'Enabled' : 'Paused'}
                    </span>
                </div>
                <div class="spec-item">
                    <span class="spec-label">🔑 Token</span>
                    <span class="spec-val ${activeIsAuth ? 'val-good' : 'val-bad'}">
                        ● ${activeIsAuth ? 'Valid' : 'Expired'}
                    </span>
                </div>
            </div>
        </div>

        <!-- Action buttons row -->
        <div class="active-card-actions">
            <button class="btn btn-outline-dark" onclick="openSessionManagerModal('${activeAcc.username}')" title="Change session / login method">
                Switch
            </button>
            <button class="btn btn-outline-dark" onclick="openReconnectModal('${activeAcc.username}')" title="Reauthenticate session">
                Reconnect
            </button>
            <button class="btn ${!isPublishingPaused ? 'btn-pause-publishing' : 'btn-resume-publishing'}" 
                    onclick="toggleAccountPublishing('${activeAcc.username}')" title="Toggle automatic publishing for this account">
                ${!isPublishingPaused ? '🔴 Pause Publishing' : '🟢 Resume Publishing'}
            </button>
            <button class="btn btn-outline-dark" onclick="verifyAccountRow('${activeAcc.username}', '${activeAcc.session_file || ''}')">
                Verify Session
            </button>
            <button class="btn btn-outline-dark" onclick="openSessionManagerModal('${activeAcc.username}', 'cookie')">
                Session Cookie
            </button>
            <button class="btn btn-outline-dark" onclick="openSessionManagerModal('${activeAcc.username}', 'otp')">
                OTP / 2FA
            </button>
        </div>
    </div>

    <!-- ── Other Accounts List (Screenshot 1) ── -->
    ${otherAccounts.length > 0 ? `
    <div class="other-accounts-section">
        <div class="other-accounts-title">YOUR OTHER ACCOUNTS</div>
        <div class="other-accounts-list">
            ${otherAccounts.map(acc => {
                const isAccExpired = (acc.status || '').toLowerCase().includes('expired') || (acc.status || '').toLowerCase() === 'session_expired';
                const isAccAuth = !isAccExpired && acc.is_authenticated !== false && (acc.status === 'Connected' || acc.status === 'connected');
                const isPaused = acc.publishing_enabled === false;

                return `
                <div class="other-account-row" onclick="openSessionManagerModal('${acc.username}')">
                    <div class="other-account-left">
                        <div class="ig-gradient-avatar sm">
                            <span class="avatar-icon">📷</span>
                        </div>
                        <div>
                            <div class="other-username">@${acc.username}</div>
                            <div class="other-auth-type">Auth Type: ${acc.auth_type || 'Instagram Login'}</div>
                        </div>
                    </div>
                    <div class="other-account-right">
                        <div class="other-stat">
                            Status: <span class="${isAccAuth ? 'status-text-good' : 'status-text-bad'}">
                                ● ${isAccAuth ? 'Connected' : (isAccExpired ? 'Expired' : 'Disconnected')}
                            </span>
                        </div>
                        <div class="other-stat">
                            Publishing: <span class="${!isPaused ? 'status-text-good' : 'status-text-warn'}">
                                ● ${!isPaused ? 'Ready' : 'Paused'}
                            </span>
                        </div>
                        <div class="other-actions-group" onclick="event.stopPropagation()">
                            <button class="btn-sm btn-ghost" onclick="switchToAccountRow('${acc.username}')" title="Set as active posting account">
                                Switch
                            </button>
                            <button class="btn-sm btn-ghost" onclick="verifyAccountRow('${acc.username}', '${acc.session_file || ''}')" title="Test session">
                                Verify
                            </button>
                            ${isAccExpired || !isAccAuth ? `
                                <button class="btn-sm btn-reconnect-badge" onclick="openReconnectModal('${acc.username}')">
                                    Reconnect
                                </button>
                            ` : ''}
                            <button class="btn-sm btn-ghost" onclick="openSessionManagerModal('${acc.username}')" title="Account & Session Manager">
                                Manage
                            </button>
                            <button class="btn-sm btn-danger-ghost" onclick="removeAccountRow('${acc.username}')" title="Remove account from dashboard">
                                ×
                            </button>
                        </div>
                        <span class="chevron-icon">›</span>
                    </div>
                </div>`;
            }).join('')}
        </div>
    </div>
    ` : ''}
    `;
}

// ── Modal & Account Actions ──────────────────────────────────────────────────
let modalPendingAccount = {
    username: '',
    displayName: '',
    sessionFile: '',
    setActive: true,
    actualUsername: ''
};

function handleModalUsernameChange(val) {
    const clean = val.trim().replace(/^@/, '');
    const sessionInp = document.getElementById('modal-acc-session');
    if (sessionInp) {
        sessionInp.value = clean ? `sessions/${clean}.json` : 'sessions/newusername.json';
    }
}

function openAccountReconnect(username) {
    const target = (username || botSelectedAccount || currentActiveUser || '').replace(/^@/, '');
    openAccountConnectModal();
    const userInp = document.getElementById('modal-acc-username');
    const dispInp = document.getElementById('modal-acc-display');
    const sessInp = document.getElementById('modal-acc-session');
    if (userInp) userInp.value = target;
    if (dispInp) dispInp.value = target;
    if (sessInp) sessInp.value = `sessions/${target}.json`;
    handleModalUsernameChange(target);
    submitModalVerifyAndConnect();
}

function openAccountConnectModal() {
    modalPendingAccount = {
        username: '',
        displayName: '',
        sessionFile: 'sessions/newusername.json',
        setActive: true,
        actualUsername: ''
    };

    const userInp = document.getElementById('modal-acc-username');
    const dispInp = document.getElementById('modal-acc-display');
    const sessInp = document.getElementById('modal-acc-session');
    const actvChk = document.getElementById('modal-acc-set-active');
    const pwdInp = document.getElementById('modal-acc-password');
    const twofaInp = document.getElementById('modal-acc-2fa');
    const formMsg = document.getElementById('modal-acc-form-msg');
    const authMsg = document.getElementById('modal-acc-auth-msg');

    if (userInp) userInp.value = '';
    if (dispInp) dispInp.value = '';
    if (sessInp) sessInp.value = 'sessions/newusername.json';
    if (actvChk) actvChk.checked = true;
    if (pwdInp) pwdInp.value = '';
    if (twofaInp) twofaInp.value = '';
    if (formMsg) { formMsg.style.display = 'none'; formMsg.innerHTML = ''; }
    if (authMsg) { authMsg.style.display = 'none'; authMsg.innerHTML = ''; }

    showModalStep('form');
    const modal = document.getElementById('account-connect-modal');
    if (modal) modal.style.display = 'flex';
    if (userInp) setTimeout(() => userInp.focus(), 100);
}

function closeAccountConnectModal() {
    const modal = document.getElementById('account-connect-modal');
    if (modal) modal.style.display = 'none';
}

function showModalStep(step) {
    const steps = ['form', 'loading', 'auth', 'success'];
    steps.forEach(s => {
        const el = document.getElementById(`acc-step-${s}`);
        if (el) el.style.display = (s === step) ? 'block' : 'none';
    });
}

async function submitModalVerifyAndConnect() {
    const userInp = document.getElementById('modal-acc-username');
    const dispInp = document.getElementById('modal-acc-display');
    const sessInp = document.getElementById('modal-acc-session');
    const actvChk = document.getElementById('modal-acc-set-active');
    const formMsg = document.getElementById('modal-acc-form-msg');

    const username = userInp ? userInp.value.trim().replace(/^@/, '') : '';
    if (!username) {
        if (formMsg) {
            formMsg.style.display = 'block';
            formMsg.innerHTML = '<div style="color:var(--error);font-size:12.5px">⚠️ Please enter an Instagram username</div>';
        }
        return;
    }

    const displayName = dispInp ? (dispInp.value.trim() || username) : username;
    const sessionFile = sessInp ? sessInp.value.trim() : `sessions/${username}.json`;
    const setActive = actvChk ? actvChk.checked : true;

    modalPendingAccount = {
        username,
        displayName,
        sessionFile,
        setActive,
        actualUsername: username
    };

    // Transition to loading step
    showModalStep('loading');
    const loadTitle = document.getElementById('modal-loading-title');
    const loadDesc = document.getElementById('modal-loading-desc');
    if (loadTitle) loadTitle.textContent = `Verifying @${username}...`;
    if (loadDesc) loadDesc.textContent = 'Checking session validity and live credentials with Instagram...';

    try {
        const res = await api('/api/account/connect', {
            method: 'POST',
            body: {
                username,
                display_name: displayName,
                session_file: sessionFile,
                set_active: setActive
            }
        });

        if (res.connected && res.valid) {
            // Success! Actual authenticated Instagram username
            modalPendingAccount.actualUsername = res.actual_username || username;
            modalPendingAccount.sessionFile = res.session_file || sessionFile;

            const succUser = document.getElementById('modal-success-username');
            const succSess = document.getElementById('modal-success-session');
            const succActv = document.getElementById('modal-success-set-active');

            if (succUser) succUser.textContent = `@${res.actual_username || username}`;
            if (succSess) succSess.textContent = res.session_file || sessionFile;
            if (succActv) succActv.checked = Boolean(res.is_active || setActive);

            showModalStep('success');
        } else {
            // Authentication required
            setupModalAuthStep(res.message || 'Session file not found or expired.');
        }
    } catch (e) {
        setupModalAuthStep(e.message || 'Connection test failed.');
    }
}

function setupModalAuthStep(errorDetail) {
    const targetUser = modalPendingAccount.username;
    const authUser = document.getElementById('auth-target-user');
    const authDesc = document.getElementById('auth-notice-desc');
    const cliPath = document.getElementById('cli-session-path');
    const cliCmd = document.getElementById('cli-command-badge');
    const grp2fa = document.getElementById('group-auth-2fa');
    const authMsg = document.getElementById('modal-acc-auth-msg');

    if (authUser) authUser.textContent = `@${targetUser}`;
    if (authDesc) {
        authDesc.innerHTML = `Instagram account not authenticated as <strong style="color:var(--text)">@${targetUser}</strong>.<br><span style="color:var(--text-muted);font-size:11.5px">${errorDetail}</span>`;
    }
    if (cliPath) cliPath.textContent = modalPendingAccount.sessionFile;
    if (cliCmd) cliCmd.textContent = `python account_manager.py login ${targetUser}`;
    if (grp2fa) grp2fa.style.display = 'none';
    if (authMsg) { authMsg.style.display = 'none'; authMsg.innerHTML = ''; }

    showModalStep('auth');
    const pwdInp = document.getElementById('modal-acc-password');
    if (pwdInp) setTimeout(() => pwdInp.focus(), 100);
}

async function submitModalLogin() {
    const pwdInp = document.getElementById('modal-acc-password');
    const twofaInp = document.getElementById('modal-acc-2fa');
    const authMsg = document.getElementById('modal-acc-auth-msg');
    const btnLogin = document.getElementById('btn-modal-do-login');

    const password = pwdInp ? pwdInp.value : '';
    const verification_code = twofaInp ? twofaInp.value.trim() : '';

    if (!password) {
        if (authMsg) {
            authMsg.style.display = 'block';
            authMsg.innerHTML = '<div style="color:var(--error);font-size:12.5px">⚠️ Password is required to authenticate</div>';
        }
        return;
    }

    if (btnLogin) { btnLogin.disabled = true; btnLogin.textContent = 'Authenticating...'; }
    if (authMsg) {
        authMsg.style.display = 'block';
        authMsg.innerHTML = '<div style="color:var(--accent);font-size:12.5px">🔄 Authenticating with Instagram...</div>';
    }

    try {
        const res = await api('/api/account/login', {
            method: 'POST',
            body: {
                username: modalPendingAccount.username,
                password: password,
                verification_code: verification_code || undefined,
                display_name: modalPendingAccount.displayName,
                set_active: modalPendingAccount.setActive
            }
        });

        if (res.status === 'two_factor_required') {
            const grp2fa = document.getElementById('group-auth-2fa');
            if (grp2fa) grp2fa.style.display = 'block';
            if (authMsg) {
                authMsg.innerHTML = '<div style="color:#fbbf24;font-size:12.5px">📱 2FA Enabled: Enter the 6-digit security code and click Authenticate again.</div>';
            }
            if (twofaInp) twofaInp.focus();
            return;
        }

        if (res.valid && res.status === 'Connected') {
            modalPendingAccount.actualUsername = res.actual_username || modalPendingAccount.username;
            modalPendingAccount.sessionFile = res.session_file;

            const succUser = document.getElementById('modal-success-username');
            const succSess = document.getElementById('modal-success-session');
            const succActv = document.getElementById('modal-success-set-active');

            if (succUser) succUser.textContent = `@${res.actual_username}`;
            if (succSess) succSess.textContent = res.session_file;
            if (succActv) succActv.checked = Boolean(res.is_active || modalPendingAccount.setActive);

            showModalStep('success');
        } else {
            if (authMsg) {
                authMsg.innerHTML = `<div style="color:var(--error);font-size:12.5px">❌ ${res.message || 'Login failed'}</div>`;
            }
        }
    } catch (e) {
        if (authMsg) {
            authMsg.innerHTML = `<div style="color:var(--error);font-size:12.5px">❌ ${e.message || e}</div>`;
        }
    } finally {
        if (btnLogin) { btnLogin.disabled = false; btnLogin.textContent = '🔐 Authenticate & Connect'; }
    }
}

async function recheckModalSession() {
    await submitModalVerifyAndConnect();
}

async function finishAccountConnect() {
    const succActv = document.getElementById('modal-success-set-active');
    const shouldMakeActive = succActv ? succActv.checked : true;
    const targetUser = modalPendingAccount.actualUsername || modalPendingAccount.username;

    if (shouldMakeActive && targetUser) {
        try {
            await api('/api/account/switch', { method: 'POST', body: { username: targetUser, force: true } });
        } catch (_) {}
    }

    closeAccountConnectModal();
    toast(`✅ Account @${targetUser} connected!`, 'success');

    await loadAccount();
    if (currentPage === 'settings') {
        await renderSettings(document.getElementById('page-content'));
    }
}

async function verifyAccountRow(username, sessionFile) {
    const rowId = username.replace(/[^a-zA-Z0-9_-]/g, '_');
    const btn = document.getElementById(`btn-verify-${rowId}`);
    const badge = document.getElementById(`status-badge-${rowId}`);

    if (btn) { btn.disabled = true; btn.textContent = 'Verifying...'; }
    toast(`Testing live session for @${username}...`, 'info');

    try {
        const res = await api('/api/account/verify', {
            method: 'POST',
            body: { username, session_file: sessionFile }
        });

        if (res.valid) {
            if (res.status === 'publishing_restricted') {
                if (badge) {
                    badge.className = 'status-pill restricted';
                    badge.textContent = '⚠️ ACTION RESTRICTED';
                }
                toast(`⚠️ @${username}: Session valid (Authenticated as @${username}), but Instagram is restricting activity. Wait 24–48h.`, 'warning');
            } else {
                if (badge) {
                    badge.className = 'status-pill connected';
                    badge.textContent = '🟢 SESSION VALID';
                }
                toast(`✅ @${username}: Session valid! Authenticated as @${res.actual_username || username}`, 'success');
            }
        } else {
            if (res.status === 'session_mismatch') {
                if (badge) {
                    badge.className = 'status-pill disconnected';
                    badge.textContent = '❌ SESSION MISMATCH';
                }
                toast(`❌ SESSION MISMATCH: Expected @${username}, authenticated as @${res.actual_username}. Publishing disabled.`, 'error');
            } else {
                if (badge) {
                    badge.className = 'status-pill disconnected';
                    badge.textContent = '🔴 VERIFICATION FAILED';
                }
                toast(`⚠️ @${username}: ${res.message || 'Session verification failed'}`, 'warning');
            }
        }
        await loadAccounts();
        if (currentPage === 'settings') {
            const pageEl = document.getElementById('page-content');
            if (pageEl) await renderSettings(pageEl);
        }
    } catch (e) {
        if (badge) {
            badge.className = 'status-pill disconnected';
            badge.textContent = '🔴 ERROR';
        }
        toast(`Error verifying @${username}: ${e.message || e}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Verify'; }
    }
}

async function switchToAccountRow(username) {
    const rowId = username.replace(/[^a-zA-Z0-9_-]/g, '_');
    const btn = document.getElementById(`btn-switch-${rowId}`);
    if (btn) { btn.disabled = true; btn.textContent = 'Switching...'; }

    try {
        const res = await api('/api/account/switch', { method: 'POST', body: { username } });
        currentActiveUser = res.active || username;
        const activeDisplay = document.getElementById('active-account');
        if (activeDisplay) activeDisplay.textContent = `@${currentActiveUser}`;

        if (res.is_authenticated === false || res.warning) {
            toast(`⚠️ Switched to @${currentActiveUser} (Session Expired — Reconnect to publish)`, 'warning');
            setTimeout(() => {
                openSessionManagerModal(currentActiveUser, 'cookie');
            }, 350);
        } else {
            toast(`✅ Switched active account to @${currentActiveUser}`, 'success');
        }

        await loadAccounts();
        if (currentPage === 'settings') {
            await renderSettings(document.getElementById('page-content'));
        } else if (currentPage === 'dashboard') {
            await renderDashboard(document.getElementById('page-content'));
        }
    } catch (e) {
        toast(`Failed to switch: ${e.message || e}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Switch'; }
    }
}

async function removeAccountRow(username) {
    const msg = `Remove @${username} from dashboard accounts?\n\n• Your Instagram account is NOT deleted.\n• Your session file in sessions/ is preserved.\n• Only the app configuration entry is removed.`;
    if (!confirm(msg)) return;

    try {
        await api(`/api/account/${username}`, { method: 'DELETE' });
        toast(`Account @${username} removed from dashboard configuration`, 'info');
        await loadAccount();
        if (currentPage === 'settings') {
            await renderSettings(document.getElementById('page-content'));
        }
    } catch (e) {
        toast(`Failed to remove @${username}: ${e.message || e}`, 'error');
    }
}

// Backward-compatibility aliases
const verifyAccountById = verifyAccountRow;
const switchToAccount = switchToAccountRow;
const removeAccount = removeAccountRow;

// ── Import Session ID & Reconnect Workflows ──────────────────────────────────
let currentImportTargetAccount = '';
let currentReconnectTargetAccount = '';

function openImportSessionModal(username) {
    currentImportTargetAccount = (username || '').replace(/^@/, '').trim();
    const modal = document.getElementById('account-import-session-modal');
    const titleEl = document.getElementById('import-session-title');
    const userEl = document.getElementById('import-session-user');
    const fileEl = document.getElementById('import-session-file');
    const inputEl = document.getElementById('import-session-input');
    const errorEl = document.getElementById('import-session-error');
    const btnSave = document.getElementById('btn-import-save');
    const btnCancel = document.getElementById('btn-import-cancel');

    if (titleEl) titleEl.textContent = `Reconnect @${currentImportTargetAccount}`;
    if (userEl) userEl.textContent = `@${currentImportTargetAccount}`;
    if (fileEl) fileEl.textContent = `sessions/${currentImportTargetAccount}.json`;
    if (inputEl) {
        inputEl.value = '';
        inputEl.type = 'password';
    }
    if (errorEl) {
        errorEl.style.display = 'none';
        errorEl.textContent = '';
    }
    if (btnSave) {
        btnSave.disabled = false;
        btnSave.textContent = 'Save & Verify';
    }
    if (btnCancel) btnCancel.disabled = false;

    if (modal) modal.style.display = 'flex';
    if (inputEl) setTimeout(() => inputEl.focus(), 100);
}

function closeImportSessionModal() {
    const modal = document.getElementById('account-import-session-modal');
    if (modal) modal.style.display = 'none';
}

function toggleImportSessionVisibility() {
    const inputEl = document.getElementById('import-session-input');
    if (inputEl) {
        inputEl.type = (inputEl.type === 'password') ? 'text' : 'password';
    }
}

async function saveImportedSession() {
    const inputEl = document.getElementById('import-session-input');
    const errorEl = document.getElementById('import-session-error');
    const btnSave = document.getElementById('btn-import-save');
    const btnCancel = document.getElementById('btn-import-cancel');

    const sessionId = (inputEl ? inputEl.value : '').trim();
    if (!sessionId) {
        if (errorEl) {
            errorEl.style.display = 'block';
            errorEl.textContent = 'Enter your session ID.';
        }
        return;
    }

    if (errorEl) {
        errorEl.style.display = 'none';
        errorEl.textContent = '';
    }
    if (btnSave) {
        btnSave.disabled = true;
        btnSave.textContent = 'Verifying...';
    }
    if (btnCancel) btnCancel.disabled = true;

    try {
        const response = await fetch(
            `/api/accounts/${encodeURIComponent(currentImportTargetAccount)}/session`,
            {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({ sessionid: sessionId })
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || "Session verification failed.");
        }

        if (inputEl) inputEl.value = '';
        closeImportSessionModal();
        toast(`✅ Session verified and saved for @${currentImportTargetAccount}! Status: Connected`, 'success');

        await loadAccount();
        if (currentPage === 'settings') {
            await renderSettings(document.getElementById('page-content'));
        }
    } catch (err) {
        if (errorEl) {
            errorEl.style.display = 'block';
            errorEl.textContent = err.message || "Could not verify session.";
        }
        toast(`Verification failed: ${err.message || 'Could not verify session'}`, 'error');
    } finally {
        if (btnSave) {
            btnSave.disabled = false;
            btnSave.textContent = 'Save & Verify';
        }
        if (btnCancel) btnCancel.disabled = false;
    }
}

function openReconnectModal(username) {
    currentReconnectTargetAccount = (username || '').replace(/^@/, '').trim();
    const modal = document.getElementById('account-reconnect-modal');
    const titleEl = document.getElementById('reconnect-modal-title');
    const userEl = document.getElementById('reconnect-target-user');
    const userDispEl = document.getElementById('reconnect-user-display');
    const pwdEl = document.getElementById('reconnect-password');
    const twofaEl = document.getElementById('reconnect-2fa');
    const group2fa = document.getElementById('reconnect-group-2fa');
    const msgEl = document.getElementById('reconnect-msg');
    const btnSubmit = document.getElementById('btn-reconnect-submit');
    const btnCancel = document.getElementById('btn-reconnect-cancel');

    if (titleEl) titleEl.textContent = `Reconnect @${currentReconnectTargetAccount}`;
    if (userEl) userEl.textContent = `@${currentReconnectTargetAccount}`;
    if (userDispEl) userDispEl.value = `@${currentReconnectTargetAccount}`;
    if (pwdEl) pwdEl.value = '';
    if (twofaEl) twofaEl.value = '';
    if (group2fa) group2fa.style.display = 'none';
    if (msgEl) {
        msgEl.style.display = 'none';
        msgEl.innerHTML = '';
    }
    if (btnSubmit) {
        btnSubmit.disabled = false;
        btnSubmit.textContent = '🔄 Reconnect & Verify';
    }
    if (btnCancel) btnCancel.disabled = false;

    if (modal) modal.style.display = 'flex';
    if (pwdEl) setTimeout(() => pwdEl.focus(), 100);
}

function closeReconnectModal() {
    const modal = document.getElementById('account-reconnect-modal');
    if (modal) modal.style.display = 'none';
}

async function submitAccountReconnect() {
    const pwdEl = document.getElementById('reconnect-password');
    const twofaEl = document.getElementById('reconnect-2fa');
    const group2fa = document.getElementById('reconnect-group-2fa');
    const msgEl = document.getElementById('reconnect-msg');
    const btnSubmit = document.getElementById('btn-reconnect-submit');
    const btnCancel = document.getElementById('btn-reconnect-cancel');

    const password = (pwdEl ? pwdEl.value : '').trim();
    const verificationCode = (twofaEl ? twofaEl.value : '').trim();

    if (!password) {
        if (msgEl) {
            msgEl.style.display = 'block';
            msgEl.style.background = 'rgba(239,68,68,0.15)';
            msgEl.style.border = '1px solid rgba(239,68,68,0.4)';
            msgEl.style.color = '#fca5a5';
            msgEl.innerHTML = '⚠️ Password is required to reauthenticate.';
        }
        return;
    }

    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.textContent = 'Authenticating...';
    }
    if (btnCancel) btnCancel.disabled = true;
    if (msgEl) {
        msgEl.style.display = 'block';
        msgEl.style.background = 'rgba(59,130,246,0.15)';
        msgEl.style.border = '1px solid rgba(59,130,246,0.4)';
        msgEl.style.color = '#93c5fd';
        msgEl.innerHTML = '🔄 Contacting Instagram authentication service...';
    }

    try {
        const response = await fetch(
            `/api/accounts/${encodeURIComponent(currentReconnectTargetAccount)}/reconnect`,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    password: password,
                    verification_code: verificationCode || undefined
                })
            }
        );

        const res = await response.json();

        if (res.status === 'two_factor_required') {
            if (group2fa) group2fa.style.display = 'block';
            if (msgEl) {
                msgEl.style.background = 'rgba(245,158,11,0.15)';
                msgEl.style.border = '1px solid rgba(245,158,11,0.4)';
                msgEl.style.color = '#fde68a';
                msgEl.innerHTML = '📱 <strong>Two-Factor Authentication required:</strong> Enter your 6-digit 2FA code above and click Reconnect & Verify.';
            }
            if (twofaEl) twofaEl.focus();
            return;
        }

        if (!response.ok || !res.valid) {
            throw new Error(res.message || res.detail || "Authentication failed.");
        }

        closeReconnectModal();
        toast(`✅ Successfully reconnected @${res.actual_username || currentReconnectTargetAccount}!`, 'success');

        await loadAccount();
        if (currentPage === 'settings') {
            await renderSettings(document.getElementById('page-content'));
        }
    } catch (err) {
        if (msgEl) {
            msgEl.style.display = 'block';
            msgEl.style.background = 'rgba(239,68,68,0.15)';
            msgEl.style.border = '1px solid rgba(239,68,68,0.4)';
            msgEl.style.color = '#fca5a5';
            msgEl.innerHTML = `❌ ${err.message || 'Authentication failed'}`;
        }
        toast(`Reconnect failed: ${err.message || err}`, 'error');
    } finally {
        if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.textContent = '🔄 Reconnect & Verify';
        }
        if (btnCancel) btnCancel.disabled = false;
    }
}





// ── Log Rendering ────────────────────────────────────────────────────────────

function renderLogEntries(entries) {
    if (entries.length === 0) return '<div style="color:var(--text-muted);text-align:center;padding:20px">No logs yet</div>';
    return entries.map(e =>
        `<div class="log-entry ${e.level || 'info'}"><span class="log-time">${e.timestamp || ''}</span><span class="log-msg">${e.message || ''}</span></div>`
    ).join('');
}

function updateLogViewer() {
    const viewers = ['main-log', 'live-log', 'dashboard-log', 'download-log'];
    viewers.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            const max = id === 'main-log' ? logEntries.length : 30;
            el.innerHTML = renderLogEntries(logEntries.slice(0, max));
        }
    });
}

function updateProgressUI(data) {
    const fill = document.getElementById('ap-fill');
    const pct = document.getElementById('ap-pct');
    const file = document.getElementById('ap-file');
    const detail = document.getElementById('ap-detail');
    if (fill) fill.style.width = data.percentage + '%';
    if (pct) pct.textContent = data.percentage + '%';
    if (file) file.textContent = data.filename || '...';
    if (detail) detail.textContent = `${data.current} / ${data.total} · ${data.media_type || ''} · ${data.step || ''}`;
}

// ── Actions ──────────────────────────────────────────────────────────────────

async function startAutoPost() {
    const account = selectedAutoPostAccount || currentActiveUser;
    const mode = selectedAutoPostMode || 'all';

    if (!account) {
        toast('Please select an Instagram account first', 'warning');
        return;
    }

    try {
        const res = await api('/api/auto-post/start', {
            method: 'POST',
            body: { account, mode }
        });
        if (res.status === 'already_running') {
            toast('Auto-post is already running!', 'warning');
        } else {
            toast(`Auto-post started for @${account} (${formatModeLabel(mode)})!`, 'success');
        }
        autoPostStatus.running = true;
        autoPostStatus.account = account;
        autoPostStatus.mode = mode;
        navigate('auto-post');
    } catch (e) {
        toast(`Failed to start auto-post: ${e.message || e}`, 'error');
    }
}

async function stopAutoPost() {
    try {
        await api('/api/auto-post/stop', { method: 'POST' });
        toast('Stopping auto-post after current upload...', 'warning');
    } catch (e) { toast('Failed to stop auto-post', 'error'); }
}

async function postImage(filename) {
    toast(`Posting ${filename}...`, 'info');
    try {
        await api('/api/post/image', { method: 'POST', body: { filename } });
    } catch (e) { toast('Failed to post image', 'error'); }
}

async function postReel(filename) {
    toast(`Posting ${filename}...`, 'info');
    try {
        await api('/api/post/reel', { method: 'POST', body: { filename } });
    } catch (e) { toast('Failed to post reel', 'error'); }
}

async function downloadMedia() {
    const url = document.getElementById('download-url').value.trim();
    if (!url) { toast('Enter an Instagram URL', 'warning'); return; }
    toast('Starting download...', 'info');
    try {
        await api('/api/download', { method: 'POST', body: { url } });
        document.getElementById('download-url').value = '';
    } catch (e) { toast('Download failed', 'error'); }
}

async function handleImageUpload(input) {
    if (!input.files.length) return;
    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);
    toast(`Uploading ${file.name}...`, 'info');
    try {
        await api('/api/upload/image', { method: 'POST', body: formData });
        toast(`Uploaded ${file.name} to images/new/`, 'success');
        if (currentPage === 'post-image') navigate('post-image');
    } catch (e) { toast('Upload failed', 'error'); }
}

async function handleReelUpload(input) {
    if (!input.files.length) return;
    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);
    toast(`Uploading ${file.name}...`, 'info');
    try {
        await api('/api/upload/reel', { method: 'POST', body: formData });
        toast(`Uploaded ${file.name} to reels/new/`, 'success');
        if (currentPage === 'post-reel') navigate('post-reel');
    } catch (e) { toast('Upload failed', 'error'); }
}

async function saveSettings() {
    const delay = parseInt(document.getElementById('set-delay').value) || 30;
    const settings = {
        posting_delay: delay,
        auto_caption: document.getElementById('set-caption').classList.contains('on'),
        auto_hashtags: document.getElementById('set-hashtags').classList.contains('on'),
        duplicate_protection: document.getElementById('set-dup').classList.contains('on'),
        auto_archive: document.getElementById('set-archive').classList.contains('on'),
    };
    try {
        await api('/api/settings', { method: 'POST', body: settings });
        toast('Settings saved!', 'success');
    } catch (e) { toast('Failed to save settings', 'error'); }
}

// ── Account Loader & Switcher ────────────────────────────────────────────────

async function loadAccounts() {
    try {
        const data = await api('/api/accounts');
        currentActiveUser = data.active || '';
        const activeEl = document.getElementById('active-account');
        if (activeEl) activeEl.textContent = `@${data.active}`;
        const sel = document.getElementById('account-select');
        const accounts = Array.isArray(data.accounts) ? data.accounts : Object.values(data.accounts || {});
        autoPostAccountsList = accounts;
        if (typeof botAccountsList !== 'undefined') {
            botAccountsList = accounts;
        }
        if (sel) {
            sel.innerHTML = accounts.map(a => {
                const uname = typeof a === 'string' ? a : a.username;
                const label = typeof a === 'string' ? `@${a}` : `@${a.username}${a.display_name && a.display_name !== a.username ? ' · ' + a.display_name : ''}`;
                return `<option value="${uname}" ${uname === data.active ? 'selected' : ''}>${label}</option>`;
            }).join('');
        }
        return data;
    } catch (e) {
        // Fallback to simple account endpoint
        try {
            const data = await api('/api/account');
            currentActiveUser = data.active || '';
            const activeEl = document.getElementById('active-account');
            if (activeEl) activeEl.textContent = `@${data.active}`;
            const sel = document.getElementById('account-select');
            if (sel && Array.isArray(data.accounts)) {
                sel.innerHTML = data.accounts.map(a =>
                    `<option value="${a}" ${a === data.active ? 'selected' : ''}>@${a}</option>`
                ).join('');
            }
            return data;
        } catch (_) {
            const activeEl = document.getElementById('active-account');
            if (activeEl) activeEl.textContent = '@error';
        }
    }
}

const loadAccount = loadAccounts;
if (typeof window !== 'undefined') {
    window.loadAccounts = loadAccounts;
    window.loadAccount = loadAccounts;
}

document.getElementById('account-select').addEventListener('change', async (e) => {
    const username = e.target.value;
    try {
        const res = await api('/api/account/switch', { method: 'POST', body: { username } });
        currentActiveUser = res.active || username;
        const activeDisplay = document.getElementById('active-account');
        if (activeDisplay) activeDisplay.textContent = `@${currentActiveUser}`;

        if (res.is_authenticated === false || res.warning) {
            toast(`⚠️ Switched to @${currentActiveUser} (Session Expired — Reconnect to publish)`, 'warning');
            setTimeout(() => {
                openSessionManagerModal(currentActiveUser, 'cookie');
            }, 350);
        } else {
            toast(`✅ Switched to @${currentActiveUser}`, 'success');
        }

        await loadAccounts();
        if (currentPage === 'bot') {
            renderInteractiveBot(document.getElementById('page-content'));
        } else if (currentPage === 'dashboard') {
            renderDashboard(document.getElementById('page-content'));
        } else if (currentPage === 'settings') {
            renderSettings(document.getElementById('page-content'));
        } else if (currentPage === 'auto-post') {
            selectedAutoPostAccount = currentActiveUser;
            renderAutoPost(document.getElementById('page-content'));
        } else if (currentPage === 'queue' || currentPage === 'post-image' || currentPage === 'post-reel') {
            if (document.getElementById('queue-table-container')) {
                await loadQueueTable(activeQueueFilter, 'queue-table-container');
            }
            if (document.getElementById('global-queue-content')) {
                await loadQueueTable(activeQueueFilter, 'global-queue-content');
            }
        }
    } catch (err) {
        toast('Failed to switch account: ' + (err.message || err), 'error');
    }
});

// ── Init ─────────────────────────────────────────────────────────────────────

document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        navigate(item.dataset.page);
    });
});

loadAccount();
connectWebSocket();
navigate('dashboard');

// ── Unified Session Manager Modal Controller (Screenshots 1-5) ───────────────

let smCachedPassword = '';

function openSessionManagerModal(username = null, defaultTab = 'cookie') {
    const modal = document.getElementById('session-manager-modal');
    if (!modal) return;

    const targetUser = username ? username.replace(/^@/, '') : (currentActiveUser || '');

    // Set usernames across tab inputs
    const cookieUser = document.getElementById('sm-cookie-username');
    if (cookieUser) cookieUser.value = targetUser;

    const pwdUser = document.getElementById('sm-pwd-username');
    if (pwdUser) pwdUser.value = targetUser;

    const otpUser = document.getElementById('sm-otp-username');
    if (otpUser) otpUser.value = targetUser;

    const jsonUser = document.getElementById('sm-json-username');
    if (jsonUser) jsonUser.value = targetUser;

    // Reset status messages
    ['sm-cookie-msg', 'sm-pwd-msg', 'sm-otp-msg', 'sm-json-msg'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.style.display = 'none'; el.innerHTML = ''; }
    });

    switchSmTab(defaultTab || 'cookie');
    if (targetUser) checkPendingChallenge(targetUser);

    modal.style.display = 'flex';
}

function closeSessionManagerModal() {
    const modal = document.getElementById('session-manager-modal');
    if (modal) modal.style.display = 'none';
    smCachedPassword = '';
}

function switchSmTab(tabKey) {
    const tabs = ['cookie', 'password', 'otp', 'json', 'meta'];
    tabs.forEach(t => {
        const btn = document.getElementById(`sm-tab-${t}`);
        const panel = document.getElementById(`sm-panel-${t}`);
        if (btn) {
            if (t === tabKey) btn.classList.add('active');
            else btn.classList.remove('active');
        }
        if (panel) {
            panel.style.display = (t === tabKey) ? 'block' : 'none';
        }
    });

    if (tabKey === 'otp') {
        const otpUser = document.getElementById('sm-otp-username');
        if (otpUser && otpUser.value.trim()) {
            checkPendingChallenge(otpUser.value.trim());
        }
        const otpCode = document.getElementById('sm-otp-code');
        if (otpCode) otpCode.focus();
    }
}

function openReconnectModal(username) {
    openSessionManagerModal(username, 'password');
}

async function checkPendingChallenge(rawUsername) {
    const u = (rawUsername || '').trim().replace(/^@/, '');
    const ind = document.getElementById('sm-otp-challenge-indicator');
    if (!ind) return;
    if (!u) {
        ind.style.display = 'none';
        return;
    }
    try {
        const res = await api(`/api/accounts/${encodeURIComponent(u)}/challenge-status`);
        if (res && res.challenge) {
            const ageSec = Math.floor(res.challenge.age_seconds || 0);
            ind.innerHTML = `⚡ <strong>Pending Challenge Detected:</strong> 2FA initiated ${ageSec}s ago for @${u}. Enter your code below.`;
            ind.style.display = 'block';
        } else {
            ind.style.display = 'none';
        }
    } catch (e) {
        ind.style.display = 'none';
    }
}

async function toggleAccountPublishing(rawUsername) {
    const u = (rawUsername || '').trim().replace(/^@/, '');
    if (!u) return;
    try {
        const res = await api(`/api/accounts/${encodeURIComponent(u)}/toggle-publishing`, { method: 'POST' });
        toast(res.message || `Updated publishing status for @${u}`, 'success');
        await loadAccounts();
        if (currentPage === 'settings') {
            const el = document.getElementById('page-content');
            if (el) renderSettings(el);
        }
    } catch (err) {
        toast(`Failed to update publishing: ${err.message}`, 'error');
    }
}

async function submitSmCookie() {
    const u = (document.getElementById('sm-cookie-username')?.value || '').trim().replace(/^@/, '');
    const sessionId = (document.getElementById('sm-cookie-sessionid')?.value || '').trim();
    const setActive = document.getElementById('sm-cookie-set-active')?.checked ?? true;
    const msg = document.getElementById('sm-cookie-msg');
    const btn = document.getElementById('sm-cookie-btn');

    if (!u) {
        showSmMsg(msg, 'Please enter an Instagram username.', 'error');
        return;
    }
    if (!sessionId) {
        showSmMsg(msg, 'Please paste your browser sessionid cookie.', 'error');
        return;
    }

    if (btn) { btn.disabled = true; btn.innerHTML = '⏳ Verifying session...'; }
    showSmMsg(msg, 'Testing cookie against Instagram API...', 'info');

    try {
        const res = await api(`/api/accounts/${encodeURIComponent(u)}/session-id`, {
            method: 'POST',
            body: { session_id: sessionId, set_active: setActive }
        });
        showSmMsg(msg, `✅ ${res.message || 'Session connected successfully!'}`, 'success');
        toast(`@${u} session verified!`, 'success');
        await loadAccounts();
        if (setActive) {
            currentActiveUser = u;
            document.getElementById('active-account').textContent = `@${u}`;
        }
        setTimeout(() => {
            closeSessionManagerModal();
            if (currentPage === 'settings') renderSettings(document.getElementById('page-content'));
        }, 1200);
    } catch (err) {
        showSmMsg(msg, `❌ ${err.message || 'Verification failed. Cookie may be expired or invalid.'}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '🍪 Accept & Create Session'; }
    }
}

async function submitSmPassword() {
    const u = (document.getElementById('sm-pwd-username')?.value || '').trim().replace(/^@/, '');
    const password = (document.getElementById('sm-pwd-password')?.value || '').trim();
    const setActive = document.getElementById('sm-pwd-set-active')?.checked ?? true;
    const msg = document.getElementById('sm-pwd-msg');
    const btn = document.getElementById('sm-pwd-btn');

    if (!u) {
        showSmMsg(msg, 'Please enter an Instagram username.', 'error');
        return;
    }
    if (!password) {
        showSmMsg(msg, 'Please enter your Instagram password.', 'error');
        return;
    }

    smCachedPassword = password;
    if (btn) { btn.disabled = true; btn.innerHTML = '⏳ Authenticating...'; }
    showSmMsg(msg, 'Contacting Instagram login endpoint...', 'info');

    try {
        const res = await api(`/api/accounts/${encodeURIComponent(u)}/reconnect`, {
            method: 'POST',
            body: { password: password, set_active: setActive }
        });

        // Check if 2FA challenge is required
        if (res.requires_2fa || res.two_factor_required || (res.status && res.status.includes('2fa'))) {
            showSmMsg(msg, '⚠️ 2FA / Checkpoint challenge requested. Redirecting to OTP tab...', 'info');
            setTimeout(() => {
                switchSmTab('otp');
                const otpUser = document.getElementById('sm-otp-username');
                if (otpUser) otpUser.value = u;
                checkPendingChallenge(u);
                const otpMsg = document.getElementById('sm-otp-msg');
                showSmMsg(otpMsg, 'Instagram sent a verification code to your device. Enter the 6-digit code below.', 'info');
            }, 600);
            return;
        }

        showSmMsg(msg, `✅ ${res.message || 'Login successful and session created!'}`, 'success');
        toast(`@${u} authenticated successfully!`, 'success');
        await loadAccounts();
        if (setActive) {
            currentActiveUser = u;
            document.getElementById('active-account').textContent = `@${u}`;
        }
        setTimeout(() => {
            closeSessionManagerModal();
            if (currentPage === 'settings') renderSettings(document.getElementById('page-content'));
        }, 1200);
    } catch (err) {
        const errMsg = err.message || '';
        if (errMsg.toLowerCase().includes('twofactor') || errMsg.toLowerCase().includes('2fa') || errMsg.toLowerCase().includes('challenge') || errMsg.toLowerCase().includes('checkpoint')) {
            showSmMsg(msg, '⚠️ 2FA checkpoint required by Instagram! Switching to OTP verification...', 'info');
            setTimeout(() => {
                switchSmTab('otp');
                const otpUser = document.getElementById('sm-otp-username');
                if (otpUser) otpUser.value = u;
                checkPendingChallenge(u);
                const otpMsg = document.getElementById('sm-otp-msg');
                showSmMsg(otpMsg, 'Please enter your 6-digit verification code below.', 'info');
            }, 700);
        } else {
            showSmMsg(msg, `❌ ${errMsg || 'Login failed. Check your credentials.'}`, 'error');
        }
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '🔐 Accept & Authenticate'; }
    }
}

async function submitSmOtp() {
    const u = (document.getElementById('sm-otp-username')?.value || '').trim().replace(/^@/, '');
    const code = (document.getElementById('sm-otp-code')?.value || '').trim().replace(/\s+/g, '');
    const msg = document.getElementById('sm-otp-msg');
    const btn = document.getElementById('sm-otp-btn');

    if (!u) {
        showSmMsg(msg, 'Please enter an Instagram username.', 'error');
        return;
    }
    if (!code || code.length < 6) {
        showSmMsg(msg, 'Please enter the 6-digit verification code.', 'error');
        return;
    }

    if (btn) { btn.disabled = true; btn.innerHTML = '⏳ Verifying OTP...'; }
    showSmMsg(msg, 'Submitting verification code to Instagram...', 'info');

    try {
        const res = await api(`/api/accounts/${encodeURIComponent(u)}/verify-otp`, {
            method: 'POST',
            body: {
                code: code,
                password: smCachedPassword || '',
                set_active: true
            }
        });

        showSmMsg(msg, `✅ ${res.message || 'OTP verified and session created successfully!'}`, 'success');
        toast(`@${u} 2FA session saved!`, 'success');
        smCachedPassword = '';
        await loadAccounts();
        setTimeout(() => {
            closeSessionManagerModal();
            if (currentPage === 'settings') renderSettings(document.getElementById('page-content'));
        }, 1200);
    } catch (err) {
        showSmMsg(msg, `❌ ${err.message || 'OTP verification failed. Code may be invalid or expired.'}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '🔑 Accept OTP & Verify Session'; }
    }
}

async function submitSmJson() {
    const u = (document.getElementById('sm-json-username')?.value || '').trim().replace(/^@/, '');
    const jsonStr = (document.getElementById('sm-json-content')?.value || '').trim();
    const setActive = document.getElementById('sm-json-set-active')?.checked ?? true;
    const msg = document.getElementById('sm-json-msg');
    const btn = document.getElementById('sm-json-btn');

    if (!u) {
        showSmMsg(msg, 'Please enter an Instagram username.', 'error');
        return;
    }
    if (!jsonStr) {
        showSmMsg(msg, 'Please paste the session JSON dictionary.', 'error');
        return;
    }

    try {
        JSON.parse(jsonStr);
    } catch (e) {
        showSmMsg(msg, 'Invalid JSON format. Please paste a valid JSON dictionary.', 'error');
        return;
    }

    if (btn) { btn.disabled = true; btn.innerHTML = '⏳ Saving & verifying JSON...'; }
    showSmMsg(msg, 'Validating session dictionary against Instagram...', 'info');

    try {
        const res = await api(`/api/accounts/${encodeURIComponent(u)}/session-json`, {
            method: 'POST',
            body: { session_json: jsonStr, set_active: setActive }
        });

        showSmMsg(msg, `✅ ${res.message || 'Session JSON imported and verified!'}`, 'success');
        toast(`@${u} session JSON saved!`, 'success');
        await loadAccounts();
        if (setActive) {
            currentActiveUser = u;
            document.getElementById('active-account').textContent = `@${u}`;
        }
        setTimeout(() => {
            closeSessionManagerModal();
            if (currentPage === 'settings') renderSettings(document.getElementById('page-content'));
        }, 1200);
    } catch (err) {
        showSmMsg(msg, `❌ ${err.message || 'Failed to import session JSON.'}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '📄 Accept & Save Session JSON'; }
    }
}

async function launchMetaOAuth() {
    try {
        const info = await api('/api/meta-oauth-info');
        if (info && info.oauth_url) {
            window.open(info.oauth_url, '_blank', 'width=700,height=650');
            toast('Opened Meta Graph API authorization window.', 'info');
        } else {
            toast('Meta App ID configured: 1063180003141134', 'info');
        }
    } catch (e) {
        toast('Opening Meta App authorization...', 'info');
        window.open('https://developers.facebook.com/apps/1063180003141134', '_blank');
    }
}

function showSmMsg(el, text, type) {
    if (!el) return;
    el.style.display = 'block';
    el.innerHTML = text;
    if (type === 'error') {
        el.style.background = 'rgba(239, 68, 68, 0.15)';
        el.style.border = '1px solid rgba(239, 68, 68, 0.4)';
        el.style.color = '#fca5a5';
    } else if (type === 'success') {
        el.style.background = 'rgba(16, 185, 129, 0.15)';
        el.style.border = '1px solid rgba(16, 185, 129, 0.4)';
        el.style.color = '#6ee7b7';
    } else {
        el.style.background = 'rgba(59, 130, 246, 0.15)';
        el.style.border = '1px solid rgba(59, 130, 246, 0.4)';
        el.style.color = '#93c5fd';
    }
}
