"""
单元测试 — BM25Searcher

覆盖:
    - 索引构建 + 检索
    - 增量追加
    - 删除标记 + 恢复
    - pickle 持久化
    - 空索引查询
"""
import pytest
import tempfile
from pathlib import Path
from backend.retrieval.bm25_search import BM25Searcher


CHUNKS_A = [
    {"content": "二叉树是计算机科学中的重要数据结构", "metadata": {"filename": "ds.pdf", "chunk_index": 0}},
    {"content": "快速排序的平均时间复杂度为 O(n log n)", "metadata": {"filename": "ds.pdf", "chunk_index": 1}},
    {"content": "链表是一种线性数据结构", "metadata": {"filename": "ds.pdf", "chunk_index": 2}},
]
CHUNKS_B = [
    {"content": "冒泡排序是一种简单的排序算法", "metadata": {"filename": "algo.pdf", "chunk_index": 0}},
]


class TestBM25Core:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.corpus_path = tmp_path / "bm25_test.pkl"
        self.bm25 = BM25Searcher(corpus_path=self.corpus_path)

    def test_add_and_search(self):
        self.bm25.add_chunks(CHUNKS_A)
        results = self.bm25.search("二叉树", top_k=5)
        assert len(results) >= 1

    def test_incremental_add(self):
        self.bm25.add_chunks(CHUNKS_A)
        assert len(self.bm25._corpus) == 3
        self.bm25.add_chunks(CHUNKS_B)
        assert len(self.bm25._corpus) == 4

    def test_duplicate_skip(self):
        self.bm25.add_chunks(CHUNKS_A)
        before = len(self.bm25._corpus)
        self.bm25.add_chunks(CHUNKS_A)  # same chunks
        assert len(self.bm25._corpus) == before

    def test_delete_and_readd(self):
        self.bm25.add_chunks(CHUNKS_A)
        self.bm25.delete_by_source("ds.pdf")
        assert len(self.bm25._deleted_ids) == 3
        # re-add should recover
        self.bm25.add_chunks(CHUNKS_A)
        assert len(self.bm25._deleted_ids) == 0

    def test_empty_search(self):
        results = self.bm25.search("anything")
        assert results == []

    def test_persistence(self):
        self.bm25.add_chunks(CHUNKS_A)
        self.bm25.save()
        assert self.corpus_path.exists()

        # reload
        bm25_2 = BM25Searcher(corpus_path=self.corpus_path)
        assert len(bm25_2._corpus) == 3
        results = bm25_2.search("二叉树")
        assert len(results) >= 1

    def test_compact_removes_deleted(self):
        self.bm25.add_chunks(CHUNKS_A)
        self.bm25.add_chunks(CHUNKS_B)
        self.bm25.delete_by_source("ds.pdf")
        assert len(self.bm25._deleted_ids) == 3
        self.bm25._compact()
        assert len(self.bm25._deleted_ids) == 0
        assert len(self.bm25._corpus) == 1  # only algo.pdf remains
