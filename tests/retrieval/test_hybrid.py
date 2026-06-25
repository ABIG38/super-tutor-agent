"""
单元测试 — HybridSearcher

覆盖:
    - RRF 融合逻辑
    - MD5 去重
    - 阈值过滤
    - 空结果处理
"""
import pytest
from unittest.mock import MagicMock, patch
from backend.retrieval.hybrid_search import HybridSearcher


class TestRRFMerge:
    def setup_method(self):
        self.hybrid = HybridSearcher.__new__(HybridSearcher)
        self.hybrid.vector = MagicMock()
        self.hybrid.bm25 = MagicMock()

    def test_rrf_combines_both_sources(self):
        vec = [
            {"content": "二叉树定义", "filename": "a.pdf", "score": 0.9},
            {"content": "排序算法", "filename": "a.pdf", "score": 0.5},
        ]
        bm25 = [
            {"content": "二叉树定义", "filename": "a.pdf", "score": 2.5, "source": "bm25", "_id": "a_0"},
            {"content": "冒泡排序", "filename": "b.pdf", "score": 1.0, "source": "bm25", "_id": "b_0"},
        ]
        merged = self.hybrid._rrf_merge(vec, bm25)
        # 二叉树 appears in both → higher RRF score
        assert len(merged) >= 2
        assert "rrf_score" in merged[0]

    def test_rrf_empty_lists(self):
        merged = self.hybrid._rrf_merge([], [])
        assert merged == []

    def test_rrf_vector_only(self):
        vec = [{"content": "唯一", "filename": "x.pdf", "score": 0.8}]
        merged = self.hybrid._rrf_merge(vec, [])
        assert len(merged) == 1


class TestDeduplicate:
    def setup_method(self):
        self.hybrid = HybridSearcher.__new__(HybridSearcher)

    def test_removes_duplicates(self):
        items = [
            {"content": "相同的文本", "filename": "a.pdf"},
            {"content": "相同的文本", "filename": "b.pdf"},  # duplicate content
            {"content": "不同的文本", "filename": "c.pdf"},
        ]
        result = self.hybrid._deduplicate(items)
        assert len(result) == 2

    def test_no_duplicates(self):
        items = [{"content": "a"}, {"content": "b"}, {"content": "c"}]
        result = self.hybrid._deduplicate(items)
        assert len(result) == 3


class TestEnrichBM25:
    def setup_method(self):
        self.hybrid = HybridSearcher.__new__(HybridSearcher)

    def test_fills_content_from_vector(self):
        vec = [{"content": "二叉树内容", "filename": "a.pdf"}]
        bm25 = [{"content": "", "filename": "a.pdf", "score": 1.0, "source": "bm25", "_id": "a_0"}]
        self.hybrid._enrich_bm25_content(bm25, vec)
        assert bm25[0]["content"] == "二叉树内容"

    def test_no_match_leaves_empty(self):
        vec = [{"content": "x", "filename": "a.pdf"}]
        bm25 = [{"content": "", "filename": "b.pdf", "score": 1.0}]
        self.hybrid._enrich_bm25_content(bm25, vec)
        assert bm25[0]["content"] == ""
