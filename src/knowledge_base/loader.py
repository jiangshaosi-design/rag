"""文档加载器 — 支持 PDF (MinerU Docker) / DOCX / Markdown，含表格提取和图片描述。"""

import os
import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from config.settings import settings


class BaseLoader(ABC):
    @abstractmethod
    def load(self, file_path: str, doc_id: int = 0, on_progress=None) -> tuple[str, list[str]]:
        ...


# ═══════════════════════════════════════════════════════
# PDF — Docker MinerU
# ═══════════════════════════════════════════════════════
class PDFLoader(BaseLoader):
    def load(self, file_path: str, doc_id: int = 0, on_progress=None) -> tuple[str, list[str]]:

        # 动态进度：MinerU 阶段占 pipeline 的 5%→15%
        _mineru_pct = [0.05]

        def _report(msg):
            if on_progress:
                on_progress(msg, _mineru_pct[0])

        if not os.path.exists(file_path):
            raise RuntimeError(f"文件不存在: {file_path}")

        docker = shutil.which("docker")
        if docker is None:
            raise RuntimeError("未找到 Docker，请确认 Docker Desktop 已启动并在 PATH 中")

        abs_path = os.path.abspath(file_path).replace("\\", "/")
        pdf_dir = os.path.dirname(abs_path)
        pdf_name = os.path.basename(file_path)
        file_stem = os.path.splitext(pdf_name)[0]

        # 项目根目录（用于持久化输出路径）
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        _report("MinerU 启动中...")

        backend = getattr(settings, "MINERU_BACKEND", "pipeline")
        with tempfile.TemporaryDirectory(prefix="mineru_") as tmpdir:
            tmp_abs = os.path.abspath(tmpdir).replace("\\", "/")

            cmd = [
                docker, "run", "--gpus", "all", "--rm",
                "-v", f"{pdf_dir}:/input",
                "-v", f"{tmp_abs}:/output",
                "mineru:latest",
                "mineru", "-p", f"/input/{pdf_name}", "-o", "/output",
                "-b", backend,
            ]

            env = os.environ.copy()
            env["MSYS_NO_PATHCONV"] = "1"

            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", errors="replace",
                                        env=env, bufsize=1)
            except FileNotFoundError:
                raise RuntimeError("未找到 Docker")

            # 逐行读取输出，解析进度
            output_lines: list[str] = []
            for line in proc.stdout:
                line = line.rstrip()
                output_lines.append(line)
                # 解析 MinerU 进度条，动态更新进度百分比
                m = re.search(r'(\S.*?):\s*(\d+)%.*?(\d+)/(\d+)', line)
                if m:
                    step_name = m.group(1).strip()
                    pct = int(m.group(2))
                    current = int(m.group(3))
                    total = int(m.group(4))
                    # 进度从 5%→15% 随 MinerU 各阶段推进
                    _mineru_pct[0] = 0.05 + 0.10 * (pct / 100.0)
                    _report(f"{step_name} {current}/{total}")

            proc.wait(timeout=600)

            if proc.returncode != 0:
                # 提取最后几行非进度条的错误信息
                err_lines = [l for l in output_lines[-20:] if "ERROR" in l or "Error" in l or "error" in l]
                if not err_lines:
                    err_lines = [l for l in output_lines[-5:]
                                if not any(c in l for c in ['%|', 'it/s', 'it]'])]
                tail = "\n".join(err_lines[-5:]) if err_lines else (
                    output_lines[-1] if output_lines else "无输出")
                raise RuntimeError(f"MinerU 解析失败: {tail}")

            # 找到输出目录
            result_dir = os.path.join(tmpdir, file_stem)
            if not os.path.isdir(result_dir):
                raise RuntimeError(f"MinerU 解析失败: 未生成输出目录，可能是 PDF 格式不兼容")

            subdirs = [d for d in os.listdir(result_dir) if os.path.isdir(os.path.join(result_dir, d))]
            if not subdirs:
                raise RuntimeError(f"MinerU 解析失败: 输出目录为空")
            parse_dir = os.path.join(result_dir, subdirs[0])

            # 持久化
            persist_dir = os.path.join(project_root, "data", "mineru_output", f"doc_{doc_id}")
            if os.path.exists(persist_dir):
                shutil.rmtree(persist_dir)
            shutil.copytree(result_dir, persist_dir)

            # 切换到持久目录
            subdirs = [d for d in os.listdir(persist_dir) if os.path.isdir(os.path.join(persist_dir, d))]
            parse_dir = os.path.join(persist_dir, subdirs[0])

            # 读取 markdown
            md_path = os.path.join(parse_dir, f"{file_stem}.md")
            if not os.path.exists(md_path):
                raise RuntimeError(f"MinerU 解析失败: 未生成 markdown 文件（目录: {parse_dir}）")

            with open(md_path, "r", encoding="utf-8") as f:
                md_text = f.read()

            if not md_text.strip():
                raise RuntimeError("PDF 解析后无有效文本内容")

            # 保护表格不被分块切断
            md_text = _protect_markdown_tables(md_text)

            # 处理图片：复制 + Qwen-VL 描述
            image_paths: list[str] = []
            images_dir = os.path.join(parse_dir, "images")
            if os.path.isdir(images_dir):
                images = sorted(os.listdir(images_dir))
                _report(f"处理 {len(images)} 张图片...")

                # ⚠️ 先复制、后检查上限、最后再描述 —— 避免白花 API 费用
                copied: list[tuple[str, str]] = []
                for fname in images:
                    src = os.path.join(images_dir, fname)
                    if not os.path.isfile(src):
                        continue
                    dst_name = f"doc{doc_id}_{fname}"
                    dst = os.path.join(settings.IMAGE_DIR, dst_name)
                    shutil.copy2(src, dst)
                    image_paths.append(dst)
                    copied.append((dst, fname))

                # 图片数检查（在这里检查，而不是等 pipeline 里描述完再查）
                max_imgs = getattr(settings, "MAX_IMAGES_PER_DOC", 200)
                if len(copied) > max_imgs:
                    raise RuntimeError(
                        f"图片数({len(copied)})超过上限({max_imgs})，已跳过图片描述。"
                        f"可在 .env 中调高 MAX_IMAGES_PER_DOC")

                # Qwen-VL 描述（IMAGE_DESCRIBE=false 则跳过）
                described: dict[str, str] = {}
                if copied and getattr(settings, "IMAGE_DESCRIBE", True):
                    _report(f"描述 {len(copied)} 张图片...")
                    with ThreadPoolExecutor(max_workers=3) as pool:
                        futures = {pool.submit(_describe_image, dst): (dst, ref)
                                   for dst, ref in copied}
                        done = 0
                        for f in as_completed(futures):
                            done += 1
                            _report(f"描述图片 {done}/{len(copied)}")
                            try:
                                desc = f.result(timeout=20)
                                dst, ref = futures[f]
                                if desc:
                                    described[ref] = desc
                            except Exception:
                                pass

                # 替换 markdown 图片引用 → [IMAGE: name]: desc
                if copied:
                    for _, ref in copied:
                        desc = described.get(ref, "图片")
                        new_tag = f"[IMAGE: doc{doc_id}_{ref}]: {desc}"
                        md_text = re.sub(
                            r'!\[.*?\]\(' + re.escape(f"images/{ref}") + r'\)',
                            lambda _: new_tag, md_text)
                        if new_tag not in md_text:
                            md_text = md_text.replace(f"images/{ref}", new_tag)

            return md_text, image_paths

