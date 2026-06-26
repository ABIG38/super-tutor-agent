"""
单元测试 — CitationLLM

覆盖场景（对应 TECH_DESIGN.md 第 9 节）:
    - ⑦ LLM 自省无实质答案 → System Prompt 第 6 条（由 prompt 测试覆盖）
    - ⑫ API 超时 → 重试 1 次 → LLMError
    - ⑬ API Key 无效 → LLMError

使用 unittest.mock 模拟 openai SDK 的 chat.completions.create。
"""

from __future__ import annotations


import pytest

from backend.llm.client import CITATION_SYSTEM_PROMPT, ChunkForLLM, CitationLLM


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def llm() -> CitationLLM:
    """返回一个 CitationLLM 实例（mock 模式下不使用真实 API Key）。"""
    return CitationLLM(api_key="sk-test-fake-key")


@pytest.fixture
def sample_chunks() -> list[ChunkForLLM]:
    """返回一组模拟检索片段。"""
    return [
        ChunkForLLM(content="B+ 树是平衡多路查找树。", filename="数据结构.md", score=0.85),
        ChunkForLLM(content="所有叶节点在同一层。", filename="数据结构.md", score=0.72),
    ]


# ── System Prompt ──────────────────────────────────────────────────────────


class TestSystemPrompt:
    """CITATION_SYSTEM_PROMPT 完整性。"""

    def test_contains_citation_rule(self) -> None:
        """必须包含强制溯源规则（第 2 条）。"""
        assert "[来源文档名]" in CITATION_SYSTEM_PROMPT

    def test_contains_anti_hallucination(self) -> None:
        """必须包含防幻觉规则（第 6 条）。"""
        assert "防幻觉" in CITATION_SYSTEM_PROMPT

    def test_contains_prompt_injection_defense(self) -> None:
        """必须包含提示注入防御（第 7 条）。"""
        assert "提示注入" in CITATION_SYSTEM_PROMPT


# ── 同步生成测试 ────────────────────────────────────────────────────────────


class TestGenerateWithCitation:
    """generate_with_citation 同步模式。"""

    # TODO: mock openai 返回正常响应
    # TODO: 验证 context 格式正确包含 <context> 标签
    # TODO: 验证 history 参数正确拼入 messages

    pass


# ── 流式生成测试 ────────────────────────────────────────────────────────────


class TestGenerateWithCitationStream:
    """generate_with_citation_stream 流式模式。"""

    # TODO: mock openai 返回流式 chunk
    # TODO: 验证逐 token yield
    # TODO: 验证中断（cancel_stream）

    pass


# ── 边界情况测试 ────────────────────────────────────────────────────────────


class TestLLMEdgeCases:
    """TECH_DESIGN.md 第 9 节边界情况。"""

    # TODO: ⑫ API 超时 → mock APITimeoutError → 重试 → LLMError
    # TODO: ⑬ API Key 无效 → mock AuthenticationError → LLMError
    # TODO: cancel_stream → 验证 _cancel_event 被 set

    pass
