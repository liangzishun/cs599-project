/**
 * chat.js — 聊天功能模块
 *
 * 处理消息发送、SSE 流式接收、消息渲染。
 */

const ChatModule = (() => {
    // ── 私有状态 ──
    let _currentConversationId = null;
    let _isStreaming = false;
    let _currentAssistantMessage = '';
    let _pendingToolCalls = [];

    // DOM 引用
    const els = {
        get chatContainer() { return document.getElementById('chatContainer'); },
        get welcomeScreen() { return document.getElementById('welcomeScreen'); },
        get messagesContainer() { return document.getElementById('messagesContainer'); },
        get thinkingIndicator() { return document.getElementById('thinkingIndicator'); },
        get messageInput() { return document.getElementById('messageInput'); },
        get btnSend() { return document.getElementById('btnSend'); },
        get currentChatTitle() { return document.getElementById('currentChatTitle'); },
    };

    // ── 初始化 ──
    function init() {
        els.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        els.btnSend.addEventListener('click', sendMessage);
    }

    // ── 发送消息 ──
    async function sendMessage() {
        if (_isStreaming) return;

        const message = els.messageInput.value.trim();
        if (!message) return;

        // 隐藏欢迎界面
        els.welcomeScreen.style.display = 'none';
        els.messagesContainer.style.display = 'flex';

        // 渲染用户消息
        renderMessage('user', message);

        // 清空输入
        els.messageInput.value = '';
        els.messageInput.disabled = true;
        els.btnSend.disabled = true;

        // 显示思考指示器
        showThinking(true);

        // 准备 SSE 流
        _currentAssistantMessage = '';
        _pendingToolCalls = [];
        _isStreaming = true;

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    conversation_id: _currentConversationId,
                }),
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData?.error?.message || `请求失败 (${response.status})`);
            }

            // 读取 SSE 流
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';  // 保留不完整行

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const event = JSON.parse(line.slice(6));
                            handleSSEEvent(event);
                        } catch (e) {
                            // 忽略解析错误（可能是空 data）
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Chat error:', error);
            renderMessage('assistant', '', true, error.message);
        } finally {
            _isStreaming = false;
            els.messageInput.disabled = false;
            els.btnSend.disabled = false;
            els.messageInput.focus();
            showThinking(false);
        }
    }

    // ── SSE 事件处理 ──
    function handleSSEEvent(event) {
        // 保存 conversation_id
        if (event.conversation_id) {
            _currentConversationId = event.conversation_id;
        }

        switch (event.type) {
            case 'thinking':
                showThinking(true, event.content);
                break;

            case 'tool_call':
                _pendingToolCalls.push({
                    name: event.name,
                    args: event.args,
                    id: event.id,
                });
                renderToolCallBadge(event.name, 'pending');
                break;

            case 'tool_result':
                // 更新工具调用状态
                const tc = _pendingToolCalls.find(t => t.name === event.name);
                if (tc) {
                    renderToolCallBadge(event.name, event.error ? 'error' : 'success');
                }
                break;

            case 'message':
                _currentAssistantMessage += event.content;
                // 移除之前的临时 assistant 消息，重新渲染
                removeLastAssistantMessage();
                renderMessage('assistant', _currentAssistantMessage);
                break;

            case 'error':
                renderMessage('assistant', '', true, event.content);
                break;

            case 'done':
                _pendingToolCalls = [];
                showThinking(false);
                // 通知 App 模块刷新对话列表
                if (typeof AppModule !== 'undefined') {
                    AppModule.refreshConversationList();
                }
                break;
        }
    }

    // ── 消息渲染 ──
    function renderMessage(role, content, isError = false, errorMsg = '') {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        msgDiv.dataset.role = role;

        // 头像
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = role === 'user' ? '👤' : '📚';
        msgDiv.appendChild(avatar);

        // 内容
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        if (isError) {
            contentDiv.innerHTML = `<div class="error-banner">⚠️ ${escapeHtml(errorMsg || '发生错误')}</div>`;
        } else if (role === 'assistant') {
            contentDiv.innerHTML = formatMarkdown(content);
        } else {
            contentDiv.textContent = content;
        }

        msgDiv.appendChild(contentDiv);
        els.messagesContainer.appendChild(msgDiv);

        // 滚动到底部
        els.chatContainer.scrollTop = els.chatContainer.scrollHeight;

        return msgDiv;
    }

    function removeLastAssistantMessage() {
        const msgs = els.messagesContainer.querySelectorAll('.message.assistant');
        const last = msgs[msgs.length - 1];
        if (last) last.remove();
    }

    function renderToolCallBadge(toolName, status) {
        const badges = els.messagesContainer.querySelectorAll('.tool-call-badge');
        // 更新已存在的 badge
        for (const badge of badges) {
            if (badge.textContent.includes(toolName) && status !== 'pending') {
                if (status === 'error') {
                    badge.className = 'tool-call-badge error';
                }
                return;
            }
        }
        // 创建新 badge
        const nameMap = {
            'search_books': '🔍 搜索书籍',
            'get_book_detail': '📖 获取详情',
            'analyze_preferences': '🧠 分析偏好',
        };
        const displayName = nameMap[toolName] || toolName;

        const badge = document.createElement('div');
        badge.className = 'tool-call-badge';
        badge.textContent = displayName;
        els.messagesContainer.appendChild(badge);
    }

    function showThinking(show, text = '') {
        els.thinkingIndicator.style.display = show ? 'flex' : 'none';
        if (show && text) {
            els.thinkingIndicator.querySelector('.thinking-text').textContent = text;
        }
    }

    // ── 格式化 ──
    function formatMarkdown(text) {
        if (!text) return '';
        let html = escapeHtml(text);
        // 加粗
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // 换行
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ── 公开 API ──
    return {
        init,
        sendMessage,
        setConversationId(id) { _currentConversationId = id; },
        getConversationId() { return _currentConversationId; },
        clearChat() {
            _currentConversationId = null;
            _currentAssistantMessage = '';
            _pendingToolCalls = [];
            els.messagesContainer.innerHTML = '';
            els.messagesContainer.style.display = 'none';
            els.welcomeScreen.style.display = 'flex';
            els.currentChatTitle.textContent = '新对话';
        },
        loadMessages(messages) {
            els.welcomeScreen.style.display = 'none';
            els.messagesContainer.style.display = 'flex';
            els.messagesContainer.innerHTML = '';
            for (const msg of messages) {
                renderMessage(msg.role, msg.content);
            }
        },
    };
})();
