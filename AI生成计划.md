# Super-Tutor 项目 AI 生成计划（V2 · PySide6 桌面版）

> **用途**：将此文档逐步喂给 Cursor / Windsurf / Claude Code 等 AI IDE，让 AI 按步骤生成项目代码。
> **核心变更**：第 9 轮从 Streamlit 改为 PySide6 原生桌面窗口。

---

## 📋 总览

| 生成轮次 | 模块 | 文件数 | 依赖 |
|----------|------|--------|------|
| 第 1 轮 | 项目脚手架 + 配置 | 4 | 无 |
| 第 2 轮 | 文档解析引擎 | 3 | 1 |
| 第 3 轮 | 向量存储 + 索引 | 2 | 1 |
| 第 4 轮 | BM25 关键词检索 | 2 | 1 |
| 第 5 轮 | LLM 客户端 + 溯源 System Prompt | 2 | 1 |
| 第 6 轮 | Agent 编排层（核心） | 2 | 2,3,4,5 |
| 第 7 轮 | 规划模块 | 1 | 2,5,6 |
| 第 8 轮 | **PySide6 桌面应用**（替代 Streamlit） | 1 | 6,7 |
| 第 9 轮 | main.py 启动入口 | 1 | 8 |
| 第 10 轮 | 单元测试 | 2 | 2,3,4,5 |

---

## 第 1 轮：项目脚手架 + 配置

### 对 AI IDE 的 Prompt

```
在 D:\super-turtor 目录下创建项目骨架，包括目录和以下文件：

═══════════════════════════════════════
文件 1：requirements.txt
═══════════════════════════════════════
langchain>=0.3.0
langchain-core>=0.3.0
openai>=1.50.0
PyMuPDF>=1.24.0
python-docx>=1.1.0
markdown-it-py>=3.0.0
chromadb>=0.5.0
sentence-transformers>=3.0.0
rank-bm25>=0.2.2
PySide6>=6.7.0
python-dotenv>=1.0.0
tiktoken>=0.7.0
jieba>=0.42.1

═══════════════════════════════════════
文件 2：.env.example
═══════════════════════════════════════
LLM_API_KEY=your-api-key-here
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4-turbo
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
VECTOR_DB_PATH=./knowledge_base/index/chroma
DOCUMENT_STORAGE_PATH=./knowledge_base/raw
CHUNK_SIZE=800
CHUNK_OVERLAP=150
VECTOR_TOP_K=5
BM25_TOP_K=5

═══════════════════════════════════════
文件 3：backend/__init__.py
═══════════════════════════════════════
只有一行文档字符串："\"\"\"Super-Tutor Backend Package\"\"\""

═══════════════════════════════════════
文件 4：backend/config.py
═══════════════════════════════════════
用 python-dotenv 从项目根目录加载 .env 文件。
用 pathlib.Path 定位项目根目录（__file__ 往上两级）。

导出的变量：
  LLM_API_KEY       = os.getenv("LLM_API_KEY")
  LLM_API_BASE      = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
  LLM_MODEL         = os.getenv("LLM_MODEL", "gpt-4-turbo")
  EMBEDDING_MODEL   = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
  VECTOR_DB_PATH    = os.getenv(..., str(PROJECT_ROOT / "knowledge_base/index/chroma"))
  DOCUMENT_STORAGE_PATH = os.getenv(..., str(PROJECT_ROOT / "knowledge_base/raw"))
  CHUNK_SIZE        = int(os.getenv("CHUNK_SIZE", "800"))
  CHUNK_OVERLAP     = int(os.getenv("CHUNK_OVERLAP", "150"))
  VECTOR_TOP_K      = int(os.getenv("VECTOR_TOP_K", "5"))
  BM25_TOP_K        = int(os.getenv("BM25_TOP_K", "5"))

额外逻辑：
  在模块加载时用 Path(VECTOR_DB_PATH).mkdir(parents=True, exist_ok=True)
  和 Path(DOCUMENT_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
  确保路径存在。

═══════════════════════════════════════
同时创建 8 个空子目录（用 Python os.makedirs 或在文件系统直接创建）：
═══════════════════════════════════════
knowledge_base/raw/
knowledge_base/index/
tests/
frontend/
backend/document/
backend/retrieval/
backend/llm/
backend/agent/
```

### 期望输出
- `requirements.txt`（含 PySide6、jieba，不含 streamlit、langgraph）
- `.env.example`
- `backend/__init__.py`
- `backend/config.py`
- 8 个空子目录

