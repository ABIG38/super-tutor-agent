"""
知识库文档树 — 左侧面板。对接 BackgroundWorker 进行上传/索引。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTreeWidget, QTreeWidgetItem, QPushButton,
    QFileDialog, QMessageBox, QMenu, QInputDialog,
)


class DocumentTree(QWidget):
    """知识库文档树 — 对接 BackgroundWorker。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker = None
        self._course = ""
        self._setup_ui()

    def set_worker(self, worker) -> None:
        """★ 注入后台 worker。"""
        self._worker = worker

    def set_course(self, course: str) -> None:
        self._course = course

    def refresh(self, course: str = "") -> None:
        """★ 从 agent 同步文档列表到树。"""
        self._course = course or self._course
        if self._worker is None:
            return
        docs = self._worker.get_documents(self._course)
        self._rebuild_tree(docs)

    # ── UI ────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background-color: #050505; border-bottom: 1px solid #1f1f22;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("知识库")
        title.setStyleSheet("color: #a0a0a5; font-size: 11px; font-weight: 700; letter-spacing: 2px;")
        h_layout.addWidget(title)

        self.btn_upload = QPushButton("+ 添加")
        self.btn_upload.setFixedSize(56, 24)
        self.btn_upload.setStyleSheet("""
            QPushButton { background-color: transparent; color: #ccff00;
                border: 1px solid #ccff00; border-radius: 4px;
                font-size: 10px; font-weight: 700; letter-spacing: 1px; }
            QPushButton:hover { background-color: #ccff00; color: #050505; }
        """)
        self.btn_upload.clicked.connect(self._upload_document)
        h_layout.addWidget(self.btn_upload)
        layout.addWidget(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setAnimated(True)
        self.tree.setStyleSheet("""
            QTreeWidget { background-color: #0f0f11; color: #a0a0a5; border: none;
                font-size: 12px; padding: 12px 8px; outline: none; }
            QTreeWidget::item { padding: 8px 12px; border-radius: 4px; margin: 2px 0; }
            QTreeWidget::item:hover { background-color: #1a1a1d; color: #fcfcfc; }
            QTreeWidget::item:selected { background-color: #ccff0015; color: #ccff00;
                border-left: 2px solid #ccff00; }
        """)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.tree)
        self._show_empty_state()

    # ── 文档操作 ──────────────────────────────────

    def _upload_document(self) -> None:
        if self._worker is None:
            QMessageBox.warning(self, "提示", "系统未初始化")
            return

        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文档", "",
            "文档 (*.pdf *.docx *.md *.txt);;所有文件 (*)",
        )
        for f in files:
            path = Path(f)
            result = self._worker.agent.ingest_document(
                str(path),
                doc_type="textbook",
                course=self._course,
            )
            if result.get("ok"):
                self.refresh(self._course)
            elif result.get("reason") == "duplicate":
                confirm = QMessageBox.question(
                    self, "重复文档",
                    f"「{path.name}」已存在，是否覆盖？",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if confirm == QMessageBox.Yes:
                    self._worker.agent.overwrite_document(
                        str(path), doc_type="textbook", course=self._course,
                    )
                    self.refresh(self._course)
            else:
                QMessageBox.warning(
                    self, "索引失败",
                    f"「{path.name}」: {result.get('reason', '未知错误')}",
                )

    def _show_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None or item.parent() is None:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("✏️ 重命名")
        delete_action = menu.addAction("🗑️ 删除")
        action = menu.exec(self.tree.viewport().mapToGlobal(pos))

        filename = item.data(0, Qt.UserRole)
        if not filename:
            return

        if action == rename_action:
            new_name, ok = QInputDialog.getText(self, "重命名", "新文件名：", text=filename)
            if ok and new_name.strip() and self._worker:
                self._worker.agent.rename_document(filename, new_name.strip())
                self.refresh(self._course)

        elif action == delete_action:
            confirm = QMessageBox.question(
                self, "删除文档", f"确定删除「{filename}」吗？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm == QMessageBox.Yes and self._worker:
                self._worker.delete_document(filename)
                self.refresh(self._course)

    # ── 树操作 ────────────────────────────────────

    def _rebuild_tree(self, docs: list[dict]) -> None:
        self.tree.clear()
        if not docs:
            self._show_empty_state()
            return

        # 分组
        groups: dict[str, list[dict]] = {"教材": [], "真题": []}
        for d in docs:
            dtype = d.get("doc_type", "textbook")
            if dtype == "past_paper":
                groups["真题"].append(d)
            else:
                groups["教材"].append(d)

        for group_name in ["教材", "真题"]:
            items = groups[group_name]
            if not items:
                continue
            group_item = QTreeWidgetItem(self.tree, [f"▪ {group_name}"])
            group_item.setExpanded(True)
            group_item.setFlags(group_item.flags() & ~Qt.ItemIsSelectable)

            for d in items:
                display = d.get("display_name", d.get("filename", ""))
                item = QTreeWidgetItem(group_item, [f"  {display}"])
                item.setData(0, Qt.UserRole, d.get("filename", ""))
                item.setToolTip(0, f"{d.get('chunk_count', 0)} chunks | {d.get('course', '')}")

        self.tree.expandAll()

    def _show_empty_state(self) -> None:
        self.tree.clear()
        item = QTreeWidgetItem(self.tree, ["📚 暂无文档"])
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.tree.addTopLevelItem(item)
