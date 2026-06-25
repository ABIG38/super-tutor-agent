"""
超级导师主窗口 — 现代化无边框设计。

特点:
  - 无边框窗口 + 自定义标题栏（可拖拽）
  - 精致暗色主题（深灰+蓝紫 accent）
  - 毛玻璃效果标题栏
  - 圆角三区布局
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QFont, QIcon, QAction, QPixmap, QPainter, QColor, QLinearGradient, QBrush, QPen
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QTabWidget,
    QStatusBar,
    QPushButton,
    QLabel,
    QFrame,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)

from frontend.components.course_selector import CourseSelector
from frontend.components.document_tree import DocumentTree
from frontend.components.settings_dialog import SettingsDialog
from frontend.pages.chat_page import ChatPage
from frontend.pages.plan_page import PlanPage
from backend.worker import BackgroundWorker


# ── 调色板 ──────────────────────────────────────────────────
# 极简精密极客风: True Black + 纯正深灰 + Acid Green 高光
COLORS = {
    "bg_primary": "#050505",       # 纯正深黑背景
    "bg_secondary": "#0f0f11",     # 稍亮的面板底色
    "bg_tertiary": "#1a1a1d",      # 悬停/控件底色
    "bg_card": "#0a0a0c",          # 毛玻璃卡片
    "accent": "#ccff00",           # Acid Green 主强调色
    "accent_hover": "#d9ff33",     # 强调色悬停
    "accent_subtle": "#ccff0015",  # 强调色低透明度(背景)
    "text_primary": "#fcfcfc",     # 极白主文字
    "text_secondary": "#a0a0a5",   # 高级次要文字
    "text_muted": "#55555a",       # 禁用/极弱文字
    "border": "#1f1f22",           # 极细边框
    "border_light": "#2a2a2e",     # 亮边框
    "success": "#ccff00",          # 成功状态也用主高光
    "warning": "#ffb000",
    "error": "#ff3333",
    "title_bg": "rgba(5, 5, 5, 0.90)",
}

class TitleBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._parent = parent
        self._is_dragging = False  # ★ 修复 #10
        self._drag_pos = None
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        self.setFixedHeight(56)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 0, 0)
        layout.setSpacing(12)

        self.icon_label = QLabel("▪")
        self.icon_label.setStyleSheet(f"color: {COLORS['accent']}; font-size: 20px; font-weight: 900;")
        layout.addWidget(self.icon_label)

        self.title_label = QLabel("超级导师")
        self.title_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 15px; font-family: 'Inter', 'Segoe UI'; font-weight: 800; letter-spacing: 2px;")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("v2.0")
        self.subtitle_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: 600; padding-top: 2px;")
        layout.addWidget(self.subtitle_label)

        layout.addSpacing(20)
        self.course_selector = CourseSelector()
        layout.addWidget(self.course_selector)

        layout.addStretch()

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(36, 36)
        self.btn_settings.clicked.connect(self._open_settings)
        layout.addWidget(self.btn_settings)

        for icon, tooltip, callback in [
            ("—", "最小化", self._parent.showMinimized),
            ("□", "最大化", self._toggle_maximize),
            ("✕", "关闭", self._parent.close),
        ]:
            btn = QPushButton(icon)
            btn.setFixedSize(46, 36)
            btn.clicked.connect(callback)
            btn.setProperty("role", tooltip)
            layout.addWidget(btn)

        self._maximized = False

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            TitleBar {{
                background-color: {COLORS['title_bg']};
                border-bottom: 1px solid {COLORS['border']};
            }}
            TitleBar QPushButton {{
                background: transparent;
                color: {COLORS['text_secondary']};
                border: none;
                font-size: 13px;
                border-radius: 4px;
            }}
            TitleBar QPushButton:hover {{
                background-color: {COLORS['bg_tertiary']};
                color: {COLORS['text_primary']};
            }}
            TitleBar QPushButton[role="关闭"]:hover {{
                background-color: {COLORS['error']};
                color: white;
            }}
        """)

    def _toggle_maximize(self) -> None:
        if self._maximized:
            self._parent.showNormal()
        else:
            self._parent.showMaximized()
        self._maximized = not self._maximized

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            self._is_dragging = True
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not getattr(self, '_is_dragging', False) or self._drag_pos is None:
            return
        if self._parent:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._parent.move(self._parent.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            event.accept()

class GlassCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            GlassCard {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)

class SuperTutorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        # ★ 修复 #2：创建后台工作线程（单例，所有页面共享）
        self.worker = BackgroundWorker()

        self._setup_window()
        self._build_layout()
        self._apply_theme()
        self._wire_signals()

    def _setup_window(self) -> None:
        self.setWindowTitle("SuperTutor")
        self.setMinimumSize(1200, 800)
        self.resize(1300, 850)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)

    def _build_layout(self) -> None:
        outer = QWidget()
        outer.setObjectName("outerContainer")
        outer.setStyleSheet(f"""
            #outerContainer {{
                background-color: {COLORS['bg_primary']};
                border: 1px solid {COLORS['border_light']};
                border-radius: 12px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(60)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(0, 10)
        outer.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(outer)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        main_layout.addWidget(self.title_bar)

        self.title_bar.course_selector.course_changed.connect(self._on_course_changed)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {COLORS['border']}; }}")

        self.doc_tree = DocumentTree()
        splitter.addWidget(self.doc_tree)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.chat_page = ChatPage()
        self.plan_page = PlanPage()

        # ★ 注入 worker 到各页面
        self.doc_tree.set_worker(self.worker)
        self.chat_page.set_worker(self.worker)
        self.plan_page.set_worker(self.worker)
        
        self.tabs.addTab(self.chat_page, "问答")
        self.tabs.addTab(self.plan_page, "计划")
        splitter.addWidget(self.tabs)

        splitter.setSizes([300, 900])
        splitter.setChildrenCollapsible(False)

        main_layout.addWidget(splitter, stretch=1)
        self._setup_status_bar()
        main_layout.addWidget(self._status_widget)

        self.setCentralWidget(outer)

    def _setup_status_bar(self) -> None:
        self._status_widget = QWidget()
        self._status_widget.setFixedHeight(32)
        self._status_widget.setStyleSheet(f"""
            background-color: {COLORS['bg_secondary']};
            border-top: 1px solid {COLORS['border']};
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
        """)

        layout = QHBoxLayout(self._status_widget)
        layout.setContentsMargins(20, 0, 20, 0)

        self.status_icon = QLabel("■")
        self.status_icon.setStyleSheet(f"color: {COLORS['accent']}; font-size: 10px;")
        layout.addWidget(self.status_icon)

        self.status_label = QLabel("系统就绪")
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

    def _on_course_changed(self, course_name: str) -> None:
        self.status_label.setText(f"当前空间 // {course_name}")
        # ★ 切换课程时刷新各页面
        self.doc_tree.refresh(course_name)
        self.plan_page.refresh_progress(course_name)

    def _wire_signals(self) -> None:
        """★ 连接 worker 信号到 UI。"""
        self.worker.status_update.connect(self.status_label.setText)
        self.worker.ingest_done.connect(lambda r: self.doc_tree.refresh(self._current_course()))

    def _current_course(self) -> str:
        return self.title_bar.course_selector.current_course

    def _apply_theme(self) -> None:
        self.setStyleSheet(f"""
            QWidget {{
                font-family: "Inter", "Segoe UI", "PingFang SC";
                color: {COLORS['text_primary']};
            }}
            QMainWindow {{ background: transparent; }}
            QTabWidget::pane {{
                background-color: {COLORS['bg_primary']};
                border: none;
                border-top: 1px solid {COLORS['border']};
            }}
            QTabBar::tab {{
                background-color: {COLORS['bg_secondary']};
                color: {COLORS['text_muted']};
                padding: 12px 32px;
                margin-right: 2px;
                border: none;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1.5px;
            }}
            QTabBar::tab:selected {{
                background-color: {COLORS['bg_primary']};
                color: {COLORS['accent']};
                border-top: 2px solid {COLORS['accent']};
            }}
            QTabBar::tab:hover:!selected {{
                color: {COLORS['text_primary']};
                background-color: {COLORS['bg_tertiary']};
            }}
            QScrollBar:vertical {{ width: 4px; background: transparent; margin: 0; }}
            QScrollBar::handle:vertical {{ background: {COLORS['border_light']}; border-radius: 2px; }}
            QScrollBar::handle:vertical:hover {{ background: {COLORS['text_muted']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{ height: 4px; background: transparent; }}
            QScrollBar::handle:horizontal {{ background: {COLORS['border_light']}; border-radius: 2px; }}
            QSplitter {{ background-color: {COLORS['bg_primary']}; }}
        """)


# ── 启动 ────────────────────────────────────────────────────


def main() -> None:
    """应用入口。"""
    app = QApplication(sys.argv)

    # 字体
    font = QFont()
    font.setFamilies(["Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK"])
    font.setPointSize(10)
    app.setFont(font)

    window = SuperTutorWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
