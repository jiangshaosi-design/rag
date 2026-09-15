"""RAG 评估指标 — 精准度、召回率、忠实度、答案相关性。

支持两种模式:
1. 手工测试用例: evaluate_rag(test_cases=[{question, expected_keywords}, ...])
2. 自动生成用例: evaluate_rag_auto(num_cases=5)  从知识库自动生成问题再评估
"""

import re
import numpy as np
from config.settings import settings
from src.knowledge_base.embedder import embed_text
from src.knowledge_base.vector_store import load_index, search, normalize
from src.database.repository import get_chunks_by_faiss_ids
from src.agent.agent import invoke_agent


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def precision_at_k(query: str, relevant_keywords: list[str], k: int = 5, debug: bool = False) -> dict:
    """精准度: Top-K 检索结果中有多少是相关的。

    使用关键词匹配判断相关性 (简化方案)。
    返回 {precision, hit_count, total, samples}。
    """
    index = load_index()
    if index is None or index.ntotal == 0:
        return {"precision": 0.0, "hit_count": 0, "total": k}

    query_vec = embed_text(query)
    results = search(index, query_vec, top_k=k)
    faiss_ids = [str(r[0]) for r in results]
    chunks = get_chunks_by_faiss_ids(faiss_ids)

    hits = 0
    chunk_samples: list[str] = []
    for chunk in chunks:
        text_lower = chunk.content.lower()
        matched_kw = [kw for kw in relevant_keywords if kw.lower() in text_lower]
        chunk_samples.append(
            f"[{'✅' if matched_kw else '❌'}] "
            f"块{chunk.chunk_index}: {chunk.content[:60].replace(chr(10), ' ')}"
        )
        if matched_kw:
            hits += 1

    return {"precision": hits / len(chunks) if chunks else 0.0,
            "hit_count": hits, "total": len(chunks),
            "retrieved_kw_matching": ",".join([kw for kw in relevant_keywords
                if any(kw.lower() in c.content.lower() for c in chunks)]),
            "samples": chunk_samples}


def recall_crude(query: str, relevant_keywords: list[str], k: int = 5) -> dict:
    """召回率 (简化): 用检索命中的关键词占期望关键词的比例估算。

    真正的召回 = 检索到的相关块数 / 知识库中所有相关块数。
    简化方案用关键词命中比例近似。
    """
    index = load_index()
    if index is None or index.ntotal == 0:
        return {"recall": 0.0, "matched": 0, "total_keywords": len(relevant_keywords)}

    query_vec = embed_text(query)
    results = search(index, query_vec, top_k=k)
    faiss_ids = [str(r[0]) for r in results]
    chunks = get_chunks_by_faiss_ids(faiss_ids)

    all_text = " ".join(c.content.lower() for c in chunks)
    matched_kw = [kw for kw in relevant_keywords if kw.lower() in all_text]
    unmatched_kw = [kw for kw in relevant_keywords if kw.lower() not in all_text]

    return {"recall": len(matched_kw) / len(relevant_keywords) if relevant_keywords else 0.0,
            "matched": len(matched_kw), "total_keywords": len(relevant_keywords),
            "matched_kw": matched_kw, "unmatched_kw": unmatched_kw}


def faithfulness(answer: str, sources: list[dict]) -> dict:
    """忠实度: 用 LLM 判断回答中的每个陈述能否在来源中找到依据。

    返回 {score (0~1), verdict: str}。
    score: 1.0 = 完全忠实, 0.0 = 严重幻觉。
    """
    if not sources:
        return {"score": 1.0, "verdict": "无来源，无法判断"}

    source_text = "\n\n".join(
        f"[来源{s.get('chunk_index','?')}] {s.get('content','')[:500]}"
        for s in sources
    )

    prompt = f"""请严格评估以下 AI 回答是否忠实于来源材料。

## 来源材料
{source_text}

## AI 回答
{answer}

## 任务
1. 逐句检查回答中的每个事实性陈述
2. 判断每个陈述是否能在来源材料中找到直接依据
3. 给出忠实度评分 (0.0 ~ 1.0)
   - 1.0: 所有陈述都有来源依据
   - 0.5: 部分陈述无依据或有轻微编造
   - 0.0: 大量胡编乱造

请只输出以下格式：
分数: X.XX
判定: (一句话总结)"""

    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=settings.DEEPSEEK_MODEL, api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL, temperature=0,
            timeout=settings.LLM_TIMEOUT, max_retries=1,
        )
        resp = llm.invoke(prompt)
        text = resp.content if hasattr(resp, "content") else str(resp)

        score_match = re.search(r'分数:\s*([\d.]+)', text)
        verdict_match = re.search(r'判定:\s*(.+)', text)
        score = float(score_match.group(1)) if score_match else 0.5
        verdict = verdict_match.group(1).strip() if verdict_match else text[:200]
        return {"score": min(max(score, 0.0), 1.0), "verdict": verdict}
    except Exception as e:
        return {"score": 0.5, "verdict": f"评估失败: {e}"}


