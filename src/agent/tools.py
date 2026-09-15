"""Agent 工具定义 — 知识库检索、数据库查询、文档管理。"""

from langchain_core.tools import tool

from src.knowledge_base.embedder import embed_text
from src.knowledge_base.vector_store import load_index, search, normalize
from src.database.repository import (
    get_chunks_by_faiss_ids,
    list_documents,
    get_document,
    delete_document,
    get_chunks_by_document,
    add_chat_record,
    get_chat_history,
    search_similar_question,
    get_answer_for_question,
)
from src.database.models import ChatRecord
import json


@tool
def search_knowledge_base(query: str) -> str:
    """在本地知识库中检索与用户问题相关的文档内容。传入自然语言查询，返回最相关的文本块及来源信息。"""
    index = load_index()
    if index is None or index.ntotal == 0:
        return "知识库为空，请先上传文档。"

    query_vec = embed_text(query)
    results = search(index, query_vec)

    if not results:
        return "未找到与查询相关的知识库内容。"

    faiss_ids = [str(r[0]) for r in results]
    chunks = get_chunks_by_faiss_ids(faiss_ids)

    if not chunks:
        return "检索到匹配项但无法获取文本内容。"

    lines = []
    for i, chunk in enumerate(chunks):
        doc = get_document(chunk.document_id)
        doc_name = doc.filename if doc else "未知文档"
        score = results[i][1] if i < len(results) else 0
        lines.append(
            f"[来源: {doc_name} | 块{chunk.chunk_index}] (相关度: {score:.2f})\n{chunk.content}"
        )

    return "\n\n---\n\n".join(lines)


@tool
def query_database(sql: str) -> str:
    """执行 SQL 查询获取结构化信息。只能使用 SELECT 语句。可用于查看上传的文档列表、对话历史等。"""
    import mysql.connector
    from src.database.connection import get_connection

    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return "仅允许执行 SELECT 查询。"

    try:
        conn = get_connection()
        with conn.cursor(dictionary=True) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        conn.close()

        if not rows:
            return "查询结果为空。"

        # 限制返回行数
        if len(rows) > 20:
            rows = rows[:20]
            truncated = True
        else:
            truncated = False

        result = json.dumps(rows, ensure_ascii=False, indent=2, default=str)
        if truncated:
            result += "\n... (结果已截断，仅显示前20行)"
        return result
    except Exception as e:
        return f"查询失败: {str(e)}"


@tool
def manage_documents(action: str) -> str:
    """管理知识库文档。action 可选值: 'list' 列出所有文档, 'delete:<doc_id>' 删除指定文档。"""
    action = action.strip()

    if action == "list":
        docs = list_documents()
        if not docs:
            return "知识库中暂无文档。"
        lines = [f"ID: {d.id} | {d.filename} | 类型: {d.file_type} | 状态: {d.status} | 分块: {d.chunk_count} | 上传: {d.created_at}" for d in docs]
        return "\n".join(lines)

    if action.startswith("delete:"):
        try:
            doc_id = int(action.split(":")[1].strip())
        except (IndexError, ValueError):
            return "用法: delete:<文档ID>，例如 delete:3"

        doc = get_document(doc_id)
        if not doc:
            return f"文档 ID={doc_id} 不存在。"

        filename = doc.filename
        delete_document(doc_id)
        return f"已删除文档: {filename} (ID={doc_id})"

    return "不支持的操作。支持: 'list' 或 'delete:<doc_id>'"


@tool
def check_history(question: str) -> str:
    """查询历史对话缓存。如果当前问题与之前的问题高度相似，直接返回缓存答案，避免重复检索和推理。
    调用时机：收到用户问题后优先调用此工具，如果返回命中就用缓存答案，否则再调用 search_knowledge_base。
    """
    similar = search_similar_question(question, top_n=3)
    if not similar:
        return "未命中历史缓存，需要正常检索。"

    # 取最相似的命中
    best = similar[0]
    cached = get_answer_for_question(best["question"])
    if not cached or not cached.get("answer"):
        return "未找到完整缓存记录，需要正常检索。"

    return (
        f"✅ 命中历史缓存 | 相似度: {best['similarity']:.2f}\n"
        f"原问题: {best['question']}\n\n"
        f"缓存答案:\n{cached['answer']}\n\n"
        f"(来源记录时间: {cached.get('created_at', '未知')})"
    )
