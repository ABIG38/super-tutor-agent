"""
模型下载工作线程 — ModelDownloadWorker

使用 QThread + huggingface_hub 逐文件下载模型，
通过 Qt 信号报告进度（文件名 + 百分比 + 速度），
UI 可连接信号实时更新状态栏/进度条。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QThread, Signal, QObject

from backend.config import settings
from backend.model_checker import _model_folder


class DownloadProgress:
    """下载进度快照。"""
    def __init__(self, model_name: str = "") -> None:
        self.model_name = model_name
        self.current_file = ""
        self.file_index = 0
        self.total_files = 0
        self.bytes_downloaded = 0
        self.total_bytes = 0
        self.speed_kbps: float = 0.0
        self.elapsed_sec: float = 0.0

    @property
    def percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(self.bytes_downloaded / self.total_bytes * 100, 100.0)

    @property
    def label(self) -> str:
        return f"正在下载 {self.model_name}  ({self.percent:.0f}%)"


class ModelDownloadWorker(QObject):
    """模型下载工作器（需配合 QThread 使用）。

    信号:
        progress(DownloadProgress)   — 进度更新
        done(str)                    — 下载完成（模型名）
        error(str, str)              — 失败（模型名, 原因）

    用法:
        thread = QThread()
        worker = ModelDownloadWorker()
        worker.moveToThread(thread)
        thread.started.connect(lambda: worker.download(["embedding", "reranker"]))
        worker.progress.connect(...)
        worker.done.connect(...)
        thread.start()
    """

    progress = Signal(DownloadProgress)  # 进度
    done = Signal(str)                   # 模型名
    error = Signal(str, str)             # 模型名, 原因

    def download(self, model_names: list[str]) -> None:
        """下载指定的模型列表。"""
        from huggingface_hub import HfApi
        from requests.exceptions import RequestException

        api = HfApi()

        for name in model_names:
            model_id = self._model_id(name)
            if model_id is None:
                self.error.emit(name, "未知模型类型")
                continue

            try:
                self._download_model(api, name, model_id)
                self.done.emit(name)
            except (RequestException, OSError) as e:
                logger.error("模型下载失败: {} — {}", name, e)
                self.error.emit(name, str(e)[:100])
            except Exception as e:
                logger.opt(exception=True).error("模型下载异常: {} — {}", name, e)
                self.error.emit(name, str(e)[:100])

    # ── 内部下载逻辑 ─────────────────────────────────

    def _download_model(self, api: "HfApi", name: str, repo_id: str) -> None:
        """下载单个仓库的全部文件，带进度回调。"""
        from huggingface_hub import hf_hub_download

        models_dir = settings.models_dir
        models_dir.mkdir(parents=True, exist_ok=True)
        local_dir = models_dir / _model_folder(repo_id)
        local_dir.mkdir(parents=True, exist_ok=True)

        logger.info("开始下载模型: {} → {}", repo_id, local_dir)

        # 临时关闭离线模式
        old_offline = os.environ.get("HF_HUB_OFFLINE")
        os.environ["HF_HUB_OFFLINE"] = "0"

        try:
            # 1. 获取模型文件列表和大小
            repo_info = api.repo_info(repo_id, files_metadata=True)
            siblings = list(repo_info.siblings or [])
            # 过滤出实际文件（排除符号链接）
            files = [s for s in siblings if s.size is not None and s.size > 0]

            if not files:
                logger.warning("模型 {} 没有可下载的文件", repo_id)
                return

            total_bytes = sum(s.size for s in files)
            downloaded_bytes = 0

            # 2. 准备进度
            prog = DownloadProgress(name)
            prog.total_files = len(files)
            prog.total_bytes = total_bytes

            start_time = time.time()

            # 3. 逐文件下载
            for idx, sibling in enumerate(files):
                file_path = sibling.rfilename
                local_file = local_dir / file_path
                local_file.parent.mkdir(parents=True, exist_ok=True)

                # 跳过已存在的完整文件
                if local_file.exists() and local_file.stat().st_size == sibling.size:
                    downloaded_bytes += sibling.size
                    prog.bytes_downloaded = downloaded_bytes
                    prog.file_index = idx + 1
                    prog.current_file = file_path
                    elapsed = time.time() - start_time
                    prog.elapsed_sec = elapsed
                    prog.speed_kbps = (downloaded_bytes / 1024) / (elapsed or 0.001)
                    self.progress.emit(prog)
                    continue

                # 下载单文件（带重试）
                try:
                    hf_hub_download(
                        repo_id=repo_id,
                        filename=file_path,
                        local_dir=str(local_dir),
                        local_dir_use_symlinks=False,
                        resume_download=True,
                        token=None,
                    )
                except Exception:
                    # 如果文件太小，忽略错误继续
                    if sibling.size and sibling.size > 100_000:
                        raise
                    logger.warning("跳过小文件下载: {}", file_path)

                # 更新进度
                if local_file.exists():
                    downloaded_bytes += local_file.stat().st_size
                else:
                    downloaded_bytes += sibling.size

                prog.bytes_downloaded = min(downloaded_bytes, total_bytes)
                prog.file_index = idx + 1
                prog.current_file = file_path
                elapsed = time.time() - start_time
                prog.elapsed_sec = elapsed
                prog.speed_kbps = (downloaded_bytes / 1024) / (elapsed or 0.001)
                self.progress.emit(prog)

        finally:
            # 恢复离线模式
            if old_offline is not None:
                os.environ["HF_HUB_OFFLINE"] = old_offline
            else:
                os.environ.pop("HF_HUB_OFFLINE", None)

        logger.info("模型下载完成: {} ({:.1f} MB)", repo_id, total_bytes / 1024 / 1024)

    @staticmethod
    def _model_id(name: str) -> str | None:
        """模型类型 → HuggingFace ID。"""
        if name == "embedding":
            return settings.embedding_model
        elif name == "reranker":
            return settings.reranker_model
        return None
