"""
超级导师主窗口 — 精简版。
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTabWidget, QPushButton, QLabel, QGraphicsDropShadowEffect, QMessageBox, QProgressBar
)
from PySide6.QtGui import QFont, QColor

from backend.agent.orchestrator import SuperTutorAgent
from frontend.components.course_selector import CourseSelector
from frontend.components.document_tree import DocumentTree
from frontend.components.settings_dialog import SettingsDialog
from frontend.pages.chat_page import ChatPage
from frontend.pages.plan_page import PlanPage

from frontend.theme import COLORS


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
        self.title_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 16px; font-family: system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; font-weight: 900; letter-spacing: 1px;")
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
        
        # 允许拖拽上传
        self.setAcceptDrops(True)

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
        splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {COLORS['border_light']}; }}")

        self.doc_tree = DocumentTree(self.agent)
        splitter.addWidget(self.doc_tree)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; border-top: 1px solid {COLORS['border_light']}; }}
            QTabBar::tab {{ background: {COLORS['bg_primary']}; color: {COLORS['text_secondary']}; padding: 12px 30px; font-size: 14px; font-family: system-ui, -apple-system, 'PingFang SC', sans-serif; font-weight: 700; border: none; margin-right: 2px; }}
            QTabBar::tab:hover {{ color: {COLORS['text_primary']}; }}
            QTabBar::tab:selected {{ color: {COLORS['accent']}; border-bottom: 3px solid {COLORS['accent']}; }}
        """)

        self.chat_page = ChatPage()
        self.chat_page.set_agent(self.agent)
        
        self.plan_page = PlanPage()
        self.plan_page.set_agent(self.agent)
        self.plan_page.plan_generated.connect(lambda: self.doc_tree._refresh())  # ★ 计划生成后刷新树

        self.tab_widget.addTab(self.chat_page, "💬 问答")
        self.tab_widget.addTab(self.plan_page, "📅 规划")
        
        splitter.addWidget(self.tab_widget)
        splitter.setSizes([260, 740])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, stretch=1)

        # 状态栏容器
        self.status_container = QWidget()
        self.status_container.setFixedHeight(32)
        self.status_container.setStyleSheet(f"background-color: {COLORS['bg_secondary']}; border-top: 1px solid {COLORS['border']}; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;")
        status_layout = QHBoxLayout(self.status_container)
        status_layout.setContentsMargins(20, 0, 20, 0)
        status_layout.setSpacing(10)

        self._status = QLabel("✨ 系统就绪")
        self._status.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: 600; border: none;")
        status_layout.addWidget(self._status)

        self.global_progress = QProgressBar()
        self.global_progress.setFixedSize(150, 10)
        self.global_progress.setTextVisible(False)
        self.global_progress.setStyleSheet(f"""
            QProgressBar {{ border: none; background-color: {COLORS['bg_primary']}; border-radius: 5px; }}
            QProgressBar::chunk {{ background-color: {COLORS['accent']}; border-radius: 5px; }}
        """)
        self.global_progress.setVisible(False)
        status_layout.addWidget(self.global_progress)
        status_layout.addStretch()

        layout.addWidget(self.status_container)

        self.setCentralWidget(outer)

        # 信号
        self.title_bar.course_selector.course_changed.connect(self._on_course_change)
        self.title_bar.course_selector.course_renamed.connect(self._on_course_rename)
        self.doc_tree.status_update.connect(self.set_global_status)
        self.doc_tree.plan_deleted.connect(self.plan_page._on_plan_deleted)

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
                self.set_global_status("⚠️ Embedding 模型未下载，请运行 python -m sentence_transformers -i BAAI/bge-small-zh-v1.5")
        except Exception:
            pass

        self.set_global_status("✨ 系统就绪")

    def set_global_status(self, msg: str, progress: int = -1):
        self._status.setText(msg)
        if progress >= 0:
            self.global_progress.setVisible(True)
            self.global_progress.setValue(progress)
        else:
            self.global_progress.setVisible(False)

    def _on_course_change(self, name: str):
        self.chat_page.set_course(name)
        self.plan_page.set_course(name)
        self.doc_tree._course = name
        self.doc_tree._refresh()
        self.set_global_status(f"当前课程: {name}")

    def _on_course_rename(self, old_name: str, new_name: str):
        if hasattr(self.agent, "rename_course_documents"):
            self.agent.rename_course_documents(old_name, new_name)

    # ── 拖拽上传 ──────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path:
                from pathlib import Path
                p = Path(file_path)
                self.set_global_status(f"⏳ 正在上传拖拽文档: {p.name}", 0)
                # 直接调用 ingest_document，因为拖拽暂不支持后台，简单加个UI刷新
                QApplication.processEvents()
                
                # 简单回调
                def cb(msg, val):
                    self.set_global_status(msg, val)
                    QApplication.processEvents()
                    
                r = self.agent.ingest_document(str(p), course=self.doc_tree._course, progress_callback=cb)
                if r.get("ok"):
                    self.doc_tree._refresh()
                    self.set_global_status(f"✅ 已上传: {p.name}", -1)
                elif r.get("reason") == "duplicate":
                    if QMessageBox.question(self, "重复", f"「{p.name}」已存在，覆盖？", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                        self.agent.delete_document(p.name)
                        self.agent.ingest_document(str(p), course=self.doc_tree._course, progress_callback=cb)
                        self.doc_tree._refresh()
                        self.set_global_status(f"✅ 已覆盖上传: {p.name}", -1)
                    else:
                        self.set_global_status("✨ 系统就绪", -1)
                else:
                    QMessageBox.warning(self, "错误", f"「{p.name}」: {r.get('reason','?')}")

# ── 启动 ────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    font = QFont()
    font.setFamilies(["system-ui", "-apple-system", "PingFang SC", "Microsoft YaHei"])
    font.setPointSize(10)
    app.setFont(font)
    
    app.setStyleSheet(f"""
        QMessageBox, QInputDialog {{ background-color: {COLORS['bg_card']}; color: {COLORS['text_primary']}; }}
        QMessageBox QLabel, QInputDialog QLabel {{ color: {COLORS['text_primary']}; }}
        QMessageBox QPushButton, QInputDialog QPushButton {{ background-color: {COLORS['bg_primary']}; color: {COLORS['text_primary']}; border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 6px 16px; min-width: 60px; }}
        QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}
    """)
    window = SuperTutorWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
