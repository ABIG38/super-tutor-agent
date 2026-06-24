"""
单元测试 — DocumentParser

覆盖场景（对应 TECH_DESIGN.md 第 9 节）:
    - ① 扫描版 PDF → scanned=True
    - ② 加密 PDF → PermissionError
    - ③ 文件 >200MB → ValueError
    - 正常 PDF / DOCX / MD / TXT 解析
    - 扩展名不支持 → ValueError
    - 文件不存在 → FileNotFoundError

使用 unittest.mock 模拟外部依赖（fitz.open、DocxDocument 等），
实际文件操作通过 pytest tmp_path 创建临时文件完成。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.document.parser import DocumentParser, ParsedDocument


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def parser() -> DocumentParser:
    """返回一个干净的 DocumentParser 实例（无状态，可复用）。"""
    return DocumentParser()


# ── 正常解析路径 ────────────────────────────────────────────────────────────


class TestParseNormal:
    """正常文档解析路径测试。"""

    # ── PDF ────────────────────────────────────────────────────────────

    @patch("backend.document.parser.fitz.open")
    def test_normal_pdf(
        self, mock_fitz_open: MagicMock, parser: DocumentParser, tmp_path: str
    ) -> None:
        """正常 PDF 解析：mock fitz 返回有内容的页面。"""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("dummy content")

        # mock fitz 文档对象
        mock_page = MagicMock()
        mock_page.get_text.return_value = "这是第一页内容。\n第二行。"
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.load_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        result = parser.parse(str(pdf_file))

        assert result.text == "这是第一页内容。\n第二行。"
        assert result.page_count == 1
        assert result.scanned is False
        assert result.filename == "test.pdf"
        assert result.extension == ".pdf"
        assert result.size_bytes > 0
        assert result.doc_type == "textbook"

    # ── DOCX ───────────────────────────────────────────────────────────

    @patch("backend.document.parser.DocxDocument")
    def test_normal_docx(
        self, mock_docx: MagicMock, parser: DocumentParser, tmp_path: str
    ) -> None:
        """正常 DOCX 解析：mock python-docx 返回段落列表。"""
        docx_file = tmp_path / "test.docx"
        docx_file.write_text("dummy")

        # mock python-docx Document 对象
        mock_para1 = MagicMock()
        mock_para1.text = "第一段落"
        mock_para2 = MagicMock()
        mock_para2.text = "第二段落"
        mock_para3 = MagicMock()
        mock_para3.text = ""  # 空段落应被跳过

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]
        mock_docx.return_value = mock_doc

        result = parser.parse(str(docx_file), doc_type="past_paper")

        assert result.text == "第一段落\n第二段落"
        assert result.page_count == 0
        assert result.scanned is False
        assert result.extension == ".docx"
        assert result.doc_type == "past_paper"

    # ── Markdown ───────────────────────────────────────────────────────

    def test_normal_markdown(self, parser: DocumentParser, tmp_path: str) -> None:
        """正常 MD 解析：直接读取文件内容。"""
        md_file = tmp_path / "test.md"
        md_file.write_text("# 第一章\n\n这是正文内容。", encoding="utf-8")

        result = parser.parse(str(md_file))

        assert result.text == "# 第一章\n\n这是正文内容。"
        assert result.extension == ".md"
        assert result.scanned is False

    # ── TXT ────────────────────────────────────────────────────────────

    def test_normal_txt(self, parser: DocumentParser, tmp_path: str) -> None:
        """正常 TXT 解析：直接读取文件内容。"""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("纯文本内容。", encoding="utf-8")

        result = parser.parse(str(txt_file))

        assert result.text == "纯文本内容。"
        assert result.extension == ".txt"

    # ── pathlib.Path 输入 ──────────────────────────────────────────────

    @patch("backend.document.parser.fitz.open")
    def test_accepts_pathlike(
        self, mock_fitz_open: MagicMock, parser: DocumentParser, tmp_path: str
    ) -> None:
        """验证 parse() 接受 pathlib.Path 而非仅 str。"""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("dummy")

        mock_page = MagicMock()
        mock_page.get_text.return_value = "content"
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.load_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        # 传入 pathlib.Path 对象
        import pathlib

        result = parser.parse(pathlib.Path(str(pdf_file)))
        assert result.text == "content"


# ── 边界情况测试（TECH_DESIGN.md 第 9 节）────────────────────────────────────


class TestParseEdgeCases:
    """TECH_DESIGN.md 第 9 节边界情况：① 扫描件 ② 加密 ③ 文件过大。"""

    # ── ① 扫描版 PDF ─────────────────────────────────────────────────

    @patch("backend.document.parser.fitz.open")
    def test_scanned_pdf(
        self, mock_fitz_open: MagicMock, parser: DocumentParser, tmp_path: str
    ) -> None:
        """① 扫描版 PDF（无文字层）：fitz 提取后 text.strip()=="" → scanned=True。

        模拟 3 页 PDF，每页 get_text() 返回空字符串。
        """
        pdf_file = tmp_path / "scanned.pdf"
        pdf_file.write_text("dummy")

        mock_page = MagicMock()
        mock_page.get_text.return_value = ""  # 无文字层
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 3
        mock_doc.load_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        result = parser.parse(str(pdf_file))

        assert result.text == "\n\n"  # 3 页空文本用换行符连接
        # 空字符串 strip() 后为 ""，触发 scanned=True
        assert result.scanned is True
        assert result.page_count == 3

    # ── ② 加密 PDF ───────────────────────────────────────────────────

    @patch("backend.document.parser.fitz.open")
    @pytest.mark.parametrize(
        "exception_class, error_message",
        [
            # fitz.FileDataError（高版本 PyMuPDF）
            (__import__("fitz").FileDataError, "password required"),
            # RuntimeError（部分旧版本 PyMuPDF）
            (RuntimeError, "Password is needed"),
            # 大小写不同的 message 也要能识别
            (RuntimeError, "ENCRYPTED PDF"),
        ],
    )
    def test_encrypted_pdf(
        self,
        mock_fitz_open: MagicMock,
        parser: DocumentParser,
        tmp_path: str,
        exception_class: type,
        error_message: str,
    ) -> None:
        """② 加密 PDF：fitz.open() 抛异常含 password/encrypted → PermissionError。

        参数化测试覆盖：
        - 不同异常类（FileDataError / RuntimeError）
        - 不同大小写的错误消息
        """
        pdf_file = tmp_path / "encrypted.pdf"
        pdf_file.write_text("dummy")

        mock_fitz_open.side_effect = exception_class(error_message)

        with pytest.raises(PermissionError, match="PDF 已加密"):
            parser.parse(str(pdf_file))

    # ── ③ 文件 >200MB ────────────────────────────────────────────────

    def test_file_too_large(
        self, parser: DocumentParser, tmp_path: str
    ) -> None:
        """③ 文件 >200MB：将 MAX_FILE_SIZE 临时设为极小值，触发校验失败。"""
        pdf_file = tmp_path / "large.pdf"
        pdf_file.write_text("small content")  # 实际文件很小

        # 将阈值设为 1 byte，任何非空文件都会触发
        original_limit = parser.MAX_FILE_SIZE
        parser.MAX_FILE_SIZE = 1

        try:
            with pytest.raises(ValueError, match="文件过大"):
                parser.parse(str(pdf_file))
        finally:
            parser.MAX_FILE_SIZE = original_limit


# ── 异常输入测试（扩展名/文件不存在）───────────────────────────────────────────


class TestParseInvalidInput:
    """非法输入测试：扩展名不支持、文件不存在。"""

    def test_unsupported_extension(
        self, parser: DocumentParser, tmp_path: str
    ) -> None:
        """扩展名不在 SUPPORTED_EXTENSIONS 中 → ValueError。"""
        unsupported_file = tmp_path / "test.xyz"
        unsupported_file.write_text("dummy")

        with pytest.raises(ValueError, match="不支持的文件格式"):
            parser.parse(str(unsupported_file))

    def test_file_not_found(self, parser: DocumentParser) -> None:
        """文件不存在 → FileNotFoundError。"""
        with pytest.raises(FileNotFoundError, match="文件不存在"):
            parser.parse("/not/exist/file.pdf")


# ── ParsedDocument 模型测试 ─────────────────────────────────────────────────


class TestParsedDocument:
    """Pydantic 模型校验。"""

    def test_default_values(self) -> None:
        """验证默认值正确。"""
        doc = ParsedDocument(text="hello", filename="test.pdf", extension=".pdf")
        assert doc.page_count == 0
        assert doc.size_bytes == 0
        assert doc.scanned is False
        assert doc.doc_type == "textbook"

    def test_requires_required_fields(self) -> None:
        """验证必填字段不可缺失。"""
        with pytest.raises(Exception):
            ParsedDocument()  # type: ignore[call-arg]

    def test_doc_type_validation(self) -> None:
        """验证 doc_type 仅接受 textbook 或 past_paper。"""
        with pytest.raises(Exception):
            ParsedDocument(
                text="hello",
                filename="test.pdf",
                extension=".pdf",
                doc_type="invalid",  # type: ignore[arg-type]
            )
