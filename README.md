# 🧠 超级导师 Super-Tutor

<p align="center">
  <img src="https://img.shields.io/badge/status-active-success" alt="Status">
  <img src="https://img.shields.io/badge/python-3.11+-orange" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License">
</p>

<p align="center">
  <b>无幻觉 · 带溯源 · 多课程隔离的学业/考研规划桌面应用</b>
  <br>
  <em>上传教材与真题，让 AI 基于真实内容回答知识点、生成个性化复习计划</em>
</p>

---

## 📖 项目简介

超级导师（Super-Tutor）是一款基于 **PySide6 + DeepSeek** 的本地桌面学业/考研规划助手。

不同于通用聊天机器人，它聚焦于**专业课教材与真题的深度理解**——上传数据结构、计算机组成原理等教材和历年真题后，系统会：

- **🤖 精准问答**：基于教材内容回答问题，强制标注 `[来源文档名]`
- **📚 个性化规划**：根据教材目录、重难点和你的时间安排，自动生成按天拆解的复习计划
- **✅ 杜绝幻觉**：检索分数过低或 LLM 自认无答案时明确告知，绝不捏造
- **📂 多课程隔离**：支持多门科目独立管理，数据互不干扰

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🏷️ **强制溯源** | 每条回答标注 `[来源文档名]`，禁止 LLM 自行编造 |
| 🎯 **混合检索** | 语义检索 + BM25 关键词 → RRF 融合 → Cross-Encoder 精排 |
| 🚦 **意图路由** | 规则+LLM 分类（闲聊/问答/规划），闲聊零检索节省费用 |
| 📅 **智能规划** | 基于教材章节目录生成按天拆解的计划，支持流式生成 |
| ✅ **打卡追踪** | 每日打卡推进进度，进度条可视化，计划注入问答上下文 |
| 💬 **会话管理** | 多会话独立存储，支持新建/切换/重命名/删除 |
| 🔀 **多课程管理** | 课程 CRUD，每门课程拥有独立的知识库和计划数据 |
| 🌐 **网络搜索** | 可选开启 360 搜索补充实时信息（4 秒超时自动降级） |
| 💾 **数据本地化** | 向量库、索引、文档全在本地，隐私无忧 |

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        用户界面 (PySide6 桌面)                             │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  ┌────────────┐  │
│  │ 课程选择器 │  │  知识库列表   │  │  问答对话页       │  │ 规划+进度   │  │
│  │ (下拉切换) │  │ (文档管理)   │  │ (流式Markdown渲染) │  │ (打卡/条)  │  │
│  └──────────┘  └──────────────┘  └──────────────────┘  └────────────┘  │
│  设置弹窗 · 预览弹窗 · 右键菜单 · 拖拽上传                               │
└──────────────────────────────────────────────────────────────────────────┘
                           │  用户输入
                           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         IntentRouter (意图路由)                          │
│                规则短路 → LLM 分类 → rag / chat / plan                   │
└──────────┬──────────────────────────────────────┬───────────────────────┘
     chat/plan │                          rag │
               ▼                              ▼
┌──────────────────────────────┐  ┌─────────────────────────────────────────┐
│  chat: 直接 LLM 闲聊          │  │  SuperTutorAgent                       │
│  plan: 引流至规划 Tab         │  │  (查询重写→历史压缩→检索→流式回答)      │
└──────────────────────────────┘  └────┬──────────┬─────────────┬──────────┘
                                       │          │             │
                                  ┌────▼───┐ ┌───▼──────┐ ┌────▼─────────┐
                                  │  文档    │ │  检索     │ │  规划+进度    │
                                  │  引擎    │ │  引擎     │ │ (文件系统)    │
                                  └────┬───┘ └───┬──────┘ └──────┬────────┘
                                       │          │              │
┌──────────────────────────────────────▼──────────▼──────────────▼──────────┐
│                             基础设施层                                      │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────┐ ┌──────────┐ │
│  │ ChromaDB │  │ BM25 + jieba │  │ LLM API      │  │ JSON │ │ 本地文件  │ │
│  │ (向量库)  │  │ (关键词索引) │  │ (溯源回答)    │  │ 文件  │ │ 系统     │ │
│  └──────────┘  └──────────────┘  └──────────────┘  │ 系统  │ │(原始文档) │ │
│                                                     │(课程/ │ └──────────┘ │
│                                                     │ 计划/ │              │
│                                                     │ 会话) │              │
│                                                     └──────┘              │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **桌面 UI** | PySide6 (Qt for Python) · QWebEngineView |
| **LLM** | DeepSeek Chat API (OpenAI 兼容) · 流式生成 |
| **向量数据库** | ChromaDB (本地持久化) |
| **Embedding** | BAAI/bge-small-zh-v1.5 (本地离线) |
| **关键词检索** | rank-bm25 + jieba 分词 + Bigram |
| **精排** | BAAI/bge-reranker-base (SiliconFlow API) |
| **融合算法** | RRF 倒数秩融合 (k=60) |
| **文档解析** | PyMuPDF · python-docx · 自动编码检测 |
| **配置** | Pydantic Settings · .env 文件 |
| **会话存储** | JSONL 文件系统 |
| **日志** | loguru (API Key 脱敏) |
| **打包** | PyInstaller (单文件 exe) |

---

## 📁 项目结构

