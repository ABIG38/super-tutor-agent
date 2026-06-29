"""
规划页 — 独立的学习计划生成与展示区。
"""
from __future__ import annotations

import re
import markdown
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTextBrowser, QLineEdit, QPushButton, QLabel,
    QSpinBox, QFormLayout, QMessageBox, QFileDialog
)
from frontend.theme import COLORS

class PlanThreadSafe(QThread):
    token = Signal(str)
    done = Signal(str)
    
    def __init__(self, agent, days, hours, start_chapter, end_chapter, course):
        super().__init__()
        self._agent = agent
        self._days = days
        self._hours = hours
        self._start_chapter = start_chapter
        self._end_chapter = end_chapter
        self._course = course

    def run(self):
        """子线程入口：执行 plan 流式生成并逐 token 发送。"""
        try:
            full_text = ""
            for t in self._agent.generate_plan_stream(self._days, self._hours, self._start_chapter, self._end_chapter, self._course):
                full_text += t
                self.token.emit(t)
            
            # 只有当生成正常结束，且不是错误信息时，才将其设为 active
            if not full_text.startswith("计划生成失败") and not full_text.startswith("请先上传") and not full_text.startswith("未能从教材"):
                # 如果中途被 cancel_stream() 打断，可能也是正常退出。但我们依赖于外部是否强制取消。
                # 由于生成结束，保存
                self._agent.save_active_plan(full_text, self._days, self._hours)

            self.done.emit(full_text)
        except Exception as e:
            self.done.emit(f"\n生成失败：{e}")


