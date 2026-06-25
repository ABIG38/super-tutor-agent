"""
ChromaDB 向量库 — 延迟加载 Embedding 模型。

修改: VectorStore 不再在 __init__ 时加载 embedding 模型，
而是首次 add_chunks / search / delete 时再加载。
避免应用启动时主线程卡死（~5-10秒模型加载时间）。
"""
from __future__ import annotations

import os
from typing import List, Dict, Optional
import uuid

import chromadb
from chromadb.utils import embedding_functions
from loguru import logger

from backend.config import settings


class VectorStore:
    """ChromaDB Vector Store Wrapper — 延迟加载 Embedding 模型。"""

    def __init__(self, db_dir: str | None = None):
        if settings.transformers_offline:
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_OFFLINE"] = "1"
        if settings.hf_home:
            os.environ["HF_HOME"] = settings.hf_home
        else:
            os.environ.setdefault("HF_HOME", str(settings.models_dir))

        if db_dir is None:
            db_dir = str(settings.chroma_dir)
        os.makedirs(db_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(path=db_dir)
        # ★ 延迟加载: 不在这里创建 embedding_fn/collection
        # 首次 add/search/delete 时才初始化
        self.embedding_fn = None
        self.collection = None
        logger.debug("VectorStore 初始化（延迟加载模式）")

    def _ensure_loaded(self) -> None:
        """★ 第一次使用时加载模型。"""
        if self.collection is not None:
            return
        logger.info("延迟加载 Embedding 模型: {} ...", settings.embedding_model)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model,
        )
        self.collection = self.client.get_or_create_collection(
            name="supertutor_chunks",
            embedding_function=self.embedding_fn,
        )
        logger.info("Embedding 模型加载完成")

    # ── 写入 ────────────────────────────────────

    def add_chunks(self, chunks: List[Dict]) -> None:
        self._ensure_loaded()
        if not chunks:
            return

        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            meta = chunk["metadata"]
            chunk_id = f"{meta.get('filename', 'unknown')}_{meta.get('chunk_index', 0)}_{uuid.uuid4().hex[:8]}"
            clean_meta = {}
            for k, v in meta.items():
                clean_meta[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
            ids.append(chunk_id)
            documents.append(chunk["content"])
            metadatas.append(clean_meta)

        batch_size = 100
        for i in range(0, len(ids), batch_size):
            self.collection.add(
                ids=ids[i:i + batch_size],
                documents=documents[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
            )
        logger.info("向量库写入 {} chunks", len(ids))

    # ── 检索 ────────────────────────────────────

    def search(
        self, query: str, top_k: int = 5, filter_meta: Optional[Dict] = None,
    ) -> List[Dict]:
        self._ensure_loaded()
        where = filter_meta if filter_meta else None

        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count()),
            where=where,
        )

        chunks = []
        if results and results['documents'] and results['documents'][0]:
            docs = results['documents'][0]
            metas = results['metadatas'][0] if results['metadatas'] else [{}] * len(docs)
            distances = results['distances'][0] if results['distances'] else [0.0] * len(docs)

            for doc, meta, dist in zip(docs, metas, distances):
                score = 1.0 / (1.0 + dist)
                chunks.append({
                    "content": doc,
                    "filename": meta.get("filename", ""),
                    "course": meta.get("course", ""),
                    "score": score,
                    "metadata": meta,
                })

        return chunks

    def search_raw(
        self, query: str, top_k: int = 15, filter_meta: Optional[Dict] = None,
    ) -> List[Dict]:
        return self.search(query, top_k, filter_meta)

    # ── 删除 ────────────────────────────────────

    def delete_by_source(self, filename: str) -> None:
        self._ensure_loaded()
        self.collection.delete(where={"filename": filename})

    def update_filename_metadata(self, old_filename: str, new_filename: str) -> None:
        self._ensure_loaded()
        try:
            existing = self.collection.get(where={"filename": old_filename})
            if not existing or not existing["ids"]:
                logger.warning("update_filename: 未找到匹配 {} 的 chunk", old_filename)
                return
            ids = existing["ids"]
            self.collection.update(
                ids=ids, metadatas=[{"filename": new_filename}] * len(ids),
            )
            logger.info("已更新 {} 个 chunk: {} → {}", len(ids), old_filename, new_filename)
        except Exception as e:
            logger.error("update_filename 失败: {}", e)
            raise

    # ── 启动恢复 ────────────────────────────────────

    def get_source_files(self) -> Dict[str, dict]:
        """★ 从 ChromaDB 恢复所有文档来源（用于重启后重建 _sources）。

        Returns:
            {filename: {"doc_type": str, "course": str}}
        """
        self._ensure_loaded()
        sources: Dict[str, dict] = {}
        offset = 0
        limit = 1000
        while True:
            batch = self.collection.get(limit=limit, offset=offset)
            if not batch or not batch["ids"]:
                break
            metadatas = batch["metadatas"] if batch["metadatas"] else []
            for meta in metadatas:
                fn = meta.get("filename", "")
                if fn and fn not in sources:
                    sources[fn] = {
                        "doc_type": meta.get("doc_type", "textbook"),
                        "course": meta.get("course", ""),
                    }
            offset += limit
        logger.info("从 ChromaDB 恢复 {} 个文档来源", len(sources))
        return sources
