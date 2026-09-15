"""FastAPI 服务器 — 连接 HTML 前端与现有 RAG 后端。"""

import os
import sys
import uuid
import shutil
import threading
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from config.settings import settings

# ---------- App ----------
app = FastAPI(title="RAG 智能问答系统", docs_url=None, redoc_url=None)

# ---------- 静态文件 ----------
_static_dir = os.path.join(_PROJECT_ROOT, "src", "ui", "static")
_templates_dir = os.path.join(_PROJECT_ROOT, "src", "ui", "templates")
_images_dir = os.path.join(_PROJECT_ROOT, settings.IMAGE_DIR)
_uploads_dir = os.path.join(_PROJECT_ROOT, settings.UPLOAD_DIR)

os.makedirs(_images_dir, exist_ok=True)
os.makedirs(_uploads_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=_static_dir), name="static")
app.mount("/images", StaticFiles(directory=_images_dir), name="images")
_jinja_env = Environment(loader=FileSystemLoader(_templates_dir))

# ---------- 上传任务进度追踪 ----------
_upload_tasks: dict[str, dict] = {}
_upload_lock = threading.Lock()


# ---------- 页面路由 ----------
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    template = _jinja_env.get_template("index.html")
    return HTMLResponse(template.render())


@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    template = _jinja_env.get_template("app.html")
    return HTMLResponse(template.render())


@app.get("/knowledge", response_class=HTMLResponse)
async def knowledge_page(request: Request):
    template = _jinja_env.get_template("knowledge.html")
    return HTMLResponse(template.render())


# ---------- Pydantic 模型 ----------
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    history: list[dict] = []


# ---------- API 路由 ----------
@app.post("/api/chat")
async def chat(req: ChatRequest):
    from src.agent.agent import invoke_agent

    result = invoke_agent(req.message, req.history)

    response_text = result.get("response", "")
    for src in result.get("sources", []):
        content = src.get("content", "")
        import re
        img_match = re.search(r'\[IMAGE:\s*(.+?)\]:\s*(.*)', content)
        if img_match and img_match.group(1) not in response_text:
            response_text += f"\n\n[IMAGE: {img_match.group(1)}]: {img_match.group(2)}"
    result["response"] = response_text

    # 自动保存对话记录
    try:
        from src.database.repository import add_chat_record
        from src.database.models import ChatRecord
        add_chat_record(ChatRecord(session_id=req.session_id, role="user", content=req.message))
        add_chat_record(ChatRecord(
            session_id=req.session_id, role="assistant",
            content=response_text,
            sources=[{"filename": s.get("filename",""), "chunk_index": s.get("chunk_index",0),
                       "score": s.get("score",0), "content": s.get("content","")[:200]}
                      for s in result.get("sources", [])],
        ))
    except Exception:
        pass

    return {"status": "ok", **result}


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "未选择文件")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("pdf", "docx", "md"):
        raise HTTPException(400, f"不支持的文件类型: .{ext}")

    # 防重复：快速检查
    from src.database.repository import list_documents
    existing = list_documents()
    if any(d.filename == file.filename and d.status == "ready" for d in existing):
        raise HTTPException(400, f"文档 {file.filename} 已入库，请勿重复上传")

    file_path = os.path.join(_uploads_dir, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    task_id = uuid.uuid4().hex[:12]
    with _upload_lock:
        _upload_tasks[task_id] = {"step": "准备处理", "pct": 0, "status": "processing"}

    def _on_progress(step_name: str, pct: float):
        with _upload_lock:
            _upload_tasks[task_id] = {
                "step": step_name,
                "pct": round(pct, 3),
                "status": "processing",
            }

    def _run():
        from src.knowledge_base.pipeline import ingest_document
        try:
            result = ingest_document(file_path, ext, file.filename, on_progress=_on_progress)
            print(f"[UPLOAD] task={task_id} status={result.get('status')} chunks={result.get('chunk_count',0)}", flush=True)
            with _upload_lock:
                _upload_tasks[task_id] = {
                    "step": "完成",
                    "pct": 1.0,
                    "status": result.get("status", "ready"),
                    "result": {
                        "doc_id": result.get("doc_id", 0),
                        "chunk_count": result.get("chunk_count", 0),
                        "error": result.get("error", ""),
                    },
                }
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[UPLOAD ERROR] task={task_id}: {e}", flush=True)
            with _upload_lock:
                _upload_tasks[task_id] = {
                    "step": str(e),
                    "pct": 0,
                    "status": "error",
                    "result": {"doc_id": 0, "chunk_count": 0, "error": str(e)},
                }

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"task_id": task_id, "status": "processing"}


