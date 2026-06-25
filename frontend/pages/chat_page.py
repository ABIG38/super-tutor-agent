"""
问答页 — 聊天界面 + 流式渲染。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextBrowser, QLineEdit, QPushButton, QLabel,
)


class ChatPage(QWidget):
    """问答 Tab 页 — 对接 BackgroundWorker 流式问答。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker = None
        self._course = ""
        self._assistant_started = False
        self._setup_ui()

    def set_worker(self, worker) -> None:
        """★ 注入后台 worker 并连接信号。"""
        self._worker = worker
        self._worker.ask_token.connect(self._on_token)
        self._worker.ask_done.connect(self._on_ask_done)
        self._worker.ask_error.connect(self._on_ask_error)

    def set_course(self, course: str) -> None:
        self._course = course

    # ── UI ────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(16)

        self.status_label = QLabel("等待输入")
        self.status_label.setStyleSheet(
            "color: #55555a; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        layout.addWidget(self.status_label)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: transparent; border: none;
                font-size: 14px; line-height: 1.8; color: #fcfcfc;
                selection-background-color: #ccff0040;
            }
        """)
        layout.addWidget(self.browser, stretch=1)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(12)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("输入您的问题...")
        self.input_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #1f1f22; border-radius: 8px;
                padding: 12px 20px; font-size: 13px;
                background-color: #0f0f11; color: #fcfcfc;
                font-family: 'Inter', 'Segoe UI';
            }
            QLineEdit:focus { border-color: #ccff00; background-color: #141417; }
            QLineEdit::placeholder { color: #55555a; font-weight: 600; }
        """)
        self.input_edit.returnPressed.connect(self._send)
        input_layout.addWidget(self.input_edit, stretch=1)

        self.btn_send = QPushButton("发送")
        self.btn_send.setFixedSize(100, 42)
        self.btn_send.setStyleSheet("""
            QPushButton { background-color: #ccff00; color: #050505; border: none;
                border-radius: 8px; font-size: 12px; font-weight: 800; letter-spacing: 2px; }
            QPushButton:hover { background-color: #d9ff33; }
            QPushButton:disabled { background-color: #1f1f22; color: #55555a; }
        """)
        self.btn_send.clicked.connect(self._send)
        input_layout.addWidget(self.btn_send)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setFixedSize(80, 42)
        self.btn_stop.setStyleSheet("""
            QPushButton { background-color: transparent; color: #ff3333;
                border: 1px solid #ff3333; border-radius: 8px;
                font-size: 12px; font-weight: 800; letter-spacing: 2px; }
            QPushButton:hover { background-color: #ff333315; }
        """)
        self.btn_stop.clicked.connect(self._stop)
        input_layout.addWidget(self.btn_stop)

        layout.addLayout(input_layout)
        self._show_welcome()

    # ── 交互 ──────────────────────────────────────

    def _send(self) -> None:
        query = self.input_edit.text().strip()
        if not query:
            return
        if self._worker is None:
            self._show_error("系统未初始化，请重启应用")
            return

        self.input_edit.setEnabled(False)
        self.btn_send.setEnabled(False)

        self.add_user_message(query)
        self._start_assistant_block()
        self._worker.ask_async(query, course=self._course)
        self.input_edit.clear()

    def _stop(self) -> None:
        if self._worker:
            self._worker.cancel_ask()
        self._finish_assistant()

    # ── 信号回调 ──────────────────────────────────

    def _on_token(self, token: str) -> None:
        if not self._assistant_started:
            self._start_assistant_block()
        cursor = self.browser.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.browser.setTextCursor(cursor)
        sb = self.browser.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_ask_done(self) -> None:
        self._finish_assistant()
        self.status_label.setText("回答完成")

    def _on_ask_error(self, msg: str) -> None:
        self._finish_assistant()
        self._show_error(msg)

    def _finish_assistant(self) -> None:
        self.input_edit.setEnabled(True)
        self.btn_send.setEnabled(True)
        self._assistant_started = False

    # ── 显示 ──────────────────────────────────────

    def _start_assistant_block(self) -> None:
        self._assistant_started = True
        self.browser.append(
            '<div style="margin: 8px 0; color: #ccff00; font-size: 10px; '
            'font-weight: 700; letter-spacing: 1px;">助 手</div>'
        )

    def _show_welcome(self) -> None:
        self.browser.setHtml("""
            <div style="text-align: left; padding: 40px 0; color: #55555a;">
                <h1 style="color: #fcfcfc; margin-bottom: 8px; font-weight: 800;
                    font-size: 32px; letter-spacing: 2px;">超级导师 v2</h1>
                <p style="font-size: 13px; margin-bottom: 32px; line-height: 1.6;">
                    系统初始化完毕。上传文档后即可开始提问。
                </p>
                <div style="display: inline-block; border: 1px solid #1f1f22;
                    border-radius: 4px; padding: 6px 12px; font-size: 10px;
                    font-weight: 700; letter-spacing: 1px; color: #a0a0a5;">
                    支持格式: PDF, DOCX, MD, TXT
                </div>
            </div>
        """)

    def add_user_message(self, text: str) -> None:
        self.browser.append(
            f'<div style="margin: 16px 0; padding: 16px 20px; '
            f'background-color: #0f0f11; border-radius: 8px; '
            f'border: 1px solid #1f1f22;">'
            f'<div style="color: #55555a; font-size: 10px; font-weight: 700; '
            f'letter-spacing: 2px; margin-bottom: 8px;">用 户</div>'
            f'<div style="color: #fcfcfc;">{text}</div></div>'
        )

    def _show_error(self, msg: str) -> None:
        self.browser.append(
            f'<div style="margin: 8px 0; padding: 12px 16px; '
            f'background-color: #ff333315; border: 1px solid #ff333340; '
            f'border-radius: 8px; color: #ff3333; font-size: 12px;">'
            f'⚠ {msg}</div>'
        )
        self.status_label.setText(f"错误: {msg}")
