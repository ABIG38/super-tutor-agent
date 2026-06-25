"""
超级导师主窗口 — 精简版。
"""
from __future__ import annotations

import sys
from loguru import logger

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTabWidget, QPushButton, QLabel, QFrame,
    QGraphicsDropShadowEffect, QMessageBox,
)
from PySide6.QtGui import QFont, QColor

from backend.agent.orchestrator import SuperTutorAgent
from backend.llm.client import LLMError
from frontend.components.course_selector import CourseSelector
from frontend.components.document_tree import DocumentTree
from frontend.components.settings_dialog import SettingsDialog
from frontend.pages.chat_page import ChatPage

COLORS = {
    "bg_primary": "#050505",
    "bg_secondary": "#0f0f11",
    "bg_tertiary": "#1a1a1d",
    "bg_card": "#0a0a0c",
    "accent": "#ccff00",
    "text_primary": "#fcfcfc",
    "text_secondary": "#a0a0a5",
    "text_muted": "#55555a",
    "border": "#1f1f22",
    "border_light": "#2a2a2e",
    "error": "#ff3333",
    "title_bg": "rgba(5, 5, 5, 0.90)",
}


class TitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        self._is_dragging = False
        self._drag_pos = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 0, 0)
        layout.setSpacing(12)
        self.setFixedHeight(56)

        self.icon_label = QLabel("▪")
        self.icon_label.setStyleSheet(f"color: {COLORS['accent']}; font-size: 20px; font-weight: 900;")
        layout.addWidget(self.icon_label)

        self.title_label = QLabel("超级导师")
        self.title_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 15px; font-family: 'Segoe UI'; font-weight: 800; letter-spacing: 2px;")
        layout.addWidget(self.title_label)

        self.course_selector = CourseSelector()
        layout.addWidget(self.course_selector)
        layout.addStretch()

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(36, 36)
        self.btn_settings.clicked.connect(self._open_settings)
        layout.addWidget(self.btn_settings)

        for icon, tip, cb in [
            ("—", "最小化", self._parent.showMinimized),
            ("□", "最大化", lambda: self._parent.showNormal() if getattr(self, '_max', False) else self._parent.showMaximized()),
            ("✕", "关闭", self._parent.close),
        ]:
            btn = QPushButton(icon)
            btn.setFixedSize(46, 36)
            btn.clicked.connect(cb)
            layout.addWidget(btn)
        self._max = False

        self.setStyleSheet(f"""
            TitleBar {{ background-color: {COLORS['title_bg']}; border-bottom: 1px solid {COLORS['border']}; }}
            TitleBar QPushButton {{ background: transparent; color: {COLORS['text_secondary']}; border: none; font-size: 13px; border-radius: 4px; }}
            TitleBar QPushButton:hover {{ background-color: {COLORS['bg_tertiary']}; color: {COLORS['text_primary']}; }}
        """)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()
            self._is_dragging = True

    def mouseMoveEvent(self, e):
        if self._is_dragging and self._drag_pos and self._parent:
            d = e.globalPosition().toPoint() - self._drag_pos
            self._parent.move(self._parent.pos() + d)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._is_dragging = False

    def _open_settings(self):
        SettingsDialog(self).exec()


class SuperTutorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.agent = SuperTutorAgent()
        self._setup_window()
        self._build_ui()
        self._startup_check()

    def _setup_window(self):
        self.setWindowTitle("SuperTutor")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)

    def _build_ui(self):
        outer = QWidget()
        outer.setObjectName("outer")
        outer.setStyleSheet(f"#outer {{ background-color: {COLORS['bg_primary']}; border: 1px solid {COLORS['border_light']}; border-radius: 12px; }}")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(60)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(0, 10)
        outer.setGraphicsEffect(shadow)

        layout = QVBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {COLORS['border']}; }}")

        self.doc_tree = DocumentTree(self.agent)
        splitter.addWidget(self.doc_tree)
        self.chat_page = ChatPage()
        self.chat_page.set_agent(self.agent)
        self.chat_page.plan_generated.connect(lambda: self.doc_tree._refresh())  # ★ 计划生成后刷新树
        splitter.addWidget(self.chat_page)
        splitter.setSizes([260, 740])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, stretch=1)

        # 状态栏
        self._status = QLabel("系统就绪")
        self._status.setFixedHeight(32)
        self._status.setStyleSheet(f"background-color: {COLORS['bg_secondary']}; border-top: 1px solid {COLORS['border']}; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; padding-left: 20px; color: {COLORS['text_muted']}; font-size: 11px; font-weight: 600;")
        layout.addWidget(self._status)

        self.setCentralWidget(outer)

        # 信号
        self.title_bar.course_selector.course_changed.connect(self._on_course_change)

    def _startup_check(self):
        from pathlib import Path
        from backend.model_checker import check_models
        cfg = __import__("backend.config", fromlist=["settings"]).settings

        # 1. API Key
        if not Path(".env").exists() or cfg.llm_api_key == "MISSING_KEY":
            QMessageBox.question(self, "⚙️ 首次配置", "未检测到 API Key。是否现在配置？", QMessageBox.Yes) and \
                SettingsDialog(self).exec()

        # 2. 模型检测
        try:
            model_status = check_models()
            if not model_status.get("embedding"):
                self._status.setText("⚠️ Embedding 模型未下载，请运行 python -m sentence_transformers -i BAAI/bge-small-zh-v1.5")
        except Exception:
            pass

        self._status.setText("系统就绪")

    def _on_course_change(self, name: str):
        self.chat_page.set_course(name)
        self.doc_tree._course = name
        self.doc_tree._refresh()
        self._status.setText(f"当前: {name}")
# ── 启动 ────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    font = QFont()
    font.setFamilies(["Segoe UI", "PingFang SC", "Microsoft YaHei"])
    font.setPointSize(10)
    app.setFont(font)
    window = SuperTutorWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
