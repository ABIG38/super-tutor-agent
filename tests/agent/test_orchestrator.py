"""
单元测试 — SuperTutorAgent 核心流程

覆盖:
    - 文档索引（正常 + 重复 + 扫描件）
    - 文档删除
    - 课程删除
    - 空知识库问答
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.agent.orchestrator import SuperTutorAgent


@pytest.fixture
def agent():
    """返回一个 mock 了 VectorStore/BM25/LLM 的 agent。"""
    with (
        patch("backend.agent.orchestrator.VectorStore") as mock_vs,
        patch("backend.agent.orchestrator.BM25Searcher") as mock_bm,
        patch("backend.agent.orchestrator.HybridSearcher") as mock_hy,
        patch("backend.agent.orchestrator.Reranker") as mock_rr,
        patch("backend.agent.orchestrator.CitationLLM") as mock_llm,
        patch("backend.agent.orchestrator.load_dotenv"),
    ):
        a = SuperTutorAgent()
        a.vector_store = MagicMock()
        a.bm25 = MagicMock()
        a.hybrid = MagicMock()
        a.reranker = MagicMock()
        a.llm = MagicMock()
        a.tracker = MagicMock()
        a._sources = {}
        yield a


class TestIngest:
    def test_normal_pdf(self, agent, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_text("fake pdf content")
        with patch.object(agent.parser, "parse") as mock_parse:
            mock_parse.return_value = MagicMock(
                text="第一章 绪论", filename="test.pdf",
                scanned=False, doc_type="textbook", course="",
            )
            result = agent.ingest_document(str(pdf))
            assert result["ok"] is True
            assert result["filename"] == "test.pdf"

    def test_scanned_pdf_rejected(self, agent, tmp_path):
        pdf = tmp_path / "scan.pdf"
        pdf.write_text("dummy")
        with patch.object(agent.parser, "parse") as mock_parse:
            mock_parse.return_value = MagicMock(
                text="", filename="scan.pdf",
                scanned=True, doc_type="textbook",
            )
            result = agent.ingest_document(str(pdf))
            assert result["ok"] is False
            assert result["reason"] == "scanned_pdf"

    def test_duplicate_rejected(self, agent, tmp_path):
        pdf = tmp_path / "dup.pdf"
        pdf.write_text("x")
        agent._sources["dup.pdf"] = {}
        result = agent.ingest_document(str(pdf))
        assert result["ok"] is False
        assert result["reason"] == "duplicate"


class TestDelete:
    def test_delete_document(self, agent, tmp_path):
        agent._sources["del.pdf"] = {"course": "test"}
        result = agent.delete_document("del.pdf")
        assert result["ok"] is True
        assert "del.pdf" not in agent._sources

    def test_delete_nonexistent(self, agent):
        result = agent.delete_document("nope.pdf")
        assert result["ok"] is False


class TestAsk:
    def test_empty_knowledge_base(self, agent):
        tokens = list(agent.ask("问题"))
        assert "知识库为空" in "".join(tokens)
