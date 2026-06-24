"""
问答页 — 聊天界面 + 流式渲染 + 反馈按钮。

布局:
  ┌─ 状态标签 ──────────────────────────────────────┐
  ├─ 聊天记录（QTextBrowser，支持 Markdown）         │
  ├─ 反馈按钮 [👍] [👎] [🤷]                      │
  ├─ 输入框 + [发送] [■停止]                      │
  └──────────────────────────────────────────────┘
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextBrowser,
    QLineEdit,
    QPushButton,
    QLabel,
    QSizePolicy,
)


class ChatPage(QWidget):
    """问答 Tab 页。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 状态标签
        self.status_label = QLabel("💡 输入问题开始学习")
        self.status_label.setStyleSheet("color: #5a5e72; font-size: 12px; padding: 4px 0;")
        layout.addWidget(self.status_label)

        # 聊天记录
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: #1c2030;
                border: 1px solid #2a2e3d;
                border-radius: 10px;
                padding: 16px;
                font-size: 14px;
                line-height: 1.7;
                color: #e8eaf0;
                selection-background-color: #6c63ff40;
            }
        """)
        layout.addWidget(self.browser, stretch=1)

        # 反馈按钮（预留测验入口）
        feedback_layout = QHBoxLayout()
        feedback_layout.setSpacing(6)
        self.btn_quiz = QPushButton("  📝  做本章测验  ")
        self.btn_quiz.setFixedHeight(28)
        self.btn_quiz.setStyleSheet("""
            QPushButton {
                background-color: #1e2231;
                border: 1px solid #2a2e3d;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
                color: #8b8fa3;
            }
            QPushButton:hover {
                background-color: #242838;
                border-color: #6c63ff40;
                color: #e8eaf0;
            }
        """)
        feedback_layout.addWidget(self.btn_quiz)
        feedback_layout.addStretch()
        layout.addLayout(feedback_layout)

        # 输入区
        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("💬 输入问题...")
        self.input_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #2a2e3d;
                border-radius: 10px;
                padding: 10px 16px;
                font-size: 14px;
                background-color: #1c2030;
                color: #e8eaf0;
                selection-background-color: #6c63ff40;
            }
            QLineEdit:focus {
                border-color: #6c63ff;
            }
            QLineEdit::placeholder {
                color: #5a5e72;
            }
        """)
        input_layout.addWidget(self.input_edit, stretch=1)

        self.btn_send = QPushButton("  📤  发送  ")
        self.btn_send.setFixedHeight(40)
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #6c63ff;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 8px 22px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #7c73ff;
            }
            QPushButton:pressed {
                background-color: #5b52e8;
            }
            QPushButton:disabled {
                background-color: #2a2e3d;
                color: #5a5e72;
            }
        """)
        input_layout.addWidget(self.btn_send)

        self.btn_stop = QPushButton("  ■  停止  ")
        self.btn_stop.setFixedHeight(40)
        self.btn_stop.setToolTip("停止生成")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #f87171;
            }
            QPushButton:pressed {
                background-color: #dc2626;
            }
        """)
        input_layout.addWidget(self.btn_stop)

        layout.addLayout(input_layout)

        # 初始欢迎
        self._show_welcome()

    def _show_welcome(self) -> None:
        """显示欢迎信息。"""
        self.browser.setHtml("""
            <div style="text-align: center; padding: 60px 20px; color: #5a5e72;">
                <div style="font-size: 48px; margin-bottom: 16px;">🧠</div>
                <h2 style="color: #e8eaf0; margin-bottom: 8px; font-weight: 600;">超级导师</h2>
                <p style="font-size: 14px; margin-bottom: 24px;">上传文档后即可开始提问</p>
                <div style="display: inline-block; background-color: #1e2231; border: 1px solid #2a2e3d; border-radius: 8px; padding: 8px 16px; font-size: 12px;">
                    PDF · DOCX · Markdown · TXT
                </div>
            </div>
        """)

    def add_user_message(self, text: str) -> None:
        """添加用户消息。"""
        self.browser.append(
            f'<div style="margin: 10px 0; padding: 10px 14px; '
            f'background-color: #242838; border-radius: 10px; '
            f'border-left: 3px solid #6c63ff;">'
            f'<b style="color: #e8eaf0;">🧑 您</b><br><span style="color: #c8cad6;">{text}</span></div>'
        )

    def add_assistant_token(self, token: str) -> None:
        """追加助手 token（流式）。"""
        self.browser.insertPlainText(token)
        # 滚动到底部
        scrollbar = self.browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def add_assistant_done(self, full_text: str) -> None:
        """助手回答完成，添加来源标注。"""
        self.browser.append(
            f'<div style="margin: 6px 0; padding: 6px 10px; '
            f'font-size: 11px; color: #5a5e72; '
            f'background-color: #1e2231; border-radius: 6px; '
            f'border: 1px solid #2a2e3d;">'
            f'[来源: 文档自动标注]</div>'
        )
