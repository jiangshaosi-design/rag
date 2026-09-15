# RAG 智能体知识库问答系统

基于 **LangChain ReAct Agent** 的检索增强生成（RAG）问答系统。上传 PDF / DOCX / Markdown 文档后，系统自动完成版面解析、分块、向量化与双存储；提问时智能体自主调用工具完成语义检索、数据库查询与文档管理，并给出**可追溯的来源引用**与**内嵌图片**。

PDF 解析采用 Docker 化 MinerU 做版面分析，能正确处理复杂表格、多栏排版与图表，解析出的图片经多模态模型生成中文描述后一并进入向量库 —— 因此系统不仅能"回答文字问题"，也能"回答图表问题"。

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **Agent 自主决策** | ReAct 模式，4 个工具自主编排：缓存查询 → 知识库检索 → 数据库查询 → 文档管理 |
| **混合分块策略** | 递归粗分（保语义边界）+ 滑动窗口细分（补召回），表格块整体保护不被切断 |
| **表格保护** | Markdown 表格自动包裹 `[TABLE_START]`/`[TABLE_END]` 占位符，分块后原样还原 |
| **图片语义化** | MinerU 提取图片 → Qwen-VL 生成中文描述 → 描述文本进入向量库，图片回显到回答中 |
| **对话缓存** | 历史问题 SQL 粗筛 + Embedding 精排（阈值 0.85），命中则零 API 消耗秒回 |
| **双存储映射** | FAISS 存向量（ID = MySQL 自增主键），MySQL 存全文；检索后按 ID 回查完整文本 |
| **来源可追溯** | 每条回答附带文件名、块序号、相关度分数与原文片段 |
| **四维评估** | 精准度 / 召回率 / 忠实度 / 答案相关性，支持手工用例与 LLM 自动出题两种模式 |
| **双前端** | Streamlit（推荐，开箱即用）与 FastAPI + 原生 HTML/CSS/JS（自定义 UI） |
| **中文路径兼容** | FAISS C++ 层不支持非 ASCII 路径，自动降级到临时 ASCII 目录读写并同步回源 |

---

## 系统架构

```
┌──────────────────────────────────────────────────────────┐
│  前端层                                                   │
│  Streamlit UI (src/app.py)  │  FastAPI + HTML (src/api/)  │
└───────────────────────┬──────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────┐
│  Agent 层  (src/agent/)                                   │
│  LangChain ReAct Agent ← DeepSeek V4 Pro                  │
│    ├─ check_history          对话缓存查询                  │
│    ├─ search_knowledge_base  知识库语义检索                │
│    ├─ query_database         SELECT 结构化查询             │
│    └─ manage_documents       文档列表 / 删除               │
└───────────────────────┬──────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────┐
│  知识库层  (src/knowledge_base/)                           │
│  loader ──► splitter ──► embedder ──► vector_store        │
│  (MinerU/DOCX/MD) (混合分块) (1024维)   (FAISS)           │
│  pipeline.py  全流程编排                                   │
└───────────────────────┬──────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────┐
│  数据层                                                   │
│  FAISS 向量索引  │  MySQL 元数据+全文  │  文件系统          │
│  data/faiss_index│  documents/chunks/  │  uploads/images/  │
│                  │  chat_history       │  mineru_output/   │
└──────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| LLM | DeepSeek V4 Pro（`langchain-openai` 兼容接口） | 推理与答案生成 |
| Agent 框架 | LangChain 1.x `create_agent`（ReAct） | 工具编排与多步推理 |
| Embedding | 阿里云 DashScope `text-embedding-v4`（1024 维） | 文本向量化 |
| 视觉模型 | 阿里云 Qwen-VL（`MultiModalConversation`） | 图片内容描述 |
| 向量库 | FAISS `IndexIDMap(IndexFlatIP)` | 余弦相似度检索（L2 归一化 + 内积） |
| 关系库 | MySQL 8.0（InnoDB / utf8mb4） | 元数据、全文、对话历史 |
| PDF 解析 | Docker MinerU（`mineru[core]`） | 版面分析 + 表格识别 + 图片分类 |
| DOCX 解析 | `python-docx` | 段落 + 表格提取 |
| 前端 | Streamlit / FastAPI + 原生 HTML/CSS/JS | 交互界面 |
| 运行环境 | Python 3.10+ | — |

---

## 快速开始

### 1. 前置条件

| 依赖 | 说明 |
|------|------|
| Python 3.10+ | 推荐 conda 环境 |
| MySQL 8.0 | 需可连接；首次运行自动建库建表 |
| Docker Desktop | **仅解析 PDF 时需要**。DOCX / Markdown 无需 Docker |
| MinerU 镜像 | `mineru:latest`，约 43 GB，构建见 `Dockerfile.mineru` |

构建 MinerU 镜像（国内网络建议设置模型源）：

```bash
# Windows CMD
set MINERU_MODEL_SOURCE=modelscope
# Linux / macOS
export MINERU_MODEL_SOURCE=modelscope