### 验证方式
```bash
pip install -r requirements.txt --dry-run
python -c "from backend.config import LLM_MODEL, VECTOR_DB_PATH; print(LLM_MODEL); print(VECTOR_DB_PATH)"
```

---

## 第 2 轮：文档解析引擎

### 对 AI IDE 的 Prompt

```
在 D:\super-turtor\backend\document 目录下创建三个文件。

═══════════════════════════════════════
文件 1：__init__.py
═══════════════════════════════════════
导出以下符号：
  from .parser import DocumentParser
  from .splitter import chunk_document

═══════════════════════════════════════
文件 2：parser.py
═══════════════════════════════════════
class DocumentParser:
    """
    根据文件扩展名自动选择解析方式。
    所有方法都是静态方法，无需实例化。
    """

    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.md', '.txt', '.markdown'}

    @staticmethod
    def parse(file_path: str) -> dict:
        """
        返回 {"text": str, "metadata": dict}
        metadata = {"filename": "xxx.pdf", "page_count": 120, "size_bytes": 2048000, "extension": ".pdf"}

        根据扩展名分派：
          .pdf  → _parse_pdf()    用 fitz.open() 逐页 get_text()
          .docx → _parse_docx()   用 Document() 逐段提取
          .md / .markdown → _parse_text() 直接 read_text()
          .txt → _parse_text()

        不支持的扩展名抛 ValueError(f"不支持的文件格式: {ext}")
        文件不存在抛 FileNotFoundError
        PDF 打开失败抛 RuntimeError
    """

    @staticmethod
    def _parse_pdf(path: str) -> dict: ...
    @staticmethod
    def _parse_docx(path: str) -> dict: ...
    @staticmethod
    def _parse_text(path: str) -> dict: ...

═══════════════════════════════════════
文件 3：splitter.py
═══════════════════════════════════════
from backend.config import CHUNK_SIZE, CHUNK_OVERLAP
from langchain.text_splitter import RecursiveCharacterTextSplitter

def chunk_document(text: str, metadata: dict) -> list[dict]:
    """
    输入：纯文本 + 文档级 metadata（含 filename, page_count 等）
    输出：list 的 chunk dict

    每个 chunk dict 格式：
    {
        "content": "这是第一个切分块的文本内容...",
        "metadata": {
            "source": "数据结构.pdf",      # 来自 metadata["filename"]
            "chunk_index": 0,              # 0-based 序号
            "page_count": 120,             # 透传原始页码
            "char_start": 0,               # 在原文中的起始字符位置
        }
    }

    使用 RecursiveCharacterTextSplitter：
      separators=["\n## ", "\n### ", "\n# ", "\n\n", "\n", ". ", "。", " "]
      chunk_size=CHUNK_SIZE
      chunk_overlap=CHUNK_OVERLAP
      length_function=len  （按字符数，不用 tokenizer）

    用 splitter.split_text(text) 先切出纯文本片段，
    再逐片包装成带 metadata 的 dict。
    """
```

### 期望输出
- `backend/document/__init__.py`
- `backend/document/parser.py`
- `backend/document/splitter.py`

### 验证方式
```python
from backend.document import DocumentParser, chunk_document
# 准备一个临时 txt 做测试：
import tempfile, pathlib
f = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8")
f.write("# 第一章\n\n这是第一段内容。\n\n## 第一节\n\n这是第二段内容。")
f.close()
result = DocumentParser.parse(f.name)
assert "text" in result
assert result["metadata"]["filename"].endswith(".txt")
chunks = chunk_document(result["text"], result["metadata"])
assert len(chunks) >= 1
assert "content" in chunks[0]
assert "source" in chunks[0]["metadata"]
pathlib.Path(f.name).unlink()
print("✅ 验证通过")
```

---

## 第 3 轮：向量存储 + 索引

### 对 AI IDE 的 Prompt

