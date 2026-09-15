"""数据模型定义。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Document:
    id: int | None = None
    filename: str = ""
    file_type: str = ""
    file_path: str = ""
    file_size: int = 0
    chunk_count: int = 0
    status: str = "processing"
    created_at: datetime | None = None


@dataclass
class Chunk:
    id: int | None = None
    document_id: int = 0
    chunk_index: int = 0
    content: str = ""
    faiss_id: str = ""
    token_count: int = 0
    created_at: datetime | None = None


@dataclass
class ChatRecord:
    id: int | None = None
    session_id: str = ""
    role: str = ""
    content: str = ""
    sources: list[dict] | None = None
    created_at: datetime | None = None
