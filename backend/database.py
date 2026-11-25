import os
import aiosqlite
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import json
from backend.config import settings

def get_db_path() -> str:
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite:////"):
        path = "/" + db_url[len("sqlite:////"):]
    elif db_url.startswith("sqlite:///"):
        path = db_url[len("sqlite:///"):]
    elif db_url.startswith("sqlite://"):
        path = db_url[len("sqlite://"):]
    else:
        path = db_url
    
    # Ensure directory exists
    dir_path = os.path.dirname(path)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    return path

async def init_db() -> None:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL, -- 'user' or 'assistant'
            content TEXT NOT NULL,
            metadata TEXT, -- JSON string, assistant messages only
            created_at TEXT NOT NULL -- server time, ISO-8601
        );
        """)
        # Index on session_id for optimal retrieval performance
        await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id);
        """)
        await db.commit()

async def check_db_health() -> bool:
    try:
        db_path = get_db_path()
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT 1;")
            row = await cursor.fetchone()
            return row is not None and row[0] == 1
    except Exception:
        return False

async def get_messages_by_session(session_id: str) -> List[Dict[str, Any]]:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        )
        rows = await cursor.fetchall()
        messages = []
        for row in rows:
            msg = {
                "role": row["role"],
                "content": row["content"]
            }
            if row["metadata"]:
                try:
                    msg["metadata"] = json.loads(row["metadata"])
                except Exception:
                    msg["metadata"] = row["metadata"]
            messages.append(msg)
        return messages

async def add_message(session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    db_path = get_db_path()
    now_iso = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata is not None else None
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, meta_json, now_iso)
        )
        await db.commit()

async def session_exists(session_id: str) -> bool:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT 1 FROM messages WHERE session_id = ? LIMIT 1", (session_id,))
        row = await cursor.fetchone()
        return row is not None