```
在 D:\super-turtor\backend\retrieval 目录下创建两个文件。

═══════════════════════════════════════
文件 1：__init__.py
═══════════════════════════════════════
导出：
  from .vector_store import VectorStore

═══════════════════════════════════════
文件 2：vector_store.py
═══════════════════════════════════════
from backend.config import VECTOR_DB_PATH, VECTOR_TOP_K, EMBEDDING_MODEL
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

class VectorStore:
    """
    封装 ChromaDB 向量数据库操作。
    使用本地 sentence-transformers 模型做 embedding。
    """

    def __init__(self, persist_dir: str = VECTOR_DB_PATH):
        """
        初始化 embedding 函数：HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        初始化 Chroma 客户端：
          Chroma(persist_directory=persist_dir, embedding_function=embedding_fn,
                 collection_name="super_tutor_docs")
        注意：如果目录下已有持久化数据，Chroma 会自动加载。
        """
        self.persist_dir = persist_dir
        self.embedding_fn = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        self.collection = Chroma(
            persist_directory=persist_dir,
            embedding_function=self.embedding_fn,
            collection_name="super_tutor_docs"
        )

    def add_chunks(self, chunks: list[dict]) -> int:
        """
        将 chunk 列表写入 ChromaDB。
        每个 chunk 的 "content" 作为文本，
        "metadata" 作为 Chroma metadata。

        用 self.collection.add_texts(
            texts=[c["content"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
            ids=[f"{c['metadata']['source']}_{c['metadata']['chunk_index']}" for c in chunks]
        )
        返回写入的条数。
        """

    def search(self, query: str, top_k: int = VECTOR_TOP_K) -> list[dict]:
        """
        向量检索。
        用 self.collection.similarity_search_with_score(query, k=top_k)
        返回 list of dict:
        [{"content": "...", "metadata": {...}, "score": 0.92}, ...]
        score 是距离值（越小越相似），统一转为 0-1 的相似度：
          similarity = 1.0 / (1.0 + distance)
        """

    def count(self) -> int:
        """返回知识库中总 chunk 数"""
        return self.collection._collection.count()

    def delete_all(self) -> None:
        """删除 collection 中所有数据"""
        ids = self.collection.get()["ids"]
        if ids:
            self.collection.delete(ids=ids)

    def get_source_files(self) -> list[str]:
        """返回所有唯一的 source 文件名"""
        all_meta = self.collection.get()["metadatas"]
        sources = set()
        for m in all_meta:
            if "source" in m:
                sources.add(m["source"])
        return sorted(sources)
```

### 期望输出
- `backend/retrieval/__init__.py`
- `backend/retrieval/vector_store.py`

### 验证方式
```python
from backend.retrieval.vector_store import VectorStore
import tempfile, pathlib
d = tempfile.mkdtemp()
vs = VectorStore(persist_dir=d)
vs.add_chunks([
    {"content": "快速排序的平均时间复杂度为 O(n log n)", 
     "metadata": {"source": "ds.pdf", "chunk_index": 0}}
])
results = vs.search("时间复杂度", top_k=1)
assert len(results) == 1
assert "O(n log n)" in results[0]["content"]
vs.delete_all()
print("✅ 向量检索验证通过")
```

---

## 第 4 轮：BM25 关键词检索引擎

### 对 AI IDE 的 Prompt

```
═══════════════════════════════════════════════════════════════
在 D:\super-turtor\backend\retrieval\bm25_search.py 创建：
═══════════════════════════════════════════════════════════════

from backend.config import BM25_TOP_K
from rank_bm25 import BM25Okapi
import jieba
import re

class BM25Searcher:
    """
    BM25 关键词搜索引擎。
    内部维护一个语料列表和对应的 metadata 列表。
    每次 add_chunks 都会重新构建整个 BM25 索引
    （因为 BM25 的 TF-IDF 矩阵依赖全局词频统计，无法增量更新）。
    """

    def __init__(self):
        self._corpus: list[list[str]] = []     # 分词后的 token 列表
        self._metadata: list[dict] = []
        self._bm25: BM25Okapi | None = None

    def add_chunks(self, chunks: list[dict]) -> int:
        """
        将新 chunks 追加到 _corpus 和 _metadata，然后全量重建 BM25 索引。
        分词逻辑用 _tokenize()。
        返回当前语料总条数。
        """

    def search(self, query: str, top_k: int = BM25_TOP_K) -> list[dict]:
        """
        对 query 分词后，用 self._bm25.get_scores() 打分。
        按分数降序取 top_k。
        返回 [{"content": str, "metadata": dict, "score": float}, ...]
        """

    def _tokenize(self, text: str) -> list[str]:
        """
        混合中英文分词：
        - 先用正则 [\\u4e00-\\u9fff]+ 提取中文片段，用 jieba.lcut() 分词
        - 其他部分（英文/数字）用 re.findall(r'[a-zA-Z0-9]+', text) 提取
        - 合并，转小写，去重
        返回 token 列表。
        """

    def count(self) -> int:
        """语料条数"""
        return len(self._corpus)
```

