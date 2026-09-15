"""统一配置管理，所有配置项从 .env 文件加载。"""

import os
from dotenv import load_dotenv

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_dotenv_path = os.path.join(_PROJECT_ROOT, ".env")
load_dotenv(_dotenv_path)


def _abs(path: str) -> str:
    """将相对路径转为相对于项目根目录的绝对路径。"""
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(_PROJECT_ROOT, path))


class Settings:
    # ===== DeepSeek LLM =====
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))
    AGENT_MAX_ITERATIONS: int = int(os.getenv("AGENT_MAX_ITERATIONS", "25"))

    # ===== 阿里云 Embedding + 视觉 =====
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
    VISION_MODEL: str = os.getenv("VISION_MODEL", "qwen-vl-plus")
    MINERU_BACKEND: str = os.getenv("MINERU_BACKEND", "pipeline")  # pipeline(快) / vllm(精)
    IMAGE_DIR: str = _abs(os.getenv("IMAGE_DIR", "data/images"))
    MAX_CHUNKS_PER_DOC: int = int(os.getenv("MAX_CHUNKS_PER_DOC", "500"))
    MAX_IMAGES_PER_DOC: int = int(os.getenv("MAX_IMAGES_PER_DOC", "20"))
    IMAGE_DESCRIBE: bool = os.getenv("IMAGE_DESCRIBE", "true").lower() in ("1", "true", "yes")

    # ===== MySQL =====
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "rag_kb")

    # ===== FAISS =====
    FAISS_INDEX_PATH: str = _abs(os.getenv("FAISS_INDEX_PATH", "data/faiss_index"))

    # ===== Chunking (递归 + 滑动混合) =====
    RECURSIVE_CHUNK_SIZE: int = int(os.getenv("RECURSIVE_CHUNK_SIZE", "1000"))
    RECURSIVE_CHUNK_OVERLAP: int = int(os.getenv("RECURSIVE_CHUNK_OVERLAP", "100"))
    SLIDING_WINDOW_SIZE: int = int(os.getenv("SLIDING_WINDOW_SIZE", "500"))
    SLIDING_STEP: int = int(os.getenv("SLIDING_STEP", "250"))

    # ===== App =====
    UPLOAD_DIR: str = _abs(os.getenv("UPLOAD_DIR", "data/uploads"))
    TOP_K: int = int(os.getenv("TOP_K", "5"))


settings = Settings()
