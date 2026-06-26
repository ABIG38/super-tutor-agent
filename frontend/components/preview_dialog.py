"""
文档预览对话框 — DocumentPreviewDialog

双击文档树中的文件时打开，显示解析后的纯文本内容。
支持 Markdown 和纯文本两种视图模式。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextBrowser,
    QPushButton, QLabel, QMessageBox,
)
from frontend.theme import COLORS


class DocumentPreviewDialog(QDialog):
    """★ F-05: 文档预览弹窗。

    显示重新解析后的文档纯文本内容。
    """

    def __init__(
        self,
        title: str,
        text: str,
        size: int,
        scanned: bool = False,
        is_markdown: bool = False,
        original_path: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"📖 {title}")
        self.setMinimumSize(800, 600)
        self.resize(960, 720)
        self._setup_ui(title, text, size, scanned, is_markdown, original_path)

    def _setup_ui(self, title: str, text: str, size: int, scanned: bool, is_markdown: bool, original_path: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 元信息
        info_layout = QHBoxLayout()
        info_text = f"字符数: {size:,}"
        if scanned:
            info_text += "  |  ⚠️ 扫描件（无文字层）"
        info_label = QLabel(info_text)
        info_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        info_layout.addWidget(info_label)
        info_layout.addStretch()

        # 原文件按钮
        if original_path:
            self.btn_open = QPushButton("📂 打开原文件")
            self.btn_open.setFixedSize(90, 30)
            self.btn_open.setStyleSheet(f"""
                QPushButton {{ background-color: transparent; color: {COLORS['accent']};
                    border: 1px solid {COLORS['accent']}; border-radius: 4px;
                    font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
                QPushButton:hover {{ background-color: {COLORS['accent']}; color: {COLORS['bg_primary']}; }}
            """)
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            self.btn_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(original_path)))
            info_layout.addWidget(self.btn_open)

        # 导出按钮
        self.btn_export = QPushButton("💾 导出")
        self.btn_export.setFixedSize(80, 30)
        self.btn_export.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']}; border-radius: 4px;
                font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; border-color: {COLORS['accent']}; }}
        """)
        self.btn_export.clicked.connect(lambda: self._export_file(title, text))
        info_layout.addWidget(self.btn_export)

        # 关闭按钮
        btn_close = QPushButton("✕ 关闭")
        btn_close.setFixedSize(80, 30)
        btn_close.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']}; border-radius: 4px;
                font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; border-color: {COLORS['accent']}; }}
        """)
        btn_close.clicked.connect(self.close)
        info_layout.addWidget(btn_close)
        layout.addLayout(info_layout)

        # 文本浏览器
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border_light']};
                border-radius: 8px;
                padding: 20px;
                font-size: 13px;
                line-height: 1.7;
                color: {COLORS['text_primary']};
                font-family: system-ui, -apple-system, 'PingFang SC', sans-serif;
            }}
        """)

        if scanned:
            self.browser.setPlainText(
                "⚠️ 该文档为扫描件 PDF，未检测到可提取的文字内容。\n\n"
                "如需识别文字，请使用 OCR 软件处理后重新上传。"
            )
        else:
            content = text[:100_000]
            if len(text) > 100_000:
                content += f"\n\n... (仅显示前 100,000 字符，全文共 {len(text):,} 字符)"
                
            if is_markdown:
                # Markdown → HTML 渲染
                try:
                    import markdown
                    html = markdown.markdown(
                        content,
                        extensions=["extra", "tables", "fenced_code", "codehilite"],
                    )
                    styled = f"""<html><head><style>
                        pre {{ background-color: {COLORS['bg_primary']}; padding: 12px; border-radius: 6px; border: 1px solid {COLORS['border']}; overflow-x: auto; font-family: Consolas, monospace; }}
                        code {{ background-color: {COLORS['bg_primary']}; padding: 2px 4px; border-radius: 4px; font-family: Consolas, monospace; color: {COLORS['accent_hover']}; }}
                        pre code {{ background-color: transparent; padding: 0; color: {COLORS['text_primary']}; }}
                        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                        th, td {{ border: 1px solid {COLORS['border']}; padding: 8px; text-align: left; }}
                        th {{ background-color: {COLORS['bg_primary']}; }}
                        blockquote {{ border-left: 4px solid {COLORS['accent']}; margin: 0; padding-left: 12px; color: {COLORS['text_secondary']}; }}
                    </style></head><body style="background:{COLORS['bg_card']};color:{COLORS['text_primary']};
                        font-size:14px;line-height:1.8;padding:20px;
                        font-family:'Segoe UI','PingFang SC',sans-serif;">
                        {html}</body></html>"""
                    self.browser.setHtml(styled)
                except ImportError:
                    self.browser.setPlainText(content)
            else:
                # 纯文本渲染（防止 PDF 里的 < > 符号被误认为是 HTML 标签导致截断）
                self.browser.setPlainText(content)
        layout.addWidget(self.browser, stretch=1)

        # 底部提示
        hint = QLabel("💡 仅显示解析后的文本，图片/公式/图表未渲染")
        hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 9px; font-weight: 600; letter-spacing: 0.5px;"
        )
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

    def _export_file(self, title: str, text: str) -> None:
        from PySide6.QtWidgets import QFileDialog
        default_name = title if title.endswith(".md") else f"{title}.md"
        path, _ = QFileDialog.getSaveFileName(self, "导出文件", default_name, "Markdown Files (*.md);;Text Files (*.txt);;All Files (*)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                QMessageBox.information(self, "导出成功", f"文件已成功导出至:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "导出失败", f"导出过程中发生错误：\n{e}")
