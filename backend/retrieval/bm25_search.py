"""
BM25 关键词检索引擎 — BM25Searcher

使用 rank-bm25 + jieba 分词实现中文友好的关键词检索。
索引通过 pickle 持久化，启动自动恢复。

对应 TECH_DESIGN.md §2.2。
"""
from __future__ import annotations

import pickle
import tempfile
from pathlib import Path
from typing import List, Dict

import jieba
from loguru import logger
from rank_bm25 import BM25Okapi

from backend.config import settings


class BM25Searcher:
    """BM25 关键词检索引擎。

    职责:
        - 全量重建 BM25 索引
        - 检索 Top-K 匹配
        - pickle 持久化（防断电的原子写入）
        - 延迟删除（维护 _deleted_source_ids 检索时过滤）
    """

    def __init__(self, corpus_path: Path | None = None) -> None:
        self._corpus_path = corpus_path or settings.bm25_corpus_path
        self._corpus: List[Dict] = []          # [{"id", "tokens", "meta"}]
        self._index: BM25Okapi | None = None    # 已构建的 BM25 索引
        self._deleted_ids: set[str] = set()     # 已删除但尚未重建的 chunk IDs

        # 启动时加载
        self._load()

    # ── 公开方法 ────────────────────────────────────────

    def add_chunks(self, chunks: List[Dict]) -> None:
        """增量追加 chunks 到 BM25 索引。

        Args:
            chunks: 格式同 VectorStore.add_chunks 的输入。
                   每个元素 {"content": str, "metadata": {filename, course, ...}}
        """
        if not chunks:
            return

        new_entries = 0
        tokenized_new: List[List[str]] = []

        for chunk in chunks:
            content = chunk.get("content", "")
            meta = chunk.get("metadata", {})
            chunk_id = self._make_id(meta)

            # 已存在的 chunk：如果是被标记删除的，则恢复（取消删除）
            existing = next((item for item in self._corpus if item["id"] == chunk_id), None)
            if existing is not None:
                if chunk_id in self._deleted_ids:
                    self._deleted_ids.discard(chunk_id)
                    logger.debug("BM25 恢复已删除 chunk: {}", chunk_id)
                continue

            tokens = self._tokenize(content)
            if not tokens:
                continue

            self._corpus.append({"id": chunk_id, "tokens": tokens, "meta": meta})
            tokenized_new.append(tokens)
            new_entries += 1

        if not tokenized_new:
            logger.debug("BM25 add_chunks: 无新增（全部已存在或已恢复）")
            return

        # 重建索引（rank_bm25 不支持增量，但 O(n) 级重建可接受）
        all_tokenized = [item["tokens"] for item in self._corpus if item["tokens"]]
        self._index = BM25Okapi(all_tokenized) if all_tokenized else None
        logger.info("BM25 增量追加: +{} chunks，总计 {} chunks", new_entries, len(self._corpus))

    def search(self, query: str, top_k: int | None = None) -> List[Dict]:
        """BM25 关键词检索。

        Args:
            query: 用户提问。
            top_k: 返回条数，默认 settings.bm25_top_k。

        Returns:
            [{"content": str, "filename": str, "course": str, "score": float, "source": "bm25"}, ...]
        """
        if top_k is None:
            top_k = settings.bm25_top_k

        if self._index is None:
            logger.debug("BM25 索引为空，返回空列表")
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = self._index.get_scores(query_tokens)
        if not scores.any():
            return []

        # 按分数降序取 top_k，同时过滤已删除的
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results: List[Dict] = []
        for idx, score in indexed:
            if len(results) >= top_k:
                break
            item = self._corpus[idx]
            if item["id"] in self._deleted_ids:
                continue
            meta = item["meta"]
            results.append({
                "content": "",  # BM25 索引不含原始文本，由调用方从 VectorStore 补充
                "filename": meta.get("filename", ""),
                "course": meta.get("course", ""),
                "score": float(score),
                "source": "bm25",
                "_id": item["id"],
            })

        return results

    def delete_by_source(self, filename: str) -> None:
        """标记某文件的所有 chunk 为已删除（延迟删除）。"""
        count = 0
        for item in self._corpus:
            if item["meta"].get("filename") == filename:
                self._deleted_ids.add(item["id"])
                count += 1
        logger.info("BM25 标记删除: {} ({} chunks)", filename, count)

    def save(self) -> None:
        """持久化分词后的语料到 pickle（原子写入防断电）。"""
        if not self._corpus:
            return
        # ★ 清理已删除项再持久化
        self._compact()
        # ... rest unchanged
        self._corpus_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # 临时文件 + 原子 rename（防断电损坏）
            fd, tmp = tempfile.mkstemp(
                suffix=".pkl", prefix="bm25_", dir=str(self._corpus_path.parent),
            )
            try:
                with open(fd, "wb") as f:
                    pickle.dump(self._corpus, f, protocol=pickle.HIGHEST_PROTOCOL)
                Path(tmp).replace(self._corpus_path)  # 原子操作
            except Exception:
                Path(tmp).unlink(missing_ok=True)
                raise
            logger.info("BM25 持久化完成: {} ({} chunks)", self._corpus_path, len(self._corpus))
        except Exception as e:
            logger.error("BM25 持久化失败: {}", e)

    # ── 内部 ────────────────────────────────────────────

    def _compact(self) -> None:
        """移除已标记删除的 corpus 条目并重建索引。"""
        if not self._deleted_ids:
            return
        before = len(self._corpus)
        self._corpus = [item for item in self._corpus if item["id"] not in self._deleted_ids]
        self._deleted_ids.clear()
        logger.info("BM25 compact: {} → {} chunks", before, len(self._corpus))

    def _load(self) -> None:
        """从 pickle 加载语料并重建索引。"""
        if not self._corpus_path.exists():
            logger.info("BM25 pickle 不存在，跳过加载")
            return
        try:
            with open(self._corpus_path, "rb") as f:
                self._corpus = pickle.load(f)
            # 重建索引
            tokenized = [item["tokens"] for item in self._corpus if item["tokens"]]
            if tokenized:
                self._index = BM25Okapi(tokenized)
            logger.info("BM25 从 pickle 恢复: {} 个文档", len(self._corpus))
        except Exception as e:
            logger.error("BM25 pickle 加载失败，将重建: {}", e)
            self._corpus = []
            self._index = None

    def _make_id(self, meta: Dict) -> str:
        """生成 chunk 唯一 ID。"""
        return f"{meta.get('filename', 'unknown')}_{meta.get('chunk_index', 0)}"

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """中文用 jieba 分词，英文用空格。"""
        # jieba 对中英混合文本效果更好
        tokens = jieba.lcut(text)
        # 过滤纯标点/空白
        return [t.strip() for t in tokens if t.strip() and not _is_punct(t)]


def _is_punct(token: str) -> bool:
    """判断 token 是否为纯标点符号。"""
    import unicodedata
    return all(unicodedata.category(c).startswith("P") or c.isspace() for c in token)
