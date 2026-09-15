/* === Chat State === */
const state = { messages: [], isProcessing: false };

const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');

document.addEventListener('DOMContentLoaded', () => {
  setupChat();
  checkInitialQuestion();
  // 异步加载统计用于 Header 指示灯
  fetch('/api/stats').then(r => r.json()).then(s => {
    const sd = document.getElementById('status-faiss');
    if (sd) sd.className = 'status-dot ' + (s.vector_count > 0 ? 'green' : 'amber');
  }).catch(() => {});
  // 清空对话按钮
  const clearBtn = document.getElementById('clearChatBtn');
  if (clearBtn) clearBtn.addEventListener('click', () => {
    state.messages = [];
    chatMessages.innerHTML = `<div class="chat-welcome">
      <div class="welcome-icon"><svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg></div>
      <h2>开始智能问答</h2><p>上传文档后即可向 AI 提问，系统会自动检索相关知识并生成回答。</p>
      <div class="welcome-hints">
        <button class="hint-btn" data-question="请介绍一下知识库中有哪些文档？">有哪些文档？</button>
        <button class="hint-btn" data-question="请总结当前知识库中所有核心技术参数">总结技术参数</button>
        <button class="hint-btn" data-question="请帮我分析知识库中提到的中断机制">分析中断机制</button>
      </div></div>`;
    document.getElementById('historyList').innerHTML = '<div class="doc-empty">暂无对话记录</div>';
    document.querySelectorAll('.hint-btn').forEach(b => {
      b.addEventListener('click', () => { chatInput.value = b.dataset.question; sendMessage(); });
    });
    fetch('/api/chat/clear', { method: 'POST' }).catch(() => {});
  });
});

/* === Chat Setup === */
function setupChat() {
  sendBtn.addEventListener('click', sendMessage);
  chatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  });
  document.querySelectorAll('.hint-btn').forEach(btn => {
    btn.addEventListener('click', () => { chatInput.value = btn.dataset.question; sendMessage(); });
  });
}

function checkInitialQuestion() {
  const q = sessionStorage.getItem('initial_question');
  if (q) { sessionStorage.removeItem('initial_question'); chatInput.value = q; sendMessage(); }
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || state.isProcessing) return;
  chatInput.value = ''; chatInput.style.height = 'auto';
  state.isProcessing = true; sendBtn.disabled = true;

  const welcome = chatMessages.querySelector('.chat-welcome');
  if (welcome) welcome.remove();

  addMessage('user', text);
  state.messages.push({ role: 'user', content: text });

  const loadingEl = addLoadingMessage();
  try {
    const res = await fetch('/api/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ message: text, history: state.messages.slice(0, -1) }),
    });
    const data = await res.json();
    loadingEl.remove();
    addAssistantMessage(data.response, data.thinking, data.sources);
    state.messages.push({ role: 'assistant', content: data.response });
    updateHistorySidebar(text);
  } catch (e) { loadingEl.remove(); addMessage('assistant', '请求失败: ' + e.message); }

  state.isProcessing = false; sendBtn.disabled = false;
  chatInput.focus(); scrollToBottom(chatMessages);
}

/* === Message Rendering === */
function addMessage(role, content) {
  const row = document.createElement('div');
  row.className = 'message-row ' + role;
  row.innerHTML = `<div class="message-avatar">${role === 'user' ? 'You' : 'AI'}</div><div class="message-bubble">${escapeHtml(content)}</div>`;
  chatMessages.appendChild(row);
  scrollToBottom(chatMessages);
  return row;
}

function addLoadingMessage() {
  const row = document.createElement('div');
  row.className = 'message-row assistant';
  row.innerHTML = `<div class="message-avatar">AI</div><div class="message-bubble"><div class="typing-indicator"><span></span><span></span><span></span></div></div>`;
  chatMessages.appendChild(row);
  scrollToBottom(chatMessages);
  return row;
}