```
super-tutor/
├── main.py                        # 启动入口
├── requirements.txt
├── .env                           # API Key / Base / Model 配置
├── .env.example                   # 配置模板
├── super-tutor.spec               # PyInstaller 打包配置
├── backend/
│   ├── config.py                  # Pydantic Settings + loguru 初始化
│   ├── model_checker.py           # 模型文件检测
│   ├── chat_store.py              # 会话存储 (JSONL + manifest)
│   ├── document/
│   │   ├── parser.py              # DocumentParser (PDF/DOCX/MD/TXT)
│   │   └── splitter.py            # chunk_document (递归段落切分)
│   ├── retrieval/
│   │   ├── vector_store.py        # ChromaDB 向量库
│   │   ├── bm25_search.py         # BM25 关键词检索 (jieba + Bigram)
│   │   ├── reranker.py            # BGEReranker (Cross-Encoder API)
│   │   └── web_search.py          # 360 搜索 (4 秒超时降级)
│   ├── llm/
│   │   └── client.py              # CitationLLM (强制溯源 + 流式)
│   └── agent/
│       ├── orchestrator.py        # SuperTutorAgent 单例
│       └── router.py              # IntentRouter (规则+LLM 分类)
├── frontend/
│   ├── theme.py                   # 赛博深海配色表 (11色)
│   ├── desktop_app.py             # SuperTutorWindow (无边框主窗口)
│   ├── components/
│   │   ├── course_selector.py     # 课程选择器 (下拉框+CRUD)
│   │   ├── document_tree.py       # 知识库文档树 (右键菜单+拖拽上传)
│   │   ├── settings_dialog.py     # 设置弹窗 (API/存储配置)
│   │   └── preview_dialog.py      # 文档/计划预览弹窗
│   └── pages/
│       ├── chat_page.py           # 问答页 (会话列表+流式Markdown渲染)
│       └── plan_page.py           # 规划页 (参数+流式生成+打卡+进度条)
├── tests/
│   ├── document/test_parser.py
│   ├── document/test_splitter.py
│   ├── agent/test_orchestrator.py
│   └── llm/test_client.py
├── knowledge_base/                # 本地数据存储
│   ├── models/                    # Embedding 模型文件
│   ├── raw/                       # 原始文档
│   └── index/
│       ├── chroma/                # ChromaDB 持久化
│       ├── bm25_corpus.pkl        # BM25 分词语料
│       ├── courses.json           # 课程列表
│       ├── plans/                 # 计划文件 (*.md + active_plan.json)
│       ├── chats/                 # 会话文件 (*.jsonl + manifest.json)
│       └── logs/                  # 应用日志 (按天滚动, 保留30天)
└── README.md
```

---

## 🚀 快速开始

### 前置条件

- Python 3.11+
- DeepSeek (或 OpenAI 兼容) API Key
- Windows 10/11 64-bit

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
# 可选配置 OPENAI_BASE_URL 和 OPENAI_MODEL
```

### 启动

```bash
python main.py
```

首次启动会自动检测模型文件和 API Key，缺失时弹窗引导配置。

### 使用流程

1. **创建课程**（可选）：标题栏下拉框点击 `+` 新建课程，如「数据结构」
2. **上传教材**：左侧面板「+ 添加」，选择 PDF/DOCX/MD/TXT 文件（支持拖拽）
3. **提问**：在「问答 Tab」输入问题，系统基于教材回答并标注来源
4. **生成计划**：切换到「规划 Tab」，设置天数和每日学时，点击生成
5. **打卡追踪**：每天点击「打卡今天」，进度条自动推进

### 打包为 exe

```bash
pip install pyinstaller
pyinstaller super-tutor.spec
# 产出 dist/super-tutor.exe
```

分发时将 `dist/super-tutor.exe` 与 `knowledge_base/models/` 目录一起打包。

---

## 🔍 数据流详解

### 问答流程

```
用户提问 → 意图路由(规则+LLM分类)
  ├─ 闲聊 → 零检索，直接 LLM 回复
  ├─ 规划 → 引流至规划面板
  └─ 知识问答 →
       ① 查询重写（短提问消解指代）
       ② 向量检索 (Top 10)
       ③ BM25 检索 (Top 30 → 过滤取 10)
       ④ RRF 倒数秩融合 (k=60)
       ⑤ Reranker 精排 (Top 15 → 5)
       ⑥ 网络搜索（可选，4 秒超时降级）
       ⑦ 计划注入（若有活跃计划）
       ⑧ LLM 流式生成（强制溯源）
```

### 规划与打卡

```
设置参数 → 流式生成 → 自动保存为活跃计划
  → 每日打卡推进 current_day
  → 进度条实时更新
  → 完成时按钮自动禁用
```

---

## 📊 项目里程碑

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| M1 基础框架 | config/日志/文档解析/LLM 客户端 | ✅ 完成 |
| M2 文档引擎 | 上传/解析/切分/向量+BM25 双索引 | ✅ 完成 |
| M3 检索问答 | RRF 融合 + Reranker 精排 + 强制溯源 | ✅ 完成 |
| M4 意图路由 | 规则+LLM 分类，闲聊零检索 | ✅ 完成 |
| M5 课程管理 | 多课程 CRUD，数据隔离 | ✅ 完成 |
| M6 学习规划 | 流式生成 + 打卡追踪 + 进度条 | ✅ 完成 |
| M7 桌面完善 | 会话管理 + 设置弹窗 + 预览弹窗 + 拖拽上传 | ✅ 完成 |
| M8 测试优化 | 语法/逻辑测试 + 边界处理 + PyInstaller 打包 | ✅ 完成 |

---

## 📄 许可证

[MIT License](LICENSE)