### 期望输出
- `backend/retrieval/bm25_search.py`

### 验证方式
```python
from backend.retrieval.bm25_search import BM25Searcher
b = BM25Searcher()
b.add_chunks([
    {"content": "线性表是数据结构中最基本的结构", "metadata": {"source": "ds.pdf", "chunk_index": 0}},
    {"content": "快速排序使用分治策略", "metadata": {"source": "ds.pdf", "chunk_index": 1}},
])
results = b.search("线性表", top_k=1)
assert len(results) == 1
assert "线性表" in results[0]["content"]
print("✅ BM25 检索验证通过")
```

---

## 第 5 轮：LLM 客户端 + 溯源 System Prompt

### 对 AI IDE 的 Prompt

```
在 D:\super-turtor\backend\llm 目录下创建两个文件。

═══════════════════════════════════════
文件 1：__init__.py
═══════════════════════════════════════
导出：
  from .client import CitationLLM, CITATION_SYSTEM_PROMPT

═══════════════════════════════════════
文件 2：client.py
═══════════════════════════════════════

from backend.config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL
from openai import OpenAI

# ═══ 硬编码溯源 System Prompt ═══
CITATION_SYSTEM_PROMPT = (
    "你是一个严谨的学术助手。请严格遵循以下规则：\n"
    "1. 优先使用下方 <context> 标签内的检索内容回答问题。\n"
    "2. 在回答中，必须用 [来源文档名] 或 [来源文档名：章节名] 标注信息来源。\n"
    "3. 如果 <context> 中的信息不足以回答问题，你可以使用自身知识库补充，"
    "但必须在补充内容前明确声明：'以下内容基于通用知识补充，不在上传文档中：'\n"
    "4. 绝对禁止编造来源或引用不存在的文档。\n"
    "5. 回答末尾列出本次使用的所有来源文档。"
)

class CitationLLM:
    """
    封装 OpenAI 兼容的 LLM 调用，强制溯源输出。
    """

    def __init__(self, model: str = LLM_MODEL, api_key: str = LLM_API_KEY,
                 base_url: str = LLM_API_BASE):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate_with_citation(self, query: str, retrieved_chunks: list[dict]) -> str:
        """
        参数：
          query: 用户提问
          retrieved_chunks: 混合检索结果，每个 dict 含 content, metadata

        流程：
          1. 调用 _format_context(chunks) 构造 <context> 块
          2. 调用 _build_messages(query, context) 构造 messages
          3. self.client.chat.completions.create(model, messages, temperature=0.3)
          4. 返回 response.choices[0].message.content
          5. 异常时返回错误信息字符串
        """

    def _format_context(self, chunks: list[dict]) -> str:
        """
        拼接格式：
        <context>
        [来源: {source}]
        {content}

        [来源: {source}]
        {content}
        </context>
        每条用 --- 分隔。
        """
        lines = ["<context>"]
        for c in chunks:
            source = c["metadata"].get("source", "未知")
            lines.append(f"[来源: {source}]")
            lines.append(c["content"])
            lines.append("---")
        lines.append("</context>")
        return "\n".join(lines)

    def _build_messages(self, query: str, context: str) -> list[dict]:
        """
        返回：
        [
            {"role": "system", "content": CITATION_SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\n问题：{query}"}
        ]
        """
```

### 期望输出
- `backend/llm/__init__.py`
- `backend/llm/client.py`

### 验证方式
```python
from backend.llm import CitationLLM, CITATION_SYSTEM_PROMPT
assert "来源文档名" in CITATION_SYSTEM_PROMPT
assert "通用知识补充" in CITATION_SYSTEM_PROMPT
llm = CitationLLM(model="mock")  # 不真调 API，只验证构造方法不报错
print("✅ LLM client 构造验证通过")
```

---

## 第 6 轮：Agent 编排层（核心）

### 对 AI IDE 的 Prompt

