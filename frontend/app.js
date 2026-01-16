/**
 * KdB Assistant Frontend
 * XLSXアップロード対応版
 */

// 本番環境（Render）では同一オリジン、開発時はlocalhost
const API_BASE = window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : '';

// セッション情報
let sessionId = null;
let courseCount = 0;
let apiKey = ''; // ユーザー設定のAPIキー

// DOM要素
const uploadScreen = document.getElementById('upload-screen');
const chatScreen = document.getElementById('chat-screen');
const uploadBox = document.getElementById('upload-box');
const fileInput = document.getElementById('file-input');
const uploadProgress = document.getElementById('upload-progress');
const progressText = document.getElementById('progress-text');
const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const courseCountEl = document.getElementById('course-count');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const hamburgerBtn = document.getElementById('hamburger-btn');
const apiKeyInput = document.getElementById('api-key-input');

// 初期化
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    setupTextareaAutoResize();
    loadApiKey(); // 保存されたAPIキーを読み込み
    updateRateLimitDisplay(); // レート制限表示を初期化
    startRateLimitTimer(); // タイマー開始
});

// ========== アップロード関連 ==========

function setupEventListeners() {
    // ファイルアップロード
    uploadBox?.addEventListener('click', () => fileInput?.click());
    uploadBox?.addEventListener('dragover', handleDragOver);
    uploadBox?.addEventListener('dragleave', handleDragLeave);
    uploadBox?.addEventListener('drop', handleDrop);
    fileInput?.addEventListener('change', handleFileSelect);

    // チャット
    document.getElementById('chat-form')?.addEventListener('submit', sendMessage);
    messageInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(e);
        }
    });
}

function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    uploadBox.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    uploadBox.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    uploadBox.classList.remove('dragover');

    const files = e.dataTransfer?.files;
    if (files && files[0]) {
        handleFileUpload(files[0]);
    }
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files && files[0]) {
        handleFileUpload(files[0]);
    }
}

async function handleFileUpload(file) {
    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
        alert('XLSXまたはXLSファイルをアップロードしてください');
        return;
    }

    // 進捗表示
    uploadBox.style.display = 'none';
    uploadProgress.style.display = 'block';
    progressText.textContent = 'ファイルをアップロード中...';

    const formData = new FormData();
    formData.append('file', file);

    try {
        progressText.textContent = 'シラバスデータを解析中...';

        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'アップロードに失敗しました');
        }

        const data = await response.json();
        sessionId = data.session_id;
        courseCount = data.course_count;

        progressText.textContent = `${courseCount}件の科目を読み込みました！`;

        // 少し待ってからチャット画面へ直接遷移
        await new Promise(resolve => setTimeout(resolve, 500));

        showChatScreen();

    } catch (error) {
        console.error('Upload error:', error);
        alert(`エラー: ${error.message}`);
        uploadBox.style.display = 'block';
        uploadProgress.style.display = 'none';
    }
}

// サイドバーのフィルター値を取得
function getFilterValues() {
    const categorySelect = document.getElementById('filter-category');
    const yearSelect = document.getElementById('filter-year');
    const courseTypeSelect = document.getElementById('filter-course-type');
    return {
        category: categorySelect?.value || '',
        year: yearSelect?.value || '',
        course_type: courseTypeSelect?.value || '',
    };
}

function showChatScreen() {
    uploadScreen.style.display = 'none';
    chatScreen.style.display = 'flex';
    courseCountEl.textContent = courseCount;

    // サイドバーに現在のプロフィールを表示
    updateProfileDisplay();

    messageInput.focus();
}

function updateProfileDisplay() {
    const categoryEl = document.getElementById('profile-info-category');
    const yearEl = document.getElementById('profile-info-year');

    if (categoryEl) {
        categoryEl.textContent = userCategory || '指定なし';
    }
    if (yearEl) {
        yearEl.textContent = userYear ? `${userYear}年次` : '指定なし';
    }
}

