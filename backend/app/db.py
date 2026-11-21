"""SQLite storage. One short-lived connection per operation keeps us thread-safe
under FastAPI's threadpool without a global lock."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id  TEXT NOT NULL,
  role        TEXT NOT NULL,
  content     TEXT NOT NULL,
  metadata    TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS sessions (
  session_id     TEXT PRIMARY KEY,
  system_prompt  TEXT,
  created_at     TEXT NOT NULL
);
"""


def path_from_url(database_url: str) -> str:
    # sqlite:////data/app.db -> /data/app.db ; sqlite:///./app.db -> ./app.db
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///"):] or "./app.db"
    return database_url or "./app.db"


class Database:
    def __init__(self, database_url: str) -> None:
        self.path = path_from_url(database_url)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")  # readers don't block on a writer
            conn.executescript(SCHEMA)
            conn.commit()

    def ping(self) -> None:
        if not Path(self.path).exists():
            raise RuntimeError("database file missing")
        with self.connect() as conn:
            conn.execute("SELECT 1 FROM messages LIMIT 1").fetchall()

    def session_exists(self, session_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1", (session_id,)
            ).fetchone()
        return row is not None

    def get_messages(self, session_id: str, limit: int | None = None) -> list[dict]:
        """Oldest first. With `limit`, only the most recent `limit` rows."""
        sql = "SELECT role, content, metadata FROM messages WHERE session_id = ?"
        params: tuple = (session_id,)
        if limit is not None:
            sql = (
                "SELECT role, content, metadata FROM ("
                "SELECT id, role, content, metadata FROM messages WHERE session_id = ?"
                " ORDER BY id DESC LIMIT ?) ORDER BY id"
            )
            params = (session_id, limit)
        else:
            sql += " ORDER BY id"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            item: dict = {"role": r["role"], "content": r["content"]}
            if r["metadata"]:
                item["metadata"] = json.loads(r["metadata"])
            out.append(item)
        return out

    def get_system_prompt(self, session_id: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row["system_prompt"] if row else None

    def append_turn(
        self,
        session_id: str,
        user_text: str,
        reply: str,
        metadata: dict,
        system_prompt: str | None,
    ) -> None:
        """One transaction: both rows (and the session prompt) land, or nothing does."""
        ts = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            with conn:  # BEGIN ... COMMIT, ROLLBACK on exception
                conn.execute(
                    "INSERT INTO sessions (session_id, system_prompt, created_at) VALUES (?,?,?)"
                    " ON CONFLICT(session_id) DO UPDATE SET"
                    " system_prompt = COALESCE(excluded.system_prompt, sessions.system_prompt)",
                    (session_id, system_prompt, ts),
                )
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, metadata, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (session_id, "user", user_text, None, ts),
                )
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, metadata, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (session_id, "assistant", reply, json.dumps(metadata), ts),
                )
