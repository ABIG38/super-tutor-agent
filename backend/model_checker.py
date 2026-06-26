"""模型检测 — 启动时检查 Embedding 模型是否存在。"""
from __future__ import annotations

from backend.config import settings


def check_models() -> dict:
    """检测模型文件状态。返回 {name: bool}"""
    models_dir = settings.models_dir
    result = {}
    for name in ["embedding", "reranker"]:
        model_id = settings.embedding_model if name == "embedding" else "BAAI/bge-reranker-base"
        folder = models_dir / model_id.replace("/", "--")
        exists = folder.exists() and any(f.suffix in (".bin", ".safetensors") for f in folder.rglob("*") if f.is_file())
        result[name] = exists
    return result
