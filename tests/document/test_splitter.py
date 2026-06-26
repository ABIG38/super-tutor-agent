"""
单元测试 — chunk_document

覆盖:
    - 正常段落切分
    - 空文本
    - 超大单段落递归切分
    - overlap 正确性
    - 混合大小段落
"""
from backend.document.splitter import chunk_document, _split_oversized_paragraph, _split_by_fixed_length


class TestChunkNormal:
    def test_single_paragraph(self):
        r = chunk_document("hello world", {"fn": "t.txt"}, chunk_size=800)
        assert len(r) == 1
        assert r[0]["content"] == "hello world"
        assert r[0]["metadata"]["fn"] == "t.txt"

    def test_multiple_paragraphs(self):
        text = "para1\n\npara2\n\npara3"
        r = chunk_document(text, {}, chunk_size=800)
        assert len(r) == 1  # all fit in one chunk

    def test_overflow_creates_new_chunk(self):
        text = "a" * 700 + "\n\n" + "b" * 200
        r = chunk_document(text, {}, chunk_size=800)
        assert len(r) == 2

    def test_empty_text(self):
        r = chunk_document("", {})
        assert r == []
        r2 = chunk_document("   \n\n  ", {})
        assert r2 == []

    def test_metadata_preserved(self):
        meta = {"filename": "test.pdf", "course": "math", "chunk_index": 99}
        r = chunk_document("hello", meta.copy(), chunk_size=800)
        assert r[0]["metadata"]["filename"] == "test.pdf"
        # chunk_index should be overwritten by the function
        assert r[0]["metadata"]["chunk_index"] == 0


class TestOversizedParagraph:
    def test_single_oversized_paragraph(self):
        text = "x" * 2000
        r = chunk_document(text, {}, chunk_size=800)
        assert len(r) >= 3
        for c in r:
            assert len(c["content"]) <= 800

    def test_mixed_normal_and_oversized(self):
        text = "normal\n\n" + "y" * 2000 + "\n\nanother"
        r = chunk_document(text, {}, chunk_size=800)
        for c in r:
            assert len(c["content"]) <= 800, f"chunk too large: {len(c['content'])}"

    def test_giant_paragraph(self):
        text = "z" * 10000
        r = chunk_document(text, {}, chunk_size=800)
        for c in r:
            assert len(c["content"]) <= 800
        assert len(r) >= 12


class TestSplitHelpers:
    def test_fixed_length(self):
        r = _split_by_fixed_length("abcdefgh", 3, 0)
        assert r == ["abc", "def", "gh"]

    def test_fixed_length_with_overlap(self):
        r = _split_by_fixed_length("abcdefgh", 3, 1)
        assert "abc" in r

    def test_sentence_split(self):
        text = "第一句。第二句！第三句？第四句。"
        r = _split_oversized_paragraph(text, 8, 0)
        assert len(r) >= 2  # sentences get grouped into fixed-length chunks
