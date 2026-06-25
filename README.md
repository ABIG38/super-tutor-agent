# 🧠 超级导师 Super-Tutor

<p align="center">
  <img src="https://img.shields.io/badge/status-active-success" alt="Status">
  <img src="https://img.shields.io/badge/python-3.11+-orange" alt="Python">
  <img src="https://img.shields.io/badge/LangChain-0.3+-green" alt="LangChain">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License">
</p>

<p align="center">
  <b>无幻觉 · 超长上下文 · 带溯源的学业/考研规划 Agent</b>
  <br>
  <em>将教材与真题一次性塞入 AI，为每一位学生生成真正可信的个性化复习方案</em>
</p>

---

## 📖 项目简介

超级导师（Super-Tutor）是一款基于 **LangChain + 超长上下文 LLM** 的智能学业/考研规划助手。

不同于通用聊天机器人，它聚焦于**专业课教材与真题的深度理解**——你可以直接把数据结构、计算机组成原理等厚重教材和历年真题上传给系统，系统会：

- **🤖 精准问答**：基于你的教材内容回答知识点问题，并标注信息来源
- **📚 个性化规划**：根据教材目录、重难点和你的时间安排，自动生成复习计划
- **✅ 杜绝幻觉**：所有回答强制溯源，未知内容明确声明"通用知识补充"

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🔗 **超长上下文** | 利用云端 LLM 的百万 Token 上下文窗口，一次载入多本教材 |
| 🏷️ **强制溯源** | 每条回答标注 `[来源文档：章节]`，杜绝无中生有 |
| 🎯 **混合检索** | 向量语义检索 + BM25 关键词检索，专业术语精准匹配 |
| 🚀 **Context Caching** | 缓存教材内容，极速响应重复查询，节省 Token 费用 |
| 📅 **智能规划** | 基于真实教材章节目录生成按天/周拆解的复习计划 |
| 💾 **数据本地化** | 向量数据库、索引文件全在本地，隐私无忧 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     PySide6 桌面窗口                              │
│  ┌──────────┐  ┌────────────┐  ┌──────────────────┐           │
│  │ 知识库列表 │  │  问答对话页  │  │  复习规划+进度    │           │
│  └──────────┘  └────────────┘  └──────────────────┘           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ signals + QThread
┌──────────────────────────▼──────────────────────────────────────┐
│                   SuperTutorAgent (orchestrator)                 │
│         编排：文档处理 / 混合检索+精排 / 规划+追踪               │
└────┬──────────┬──────────────┬──────────────────┬───────────────┘
     │          │              │                  │
┌────▼───┐ ┌───▼──────┐ ┌─────▼──────┐  ┌───────▼────────┐
│  文档    │ │  检索     │ │  规划       │  │  进度追踪       │
│  引擎    │ │  引擎     │ │  引擎       │  │  (SQLite)       │
└────┬───┘ └───┬──────┘ └─────┬──────┘  └───────┬────────┘
     │          │              │                  │
┌────▼──────────▼──────────────▼──────────────────▼─────────────┐
│                       基础设施层                                 │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │ ChromaDB │  │ BM25 + RRF   │  │ LLM API (DeepSeek)      │   │
│  │ (向量库)  │  │ + Reranker   │  │ + 流式生成              │   │
│  └──────────┘  └──────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

系统由 **三大核心模块** 构成：

### 1️⃣ 文件处理与超长上下文引擎
文档上传 → 语义切分（按章节/段落） → 向量化存储 → 上下文缓存预热

### 2️⃣ 无幻觉带溯源的检索系统
混合检索（Vector + BM25） → 结果融合 → LLM 强制溯源生成

### 3️⃣ Agent 规划模块
教材分析 → 时间拆解 → 按周/天生成计划 → 动态调整

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **桌面 UI** | PySide6 (Qt for Python) |
| **核心框架** | Python 3.11+ |
| **LLM** | DeepSeek Chat API (OpenAI 兼容) |
| **向量数据库** | ChromaDB (本地持久化) |
| **Embedding** | BAAI/bge-small-zh-v1.5 (中文优化) |
| **关键词检索** | rank-bm25 + jieba 分词 |
| **精排** | BAAI/bge-reranker-base (Cross-Encoder) |
| **融合** | RRF 倒数秩融合 |
| **文档解析** | PyMuPDF · python-docx |
| **配置** | Pydantic Settings |
| **日志** | loguru (脱敏) |
| **打包** | PyInstaller |

---