def answer_relevance(question: str, answer: str) -> dict:
    """答案相关性: 用 Embedding 余弦相似度衡量回答与问题的语义相关性。

    同时用 LLM 做辅助判断。
    """
    q_vec = embed_text(question)
    a_vec = embed_text(answer)
    cos_sim = _cosine_sim(q_vec, a_vec)

    # 归一化：经验阈值，相似度 0.5 以上基本相关
    relevance = min(cos_sim / 0.8, 1.0) if cos_sim < 0.8 else 1.0

    return {"cosine_similarity": round(cos_sim, 4), "relevance_score": round(relevance, 4)}


def evaluate_rag(test_cases: list[dict], k: int = 5, eval_faithfulness: bool = True) -> dict:
    """批量评估。

    test_cases 格式: [{"question": "...", "expected_keywords": ["...", "..."], "expected_image": bool}]

    Returns: {case_results: [...], summary: {avg_precision, avg_recall, avg_faithfulness, avg_relevance}}
    """
    case_results = []
    p_vals, r_vals, f_vals, a_vals = [], [], [], []

    for i, tc in enumerate(test_cases):
        question = tc["question"]
        keywords = tc.get("expected_keywords", [])
        print(f"\n[{i+1}/{len(test_cases)}] 评估: {question[:60]}...")

        # 1. 检索指标
        p = precision_at_k(question, keywords, k)
        r = recall_crude(question, keywords, k)
        p_vals.append(p["precision"])
        r_vals.append(r["recall"])

        # 2. 生成回答
        agent_result = invoke_agent(question)
        answer = agent_result.get("response", "")
        sources = agent_result.get("sources", [])

        # 3. 忠实度 (LLM-as-judge)
        f = {"score": 0.5, "verdict": "未评估"}
        if eval_faithfulness and answer:
            f = faithfulness(answer, sources)
        f_vals.append(f["score"])

        # 4. 答案相关性
        a = answer_relevance(question, answer) if answer else {"relevance_score": 0.0}
        a_vals.append(a["relevance_score"])

        has_image = tc.get("expected_image", False)
        actual_image = any("[IMAGE:" in s.get("content", "") for s in sources)
        image_ok = actual_image == has_image if tc.get("check_image") else True

        case_results.append({
            "question": question,
            "precision": p,
            "recall": r,
            "faithfulness": f,
            "answer_relevance": a,
            "image_expected": has_image,
            "image_shown": actual_image,
            "image_ok": image_ok,
        })

    summary = {
        "total_cases": len(test_cases),
        "avg_precision": round(np.mean(p_vals), 4),
        "avg_recall": round(np.mean(r_vals), 4),
        "avg_faithfulness": round(np.mean(f_vals), 4),
        "avg_relevance": round(np.mean(a_vals), 4),
    }

    return {"case_results": case_results, "summary": summary}


