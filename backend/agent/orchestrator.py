"""
Orchestrator — 精简版：只做上传→索引→检索→LLM 流式回答。
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Generator

from loguru import logger
from dotenv import load_dotenv

from backend.config import settings
from backend.document.parser import DocumentParser
from backend.document.splitter import chunk_document
from backend.retrieval.vector_store import VectorStore
from backend.retrieval.bm25_search import BM25Searcher
from backend.retrieval.reranker import BGEReranker
from backend.agent.router import IntentRouter
from backend.llm.client import CitationLLM, ChunkForLLM


class SuperTutorAgent:
    """单例 — 文档解析 + 向量检索 + LLM 流式问答。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """线程安全的单例模式，确保全局只有一个 agent 实例。"""
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化所有子模块（解析器、检索引擎、LLM客户端、路由器），仅执行一次。"""
        if hasattr(self, "initialized") and self.initialized:
            return
        load_dotenv()

        self.parser = DocumentParser()
        self.vector_store = VectorStore()
        self.bm25 = BM25Searcher()
        self.reranker = BGEReranker()

        api_key = settings.llm_api_key if settings.llm_api_key != "MISSING_KEY" else __import__("os").environ.get("OPENAI_API_KEY", "")
        self.llm = CitationLLM(
            api_key=api_key,
            api_base=settings.llm_api_base,
            model=settings.llm_model,
        )
        self.router = IntentRouter(self.llm)

        # 来源追踪 — 从 ChromaDB 恢复
        self._sources: Dict[str, dict] = {}
        self._restore_sources()
        self.initialized = True

    def _restore_sources(self) -> None:
        """从 ChromaDB 恢复所有已索引文档的来源信息（用于重启后重建 _sources）。"""
        try:
            for fn, info in self.vector_store.get_source_files().items():
                self._sources[fn] = {
                    "doc_type": info.get("doc_type", "textbook"),
                    "course": info.get("course", ""),
                    "display_name": info.get("display_name", fn),
                    "file_path": info.get("file_path", ""),
                }
        except Exception:
            pass

    # ── 文档获取 ──────────────────────────────────

    def rename_course_documents(self, old_name: str, new_name: str) -> None:
        """当课程重命名时，更新 sources 里的课程归属。
        此时无需更新 ChromaDB 底层的 course 字段，因为检索已改为按 filename 过滤。
        """
        for fn, info in self._sources.items():
            if info.get("course") == old_name:
                self._sources[fn]["course"] = new_name

    def ingest_document(self, file_path: str, course: str = "", progress_callback=None) -> Dict:
        """解析并切分文档，存入 ChromaDB 和 BM25。"""
        path = Path(file_path)
        fn = path.name
        if fn in self._sources:
            return {"ok": False, "reason": "duplicate", "filename": fn}
        try:
            if progress_callback: progress_callback("📄 正在解析文档...", 10)
            doc = self.parser.parse(file_path, course=course)
            if doc.scanned:
                return {"ok": False, "reason": "scanned_pdf", "filename": fn}
            
            if progress_callback: progress_callback("✂️ 正在切分文本块...", 30)
            abs_path = str(Path(file_path).resolve())
            chunks = chunk_document(doc.text, {"filename": doc.filename, "course": course, "display_name": doc.filename, "doc_type": doc.doc_type, "file_path": abs_path})
            
            if progress_callback: progress_callback("🗂️ 正在生成向量索引...", 50)
            self.vector_store.add_chunks(chunks)
            
            if progress_callback: progress_callback("🔍 正在生成 BM25 索引...", 80)
            self.bm25.add_chunks(chunks)  # ★ F-09: 同步 BM25
            
            self._sources[fn] = {"doc_type": doc.doc_type, "course": course, "file_path": abs_path, "display_name": doc.filename}
            
            if progress_callback: progress_callback("✅ 索引构建完成", 100)
            return {"ok": True, "chunk_count": len(chunks), "filename": fn}
        except (FileNotFoundError, ValueError, PermissionError) as e:
            return {"ok": False, "reason": str(e)[:100], "filename": fn}
        except Exception as e:
            logger.opt(exception=True).error("索引异常: {}", e)
            return {"ok": False, "reason": str(e)[:100], "filename": fn}

    def delete_document(self, filename: str) -> Dict:
        """删除指定文档及其向量和 BM25 索引。"""
        if filename not in self._sources:
            return {"ok": False, "reason": "not_found"}
        try:
            self.vector_store.delete_by_source(filename)
            self.bm25.delete_by_source(filename)
            self._sources.pop(filename, None)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    def rename_document(self, filename: str, new_display_name: str) -> Dict:
        """重命名文档在 ChromaDB 中的显示名称。"""
        if filename not in self._sources:
            return {"ok": False, "reason": "not_found"}
        try:
            self.vector_store.update_display_name_metadata(filename, new_display_name)
            self._sources[filename]["display_name"] = new_display_name
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    def get_documents(self, course: str = "") -> List[Dict]:
        """返回所有已索引文档列表（可按课程过滤）。"""
        return [{"filename": fn, **info} for fn, info in self._sources.items()
                if not course or info.get("course") == course]

    def preview_document(self, filename: str) -> Dict:
        """重新解析文档返回纯文本预览。"""
        if filename not in self._sources:
            return {"ok": False, "reason": "not_found"}
        fp = self._sources[filename].get("file_path", "")
        if not fp or not Path(fp).exists():
            return {"ok": False, "reason": "文件已不存在，请重新上传"}
        try:
            doc = self.parser.parse(fp, course=self._sources[filename].get("course", ""))
            return {"ok": True, "text": doc.text, "filename": doc.filename, "size": len(doc.text), "scanned": doc.scanned, "original_path": fp}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    def _rewrite_query(self, query: str, history: list) -> str:
        """指代消解：将用户简短追问补全为独立关键词（如 "它呢" → "B+树优点"）。"""
        if not history or len(query) > 15:
            return query
            
        recent = history[-4:]
        prompt = "根据以下对话历史，将用户的最新简短回复重写为一个独立、完整的搜索关键词短语，补全省略的代词和主语。如果无需补全，直接输出原话。禁止回答问题，禁止输出额外解释文字。\n\n对话历史：\n"
        for msg in recent:
            role = "用户" if msg.get("role") == "user" else "AI"
            content = msg.get("content", "")[:100]
            prompt += f"{role}: {content}\n"
        prompt += f"\n用户最新回复：{query}\n\n重写后的独立短语："
        
        try:
            logger.info(f"触发查询指代消解... 原问题: {query}")
            rewritten = self.llm.generate_with_citation(prompt, []).strip(' "\'\n\r')
            logger.info(f"重写结果: {rewritten}")
            if rewritten and len(rewritten) < 50:
                return rewritten
        except Exception as e:
            logger.error(f"查询重写失败: {e}")
        return query

    # ── 问答 ──────────────────────────────────────

    def _compress_history(self, history: list) -> list:
        """历史压缩：超过 8 轮对话时，将旧消息压缩为摘要以节省 token。"""
        if len(history) <= 8:
            return history
            
        recent_history = history[-8:]
        old_history = history[:-8]
        
        summary_prompt = "请用简短的一两句话，总结以下对话中用户的核心意图、提及的概念和关键结论，忽略寒暄语：\n\n"
        for msg in old_history:
            role = "用户" if msg.get("role") == "user" else "AI"
            content = msg.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            summary_prompt += f"{role}: {content}\n"
            
        try:
            logger.info("触发对话历史压缩...")
            summary = self.llm.generate_with_citation(summary_prompt, [])
            compressed_msg = {"role": "system", "content": f"【之前对话的摘要】{summary}"}
            return [compressed_msg] + recent_history
        except Exception as e:
            logger.error(f"历史压缩失败: {e}")
            return recent_history

    def ask(self, query: str, course: str = "", enable_web_search: bool = False, history: list = None) -> Generator[str, None, None]:
        """RAG 问答主流程：意图识别→指代消解→双路检索→RRF融合→Reranker精排→LLM流式回答。"""
        # 1. 意图识别 (Intent Routing)
        intent = self.router.classify_intent(query, history)
        
        # 2. 如果是闲聊，直接跳过所有检索步骤
        if intent == "chat":
            yield """<details><summary>🔍 检索诊断报告 (Diagnostics)</summary>
