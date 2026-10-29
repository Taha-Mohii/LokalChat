import os
import sqlite3
from config import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, "storage", "localchat.db")


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            from_id TEXT NOT NULL,
            from_name TEXT NOT NULL,
            text TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT 'GROUP',
            to_id TEXT NOT NULL DEFAULT ''
        )""")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        if "kind" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN kind TEXT NOT NULL DEFAULT 'GROUP'")
        if "to_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN to_id TEXT NOT NULL DEFAULT ''")


def save_message(room: str, from_id: str, from_name: str, text: str,
                 timestamp: int, kind: str = "GROUP", to_id: str = ""):
    with _connect() as conn:
        conn.execute("""INSERT INTO messages
            (room, from_id, from_name, text, timestamp, kind, to_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                     (room, from_id, from_name, text, timestamp, kind, to_id))


def get_messages(room: str, limit: int = 1000, kind: str = "GROUP",
                 participant_id: str = "") -> list:
    with _connect() as conn:
        if kind == "DM" and participant_id:
            rows = conn.execute("""SELECT from_id, from_name, text, timestamp, to_id
                FROM messages WHERE room=? AND kind='DM'
                AND (from_id=? OR to_id=?) ORDER BY timestamp DESC LIMIT ?""",
                                (room, participant_id, participant_id, limit)).fetchall()
        else:
            rows = conn.execute("""SELECT from_id, from_name, text, timestamp, to_id
                FROM messages WHERE room=? AND kind=? ORDER BY timestamp DESC LIMIT ?""",
                                (room, kind, limit)).fetchall()
    rows.reverse()
    return [{"from_id": r[0], "from_name": r[1], "text": r[2],
             "timestamp": r[3], "to_id": r[4]} for r in rows]


def clear_messages(room: str):
    with _connect() as conn:
        conn.execute("DELETE FROM messages WHERE room=?", (room,))
