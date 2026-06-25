"""
Reranker 精排 — Cross-Encoder 深度相关性判断

使用 BAAI/bge-reranker-base 对候选 chunk 逐条计算 (query, chunk)
交叉注意力分数，过滤低分噪声，输出 Top-N。

对应 TECH_DESIGN.md §2.2。
"""
from __future__ import annotations

from typing import List, Dict

from loguru import logger

from backend.config import settings


class Reranker:
    """Cross-Encoder Reranker — 对候选列表二次精排。

    延迟加载模型（首次调用时加载），避免启动时间和内存浪费。
    """

    def __init__(self) -> None:
        self._model = None       # FlagEmbedding 的 FlagReranker 实例
        self._loaded = False
        self._loading = False

    # ── 公开方法 ────────────────────────────────────────

    def rerank(
        self,
        query: str,
        candidates: List[Dict],
        top_k: int | None = None,
        threshold: float = 0.0,
    ) -> List[Dict]:
        """对候选列表重新打分排序。

        Args:
            query: 用户提问。
            candidates: 候选 chunk 列表，每个需含 "content" 字段。
            top_k: 最终返回条数（默认 settings.final_top_k）。
            threshold: 低于此分数的 chunk 丢弃。

        Returns:
            按 rerank_score 降序的 chunk 列表，添加 "rerank_score" 字段。
        """
        if not candidates:
            return []

        if top_k is None:
            top_k = settings.final_top_k

        # 确保模型已加载
        self._ensure_loaded()

        if self._model is None:
            logger.warning("Reranker 模型不可用，返回原始排序")
            return candidates[:top_k]

        # 准备 (query, doc) 对
        pairs = [[query, c.get("content", "")] for c in candidates]

        try:
            scores = self._model.compute_score(pairs, normalize=True)
        except Exception as e:
            logger.error("Reranker 评分失败: {}", e)
            return candidates[:top_k]

        # 附加分数
        if not isinstance(scores, list):
            scores = [scores] * len(candidates)

        for i, score in enumerate(scores):
            candidates[i]["rerank_score"] = float(score)

        # 过滤 + 排序
        filtered = [c for c in candidates if c.get("rerank_score", 0) >= threshold]
        filtered.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

        logger.debug(
            "Reranker: {} → {} (threshold={:.2f})",
            len(candidates), len(filtered), threshold,
        )
        return filtered[:top_k]

    def is_available(self) -> bool:
        """检查模型是否可用（不触发加载）。"""
        return self._loaded and self._model is not None

    # ── 内部 ────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """延迟加载 Reranker 模型（线程不安全，应在主线程调用）。"""
        if self._loaded:
            return
        if self._loading:
            return  # 防止重入

        self._loading = True
        try:
            from FlagEmbedding import FlagReranker  # type: ignore[import-untyped]

            device = self._resolve_device()
            logger.info("加载 Reranker 模型: {} (device={})", settings.reranker_model, device)
            self._model = FlagReranker(
                settings.reranker_model,
                use_fp16=(device == "cuda"),
                device=device,
            )
            self._loaded = True
            logger.info("Reranker 模型加载完成")
        except ImportError:
            logger.warning("FlagEmbedding 未安装，Reranker 不可用")
            self._model = None
            self._loaded = True
        except Exception as e:
            logger.opt(exception=True).error("Reranker 模型加载失败: {}", e)
            self._model = None
            self._loaded = True  # 标记已尝试，避免反复失败
        finally:
            self._loading = False

    @staticmethod
    def _resolve_device() -> str:
        """解析 settings.reranker_device → 实际设备。"""
        device = settings.reranker_device
        if device != "auto":
            return device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
