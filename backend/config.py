"""
全局配置 — Pydantic BaseSettings

从 .env 加载，自动校验类型，缺失必填项时明确报错。
对应 TECH_DESIGN.md §8.2。
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """超级导师全局配置。

    所有字段可通过 .env 文件或环境变量设置。
    llm_api_key 为必填，缺失时启动报错。
    """

    # ── LLM ───────────────────────────────────────

    llm_api_key: str  # 必填 — API Key
    llm_api_base: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    # ── Embedding / Reranker ─────────────────────

    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_device: str = "auto"  # auto / cpu / cuda
    transformers_offline: bool = True  # 打包后强制离线
    hf_home: str = ""  # HuggingFace 模型缓存目录，空则自动推断

    # ── 文档切分 ─────────────────────────────────

    chunk_size: int = 800
    chunk_overlap: int = 120

    # ── 检索 ─────────────────────────────────────

    vector_top_k: int = 5
    bm25_top_k: int = 5
    rrf_k: int = 60           # RRF 平滑常数（论文推荐值）
    reranker_top_k: int = 15  # Reranker 输入条数
    final_top_k: int = 7      # 最终传给 LLM 的条数
    score_threshold: float = 0.3  # 检索分数阈值，低于此值跳过 LLM

    # ── 存储路径 ─────────────────────────────────

    storage_root: str = "knowledge_base"
    tracker_db_path: str = ""       # 空则用 {storage_root}/index/learning_progress.db
    courses_config_path: str = ""   # 空则用 {storage_root}/index/courses.json

    # ── 日志 ─────────────────────────────────────

    log_retention_days: int = 30

    # ── Pydantic 配置 ────────────────────────────

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # 忽略未知环境变量
    }

    # ── 派生属性 ─────────────────────────────────

    @property
    def storage_root_path(self) -> Path:
        return Path(self.storage_root).resolve()

    @property
    def index_dir(self) -> Path:
        return self.storage_root_path / "index"

    @property
    def chroma_dir(self) -> Path:
        return self.index_dir / "chroma"

    @property
    def models_dir(self) -> Path:
        return self.storage_root_path / "models"

    @property
    def logs_dir(self) -> Path:
        return self.storage_root_path / "logs"

    @property
    def bm25_corpus_path(self) -> Path:
        return self.index_dir / "bm25_corpus.pkl"

    @property
    def tracker_db(self) -> Path:
        if self.tracker_db_path:
            return Path(self.tracker_db_path)
        return self.index_dir / "learning_progress.db"

    @property
    def courses_json(self) -> Path:
        if self.courses_config_path:
            return Path(self.courses_config_path)
        return self.index_dir / "courses.json"


# ── 全局单例 ──────────────────────────────────────────

# 实例化时自动从 .env 加载，缺失 llm_api_key 会抛 ValidationError
try:
    settings = Settings()
except Exception as e:
    # 允许启动（UI 层会检查并引导配置），但打印警告
    import sys
    print(f"[config] 配置加载警告: {e}", file=sys.stderr)
    # 用占位值创建实例以便应用能启动到设置界面
    settings = Settings(llm_api_key="MISSING_KEY")


# ── 日志初始化 ────────────────────────────────────────

def init_logging() -> None:
    """初始化 loguru 日志系统。

    - 写入 {storage_root}/logs/app.log
    - 按天滚动，保留 N 天
    - 脱敏 API Key 和用户提问原文
    - 不 raise，任何错误静默回退到 stderr

    应在应用入口 (main.py) 最早期调用。
    """
    import re
    import sys
    from loguru import logger

    # 移除默认 handler
    logger.remove()

    # 始终保留一个 stderr handler（用于开发调试）
    logger.add(
        sys.stderr,
        level="DEBUG",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True,
    )

    # 文件 handler
    try:
        log_dir = settings.logs_dir
        log_dir.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_dir / "app.log",
            rotation="1 day",
            retention=f"{settings.log_retention_days} days",
            level="INFO",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            filter=_sanitize_record,  # ★ 脱敏
        )
        logger.info("日志系统初始化完成: {}", log_dir / "app.log")
    except Exception as e:
        logger.warning("无法创建日志文件: {}", e)


def _sanitize_record(record: dict) -> bool:
    """日志脱敏 filter — mask API Key 和用户提问原文。"""
    import re
    msg = record.get("message", "")
    if isinstance(msg, str):
        # Mask API Key (sk-...)
        msg = re.sub(r"sk-[A-Za-z0-9]{20,}", "sk-***", msg)
        # Mask question 字段（JSON 日志中的用户提问）
        msg = re.sub(
            r'["\']question["\']\s*:\s*["\'][^"\']*["\']',
            "'question': '***'",
            msg,
        )
        record["message"] = msg
    return True
