/**
 * Gemini AI 질문/답변 로직
 */

let chatHistory = [];
let isAiLoading = false;

// 추천 질문 클릭
function askSuggestion(btn) {
    const question = btn.textContent.trim();
    const input = document.getElementById('ai-input');
    if (input) {
        input.value = question;
        sendAiQuestion();
    }
}

// 질문 전송
async function sendAiQuestion() {
    const input = document.getElementById('ai-input');
    const question = input.value.trim();
    if (!question || isAiLoading) return;

    isAiLoading = true;
    input.value = '';
    autoResizeInput(input);

    // 추천 질문 숨기기
    const suggestions = document.querySelector('.ai-suggestions');
    if (suggestions) suggestions.style.display = 'none';

    // 유저 메시지 추가
    appendMessage('user', question);
    chatHistory.push({ role: 'user', content: question });

    // 로딩 표시
    const loadingId = appendLoading();

    // 전송 버튼 비활성화
    const sendBtn = document.getElementById('ai-send-btn');
    if (sendBtn) sendBtn.disabled = true;

    try {
        const res = await fetch('/api/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                history: chatHistory.slice(-10)
            })
        });

        if (!res.ok) {
            removeLoading(loadingId);
            const errData = await res.json().catch(() => ({}));
            const errMsg = errData.error || `서버 오류 (${res.status})`;
            appendMessage('bot', `⚠️ ${errMsg}\n\n잠시 후 다시 시도해 주세요.`);
            return;
        }

        // 스트리밍 시작
        removeLoading(loadingId);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullAnswer = '';

        // 봇 메시지 버블 먼저 생성 (빈 내용)
        const botMsgDiv = appendMessage('bot', '');
        const bubble = botMsgDiv.querySelector('.ai-bubble');

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            fullAnswer += chunk;

            // 실시간 렌더링 (마크다운 포함)
            bubble.innerHTML = renderMarkdown(fullAnswer);
            scrollToBottom();
        }

        chatHistory.push({ role: 'assistant', content: fullAnswer });
    } catch (e) {
        removeLoading(loadingId);
        appendMessage('bot', `⚠️ 네트워크 오류가 발생했습니다.\n\n${e.message}`);
    } finally {
        isAiLoading = false;
        if (sendBtn) sendBtn.disabled = false;
        input.focus();
    }
}

// 메시지 추가
function appendMessage(role, content) {
    const container = document.getElementById('ai-messages');
    if (!container) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = `ai-message ai-${role === 'user' ? 'user' : 'bot'}`;

    if (role === 'user') {
        msgDiv.innerHTML = `
            <div class="ai-bubble">${escapeHtml(content)}</div>
            <div class="ai-avatar">👤</div>
        `;
    } else {
        msgDiv.innerHTML = `
            <div class="ai-avatar">🤖</div>
            <div class="ai-bubble">${renderMarkdown(content)}</div>
        `;
    }

    container.appendChild(msgDiv);
    scrollToBottom();
    return msgDiv;
}

// 로딩 애니메이션
let loadingCounter = 0;
function appendLoading() {
    const container = document.getElementById('ai-messages');
    if (!container) return null;

    const id = `ai-loading-${++loadingCounter}`;
    const loadDiv = document.createElement('div');
    loadDiv.className = 'ai-message ai-bot';
    loadDiv.id = id;
    loadDiv.innerHTML = `
        <div class="ai-avatar">🤖</div>
        <div class="ai-bubble ai-typing">
            <div class="typing-dots">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;
    container.appendChild(loadDiv);
    scrollToBottom();
    return id;
}

function removeLoading(id) {
    if (!id) return;
    const el = document.getElementById(id);
    if (el) el.remove();
}

// 스크롤 하단으로
function scrollToBottom() {
    const chat = document.getElementById('ai-chat-container');
    if (chat) {
        requestAnimationFrame(() => {
            chat.scrollTop = chat.scrollHeight;
        });
    }
}

// HTML 이스케이프
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 간단한 마크다운 렌더링
function renderMarkdown(text) {
    if (!text) return '';

    let html = escapeHtml(text);

    // 코드 블록 (```)
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');

    // 인라인 코드 (`)
    html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

    // 굵은 글씨 (**)
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // 이탤릭 (*)
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // 제목 (###, ##, #)
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');

    // 리스트 (- 또는 *)
    html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // 번호 리스트
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // 줄바꿈
    html = html.replace(/\n/g, '<br>');

    // 연속 <br> 정리
    html = html.replace(/(<br>){3,}/g, '<br><br>');

    return html;
}

// textarea 자동 높이 조절
function autoResizeInput(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

// 이벤트 바인딩
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('ai-input');
    if (input) {
        // Enter 키로 전송 (Shift+Enter는 줄바꿈)
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendAiQuestion();
            }
        });

        // 자동 높이 조절
        input.addEventListener('input', () => autoResizeInput(input));
    }
});
