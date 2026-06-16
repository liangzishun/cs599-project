/**
 * app.js — 应用主逻辑
 *
 * 管理侧边栏、对话列表、页面状态。
 */

const AppModule = (() => {
    // ── DOM 引用 ──
    const els = {
        sidebar: () => document.getElementById('sidebar'),
        conversationList: () => document.getElementById('conversationList'),
        btnNewChat: () => document.getElementById('btnNewChat'),
        btnToggleSidebar: () => document.getElementById('btnToggleSidebar'),
        btnDeleteChat: () => document.getElementById('btnDeleteChat'),
        currentChatTitle: () => document.getElementById('currentChatTitle'),
        apiStatus: () => document.getElementById('apiStatus'),
        quickPrompts: () => document.querySelectorAll('.quick-prompt'),
        bookDetailModal: () => document.getElementById('bookDetailModal'),
        btnCloseModal: () => document.getElementById('btnCloseModal'),
        modalBody: () => document.getElementById('modalBody'),
    };

    let _currentConversationId = null;

    // ── 初始化 ──
    function init() {
        // 初始化聊天模块
        ChatModule.init();

        // 绑定事件
        els.btnNewChat().addEventListener('click', startNewChat);
        els.btnToggleSidebar().addEventListener('click', toggleSidebar);
        els.btnDeleteChat().addEventListener('click', deleteCurrentChat);
        els.btnCloseModal().addEventListener('click', closeModal);

        // 快捷提示
        els.quickPrompts().forEach(btn => {
            btn.addEventListener('click', () => {
                const prompt = btn.dataset.prompt;
                document.getElementById('messageInput').value = prompt;
                ChatModule.sendMessage();
            });
        });

        // 点击弹窗遮罩关闭
        els.bookDetailModal().addEventListener('click', (e) => {
            if (e.target === els.bookDetailModal()) closeModal();
        });

        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === '\\') {
                e.preventDefault();
                toggleSidebar();
            }
        });

        // 检查 API 健康状态
        checkApiHealth();
        // 加载对话列表
        refreshConversationList();

        // 响应式：移动端默认折叠侧边栏
        if (window.innerWidth <= 768) {
            els.sidebar().classList.add('collapsed');
        }
        window.addEventListener('resize', handleResize);
    }

    // ── 侧边栏 ──
    function toggleSidebar() {
        els.sidebar().classList.toggle('collapsed');
    }

    function handleResize() {
        if (window.innerWidth <= 768) {
            els.sidebar().classList.add('collapsed');
        } else {
            els.sidebar().classList.remove('collapsed');
        }
    }

    // ── 对话管理 ──
    function startNewChat() {
        if (ChatModule.getConversationId()) {
            ChatModule.clearChat();
        }
        _currentConversationId = null;
        els.currentChatTitle().textContent = '新对话';
        els.btnDeleteChat().style.display = 'none';
        document.getElementById('messageInput').focus();

        // 移动端收起侧边栏
        if (window.innerWidth <= 768) {
            els.sidebar().classList.add('collapsed');
        }
    }

    async function refreshConversationList() {
        try {
            const response = await fetch('/api/conversations');
            if (!response.ok) return;
            const data = await response.json();

            const list = els.conversationList();
            list.innerHTML = '';

            if (data.conversations.length === 0) {
                list.innerHTML = '<div style="padding:16px;text-align:center;opacity:0.5;font-size:0.85rem;">暂无对话记录</div>';
                return;
            }

            for (const conv of data.conversations) {
                const item = document.createElement('div');
                item.className = 'conversation-item';
                if (conv.id === _currentConversationId) {
                    item.classList.add('active');
                }

                item.innerHTML = `
                    <span class="conversation-item-title">${escapeHtml(conv.title)}</span>
                    <span class="conversation-item-count">${conv.message_count}</span>
                `;

                item.addEventListener('click', () => loadConversation(conv.id));
                list.appendChild(item);
            }
        } catch (e) {
            console.error('Failed to load conversations:', e);
        }
    }

    async function loadConversation(conversationId) {
        try {
            const response = await fetch(`/api/conversations/${conversationId}`);
            if (!response.ok) throw new Error('对话不存在');

            const data = await response.json();
            _currentConversationId = conversationId;
            ChatModule.setConversationId(conversationId);
            ChatModule.loadMessages(data.messages);

            els.currentChatTitle().textContent = data.title || '对话';
            els.btnDeleteChat().style.display = 'block';

            // 更新侧边栏高亮
            refreshConversationList();

            // 移动端收起侧边栏
            if (window.innerWidth <= 768) {
                els.sidebar().classList.add('collapsed');
            }
        } catch (e) {
            console.error('Failed to load conversation:', e);
        }
    }

    async function deleteCurrentChat() {
        if (!_currentConversationId) return;

        if (!confirm('确定要删除这个对话吗？此操作不可撤销。')) return;

        try {
            const response = await fetch(`/api/conversations/${_currentConversationId}`, {
                method: 'DELETE',
            });
            if (!response.ok) throw new Error('删除失败');

            startNewChat();
            refreshConversationList();
        } catch (e) {
            console.error('Failed to delete conversation:', e);
            alert('删除失败，请重试');
        }
    }

    // ── API 健康检查 ──
    async function checkApiHealth() {
        const statusEl = els.apiStatus();
        const dot = statusEl.querySelector('.status-dot');
        const text = statusEl.querySelector('.status-text');

        dot.className = 'status-dot checking';
        text.textContent = '检查连接...';

        try {
            const response = await fetch('/api/health');
            if (response.ok) {
                dot.className = 'status-dot connected';
                text.textContent = '服务已连接';
            } else {
                throw new Error('Unhealthy');
            }
        } catch (e) {
            dot.className = 'status-dot error';
            text.textContent = '连接失败';
        }
    }

    // ── 弹窗 ──
    function openBookDetail(bookData) {
        const modal = els.bookDetailModal();
        const body = els.modalBody();

        body.innerHTML = `
            <div style="display:flex;gap:20px;">
                <div style="flex-shrink:0;">
                    <img src="${bookData.cover_url || ''}"
                         alt="${escapeHtml(bookData.title)}"
                         style="width:150px;border-radius:8px;"
                         onerror="this.style.display='none'">
                </div>
                <div>
                    <h2 style="margin-bottom:8px;">${escapeHtml(bookData.title)}</h2>
                    <p style="color:#64748b;margin-bottom:4px;">作者: ${escapeHtml(bookData.author || 'Unknown')}</p>
                    ${bookData.publish_year ? `<p style="color:#64748b;margin-bottom:4px;">出版年份: ${bookData.publish_year}</p>` : ''}
                    ${bookData.publisher ? `<p style="color:#64748b;margin-bottom:4px;">出版社: ${bookData.publisher}</p>` : ''}
                    ${bookData.ratings_average ? `<p style="color:#64748b;margin-bottom:8px;">评分: ⭐ ${bookData.ratings_average}/5</p>` : ''}
                    ${bookData.description ? `<p style="margin-top:12px;line-height:1.7;">${escapeHtml(bookData.description)}</p>` : ''}
                </div>
            </div>
        `;

        modal.style.display = 'flex';
    }

    function closeModal() {
        els.bookDetailModal().style.display = 'none';
    }

    // ── 工具函数 ──
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    // ── 公开 API ──
    return {
        init,
        refreshConversationList,
        startNewChat,
        openBookDetail,
    };
})();

// ── 启动 ──
document.addEventListener('DOMContentLoaded', () => {
    AppModule.init();
});
