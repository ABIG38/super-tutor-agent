"""
模型检测器 — ModelChecker

职责:
    1. 启动时检测本地 Embedding / Reranker 模型文件是否存在
    2. 缺失时提供下载能力（huggingface_hub）
    3. 损坏时提示重新下载

对应需求 F-20 / TECH_DESIGN §9 #⑱ #⑲。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from loguru import logger

from backend.config import settings


class ModelStatus:
    """单个模型的检测状态。"""
    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.path = path
        self.exists = path.exists()
        self.is_dir = path.is_dir() if self.exists else False
        self.file_count = 0

        if self.is_dir:
            # 简单判断：目录下至少有一个 .json 配置文件 + 一个模型权重文件
            contents = list(path.rglob("*"))
            self.file_count = len([f for f in contents if f.is_file()])
            has_config = any(f.suffix == ".json" for f in contents if f.is_file())
            has_weights = any(
                f.suffix in (".bin", ".safetensors", ".pt", ".pth", ".msgpack", ".h5", ".onnx")
                for f in contents if f.is_file()
            )
            self.healthy = has_config and has_weights
        else:
            self.healthy = False


class CheckResult:
    """模型检测结果。"""
    def __init__(self) -> None:
        self.models: dict[str, ModelStatus] = {}
        self.all_ok: bool = True
        self.missing: list[str] = []       # 不存在的模型名
        self.corrupted: list[str] = []     # 存在但无效的模型名

    def add(self, status: ModelStatus) -> None:
        self.models[status.name] = status
        if not status.exists:
            self.all_ok = False
            self.missing.append(status.name)
        elif not status.healthy:
            self.all_ok = False
            self.corrupted.append(status.name)


def check_models(models_dir: Path | None = None) -> CheckResult:
    """检测 Embedding 和 Reranker 模型文件。

    Args:
        models_dir: 模型缓存目录，默认 settings.models_dir。

    Returns:
        CheckResult: 包含每个模型的状态。
    """
    if models_dir is None:
        models_dir = settings.models_dir

    logger.info("检测模型文件: {}", models_dir)

    result = CheckResult()

    # ── Embedding 模型 ──
    emb_name = settings.embedding_model  # e.g. "BAAI/bge-small-zh-v1.5"
    emb_dir = models_dir / _model_folder(emb_name)
    result.add(ModelStatus("embedding", emb_dir))

    # ── Reranker 模型 ──
    rerank_name = settings.reranker_model  # e.g. "BAAI/bge-reranker-base"
    rerank_dir = models_dir / _model_folder(rerank_name)
    result.add(ModelStatus("reranker", rerank_dir))

    # 日志
    for name, st in result.models.items():
        if st.exists and st.healthy:
            logger.info("  ✅ {}: {} ({} 文件)", name, st.path, st.file_count)
        elif st.exists:
            logger.warning("  ⚠️ {}: {} 存在但可能损坏 ({} 文件)", name, st.path, st.file_count)
        else:
            logger.warning("  ❌ {}: {} 不存在", name, st.path)

    return result


def download_model(
    model_name: str,
    models_dir: Path | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> bool:
    """下载单个 HuggingFace 模型到本地。

    Args:
        model_name: HuggingFace 模型 ID，如 "BAAI/bge-small-zh-v1.5"。
        models_dir: 缓存目录。
        progress_callback: 进度回调 (current, total)。

    Returns:
        True 表示下载成功。
    """
    if models_dir is None:
        models_dir = settings.models_dir

    models_dir.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download

        logger.info("开始下载模型: {} → {}", model_name, models_dir)

        # 临时关闭离线模式以下载
        old_offline = os.environ.get("HF_HUB_OFFLINE")
        old_transformers = os.environ.get("TRANSFORMERS_OFFLINE")
        os.environ["HF_HUB_OFFLINE"] = "0"
        os.environ["TRANSFORMERS_OFFLINE"] = "0"

        try:
            local_path = snapshot_download(
                repo_id=model_name,
                cache_dir=str(models_dir),
                local_dir=str(models_dir / _model_folder(model_name)),
                local_dir_use_symlinks=False,
                resume_download=True,
                max_workers=2,
            )
        finally:
            # 恢复离线模式
            if old_offline is not None:
                os.environ["HF_HUB_OFFLINE"] = old_offline
            else:
                os.environ.pop("HF_HUB_OFFLINE", None)
            if old_transformers is not None:
                os.environ["TRANSFORMERS_OFFLINE"] = old_transformers
            else:
                os.environ.pop("TRANSFORMERS_OFFLINE", None)

        logger.info("模型下载完成: {} → {}", model_name, local_path)
        return True

    except Exception as e:
        logger.opt(exception=True).error("模型下载失败: {} — {}", model_name, e)
        return False


def download_all_missing(
    result: CheckResult,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> dict[str, bool]:
    """下载所有缺失/损坏的模型。

    Args:
        result: check_models() 的返回值。
        progress_callback: 进度回调 (model_name, current, total)。

    Returns:
        {model_name: success_bool}
    """
    outcomes: dict[str, bool] = {}
    to_download = result.missing + result.corrupted

    for name in to_download:
        model_id = _model_id_for(name)
        if model_id is None:
            logger.warning("未知模型类型: {}", name)
            outcomes[name] = False
            continue
        ok = download_model(model_id, progress_callback=(
            lambda c, t, n=name: progress_callback(n, c, t) if progress_callback else None
        ))
        outcomes[name] = ok

    return outcomes


# ── 内部 ──────────────────────────────────────────────

def _model_folder(model_id: str) -> str:
    """HuggingFace ID → 本地文件夹名。"""
    return model_id.replace("/", "--")


def _model_id_for(kind: str) -> str | None:
    """模型类型 → HuggingFace ID。"""
    if kind == "embedding":
        return settings.embedding_model
    elif kind == "reranker":
        return settings.reranker_model
    return None
