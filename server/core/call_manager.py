import sqlite3
import uuid
import json
import time
from typing import Any


_DB_PATH = "./calls.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("metadata", "dynamic_variables", "call_analysis"):
        if d.get(field) is not None:
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


class CallManager:
    @classmethod
    def initialize(cls) -> None:
        with _get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS calls (
                    call_id TEXT PRIMARY KEY,
                    call_type TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    call_status TEXT NOT NULL DEFAULT 'registered',
                    from_number TEXT,
                    to_number TEXT,
                    direction TEXT NOT NULL DEFAULT 'inbound',
                    discord_channel_id TEXT,
                    metadata TEXT,
                    dynamic_variables TEXT,
                    start_timestamp INTEGER,
                    end_timestamp INTEGER,
                    duration_ms INTEGER,
                    transcript TEXT,
                    recording_url TEXT,
                    disconnection_reason TEXT,
                    call_analysis TEXT,
                    created_at INTEGER NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.commit()

    @classmethod
    def create_call(
        cls,
        call_type: str,
        agent_id: str,
        **kwargs: Any,
    ) -> dict:
        call_id = uuid.uuid4().hex
        now = int(time.time() * 1000)
        metadata = json.dumps(kwargs.get("metadata") or {})
        dynamic_variables = json.dumps(kwargs.get("dynamic_variables") or {})
        direction = kwargs.get("direction", "inbound")
        from_number = kwargs.get("from_number")
        to_number = kwargs.get("to_number")
        discord_channel_id = kwargs.get("discord_channel_id")
        call_status = kwargs.get("call_status", "registered")

        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO calls (
                    call_id, call_type, agent_id, call_status,
                    from_number, to_number, direction, discord_channel_id,
                    metadata, dynamic_variables, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call_id, call_type, agent_id, call_status,
                    from_number, to_number, direction, discord_channel_id,
                    metadata, dynamic_variables, now,
                ),
            )
            conn.commit()

        return cls.get_call(call_id)  # type: ignore[return-value]

    @classmethod
    def get_call(cls, call_id: str) -> dict | None:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM calls WHERE call_id = ? AND deleted = 0", (call_id,)
            ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    @classmethod
    def list_calls(
        cls,
        filter_criteria: dict | None = None,
        sort_order: str = "descending",
        limit: int = 50,
        skip: int = 0,
        pagination_key: str | None = None,
    ) -> dict:
        filter_criteria = filter_criteria or {}
        conditions = ["deleted = 0"]
        params: list[Any] = []

        allowed_filters = ("call_status", "call_type", "direction", "agent_id")
        for key in allowed_filters:
            if key in filter_criteria:
                val = filter_criteria[key]
                if isinstance(val, list):
                    placeholders = ",".join("?" * len(val))
                    conditions.append(f"{key} IN ({placeholders})")
                    params.extend(val)
                else:
                    conditions.append(f"{key} = ?")
                    params.append(val)

        if pagination_key:
            op = "<" if sort_order == "descending" else ">"
            conditions.append(f"created_at {op} ?")
            params.append(int(pagination_key))

        order = "DESC" if sort_order == "descending" else "ASC"
        where = " AND ".join(conditions)
        fetch_limit = limit + 1

        with _get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM calls WHERE {where} ORDER BY created_at {order} LIMIT ? OFFSET ?",
                params + [fetch_limit, skip],
            ).fetchall()

        items = [_row_to_dict(r) for r in rows]
        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        result: dict[str, Any] = {"items": items, "has_more": has_more}
        if has_more and items:
            result["pagination_key"] = str(items[-1]["created_at"])
        return result

    @classmethod
    def update_call(cls, call_id: str, **fields: Any) -> dict:
        json_fields = ("metadata", "dynamic_variables", "call_analysis")
        set_clauses = []
        params: list[Any] = []

        for key, val in fields.items():
            if key in json_fields and not isinstance(val, str):
                val = json.dumps(val)
            set_clauses.append(f"{key} = ?")
            params.append(val)

        if not set_clauses:
            return cls.get_call(call_id)  # type: ignore[return-value]

        params.append(call_id)
        with _get_conn() as conn:
            conn.execute(
                f"UPDATE calls SET {', '.join(set_clauses)} WHERE call_id = ?",
                params,
            )
            conn.commit()

        return cls.get_call(call_id)  # type: ignore[return-value]

    @classmethod
    def delete_call(cls, call_id: str) -> None:
        with _get_conn() as conn:
            conn.execute(
                "UPDATE calls SET deleted = 1 WHERE call_id = ?", (call_id,)
            )
            conn.commit()