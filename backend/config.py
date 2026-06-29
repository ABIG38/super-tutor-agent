from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    llm_api_key: str = Field(default="MISSING_KEY", validation_alias="OPENAI_API_KEY")
    llm_api_base: str = Field(default="https://api.deepseek.com/v1", validation_alias="OPENAI_BASE_URL")
    llm_model: str = Field(default="deepseek-chat", validation_alias="OPENAI_MODEL")

    # Embedding
    embedding_api_key: str = Field(default="", validation_alias="EMBEDDING_API_KEY")
    embedding_api_base: str = Field(default="https://api.siliconflow.cn/v1", validation_alias="EMBEDDING_API_BASE")
    embedding_model: str = "BAAI/bge-m3"

    # Chunk
    chunk_size: int = 800
    chunk_overlap: int = 120

    # Storage
    storage_root: str = "knowledge_base"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def storage_root_path(self) -> Path:
        """将 storage_root 解析为绝对路径。"""
        return Path(self.storage_root).resolve()
    @property
    def chroma_dir(self) -> Path:
        """ChromaDB 向量数据库持久化目录。"""
        return self.storage_root_path / "index" / "chroma"
    @property
    def models_dir(self) -> Path:
        """模型文件存放目录。"""
        return self.storage_root_path / "models"


settings = Settings()
if settings.llm_api_key == "MISSING_KEY":
    print("[config] 注意: OPENAI_API_KEY 未设置，启动后将引导配置", file=__import__("sys").stderr)
