from __future__ import annotations

import os
from typing import List, Dict, Optional
import uuid

import chromadb
from chromadb.utils import embedding_functions
from loguru import logger

from backend.config import settings

class VectorStore:
    """ChromaDB Vector Store Wrapper — 使用中文 BGE Embedding。"""
    
    def __init__(self, db_dir: str | None = None):
        # ★ A5：使用 settings 中的中文模型 + 配置离线模式
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

        # ★ 中文 Embedding: BAAI/bge-small-zh-v1.5
        logger.info("加载 Embedding 模型: {}", settings.embedding_model)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model,
        )
        self.collection = self.client.get_or_create_collection(
            name="supertutor_chunks",
            embedding_function=self.embedding_fn,
        )

    def add_chunks(self, chunks: List[Dict]) -> None:
        """Add chunks to ChromaDB."""
        if not chunks:
            return
            
        ids = []
        documents = []
        metadatas = []
        
        for chunk in chunks:
            # metadata dict: course, filename, chunk_index, etc.
            meta = chunk["metadata"]
            # Generate unique ID for each chunk
            chunk_id = f"{meta.get('filename', 'unknown')}_{meta.get('chunk_index', 0)}_{uuid.uuid4().hex[:8]}"
            
            # Ensure metadata values are scalar
            clean_meta = {}
            for k, v in meta.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_meta[k] = v
                else:
                    clean_meta[k] = str(v)
                    
            ids.append(chunk_id)
            documents.append(chunk["content"])
            metadatas.append(clean_meta)
            
        # Add in batches to prevent payload limits
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            self.collection.add(
                ids=ids[i:i+batch_size],
                documents=documents[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size]
            )
            
    def search(self, query: str, top_k: int = 5, filter_meta: Optional[Dict] = None) -> List[Dict]:
        """Search vector database."""
        where = filter_meta if filter_meta else None
        
        # Avoid crashing if collection is empty
        if self.collection.count() == 0:
            return []
            
        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count()),
            where=where
        )
        
        chunks = []
        if results and results['documents'] and results['documents'][0]:
            docs = results['documents'][0]
            metas = results['metadatas'][0] if results['metadatas'] else [{}] * len(docs)
            distances = results['distances'][0] if results['distances'] else [0.0] * len(docs)
            
            for doc, meta, dist in zip(docs, metas, distances):
                # distance ranges from 0 to 2 usually (for cosine), lower is better. 
                # convert to similarity score 0-1
                score = 1.0 / (1.0 + dist)
                chunks.append({
                    "content": doc,
                    "filename": meta.get("filename", ""),
                    "course": meta.get("course", ""),
                    "score": score,
                    "metadata": meta
                })
                
        return chunks

    def search_raw(self, query: str, top_k: int = 15, filter_meta: Optional[Dict] = None) -> List[Dict]:
        """Search without thresholding (for planner)."""
        return self.search(query, top_k, filter_meta)

    def delete_by_source(self, filename: str) -> None:
        """Delete all chunks originating from a specific file."""
        self.collection.delete(where={"filename": filename})

    def update_filename_metadata(self, old_filename: str, new_filename: str) -> None:
        """★ 修复 #8 配套：更新所有 chunk 的 filename metadata（重命名用）。

        通过 ChromaDB 的 get + update API 原地修改 metadata，
        不重建 embedding，避免重复计算。
        """
        try:
            existing = self.collection.get(where={"filename": old_filename})
            if not existing or not existing["ids"]:
                logger.warning("update_filename: 未找到匹配 {} 的 chunk", old_filename)
                return
            ids = existing["ids"]
            self.collection.update(ids=ids, metadatas=[{"filename": new_filename}] * len(ids))
            logger.info("已更新 {} 个 chunk 的 filename: {} → {}", len(ids), old_filename, new_filename)
        except Exception as e:
            logger.error("update_filename 失败: {}", e)
            raise
