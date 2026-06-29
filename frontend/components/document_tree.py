"""知识库文档树 — 精简版，双击预览文件/计划。"""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTreeWidget, QTreeWidgetItem, QPushButton, QFileDialog, QMessageBox, QMenu)
from frontend.theme import COLORS


class DocumentTree(QWidget):
    status_update = Signal(str, int)  # msg, progress
    plan_deleted = Signal()

    def __init__(self, agent, parent=None):
        super().__init__(parent)
        self._agent = agent
        self._course = ""
        self._setup_ui()

    def _setup_ui(self):
        """构建文档树界面：标题栏 + 上传按钮 + 文件树。"""
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        h = QWidget(); h.setFixedHeight(48)
        h.setStyleSheet(f"background-color:{COLORS['bg_primary']};border-bottom:1px solid {COLORS['border']}")
        hl = QHBoxLayout(h); hl.setContentsMargins(20,0,20,0)
        t = QLabel("知识库"); t.setStyleSheet(f"color:{COLORS['text_secondary']};font-size:11px;font-weight:700;letter-spacing:2px")
        hl.addWidget(t)
        self.btn_upload = QPushButton("+ 添加")
        self.btn_upload.setFixedSize(56,24)
        self.btn_upload.setStyleSheet(f"QPushButton{{background:transparent;color:{COLORS['accent']};border:1px solid {COLORS['accent']};border-radius:4px;font-size:10px;font-weight:700}}QPushButton:hover{{background-color:{COLORS['accent']};color:{COLORS['bg_primary']}}}")
        self.btn_upload.clicked.connect(self._upload)
        hl.addWidget(self.btn_upload); layout.addWidget(h)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True); self.tree.setIndentation(12)
        self.tree.setStyleSheet(f"QTreeWidget{{background-color:{COLORS['bg_secondary']};color:{COLORS['text_secondary']};border:none;font-size:13px;font-family: system-ui, -apple-system, sans-serif;padding:8px}}QTreeWidget::item{{padding:8px 12px;border-radius:8px}}QTreeWidget::item:hover{{background-color:{COLORS['bg_tertiary']};color:{COLORS['text_primary']}}}QTreeWidget::item:selected{{background-color:{COLORS['accent_muted']};color:{COLORS['accent']};font-weight:bold;}}")
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree); self._refresh()

    def _upload(self):
        """打开文件选择对话框，启动 UploadWorker 子线程批量上传。"""
        files, _ = QFileDialog.getOpenFileNames(self, "选择文档", "", "文档 (*.pdf *.docx *.md *.txt);;所有文件 (*)")
        if not files:
            return

        self.btn_upload.setEnabled(False)
        self.btn_upload.setText("⏳ 上传中")
        
        self.worker = UploadWorker(self._agent, files, self._course)
        self.worker.status.connect(self.status_update.emit)
        self.worker.progress.connect(self._on_upload_progress)
        self.worker.finished.connect(self._on_upload_finished)
        self.worker.start()

    def _on_upload_progress(self, file_path, result):
        """单个文件上传结果回调：处理重复/失败/扫描件等情况。"""
        p = Path(file_path)
        if result.get("reason") == "duplicate":
            if QMessageBox.question(self, "重复", f"「{p.name}」已存在，覆盖？", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                # User wants to overwrite. We do this synchronously for simplicity here.
                from PySide6.QtWidgets import QApplication
                QApplication.setOverrideCursor(Qt.WaitCursor)
                QApplication.processEvents()
                try:
                    self._agent.delete_document(p.name)
                    r = self._agent.ingest_document(file_path, course=self._course)
                    if not r.get("ok"):
                        QMessageBox.warning(self, "错误", f"覆盖失败: {r.get('reason','?')}")
                finally:
                    QApplication.restoreOverrideCursor()
        elif not result.get("ok"):
            reason = result.get('reason', '?')
            if reason == "scanned_pdf":
                msg = "这是一个纯图片/扫描版PDF，目前无法提取文字，因此无法加入知识库。"
            elif "429" in reason or "Rate Limit" in reason:
                msg = "调用向量大模型频繁或已超出额度（429）。"
            elif "Connection" in reason or "Timeout" in reason:
                msg = "网络连接超时，无法连接到大模型向量服务。"
            else:
                msg = str(reason)
            QMessageBox.warning(self, "上传失败", f"文件「{p.name}」未加入知识库：\n{msg}")
        self._refresh()

    def _on_upload_finished(self):
        """所有文件上传完毕，恢复按钮状态并刷新列表。"""
        self.btn_upload.setEnabled(True)
        self.btn_upload.setText("+ 添加")
        self.status_update.emit("✨ 系统就绪", -1)
        self._refresh()

    def _on_double_click(self, item, _col):
        """★ 双击预览文档/计划。"""
        fn = item.data(0, Qt.UserRole)
        if not fn or not item.parent():
            return
        from frontend.components.preview_dialog import DocumentPreviewDialog
        if fn.startswith("__plan__:"):
            pfn = fn.split(":", 1)[1]
            content = self._agent.get_plan_content(pfn)
            if content:
                d = DocumentPreviewDialog(title=pfn, text=content, size=len(content), is_markdown=True, parent=self)
                d.exec()
            else:
                QMessageBox.warning(self, "预览失败", "无法读取计划内容或该计划已被删除。")
        elif self._agent._sources.get(fn):
            r = self._agent.preview_document(fn)
            if r.get("ok"):
                filename = r.get("filename", fn)
                text = r.get("text", "")
                is_markdown = False
                ext = filename.lower().split('.')[-1] if '.' in filename else ''
                
                # 代码文件添加语法高亮
                code_exts = {'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'json': 'json', 
                             'cpp': 'cpp', 'c': 'c', 'h': 'c', 'java': 'java', 'html': 'html', 
                             'css': 'css', 'sql': 'sql', 'sh': 'bash', 'yaml': 'yaml', 'yml': 'yaml'}
                
                if ext == 'md':
                    is_markdown = True
                elif ext in code_exts:
                    is_markdown = True
                    lang = code_exts[ext]
                    text = f"```{lang}\n{text}\n```"
                
                d = DocumentPreviewDialog(title=filename, text=text,
                    size=r.get("size",0), scanned=r.get("scanned",False), is_markdown=is_markdown, original_path=r.get("original_path", ""), parent=self)
                d.exec()
            else:
                QMessageBox.warning(self, "预览失败", f"无法预览文档：{r.get('reason', '未知错误')}")

    def _refresh(self):
        """刷新文档树，显示当前课程下的文档和计划。"""
        self.tree.clear()
        docs = self._agent.get_documents(self._course)
        groups = {"textbook":"▪ 教材","past_paper":"▪ 真题"}
        gd = {k:[] for k in groups}
        for d in docs:
            t = d.get("doc_type","textbook")
            gd.get(t,gd["textbook"]).append(d)
        for k,lbl in groups.items():
            if not gd[k]: continue
            g = QTreeWidgetItem(self.tree,[lbl]); g.setExpanded(True)
            g.setFlags(g.flags() & ~Qt.ItemIsSelectable)
            for d in gd[k]:
                disp = d.get("display_name", d["filename"])
                it = QTreeWidgetItem(g,[f"  {disp}"])
                it.setData(0, Qt.UserRole, d["filename"])
        plans = self._agent.get_plans()
        if plans:
            pg = QTreeWidgetItem(self.tree,["📋 计划"]); pg.setExpanded(True)
            pg.setFlags(pg.flags() & ~Qt.ItemIsSelectable)
            for p in plans:
                it = QTreeWidgetItem(pg,[f"  {p['display_name']}"])
                it.setData(0, Qt.UserRole, f"__plan__:{p['filename']}")
        if not docs and not plans:
            it = QTreeWidgetItem(self.tree,["📚 暂无文档"])
            it.setFlags(it.flags() & ~Qt.ItemIsSelectable)
        self.tree.expandAll()

    def _context_menu(self, pos):
        """右键菜单：预览、重命名、删除。"""
        item = self.tree.itemAt(pos)
        if not item or not item.parent(): return
        fn = item.data(0, Qt.UserRole)
        if not fn: return
        menu = QMenu(self)
        rename = menu.addAction("✏️ 重命名")
        delete = menu.addAction("🗑️ 删除")
        
        menu.setStyleSheet(f"QMenu{{background-color:{COLORS['bg_tertiary']};color:{COLORS['text_primary']};border:1px solid {COLORS['border_light']};border-radius:6px;padding:4px}}QMenu::item{{padding:6px 24px;border-radius:4px}}QMenu::item:selected{{background-color:{COLORS['accent']};color:{COLORS['bg_primary']}}}")
        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if action == rename:
            if fn.startswith("__plan__:"):
                QMessageBox.warning(self, "提示", "计划暂不支持重命名。")
            else:
                from PySide6.QtWidgets import QInputDialog
                info = self._agent._sources.get(fn, {})
                old_name = info.get("display_name", fn)
                new_name, ok = QInputDialog.getText(self, "重命名", "新显示名称：", text=old_name)
                if ok and new_name.strip():
                    self._agent.rename_document(fn, new_name.strip())
                    self._refresh()
        elif action == delete:
            if fn.startswith("__plan__:"):
                pfn = fn.split(":",1)[1]
                p = self._agent.PLANS_DIR / pfn
                if p.exists(): p.unlink()
                
                info = self._agent.get_active_plan_info()
                if info and info.get("plan_filename") == pfn:
                    if hasattr(self._agent, "clear_active_plan"):
                        self._agent.clear_active_plan()
                    self.plan_deleted.emit()
            else:
                if QMessageBox.question(self,"确认",f"删除「{fn}」？",QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                    from PySide6.QtWidgets import QApplication
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    QApplication.processEvents()
                    try:
                        self._agent.delete_document(fn)
                    finally:
                        QApplication.restoreOverrideCursor()
            self._refresh()

from PySide6.QtCore import QThread, Signal

class UploadWorker(QThread):
    progress = Signal(str, dict)
    status = Signal(str, int)
    finished = Signal()

    def __init__(self, agent, files, course):
        super().__init__()
        self.agent = agent
        self.files = files
        self.course = course

    def run(self):
        """子线程入口：逐个调用 ingest_document 上传文件。"""
        for f in self.files:
            def cb(msg, val):
                self.status.emit(msg, val)
            r = self.agent.ingest_document(f, course=self.course, progress_callback=cb)
            self.progress.emit(f, r)
        self.finished.emit()
