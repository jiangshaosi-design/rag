"""MySQL 连接池管理，首次连接自动建库建表。"""

import mysql.connector
from mysql.connector import pooling
from config.settings import settings


_pool: pooling.MySQLConnectionPool | None = None
_initialized: bool = False

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(500) NOT NULL COMMENT '原始文件名',
    file_type VARCHAR(20) NOT NULL COMMENT '文件类型: pdf/docx/md',
    file_path VARCHAR(1000) NOT NULL COMMENT '存储路径',
    file_size BIGINT DEFAULT 0 COMMENT '文件大小(bytes)',
    chunk_count INT DEFAULT 0 COMMENT '分块数量',
    status VARCHAR(20) DEFAULT 'processing' COMMENT '状态: processing/ready/error',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    INDEX idx_status (status),
    INDEX idx_file_type (file_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chunks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL COMMENT '所属文档ID',
    chunk_index INT NOT NULL COMMENT '块序号',
    content TEXT NOT NULL COMMENT '文本块内容',
    faiss_id VARCHAR(100) NOT NULL COMMENT 'FAISS中对应的向量ID',
    token_count INT DEFAULT 0 COMMENT 'Token数量',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    INDEX idx_document_id (document_id),
    INDEX idx_faiss_id (faiss_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL COMMENT '会话标识',
    role VARCHAR(20) NOT NULL COMMENT '角色: user/assistant',
    content TEXT NOT NULL COMMENT '消息内容',
    sources JSON COMMENT '引用来源(chunk_id列表)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '时间',
    INDEX idx_session_id (session_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def _ensure_database() -> None:
    conn = mysql.connector.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.MYSQL_DATABASE}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


def _ensure_tables() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for statement in _CREATE_TABLES_SQL.split(";"):
                stmt = statement.strip()
                if stmt:
                    cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def _create_pool() -> pooling.MySQLConnectionPool:
    _ensure_database()
    return mysql.connector.pooling.MySQLConnectionPool(
        pool_name="rag_pool",
        pool_size=5,
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE,
        charset="utf8mb4",
    )


def init_db() -> None:
    """初始化数据库和表（幂等，可重复调用）。"""
    global _initialized
    if _initialized:
        return
    get_pool()  # 触发 _ensure_database
    _ensure_tables()
    _initialized = True


def get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = _create_pool()
    return _pool


def get_connection():
    return get_pool().get_connection()
