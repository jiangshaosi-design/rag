/* === Knowledge Base Management === */
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const uploadProgress = document.getElementById('uploadProgress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');

document.addEventListener('DOMContentLoaded', () => {
  loadDocuments();
  loadStats();
  setupUpload();
  setupEval();
});

/* === Document Upload === */
function setupUpload() {
  if (!uploadArea) return;
  uploadArea.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => handleFile(fileInput.files[0]));
  uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
  uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
  uploadArea.addEventListener('drop', e => {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });
}

function handleFile(file) {
  if (!file) return;
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['pdf', 'docx', 'md'].includes(ext)) {
    alert('不支持的文件类型，仅支持 PDF / DOCX / Markdown');
    return;
  }
  uploadArea.style.display = 'none';
  uploadProgress.style.display = 'block';
  progressFill.style.width = '2%';
  progressFill.classList.add('indeterminate');
  progressText.textContent = '上传文件中...';

  const formData = new FormData();
  formData.append('file', file);
  const xhr = new XMLHttpRequest();
  xhr.addEventListener('load', () => {
    if (xhr.status === 200) {
      const data = JSON.parse(xhr.responseText);
      if (data.task_id) pollProgress(data.task_id);
      else if (data.status === 'error') showUploadError(data.error || '处理失败');
      else showUploadError('未知响应格式');
    } else {
      let errMsg = '上传失败';
      try { errMsg = JSON.parse(xhr.responseText).detail || errMsg; } catch(e) {}
      showUploadError(errMsg);
    }
  });
  xhr.addEventListener('error', () => showUploadError('网络错误，请重试'));
  xhr.open('POST', '/api/documents/upload');
  xhr.send(formData);
}

function pollProgress(taskId) {
  progressFill.classList.remove('indeterminate');
  let lastDone = false, polls = 0;
  const MAX_POLLS = 2400;
  function tick() {
    polls++;
    if (polls > MAX_POLLS) { showUploadError('处理超时，请检查文档是否过大或重试'); return; }
    fetch('/api/documents/upload/' + taskId + '/status')
      .then(r => { if (!r.ok) throw new Error('status ' + r.status); return r.json(); })
      .then(data => {
        progressFill.style.width = Math.round(data.pct * 100) + '%';
        progressText.textContent = data.step;
        if (data.status === 'ready') {
          progressText.textContent = '完成！共 ' + data.result.chunk_count + ' 个文本块';
          progressFill.style.width = '100%';
          setTimeout(() => { uploadProgress.style.display = 'none'; uploadArea.style.display = 'block'; progressFill.style.width = '0%'; loadDocuments(); loadStats(); }, 1500);
          lastDone = true;
        } else if (data.status === 'error') {
          showUploadError((data.result && data.result.error) || data.step || '未知错误');
          lastDone = true;
        } else {
          setTimeout(tick, 500);
        }
      })
      .catch(() => { if (!lastDone) setTimeout(tick, 800); });
  }
  tick();
}

function showUploadError(msg) {
  progressFill.classList.remove('indeterminate');
  progressText.textContent = '错误: ' + msg;
  progressFill.style.width = '100%';
  progressFill.style.background = 'var(--accent-red)';
  const old = document.querySelector('.retry-btn');
  if (old) old.remove();
  const retryBtn = document.createElement('button');
  retryBtn.textContent = '重新上传';
  retryBtn.className = 'retry-btn';
  retryBtn.style.cssText = 'margin-top:8px;padding:4px 12px;background:var(--bg-card);color:var(--text-primary);border:1px solid var(--border-color);border-radius:4px;cursor:pointer;font-size:0.8rem;';
  retryBtn.onclick = () => { uploadProgress.style.display = 'none'; uploadArea.style.display = 'block'; progressFill.style.background = ''; progressFill.style.width = '0%'; const b = document.querySelector('.retry-btn'); if (b) b.remove(); };
  uploadProgress.appendChild(retryBtn);
}

/* === Documents List === */
async function loadDocuments() {
  try {
    const res = await fetch('/api/documents');
    const docs = await res.json();
    const container = document.getElementById('docList');
    if (docs.length === 0) { container.innerHTML = '<div class="doc-empty">暂无文档，请上传</div>'; return; }
    container.innerHTML = docs.map(d => `
      <div class="doc-item">
        <span class="status-dot ${d.status === 'ready' ? 'green' : d.status === 'error' ? 'red' : 'amber'}"></span>
        <span class="doc-name" title="${d.filename}" onclick="previewDocument(${d.id})" style="cursor:pointer;">${d.filename}</span>
        <span class="doc-meta">${d.chunk_count}块</span>
        <button class="doc-delete" onclick="event.stopPropagation(); deleteDocument(${d.id})" title="删除">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
        </button>
      </div>`).join('');
  } catch (e) { console.error('Failed to load documents:', e); }
}