class PlanPage(QWidget):
    plan_generated = Signal()  # 计划生成后通知刷新知识库

    def __init__(self, parent=None):
        super().__init__(parent)
        self._agent = None
        self._course = ""
        self._current_plan_content = ""
        self._setup_ui()
        self._refresh_progress_ui()

    def set_agent(self, agent):
        """绑定后端 agent 并刷新进度。"""
        self._agent = agent
        self._refresh_progress_ui()

    def set_course(self, course: str):
        """设置当前课程。"""
        self._course = course

    def _setup_ui(self):
        """搭建计划页面：参数设置 + 计划内容渲染 + 进度追踪。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {COLORS['border']}; }}")

        # ── 左侧参数表单 ──
        left = QWidget()
        left.setMinimumWidth(240)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 24, 16, 24)
        left_layout.setSpacing(16)

        title_lbl = QLabel("学习计划配置")
        title_lbl.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 16px; font-weight: 800;")
        left_layout.addWidget(title_lbl)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)

        # 天数
        self.spin_days = QSpinBox()
        self.spin_days.setRange(1, 365)
        self.spin_days.setValue(30)
        self.spin_days.setButtonSymbols(QSpinBox.NoButtons)
        self.spin_days.setStyleSheet(f"QSpinBox {{ background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; border-radius: 4px; color: {COLORS['text_primary']}; padding: 4px; }}")
        
        # 每日学时
        self.spin_hours = QSpinBox()
        self.spin_hours.setRange(1, 24)
        self.spin_hours.setValue(2)
        self.spin_hours.setButtonSymbols(QSpinBox.NoButtons)
        self.spin_hours.setStyleSheet(f"QSpinBox {{ background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; border-radius: 4px; color: {COLORS['text_primary']}; padding: 4px; }}")

        # 起始章节
        self.edit_start_chapter = QLineEdit()
        self.edit_start_chapter.setPlaceholderText("选填，如：第3章")
        self.edit_start_chapter.setStyleSheet(f"QLineEdit {{ background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; border-radius: 4px; color: {COLORS['text_primary']}; padding: 4px; }}")

        # 结束章节
        self.edit_end_chapter = QLineEdit()
        self.edit_end_chapter.setPlaceholderText("选填，如：第8章")
        self.edit_end_chapter.setStyleSheet(f"QLineEdit {{ background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; border-radius: 4px; color: {COLORS['text_primary']}; padding: 4px; }}")

        lbl_style = f"color: {COLORS['text_secondary']}; font-size: 13px;"
        
        lbl_days = QLabel("总天数 (必填):")
        lbl_days.setStyleSheet(lbl_style)
        form.addRow(lbl_days, self.spin_days)

        lbl_hours = QLabel("每日学时 (选填):")
        lbl_hours.setStyleSheet(lbl_style)
        form.addRow(lbl_hours, self.spin_hours)

        lbl_chapter = QLabel("起始章节 (选填):")
        lbl_chapter.setStyleSheet(lbl_style)
        form.addRow(lbl_chapter, self.edit_start_chapter)

        lbl_end_chapter = QLabel("结束章节 (选填):")
        lbl_end_chapter.setStyleSheet(lbl_style)
        form.addRow(lbl_end_chapter, self.edit_end_chapter)

        left_layout.addLayout(form)

        self.btn_generate = QPushButton("生成计划")
        self.btn_generate.setFixedHeight(40)
        self.btn_generate.setStyleSheet(f"QPushButton {{ background-color: {COLORS['accent']}; color: {COLORS['bg_primary']}; border: none; border-radius: 6px; font-weight: bold; }} QPushButton:hover {{ background-color: {COLORS['accent_hover']}; }}")
        self.btn_generate.clicked.connect(self._generate_plan)
        left_layout.addWidget(self.btn_generate)
        
        left_layout.addStretch()
        splitter.addWidget(left)

        # ── 右侧预览区 ──
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(20, 20, 20, 20)
        
        self._is_showing_full_plan = False
        
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 20px;
                font-size: 14px;
                line-height: 1.7;
                color: {COLORS['text_primary']};
            }}
        """)
        self._welcome()
        
        right_layout.addWidget(self.browser)

        # 底部操作栏 (左侧进度区，右侧导出区)
        bottom_layout = QHBoxLayout()
        
        self.progress_container = QWidget()
        progress_layout = QHBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_progress = QLabel("当前无进行中的计划")
        self.lbl_progress.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; font-weight: bold;")
        progress_layout.addWidget(self.lbl_progress)
        
        from PySide6.QtWidgets import QProgressBar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedSize(120, 14)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ border: 1px solid {COLORS['border']}; border-radius: 7px; background-color: {COLORS['bg_primary']}; }}
            QProgressBar::chunk {{ background-color: {COLORS['accent']}; border-radius: 6px; }}
        """)
        progress_layout.addWidget(self.progress_bar)
        
        self.btn_checkin = QPushButton("✅ 打卡")
        self.btn_checkin.setFixedHeight(28)
        self.btn_checkin.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {COLORS['accent']};
                border: 1px solid {COLORS['accent']}; border-radius: 6px; padding: 0 10px; font-weight: bold; font-size: 12px; }}
            QPushButton:hover {{ background-color: {COLORS['accent']}; color: {COLORS['bg_primary']}; }}
        """)
        self.btn_checkin.clicked.connect(self._on_checkin)
        progress_layout.addWidget(self.btn_checkin)
        
        bottom_layout.addWidget(self.progress_container)
        
        bottom_layout.addStretch()
        
        self.btn_toggle_view = QPushButton("👀 查看完整计划")
        self.btn_toggle_view.setFixedHeight(32)
        self.btn_toggle_view.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {COLORS['accent']};
                border: 1px solid {COLORS['accent']}; border-radius: 6px; padding: 0 16px; font-weight: bold; }}
            QPushButton:hover {{ background-color: {COLORS['accent']}; color: {COLORS['bg_primary']}; }}
        """)
        self.btn_toggle_view.clicked.connect(self._on_toggle_view)
        self.btn_toggle_view.setVisible(False)
        bottom_layout.addWidget(self.btn_toggle_view)
        
        self.btn_export = QPushButton("💾 导出为 Markdown")
        self.btn_export.setFixedHeight(32)
        self.btn_export.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 0 16px; font-weight: bold; }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; border-color: {COLORS['accent']}; }}
        """)
        self.btn_export.clicked.connect(self._export_plan)
        self.btn_export.setEnabled(False)
        bottom_layout.addWidget(self.btn_export)

        right_layout.addLayout(bottom_layout)
        splitter.addWidget(right)
        splitter.setSizes([240, 560])

        layout.addWidget(splitter)

    def _welcome(self):
        """渲染空状态欢迎页。"""
        self.browser.setHtml(
            f'<div style="text-align:center;padding:100px 0;color:{COLORS["text_muted"]};">'
            f'<h2 style="color:{COLORS["text_primary"]};">📖 专属学习计划</h2>'
            f'<p style="font-size:18px;margin-top:20px;color:{COLORS["accent"]};font-weight:bold;">今天有什么计划吗？</p>'
            '<p style="font-size:13px;margin-top:10px;">请在左侧配置参数，立刻生成一份您的专属打卡计划！</p>'
            f'<p style="font-size:12px;color:{COLORS["text_muted"]};margin-top:20px;">（注意：生成计划需要先在知识库上传包含目录的“教材”类文档）</p>'
            '</div>'
        )

    def _refresh_progress_ui(self):
        """刷新今日进度条和打卡按钮状态。"""
        if not self._agent:
            return
        info = self._agent.get_active_plan_info()
        if not info:
            self.progress_container.setVisible(True)
            self.lbl_progress.setText("当前无进行中的计划")
            self.progress_bar.setVisible(False)
            self.btn_checkin.setVisible(False)
            return
            
        self.progress_container.setVisible(True)
        self.progress_bar.setVisible(True)
        self.btn_checkin.setVisible(True)
        cur = info.get("current_day", 1)
        tot = info.get("total_days", 1)
        self.lbl_progress.setText(f"当前进度: 第 {cur} 天 / 共 {tot} 天")
        self.progress_bar.setMaximum(tot)
        self.progress_bar.setValue(cur)
        
        if cur >= tot:
            self.btn_checkin.setText("🎉 计划已完成")
            self.btn_checkin.setEnabled(False)
        else:
            self.btn_checkin.setText("✅ 打卡今天")
            self.btn_checkin.setEnabled(True)
            
        # 尝试加载活跃计划内容
        if not self._current_plan_content:
            try:
                fn = info.get("plan_filename")
                if fn:
                    text = self._agent.get_plan_content(fn)
                    self._on_plan_done(text)
            except Exception:
                pass

    def _on_checkin(self):
        """打卡：保存当日进度到 active_plan.json。"""
        if not self._agent: return
        info = self._agent.get_active_plan_info()
        if not info: return
        cur = info.get("current_day", 1)
        tot = info.get("total_days", 1)
        if cur < tot:
            next_day = cur + 1
            if self._agent.update_active_plan_progress(next_day):
                QMessageBox.information(self, "打卡成功", f"太棒了！您已完成第 {cur} 天的学习，现在进入第 {next_day} 天！\n(回到问答区继续向 AI 提问吧！)")
                self._refresh_progress_ui()
            else:
                QMessageBox.warning(self, "打卡失败", "无法更新进度状态。")

    def _generate_plan(self):
        """启动计划生成的子线程（PlanWorker）。"""
        if not self._agent:
            return
        
        # 检查是否正在生成（支持停止）
        if self.btn_generate.text() == "⏹ 停止生成":
            if self._agent:
                self._agent.cancel_stream()
            self.btn_generate.setText("生成计划")
            self.btn_generate.setEnabled(False)
            return

        days = self.spin_days.value()
        hours = self.spin_hours.value()
        start_chapter = self.edit_start_chapter.text().strip()
        end_chapter = self.edit_end_chapter.text().strip()

        self.btn_generate.setText("⏹ 停止生成")
        self.btn_generate.setStyleSheet(f"""
            QPushButton {{ background-color: {COLORS['error']}; color: {COLORS['bg_primary']}; border-radius: 6px; padding: 10px; font-weight: bold; }}
            QPushButton:hover {{ background-color: #ff5555; }}
        """)
        self.btn_export.setEnabled(False)
        self.btn_toggle_view.setVisible(False)
        self._current_plan_content = ""
        self._token_count = 0
        self.browser.clear()
        
        # 初始化界面以便接收流
        self._token_count = 0

        self._plan_thread = PlanThreadSafe(self._agent, days, hours, start_chapter, end_chapter, self._course)
        self._plan_thread.token.connect(self._on_plan_token)
        self._plan_thread.done.connect(self._on_plan_done)
        self._plan_thread.start()

    def _on_plan_token(self, t: str):
        """计划流式生成回调：逐行 Markdown 渲染。"""
        self._current_plan_content += t
        self._token_count += 1
        # 每10个token刷新一次HTML，防止频繁渲染卡顿
        if self._token_count % 10 == 0:
            try:
                import re
                clean_text = re.sub(r'<think>.*?(</think>|$)', '', self._current_plan_content, flags=re.DOTALL)
                html = markdown.markdown(clean_text + " █", extensions=["extra", "tables", "fenced_code", "toc"])
                styled = f"""<html><head><style>
                    table, th, td {{ border: 1px solid {COLORS['border']}; border-collapse: collapse; padding: 6px; }} 
                    th {{ background-color: {COLORS['bg_secondary']}; }}
                </style></head><body style='font-family:sans-serif;'>{html}</body></html>"""
                self.browser.setHtml(styled)
                self.browser.verticalScrollBar().setValue(self.browser.verticalScrollBar().maximum())
            except Exception:
                pass

    def _render_markdown(self, text: str, show_toc: bool = False):
        """渲染 Markdown 为 HTML（支持 TOC、表格、代码块）。"""
        try:
            import re
            clean_text = re.sub(r'<think>.*?(</think>|$)', '', text, flags=re.DOTALL)
            
            if show_toc:
                clean_text = "[TOC]\n\n" + clean_text
                
            html = markdown.markdown(clean_text, extensions=["extra", "tables", "fenced_code", "toc"])
            styled = f"""<html><head><style>
                table, th, td {{ border: 1px solid {COLORS['border']}; border-collapse: collapse; padding: 6px; }} 
                th {{ background-color: {COLORS['bg_secondary']}; }}
                .toc {{ background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; border-radius: 8px; padding: 15px; margin-bottom: 20px; }}
                .toc ul {{ list-style-type: none; padding-left: 20px; margin: 5px 0; }}
                .toc > ul {{ padding-left: 0; }}
                .toc a {{ text-decoration: none; color: {COLORS['accent']}; font-weight: bold; line-height: 1.8; }}
                .toc a:hover {{ text-decoration: underline; }}
            </style></head><body style='font-family:sans-serif;'>{html}</body></html>"""
            self.browser.setHtml(styled)
        except Exception:
            self.browser.setPlainText(text)
            
    def _render_current_day(self):
        """单独渲染今日计划内容。"""
        info = self._agent.get_active_plan_info() if self._agent else {}
        cur_day = info.get("current_day", 1)
        
        target_content = None
        for i, (title, content) in enumerate(self._parsed_days):
            if f"第{cur_day}天" in title or f"第 {cur_day} 天" in title:
                target_content = content
                break
                
        if not target_content:
            self._render_markdown(self._current_plan_content, show_toc=True)
        else:
            self._render_markdown(target_content, show_toc=False)
            
    def _on_toggle_view(self):
        """切换「今日」/「全部计划」视图。"""
        if not self._current_plan_content:
            return
            
        self._is_showing_full_plan = not self._is_showing_full_plan
        if self._is_showing_full_plan:
            self.btn_toggle_view.setText("🎯 返回当天计划")
            self._render_markdown(self._current_plan_content, show_toc=True)
        else:
            self.btn_toggle_view.setText("👀 查看完整计划")
            self._render_current_day()

    def _on_plan_deleted(self):
        """计划被外部删除时刷新界面。"""
        self._current_plan_content = ""
        self._token_count = 0
        self._parsed_days = []
        self._is_showing_full_plan = False
        self.browser.clear()
        self.btn_export.setEnabled(False)
        self.btn_toggle_view.setVisible(False)
        self.progress_container.setVisible(True)
        self.lbl_progress.setText("当前无进行中的计划")
        self.progress_bar.setVisible(False)
        self.btn_checkin.setVisible(False)
        self._welcome()

    def _on_plan_done(self, text: str):
        """计划生成完成的回调。"""
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("生成计划")
        self.btn_generate.setStyleSheet(f"""
            QPushButton {{ background-color: {COLORS['accent']}; color: {COLORS['bg_primary']}; border-radius: 6px; padding: 10px; font-weight: bold; border: none; }}
            QPushButton:hover {{ background-color: {COLORS['accent_hover']}; }}
            QPushButton:disabled {{ background-color: {COLORS['bg_tertiary']}; color: {COLORS['text_muted']}; }}
        """)
        self._current_plan_content = text
        
        if not text.strip():
            self._welcome()
            self.btn_export.setEnabled(False)
            self.btn_toggle_view.setVisible(False)
            return
            
        if text.startswith("请先上传含目录的教材") or text.startswith("未能从教材中提取到内容") or "计划生成失败" in text:
            self.browser.setPlainText(text)
            self.btn_export.setEnabled(False)
            self.btn_toggle_view.setVisible(False)
            return

        self.btn_export.setEnabled(True)
        self.btn_toggle_view.setVisible(True)
        self.btn_toggle_view.setText("👀 查看完整计划")
        self._is_showing_full_plan = False
        
        self.plan_generated.emit()
        self._refresh_progress_ui()

        # 解析按天分割
        parts = re.split(r'(?m)^(#+\s*第[0-9一二三四五六七八九十百]+天.*)$', text)
        self._parsed_days = []
        
        if len(parts) > 1:
            preface = parts[0].strip()
            if preface:
                self._parsed_days.append(("🎯 学习总览", preface))
                
            for i in range(1, len(parts), 2):
                title = parts[i].replace("#", "").strip()
                content = parts[i] + "\n" + (parts[i+1] if i+1 < len(parts) else "")
                self._parsed_days.append((title, content.strip()))
                
        self._render_current_day()

    def _export_file_dialog(self, title: str, text: str) -> None:
        """另存为 .md 文件。"""
        path, _ = QFileDialog.getSaveFileName(self, "导出学习计划", title, "Markdown Files (*.md);;All Files (*)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                QMessageBox.information(self, "导出成功", f"计划已成功导出至:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "导出失败", f"导出失败:\n{e}")

    def _export_plan(self):
        """另存计划文件。"""
        if self._current_plan_content:
            from datetime import datetime
            default_name = f"学习计划_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            self._export_file_dialog(default_name, self._current_plan_content)
