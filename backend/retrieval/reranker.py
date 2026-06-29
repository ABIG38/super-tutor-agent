import os
import requests
from typing import List, Dict
from loguru import logger

class BGEReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        """初始化 Reranker，从环境变量读取 API Key，无 Key 则优雅降级。"""
        self.model_name = model_name
        self.api_url = "https://api.siliconflow.cn/v1/rerank"
        # 从环境变量获取 API Key，如果没有则降级
        self.api_key = os.environ.get("SILICONFLOW_API_KEY", "")

    def rerank(self, query: str, chunks: List[Dict], top_k: int = 3) -> List[Dict]:
        """
        通过云端 API 对 chunks 进行重排序。
        返回重排后的 top_k chunks，并在 chunk 中附加 'rerank_score'。
        """
        if not chunks:
            return []
            
        if not self.api_key:
            logger.warning("未配置 SILICONFLOW_API_KEY，跳过重排序，直接返回原文。")
            return chunks[:top_k]
            
        try:
            texts = [c.get("content", "") for c in chunks]
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model_name,
                "query": query,
                "documents": texts,
                "top_n": top_k
            }
            
            logger.info(f"正在请求云端 Reranker: {self.model_name}")
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            # results 包含 index 和 relevance_score
            reranked_chunks = []
            for item in results:
                idx = item.get("index")
                score = item.get("relevance_score", 0.0)
                if idx is not None and idx < len(chunks):
                    chunk = chunks[idx].copy()
                    chunk["rerank_score"] = float(score)
                    reranked_chunks.append(chunk)
            
            # 防御：如果云端返回数量不足，用原数据补齐
            if len(reranked_chunks) < top_k and len(chunks) > len(reranked_chunks):
                seen_indices = {item.get("index") for item in results}
                for i, chunk in enumerate(chunks):
                    if i not in seen_indices:
                        c = chunk.copy()
                        c["rerank_score"] = -999.0
                        reranked_chunks.append(c)
                        if len(reranked_chunks) >= top_k:
                            break
                            
            logger.info("云端 Reranker 请求成功。")
            return reranked_chunks[:top_k]
            
        except Exception as e:
            logger.error(f"云端重排序失败: {e}")
            # 优雅降级，直接返回原顺序的前 K 个
            return chunks[:top_k]