```
在 D:\super-turtor\backend\agent 目录下创建两个文件。

═══════════════════════════════════════
文件 1：__init__.py
═══════════════════════════════════════
导出：
  from .orchestrator import SuperTutorAgent

═══════════════════════════════════════
文件 2：orchestrator.py
═══════════════════════════════════════

from backend.config import VECTOR_TOP_K, BM25_TOP_K
from backend.document import DocumentParser, chunk_document
from backend.retrieval.vector_store import VectorStore
from backend.retrieval.bm25_search import BM25Searcher
from backend.llm import CitationLLM
import hashlib

class SuperTutorAgent:
    """
    核心编排器 — 不依赖 LangGraph，所有逻辑显式调用。
    桌面应用直接创建此实例然后调用其方法。
    """

    def __init__(self):
        self.vector_store = VectorStore()
        self.bm25_searcher = BM25Searcher()
        self.llm = CitationLLM()
        # 已索引的源文件名集合（用于 UI 展示"已索引文档列表"）
        self._sources: set[str] = set()

    # ── 文档管理 ──────────────────────────────

    def ingest_document(self, file_path: str) -> dict:
        """
        上传并索引一个文档文件。
        返回 {"ok": True, "chunk_count": 42, "filename": "xxx.pdf", "message": "..."}

        流程：
          1. DocumentParser.parse(file_path) → {"text": ..., "metadata": {...}}
          2. chunk_document(text, metadata) → list[dict] chunks
          3. self.vector_store.add_chunks(chunks)
          4. self.bm25_searcher.add_chunks(chunks)
          5. self._sources.add(metadata["filename"])
          6. 返回结果 dict
        """

    def remove_document(self, filename: str) -> None:
        """
        从知识库中移除指定文档的所有 chunk。
        （遍历 vector_store 中该 source 的 ids，逐个删除；
         BM25 侧需要重建索引，排除该 source）
        self._sources.discard(filename)
        """

    def list_sources(self) -> list[str]:
        """返回所有已索引的源文件名"""
        return sorted(self._sources)

    # ── 检索 ──────────────────────────────────

    def _hybrid_search(self, query: str) -> list[dict]:
        """
        混合检索（内部方法）：
          1. vec_results = self.vector_store.search(query, top_k=VECTOR_TOP_K)
          2. bm25_results = self.bm25_searcher.search(query, top_k=BM25_TOP_K)
          3. merged = self._merge_and_rerank(vec_results, bm25_results)
          4. 返回 merged （去重 + 排序后的 list[dict]）
        """

    def _merge_and_rerank(self, vec: list[dict], bm25: list[dict]) -> list[dict]:
        """
        合并策略：
          1. 对每个结果计算 content 的 MD5 作为去重键
          2. 同名 chunk 保留分数较高的那个
          3. 向量相似度和 BM25 分数不在同一量级，分别做 min-max 归一化后再融合：
              归一化_向量 = (score - min_vector) / (max_vector - min_vector)
              归一化_BM25 = (score - min_bm25) / (max_bm25 - min_bm25)
              最终分数 = 0.5 * 归一化_向量 + 0.5 * 归一化_BM25
              （如果只有一种结果，直接用原始分数）
          4. 按最终分数降序排列返回
        """

    # ── 问答 ──────────────────────────────────

    def ask(self, question: str) -> str:
        """
        对外问答接口。
          1. merged = self._hybrid_search(question)
          2. answer = self.llm.generate_with_citation(question, merged)
          3. 返回 answer 字符串
        """

    # ── 规划参考检索 ──────────────────────────

    def search_raw(self, query: str, top_k: int = 10) -> list[dict]:
        """
        绕过混合检索的排序融合，直接返回合并后的检索结果。
        供规划模块使用 — 它不需要精排，需要更宽的召回。
        相当于 _hybrid_search 但取 top_k 条。
        """
```

### 期望输出
- `backend/agent/__init__.py`
- `backend/agent/orchestrator.py`

### 验证方式
```python
from backend.agent import SuperTutorAgent
agent = SuperTutorAgent()
import tempfile, pathlib
f = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8")
f.write("# 测试\n\n这是关于数据结构的测试文档。")
f.close()
result = agent.ingest_document(f.name)
assert result["ok"] is True
assert result["chunk_count"] >= 1
sources = agent.list_sources()
assert len(sources) >= 1
# ask 需要真实的 LLM API Key，跳过或 mock
pathlib.Path(f.name).unlink()
print(f"✅ Agent 编排验证通过，已索引 {sources}")
```

---

## 第 7 轮：规划模块

### 对 AI IDE 的 Prompt

