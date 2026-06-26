"""
问答页 — 多会话 + 消息持久化。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QSplitter, QListWidget,
    QListWidgetItem, QLabel, QMenu, QMessageBox, QInputDialog, QCheckBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
import urllib.parse
import markdown
import html
import re
from frontend.theme import COLORS

from backend.chat_store import list_sessions, new_session, load_messages, rename_session, delete_session, append_message


class AskThread(QThread):
    token = Signal(str)
    done = Signal()
    error = Signal(str)

    def __init__(self, agent, query: str, course: str, enable_web_search: bool = False, history: list = None, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.query = query
        self.course = course
        self.enable_web_search = enable_web_search
        self.history = history or []

    def run(self):
        try:
            for t in self.agent.ask(self.query, self.course, self.enable_web_search, self.history):
                self.token.emit(t)
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class ChatPage(QWidget):
    plan_generated = Signal()  # ★ 计划生成后通知刷新知识库

    def __init__(self, parent=None):
        super().__init__(parent)
        self._agent = None
        self._course = ""
        self._thread = None
        self._current_session_id = None  # 当前会话 ID
        self._current_answer = ""        # 正在生成的回答
        self._history_html = ""          # 缓存历史记录的 HTML
        self._token_count = 0
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
        splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {COLORS['border_light']}; }}")

        # ── 左侧会话列表 ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(f"background-color: {COLORS['bg_primary']}; border-bottom: 1px solid {COLORS['border']};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        lbl = QLabel("💬 会话")
        lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px; font-weight: 700; letter-spacing: 2px;")
        hl.addWidget(lbl)
        hl.addStretch()
        self.btn_new = QPushButton("+")
        self.btn_new.setFixedSize(28, 28)
        self.btn_new.setStyleSheet(f"QPushButton {{ background: transparent; color: {COLORS['accent']}; border: 1px solid {COLORS['accent']}; border-radius: 4px; font-size: 14px; font-weight: 700; }} QPushButton:hover {{ background-color: {COLORS['accent']}; color: {COLORS['bg_primary']}; }}")
        self.btn_new.clicked.connect(self._new_session)
        hl.addWidget(self.btn_new)
        left_layout.addWidget(header)

        self.session_list = QListWidget()
        self.session_list.setStyleSheet(f"QListWidget {{ background-color: {COLORS['bg_secondary']}; border: none; font-size: 13px; font-family: system-ui, -apple-system, sans-serif; color: {COLORS['text_secondary']}; padding: 8px; outline: none; }} QListWidget::item {{ padding: 10px 14px; border-radius: 8px; margin: 2px 4px; }} QListWidget::item:hover {{ background-color: {COLORS['bg_tertiary']}; color: {COLORS['text_primary']}; }} QListWidget::item:selected {{ background-color: {COLORS['accent_muted']}; color: {COLORS['accent']}; font-weight: bold; }}")
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

        self.browser = QWebEngineView()
        self.browser.page().setBackgroundColor(Qt.transparent)
        right_layout.addWidget(self.browser, stretch=1)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("输入您的问题...")
        self.input_edit.setStyleSheet(f"QLineEdit {{ border: 1px solid {COLORS['border']}; border-radius: 8px; padding: 12px 16px; font-size: 13px; background-color: {COLORS['bg_secondary']}; color: {COLORS['text_primary']}; }} QLineEdit:focus {{ border-color: {COLORS['accent']}; }}")
        self.input_edit.returnPressed.connect(self._send)
        input_layout.addWidget(self.input_edit, stretch=1)
        
        self.cb_web_search = QCheckBox("🌐 允许网络搜索")
        self.cb_web_search.setStyleSheet(f"QCheckBox {{ color: {COLORS['text_secondary']}; font-size: 12px; }}")
        input_layout.addWidget(self.cb_web_search)

        self.btn_clear = QPushButton("🗑️ 清空对话")
        self.btn_clear.setFixedSize(80, 42)
        self.btn_clear.setToolTip("清空当前对话的所有消息")
        self.btn_clear.setStyleSheet(f"QPushButton {{ background-color: transparent; color: {COLORS['error']}; border: 1px solid {COLORS['border']}; border-radius: 8px; font-size: 12px; }} QPushButton:hover {{ border-color: {COLORS['error']}; }}")
        self.btn_clear.clicked.connect(self._clear_conversation)
        input_layout.addWidget(self.btn_clear)

        self.btn_send = QPushButton("发送")
        self.btn_send.setFixedSize(80, 42)
        self.btn_send.setStyleSheet(f"QPushButton {{ background-color: {COLORS['accent']}; color: {COLORS['bg_primary']}; border: none; border-radius: 8px; font-size: 12px; font-weight: 800; }} QPushButton:hover {{ background-color: {COLORS['accent_hover']}; }}")
        self.btn_send.clicked.connect(self._send)
        input_layout.addWidget(self.btn_send)

        self.btn_stop = QPushButton("■")
        self.btn_stop.setFixedSize(42, 42)
        self.btn_stop.setToolTip("停止生成")
        self.btn_stop.setStyleSheet(f"QPushButton {{ background-color: transparent; color: {COLORS['error']}; border: 1px solid {COLORS['error']}; border-radius: 8px; font-size: 14px; font-weight: 800; }}")
        self.btn_stop.clicked.connect(self._stop)
        input_layout.addWidget(self.btn_stop)

        right_layout.addLayout(input_layout)
        splitter.addWidget(right)
        splitter.setSizes([180, 620])

        layout.addWidget(splitter)

    def _clear_conversation(self):
        if not self._current_session_id:
            return
        if QMessageBox.question(self, "确认", "确定要清空当前对话的所有消息吗？", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                if hasattr(self, '_agent') and self._agent:
                    self._agent.chat_clear(self._current_session_id)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"清空对话失败：{e}")
                return
            
            # 清空界面状态并重置为欢迎页
            self._history_html = ""
            self._current_answer = ""
            self._welcome()

    # ── 会话管理 ──────────────────────────────

    def _load_sessions(self):
        self.session_list.clear()
        sessions = list_sessions()
        if not sessions:
            # 静默创建默认会话，不弹输入框
            session = new_session("会话 1")
            item = QListWidgetItem(f"💬 {session['name']}")
            item.setData(Qt.UserRole, session["id"])
            self.session_list.addItem(item)
            self.session_list.setCurrentItem(item)
            self._switch_session(item)
            return
        for s in sessions:
            item = QListWidgetItem(f"💬 {s['name']}")
            item.setData(Qt.UserRole, s["id"])
            self.session_list.addItem(item)
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
        self._history_html = ""
        # 加载历史消息
        msgs = load_messages(sid)
        for msg in msgs:
            self._history_html += self._render_message_html(msg["role"], msg["content"], False)
            
        self._page_loaded = False
        
        if self._history_html:
            self._render_all()
        else:
            self._welcome()

    def _render_all(self):
        html_content = self._history_html
        if self._current_answer:
            html_content += self._render_message_html("assistant", self._current_answer, True)
            
        if not hasattr(self, '_page_loaded') or not self._page_loaded:
            base_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <meta charset="utf-8">
            <style>
            body {{ background-color: transparent; font-family: system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; margin: 0; padding: 10px; color: {COLORS['text_primary']}; }}
            h1, h2, h3, h4, h5, h6 {{ font-family: 'Georgia', 'Times New Roman', serif; color: {COLORS['text_primary']}; }}
            details {{ margin-bottom: 12px; background: {COLORS['bg_secondary']}; border-left: 3px solid {COLORS['accent']}; border-radius: 4px; padding: 10px; border: 1px solid {COLORS['border_light']}; }}
            summary {{ cursor: pointer; font-weight: bold; color: {COLORS['text_secondary']}; font-size: 12px; outline: none; margin-bottom: 6px; font-family: 'Georgia', 'Times New Roman', serif; }}
            a {{ color: {COLORS['accent']}; text-decoration: none; }}
            pre {{ background: {COLORS['bg_secondary']}; padding: 12px; border-radius: 8px; border: 1px solid {COLORS['border']}; overflow-x: auto; }}
            code {{ font-family: 'Consolas', monospace; }}
            </style>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
            <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
            <script>
            function updateContent(html) {{
                document.body.innerHTML = html;
                renderMathInElement(document.body, {{
                  delimiters: [
                      {{left: '$$', right: '$$', display: true}},
                      {{left: '$', right: '$', display: false}}
                  ],
                  throwOnError: false
                }});
                window.scrollTo(0, document.body.scrollHeight);
            }}
            window.onload = function() {{
                renderMathInElement(document.body, {{
                  delimiters: [
                      {{left: '$$', right: '$$', display: true}},
                      {{left: '$', right: '$', display: false}}
                  ],
                  throwOnError: false
                }});
                window.scrollTo(0, document.body.scrollHeight);
            }};
            </script>
            </head>
            <body>{html_content}</body>
            </html>
            """
            self.browser.setHtml(base_html)
            self._page_loaded = True
        else:
            encoded = urllib.parse.quote(html_content)
            js = f"if(typeof updateContent === 'function') {{ updateContent(decodeURIComponent('{encoded}')); }}"
            self.browser.page().runJavaScript(js)

    def _session_menu(self, pos):
        item = self.session_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; color: {COLORS['text_secondary']}; }} QMenu::item:selected {{ background-color: {COLORS['bg_tertiary']}; color: {COLORS['text_primary']}; }}")
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
        welcome_html = f'<div style="text-align:left;padding:40px 0;color:{COLORS["text_secondary"]};"><h1 style="color:{COLORS["text_primary"]};font-family:\'Georgia\', serif;font-weight:800;font-size:28px;">AgentOS Tutor</h1><p style="font-size:14px;">上传文档后即可提问，知识库已接入。</p></div>'
        encoded = urllib.parse.quote(welcome_html)
        js = f"setTimeout(function() {{ if(typeof updateContent === 'function') updateContent(decodeURIComponent('{encoded}')); }}, 100);"
        self.browser.page().runJavaScript(js)

    def _send(self):
        query = self.input_edit.text().strip()
        if not query:
            return
        if self._agent is None:
            from backend.agent.orchestrator import SuperTutorAgent
            self._agent = SuperTutorAgent()
        if not self._current_session_id:
            s = new_session("会话 1")
            item = QListWidgetItem(f"💬 {s['name']}")
            item.setData(Qt.UserRole, s["id"])
            self.session_list.addItem(item)
            self.session_list.setCurrentItem(item)
            self._switch_session(item)

        self.input_edit.setEnabled(False)
        self.btn_send.setEnabled(False)

        # 获取历史记录（在追加当前消息前获取，避免重复）
        history_msgs = load_messages(self._current_session_id)

        # 保存用户消息
        append_message(self._current_session_id, "user", query)
        self._history_html += self._render_message_html("user", query, False)
        self._render_all()

        self._current_answer = ""
        self._token_count = 0
        
        enable_web_search = self.cb_web_search.isChecked()
        self._thread = AskThread(self._agent, query, self._course, enable_web_search, history_msgs)
        self._thread.token.connect(self._on_token)
        self._thread.done.connect(self._on_done)
        self._thread.error.connect(self._on_error)
        self._thread.finished.connect(self._finish)
        self._thread.start()
        self.input_edit.clear()

    def _on_token(self, t: str):
        self._current_answer += t
        self._token_count += 1
        
        if self._token_count % 3 == 0:
            self._render_all()

    def _on_done(self):
        if self._current_answer and self._current_session_id:
            append_message(self._current_session_id, "assistant", self._current_answer)
            self._history_html += self._render_message_html("assistant", self._current_answer, False)
            self._current_answer = ""
            self._render_all()
        self._current_answer = ""

    def _on_error(self, msg: str):
        error_html = f'<div style="color:{COLORS["error"]};margin:8px 0;">⚠ {msg}</div>'
        self._history_html += error_html
        self._render_all()

    def _stop(self):
        if self._agent:
            self._agent.cancel_stream()
        self._finish()

    def _finish(self):
        self.input_edit.setEnabled(True)
        self.btn_send.setEnabled(True)

    def _render_message_html(self, role: str, content: str, is_streaming: bool) -> str:
        if role == "user":
            return f'<div style="margin:16px 0;padding:16px 20px;background-color:{COLORS["bg_secondary"]};border-radius:12px;border:1px solid {COLORS["border_light"]};"><div style="color:{COLORS["text_secondary"]};font-size:11px;font-weight:700;margin-bottom:8px;font-family:\'Georgia\', serif;letter-spacing:1px;">USER</div><div style="color:{COLORS["text_primary"]};white-space:pre-wrap;font-size:14px;">{html.escape(content)}</div></div>'
        else:
            # 解析 <think> 块
            think_text = ""
            match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
            if match:
                think_text = match.group(1).strip()
                content = content.replace(match.group(0), "").strip()
            else:
                match_open = re.search(r'<think>(.*)', content, re.DOTALL)
                if match_open:
                    think_text = match_open.group(1).strip()
                    content = content.replace(match_open.group(0), "").strip()

            cursor = " █" if is_streaming else ""
            main_html = markdown.markdown(content + cursor, extensions=["extra", "tables", "fenced_code"]) if content or is_streaming else ""

            think_html = ""
            if think_text or (is_streaming and not main_html):
                display_think = think_text if think_text else "..."
                cursor_think = " █" if is_streaming and not main_html else ""
                # 使用 HTML5 <details> 和 <summary>
                think_html = f'''
                <details {'open' if is_streaming else ''}>
                    <summary>THINKING PROCESS</summary>
                    <div style="color: {COLORS['text_secondary']}; font-size: 13px; line-height: 1.6; white-space: pre-wrap; margin-top: 8px;">{html.escape(display_think)}{cursor_think}</div>
                </details>
                '''

            return f'<div style="margin:16px 0;padding:16px 20px;background-color:{COLORS["bg_card"]};border:1px solid {COLORS["border"]};border-radius:12px;box-shadow: 0 2px 8px rgba(0,0,0,0.02);"><div style="color:{COLORS["accent"]};font-size:11px;font-weight:700;margin-bottom:8px;font-family:\'Georgia\', serif;letter-spacing:1px;">AGENTOS TUTOR</div>{think_html}<div style="color:{COLORS["text_primary"]};font-size:14px;line-height:1.8;">{main_html}</div></div>'
