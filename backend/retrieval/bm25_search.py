"""
BM25 关键词检索引擎 — 精简版。
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
    def __init__(self):
        """初始化 BM25 检索引擎，从磁盘恢复已有索引。"""
        self._corpus_path = Path(str(settings.storage_root_path) + "/index/bm25_corpus.pkl")
        self._corpus: List[Dict] = []
        self._index: BM25Okapi | None = None
        
        self._load()

    def _tokenize(self, text: str) -> List[str]:
        """混合分词：Jieba 词粒度 + 字符 Bigram，提升关键词匹配查全率。"""
        # 1. 基础分词
        base_tokens = [t for t in jieba.lcut(text) if len(t.strip()) > 0]
        # 2. Bigram 滑动窗口 (忽略空白)
        clean_text = text.replace(" ", "").replace("\n", "").replace("\t", "").replace("\r", "")
        bigrams = [clean_text[i:i+2] for i in range(len(clean_text)-1) if len(clean_text[i:i+2].strip()) == 2]
        return base_tokens + bigrams

    def add_chunks(self, chunks: List[Dict]) -> None:
        """增量追加 chunks。"""
        if not chunks:
            return
        new_tokens = []
        for c in chunks:
            content = c.get("content", "")
            meta = c.get("metadata", {})
            cid = f"{meta.get('filename','')}_{meta.get('chunk_index',0)}"
            if any(item["id"] == cid for item in self._corpus):
                continue
            tokens = self._tokenize(content)
            if tokens:
                self._corpus.append({"id": cid, "tokens": tokens, "meta": meta, "content": content})
                new_tokens.append(tokens)
        if not new_tokens:
            return
        all_t = [item["tokens"] for item in self._corpus if item["tokens"]]
        self._index = BM25Okapi(all_t) if all_t else None
        self.save()
        logger.info("BM25 索引: {} chunks", len(self._corpus))

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """关键词检索：用 BM25 算法对查询和语料库打分，返回 top_k 个匹配片段。"""
        if self._index is None:
            return []
        tokens = self._tokenize(query)
        if not tokens:
            return []
        scores = self._index.get_scores(tokens)
        if not scores.any():
            return []
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in indexed:
            if len(results) >= top_k:
                break
            item = self._corpus[idx]
            meta = item["meta"]
            results.append({
                "content": item.get("content", ""),
                "filename": meta.get("filename", ""),
                "course": meta.get("course", ""),
                "score": float(score),
                "source": "bm25",
            })
        return results

    def delete_by_source(self, filename: str) -> None:
        """删除指定文件的所有 chunks 并重建索引"""
        original_len = len(self._corpus)
        self._corpus = [item for item in self._corpus if item["meta"].get("filename") != filename]
        
        if len(self._corpus) < original_len:
            all_t = [item["tokens"] for item in self._corpus if item["tokens"]]
            self._index = BM25Okapi(all_t) if all_t else None
            self.save()
            logger.info("BM25 删除文件 '{}', 剩余 chunks: {}", filename, len(self._corpus))

    def save(self) -> None:
        """原子写入：先写临时文件再替换，防止写一半崩溃损坏索引。"""
        if not self._corpus:
            return
        self._corpus_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(suffix=".pkl", prefix="bm25_", dir=str(self._corpus_path.parent))
        try:
            with open(fd, "wb") as f:
                pickle.dump(self._corpus, f)
            Path(tmp).replace(self._corpus_path)
        except Exception:
            Path(tmp).unlink(missing_ok=True)

    def _load(self) -> None:
        """从磁盘加载 BM25 语料库并重建索引。"""
        if not self._corpus_path.exists():
            return
        try:
            self._corpus = pickle.loads(self._corpus_path.read_bytes())
            tokenized = [item["tokens"] for item in self._corpus if item["tokens"]]
            if tokenized:
                self._index = BM25Okapi(tokenized)
        except Exception:
            self._corpus = []