```
在 D:\super-turtor\backend\agent\planner.py 创建：

from backend.llm import CitationLLM, CITATION_SYSTEM_PROMPT

class StudyPlanner:
    """
    基于已索引教材生成个性化复习计划。
    不继承 Agent — 通过组合方式调用 Agent 的检索 + LLM。
    """

    def __init__(self, agent: "SuperTutorAgent"):
        """
        接收外部传入的 SuperTutorAgent 实例。
        额外创建一个专属 LLM 客户端（可用相同配置）。
        """
        self.agent = agent
        self.llm = CitationLLM()

    def generate_plan(self, days: int, subject: str | None = None) -> str:
        """
        参数：
          days: 复习天数（1-180）
          subject: 限定科目名称，None 表示所有已索引教材

        返回：Markdown 格式的复习计划字符串。

        流程：
          1. 用 self.agent.search_raw("列出教材的完整章节目录和每章包含的小节标题") 检索
          2. 用 self.agent.search_raw("各章节的重点知识点和难点") 检索
          3. 将两批检索结果 + days + subject 拼入 _build_plan_prompt()
          4. 调用 self.llm.client.chat.completions.create() 生成最终计划
          5. 返回 LLM 输出
        """

    def _build_plan_prompt(self, chapters_info: list[dict],
                           key_points: list[dict],
                           days: int, subject: str | None) -> str:
        """
        构造一个规划专用的 System Prompt，包含：
        - 角色设定："你是一位资深的考研规划师"
        - 输出格式要求（必须按 ## 第N周 的格式，每天标注 学习内容 / 配套习题 / 预计用时）
        - 带上检索到的章节目录和重难点信息
        - 带上天数要求

        返回完整的 prompt 文本（作为 user message 传给 LLM）。
        """
```

### 期望输出
- `backend/agent/planner.py`

### 验证方式
```python
from backend.agent.planner import StudyPlanner
# 只验证能实例化，不做端到端（需要真实 Agent + LLM）
print("✅ StudyPlanner 构造验证通过")
```

---

## 第 8 轮：PySide6 桌面应用（★ 核心变更）

### 对 AI IDE 的 Prompt