## 📁 项目结构

```
super-tutor/
├── 📂 backend/                  # 后端代码
│   ├── agent/                   # Agent 编排
│   │   ├── orchestrator.py      # SuperTutorAgent 主路由
│   │   ├── planner.py           # 复习计划生成
│   │   └── tracker.py           # SQLite 进度追踪
│   ├── document/                # 文档引擎
│   │   ├── parser.py            # PDF/DOCX/MD/TXT 解析
│   │   └── splitter.py          # 语义切分 (800字符)
│   ├── retrieval/               # 检索引擎
│   │   ├── vector_store.py      # ChromaDB 向量库
│   │   ├── bm25_search.py       # BM25 关键词检索
│   │   ├── hybrid_search.py     # RRF 混合检索融合
│   │   └── reranker.py          # Cross-Encoder 精排
│   ├── llm/                     # LLM 交互
│   │   └── client.py            # CitationLLM (流式+溯源)
│   ├── config.py                # Pydantic 全局配置
│   ├── model_checker.py         # 模型检测+下载 (F-20)
│   └── worker.py                # QThread 后台工作线程
├── 📂 frontend/                 # PySide6 桌面
│   ├── desktop_app.py           # 主窗口 (无边框+三区布局)
│   ├── pages/
│   │   ├── chat_page.py         # 问答页 (流式渲染)
│   │   └── plan_page.py         # 规划+进度页
│   └── components/
│       ├── document_tree.py     # 知识库文档树
│       ├── course_selector.py   # 课程选择器
│       └── settings_dialog.py   # 设置弹窗
├── 📂 tests/                    # 测试 (49 tests)
│   ├── document/test_parser.py
│   ├── document/test_splitter.py
│   ├── retrieval/test_bm25.py
│   ├── retrieval/test_hybrid.py
│   ├── agent/test_orchestrator.py
│   └── llm/test_client.py
├── 📂 knowledge_base/           # 本地数据存储
│   ├── raw/                     # 原始文档
│   ├── index/                   # ChromaDB + BM25 + SQLite
│   └── models/                  # Embedding/Reranker 模型文件
├── 📄 super-tutor.spec          # PyInstaller 打包配置
├── 📄 requirements.txt
├── 📄 .env.example
└── 📄 README.md
```

---

## 🚀 快速开始

### 前置条件

- Python 3.11+
- 一个支持超长上下文的 LLM API Key（如 DeepSeek）
- Windows 10/11 64-bit（阶段一仅支持 Windows）

### 安装

```bash
# 克隆项目
git clone https://github.com/ABIG38/super-tutor.git
cd super-tutor

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY=sk-xxx
```

### 启动

```bash
python main.py
```

首次启动会自动检测模型文件，缺失时引导下载（约 1.2GB）。

### 使用

1. **上传教材**：左侧面板点击「+ 添加」，选择 PDF/DOCX/MD/TXT 文件
2. **提问**：在问答 Tab 输入问题，系统基于教材内容回答并标注来源
3. **生成计划**：在计划 Tab 设置天数和每日学时，点击生成

### 打包为 exe

```bash
# 先确保模型文件已下载到 knowledge_base/models/
pip install pyinstaller
pyinstaller super-tutor.spec
# 产出 dist/super-tutor.exe
```

分发时将 `dist/super-tutor.exe` 与 `knowledge_base/models/` 目录一起打包。


---

## 📊 项目里程碑

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| M1 基础框架 | config/日志/文档解析/LLM 客户端 | ✅ 完成 |
| M2 文档引擎 | 文档上传/解析/切分/向量索引 | ✅ 完成 |
| M3 检索问答 | 混合检索(Vector+BM25+RRF)+Reranker+溯源生成 | ✅ 完成 |
| M4 学习规划 | 复习计划生成 + SQLite 进度追踪 | ✅ 完成 |
| M5 PySide6 桌面 | 无边框窗口 + 三区布局 + 流式问答 | ✅ 完成 |
| M6 测试优化 | 49 个测试 + 边界处理 + 打包配置 | ✅ 完成 |
| M7 阶段二 | 多轮对话 / Context Caching / 学习反馈闭环 | 🔲 待启动 |

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！请确保：

1. 代码通过现有测试 (`pytest tests/`)
2. 新功能附带测试用例
3. 文档同步更新

---

## 📄 许可证

[MIT License](LICENSE)

---

## 🙏 致谢

- LangChain 社区
- 所有提供建议的用户和贡献者