function resetSession() {
    if (confirm('現在のセッションを終了して、新しいファイルをアップロードしますか？')) {
        // セッション削除
        if (sessionId) {
            fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' }).catch(() => { });
        }

        sessionId = null;
        courseCount = 0;
        userCategory = '';
        userYear = '';

        // UI リセット
        chatScreen.style.display = 'none';
        profileScreen.style.display = 'none';
        uploadScreen.style.display = 'flex';
        uploadBox.style.display = 'block';
        uploadProgress.style.display = 'none';

        // チャット履歴クリア
        chatMessages.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">🤖</div>
                <h2>こんにちは！</h2>
                <p>筑波大学の履修相談AIアシスタントです。<br>授業選びに困ったら、何でも質問してください！</p>
                <div class="example-questions">
                    <p>例：</p>
                    <button class="example-btn" onclick="askExample(this)">プログラミング初心者向けの授業を教えて</button>
                    <button class="example-btn" onclick="askExample(this)">おすすめの授業は？</button>
                    <button class="example-btn" onclick="askExample(this)">AIや機械学習を学べる授業はある？</button>
                    <button class="example-btn" onclick="askExample(this)">英語以外の外国語でおすすめは？</button>
                </div>
            </div>
        `;
    }
}

// ========== チャット関連 ==========

function setupTextareaAutoResize() {
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
    });
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage(event);
    }
}

async function sendMessage(event) {
    event.preventDefault();

    const message = messageInput.value.trim();
    if (!message || !sessionId) return;

    // APIキーがある場合のみレート制限をチェック
    if (apiKey) {
        const rateCheck = checkRateLimit();
        if (!rateCheck.allowed) {
            showToast(rateCheck.message, true);
            return;
        }
    }

    // 入力をクリア
    messageInput.value = '';
    messageInput.style.height = 'auto';

    // ウェルカムメッセージを削除
    const welcome = chatMessages.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    // ユーザーメッセージを追加
    addMessage(message, 'user');

    // AIメッセージ用のプレースホルダ
    const aiMessage = addMessage('', 'assistant');
    const contentDiv = aiMessage.querySelector('.message-content');

    // 送信ボタンを無効化
    sendBtn.disabled = true;

    try {
        // サイドバーのフィルター値を取得
        const filters = getFilterValues();

        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                session_id: sessionId,
                category: filters.category,
                year_level: filters.year,
                course_type: filters.course_type,
                api_key: apiKey || null, // ユーザーのAPIキー
                stream: true,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'エラーが発生しました');
        }

        // ストリーミングレスポンスを処理
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text = decoder.decode(value);
            const lines = text.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data === '[DONE]') continue;

                    try {
                        const parsed = JSON.parse(data);
                        if (parsed.text) {
                            fullText += parsed.text;
                            contentDiv.innerHTML = formatMarkdown(fullText);
                        }
                    } catch (e) {
                        // JSONパースエラーは無視
                    }
                }
            }

            // スクロール
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

    } catch (error) {
        console.error('Chat error:', error);
        contentDiv.innerHTML = `<p class="error">エラーが発生しました: ${error.message}</p>`;
    } finally {
        sendBtn.disabled = false;
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // APIキー使用時は使用回数を記録
        if (apiKey) {
            recordApiUsage();
        }
    }
}

function addMessage(content, role) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const icon = role === 'user' ? '👤' : '🤖';

    messageDiv.innerHTML = `
        <div class="message-icon">${icon}</div>
        <div class="message-content">${content ? formatMarkdown(content) : '<span class="typing">考え中...</span>'}</div>
    `;

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return messageDiv;
}

function askExample(button) {
    if (!sessionId) {
        alert('まずXLSXファイルをアップロードしてください');
        return;
    }
    messageInput.value = button.textContent;
    sendMessage(new Event('submit'));
}

// ========== Markdownフォーマット ==========

function formatMarkdown(text) {
    // details/summaryタグを保護（改行を一時的に置換）
    let html = text;

    // detailsブロック内の改行を保護
    html = html.replace(/<details>([\s\S]*?)<\/details>/g, (match, content) => {
        const protectedContent = content.replace(/\n/g, '{{NEWLINE}}');
        return `<details>${protectedContent}</details>`;
    });

    // 通常の改行をbrに変換
    html = html.replace(/\n/g, '<br>');

    // 保護した改行を戻す
    html = html.replace(/\{\{NEWLINE\}\}/g, '\n');

    // マークダウンリンク [text](url) → <a href="url">text</a>
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="course-link">$1</a>');

    // 太字
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // 見出し（brの後でもマッチするように）
    html = html.replace(/(<br>|^)### (.*?)(<br>|$)/gm, '$1<h4 class="section-title">$2</h4>');
    html = html.replace(/(<br>|^)## (.*?)(<br>|$)/gm, '$1<h3 class="section-title">$2</h3>');
    html = html.replace(/(<br>|^)# (.*?)(<br>|$)/gm, '$1<h2 class="section-title">$2</h2>');

    // リスト（detailsの外のみ）
    html = html.replace(/^- (.*?)(<br>|$)/gm, '<li>$1</li>');

    // 番号付きリスト
    html = html.replace(/^\d+\. (.*?)(<br>|$)/gm, '<li>$1</li>');

    // 水平線
    html = html.replace(/^---(<br>|$)/gm, '<hr>');

    // コードブロック
    html = html.replace(/```(.*?)```/gs, '<pre><code>$1</code></pre>');

    // インラインコード
    html = html.replace(/`(.*?)`/g, '<code>$1</code>');

    return html;
}

// ========== サイドバー制御 ==========

function toggleSidebar() {
    const isOpen = sidebar?.classList.toggle('open');
    sidebarOverlay?.classList.toggle('active', isOpen);
    hamburgerBtn?.classList.toggle('active', isOpen);
}

function closeSidebar() {
    sidebar?.classList.remove('open');
    sidebarOverlay?.classList.remove('active');
    hamburgerBtn?.classList.remove('active');
}

// ========== APIキー管理 ==========

function loadApiKey() {
    const savedKey = localStorage.getItem('kdb_api_key');
    if (savedKey) {
        apiKey = savedKey;
        if (apiKeyInput) {
            apiKeyInput.value = savedKey;
        }
    }
}

function saveApiKey() {
    const inputEl = document.getElementById('api-key-input');
    const key = inputEl?.value?.trim() || '';

    if (!key) {
        showToast('APIキーを入力してください', true);
        return;
    }

    apiKey = key;
    localStorage.setItem('kdb_api_key', key);
    showToast('APIキーを保存しました ✓');
    updateRateLimitDisplay(); // レート制限表示を更新
}

function toggleApiKeyVisibility() {
    const inputEl = document.getElementById('api-key-input');
    if (inputEl) {
        inputEl.type = inputEl.type === 'password' ? 'text' : 'password';
    }
}

function deleteApiKey() {
    if (!confirm('APIキーを削除しますか？')) {
        return;
    }

    apiKey = '';
    localStorage.removeItem('kdb_api_key');

    const inputEl = document.getElementById('api-key-input');
    if (inputEl) {
        inputEl.value = '';
    }

    showToast('APIキーを削除しました');
    updateRateLimitDisplay(); // レート制限表示を更新（非表示になる）
}

// ========== レート制限 ==========

const RATE_LIMIT_INTERVAL = 2 * 60 * 1000; // 2分（ミリ秒）
const DAILY_LIMIT = 5; // 1日の最大回数

function checkRateLimit() {
    const now = Date.now();
    const today = new Date().toDateString();

    // LocalStorageからレート制限情報を取得
    const lastUsed = parseInt(localStorage.getItem('kdb_last_api_use') || '0');
    const dailyData = JSON.parse(localStorage.getItem('kdb_daily_usage') || '{}');

    // 日付が変わっていたらリセット
    if (dailyData.date !== today) {
        dailyData.date = today;
        dailyData.count = 0;
        localStorage.setItem('kdb_daily_usage', JSON.stringify(dailyData));
    }

    // 1日の上限チェック
    if (dailyData.count >= DAILY_LIMIT) {
        return {
            allowed: false,
            message: `本日のAI検索上限（${DAILY_LIMIT}回）に達しました。明日また使えます。`
        };
    }

    // 2分間隔チェック
    const elapsed = now - lastUsed;
    if (elapsed < RATE_LIMIT_INTERVAL) {
        const remaining = Math.ceil((RATE_LIMIT_INTERVAL - elapsed) / 1000);
        const min = Math.floor(remaining / 60);
        const sec = remaining % 60;
        return {
            allowed: false,
            message: `AI検索は2分に1回です。あと${min}分${sec}秒お待ちください。`
        };
    }

    return { allowed: true };
}

function recordApiUsage() {
    const now = Date.now();
    const today = new Date().toDateString();

    // 最終使用時刻を記録
    localStorage.setItem('kdb_last_api_use', now.toString());

    // 日次カウントを更新
    const dailyData = JSON.parse(localStorage.getItem('kdb_daily_usage') || '{}');
    if (dailyData.date !== today) {
        dailyData.date = today;
        dailyData.count = 0;
    }
    dailyData.count = (dailyData.count || 0) + 1;
    localStorage.setItem('kdb_daily_usage', JSON.stringify(dailyData));

    console.log(`[RATE LIMIT] API used: ${dailyData.count}/${DAILY_LIMIT} today`);

    // 表示を更新
    updateRateLimitDisplay();
}

function updateRateLimitDisplay() {
    const statusEl = document.getElementById('rate-limit-status');
    const countEl = document.getElementById('daily-count');
    const timerEl = document.getElementById('cooldown-timer');

    // APIキーがない場合は非表示
    if (!apiKey) {
        if (statusEl) statusEl.style.display = 'none';
        return;
    }

    // 表示
    if (statusEl) statusEl.style.display = 'block';

    const now = Date.now();
    const today = new Date().toDateString();
    const lastUsed = parseInt(localStorage.getItem('kdb_last_api_use') || '0');
    const dailyData = JSON.parse(localStorage.getItem('kdb_daily_usage') || '{}');

    // 日付リセット
    const count = (dailyData.date === today) ? (dailyData.count || 0) : 0;

    // カウント表示
    if (countEl) {
        countEl.textContent = count;
    }

    // クールダウンタイマー
    if (timerEl) {
        const elapsed = now - lastUsed;
        if (elapsed < RATE_LIMIT_INTERVAL) {
            const remaining = Math.ceil((RATE_LIMIT_INTERVAL - elapsed) / 1000);
            const min = Math.floor(remaining / 60);
            const sec = remaining % 60;
            timerEl.textContent = `⏱️ 次回まで: ${min}分${sec.toString().padStart(2, '0')}秒`;
            timerEl.className = 'rate-limit-timer';
        } else {
            timerEl.textContent = '✅ 送信可能';
            timerEl.className = 'rate-limit-timer ready';
        }
    }
}

// レート制限表示を1秒ごとに更新
let rateLimitTimer = null;

function startRateLimitTimer() {
    if (rateLimitTimer) clearInterval(rateLimitTimer);
    rateLimitTimer = setInterval(updateRateLimitDisplay, 1000);
}

// ========== トースト通知 ==========

function showToast(message, isError = false) {
    // 既存のトーストを削除
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    const toast = document.createElement('div');
    toast.className = `toast ${isError ? 'error' : ''}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    // 表示
    setTimeout(() => toast.classList.add('show'), 10);

    // 3秒後に非表示
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
