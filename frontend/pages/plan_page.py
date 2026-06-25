"""
规划+进度页 — 对接 BackgroundWorker 生成计划 + 打勾持久化。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QPushButton, QLabel, QCheckBox, QProgressBar,
    QSpinBox, QFrame, QMessageBox,
)


class PlanPage(QWidget):
    """规划+进度 Tab 页 — 对接 BackgroundWorker。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker = None
        self._course = ""
        self._setup_ui()

    def set_worker(self, worker) -> None:
        """★ 注入后台 worker 并连接信号。"""
        self._worker = worker
        self._worker.plan_done.connect(self._on_plan_done)
        self._worker.plan_error.connect(self._on_plan_error)
        self._worker.progress_loaded.connect(self._on_progress_loaded)

    def set_course(self, course: str) -> None:
        self._course = course

    def refresh_progress(self, course: str = "") -> None:
        """★ 切换课程时刷新进度。"""
        self._course = course or self._course
        if self._worker:
            self._worker.load_progress(self._course)

    # ── UI ────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(16)

        # 参数行
        params = QHBoxLayout()
        params.setSpacing(16)

        for label, suffix, default, rng in [
            ("目 标", " 天", 30, (1, 365)),
            ("每 日", " 小时", 2, (1, 16)),
        ]:
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #55555a; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
            params.addWidget(lbl)

        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 365)
        self.days_spin.setValue(30)
        self.days_spin.setSuffix(" 天")

        self.hours_spin = QSpinBox()
        self.hours_spin.setRange(1, 16)
        self.hours_spin.setValue(2)
        self.hours_spin.setSuffix(" 小时")

        spin_style = """
            QSpinBox { background-color: #0f0f11; color: #fcfcfc;
                border: 1px solid #1f1f22; border-radius: 4px;
                padding: 6px 12px; font-size: 12px; font-weight: 700; min-height: 28px; }
            QSpinBox:focus { border-color: #ccff00; }
            QSpinBox::up-button, QSpinBox::down-button { border: none; width: 0; }
        """
        self.days_spin.setStyleSheet(spin_style)
        self.hours_spin.setStyleSheet(spin_style)
        params.addWidget(self.days_spin)
        params.addWidget(self.hours_spin)

        self.btn_generate = QPushButton("生 成 计 划")
        self.btn_generate.setFixedHeight(42)
        self.btn_generate.setStyleSheet("""
            QPushButton { background-color: transparent; color: #ccff00;
                border: 1px solid #ccff00; border-radius: 4px;
                padding: 8px 24px; font-size: 12px; font-weight: 800; letter-spacing: 1px; }
            QPushButton:hover { background-color: #ccff00; color: #050505; }
        """)
        self.btn_generate.clicked.connect(self._generate)
        params.addWidget(self.btn_generate)
        params.addStretch()
        layout.addLayout(params)

        # 计划内容区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.plan_container = QWidget()
        self.plan_layout = QVBoxLayout(self.plan_container)
        self.plan_layout.setSpacing(12)
        self.plan_layout.setContentsMargins(0, 0, 16, 0)
        scroll.setWidget(self.plan_container)
        layout.addWidget(scroll, stretch=1)

        # 整体进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFormat("整体进度: 0%")
        self.progress_bar.setFixedHeight(24)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: none; border-radius: 4px; text-align: center;
                font-size: 10px; color: #fcfcfc; background-color: #0f0f11;
                font-weight: 800; letter-spacing: 1px; }
            QProgressBar::chunk { background-color: #ccff00; border-radius: 4px; }
        """)
        layout.addWidget(self.progress_bar)

        self.label_completed = QLabel("已掌握模块: 无")
        self.label_completed.setStyleSheet(
            "color: #55555a; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        layout.addWidget(self.label_completed)

        # 操作行
        actions = QHBoxLayout()
        actions.setSpacing(12)

        self.btn_regenerate = QPushButton("重 新 生 成 (跳过已掌握)")
        self.btn_regenerate.clicked.connect(self._generate)
        btn2_style = """
            QPushButton { background-color: transparent; border: 1px solid #1f1f22;
                border-radius: 4px; padding: 10px 24px; font-size: 11px;
                font-weight: 800; letter-spacing: 1px; color: #a0a0a5; }
            QPushButton:hover { background-color: #0f0f11; color: #fcfcfc;
                border-color: #ccff0040; }
        """
        self.btn_regenerate.setStyleSheet(btn2_style)
        actions.addWidget(self.btn_regenerate)

        self.btn_export = QPushButton("导 出 计 划")
        self.btn_export.setStyleSheet(btn2_style)
        self.btn_export.clicked.connect(self._export)
        actions.addWidget(self.btn_export)
        actions.addStretch()
        layout.addLayout(actions)

        self._show_empty()

    # ── 交互 ──────────────────────────────────────

    def _generate(self) -> None:
        if self._worker is None:
            return
        self._clear_plan()
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("生成中...")
        self._worker.plan_async(
            self.days_spin.value(),
            self.hours_spin.value(),
            course=self._course,
        )

    def _export(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出计划", "study_plan.md", "Markdown (*.md)",
        )
        if path:
            md = self._plan_to_markdown()
            import pathlib
            pathlib.Path(path).write_text(md, encoding="utf-8")
            QMessageBox.information(self, "✅", "计划已导出")

    # ── 信号回调 ──────────────────────────────────

    def _on_plan_done(self, result: dict) -> None:
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("生 成 计 划")
        if not result.get("ok"):
            self._show_error(result.get("reason", "未知错误"))
            return
        tasks = result.get("tasks", [])
        self._render_tasks(tasks)

    def _on_plan_error(self, msg: str) -> None:
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("生 成 计 划")
        self._show_error(msg)

    def _on_progress_loaded(self, progress: dict) -> None:
        """加载已有进度，渲染卡片并恢复打勾状态。"""
        tasks = progress.get("tasks", [])
        if not tasks:
            self._show_empty()
            return
        self._render_tasks(tasks, from_db=True)

    # ── 渲染 ──────────────────────────────────────

    def _render_tasks(self, tasks: list[dict], from_db: bool = False) -> None:
        self._clear_plan()
        # 按 day 分组
        days: dict[int, list[dict]] = {}
        for t in tasks:
            d = t.get("day", 1)
            days.setdefault(d, []).append(t)

        for day_num in sorted(days):
            day_tasks = days[day_num]
            card = QFrame()
            card.setStyleSheet("""
                QFrame { background-color: #050505; border: 1px solid #1f1f22;
                    border-radius: 8px; padding: 16px; }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setSpacing(8)

            header = QLabel(f"第 {day_num} 天")
            header.setStyleSheet(
                "font-weight: 800; font-size: 11px; color: #fcfcfc; letter-spacing: 1px;"
            )
            card_layout.addWidget(header)

            done_count = 0
            for task in day_tasks:
                task_text = task.get("task", task.get("task_content", ""))
                task_id = task.get("id")
                is_done = bool(task.get("completed", False))

                cb = QCheckBox(task_text)
                cb.setChecked(is_done)
                cb.setStyleSheet("""
                    QCheckBox { font-size: 12px; color: #a0a0a5; padding: 4px 0; spacing: 12px; }
                    QCheckBox::indicator { width: 14px; height: 14px;
                        border: 1px solid #55555a; border-radius: 2px; }
                    QCheckBox::indicator:checked { background-color: #ccff00; border-color: #ccff00; }
                    QCheckBox::indicator:hover { border-color: #ccff0080; }
                """)
                if task_id is not None and self._worker:
                    cb.toggled.connect(
                        lambda checked, tid=task_id: self._on_checkbox(tid, checked)
                    )
                if is_done:
                    done_count += 1
                card_layout.addWidget(cb)

            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("color: #1f1f22;")
            card_layout.addWidget(line)

            total = len(day_tasks)
            progress = QProgressBar()
            progress.setRange(0, total)
            progress.setValue(done_count)
            progress.setFormat(f"已完成 {done_count}/{total}")
            progress.setFixedHeight(16)
            progress.setStyleSheet("""
                QProgressBar { border: none; border-radius: 4px; text-align: center;
                    font-size: 9px; color: #050505; background-color: #1a1a1d;
                    font-weight: 800; letter-spacing: 1px; }
                QProgressBar::chunk { background-color: #ccff00; border-radius: 4px; }
            """)
            card_layout.addWidget(progress)
            self.plan_layout.addWidget(card)

        self.plan_layout.addStretch()
        self._update_overall()

    def _on_checkbox(self, task_id: int, checked: bool) -> None:
        if self._worker:
            self._worker.mark_task(task_id, checked)
        self._update_overall()

    def _update_overall(self) -> None:
        total = 0
        done = 0
        for i in range(self.plan_layout.count()):
            item = self.plan_layout.itemAt(i)
            if not item or not item.widget():
                continue
            card = item.widget()
            if not isinstance(card, QFrame):
                continue
            cbs = card.findChildren(QCheckBox)
            pbs = card.findChildren(QProgressBar)
            if not pbs:
                continue
            d = sum(1 for cb in cbs if cb.isChecked())
            t = len(cbs)
            pbs[0].setValue(d)
            pbs[0].setFormat(f"已完成 {d}/{t}")
            done += d
            total += t

        if total > 0:
            pct = int(done / total * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"整体进度: {pct}% ({done}/{total})")
        self.label_completed.setText(
            f"已完成: {done}/{total} 项" if total > 0 else "已掌握模块: 无"
        )

    def _clear_plan(self) -> None:
        while self.plan_layout.count():
            item = self.plan_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_empty(self) -> None:
        self._clear_plan()
        label = QLabel("请设置目标参数并生成计划")
        label.setStyleSheet(
            "color: #55555a; font-size: 11px; font-weight: 700; letter-spacing: 1px; padding: 60px 40px;"
        )
        label.setAlignment(Qt.AlignCenter)
        self.plan_layout.addWidget(label)

    def _show_error(self, msg: str) -> None:
        label = QLabel(f"⚠ {msg}")
        label.setStyleSheet(
            "color: #ff3333; font-size: 11px; font-weight: 700; padding: 20px 40px;"
        )
        label.setAlignment(Qt.AlignCenter)
        self.plan_layout.addWidget(label)

    def _plan_to_markdown(self) -> str:
        lines = ["# 学习计划\n"]
        for i in range(self.plan_layout.count()):
            item = self.plan_layout.itemAt(i)
            if not item or not item.widget():
                continue
            card = item.widget()
            if not isinstance(card, QFrame):
                continue
            header = card.findChildren(QLabel)
            checkboxes = card.findChildren(QCheckBox)
            if header:
                lines.append(f"## {header[0].text()}\n")
            for cb in checkboxes:
                mark = "✅" if cb.isChecked() else "⬜"
                lines.append(f"- {mark} {cb.text()}")
            lines.append("")
        return "\n".join(lines)
