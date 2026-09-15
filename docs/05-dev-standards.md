# 开发规范

## 环境配置

1. 复制 `.env.example` 为 `.env`，填入真实的 API Key 和数据库密码
2. `.env` 文件已在 `.gitignore` 中，不会被提交
3. 所有配置项通过 `config/settings.py` 统一读取

## 代码风格

- 使用 Python 类型注解（Type Hints）
- 函数和类遵循 PEP 8 命名规范
- 不写冗余注释，代码即文档
- 异常处理仅用于可预见的业务异常，不捕获 BaseException

## 项目结构规范

```
src/
├── database/       # MySQL 相关：连接、模型、仓库
├── knowledge_base/ # 知识库：加载、分块、嵌入、向量存储
├── agent/          # Agent：工具定义、Agent 组装
├── evaluation/     # 评估：四维指标、测试用例
├── ui/             # HTML 版前端资源（Jinja2 模板 + CSS + JS）
├── api/            # FastAPI 服务（HTML 版后端）
└── app.py          # Streamlit 入口
```

每层有清晰的职责边界：
- `database/` 不依赖 `knowledge_base/` 和 `agent/`
- `knowledge_base/` 只依赖 `database/` 和 `config/`
- `agent/` 依赖 `knowledge_base/` 和 `database/`
- `evaluation/` 依赖 `agent/` 和 `knowledge_base/`
- `ui/` 是纯静态资源，无 Python 依赖
- `app.py` 与 `api/` 位于最上层，可依赖所有下层模块

> 唯一的跨层反向依赖：`database/repository.py` 的 `search_similar_question()` 在函数内
> 惰性 import 了 `knowledge_base/embedder.py` 的 `embed_text()`，用于历史提问的语义精排。

## 开发流程

1. 每阶段先阅读对应的 `docs/` 文档
2. 实现代码
3. 写简单验证脚本（非正式测试，确认流程可走通）
4. 记录本次改动内容与待办

## 文件命名

- Python 文件使用小写 + 下划线：`vector_store.py`
- 类名使用 PascalCase：`VectorStore`
- 函数/变量使用小写 + 下划线：`search_chunks()`

## 分块策略

混合分块：递归粗分 + 滑动窗口细分

| 参数 | 默认值 | 说明 |
|------|--------|------|
| RECURSIVE_CHUNK_SIZE | 1000 | 递归分块器粗分阈值 |
| RECURSIVE_CHUNK_OVERLAP | 100 | 粗分块间重叠 |
| SLIDING_WINDOW_SIZE | 500 | 滑动窗口大小 |
| SLIDING_STEP | 250 | 滑动步长(50%重叠) |

滑动窗口只在递归块内部滑动，不跨段落/章节边界。

## 依赖管理

- 所有依赖写在 `requirements.txt`
- 新增依赖需先确认无冲突
- 使用 `pip install -r requirements.txt` 一键安装
- **不保留未使用的依赖**：PDF 由 Docker MinerU 处理，因此不需要本地 PDF 库