# ═══════════════════════════════════════════════════════
# DOCX
# ═══════════════════════════════════════════════════════
class DOCXLoader(BaseLoader):
    def load(self, file_path: str, doc_id: int = 0, on_progress=None) -> tuple[str, list[str]]:
        from docx import Document as DocxDocument

        try:
            doc = DocxDocument(file_path)
        except Exception as e:
            raise RuntimeError(f"无法打开 DOCX 文件: {e}")

        all_parts: list[str] = []
        image_paths: list[str] = []

        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                all_parts.append(text)

        for tab in doc.tables:
            rows = []
            for row in tab.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                rows.append("| " + " | ".join(cells) + " |")
            if rows:
                header_sep = "|" + "|".join([" --- " for _ in rows[0].split("|") if _]) + "|"
                md = rows[0] + "\n" + header_sep + "\n" + "\n".join(rows[1:])
                all_parts.append(f"[TABLE_START]\n{md}\n[TABLE_END]")

        if not all_parts:
            raise RuntimeError("DOCX 文件无有效内容")

        return "\n\n".join(all_parts), image_paths


# ═══════════════════════════════════════════════════════
# Markdown
# ═══════════════════════════════════════════════════════
class MarkdownLoader(BaseLoader):
    def load(self, file_path: str, doc_id: int = 0, on_progress=None) -> tuple[str, list[str]]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            raise RuntimeError(f"文件不存在: {file_path}")
        except UnicodeDecodeError:
            raise RuntimeError(f"文件编码不支持: {file_path}")

        if not text.strip():
            raise RuntimeError("文件内容为空")
        return text, []


# ═══════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════
def _protect_markdown_tables(text: str) -> str:
    """将 markdown 表格包裹在 [TABLE_START]...[TABLE_END] 中，防止分块切断。"""
    lines = text.split("\n")
    result: list[str] = []
    in_table = False
    table_buf: list[str] = []

    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|")
        is_separator = bool(re.match(r'^\|[\s\-:]+\|$', stripped))

        if is_table_line or is_separator:
            if not in_table:
                in_table = True
                table_buf = []
            table_buf.append(line)
        else:
            if in_table:
                if len(table_buf) >= 2:
                    result.append("[TABLE_START]")
                    result.extend(table_buf)
                    result.append("[TABLE_END]")
                else:
                    result.extend(table_buf)
                table_buf = []
                in_table = False
            result.append(line)

    if in_table and len(table_buf) >= 2:
        result.append("[TABLE_START]")
        result.extend(table_buf)
        result.append("[TABLE_END]")

    return "\n".join(result)


def _describe_image(image_path: str) -> str | None:
    """用 Qwen-VL 描述图片内容。"""
    try:
        from src.knowledge_base.image_describer import describe_image
        return describe_image(image_path)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════
# 注册
# ═══════════════════════════════════════════════════════
LOADERS: dict[str, BaseLoader] = {
    "pdf": PDFLoader(),
    "docx": DOCXLoader(),
    "md": MarkdownLoader(),
}


def get_loader(file_type: str) -> BaseLoader:
    loader = LOADERS.get(file_type.lower())
    if loader is None:
        raise ValueError(f"不支持的文件类型: {file_type}，支持: {list(LOADERS.keys())}")
    return loader


def load_document(file_path: str, file_type: str, doc_id: int = 0, on_progress=None) -> tuple[str, list[str]]:
    """返回 (合并文本, 图片路径列表)。on_progress(step_name, pct) 可选。"""
    loader = get_loader(file_type)
    return loader.load(file_path, doc_id, on_progress=on_progress)
