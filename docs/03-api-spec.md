# 接口规范（Agent 工具定义与 REST 接口）

## 一、Agent 工具

4 个工具定义在 `src/agent/tools.py`，用 `@tool` 装饰器声明。**函数 docstring 即为 LLM 看到的工具说明**，修改 docstring 会直接影响 Agent 的工具选择行为。

Agent 的推荐调用顺序：

```
check_history  →  search_knowledge_base  →  query_database / manage_documents
  （优先）           （缓存未命中时）              （按需）
```

---

### Tool 1: check_history

**用途**: 查询历史对话缓存。若当前问题与历史提问高度相似，直接返回缓存答案，避免重复检索与推理。

**输入参数**:
```python
{
    "question": str  # 用户的自然语言问题
}
```

**内部执行流程**:
1. `repository.search_similar_question(question, top_n=3)`
   - 阶段一：按空格切词（长度 ≥2），用 `content LIKE %kw%` 的 OR 条件做 SQL 粗筛
   - 阶段二：对候选逐条计算与当前问题的 Embedding 余弦相似度，保留 `> 0.85` 的
2. 命中最相似条目后，`get_answer_for_question()` 按 `session_id` 取该提问之后的首条 assistant 消息

**返回格式（命中）**:
```
✅ 命中历史缓存 | 相似度: 0.92
原问题: CH32V103 的最大主频是多少？

缓存答案:
（历史回答正文）

(来源记录时间: 2026-06-15 10:58:30)
```

**返回格式（未命中）**: `未命中历史缓存，需要正常检索。`

> ⚠️ 粗筛依赖空格分词，对不含空格的中文长句，分词结果往往是整句一个词，`LIKE` 匹配会退化。

---

### Tool 2: search_knowledge_base

**用途**: 在本地知识库中检索与用户问题相关的文本块。

**输入参数**:
```python
{
    "query": str  # 用户的自然语言查询
}
```

**内部执行流程**:
1. `load_index()` 载入 FAISS 索引；索引为空则直接返回提示
2. `embed_text(query)` 将 query 向量化（1024 维）
3. `search(index, query_vec)` 执行余弦相似度检索，Top-K = `settings.TOP_K`
4. `get_chunks_by_faiss_ids()` 按 FAISS ID 从 MySQL `chunks` 表回查完整文本，
   用 `ORDER BY field(faiss_id, ...)` **保持 FAISS 的相关度排序**
5. 逐块组装为带来源头的文本，段间以 `\n\n---\n\n` 分隔

**返回格式**:
```
[来源: CH32V103DS0.pdf | 块12] (相关度: 0.83)
文本块内容...

---

[来源: CH32V103DS0.pdf | 块3] (相关度: 0.71)
文本块内容...
```

> ⚠️ **这是 Agent 层与本工具之间的隐式契约**：`agent.py` 用正则
> `\[来源:\s*(.+?)\s*\|\s*块(\d+)\]\s*\(相关度:\s*([\d.]+)\)`
> 解析该格式来提取 `sources`。修改返回格式必须同步修改该正则。

**异常返回**（同样以纯文本返回，由 LLM 自行处理）:
- `知识库为空，请先上传文档。`
- `未找到与查询相关的知识库内容。`
- `检索到匹配项但无法获取文本内容。`

---

### Tool 3: query_database

**用途**: 执行 SQL 查询，获取结构化数据（文档列表、对话记录等）。

**输入参数**:
```python
{
    "sql": str  # 仅允许 SELECT 语句
}
```

**安全约束**:
- `sql.strip().upper()` 必须以 `SELECT` 开头，否则返回 `仅允许执行 SELECT 查询。`
- 结果超过 20 行时截断，并在末尾追加 `... (结果已截断，仅显示前20行)`

**返回格式**: `json.dumps(rows, ensure_ascii=False, indent=2)`；无结果时返回 `查询结果为空。`；异常时返回 `查询失败: <原因>`

---

### Tool 4: manage_documents

**用途**: 管理知识库中的文档（查看列表、删除文档）。

**输入参数**:
```python
{
    "action": str  # "list" 列出所有文档 | "delete:<doc_id>" 删除指定文档
}
```

**返回格式**:
- `list`：
  ```
  ID: 3 | 产品使用说明书.docx | 类型: docx | 状态: ready | 分块: 128 | 上传: 2026-06-15 10:56:12
  ```