```
═══════════════════════════════════════════════════════════════
在 D:\super-turtor\frontend\desktop_app.py 创建 PySide6 桌面应用。
═══════════════════════════════════════════════════════════════

整体布局：

┌──────────────────────────────────────────────────────────┐
│ 🧠 超级导师 Super-Tutor                          ─ ✕     │
├──────────────┬───────────────────────────────────────────┤
│ 📚 知识库     │  Tab: 💬 问答  │  Tab: 📅 复习计划        │
│              │                                           │
│ [选择文件]    │  ┌─ 聊天区 (QScrollArea) ──────────────┐ │
│              │  │  你：什么是哈希表？                    │ │
│ 📄 ds.pdf    │  │  🧠：哈希表是一种...                   │ │
│ 📄 计组.pdf  │  │  [来源：《数据结构》第8章]              │ │
│ [✕删除]      │  └────────────────────────────────────┘ │
│              │  ┌─ 输入区 ─────────────────────────┐    │
│              │  │ [输入问题.................] [发送] │    │
├──────────────┴┴──────────────────────────────────────────┤
│ ⬤ 就绪 · 3 本教材已索引                                   │
└──────────────────────────────────────────────────────────┘

═══════════════════════════════════════
代码结构要求：
═══════════════════════════════════════

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel,
    QTabWidget, QScrollArea, QTextBrowser, QLineEdit, QStatusBar,
    QFileDialog, QSpinBox, QMessageBox, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont, QTextCursor, QIcon
from markdown_it import MarkdownIt   # 用于将 MD 转 HTML 后在 QTextBrowser 渲染

from backend.agent import SuperTutorAgent
from backend.agent.planner import StudyPlanner

# ═══════════════════════════════════════════
# 类 1：WorkerThread(QThread)
# ═══════════════════════════════════════════
# 用于在后台执行耗时的 LLM 调用，避免阻塞 UI。
# - 信号 finished = Signal(str)   — 执行完成
# - 信号 error = Signal(str)      — 执行出错
# - 属性 _task_type: "ask" | "plan" | "ingest"
# - 属性 _args: dict — 传给 worker 的参数

# ═══════════════════════════════════════════
# 类 2：ChatBubble(QWidget)
# ═══════════════════════════════════════════
# 自定义聊天气泡组件。
# - 构造函数参数：text, is_user=False
# - 用户气泡靠右（浅蓝底），AI 气泡靠左（浅绿底）
# - 用 QLabel 渲染 HTML 内容（markdown → HTML 通过 MarkdownIt 转换）
# - 引用格式 [来源：...] 用蓝色高亮（CSS span class）

# ═══════════════════════════════════════════
# 类 3：MainWindow(QMainWindow)
# ═══════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🧠 超级导师 Super-Tutor")
        self.resize(1100, 750)

        # ── 初始化后端 ──
        self.agent = SuperTutorAgent()
        self.planner = StudyPlanner(self.agent)

        # ── 构建 UI ──
        self._setup_ui()
        self._refresh_source_list()
        self.statusBar().showMessage("⬤ 就绪 · 尚未索引任何文档")

    def _setup_ui(self):
        """
        构建三区布局：
          左侧面板 (280px)  = 知识库列表 + 文件选择按钮 + 删除按钮
          右侧 = QTabWidget
            Tab "💬 问答" = 聊天区 (QScrollArea) + 输入区 (QLineEdit + QPushButton)
            Tab "📅 复习计划" = 天数选择 QSpinBox + 生成按钮 + 结果显示 QTextBrowser

        使用 QSplitter 分隔左右面板。
        """

        # --- 左侧面板 ---
        left = QWidget()
        left.setFixedWidth(280)
        left_layout = QVBoxLayout(left)

        title = QLabel("📚 知识库")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))

        btn_select = QPushButton("📂 选择文件")
        btn_select.clicked.connect(self._on_select_file)

        self.source_list = QListWidget()

        btn_delete = QPushButton("🗑 删除选中")
        btn_delete.clicked.connect(self._on_delete_source)

        left_layout.addWidget(title)
        left_layout.addWidget(btn_select)
        left_layout.addWidget(self.source_list)
        left_layout.addWidget(btn_delete)

        # --- 右侧 Tabs ---
        self.tabs = QTabWidget()

        # Tab 1: 问答
        chat_tab = self._build_chat_tab()
        self.tabs.addTab(chat_tab, "💬 问答")

        # Tab 2: 复习计划
        plan_tab = self._build_plan_tab()
        self.tabs.addTab(plan_tab, "📅 复习计划")

        # --- Splitter ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.setCentralWidget(splitter)

    def _build_chat_tab(self) -> QWidget:
        """构建问答 Tab"""

    def _build_plan_tab(self) -> QWidget:
        """构建复习计划 Tab"""

    def _on_select_file(self):
        """
        弹出 QFileDialog.getOpenFileName()，筛选 PDF/Word/MD/TXT。
        选择后启动 WorkerThread 执行 agent.ingest_document()，
        UI 显示进度条。完成后刷新左侧列表。
        """

    def _on_delete_source(self):
        """删除选中文档，刷新列表"""

    def _on_ask(self):
        """获取输入框文本，启动 WorkerThread 执行 agent.ask()，
           在聊天区添加用户气泡和 AI 气泡"""

    def _on_generate_plan(self):
        """获取天数，启动 WorkerThread 执行 planner.generate_plan()，
           在计划 Tab 的 QTextBrowser 中显示结果"""

    def _refresh_source_list(self):
        """刷新左侧 QListWidget"""

═══════════════════════════════════════
关键技术要点：
═══════════════════════════════════════
1. QThread 的正确用法：
   - WorkerThread.run() 中执行业务逻辑
   - 完成时 emit finished(result) 或 error(msg)
   - MainWindow 中用信号槽连接更新 UI

2. Markdown 渲染：
   - 用 markdown-it-py 的 MarkdownIt().render(text) 把 MD 转 HTML
   - QTextBrowser.setHtml(html) 显示

3. 聊天区滚动：
   - 聊天区用 QScrollArea 包裹一个 QVBoxLayout 的容器
   - 每添加一条气泡时，添加后把滚动条滚到底
   - scroll_bar = scroll_area.verticalScrollBar()
   - scroll_bar.setValue(scroll_bar.maximum())

4. 引用高亮（正则替换）：
   在 Markdown → HTML 之前，用正则把 [来源：...] 包裹成
   <span style="color:#2563eb;font-weight:bold;">[来源：...]</span>

5. 状态栏：
   操作前后更新：self.statusBar().showMessage("⏳ 正在索引...") 等
```

### 期望输出
- `frontend/desktop_app.py`（约 300-350 行）

### 验证方式
```bash
# 启动桌面应用
python -m frontend.desktop_app
# 应弹出窗口，左侧知识库为空，右侧问答 Tab 可用
# 无 API Key 时会在状态栏显示"未配置 LLM"但不崩溃
```

---

## 第 9 轮：main.py 启动入口

### 对 AI IDE 的 Prompt

