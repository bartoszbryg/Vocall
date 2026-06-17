import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


_DB_PATH = "./calls.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class AgentManager:
    _initialized: bool = False

    @classmethod
    def initialize(cls) -> None:
        with _get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    system_prompt TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT 'claude-haiku-4-5-20251001',
                    temperature REAL NOT NULL DEFAULT 0.7,
                    voice_id TEXT NOT NULL DEFAULT '21m00Tcm4TlvDq8ikWAM',
                    language TEXT NOT NULL DEFAULT 'en-US',
                    begin_message TEXT DEFAULT NULL,
                    max_call_duration_ms INTEGER DEFAULT 3600000,
                    end_call_after_silence_ms INTEGER DEFAULT 30000,
                    salesforce_enabled INTEGER NOT NULL DEFAULT 0,
                    gsa_enabled INTEGER NOT NULL DEFAULT 0,
                    tools TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # Migrate: add gsa_enabled if this is an existing DB without it
            existing_cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(agents)").fetchall()
            }
            if "gsa_enabled" not in existing_cols:
                conn.execute(
                    "ALTER TABLE agents ADD COLUMN gsa_enabled INTEGER NOT NULL DEFAULT 0"
                )
            conn.commit()
        cls._initialized = True

    @classmethod
    def _now_iso(cls) -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def agent_to_dict(cls, row: sqlite3.Row) -> dict:
        d = dict(row)
        try:
            d["tools"] = json.loads(d["tools"])
        except (json.JSONDecodeError, TypeError):
            d["tools"] = []
        d["salesforce_enabled"] = bool(d["salesforce_enabled"])
        d["gsa_enabled"] = bool(d.get("gsa_enabled", 0))
        return d

    @classmethod
    def create_agent(cls, name: str, system_prompt: str = "", **kwargs: Any) -> dict:
        agent_id = uuid.uuid4().hex
        now = cls._now_iso()
        tools = kwargs.get("tools", [])
        if not isinstance(tools, str):
            tools = json.dumps(tools)

        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO agents (
                    agent_id, name, system_prompt, model, temperature,
                    voice_id, language, begin_message, max_call_duration_ms,
                    end_call_after_silence_ms, salesforce_enabled, gsa_enabled,
                    tools, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    name,
                    system_prompt,
                    kwargs.get("model", "claude-haiku-4-5-20251001"),
                    kwargs.get("temperature", 0.7),
                    kwargs.get("voice_id", "21m00Tcm4TlvDq8ikWAM"),
                    kwargs.get("language", "en-US"),
                    kwargs.get("begin_message", None),
                    kwargs.get("max_call_duration_ms", 3600000),
                    kwargs.get("end_call_after_silence_ms", 30000),
                    1 if kwargs.get("salesforce_enabled") else 0,
                    1 if kwargs.get("gsa_enabled") else 0,
                    tools,
                    now,
                    now,
                ),
            )
            conn.commit()

        return cls.get_agent(agent_id)  # type: ignore[return-value]

    @classmethod
    def get_agent(cls, agent_id: str) -> dict | None:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        if row is None:
            return None
        return cls.agent_to_dict(row)

    @classmethod
    def list_agents(cls) -> list[dict]:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM agents ORDER BY created_at DESC"
            ).fetchall()
        return [cls.agent_to_dict(r) for r in rows]

    @classmethod
    def update_agent(cls, agent_id: str, **fields: Any) -> dict:
        if not fields:
            return cls.get_agent(agent_id)  # type: ignore[return-value]

        fields["updated_at"] = cls._now_iso()

        if "tools" in fields and not isinstance(fields["tools"], str):
            fields["tools"] = json.dumps(fields["tools"])
        if "salesforce_enabled" in fields:
            fields["salesforce_enabled"] = 1 if fields["salesforce_enabled"] else 0
        if "gsa_enabled" in fields:
            fields["gsa_enabled"] = 1 if fields["gsa_enabled"] else 0

        set_clauses = [f"{k} = ?" for k in fields]
        params = list(fields.values()) + [agent_id]

        with _get_conn() as conn:
            conn.execute(
                f"UPDATE agents SET {', '.join(set_clauses)} WHERE agent_id = ?",
                params,
            )
            conn.commit()

        return cls.get_agent(agent_id)  # type: ignore[return-value]

    @classmethod
    def delete_agent(cls, agent_id: str) -> None:
        with _get_conn() as conn:
            conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
            conn.commit()