function addAssistantMessage(content, thinking, sources) {
  const row = document.createElement('div');
  row.className = 'message-row assistant';
  let html = '<div class="message-avatar">AI</div><div class="message-bubble">';

  if (thinking && thinking.length > 0) {
    const tid = 'thinking-' + Date.now();
    html += `<button class="thinking-toggle" onclick="toggleThinking('${tid}', this)"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg> 思考过程 (${thinking.length} 步)</button>`;
    html += `<div class="thinking-steps" id="${tid}">`;
    for (const step of thinking) {
      if (step.type === 'thought') html += `<div class="think-step thought"><span class="step-icon">💭</span><span class="step-text">${escapeHtml(step.content)}</span></div>`;
      else if (step.type === 'action') html += `<div class="think-step action"><span class="step-icon">🔧</span><span class="step-text">调用: <strong>${escapeHtml(step.tool)}</strong></span><span class="step-args">${escapeHtml(step.args ? JSON.stringify(step.args) : '')}</span></div>`;
      else if (step.type === 'observation') html += `<div class="think-step observation"><span class="step-icon">📋</span><span class="step-text">${escapeHtml(step.content)}</span></div>`;
    }
    html += '</div>';
  }

  html += `<div class="message-content">${formatContent(content)}</div>`;

  if (sources && sources.length > 0) {
    const sid = 'sources-' + Date.now();
    html += `<button class="sources-toggle" onclick="toggleSources('${sid}', this)"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg> 引用来源 (${sources.length})</button>`;
    html += `<div class="sources-list" id="${sid}">`;
    for (const s of sources) {
      const safeContent = (s.content || '').substring(0, 500);
      html += `<div class="source-card"><div class="source-content">${escapeHtml(safeContent)}</div><div class="source-header"><span class="source-filename">📄 ${escapeHtml(s.filename || '?')}</span><span class="source-chunk">第${s.chunk_index || '?'}块</span><span class="source-score">相关度 ${(s.score || 0).toFixed(2)}</span></div></div>`;
    }
    html += '</div>';
  }

  html += '</div>';
  row.innerHTML = html;
  chatMessages.appendChild(row);
  scrollToBottom(chatMessages);
}

function toggleThinking(id, btn) { const el = document.getElementById(id); el.classList.toggle('show'); btn.classList.toggle('open'); }
function toggleSources(id, btn) { const el = document.getElementById(id); el.classList.toggle('show'); }

function updateHistorySidebar(question) {
  const list = document.getElementById('historyList');
  if (!list) return;
  const empty = list.querySelector('.doc-empty');
  if (empty) empty.remove();
  const item = document.createElement('div');
  item.className = 'history-item';
  const now = new Date();
  const time = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  item.innerHTML = `<div class="history-q">${escapeHtml(question.substring(0, 40))}</div><div class="history-time">${time}</div>`;
  list.insertBefore(item, list.firstChild);
  while (list.children.length > 20) list.removeChild(list.lastChild);
}

function formatContent(text) {
  if (!text) return '';
  const imgTagRegex = /\[IMAGE:\s*(.+?)\]:\s*([^\n]*)/g;
  const parts = text.split(imgTagRegex);
  let html = '';
  for (let i = 0; i < parts.length; i++) {
    if (i % 3 === 0) {
      let t = escapeHtml(parts[i] || '');
      t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      t = t.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
      t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
      t = t.replace(/\|(.+)\|/g, (m) => m.includes('---') ? '' : '<tr>' + m.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('') + '</tr>');
      t = t.replace(/(<tr>.*?<\/tr>\s*)+/g, '<table>$&</table>');
      t = t.replace(/\n/g, '<br>');
      html += t;
    } else if (i % 3 === 1) {
      const fname = parts[i];
      const desc = escapeHtml(parts[i + 1] || '图片');
      html += `<div class="msg-image"><img src="/images/${escapeHtml(fname)}" alt="${desc}" onerror="this.parentElement.style.display='none'" style="max-width:100%;border-radius:8px;margin:8px 0;border:1px solid var(--border-color);"><div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:8px;">📷 ${desc}</div></div>`;
    }
  }
  return html;
}