async function previewDocument(id) {
  const previewDiv = document.getElementById('docPreview');
  previewDiv.innerHTML = '<div class="doc-empty">加载中...</div>';
  try {
    const res = await fetch('/api/documents/' + id + '/preview');
    if (!res.ok) throw new Error('status ' + res.status);
    const data = await res.json();
    previewDiv.innerHTML = `
      <div style="margin-bottom:6px;font-size:0.72rem;color:var(--text-muted);">
        📄 ${data.md_file} · 🖼 ${data.image_count} 张图片
      </div>
      <div class="preview-content">${escapeHtml(data.preview)}</div>`;
  } catch (e) {
    previewDiv.innerHTML = `<div class="doc-empty" style="color:var(--accent-red);">加载失败: ${e.message}</div>`;
  }
}

async function deleteDocument(id) {
  if (!confirm('确定删除此文档？所有相关的文本块和向量将被移除。')) return;
  try { await fetch('/api/documents/' + id, { method: 'DELETE' }); loadDocuments(); loadStats(); } catch (e) { console.error('Delete failed:', e); }
}

/* === Stats === */
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const stats = await res.json();
    document.getElementById('statDocs').textContent = stats.doc_count;
    document.getElementById('statChunks').textContent = stats.chunk_count;
    document.getElementById('statVectors').textContent = stats.vector_count;
    const sd = document.getElementById('status-faiss');
    if (sd) sd.className = 'status-dot ' + (stats.vector_count > 0 ? 'green' : 'amber');
  } catch (e) { console.error('Failed to load stats:', e); }
}

/* === Evaluation === */
function setupEval() {
  const countSlider = document.getElementById('evalCount');
  const countLabel = document.getElementById('evalCountLabel');
  if (countSlider) countSlider.addEventListener('input', () => { countLabel.textContent = countSlider.value; });
  const runBtn = document.getElementById('runEvalBtn');
  if (!runBtn) return;
  runBtn.addEventListener('click', async function() {
    const btn = this; btn.disabled = true; btn.textContent = '⏳ 评估中...';
    const resultsDiv = document.getElementById('evalResults'); resultsDiv.innerHTML = '';
    try {
      const res = await fetch('/api/evaluate', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          num_cases: parseInt(document.getElementById('evalCount').value),
          faithfulness: document.getElementById('evalFaithfulness').checked,
          mode: document.getElementById('evalMode').value,
        }),
      });
      const data = await res.json();
      if (data.summary && data.summary.error) { resultsDiv.innerHTML = `<div style="color:var(--accent-red);font-size:0.8rem;">${data.summary.error}</div>`; return; }
      const s = data.summary;
      resultsDiv.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:8px;">
          <div class="stat-card" style="padding:8px;"><div class="stat-value" style="font-size:1.2rem;">${(s.avg_precision*100).toFixed(0)}%</div><div class="stat-label">精准度</div></div>
          <div class="stat-card" style="padding:8px;"><div class="stat-value" style="font-size:1.2rem;">${(s.avg_recall*100).toFixed(0)}%</div><div class="stat-label">召回率</div></div>
          <div class="stat-card" style="padding:8px;"><div class="stat-value" style="font-size:1.2rem;">${(s.avg_faithfulness*100).toFixed(0)}%</div><div class="stat-label">忠实度</div></div>
          <div class="stat-card" style="padding:8px;"><div class="stat-value" style="font-size:1.2rem;">${(s.avg_relevance*100).toFixed(0)}%</div><div class="stat-label">答案相关性</div></div>
        </div>`;
      data.case_results.forEach((c, i) => {
        const dd = document.createElement('div');
        dd.style.cssText = 'margin-top:6px;font-size:0.75rem;';
        dd.innerHTML = `<details><summary style="color:var(--accent-purple);cursor:pointer;">案例${i+1}: ${c.question.substring(0,40)}...</summary>
          <div style="padding:4px 8px;color:var(--text-secondary);">
            精准: ${c.precision.hit_count}/${c.precision.total} (${(c.precision.precision*100).toFixed(0)}%) | 召回: ${c.recall.matched}/${c.recall.total_keywords} (${(c.recall.recall*100).toFixed(0)}%)<br>
            忠实度: ${(c.faithfulness.score*100).toFixed(0)}% — ${c.faithfulness.verdict.substring(0,100)}<br>
            相关性: ${(c.answer_relevance.relevance_score*100).toFixed(0)}%</div></details>`;
        resultsDiv.appendChild(dd);
      });
    } catch (e) { resultsDiv.innerHTML = `<div style="color:var(--accent-red);font-size:0.8rem;">评估失败: ${e.message}</div>`; }
    finally { btn.disabled = false; btn.textContent = '🚀 运行评估'; }
  });
}