@app.get("/api/documents/upload/{task_id}/status")
async def upload_status(task_id: str):
    with _upload_lock:
        if task_id not in _upload_tasks:
            raise HTTPException(404, "任务不存在")
        return _upload_tasks[task_id]


@app.get("/api/documents")
async def get_documents():
    from src.database.repository import list_documents

    docs = list_documents()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "chunk_count": d.chunk_count,
            "status": d.status,
            "created_at": str(d.created_at) if d.created_at else "",
        }
        for d in docs
    ]


@app.get("/api/documents/{doc_id}/preview")
async def preview_document(doc_id: int):
    """获取文档处理后的内容预览（PDF 从 MinerU 输出读取，其他从数据库读取）。"""
    import glob as glob_mod

    # 1. 尝试 MinerU 输出（仅 PDF 有）
    mineru_dir = os.path.join(_PROJECT_ROOT, "data", "mineru_output", f"doc_{doc_id}")
    if os.path.isdir(mineru_dir):
        md_files = glob_mod.glob(os.path.join(mineru_dir, "**", "*.md"), recursive=True)
        if md_files:
            with open(md_files[0], "r", encoding="utf-8") as f:
                text = f.read(3000)
            img_count = 0
            img_dir = os.path.join(os.path.dirname(md_files[0]), "images")
            if os.path.isdir(img_dir):
                img_count = len([f for f in os.listdir(img_dir) if os.path.isfile(os.path.join(img_dir, f))])
            return {"doc_id": doc_id, "preview": text, "image_count": img_count, "md_file": os.path.basename(md_files[0])}

    # 2. 回退：从数据库读取文本块拼接预览
    from src.database.repository import get_chunks_by_document
    chunks = get_chunks_by_document(doc_id)
    if not chunks:
        raise HTTPException(404, "未找到该文档的内容")

    preview = "\n\n".join(c.content for c in chunks[:10])
    return {"doc_id": doc_id, "preview": preview[:3000], "image_count": 0, "md_file": ""}


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: int):
    from src.knowledge_base.pipeline import remove_document

    result = remove_document(doc_id)
    return result


@app.get("/api/stats")
async def get_stats():
    from src.database.repository import list_documents
    from src.knowledge_base.vector_store import load_index, count_indexed

    docs = list_documents()
    ready_docs = [d for d in docs if d.status == "ready"]
    index = load_index()
    vector_count = count_indexed(index) if index is not None else 0
    return {
        "doc_count": len(ready_docs),
        "chunk_count": sum(d.chunk_count for d in ready_docs),
        "vector_count": vector_count,
    }


@app.post("/api/chat/clear")
async def clear_chat():
    from src.agent.agent import reset_agent

    reset_agent()
    return {"status": "ok"}


# ---------- 对话历史 API ----------
@app.get("/api/chat/history")
async def chat_history(session_id: str = "default", limit: int = 20):
    from src.database.repository import get_chat_history
    records = get_chat_history(session_id, limit)
    return [{"role": r.role, "content": r.content[:80], "created_at": str(r.created_at)} for r in records]


# ---------- 评估 API ----------
class EvalRequest(BaseModel):
    num_cases: int = 5
    faithfulness: bool = True
    mode: str = "auto"  # "auto" | "manual"


@app.post("/api/evaluate")
async def evaluate(req: EvalRequest):
    if req.mode == "auto":
        from src.evaluation.metrics import evaluate_rag_auto
        results = evaluate_rag_auto(req.num_cases, eval_faithfulness=req.faithfulness)
    else:
        from src.evaluation.run_eval import TEST_CASES
        from src.evaluation.metrics import evaluate_rag
        cases = TEST_CASES[:req.num_cases]
        results = evaluate_rag(cases, k=5, eval_faithfulness=req.faithfulness)

    # 确保结果可序列化
    for c in results.get("case_results", []):
        for key in ["precision", "recall", "faithfulness", "answer_relevance"]:
            if key in c and hasattr(c[key], 'get'):
                c[key] = dict(c[key])
    return results


# ---------- 启动 ----------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.server:app", host="0.0.0.0", port=8000, reload=True)
