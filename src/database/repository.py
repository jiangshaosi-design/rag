"""数据访问层 — 对 documents / chunks / chat_history 表的 CRUD 操作。"""

from src.database.connection import get_connection
from src.database.models import Document, Chunk, ChatRecord


# ===== Documents =====

def add_document(doc: Document) -> int:
    """插入文档记录，返回自增 ID。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (filename, file_type, file_path, file_size, chunk_count, status) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (doc.filename, doc.file_type, doc.file_path, doc.file_size, doc.chunk_count, doc.status),
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def get_document(doc_id: int) -> Document | None:
    conn = get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT * FROM documents WHERE id = %s", (doc_id,))
            row = cur.fetchone()
            return Document(**row) if row else None
    finally:
        conn.close()


def list_documents(file_type: str | None = None) -> list[Document]:
    conn = get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            if file_type:
                cur.execute("SELECT * FROM documents WHERE file_type = %s ORDER BY created_at DESC", (file_type,))
            else:
                cur.execute("SELECT * FROM documents ORDER BY created_at DESC")
            return [Document(**row) for row in cur.fetchall()]
    finally:
        conn.close()


def update_document_status(doc_id: int, status: str, chunk_count: int = 0) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE documents SET status = %s, chunk_count = %s WHERE id = %s",
                (status, chunk_count, doc_id),
            )
            conn.commit()
    finally:
        conn.close()


def delete_document(doc_id: int) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            conn.commit()
    finally:
        conn.close()


# ===== Chunks =====

def add_chunks_batch(chunks: list[Chunk]) -> None:
    """批量插入文本块。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (document_id, chunk_index, content, faiss_id, token_count) "
                "VALUES (%s, %s, %s, %s, %s)",
                [(c.document_id, c.chunk_index, c.content, c.faiss_id, c.token_count) for c in chunks],
            )
            conn.commit()
    finally:
        conn.close()


def get_chunks_by_document(doc_id: int) -> list[Chunk]:
    conn = get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT * FROM chunks WHERE document_id = %s ORDER BY chunk_index", (doc_id,))
            return [Chunk(**row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_chunks_by_faiss_ids(faiss_ids: list[str]) -> list[Chunk]:
    """根据 FAISS ID 列表批量查询文本块。"""
    if not faiss_ids:
        return []
    conn = get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            placeholders = ",".join(["%s"] * len(faiss_ids))
            cur.execute(
                f"SELECT * FROM chunks WHERE faiss_id IN ({placeholders}) ORDER BY field(faiss_id, {placeholders})",
                faiss_ids * 2,
            )
            return [Chunk(**row) for row in cur.fetchall()]
    finally:
        conn.close()


def delete_chunks_by_document(doc_id: int) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
            conn.commit()
    finally:
        conn.close()


# ===== Chat History =====

def add_chat_record(record: ChatRecord) -> int:
    import json

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sources_json = json.dumps(record.sources, ensure_ascii=False) if record.sources else None
            cur.execute(
                "INSERT INTO chat_history (session_id, role, content, sources) VALUES (%s, %s, %s, %s)",
                (record.session_id, record.role, record.content, sources_json),
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def get_chat_history(session_id: str, limit: int = 20) -> list[ChatRecord]:
    import json

    conn = get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "SELECT * FROM chat_history WHERE session_id = %s ORDER BY created_at DESC LIMIT %s",
                (session_id, limit),
            )
            rows = cur.fetchall()
            records = []
            for row in rows:
                if row.get("sources") and isinstance(row["sources"], str):
                    row["sources"] = json.loads(row["sources"])
                records.append(ChatRecord(**row))
            return list(reversed(records))
    finally:
        conn.close()


def search_similar_question(query_text: str, top_n: int = 3) -> list[dict]:
    """在 chat_history 中搜索相似问题，返回匹配记录。
    先用 SQL LIKE 粗筛（含相同关键词），再用 embedding 余弦相似度精排。
    """
    from src.knowledge_base.embedder import embed_text
    import numpy as np

    # 提取问题中的关键词做 SQL 粗筛
    keywords = [w for w in query_text.replace("？", "").replace("?", "").split() if len(w) >= 2]
    if not keywords:
        return []

    conn = get_connection()
    try:
        # 用 LIKE 查找包含关键词的历史问题
        conditions = " OR ".join(["content LIKE %s"] * len(keywords))
        params = [f"%{kw}%" for kw in keywords[:5]]
        sql = f"""SELECT session_id, content, sources, created_at
                  FROM chat_history
                  WHERE role = 'user' AND ({conditions})
                  ORDER BY created_at DESC LIMIT %s"""
        params.append(top_n * 3)

        with conn.cursor(dictionary=True) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    # Embedding 精排
    query_vec = np.array(embed_text(query_text), dtype=np.float32)
    scored = []
    for row in rows:
        q_vec = np.array(embed_text(row["content"]), dtype=np.float32)
        sim = float(np.dot(query_vec, q_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(q_vec) + 1e-8))
        if sim > 0.85:  # 相似度阈值
            scored.append({"question": row["content"], "similarity": round(sim, 4),
                           "session_id": row["session_id"], "created_at": str(row["created_at"])})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_n]


def get_answer_for_question(question: str) -> dict | None:
    """查找某个问题的历史回答。"""
    conn = get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                "SELECT * FROM chat_history WHERE role = 'user' AND content = %s ORDER BY created_at DESC LIMIT 1",
                (question,)
            )
            user_row = cur.fetchone()
            if not user_row:
                return None

            cur.execute(
                "SELECT * FROM chat_history WHERE session_id = %s AND role = 'assistant' AND id > %s ORDER BY id ASC LIMIT 1",
                (user_row["session_id"], user_row["id"])
            )
            assist_row = cur.fetchone()
            if not assist_row:
                return None

            sources = assist_row.get("sources")
            if isinstance(sources, str):
                import json
                sources = json.loads(sources)

            return {"question": user_row["content"], "answer": assist_row["content"],
                    "sources": sources, "created_at": str(assist_row["created_at"])}
    finally:
        conn.close()