<div style='font-size: 12px; color: #666; margin-top: 8px;'>
- <b>🚦 路由通道</b>: <code>纯聊天 (Chat)</code> - 零 RAG 延迟直达<br>
</div>
</details>
"""
            for token in self.llm.generate_with_citation_stream(query, [], history=history):
                yield token
            return
            
        # 3. 如果是规划，引流到专业面板
        if intent == "plan":
            yield """<details><summary>🔍 检索诊断报告 (Diagnostics)</summary>
<div style='font-size: 12px; color: #666; margin-top: 8px;'>
- <b>🚦 路由通道</b>: <code>任务规划 (Plan)</code><br>
</div>
</details>
"""
            yield "我检测到您想要制定学习计划。为了提供更精准的排期，请点击界面侧边栏的 **【学习计划】** 按钮进入专业规划面板，输入您的天数和每天可用的时间段，我会在那里为您生成专属复习路线！"
            return
            
        # 4. 否则走标准 RAG 流程
        search_query = self._rewrite_query(query, history) if history else query
        
        if history and len(history) > 8:
            history = self._compress_history(history)
        if not self._sources and not enable_web_search:
            yield "知识库为空，请先上传文档。"
            return
            
        course_files = [fn for fn, info in self._sources.items() if not course or info.get("course") == course]
        if course and not course_files and not enable_web_search:
            yield "当前课程知识库为空，请先上传文档。"
            return
            
        filter_meta = {"filename": {"$in": course_files}} if course_files else None
        
        # ★ F-09: 混合检索 — 向量 + BM25
        vec_chunks = self.vector_store.search(search_query, top_k=10, filter_meta=filter_meta)
        
        # BM25 不支持底层过滤，需取更多结果后在内存中过滤
        all_bm25 = self.bm25.search(search_query, top_k=30)
        if course_files:
            bm25_chunks = [c for c in all_bm25 if c.get("metadata", {}).get("filename") in course_files][:10]
        else:
            bm25_chunks = all_bm25[:10]
        # ★ RRF (Reciprocal Rank Fusion) 融合
        k = 60
        rrf_scores = {}
        chunk_map = {}

        def add_to_rrf(chunks):
            for rank, c in enumerate(chunks):
                # 用 content 的前 80 个字符加上 filename 作为唯一摘要键去重
                key = f"{c.get('filename', '')}_{c.get('content', '')[:80]}"
                if not key.strip("_"):
                    continue
                if key not in chunk_map:
                    chunk_map[key] = c
                    rrf_scores[key] = 0.0
                rrf_scores[key] += 1.0 / (k + rank + 1)

        add_to_rrf(vec_chunks)
        add_to_rrf(bm25_chunks)

        # 按照 RRF 分数排序
        sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        all_chunks = [chunk_map[k_idx] for k_idx in sorted_keys]

        # ★ 精排 Reranker
        rerank_candidates = all_chunks[:15]
        if hasattr(self, 'reranker') and rerank_candidates:
            all_chunks = self.reranker.rerank(search_query, rerank_candidates, top_k=5)
            
        # ★ Diagnostics 诊断报告
        semantic_count = len(vec_chunks)
        keyword_count = len(bm25_chunks)
        diag_html = f"""<details><summary>🔍 检索诊断报告 (Diagnostics)</summary>
