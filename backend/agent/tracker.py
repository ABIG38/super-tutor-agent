import sqlite3
import os
import json
from pathlib import Path
from typing import List, Dict

from loguru import logger

class StudyTracker:
    """SQLite-based learning progress tracker."""
    
    def __init__(self, db_dir: str = "knowledge_base/index"):
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = Path(db_dir) / "learning_progress.db"
        self._init_db()
        
    def _get_conn(self):
        # Enable WAL mode and busy timeout for concurrent safety
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
        
    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_task (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT NOT NULL,
                course TEXT DEFAULT '',
                day_index INTEGER NOT NULL,
                task_content TEXT NOT NULL,
                completed INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            ''')
            
    def init_plan(self, plan_id: str, tasks: List[Dict], course: str = "") -> None:
        """
        Init a new plan with daily tasks.
        tasks format: [{"day": 1, "task": "1.1 xxx"}]
        """
        with self._get_conn() as conn:
            # First, delete existing tasks for this course to replace the plan
            if course:
                conn.execute("DELETE FROM daily_task WHERE course = ?", (course,))
                
            for task in tasks:
                conn.execute('''
                INSERT INTO daily_task (plan_id, course, day_index, task_content, completed)
                VALUES (?, ?, ?, ?, 0)
                ''', (plan_id, course, task.get("day", 1), task.get("task", "")))
                
    def mark_task(self, task_id: int, completed: bool) -> None:
        """Mark a specific task as completed/uncompleted."""
        with self._get_conn() as conn:
            conn.execute('''
            UPDATE daily_task SET completed = ?, updated_at = datetime('now')
            WHERE id = ?
            ''', (1 if completed else 0, task_id))
            
    def get_plan_progress(self, course: str = "") -> Dict:
        """Get the current progress for the active plan in the course."""
        with self._get_conn() as conn:
            cursor = conn.execute('''
            SELECT COUNT(*), SUM(completed) FROM daily_task
            WHERE course = ?
            ''', (course,))
            row = cursor.fetchone()
            
            total = row[0] or 0
            completed = row[1] or 0
            
            tasks_cursor = conn.execute('''
            SELECT id, day_index, task_content, completed FROM daily_task
            WHERE course = ? ORDER BY day_index, id
            ''', (course,))
            
            tasks = [{"id": r[0], "day": r[1], "task": r[2], "completed": bool(r[3])} for r in tasks_cursor.fetchall()]
            
            return {
                "total": total,
                "completed": completed,
                "pct": (completed / total) if total > 0 else 0.0,
                "tasks": tasks
            }
            
    def get_completed_chapters(self, course: str = "") -> List[str]:
        """Get list of completed task contents for prompt injection."""
        with self._get_conn() as conn:
            cursor = conn.execute('''
            SELECT task_content FROM daily_task
            WHERE course = ? AND completed = 1
            ''', (course,))
            return [r[0] for r in cursor.fetchall()]

    def delete_course(self, course: str) -> None:
        """★ 修复 #8：删除课程的所有进度数据。"""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM daily_task WHERE course = ?", (course,))
            logger.info("已删除课程 {} 的所有进度数据", course)

    def close(self):
        pass