docker build -f Dockerfile.mineru -t mineru:latest .
```

> 若只使用 DOCX / Markdown 文档，可跳过 Docker 与镜像构建。

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填写下列三项：

```ini
DEEPSEEK_API_KEY=sk-xxxxxxxx      # https://platform.deepseek.com
DASHSCOPE_API_KEY=sk-xxxxxxxx     # https://dashscope.console.aliyun.com
MYSQL_PASSWORD=your-password
```

> `.env` 已在 `.gitignore` 中，不会被提交。请勿将真实密钥写入 `.env.example`。

### 4. 初始化数据库（可选）

首次启动时 `src/database/connection.py` 会自动建库建表，无需手动执行。如需手动：

```bash
mysql -u root -p < scripts/init_db.sql
```

### 5. 启动

**Streamlit 版（推荐）**

```bash
streamlit run src/app.py --server.port 8501
```

访问 <http://localhost:8501>

**HTML 版（FastAPI + 原生前端）**

```bash
python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

访问 <http://localhost:8000>（落地页） / <http://localhost:8000/app>（运行页）

---

## 使用方式

1. 侧边栏「上传文档」选择 PDF / DOCX / Markdown，观察分步进度条
2. 上传完成后在对话区提问，例如：
   - `知识库中有哪些文档？`
   - `帮我总结已上传文档的主要内容`
   - `根据文档回答关于系统架构的问题`
3. 展开「🧠 思考过程」查看 Agent 的 Thought / Action / Observation 链路
4. 展开「📎 引用来源」查看每个文本块的出处、相关度与原文片段
5. 侧边栏「📊 系统评估指标」可运行四维评估

---

## 项目结构

```
rag/
├── config/
│   └── settings.py              # 统一配置入口，所有配置从 .env 加载
├── src/
│   ├── app.py                   # Streamlit 主界面
│   ├── agent/                   # Agent 层
│   │   ├── agent.py             #   ReAct Agent 组装 + invoke_agent
│   │   └── tools.py             #   4 个工具定义
│   ├── api/
│   │   └── server.py            # FastAPI 服务与 REST 接口
│   ├── database/                # 数据访问层
│   │   ├── connection.py        #   连接池 + 自动建库建表
│   │   ├── models.py            #   Document / Chunk / ChatRecord
│   │   └── repository.py        #   CRUD
│   ├── knowledge_base/          # 知识库层
│   │   ├── loader.py            #   PDF(MinerU) / DOCX / Markdown 解析
│   │   ├── splitter.py          #   递归 + 滑动窗口混合分块
│   │   ├── embedder.py          #   阿里云向量化
│   │   ├── image_describer.py   #   Qwen-VL 图片描述
│   │   ├── vector_store.py      #   FAISS 索引读写与检索
│   │   └── pipeline.py          #   入库 / 删除全流程编排
│   ├── evaluation/              # 评估层
│   │   ├── metrics.py           #   四维指标 + LLM 自动出题
│   │   └── run_eval.py          #   手工测试用例与 CLI 入口
│   └── ui/                      # HTML 版前端资源
│       ├── templates/           #   Jinja2 模板
│       └── static/              #   CSS / JS
├── scripts/
│   └── init_db.sql              # 建库建表脚本
├── docs/                        # 设计文档
├── data/                        # 运行时数据（不提交）
├── Dockerfile.mineru            # MinerU 镜像构建
└── requirements.txt
```

