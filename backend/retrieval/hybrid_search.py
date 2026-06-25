"""
混合检索引擎 — HybridSearcher

整合 VectorStore（语义） + BM25Searcher（关键词），
通过 RRF 倒数秩融合 + MD5 去重 + 分数阈值过滤，
输出高质量 Top-K 结果。

对应 TECH_DESIGN.md §2.2。
"""
from __future__ import annotations

import hashlib
from typing import List, Dict

from loguru import logger

from backend.config import settings
from backend.retrieval.vector_store import VectorStore
from backend.retrieval.bm25_search import BM25Searcher


class HybridSearcher:
    """混合检索引擎 — Vector + BM25 + RRF 融合。"""

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        bm25: BM25Searcher | None = None,
    ) -> None:
        self.vector = vector_store or VectorStore()
        self.bm25 = bm25 or BM25Searcher()

    # ── 检索 ────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int | None = None,
        course: str = "",
        use_bm25: bool = True,
    ) -> List[Dict]:
        """混合检索入口。

        流程:
            1. VectorStore.search(top_k=5) → 语义相似度
            2. BM25Searcher.search(top_k=5) → 关键词匹配
            3. RRF 倒数秩融合
            4. MD5 去重
            5. 分数阈值过滤

        Args:
            query: 用户提问。
            top_k: 最终返回条数（默认 final_top_k）。
            course: 课程过滤。
            use_bm25: 是否启用 BM25（关闭时退化为纯向量检索）。

        Returns:
            [{"content": str, "filename": str, "course": str, "score": float, "source": str}, ...]
        """
        if top_k is None:
            top_k = settings.final_top_k

        filter_meta = {"course": course} if course else None

        # ── 1. 向量检索 ──
        vector_results = self.vector.search(
            query, top_k=settings.vector_top_k, filter_meta=filter_meta,
        )
        logger.debug("向量检索: {} 条", len(vector_results))

        # ── 2. BM25 检索 ──
        bm25_results: List[Dict] = []
        if use_bm25:
            bm25_results = self.bm25.search(query, top_k=settings.bm25_top_k)
            # BM25 结果不含 content，从 vector_results 中补齐
            self._enrich_bm25_content(bm25_results, vector_results)
            logger.debug("BM25 检索: {} 条", len(bm25_results))

        # ── 3. RRF 融合 ──
        merged = self._rrf_merge(vector_results, bm25_results)
        logger.debug("RRF 融合后: {} 条", len(merged))

        # ── 4. MD5 去重 ──
        merged = self._deduplicate(merged)

        # ── 5. 阈值过滤 ──
        if not merged or merged[0].get("rrf_score", 0) < settings.score_threshold:
            logger.info("检索分数低于阈值 {:.3f}，返回空", settings.score_threshold)
            return []

        return merged[:top_k]

    def search_raw(
        self,
        query: str,
        top_k: int = 15,
        course: str = "",
    ) -> List[Dict]:
        """检索不过滤（供 planner 使用，返回纯向量结果）。"""
        filter_meta = {"course": course} if course else None
        return self.vector.search(query, top_k=top_k, filter_meta=filter_meta)

    # ── 同步 ────────────────────────────────────────────

    def sync_chunks(self, chunks: List[Dict]) -> None:
        """文档索引后同步 BM25（增量追加）。"""
        self.bm25.add_chunks(chunks)

    def sync_delete(self, filename: str) -> None:
        """删除文档后同步 BM25。"""
        self.bm25.delete_by_source(filename)

    def save(self) -> None:
        """持久化 BM25。"""
        self.bm25.save()

    # ── 内部 ────────────────────────────────────────────

    def _rrf_merge(self, vector: List[Dict], bm25: List[Dict]) -> List[Dict]:
        """RRF 倒数秩融合。

        RRF score = Σ 1/(k + rank)
        其中 k = settings.rrf_k (默认 60)，rank 从 0 开始。
        """
        rrf_scores: Dict[str, float] = {}
        content_map: Dict[str, Dict] = {}

        for rank, item in enumerate(vector):
            key = item.get("content", "")[:80]  # 用内容前缀作 key
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (settings.rrf_k + rank)
            content_map[key] = item

        for rank, item in enumerate(bm25):
            key = item.get("content", "")[:80]
            if not key:  # BM25 可能没有 content
                key = item.get("_id", f"bm25_{rank}")
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (settings.rrf_k + rank)
            if key not in content_map:
                content_map[key] = item

        # 按 RRF 分数降序
        sorted_keys = sorted(rrf_scores, key=rrf_scores.get, reverse=True)  # type: ignore[arg-type]
        result: List[Dict] = []
        for key in sorted_keys:
            item = content_map.get(key, {})
            item["rrf_score"] = rrf_scores[key]
            result.append(item)

        return result

    @staticmethod
    def _deduplicate(items: List[Dict]) -> List[Dict]:
        """MD5 去重 — 相同内容的 chunk 只保留一个。"""
        seen: set[str] = set()
        unique: List[Dict] = []
        for item in items:
            content = item.get("content", "")
            digest = hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()
            if digest not in seen:
                seen.add(digest)
                unique.append(item)
        if len(items) != len(unique):
            logger.debug("MD5 去重: {} → {}", len(items), len(unique))
        return unique

    @staticmethod
    def _enrich_bm25_content(bm25_results: List[Dict], vector_results: List[Dict]) -> None:
        """BM25 结果不含 content，尝试从向量结果中按 filename 补齐。"""
        # 构建 filename → content 的简单映射
        content_by_file: Dict[str, List[Dict]] = {}
        for v in vector_results:
            fn = v.get("filename", "")
            content_by_file.setdefault(fn, []).append(v)

        for b in bm25_results:
            if b.get("content"):
                continue
            fn = b.get("filename", "")
            candidates = content_by_file.get(fn, [])
            if candidates:
                b["content"] = candidates[0].get("content", "")
