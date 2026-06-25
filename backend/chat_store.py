"""
会话存储 — ChatStore

JSON 文件存储，每条消息一行 JSONL，轻量无数据库依赖。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from loguru import logger


CHATS_DIR = Path("knowledge_base/index/chats")


def _chats_dir() -> Path:
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    return CHATS_DIR


def _session_path(session_id: str) -> Path:
    return _chats_dir() / f"{session_id}.jsonl"


def _manifest_path() -> Path:
    return _chats_dir() / "manifest.json"


# ── 会话列表管理 ────────────────────────────────

def list_sessions() -> List[Dict]:
    """返回所有会话 [{id, name, created_at, msg_count}]"""
    p = _manifest_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return []


def _save_manifest(sessions: List[Dict]) -> None:
    _manifest_path().write_text(json.dumps(sessions, ensure_ascii=False, indent=2), "utf-8")


def new_session(name: Optional[str] = None) -> Dict:
    """创建新会话。"""
    sid = uuid.uuid4().hex[:12]
    now = datetime.now().isoformat(timespec="seconds")
    session = {
        "id": sid,
        "name": name or f"会话 {len(list_sessions()) + 1}",
        "created_at": now,
        "msg_count": 0,
    }
    sessions = list_sessions()
    sessions.append(session)
    _save_manifest(sessions)
    # 创建空文件
    _session_path(sid).write_text("", "utf-8")
    logger.info("新会话: {} ({})", session["name"], sid)
    return session


def delete_session(session_id: str) -> None:
    sessions = [s for s in list_sessions() if s["id"] != session_id]
    _save_manifest(sessions)
    p = _session_path(session_id)
    if p.exists():
        p.unlink()
    logger.info("删除会话: {}", session_id)


def rename_session(session_id: str, new_name: str) -> None:
    sessions = list_sessions()
    for s in sessions:
        if s["id"] == session_id:
            s["name"] = new_name
            break
    _save_manifest(sessions)


# ── 消息读写 ────────────────────────────────────

def load_messages(session_id: str) -> List[Dict]:
    """加载会话的所有消息 [{role, content, timestamp}]"""
    p = _session_path(session_id)
    if not p.exists():
        return []
    messages = []
    for line in p.read_text("utf-8").strip().splitlines():
        if line.strip():
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return messages


def append_message(session_id: str, role: str, content: str) -> None:
    """追加一条消息并更新 manifest 计数。"""
    msg = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    p = _session_path(session_id)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    # 更新计数
    sessions = list_sessions()
    for s in sessions:
        if s["id"] == session_id:
            s["msg_count"] = (s.get("msg_count", 0) or 0) + 1
            break
    _save_manifest(sessions)