各文件职责与调用关系的完整梳理见 [`docs/06-文件结构梳理.md`](docs/06-文件结构梳理.md)。

---

## 工作流程

### 文档入库

```
上传文件
  └─► 建 documents 记录（status=processing）
      └─► 解析
          ├─ PDF  ─► Docker MinerU：版面分析 → 阅读顺序还原 → 表格转 Markdown → 图片提取
          ├─ DOCX ─► python-docx：段落 + 表格转 Markdown
          └─ MD   ─► 直接读取
      └─► 图片复制到 data/images/ ─► Qwen-VL 并行描述（3 线程）
      └─► Markdown 引用替换为 [IMAGE: 文件名]: 描述
      └─► 表格包裹 [TABLE_START]...[TABLE_END]
      └─► 混合分块：递归粗分(1000/100) → 超长块滑动窗口细分(500/250)
      └─► 向量化（10 条/批）→ L2 归一化
      └─► MySQL 写入 chunks（faiss_id = 主键）
      └─► FAISS add_with_ids → 落盘
      └─► 更新 status=ready
```

### 问答

```
用户提问
  └─► Agent 决策
      ├─ check_history         SQL LIKE 粗筛 + Embedding 精排(>0.85) → 命中直接返回
      ├─ search_knowledge_base 问题向量化 → FAISS Top-K → MySQL 回查全文
      ├─ query_database        仅允许 SELECT，最多返回 20 行
      └─ manage_documents      list / delete:<id>
  └─► LLM 基于工具返回生成回答
  └─► 从工具输出解析来源（文件名 / 块序号 / 相关度 / 原文片段）
  └─► 检测 [IMAGE:...] 标签 → 追加到回答并渲染图片
  └─► 写入 chat_history
```

完整调用链（含函数级定位）见 [`docs/07-系统流程梳理.md`](docs/07-系统流程梳理.md)。

---

## 评估指标

| 指标 | 实现方式 |
|------|---------|
| **精准度** Precision@K | Top-K 检索结果中命中期望关键词的块占比 |
| **召回率** Recall | 期望关键词被检索结果覆盖的比例 |
| **忠实度** Faithfulness | LLM-as-judge 逐句核查回答中的事实性陈述能否在来源中找到依据（0~1 分） |
| **答案相关性** Answer Relevance | 问题与回答的 Embedding 余弦相似度（经验阈值归一化） |

两种运行模式：

- **手工用例**：预设问题与期望关键词，`python -m src.evaluation.run_eval`
- **自动出题**：从知识库随机采样文本块 → LLM 反向生成问题 → 用生成的问题检索 → 检查原块是否被召回，避免人工设计用例的偏差

---

## 已知限制

- **PDF 解析依赖 Docker**，MinerU 镜像约 43 GB，首次构建耗时较长
- **Windows 中文路径**：FAISS 的 C++ 层无法处理非 ASCII 路径，索引实际读写发生在系统临时目录，保存时同步回源路径
- **无鉴权**：当前为单机 / 内网演示用途，未实现用户体系与 API 鉴权，请勿直接暴露公网
- **recall_crude 为近似指标**：真正的召回率需枚举知识库中全部相关块，此处用关键词命中比例估算
- **对话缓存基于字符串匹配**：`search_similar_question` 依赖空格分词，对无空格的中文长句粗筛效果有限

---

## License

[MIT](LICENSE)
