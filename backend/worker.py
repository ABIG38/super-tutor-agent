"""
后台工作线程 — BackgroundWorker

将所有耗时操作（文档索引、LLM 问答、计划生成）放到 QThread 执行，
通过 Qt 信号与主线程通信，保持 UI 不卡顿。

信号:
    status_update(str)     — 状态栏文字更新
    ingest_done(dict)      — 索引完成
    ask_token(str)         — 流式 token
    ask_done()             — 问答完成
    ask_error(str)         — 问答出错
    plan_done(dict)        — 计划生成完成
    plan_error(str)        — 计划生成失败
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal, QObject

from backend.agent.orchestrator import SuperTutorAgent
from backend.agent.planner import PlanGenerationError
from backend.llm.client import LLMError


class BackgroundWorker(QObject):
    """后台工作线程管理器。

    使用方式:
        worker = BackgroundWorker()
        worker.status_update.connect(status_label.setText)
        worker.ingest_done.connect(on_ingest_done)
        worker.ingest_async("/path/to/file.pdf", doc_type="textbook", course="课程1")
    """

    # ── 信号 ──────────────────────────────────────────

    status_update = Signal(str)

    # 文档索引
    ingest_done = Signal(dict)  # {"ok": bool, ...}

    # 问答（流式）
    ask_token = Signal(str)     # 逐 token
    ask_done = Signal()         # 完成
    ask_error = Signal(str)     # 出错

    # 计划
    plan_done = Signal(dict)    # {"ok": bool, "tasks": [...], ...}
    plan_error = Signal(str)
    progress_loaded = Signal(dict)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._agent: SuperTutorAgent | None = None

    @property
    def agent(self) -> SuperTutorAgent:
        if self._agent is None:
            self._agent = SuperTutorAgent()
        return self._agent

    # ── 文档索引 ───────────────────────────────────────

    def ingest_async(
        self,
        file_path: str,
        doc_type: str = "textbook",
        course: str = "",
    ) -> None:
        """后台索引文档。"""
        self.status_update.emit(f"正在索引 {file_path.rsplit('/', 1)[-1]}...")

        class IngestThread(QThread):
            result_signal = Signal(dict)

            def __init__(self, agent, file_path, doc_type, course):
                super().__init__()
                self._agent = agent
                self._file_path = file_path
                self._doc_type = doc_type
                self._course = course

            def run(self):
                result = self._agent.ingest_document(
                    self._file_path, doc_type=self._doc_type, course=self._course,
                )
                self.result_signal.emit(result)

        self._thread = IngestThread(self.agent, file_path, doc_type, course)
        # noinspection PyUnresolvedReferences
        self._thread.result_signal.connect(self._on_ingest_done)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_ingest_done(self, result: dict) -> None:
        if result.get("ok"):
            self.status_update.emit(
                f"索引完成: {result.get('filename', '')} ({result.get('chunk_count', 0)} 个片段)"
            )
        else:
            reason = result.get("reason", "未知错误")
            self.status_update.emit(f"索引失败: {reason}")
        self.ingest_done.emit(result)

    # ── 问答（流式）───────────────────────────────────

    def ask_async(self, query: str, course: str = "") -> None:
        """后台流式问答。"""
        self.status_update.emit("正在检索并生成回答...")

        class AskThread(QThread):
            token_signal = Signal(str)
            done_signal = Signal()
            error_signal = Signal(str)

            def __init__(self, agent, query, course):
                super().__init__()
                self._agent = agent
                self._query = query
                self._course = course

            def run(self):
                try:
                    for token in self._agent.ask(self._query, course=self._course):
                        self.token_signal.emit(token)
                    self.done_signal.emit()
                except LLMError as e:
                    self.error_signal.emit(str(e.message))
                except Exception as e:
                    self.error_signal.emit(f"问答异常: {e}")

        self._ask_thread = AskThread(self.agent, query, course)
        # noinspection PyUnresolvedReferences
        self._ask_thread.token_signal.connect(self.ask_token)
        self._ask_thread.done_signal.connect(self._on_ask_done)
        self._ask_thread.error_signal.connect(self._on_ask_error)
        self._ask_thread.finished.connect(self._ask_thread.deleteLater)
        self._ask_thread.start()

    def _on_ask_done(self) -> None:
        self.status_update.emit("就绪")
        self.ask_done.emit()

    def _on_ask_error(self, msg: str) -> None:
        self.status_update.emit(f"问答失败: {msg}")
        self.ask_error.emit(msg)

    def cancel_ask(self) -> None:
        """中断当前问答。"""
        self.agent.cancel_stream()

    # ── 计划生成 ───────────────────────────────────────

    def plan_async(self, days: int, hours: int, course: str = "") -> None:
        """后台生成学习计划。"""
        self.status_update.emit("正在生成学习计划...")

        class PlanThread(QThread):
            result_signal = Signal(dict)
            error_signal = Signal(str)

            def __init__(self, agent, days, hours, course):
                super().__init__()
                self._agent = agent
                self._days = days
                self._hours = hours
                self._course = course

            def run(self):
                try:
                    result = self._agent.generate_plan(
                        self._days, self._hours, course=self._course,
                    )
                    self.result_signal.emit(result)
                except PlanGenerationError as e:
                    self.error_signal.emit(str(e))
                except LLMError as e:
                    self.error_signal.emit(str(e.message))
                except Exception as e:
                    self.error_signal.emit(f"计划生成异常: {e}")

        self._plan_thread = PlanThread(self.agent, days, hours, course)
        # noinspection PyUnresolvedReferences
        self._plan_thread.result_signal.connect(self._on_plan_done)
        # noinspection PyUnresolvedReferences
        self._plan_thread.error_signal.connect(self._on_plan_error)
        self._plan_thread.finished.connect(self._plan_thread.deleteLater)
        self._plan_thread.start()

    def _on_plan_done(self, result: dict) -> None:
        if result.get("ok"):
            self.status_update.emit("计划生成完成")
        else:
            self.status_update.emit(f"计划生成失败: {result.get('reason', '')}")
        self.plan_done.emit(result)

    def _on_plan_error(self, msg: str) -> None:
        self.status_update.emit(f"计划生成失败: {msg}")
        self.plan_error.emit(msg)

    # ── 进度 ──────────────────────────────────────────

    def load_progress(self, course: str = "") -> None:
        """加载当前课程的学习进度。"""
        progress = self.agent.get_plan_progress(course)
        self.progress_loaded.emit(progress)

    def mark_task(self, task_id: int, completed: bool) -> None:
        """标记任务完成状态。"""
        self.agent.mark_task(task_id, completed)

    def get_documents(self, course: str = "") -> list:
        """获取文档列表（同步，可直接在主线程调用）。"""
        return self.agent.get_documents(course)

    def delete_document(self, filename: str) -> dict:
        """删除文档。"""
        return self.agent.delete_document(filename)