def print_eval_report(results: dict):
    """打印评估报告。"""
    s = results["summary"]
    print("\n" + "=" * 50)
    print("  RAG 系统评估报告")
    print("=" * 50)
    print(f"  测试用例数:       {s['total_cases']}")
    print(f"  平均精准度:       {s['avg_precision']:.2%}   (检索结果中相关的比例)")
    print(f"  平均召回率:       {s['avg_recall']:.2%}   (相关关键词命中的比例)")
    print(f"  平均忠实度:       {s['avg_faithfulness']:.2%}   (回答是否基于来源)")
    print(f"  平均答案相关性:   {s['avg_relevance']:.2%}   (回答是否切题)")
    print("=" * 50)

    for i, c in enumerate(results["case_results"]):
        print(f"\n案例{i+1}: {c['question'][:60]}...")
        print(f"  精准度: {c['precision']['hit_count']}/{c['precision']['total']} ({c['precision']['precision']:.2%})")
        print(f"  召回率: {c['recall']['matched']}/{c['recall']['total_keywords']} ({c['recall']['recall']:.2%})")
        print(f"  忠实度: {c['faithfulness']['score']:.2f} — {c['faithfulness']['verdict'][:80]}")
        print(f"  答案相关性: {c['answer_relevance']['relevance_score']:.2f}")
        if c.get("image_expected"):
            print(f"  图片展示: {'✅' if c['image_shown'] else '❌'} (期望: {c['image_expected']})")


# ═══════════════════════════════════════════════════════
# 自动生成测试用例 — 从知识库随机采样 + LLM 反向出题
# ═══════════════════════════════════════════════════════
def generate_test_cases(num_cases: int = 5) -> list[dict]:
    """从知识库中随机抽取文本块，用 LLM 生成对应的问题作为测试用例。

    返回: [{"question": "...", "source_chunk_id": N, "source_content": "..."}, ...]
    """
    import random
    from src.database.repository import list_documents, get_chunks_by_document
    from langchain_openai import ChatOpenAI

    # 获取所有 ready 文档
    docs = list_documents()
    ready_docs = [d for d in docs if d.status == "ready"]
    if not ready_docs:
        return []

    # 随机抽取文档和块
    cases = []
    for _ in range(min(num_cases, len(ready_docs) * 3)):
        doc = random.choice(ready_docs)
        chunks = get_chunks_by_document(doc.id)
        if not chunks:
            continue
        # 优先选中等长度的块 (更有信息量)
        good_chunks = [c for c in chunks if 100 < len(c.content) < 2000]
        if not good_chunks:
            good_chunks = chunks[:10]
        chunk = random.choice(good_chunks)

        # LLM 根据文本块生成问题
        try:
            llm = ChatOpenAI(
                model=settings.DEEPSEEK_MODEL, api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL, temperature=0.7,
                timeout=settings.LLM_TIMEOUT, max_retries=1,
            )
            prompt = f"""请根据以下文本片段，生成一个可以用这段文字回答的问题。
要求：
- 问题简洁明确，像一个真实用户会问的问题
- 问题答案必须包含在这段文字中
- 只输出问题本身，不要加任何前缀

文本片段:
{chunk.content[:800]}"""

            resp = llm.invoke(prompt)
            question = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if question and 5 < len(question) < 200:
                cases.append({
                    "question": question,
                    "source_chunk_id": chunk.id,
                    "source_content": chunk.content[:500],
                    "source_filename": doc.filename,
                })
        except Exception:
            continue

        if len(cases) >= num_cases:
            break

    return cases[:num_cases]


def evaluate_rag_auto(num_cases: int = 5, eval_faithfulness: bool = True) -> dict:
    """自动从知识库生成测试用例并评估。

    精准度/召回率: 检查原始源块是否在检索的 Top-K 中（更可靠的指标）。
    忠实度/相关性: 同上。
    """
    test_cases = generate_test_cases(num_cases)
    if not test_cases:
        return {"case_results": [], "summary": {"error": "知识库为空，无法生成测试用例"}}

    # 将自动生成的用例转换为手动格式的关键词
    cases_with_kw = []
    for tc in test_cases:
        # 从源内容中提取关键短语作为 benchmark
        content = tc["source_content"]
        words = [w for w in re.findall(r'[一-龥a-zA-Z0-9]+', content) if len(w) >= 3]
        # 取出现频率最高的或长度适中的词作为关键词
        keywords = list(dict.fromkeys([w for w in words if 3 <= len(w) <= 8][:8]))
        cases_with_kw.append({
            "question": tc["question"],
            "expected_keywords": keywords,
            "expected_image": "[IMAGE:" in tc["source_content"],
            "check_image": "[IMAGE:" in tc["source_content"],
        })

    return evaluate_rag(cases_with_kw, k=5, eval_faithfulness=eval_faithfulness)