```
在 D:\super-turtor 目录下创建 main.py：

import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """启动 PySide6 桌面应用"""
    from PySide6.QtWidgets import QApplication
    from frontend.desktop_app import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 跨平台一致的外观

    # 全局字体
    from PySide6.QtGui import QFont
    app.setFont(QFont("Microsoft YaHei", 10))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

### 期望输出
- `main.py`（约 25 行）

### 验证方式
```bash
python main.py
# 应弹出 PySide6 桌面窗口
```

---

## 第 10 轮：单元测试

### 对 AI IDE 的 Prompt

```
在 D:\super-turtor\tests 目录下创建两个测试文件。

═══════════════════════════════════════
文件 1：test_document.py
═══════════════════════════════════════
import pytest, tempfile, pathlib, os
from backend.document import DocumentParser, chunk_document

class TestDocumentParser:
    def test_parse_txt(self):
        """创建临时 txt，解析后验证 text 和 metadata"""
        ...

    def test_parse_markdown(self):
        """创建临时 md，验证解析"""
        ...

    def test_invalid_file(self):
        """传入不存在的文件，应抛出 FileNotFoundError"""
        ...

    def test_unsupported_extension(self):
        """传入 .png 文件，应抛出 ValueError"""
        ...

class TestChunker:
    def test_chunk_count(self):
        """长文本切分后 chunk 数 >= 1"""
        ...

    def test_chunk_has_content_and_metadata(self):
        """每个 chunk 包含 content 和 metadata.source"""
        ...

    def test_chunk_preserves_source(self):
        """metadata.source 与传入的 filename 一致"""
        ...

═══════════════════════════════════════
文件 2：test_retrieval.py
═══════════════════════════════════════
import pytest, tempfile, shutil
from backend.retrieval.vector_store import VectorStore
from backend.retrieval.bm25_search import BM25Searcher

class TestVectorStore:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vs = VectorStore(persist_dir=self.tmpdir)

    def teardown_method(self):
        self.vs.delete_all()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_and_search(self):
        """添加 chunk 后能检索到"""
        ...

    def test_count(self):
        """count() 返回正确数量"""
        ...

    def test_get_source_files(self):
        """get_source_files() 返回去重的源文件列表"""
        ...

class TestBM25Searcher:
    def setup_method(self):
        self.bm25 = BM25Searcher()

    def test_build_and_search(self):
        """添加 chunks 后 BM25 检索命中"""
        ...

    def test_chinese_tokenization(self):
        """中文查询能命中中文内容"""
        ...

    def test_count(self):
        """count() 返回正确数量"""
        ...
```

### 期望输出
- `tests/test_document.py`
- `tests/test_retrieval.py`

### 验证方式
```bash
pip install pytest
pytest tests/ -v
```

---

## 🔄 生成顺序 & 依赖图

```
第 1 轮 (config + 目录)
    │
    ├──► 第 2 轮 (parser + splitter) ──────────────────────┐
    ├──► 第 3 轮 (vector_store) ───────────────────────────┤
    ├──► 第 4 轮 (bm25) ───────────────────────────────────┤
    └──► 第 5 轮 (llm client) ─────────────────────────────┤
              │                                              │
              └────────────┬─────────────┬──────────┬───────┘
                           ▼             ▼          ▼
                      第 6 轮 (orchestrator)        第 10 轮 (tests)
                           │
                     ┌─────┴─────┐
                     ▼           ▼
                 第 7 轮      (等待)
                (planner)
                     │
                     ▼
                 第 8 轮 (PySide6 desktop app)
                     │
                     ▼
                 第 9 轮 (main.py)
```

---

## ⚠️ 注意事项

1. **方案 C ─ PySide6**：第 8 轮是桌面应用，打包后是一个 exe，不需要浏览器
2. **无 LangGraph**：本项目不需要复杂的状态机，编排器直接显式调用各方法
3. **无 jieba 依赖风险**：第 4 轮的 `_tokenize()` 里 jieba 用 try/except 包裹，降级为字符级分词
4. **LLM API 不真实调用**：第 5 轮生成后，验证只测试构造和 Prompt 常量，不调真实 API
5. **第 6 轮是关键**：`_merge_and_rerank()` 的归一化逻辑容易写错，生成后用第 10 轮测试验证
6. **第 8 轮 WorkerThread**：QThread 的 `run()` 不能直接更新 UI，必须通过信号槽，这是最常见的 PySide6 bug
7. **所有路径用 `from backend.xxx import`**：因为 main.py 把项目根目录加到了 sys.path

---

*生成日期：2025-06-19 · V2 PySide6 桌面版*
