import uuid
import os
import shutil
import threading
from pathlib import Path
from typing import List, Dict, Literal, Generator

from loguru import logger
from dotenv import load_dotenv

from backend.document.parser import DocumentParser
from backend.document.splitter import chunk_document
from backend.retrieval.vector_store import VectorStore
from backend.llm.client import CitationLLM, ChunkForLLM
from backend.agent.tracker import StudyTracker
from backend.agent.planner import StudyPlanner, PlanGenerationError


class SuperTutorAgent:
    """Orchestrator tying together Document Parser, VectorStore, LLM, and Tracker."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(SuperTutorAgent, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Prevent re-initialization
        if hasattr(self, "initialized") and self.initialized:
            return

        load_dotenv()

        self.parser = DocumentParser()
        self.vector_store = VectorStore()

        api_key = os.environ.get("OPENAI_API_KEY", "dummy_key")
        api_base = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        model = os.environ.get("OPENAI_MODEL", "deepseek-chat")
        self.llm = CitationLLM(api_key=api_key, api_base=api_base, model=model)

        self.tracker = StudyTracker()
        self.planner = StudyPlanner(self.llm)

        # ★ 修复 #4：来源追踪 — 记录已索引的文件（用于重复检测 + 删除/重命名）
        self._sources: Dict[str, dict] = {}        # filename → {file_path, doc_type, course, chunk_count}
        self._display_names: Dict[str, str] = {}   # filename → 显示名

        self.initialized = True

    # ── 文档管理 ─────────────────────────────────────────────

    def ingest_document(
        self,
        file_path: str,
        doc_type: Literal["textbook", "past_paper"] = "textbook",  # ★ 修复 #3
        course: str = "",
    ) -> Dict:
        """Parse, chunk, and index a document.

        Returns:
            {"ok": True, "chunk_count": int, "filename": str}
            {"ok": False, "reason": "duplicate"|"scanned_pdf"|"file_too_large"|...}
        """
        file_path_obj = Path(file_path)
        filename = file_path_obj.name

        # ★ 修复 #4：重复上传检测
        if filename in self._sources:
            logger.info("重复上传检测: {} — 已存在", filename)
            return {"ok": False, "reason": "duplicate", "filename": filename}

        try:
            logger.info("开始索引文档: {}", file_path_obj.resolve())

            # 磁盘空间检查（TECH_DESIGN §9 #⑭）
            self._check_disk_space(file_path_obj)

            doc = self.parser.parse(file_path, doc_type=doc_type, course=course)

            if doc.scanned:
                logger.warning("扫描件 PDF 拒绝索引: {}", filename)
                return {"ok": False, "reason": "scanned_pdf", "filename": filename}

            chunks = chunk_document(doc.text, {
                "filename": doc.filename,
                "course": course,
                "doc_type": doc.doc_type,
            })

            self.vector_store.add_chunks(chunks)

            # 记录来源
            self._sources[filename] = {
                "file_path": str(file_path_obj.resolve()),
                "doc_type": doc_type,
                "course": course,
                "chunk_count": len(chunks),
            }
            self._display_names[filename] = filename

            logger.info(
                "文档索引完成: {} | {} chunks | course={} | type={}",
                filename, len(chunks), course, doc_type,
            )
            return {"ok": True, "chunk_count": len(chunks), "filename": filename}

        except (FileNotFoundError, ValueError, PermissionError) as e:
            logger.warning("索引前置检查失败: {}", e)
            return {"ok": False, "reason": self._classify_error(e), "filename": filename}

        except OSError as e:
            logger.warning("磁盘空间不足: {}", e)
            return {"ok": False, "reason": "disk_full", "filename": filename}

        except Exception as e:
            logger.opt(exception=True).error("索引异常: {}", e)
            return {"ok": False, "reason": str(e), "filename": filename}

    def delete_document(self, filename: str) -> Dict:
        """删除文档：向量索引 + 来源记录。"""
        if filename not in self._sources:
            return {"ok": False, "reason": "not_found"}
        try:
            self.vector_store.delete_by_source(filename)
            self._sources.pop(filename, None)
            self._display_names.pop(filename, None)
            logger.info("文档已删除: {}", filename)
            return {"ok": True}
        except Exception as e:
            logger.error("删除文档失败: {} — {}", filename, e)
            return {"ok": False, "reason": str(e)}

    def rename_document(self, old_filename: str, new_filename: str) -> Dict:
        """重命名文档显示名（不改动磁盘文件）。"""
        if old_filename not in self._sources:
            return {"ok": False, "reason": "not_found"}
        if new_filename in self._display_names:
            return {"ok": False, "reason": "name_conflict"}
        self._display_names[new_filename] = self._display_names.pop(old_filename, old_filename)
        self._sources[new_filename] = self._sources.pop(old_filename)
        self.vector_store.update_filename_metadata(old_filename, new_filename)
        logger.info("文档重命名: {} → {}", old_filename, new_filename)
        return {"ok": True}

    def get_documents(self, course: str = "") -> List[Dict]:
        """获取已索引文档列表。"""
        docs = []
        for filename, info in self._sources.items():
            if course and info.get("course") != course:
                continue
            docs.append({
                "filename": filename,
                "display_name": self._display_names.get(filename, filename),
                "doc_type": info.get("doc_type", "textbook"),
                "course": info.get("course", ""),
                "chunk_count": info.get("chunk_count", 0),
            })
        return docs

    def overwrite_document(self, file_path: str, doc_type: str = "textbook", course: str = "") -> Dict:
        """覆盖已有文档：先删除旧索引，再重新索引。"""
        filename = Path(file_path).name
        if filename in self._sources:
            self.delete_document(filename)
        return self.ingest_document(file_path, doc_type=doc_type, course=course)

    def delete_course(self, course: str) -> Dict:
        """★ 修复 #8：删除课程时清理 ChromaDB 和 SQLite 关联数据。"""
        docs_to_delete = [
            fn for fn, info in self._sources.items()
            if info.get("course") == course
        ]
        for fn in docs_to_delete:
            self.delete_document(fn)
        try:
            self.tracker.delete_course(course)
        except Exception as e:
            logger.warning("清理课程进度数据失败: {}", e)
        logger.info("课程已清理: {} | 删除了 {} 个文档", course, len(docs_to_delete))
        return {"ok": True, "deleted_docs": len(docs_to_delete)}

    # ── 问答 ────────────────────────────────────────────────

    def ask(self, query: str, course: str = "") -> Generator[str, None, None]:
        """Hybrid search and stream response."""
        filter_meta = {"course": course} if course else None

        if not self._sources:
            yield "知识库为空，请先上传文档。"
            return

        chunks = self.vector_store.search(query, top_k=7, filter_meta=filter_meta)

        if not chunks:
            yield "未在当前课程的文档中找到相关内容，请先上传教材或调整提问。"
            return

        pydantic_chunks = [
            ChunkForLLM(
                content=c["content"],
                filename=c["filename"],
                course=c.get("course", ""),
                score=c.get("score", 0.0),
            ) for c in chunks
        ]

        for token in self.llm.generate_with_citation_stream(query, pydantic_chunks):
            yield token

    # ── 规划 ────────────────────────────────────────────────

    def generate_plan(self, days: int, hours: int, course: str = "") -> Dict:
        """Generate a study plan, save it to tracker, and return tasks."""
        filter_meta = {"course": course} if course else None
        chunks = self.vector_store.search_raw("课程目录 章节重点 考点", top_k=15, filter_meta=filter_meta)

        completed_chapters = self.tracker.get_completed_chapters(course)

        try:
            tasks = self.planner.generate_plan_json(days, hours, chunks, completed_chapters)
        except PlanGenerationError as e:
            logger.error("计划生成失败: {}", e)
            return {"ok": False, "reason": str(e)}

        # Save to DB
        plan_id = uuid.uuid4().hex
        self.tracker.init_plan(plan_id, tasks, course)

        return {"ok": True, "tasks": tasks, "plan_id": plan_id}

    def mark_task(self, task_id: int, completed: bool) -> None:
        """Mark task as completed."""
        self.tracker.mark_task(task_id, completed)

    def get_plan_progress(self, course: str = "") -> Dict:
        """Get current plan progress for a course."""
        return self.tracker.get_plan_progress(course)

    def cancel_stream(self) -> None:
        """中断当前 LLM 流式生成。"""
        self.llm.cancel_stream()

    # ── 内部 ────────────────────────────────────────────────

    @staticmethod
    def _check_disk_space(file_path: Path) -> None:
        """索引前检查磁盘剩余空间（TECH_DESIGN §9 #⑭）。"""
        try:
            usage = shutil.disk_usage(file_path.parent)
            file_size = file_path.stat().st_size
            estimated_index = file_size * 0.5  # 粗略预估 ChromaDB + BM25
            required = (file_size + estimated_index) * 2
            if usage.free < required:
                raise OSError(
                    f"磁盘空间不足：需要 {required / 1024 / 1024:.0f} MB，"
                    f"剩余 {usage.free / 1024 / 1024:.0f} MB"
                )
        except FileNotFoundError:
            pass  # 文件还不存在，跳过检查

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        """将已知异常映射为 UI 可读的原因码。"""
        msg = str(exc).lower()
        if "文件过大" in msg or "mb" in msg:
            return "file_too_large"
        if "不支持" in msg:
            return "unsupported_format"
        if "不存在" in msg:
            return "file_not_found"
        if "加密" in msg or "password" in msg:
            return "encrypted_pdf"
        return str(exc)[:100]
