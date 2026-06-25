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
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"📖 {title}")
        self.setMinimumSize(800, 600)
        self.resize(960, 720)
        self._setup_ui(text, size, scanned)

    def _setup_ui(self, text: str, size: int, scanned: bool) -> None:
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
            "color: #55555a; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        info_layout.addWidget(info_label)
        info_layout.addStretch()

        # 关闭按钮
        btn_close = QPushButton("✕ 关闭")
        btn_close.setFixedSize(80, 30)
        btn_close.setStyleSheet("""
            QPushButton { background-color: transparent; color: #a0a0a5;
                border: 1px solid #1f1f22; border-radius: 4px;
                font-size: 10px; font-weight: 700; letter-spacing: 1px; }
            QPushButton:hover { color: #fcfcfc; border-color: #ccff00; }
        """)
        btn_close.clicked.connect(self.close)
        info_layout.addWidget(btn_close)
        layout.addLayout(info_layout)

        # 文本浏览器
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: #0a0a0c;
                border: 1px solid #1f1f22;
                border-radius: 8px;
                padding: 20px;
                font-size: 13px;
                line-height: 1.7;
                color: #e8eaf0;
                font-family: 'Segoe UI', 'PingFang SC', monospace;
            }
        """)

        if scanned:
            self.browser.setPlainText(
                "⚠️ 该文档为扫描件 PDF，未检测到可提取的文字内容。\n\n"
                "如需识别文字，请使用 OCR 软件处理后重新上传。"
            )
        else:
            # 显示纯文本（保留换行和缩进）
            self.browser.setPlainText(text[:100_000])  # 截断防止卡 UI
            if len(text) > 100_000:
                self.browser.append(
                    f"\n\n... (仅显示前 100,000 字符，全文共 {len(text):,} 字符)"
                )
        layout.addWidget(self.browser, stretch=1)

        # 底部提示
        hint = QLabel("💡 仅显示解析后的纯文本，图片/公式/图表未渲染")
        hint.setStyleSheet(
            "color: #55555a; font-size: 9px; font-weight: 600; letter-spacing: 0.5px;"
        )
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
