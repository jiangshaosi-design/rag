"""文本分块策略 — 递归粗分 + 滑动窗口细分的混合模式。

第一层: RecursiveCharacterTextSplitter 粗分（保语义边界）
第二层: 对超长块用小步长滑动窗口细分（补召回）

关键约束:
- 滑动窗口只在递归块内部滑动，不跨段落/章节边界
- [TABLE_START]...[TABLE_END] 包裹的表格块不被切分
"""

import re
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config.settings import settings

_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " ", ""]
_PROTECTED_PATTERN = re.compile(r"\[TABLE_START\].*?\[TABLE_END\]", re.DOTALL)


def _protect_blocks(text: str) -> tuple[str, dict[str, str]]:
    """将受保护的表格块替换为占位符，返回 (处理后文本, {占位符: 原文})。"""
    placeholders: dict[str, str] = {}
    counter = [0]

    def _replace(m: re.Match) -> str:
        key = f"__TABLE_BLOCK_{counter[0]}__"
        placeholders[key] = m.group(0)
        counter[0] += 1
        return key

    return _PROTECTED_PATTERN.sub(_replace, text), placeholders


def _restore_blocks(chunks: list[str], placeholders: dict[str, str]) -> list[str]:
    """将占位符还原为原始表格块。"""
    result = []
    for chunk in chunks:
        for key, original in placeholders.items():
            chunk = chunk.replace(key, original)
        result.append(chunk)
    return result


def _create_recursive_splitter(
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.RECURSIVE_CHUNK_SIZE,
        chunk_overlap=chunk_overlap or settings.RECURSIVE_CHUNK_OVERLAP,
        separators=_SEPARATORS,
        length_function=len,
    )


def _apply_sliding_window(text: str, window_size: int, step: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + window_size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def split_text(
    text: str,
    recursive_chunk_size: int | None = None,
    recursive_chunk_overlap: int | None = None,
    sliding_window_size: int | None = None,
    sliding_step: int | None = None,
) -> list[str]:
    """混合分块入口。自动保护 [TABLE_START]...[TABLE_END] 表格块不被切割。"""
    window_size = sliding_window_size or settings.SLIDING_WINDOW_SIZE
    step = sliding_step or settings.SLIDING_STEP

    # 1. 保护表格块
    protected_text, placeholders = _protect_blocks(text)

    # 2. 递归分块
    recursive_splitter = _create_recursive_splitter(recursive_chunk_size, recursive_chunk_overlap)
    coarse_chunks = recursive_splitter.split_text(protected_text)

    # 3. 滑动窗口
    result: list[str] = []
    for coarse in coarse_chunks:
        if len(coarse) <= window_size:
            result.append(coarse)
        else:
            result.extend(_apply_sliding_window(coarse, window_size, step))

    # 4. 还原表格块
    return _restore_blocks(result, placeholders)