- `delete:<id>`：`已删除文档: 产品使用说明书.docx (ID=3)`
- 文档不存在：`文档 ID=3 不存在。`
- 其他输入：`不支持的操作。支持: 'list' 或 'delete:<doc_id>'`

---

## 二、Agent System Prompt

实际使用的系统提示词（位于 `src/agent/agent.py` 的 `_SYSTEM_PROMPT`）：

```
你是一个知识库问答助手。你可以使用工具检索本地知识库来回答用户问题。

## 工具说明
- check_history(question): 优先调用，查询历史对话缓存。如果命中相似问题则直接返回缓存答案
- search_knowledge_base(query): 检索知识库中的文档内容（check_history 未命中时使用）
- query_database(sql): 执行 SELECT 查询
- manage_documents(action): 管理文档，"list" 或 "delete:<id>"

## 规则
1. 收到问题后先调用 search_knowledge_base 检索，再根据结果回答
2. 一轮检索后如果信息足够就直接回答，不要反复检索
3. 如果知识库没有相关信息，直接告知用户
4. 如果检索结果包含 [IMAGE:xxx]: 标签说明有对应图片，在回答中简要说明"相关图片已附在下方"
5. 使用中文回答，简洁准确
6. 引用来源会自动展示在下方，回答正文中不要列出引用来源
```

**调用参数**: `temperature=0.3`，`recursion_limit = settings.AGENT_MAX_ITERATIONS`（默认 25）

> 设计说明：规则 6 是刻意为之 —— 引用来源由前端独立渲染为卡片（含相关度与原文片段），
> 若让模型在正文里重复列一遍，会造成信息冗余且格式不可控。

---

## 三、Agent 返回结构

`invoke_agent()` 返回的字典是前后端之间的核心数据契约：

```python
{
    "response": str,        # 最终回答正文（不含引用来源清单）
    "thinking": [           # 思考链，供前端折叠展示
        {"type": "thought",     "content": str},              # AI 带 tool_calls 时的文本（截前 200 字）
        {"type": "action",      "tool": str, "args": dict},   # 工具调用
        {"type": "observation", "tool": str, "content": str}, # 工具返回（截前 150 字）
    ],
    "sources": [            # 引用来源
        {
            "filename": str,    # 文档名
            "chunk_index": int, # 块序号
            "score": float,     # 相关度
            "content": str,     # 原文片段（截前 300 字，可能含 [IMAGE:] 标签）
        },
    ],
}
```

---

## 四、REST 接口（HTML 版后端）

由 `src/api/server.py` 提供。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 落地页 |
| GET | `/app` | 问答运行页 |
| GET | `/knowledge` | 知识库管理页 |
| POST | `/api/chat` | 对话。请求体 `{message, session_id, history}`；返回 `{status, response, thinking, sources}`，并把来源中的 `[IMAGE:]` 标签追加到回答正文 |
| POST | `/api/documents/upload` | 上传文档。校验扩展名 → 去重 → 落盘 → **后台线程**执行入库，立即返回 `{task_id, status}` |
| GET | `/api/documents/upload/{task_id}/status` | 轮询上传进度，返回 `{step, pct, status, result}` |
| GET | `/api/documents` | 文档列表 |
| GET | `/api/documents/{doc_id}/preview` | 文档预览。优先读 MinerU 输出的 `.md`（前 3000 字），回退到数据库 chunks 拼接 |
| DELETE | `/api/documents/{doc_id}` | 删除文档（四路同步清理） |
| GET | `/api/stats` | 返回 `{doc_count, chunk_count, vector_count}` |
| POST | `/api/chat/clear` | 重置 Agent 实例 |
| GET | `/api/chat/history` | 会话历史，参数 `session_id`、`limit` |
| POST | `/api/evaluate` | 运行评估。请求体 `{num_cases, faithfulness, mode}`，`mode` 为 `auto` 或 `manual` |

**静态资源挂载**：`/static` → `src/ui/static`，`/images` → `data/images`

> 上传采用「后台线程 + 轮询」而非同步请求：MinerU 解析大 PDF 可能耗时 20 分钟以上，
> 同步 HTTP 会超时。进度写入模块级 `_upload_tasks` 字典，由 `threading.Lock` 保护。
> 前端轮询上限 `MAX_POLLS = 2400` 次（`src/ui/static/js/knowledge.js`）。
