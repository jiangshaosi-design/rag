"""文档入库全流程编排 — 加载 → 分块 → 嵌入 → 存储。"""

import os
import shutil
from config.settings import settings
from src.database.connection import get_connection
from src.database.models import Document, Chunk
from src.database.repository import add_document, update_document_status, add_chunks_batch
from src.knowledge_base.loader import load_document
from src.knowledge_base.splitter import split_text
from src.knowledge_base.embedder import embed_batch, embed_text
from src.knowledge_base.vector_store import (
    create_index, load_index, save_index, add_to_index, normalize, remove_from_index, count_indexed
)
import numpy as np


def ingest_document(
    file_path: str,
    file_type: str,
    filename: str,
    on_progress=None,
) -> dict:
    """完整入库流程。

    on_progress(step_name: str, pct: float) — 可选进度回调，pct 为 0.0~1.0。
    """
    def _progress(name: str, pct: float):
        if on_progress:
            on_progress(name, pct)

    try:
        # 0. 防重复入库
        from src.database.repository import list_documents
        existing = list_documents()
        if any(d.filename == filename and d.status == "ready" for d in existing):
            return {"doc_id": 0, "chunk_count": 0, "status": "error", "error": f"文档 {filename} 已入库，请勿重复上传"}

        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        _progress("创建文档记录", 0.02)

        doc = Document(
            filename=filename, file_type=file_type, file_path=file_path,
            file_size=file_size, status="processing",
        )
        doc_id = add_document(doc)

        # 1. 加载文本（含表格、图片描述）
        _progress("解析文档文本", 0.05)
        text, image_paths = load_document(file_path, file_type, doc_id, on_progress=_progress)

        # 图片数保护
        if len(image_paths) > settings.MAX_IMAGES_PER_DOC:
            update_document_status(doc_id, "error", 0)
            return {"doc_id": doc_id, "chunk_count": 0, "status": "error",
                    "error": f"图片数({len(image_paths)})超过上限({settings.MAX_IMAGES_PER_DOC})，请减少图片后重试"}

        # 2. 分块
        _progress("文本分块", 0.10)
        chunks_text = split_text(text)

        # 块数保护
        if len(chunks_text) > settings.MAX_CHUNKS_PER_DOC:
            update_document_status(doc_id, "error", 0)
            return {"doc_id": doc_id, "chunk_count": 0, "status": "error",
                    "error": f"文本块数({len(chunks_text)})超过上限({settings.MAX_CHUNKS_PER_DOC})，请上传较小的文档"}

        if not chunks_text:
            update_document_status(doc_id, "error", 0)
            return {"doc_id": doc_id, "chunk_count": 0, "status": "error", "error": "文档解析后无有效文本内容"}

        # 4. 嵌入 — 最耗时，细化进度
        total = len(chunks_text)
        _progress(f"向量化（共 {total} 块）", 0.15)

        from src.knowledge_base.embedder import _BATCH_LIMIT
        import numpy as np
        from src.knowledge_base.embedder import _safe_call
        from config.settings import settings as s

        all_vectors: list[np.ndarray] = []
        for i in range(0, total, _BATCH_LIMIT):
            batch = chunks_text[i : i + _BATCH_LIMIT]
            vecs = _safe_call(s.EMBEDDING_MODEL, batch, s.DASHSCOPE_API_KEY)
            for v in vecs:
                all_vectors.append(np.array(v, dtype=np.float32))
            done = min(i + _BATCH_LIMIT, total)
            pct = 0.15 + 0.60 * (done / total)
            _progress(f"向量化 {done}/{total}", pct)
        vectors = np.vstack(all_vectors)

        # 5. MySQL
        _progress("写入数据库", 0.80)
        chunk_records = [
            Chunk(document_id=doc_id, chunk_index=i, content=t, faiss_id="", token_count=len(t))
            for i, t in enumerate(chunks_text)
        ]
        add_chunks_batch(chunk_records)
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM chunks WHERE document_id = %s ORDER BY chunk_index", (doc_id,))
                rows = cur.fetchall()
                chunk_ids = [r[0] for r in rows]
                for cid in chunk_ids:
                    cur.execute("UPDATE chunks SET faiss_id = %s WHERE id = %s", (str(cid), cid))
                conn.commit()
        finally:
            conn.close()

        # 6. FAISS
        _progress("写入向量索引", 0.90)
        index = load_index()
        if index is None:
            index = create_index()
        normalize(vectors)
        add_to_index(index, vectors, chunk_ids)
        save_index(index)

        # 7
        _progress("完成", 1.0)
        update_document_status(doc_id, "ready", len(chunks_text))
        return {"doc_id": doc_id, "chunk_count": len(chunks_text), "status": "ready"}

    except Exception as e:
        if 'doc_id' in locals():
            update_document_status(doc_id, "error", 0)
        return {"doc_id": locals().get("doc_id", 0), "chunk_count": 0, "status": "error", "error": str(e)}


def remove_document(doc_id: int) -> dict:
    """删除文档（MySQL + FAISS + 图片 + MinerU 输出 同步清理）。"""
    from src.database.repository import get_chunks_by_document, delete_document
    import glob

    try:
        chunks = get_chunks_by_document(doc_id)
        faiss_int_ids = [c.id for c in chunks]

        # 清理 MySQL
        delete_document(doc_id)

        # 清理 FAISS
        index = load_index()
        if index is not None and faiss_int_ids:
            remove_from_index(index, faiss_int_ids)
            save_index(index)

        # 清理图片文件
        for pat in (f"doc{doc_id}_*.png", f"doc{doc_id}_*.jpg", f"doc{doc_id}_*.jpeg", f"doc{doc_id}_*.gif"):
            for f in glob.glob(os.path.join(settings.IMAGE_DIR, pat)):
                try:
                    os.remove(f)
                except OSError:
                    pass

        # 清理 MinerU 输出
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        mineru_dir = os.path.join(project_root, "data", "mineru_output", f"doc_{doc_id}")
        if os.path.isdir(mineru_dir):
            shutil.rmtree(mineru_dir, ignore_errors=True)

        return {"status": "deleted", "doc_id": doc_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}
