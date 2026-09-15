"""FAISS 向量库操作 — 索引创建、保存、加载、检索。"""

import os
import sys
import numpy as np
import faiss
from config.settings import settings


_EMBEDDING_DIM = 1024
_INDEX_FILE = "faiss.index"


def _is_ascii_path(path: str) -> bool:
    try:
        path.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _ensure_ascii_path(path: str) -> str:
    """确保路径不含非 ASCII 字符，FAISS C++ 无法处理中文路径。

    策略：将索引文件复制到系统临时目录（纯 ASCII 路径），读写都在临时目录进行。
    保存时同步回原路径。
    """
    if _is_ascii_path(path):
        return path

    import tempfile, shutil
    cache_dir = os.path.join(tempfile.gettempdir(), "rag_faiss_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cached = os.path.join(cache_dir, _INDEX_FILE)
    if os.path.exists(path) and not os.path.exists(cached):
        shutil.copy2(path, cached)
    return cached


# 当前是否使用了临时缓存目录
_using_cache_dir = False


def _index_path() -> str:
    global _using_cache_dir
    os.makedirs(settings.FAISS_INDEX_PATH, exist_ok=True)
    raw = os.path.join(settings.FAISS_INDEX_PATH, _INDEX_FILE)
    result = _ensure_ascii_path(raw)
    _using_cache_dir = (result != raw)
    return result


def _sync_cache_to_source() -> None:
    """如果使用了临时缓存，将索引同步回原始路径。"""
    if not _using_cache_dir:
        return
    import shutil
    raw = os.path.join(settings.FAISS_INDEX_PATH, _INDEX_FILE)
    cached = _index_path()
    if os.path.exists(cached):
        shutil.copy2(cached, raw)


def create_index() -> faiss.Index:
    """创建空索引。"""
    base = faiss.IndexFlatIP(_EMBEDDING_DIM)  # 内积相似度
    return faiss.IndexIDMap(base)


def normalize(vecs: np.ndarray) -> np.ndarray:
    """L2 归一化，配合 IndexFlatIP 等价于余弦相似度。"""
    faiss.normalize_L2(vecs)
    return vecs


def add_to_index(index: faiss.Index, vectors: np.ndarray, ids: list[int]) -> None:
    """将归一化向量和整数 ID 加入索引。"""
    if len(vectors) == 0:
        return
    index.add_with_ids(vectors, np.array(ids, dtype=np.int64))


def save_index(index: faiss.Index) -> None:
    path = _index_path()
    faiss.write_index(index, path)
    _sync_cache_to_source()


def load_index() -> faiss.Index | None:
    path = _index_path()
    if not os.path.exists(path):
        return None
    try:
        return faiss.read_index(path)
    except Exception:
        # 索引文件损坏，删除并重建
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def search(
    index: faiss.Index,
    query_vector: np.ndarray,
    top_k: int | None = None,
) -> list[tuple[int, float]]:
    """检索 Top-K，返回 [(faiss_int_id, score), ...]。"""
    k = top_k or settings.TOP_K
    if index.ntotal == 0:
        return []
    query = query_vector.reshape(1, -1).astype(np.float32)
    normalize(query)
    scores, ids = index.search(query, min(k, index.ntotal))
    results = []
    for score, faiss_id in zip(scores[0], ids[0]):
        if faiss_id >= 0:
            results.append((int(faiss_id), float(score)))
    return results


def count_indexed(index: faiss.Index) -> int:
    return index.ntotal


def remove_from_index(index: faiss.Index, ids: list[int]) -> None:
    """从索引中删除指定 ID 的向量。"""
    if not ids:
        return
    id_array = np.array(ids, dtype=np.int64)
    index.remove_ids(id_array)
