import uuid
import os
import shutil
import threading
from pathlib import Path
from typing import List, Dict, Literal, Generator

from loguru import logger
from dotenv import load_dotenv

from backend.config import settings
from backend.document.parser import DocumentParser
from backend.document.splitter import chunk_document
from backend.retrieval.vector_store import VectorStore
from backend.retrieval.bm25_search import BM25Searcher
from backend.retrieval.hybrid_search import HybridSearcher
from backend.retrieval.reranker import Reranker
from backend.llm.client import CitationLLM, ChunkForLLM
from backend.agent.tracker import StudyTracker
from backend.agent.planner import StudyPlanner, PlanGenerationError


class SuperTutorAgent:
    """Orchestrator: DocumentParser + HybridSearcher(RRF+BM25+Reranker) + LLM + Tracker."""

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
        self.bm25 = BM25Searcher()
        self.hybrid = HybridSearcher(self.vector_store, self.bm25)
        self.reranker = Reranker()  # ★ B3/B4: Cross-Encoder 精排

        api_key = settings.llm_api_key if settings.llm_api_key != "MISSING_KEY" else os.environ.get("OPENAI_API_KEY", "dummy_key")
        api_base = os.environ.get("OPENAI_BASE_URL") or settings.llm_api_base
        model = os.environ.get("OPENAI_MODEL") or settings.llm_model
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

            # ★ D1: 分步写入 + 失败回滚
            chroma_ok = False
            try:
                self.vector_store.add_chunks(chunks)
                chroma_ok = True

                self.hybrid.sync_chunks(chunks)

            except Exception:
                # 回滚 ChromaDB（如果已写入）
                if chroma_ok:
                    logger.warning("BM25 同步失败，回滚 ChromaDB chunks for {}", filename)
                    try:
                        self.vector_store.delete_by_source(filename)
                    except Exception as rollback_err:
                        logger.error("回滚 ChromaDB 失败: {}", rollback_err)
                raise

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
        """删除文档：向量索引 + BM25 + 来源记录。"""
        if filename not in self._sources:
            return {"ok": False, "reason": "not_found"}
        try:
            self.vector_store.delete_by_source(filename)
            self.hybrid.sync_delete(filename)  # ★ B4: 同步 BM25 删除
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
                "file_path": info.get("file_path", ""),
            })
        return docs

    def preview_document(self, filename: str) -> Dict:
        """★ F-05: 重新解析文档并返回纯文本预览。

        Returns:
            {"ok": True, "text": str, "filename": str, "size": int}
            {"ok": False, "reason": str}
        """
        if filename not in self._sources:
            return {"ok": False, "reason": "not_found"}

        file_path = self._sources[filename].get("file_path", "")
        if not file_path or not Path(file_path).exists():
            return {"ok": False, "reason": "文件已不存在，请重新上传"}

        try:
            doc = self.parser.parse(file_path, doc_type=self._sources[filename].get("doc_type", "textbook"))
            return {
                "ok": True,
                "text": doc.text,
                "filename": doc.filename,
                "size": len(doc.text),
                "scanned": doc.scanned,
            }
        except Exception as e:
            logger.error("预览失败: {} — {}", filename, e)
            return {"ok": False, "reason": str(e)}

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
        """★ B4: 混合检索 (Vector+BM25+RRF) + Reranker → 流式回答。"""
        if not self._sources:
            yield "知识库为空，请先上传文档。"
            return

        # 1. 混合检索
        candidates = self.hybrid.search(query, course=course)
        if not candidates:
            yield "未在上传文档中找到相关答案，请检查文档内容或更换提问方式。"
            return

        # 2. Reranker 精排
        final = self.reranker.rerank(query, candidates) if self.reranker.is_available() else candidates[:settings.final_top_k]
        if not final:
            yield "未在上传文档中找到相关答案，请检查文档内容或更换提问方式。"
            return

        # 3. 转换为 ChunkForLLM
        pydantic_chunks = [
            ChunkForLLM(
                content=c.get("content", ""),
                filename=c.get("filename", ""),
                course=c.get("course", ""),
                score=c.get("rerank_score", c.get("rrf_score", c.get("score", 0.0))),
            ) for c in final
        ]

        # 4. 流式 LLM
        for token in self.llm.generate_with_citation_stream(query, pydantic_chunks):
            yield token

    # ── 规划 ────────────────────────────────────────────────

    def generate_plan(self, days: int, hours: int, course: str = "") -> Dict:
        """Generate a study plan, save it to tracker, and return tasks."""
        chunks = self.hybrid.search_raw("课程目录 章节重点 考点", top_k=15, course=course)

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

    def save(self) -> None:
        """持久化 BM25 索引（应用关闭时调用）。"""
        self.hybrid.save()

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
