"""文本向量化 — 阿里云 DashScope text-embedding-v4。"""

import numpy as np
from dashscope import TextEmbedding
from config.settings import settings

_BATCH_LIMIT = 10


def _safe_call(model: str, input_text, api_key: str):
    try:
        resp = TextEmbedding.call(model=model, input=input_text, api_key=api_key)
    except Exception as e:
        raise RuntimeError(f"Embedding API 请求异常（网络/超时/限流）: {e}")
    if resp.status_code != 200:
        raise RuntimeError(f"Embedding API 错误: {resp.code} - {resp.message}")
    try:
        return [item["embedding"] for item in resp.output["embeddings"]]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Embedding 响应格式异常: {e}")


def embed_text(text: str) -> np.ndarray:
    """对单条文本生成 Embedding。"""
    vecs = _safe_call(settings.EMBEDDING_MODEL, text, settings.DASHSCOPE_API_KEY)
    return np.array(vecs[0], dtype=np.float32)


def embed_batch(texts: list[str]) -> np.ndarray:
    """批量生成 Embedding，自动按 API 限制（10条/批）分批。"""
    if not texts:
        return np.empty((0, 1024), dtype=np.float32)

    all_vectors: list[np.ndarray] = []
    for i in range(0, len(texts), _BATCH_LIMIT):
        batch = texts[i : i + _BATCH_LIMIT]
        vecs = _safe_call(settings.EMBEDDING_MODEL, batch, settings.DASHSCOPE_API_KEY)
        for v in vecs:
            all_vectors.append(np.array(v, dtype=np.float32))

    return np.vstack(all_vectors)


def get_embedding_dim() -> int:
    return 1024
