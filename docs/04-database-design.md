# 数据库表设计

## ER 关系

```
documents (1) ──── (N) chunks
     │
     └── 文档元数据，关联分块
```

## 建表 SQL

```sql
CREATE DATABASE IF NOT EXISTS rag_kb DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE rag_kb;

-- 文档表
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

-- 文本块表
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

-- 对话记录表
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
```

## FAISS ID 映射规则

**FAISS 中的向量 ID = `chunks.id`（MySQL 自增主键）**，而不是 `{document_id}_{chunk_index}` 这类复合串。

### 为什么用主键

FAISS 的 `IndexIDMap.add_with_ids()` 要求 ID 为 `int64`，复合字符串无法直接使用；且自增主键天然唯一，无需额外的编码/解析逻辑。

### 写入顺序（`pipeline.py` 第 5–6 步）

```
1. add_chunks_batch(chunk_records)          # faiss_id 先留空，拿到自增 id
2. SELECT id FROM chunks WHERE document_id=%s ORDER BY chunk_index
3. UPDATE chunks SET faiss_id = str(id) WHERE id = %s
4. index.add_with_ids(vectors, chunk_ids)   # chunk_ids 与上一步的顺序一致
```

### 检索回查链路

```
FAISS.search()  →  [(faiss_id: int, score: float), ...]
                     │
                     ▼  str(faiss_id)
get_chunks_by_faiss_ids([...])
  SELECT * FROM chunks WHERE faiss_id IN (...)
  ORDER BY field(faiss_id, ...)   ← 保持 FAISS 的相关度排序
                     │
                     ▼
                  chunk.content + chunk.document_id → documents.filename
```

`chunks.faiss_id` 存的是**字符串形式**（`VARCHAR(100)`），查询时把 FAISS 返回的整数 `str()` 化即可匹配。

### 删除时的同步

`remove_document(doc_id)` 先取该文档全部 `chunks.id`，再调用 `index.remove_ids(np.array(ids, dtype=int64))` —— `IndexIDMap` 支持按 ID 删除，这是选用它而非裸 `IndexFlatIP` 的原因之一。