<div style='font-size: 12px; color: #666; margin-top: 8px;'>
- <b>🚦 路由通道</b>: <code>知识检索 (RAG)</code><br>
- <b>指代消解</b>: <code>{query}</code> → <code>{search_query}</code><br>
- <b>语义召回 (FAISS)</b>: {semantic_count} 段<br>
- <b>关键词召回 (BM25)</b>: {keyword_count} 段<br>
- <b>精排通过 (Reranker)</b>: {len(all_chunks)} 段<br>
</div>
</details>
"""
        yield diag_html

        # 追加网络搜索结果（直接放置在头部或尾部，避免 RRF 削弱权重）
        if enable_web_search:
            from backend.retrieval.web_search import search_web
            web_chunks = search_web(search_query, max_results=3)
            # 放到开头，确保大模型优先注意到最新的网络信息
            all_chunks = web_chunks + all_chunks
            
        # 将当前活跃的计划注入到 chunk 中，模拟检索到的特殊上下文
        active_plan_info = self.get_active_plan_daily_content()
        if active_plan_info:
            all_chunks.insert(0, {
                "content": f"【当前计划进度】用户今天处于第 {active_plan_info['current_day']} 天，今天的任务是：\n{active_plan_info['content']}",
                "filename": "当前学习计划",
                "course": course,
                "score": 1.0
            })

        llm_chunks = [
            ChunkForLLM(content=c.get("content",""), filename=c.get("filename",""), course=c.get("course",""), score=c.get("score",0))
            for c in all_chunks[:12]
        ]
        for token in self.llm.generate_with_citation_stream(query, llm_chunks, history=history):
            yield token

    def cancel_stream(self) -> None:
        """取消当前流式生成。"""
        self.llm.cancel_stream()

    # ── 计划生成 ──────────────────────────────────

    PLANS_DIR = settings.storage_root_path / "index" / "plans"

    def generate_plan_stream(self, days: int, hours: int, start_chapter: str = "", end_chapter: str = "", course: str = "") -> Generator[str, None, None]:
        """流式生成学习计划。"""
        textbooks = [d["filename"] for d in self.get_documents(course) if d.get("doc_type") == "textbook"]
        if not textbooks:
            yield "请先上传含目录的教材。"
            return

        if len(textbooks) == 1:
            filter_meta = {"filename": textbooks[0]}
        else:
            filter_meta = {"filename": {"$in": textbooks}}

        chunks = self.vector_store.search("目录 内容 结构 重点", top_k=15, filter_meta=filter_meta)
        if not chunks:
            chunks = self.vector_store.search("", top_k=10, filter_meta=filter_meta)
        if not chunks:
            yield "未能从教材中提取到内容，无法生成计划。"
            return

        llm_chunks = [
            ChunkForLLM(content=c.get("content",""), filename=c.get("filename",""), course=c.get("course",""))
            for c in chunks
        ]

        today_str = datetime.now().strftime("%Y-%m-%d")
        prompt = (
            f"你是一位学习规划助手。今天是 {today_str}。\n"
            f"请根据上方<context>提供的教材内容，"
            f"为用户制定一份 {days} 天的学习/阅读计划，每天学习 {hours} 小时。\n\n"
        )
        if start_chapter and end_chapter:
            prompt += f"【重要指示】用户要求计划范围从“{start_chapter}”开始，到“{end_chapter}”结束，请严格在此范围内安排学习计划。\n\n"
        elif start_chapter:
            prompt += f"【重要指示】用户要求从“{start_chapter}”开始复习，请从匹配到该章节的内容开始向后安排计划。\n\n"
        elif end_chapter:
            prompt += f"【重要指示】用户要求复习到“{end_chapter}”为止，请合理安排在这个章节之前的内容。\n\n"

        prompt += (
            "要求：\n"
            f"1. 严格使用 `### 第X天 (YYYY-MM-DD)` 作为每天的标题格式，例如第一天是 `### 第1天 ({today_str})`，第二天顺延\n"
            "2. 按天拆分，每天安排具体内容\n"
            "3. 如果资料中有明确章节/模块结构，按结构拆分\n"
            "4. 如果资料是项目文档/非教材，按主题或知识点合理分配天数\n"
            "5. Markdown 格式\n"
            "6. 如果内容不足以覆盖所有天数，说明是按什么依据排期的"
        )

        try:
            for token in self.llm.generate_with_citation_stream(query=prompt, chunks=llm_chunks, timeout=60):
                yield token
        except Exception as e:
            logger.error("流式计划生成失败: {}", e)
            yield f"\n计划生成失败：{e}"

    def save_active_plan(self, content: str, days: int, hours: int) -> str:
        """保存计划并设为激活状态"""
        return self._save_plan(content, days, hours)

    def _save_plan(self, content: str, days: int, hours: int) -> str:
        """保存计划到 knowledge_base/index/plans/。"""
        from datetime import datetime
        import json
        self.PLANS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{days}d_{hours}h.md"
        path = self.PLANS_DIR / filename
        path.write_text(f"# 学习计划 ({days}天, 每天{hours}小时)\n\n{content}", encoding="utf-8")
        logger.info("计划已保存: {}", path)
        
        # 将新生成的计划设为激活计划
        active_path = self.PLANS_DIR / "active_plan.json"
        active_path.write_text(json.dumps({
            "plan_filename": filename,
            "total_days": days,
            "current_day": 1
        }), encoding="utf-8")
        
        return str(path)

    def get_plans(self) -> List[Dict]:
        """返回已保存的计划列表。"""
        from datetime import datetime
        if not self.PLANS_DIR.exists():
            return []
        plans = []
        for f in sorted(self.PLANS_DIR.glob("*.md"), reverse=True):
            size = len(f.read_text("utf-8"))
            name = f.stem  # plan_20260109_120000_30d_2h
            d_time = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            plans.append({
                "filename": f.name,
                "display_name": name,
                "file_path": str(f),
                "created_at": d_time
            })
        return plans

    # ── 计划进度追踪 ──────────────────────────────

    def clear_active_plan(self):
        """清除当前活跃的学习计划。"""
        active_path = self.PLANS_DIR / "active_plan.json"
        if active_path.exists():
            active_path.unlink()
            
    def get_active_plan_info(self) -> Optional[Dict]:
        """获取当前活跃的计划进度信息。"""
        import json
        active_path = self.PLANS_DIR / "active_plan.json"
        if not active_path.exists():
            return None
        try:
            return json.loads(active_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def update_active_plan_progress(self, current_day: int) -> bool:
        """更新当前活跃计划的打卡进度。"""
        import json
        info = self.get_active_plan_info()
        if not info:
            return False
        info["current_day"] = current_day
        active_path = self.PLANS_DIR / "active_plan.json"
        active_path.write_text(json.dumps(info), encoding="utf-8")
        return True

    def get_active_plan_daily_content(self) -> Optional[Dict]:
        """提取当前激活计划中，今日的具体内容。"""
        info = self.get_active_plan_info()
        if not info: return None
        
        plan_path = self.PLANS_DIR / info["plan_filename"]
        if not plan_path.exists(): return None
        
        text = plan_path.read_text(encoding="utf-8")
        import re
        # 匹配 ### 第X天 到下一个 ### 第Y天 之间的内容
        day = info["current_day"]
        pattern = re.compile(rf"(### 第{day}天.*?)(?=### 第\d+天|$)", re.DOTALL)
        match = pattern.search(text)
        if match:
            return {"current_day": day, "content": match.group(1).strip()}
        return None

    def get_plan_content(self, filename: str) -> str:
        """读取计划文件内容。"""
        path = self.PLANS_DIR / filename
        if path.exists():
            return path.read_text("utf-8")
        return ""
