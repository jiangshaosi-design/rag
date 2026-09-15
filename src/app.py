"""Streamlit 主界面 — RAG 智能助手。"""

import sys, os, time, re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from config.settings import settings
from src.database.connection import init_db
from src.database.repository import list_documents
from src.knowledge_base.pipeline import ingest_document, remove_document
from src.knowledge_base.vector_store import load_index, count_indexed
from src.agent.agent import invoke_agent, reset_agent

# ═══════════════════════════════════════════════════════
# 页面配置
# ═══════════════════════════════════════════════════════
st.set_page_config(
    page_title="RAG 智能助手",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════
# CSS — 深紫科技风 · 全覆盖
# ═══════════════════════════════════════════════════════
st.markdown("""<style>
/* ── 全局 ── */
/* 隐藏 Streamlit 默认顶部工具栏 */
header[data-testid="stHeader"] {
    display: none !important;
}
.stApp {
    background: linear-gradient(155deg, #070018 0%, #0c0024 30%, #0f002c 60%, #09001e 100%) !important;
}
/* 主内容面板 — 深色卡片浮于紫色背景之上 */
.stMain, section.main, div[data-testid="stAppViewContainer"] {
    background: #0f0c1e !important;
}
.block-container {
    background: #0f0c1e !important;
    border-left: 1px solid rgba(124,58,237,0.1) !important;
    border-right: 1px solid rgba(124,58,237,0.1) !important;
}
div[data-testid="stVerticalBlock"], .element-container {
    background: transparent !important;
}
p, span, label, div { color: #ddd8f0; }

/* placeholder 文字提亮 */
[data-testid="stChatInput"] textarea::placeholder,
.stChatInput textarea::placeholder { color: #9888c0 !important; opacity: 1 !important; }

/* 输入栏 — 底部全部容器统一色号 */
.stBottom,
[class*="stBottom"],
div[data-testid="stBottom"],
div[data-testid="stBottomBlockContainer"],
div[data-testid="stChatInput"],
div[data-testid="stChatInput"] > div {
    background: #0f0c1e !important;
}
.stBottom, [class*="stBottom"], div[data-testid="stBottom"] {
    border-top: none !important;
    outline: none !important;
}
div[data-testid="stBottomBlockContainer"] {
    padding: 0 !important;
    margin: 0 !important;
    outline: none !important;
}
div[data-testid="stChatInput"] {
    border: none !important;
    padding: 8px 0 0 0 !important;
    box-shadow: none !important;
}
div[data-testid="stChatInput"] textarea {
    background-color: #181428 !important;
    border: 1px solid rgba(124,58,237,0.25) !important;
    border-radius: 12px !important;
    color: #e0d8f0 !important;
    caret-color: #a855f7 !important;
}
div[data-testid="stChatInput"] textarea:focus {
    border-color: #a855f7 !important;
    box-shadow: 0 0 20px rgba(124,58,237,0.3) !important;
}

/* ── 侧边栏 ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b0020 0%, #130038 100%) !important;
    border-right: 1px solid rgba(124,58,237,0.15) !important;
}
section[data-testid="stSidebar"] * { color: #d0c8f0 !important; }
section[data-testid="stSidebar"] button { color: #fff !important; }
section[data-testid="stSidebar"] hr, section[data-testid="stSidebar"] .stDivider {
    border-color: rgba(124,58,237,0.2) !important;
}
section[data-testid="stSidebar"] .stCaption { color: #b0a8d0 !important; }
section[data-testid="stSidebar"] small { color: #b8b0d8 !important; }

/* ── 聊天气泡 — user ── */
div[data-testid="stChatMessage"][aria-label*="ser" i] > div:last-child,
div[data-testid="stChatMessage"][aria-label*="用户" i] > div:last-child {
    background: linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%) !important;
    border-radius: 16px 16px 4px 16px !important;
    padding: 10px 16px !important;
    color: #ede8ff !important;
    max-width: 68% !important;
    box-shadow: 0 0 20px rgba(109,40,217,0.35) !important;
    border: 1px solid rgba(168,85,247,0.25) !important;
}

/* ── 聊天气泡 — assistant ── */
div[data-testid="stChatMessage"][aria-label*="ssistant" i] > div:last-child,
div[data-testid="stChatMessage"][aria-label*="助手" i] > div:last-child {
    background: rgba(18,8,48,0.82) !important;
    border: 1px solid rgba(124,58,237,0.22) !important;
    border-radius: 16px 16px 16px 4px !important;
    padding: 10px 16px !important;
    color: #e0d8f5 !important;
    max-width: 82% !important;
}
div[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
}
div[data-testid="stChatMessage"] p, div[data-testid="stChatMessage"] span { color: inherit !important; }

/* ── 来源展开 ── */
[data-testid="stExpander"] {
    background: rgba(124,58,237,0.05) !important;
    border: 1px solid rgba(124,58,237,0.16) !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] details summary {
    background: rgba(124,58,237,0.06) !important;
    color: #c0b0eb !important;
    border-radius: 10px !important;
    font-size: 0.82rem !important;
}
[data-testid="stExpander"] details > div {
    background: transparent !important;
    color: #d0c4f0 !important;
}

/* ── 通知 ── */
div[data-testid="stNotification"], .stAlert {
    background: rgba(16,8,44,0.9) !important;
    border-radius: 10px !important;
    color: #e8e0f5 !important;
}
div[kind="success"] { border-left: 3px solid #22c55e !important; }
div[kind="error"]   { border-left: 3px solid #ef4444 !important; }
div[kind="info"]    { border-left: 3px solid #7c3aed !important; }
div[kind="warning"] { border-left: 3px solid #f59e0b !important; }

/* ── 上传 ── */
[data-testid="stFileUploaderDropzone"] {
    background: rgba(124,58,237,0.04) !important;
    border: 1.5px dashed rgba(124,58,237,0.38) !important;
    border-radius: 12px !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: #a855f7 !important;
    background: rgba(124,58,237,0.1) !important;
    box-shadow: 0 0 24px rgba(124,58,237,0.18) !important;
}
[data-testid="stFileUploaderDropzone"] * { color: #c4b8e8 !important; }

/* ── 按钮 ── */
.stButton > button {
    background: linear-gradient(135deg, #5b21b6, #7c3aed) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    box-shadow: 0 0 22px rgba(124,58,237,0.5) !important;
    transform: translateY(-1px) !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(124,58,237,0.16) !important;
    border: 1px solid rgba(124,58,237,0.28) !important;
}

/* ── 指标卡 — 增强立体感 ── */
[data-testid="stMetric"] {
    background: rgba(124,58,237,0.14) !important;
    border: 1px solid rgba(124,58,237,0.3) !important;
    border-radius: 10px !important;
    padding: 8px 10px !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.03) !important;
}
[data-testid="stMetricLabel"]  { color: #b0a8d8 !important; font-size: 0.72rem !important; }
[data-testid="stMetricValue"] { color: #e8e0ff !important; font-size: 1.2rem !important; font-weight: 700 !important; }

/* ── 发送按钮 强化 ── */
button[data-testid="stChatInputSubmitButton"] {
    background: linear-gradient(135deg, #7c3aed, #a855f7) !important;
    border-radius: 8px !important;
    box-shadow: 0 0 14px rgba(124,58,237,0.45) !important;
    transition: all 0.2s !important;
}
button[data-testid="stChatInputSubmitButton"]:hover {
    box-shadow: 0 0 24px rgba(124,58,237,0.7) !important;
}
button[data-testid="stChatInputSubmitButton"] svg {
    width: 18px !important;
    height: 18px !important;
}

/* ── 滚动条 ── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: rgba(8,0,20,0.6); }
::-webkit-scrollbar-thumb { background: #5b21b6; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #7c3aed; }
</style>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════════════
init_db()

if "messages" not in st.session_state:
    st.session_state.messages = []


def _kb_stats():
    docs = list_documents()
    total_chunks = sum(d.chunk_count for d in docs)
    idx = load_index()
    vecs = count_indexed(idx) if idx else 0
    return len(docs), total_chunks, vecs


# ═══════════════════════════════════════════════════════
# 侧边栏
# ═══════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">
        <span style="font-size:1.3rem;">◈</span>
        <span style="font-size:1.1rem;font-weight:700;color:#a855f7;">知识库控制台</span>
    </div>
    <p style="color:#8880a8;font-size:0.72rem;margin-top:-4px;">DeepSeek V4 Pro · FAISS · MySQL</p>
    """, unsafe_allow_html=True)
    st.divider()

    # ── 系统状态 ──
    doc_n, chunk_n, vec_n = _kb_stats()
    st.markdown('<p style="color:#b8a8e0;font-weight:700;font-size:0.75rem;letter-spacing:0.05em;">📊 系统状态</p>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("文档", str(doc_n))
    c2.metric("文本块", str(chunk_n))
    c3.metric("向量", str(vec_n))

    # 连接指示灯
    faiss_color = "#22c55e" if vec_n > 0 else "#f59e0b"
    faiss_label = f"{vec_n}" if vec_n > 0 else "空"
    st.markdown(
        f'<div style="font-size:0.7rem;margin-top:4px;line-height:1.6;">'
        f'<span style="color:#22c55e;">●</span> 数据库 &nbsp;&nbsp;'
        f'<span style="color:{faiss_color};">●</span> 向量库({faiss_label}) &nbsp;&nbsp;'
        f'<span style="color:#22c55e;">●</span> 大模型'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    # ── 文档上传 ──
    st.markdown('<p style="color:#b8a8e0;font-weight:700;font-size:0.75rem;letter-spacing:0.05em;">📁 上传文档</p>', unsafe_allow_html=True)
    st.caption("支持 PDF / DOCX / Markdown，上传后自动解析入库")
    uploaded_file = st.file_uploader("选择文件", type=["pdf", "docx", "md"], label_visibility="collapsed")

    if uploaded_file is None:
        st.session_state.pop("_processed_file", None)
    else:
        if st.session_state.get("_processed_file") == uploaded_file.name:
            pass  # rerun 后跳过，防止重复处理
        elif any(d.filename == uploaded_file.name for d in list_documents()):
            st.warning(f"文档 {uploaded_file.name} 已存在")
        else:
            ext = uploaded_file.name.rsplit(".", 1)[-1].lower()
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            file_path = os.path.join(settings.UPLOAD_DIR, uploaded_file.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            progress_bar = st.progress(0)
            status_text = st.empty()

            def on_progress(name: str, pct: float):
                progress_bar.progress(pct)
                status_text.text(f"{name}")

            result = ingest_document(file_path, ext, uploaded_file.name, on_progress=on_progress)

            progress_bar.empty()
            status_text.empty()

            if result["status"] == "ready":
                st.session_state._processed_file = uploaded_file.name
                st.success(f"入库成功：{result['chunk_count']} 个文本块")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"处理失败：{result.get('error', '未知错误')}")

    st.divider()

    # ── 文档列表 ──
    st.markdown('<p style="color:#b8a8e0;font-weight:700;font-size:0.75rem;letter-spacing:0.05em;">📋 已入库文档</p>', unsafe_allow_html=True)

    docs = list_documents()
    if not docs:
        st.info("暂无文档，请上传")
    else:
        for doc in docs:
            color = "#22c55e" if doc.status == "ready" else ("#f59e0b" if doc.status == "processing" else "#ef4444")
            label = {"ready": "就绪", "processing": "处理中", "error": "失败"}.get(doc.status, doc.status)
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(
                    f'<div style="background:rgba(124,58,237,0.06);border:1px solid rgba(124,58,237,0.14);'
                    f'border-radius:6px;padding:5px 8px;margin:2px 0;font-size:0.78rem;">'
                    f'<span style="color:{color};">●</span> {doc.filename[:28]} '
                    f'<span style="color:#7868a0;font-size:0.68rem;">{doc.chunk_count}块 · {label}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button("", key=f"del_{doc.id}", icon=":material/delete:", help=f"删除 {doc.filename}"):
                    remove_document(doc.id)
                    st.rerun()

    st.divider()

    # ── 快捷操作 ──
    st.markdown('<p style="color:#b8a8e0;font-weight:700;font-size:0.75rem;letter-spacing:0.05em;">⚡ 快捷操作</p>', unsafe_allow_html=True)
    if st.button("🗑 清空对话记录", use_container_width=True):
        st.session_state.messages = []
        reset_agent()
        st.rerun()

    # ── 系统评估 ──
    with st.expander("📊 系统评估指标", expanded=False):
        eval_mode = st.radio("评估模式", ["📝 自动生成 (通用)", "📋 手工用例 (需预设)"],
                             horizontal=True)

        if "自动" in eval_mode:
            st.caption("从知识库随机采样文本块 → LLM 反向出题 → 检索验证")
            test_count = st.slider("测试用例数", 3, 10, 5, 1)
        else:
            st.caption("使用预设的专用测试用例")
            test_count = st.slider("测试用例数", 3, 10, 5, 1)

        include_faithfulness = st.checkbox("包含忠实度评估 (需调用 LLM)", True)

        if st.button("🚀 运行评估", use_container_width=True):
            with st.spinner("评估中..."):
                if "自动" in eval_mode:
                    from src.evaluation.metrics import evaluate_rag_auto
                    results = evaluate_rag_auto(test_count, eval_faithfulness=include_faithfulness)
                    if "error" in results.get("summary", {}):
                        st.error(results["summary"]["error"])
                        st.stop()
                else:
                    from src.evaluation.run_eval import TEST_CASES
                    from src.evaluation.metrics import evaluate_rag
                    cases = TEST_CASES[:test_count]
                    results = evaluate_rag(cases, k=5, eval_faithfulness=include_faithfulness)
                s = results["summary"]

                # 指标卡片
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🎯 精准度", f"{s['avg_precision']:.0%}")
                c2.metric("📡 召回率", f"{s['avg_recall']:.0%}")
                c3.metric("✅ 忠实度", f"{s['avg_faithfulness']:.0%}")
                c4.metric("🎯 答案相关性", f"{s['avg_relevance']:.0%}")

                st.divider()

                # 逐案例详情
                for i, c in enumerate(results["case_results"]):
                    with st.expander(f"案例{i+1}: {c['question'][:50]}...", expanded=False):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.metric("精准度",
                                      f"{c['precision']['hit_count']}/{c['precision']['total']} ({c['precision']['precision']:.0%})")
                            st.metric("召回率",
                                      f"{c['recall']['matched']}/{c['recall']['total_keywords']} ({c['recall']['recall']:.0%})")
                            if c['recall'].get('unmatched_kw'):
                                st.caption(f"未匹配: {', '.join(c['recall']['unmatched_kw'])}")
                        with c2:
                            st.metric("忠实度", f"{c['faithfulness']['score']:.0%}")
                            st.metric("答案相关性", f"{c['answer_relevance']['relevance_score']:.0%}")
                            st.caption(c['faithfulness']['verdict'][:120])
                        # 检索详情
                        if c['precision'].get('samples'):
                            st.caption("检索到的块:")
                            for s in c['precision']['samples']:
                                st.caption(s)

    st.markdown(
        f'<p style="color:#9080c0;font-size:0.64rem;text-align:center;margin-top:1rem;">'
        f'嵌入：text-embedding-v4 · 分块：{settings.RECURSIVE_CHUNK_SIZE}/{settings.SLIDING_WINDOW_SIZE}'
        f'</p>',
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════
# 主界面
# ═══════════════════════════════════════════════════════
st.markdown("""
<div style="margin-bottom:4px;">
    <span style="font-size:1.6rem;font-weight:800;background:linear-gradient(135deg,#a78bfa 0%,#7c3aed 50%,#6366f1 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">
        智能知识检索助手
    </span>
</div>
""", unsafe_allow_html=True)

# ── 状态条（提亮） ──
doc_n, chunk_n, vec_n = _kb_stats()
st.markdown(
    f'<div style="font-size:0.74rem;margin-bottom:14px;color:#c8c0e8;">'
    f'<span>{doc_n} 文档</span>'
    f'<span style="margin:0 8px;color:#7c3aed;">|</span>'
    f'<span>{chunk_n} 文本块</span>'
    f'<span style="margin:0 8px;color:#7c3aed;">|</span>'
    f'<span>{vec_n} 向量</span>'
    f'<span style="margin:0 8px;color:#7c3aed;">|</span>'
    f'<span>{settings.DEEPSEEK_MODEL}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── 空状态欢迎卡片 ──
if not st.session_state.messages:
    with st.container():
        st.markdown("""
        <div style="background:rgba(18,10,44,0.55);border:1px solid rgba(124,58,237,0.22);border-radius:16px;
                    padding:28px 24px 18px;text-align:center;margin-bottom:8px;">
            <p style="font-size:1.15rem;font-weight:700;color:#d8d0f5;margin-bottom:6px;">
                有什么我可以帮你的？
            </p>
            <p style="font-size:0.82rem;color:#b0a8d0;margin-bottom:16px;">
                我可以基于已上传的文档检索相关内容并回答你的问题
            </p>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button(" 知识库中有哪些文档？", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": "知识库中有哪些文档？"})
                st.session_state._trigger_example = True
                st.rerun()
        with c2:
            if st.button(" 帮我总结已上传文档的主要内容", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": "帮我总结一下已上传文档的主要内容"})
                st.session_state._trigger_example = True
                st.rerun()
        with c3:
            if st.button(" 根据文档回答关于系统架构的问题", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": "请根据已上传的文档，介绍一下其中涉及的系统架构"})
                st.session_state._trigger_example = True
                st.rerun()

        st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)

# 处理示例问题触发
if st.session_state.get("_trigger_example"):
    st.session_state._trigger_example = False
    last_msg = st.session_state.messages[-1]["content"]
    with st.spinner("智能体思考中…"):
        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
        result = invoke_agent(last_msg, history)
    # 自动保存对话记录
    try:
        from src.database.repository import add_chat_record
        from src.database.models import ChatRecord
        add_chat_record(ChatRecord(session_id="default", role="user", content=last_msg))
        add_chat_record(ChatRecord(
            session_id="default", role="assistant",
            content=result.get("response", ""),
            sources=[{"filename": s.get("filename",""), "chunk_index": s.get("chunk_index",0),
                       "score": s.get("score",0), "content": s.get("content","")[:200]}
                      for s in result.get("sources", [])],
        ))
    except Exception:
        pass

    st.session_state.messages.append({
        "role": "assistant",
        "content": result.get("response", "抱歉，处理请求时出错。"),
        "thinking": result.get("thinking", []),
        "sources": result.get("sources", []),
    })
    st.rerun()

# ── 对话区 ──
for msg in st.session_state.messages:
    role = msg["role"]
    thinking = msg.get("thinking", [])
    sources = msg.get("sources", [])

    with st.chat_message(role):
        if role == "assistant" and thinking:
            # 显示思考链
            with st.expander(f"🧠 思考过程 ({len(thinking)} 步)", expanded=False):
                for step in thinking:
                    t = step.get("type", "")
                    if t == "thought":
                        st.markdown(f'<div style="font-size:0.8rem;color:#a78bfa;margin:2px 0;">💭 思考：{step["content"]}</div>', unsafe_allow_html=True)
                    elif t == "action":
                        st.markdown(f'<div style="font-size:0.8rem;color:#f59e0b;margin:2px 0;">🔧 行动：调用 <b>{step["tool"]}</b> {step.get("args", {})}</div>', unsafe_allow_html=True)
                    elif t == "observation":
                        st.markdown(f'<div style="font-size:0.8rem;color:#22c55e;margin:2px 0;">📋 观察：{step.get("content", "")}</div>', unsafe_allow_html=True)
            st.markdown("---")

        # 渲染回答正文 + 内嵌图片
        response_text = msg["content"]
        if role == "assistant" and sources:
            # 从 sources 中提取图片，追加到回答正文末尾
            for src in sources:
                content = src.get("content", "")
                img_match = re.search(r'\[IMAGE:\s*(.+?)\]:\s*(.*)', content)
                if img_match and img_match.group(1) not in response_text:
                    response_text += f"\n\n[IMAGE: {img_match.group(1)}]: {img_match.group(2)}"

        # 分割内容，将 [IMAGE:...]: 标签替换为实际渲染
        parts = re.split(r'(\[IMAGE:\s*.+?\]:\s*[^\n]*)', response_text)
        for part in parts:
            img_match = re.match(r'\[IMAGE:\s*(.+?)\]:\s*(.*)', part)
            if img_match:
                fname = img_match.group(1)
                desc = img_match.group(2)
                img_full = os.path.join(settings.IMAGE_DIR, fname)
                col1, col2 = st.columns([0.45, 0.55])
                with col1:
                    if os.path.exists(img_full):
                        st.image(img_full, use_container_width=True)
                    else:
                        st.caption("📷 图片文件不存在")
                with col2:
                    st.caption(desc[:300])
            elif part.strip():
                st.markdown(part)

        # 来源卡片
        if role == "assistant" and sources:
            with st.expander(f"📎 引用来源 ({len(sources)})", expanded=True):
                for src in sources:
                    content = src.get("content", "")
                    img_match = re.search(r'\[IMAGE:\s*(.+?)\]:\s*(.*)', content)
                    if img_match:
                        fname = img_match.group(1)
                        desc = img_match.group(2)
                        img_full = os.path.join(settings.IMAGE_DIR, fname)
                        col1, col2 = st.columns([0.4, 0.6])
                        with col1:
                            if os.path.exists(img_full):
                                st.image(img_full, use_container_width=True)
                            else:
                                st.caption(f"📷 图片文件不存在")
                        with col2:
                            st.caption(f"📄 {src.get('filename','?')} · 第{src.get('chunk_index','?')}块 · 相关度 {src.get('score',0):.2f}")
                            st.caption(desc[:200])
                    else:
                        st.markdown(
                            f'<div style="background:rgba(124,58,237,0.06);border:1px solid rgba(124,58,237,0.16);'
                            f'border-radius:8px;padding:8px 10px;margin:4px 0;font-size:0.8rem;">'
                            f'<strong style="color:#a78bfa;">{src.get("filename","?")}</strong>'
                            f' <span style="color:#8b80b0;">· 第{src.get("chunk_index","?")}块</span>'
                            f' <span style="color:#f59e0b;">· 相关度 {src.get("score",0):.2f}</span>'
                            f'<p style="margin:4px 0 0;color:#b8b0d0;font-size:0.76rem;">{content[:250]}</p>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

# ── 输入 ──
if prompt := st.chat_input("💬 输入问题，智能体会自动检索知识库回答…"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner("智能体思考中…"):
        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
        result = invoke_agent(prompt, history)

    # 自动保存对话记录到数据库
    try:
        from src.database.repository import add_chat_record
        from src.database.models import ChatRecord
        add_chat_record(ChatRecord(session_id="default", role="user", content=prompt))
        add_chat_record(ChatRecord(
            session_id="default", role="assistant",
            content=result.get("response", ""),
            sources=[{"filename": s.get("filename",""), "chunk_index": s.get("chunk_index",0),
                       "score": s.get("score",0), "content": s.get("content","")[:200]}
                      for s in result.get("sources", [])],
        ))
    except Exception:
        pass

    st.session_state.messages.append({
        "role": "assistant",
        "content": result.get("response", "抱歉，处理请求时出错。"),
        "thinking": result.get("thinking", []),
        "sources": result.get("sources", []),
    })
    st.rerun()
