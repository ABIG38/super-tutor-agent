"""
问答页 — 多会话 + 消息持久化。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTextBrowser, QLineEdit, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
)

from backend.chat_store import *


class AskThread(QThread):
    token = Signal(str)
    done = Signal()
    error = Signal(str)

    def __init__(self, agent, query, course):
        super().__init__()
        self._agent = agent
        self._query = query
        self._course = course

    def run(self):
        try:
            for t in self._agent.ask(self._query, course=self._course):
                self.token.emit(t)
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class ChatPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._agent = None
        self._course = ""
        self._thread = None
        self._current_session_id = None  # 当前会话 ID
        self._current_answer = ""        # 正在生成的回答
        self._setup_ui()
        self._load_sessions()

    def set_agent(self, agent):
        self._agent = agent

    def set_course(self, course: str):
        self._course = course

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 会话列表 + 聊天区分栏
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #1f1f22; }")

        # ── 左侧会话列表 ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background-color: #050505; border-bottom: 1px solid #1f1f22;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        lbl = QLabel("💬 会话")
        lbl.setStyleSheet("color: #a0a0a5; font-size: 11px; font-weight: 700; letter-spacing: 2px;")
        hl.addWidget(lbl)
        hl.addStretch()
        self.btn_new = QPushButton("+")
        self.btn_new.setFixedSize(28, 28)
        self.btn_new.setStyleSheet("QPushButton { background: transparent; color: #ccff00; border: 1px solid #ccff00; border-radius: 4px; font-size: 14px; font-weight: 700; } QPushButton:hover { background-color: #ccff00; color: #050505; }")
        self.btn_new.clicked.connect(self._new_session)
        hl.addWidget(self.btn_new)
        left_layout.addWidget(header)

        self.session_list = QListWidget()
        self.session_list.setStyleSheet("QListWidget { background-color: #0f0f11; border: none; font-size: 12px; color: #a0a0a5; padding: 8px; outline: none; } QListWidget::item { padding: 10px 12px; border-radius: 4px; margin: 2px 4px; } QListWidget::item:hover { background-color: #1a1a1d; color: #fcfcfc; } QListWidget::item:selected { background-color: #ccff0015; color: #ccff00; }")
        self.session_list.itemClicked.connect(self._switch_session)
        self.session_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._session_menu)
        left_layout.addWidget(self.session_list)

        splitter.addWidget(left)

        # ── 右侧聊天区 ──
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(24, 32, 24, 24)
        right_layout.setSpacing(12)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("QTextBrowser { background-color: transparent; border: none; font-size: 14px; line-height: 1.8; color: #fcfcfc; }")
        right_layout.addWidget(self.browser, stretch=1)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("输入您的问题...")
        self.input_edit.setStyleSheet("QLineEdit { border: 1px solid #1f1f22; border-radius: 8px; padding: 12px 16px; font-size: 13px; background-color: #0f0f11; color: #fcfcfc; } QLineEdit:focus { border-color: #ccff00; }")
        self.input_edit.returnPressed.connect(self._send)
        input_layout.addWidget(self.input_edit, stretch=1)

        self.btn_plan = QPushButton("📅")
        self.btn_plan.setFixedSize(42, 42)
        self.btn_plan.setToolTip("生成学习计划")
        self.btn_plan.setStyleSheet("QPushButton { background-color: transparent; color: #ccff00; border: 1px solid #ccff00; border-radius: 8px; font-size: 16px; } QPushButton:hover { background-color: #ccff00; color: #050505; }")
        self.btn_plan.clicked.connect(self._generate_plan)
        input_layout.addWidget(self.btn_plan)

        self.btn_send = QPushButton("发送")
        self.btn_send.setFixedSize(80, 42)
        self.btn_send.setStyleSheet("QPushButton { background-color: #ccff00; color: #050505; border: none; border-radius: 8px; font-size: 12px; font-weight: 800; } QPushButton:hover { background-color: #d9ff33; }")
        self.btn_send.clicked.connect(self._send)
        input_layout.addWidget(self.btn_send)

        self.btn_stop = QPushButton("■")
        self.btn_stop.setFixedSize(42, 42)
        self.btn_stop.setToolTip("停止生成")
        self.btn_stop.setStyleSheet("QPushButton { background-color: transparent; color: #ff3333; border: 1px solid #ff3333; border-radius: 8px; font-size: 14px; font-weight: 800; }")
        self.btn_stop.clicked.connect(self._stop)
        input_layout.addWidget(self.btn_stop)

        right_layout.addLayout(input_layout)
        splitter.addWidget(right)
        splitter.setSizes([180, 620])

        layout.addWidget(splitter)

    # ── 会话管理 ──────────────────────────────

    def _load_sessions(self):
        self.session_list.clear()
        sessions = list_sessions()
        if not sessions:
            self._new_session()
            return
        for s in sessions:
            item = QListWidgetItem(f"💬 {s['name']}")
            item.setData(Qt.UserRole, s["id"])
            self.session_list.addItem(item)
        # 选中第一个
        self.session_list.setCurrentRow(0)
        self._switch_session(self.session_list.item(0))

    def _new_session(self):
        name, ok = QInputDialog.getText(self, "新会话", "会话名称：", text=f"会话 {len(list_sessions()) + 1}")
        if not ok or not name.strip():
            name = f"会话 {len(list_sessions()) + 1}"
        session = new_session(name.strip())
        item = QListWidgetItem(f"💬 {session['name']}")
        item.setData(Qt.UserRole, session["id"])
        self.session_list.addItem(item)
        self.session_list.setCurrentItem(item)
        self._switch_session(item)

    def _switch_session(self, item):
        if not item:
            return
        sid = item.data(Qt.UserRole)
        self._current_session_id = sid
        self._current_answer = ""
        self.browser.clear()
        # 加载历史消息
        for msg in load_messages(sid):
            self._render_message(msg["role"], msg["content"])
        if not load_messages(sid):
            self._welcome()

    def _session_menu(self, pos):
        item = self.session_list.itemAt(pos)
        if not item:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #0f0f11; border: 1px solid #1f1f22; color: #a0a0a5; } QMenu::item:selected { background-color: #1a1a1d; color: #fcfcfc; }")
        rename = menu.addAction("✏️ 重命名")
        delete = menu.addAction("🗑️ 删除")
        action = menu.exec(self.session_list.viewport().mapToGlobal(pos))
        sid = item.data(Qt.UserRole)
        if action == rename:
            name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=item.text().replace("💬 ", ""))
            if ok and name.strip():
                rename_session(sid, name.strip())
                item.setText(f"💬 {name.strip()}")
        elif action == delete:
            if QMessageBox.question(self, "确认", "删除此会话？", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                delete_session(sid)
                self.session_list.takeItem(self.session_list.row(item))
                if self.session_list.count() > 0:
                    self.session_list.setCurrentRow(0)
                    self._switch_session(self.session_list.item(0))
                else:
                    self._new_session()

    # ── 问答 ──────────────────────────────────

    def _welcome(self):
        self.browser.setHtml('<div style="text-align:left;padding:40px 0;color:#55555a;"><h1 style="color:#fcfcfc;font-weight:800;font-size:28px;">超级导师</h1><p style="font-size:13px;">上传文档后即可提问。</p></div>')

    def _send(self):
        query = self.input_edit.text().strip()
        if not query:
            return
        if self._agent is None:
            from backend.agent.orchestrator import SuperTutorAgent
            self._agent = SuperTutorAgent()
        if not self._current_session_id:
            self._new_session()

        self.input_edit.setEnabled(False)
        self.btn_send.setEnabled(False)

        # 保存用户消息
        append_message(self._current_session_id, "user", query)
        self._render_message("user", query)

        self._current_answer = ""
        self._start_assistant()

        self._thread = AskThread(self._agent, query, self._course)
        self._thread.token.connect(self._on_token)
        self._thread.done.connect(self._on_done)
        self._thread.error.connect(self._on_error)
        self._thread.finished.connect(self._finish)
        self._thread.start()
        self.input_edit.clear()

    def _on_token(self, t: str):
        self._current_answer += t
        cursor = self.browser.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(t)
        self.browser.setTextCursor(cursor)
        sb = self.browser.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_done(self):
        if self._current_answer and self._current_session_id:
            append_message(self._current_session_id, "assistant", self._current_answer)
        self._current_answer = ""

    def _on_error(self, msg: str):
        self.browser.append(f'<div style="color:#ff3333;margin:8px 0;">⚠ {msg}</div>')

    def _stop(self):
        if self._agent:
            self._agent.cancel_stream()
        self._finish()

    def _finish(self):
        self.input_edit.setEnabled(True)
        self.btn_send.setEnabled(True)

    def _render_message(self, role: str, content: str):
        if role == "user":
            self.browser.append(f'<div style="margin:12px 0;padding:14px 18px;background-color:#0f0f11;border-radius:8px;border:1px solid #1f1f22;"><div style="color:#55555a;font-size:10px;font-weight:700;margin-bottom:6px;">用 户</div><div style="color:#fcfcfc;white-space:pre-wrap;">{content}</div></div>')
        else:
            import html
            self.browser.append(f'<div style="margin:12px 0;padding:14px 18px;background-color:#0a0a0c;border:1px solid #1f1f22;border-radius:8px;"><div style="color:#ccff00;font-size:10px;font-weight:700;margin-bottom:6px;">助 手</div><div style="color:#e8eaf0;font-size:13px;line-height:1.7;white-space:pre-wrap;">{html.escape(content)}</div></div>')

    def _start_assistant(self):
        self.browser.append('<div style="margin:8px 0;color:#ccff00;font-size:10px;font-weight:700;">助 手</div>')

    def _generate_plan(self):
        if self._agent is None or not self._current_session_id:
            return
        days, ok = QInputDialog.getInt(self, "学习计划", "总天数：", 30, 1, 365)
        if not ok:
            return
        hours, ok = QInputDialog.getInt(self, "学习计划", "每天学习（小时）：", 2, 1, 16)
        if not ok:
            return

        self.btn_plan.setEnabled(False)
        query = f"📅 请为我制定 {days} 天、每天 {hours} 小时的学习计划"
        append_message(self._current_session_id, "user", query)
        self._render_message("user", query)
        self._start_assistant()
        self._current_answer = ""

        class PlanThread(QThread):
            done = Signal(str)
            def __init__(self, agent, days, hours, course):
                super().__init__()
                self._agent = agent
                self._days = days
                self._hours = hours
                self._course = course
            def run(self):
                try:
                    self.done.emit(self._agent.generate_plan(self._days, self._hours, self._course))
                except Exception as e:
                    self.done.emit(f"生成失败：{e}")

        t = PlanThread(self._agent, days, hours, self._course)
        t.done.connect(self._on_plan_done)
        t.start()

    def _on_plan_done(self, text: str):
        self.btn_plan.setEnabled(True)
        self._current_answer = text
        if self._current_session_id:
            append_message(self._current_session_id, "assistant", text)
        self._render_message("assistant", text)
        sb = self.browser.verticalScrollBar()
        sb.setValue(sb.maximum())
