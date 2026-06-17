from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from server.core.auth import require_auth
from server.core.agent_manager import AgentManager

router = APIRouter(dependencies=[Depends(require_auth)])


class WebhookTool(BaseModel):
    name: str
    description: str
    url: str
    method: str = "POST"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }


class CreateAgentBody(BaseModel):
    name: str
    system_prompt: str = ""
    model: str = "claude-haiku-4-5-20251001"
    temperature: float = 0.7
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    language: str = "en-US"
    begin_message: str | None = None
    max_call_duration_ms: int = 3600000
    end_call_after_silence_ms: int = 30000
    salesforce_enabled: bool = False
    tools: list[WebhookTool] = []


class UpdateAgentBody(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    voice_id: str | None = None
    language: str | None = None
    begin_message: str | None = None
    max_call_duration_ms: int | None = None
    end_call_after_silence_ms: int | None = None
    salesforce_enabled: bool | None = None
    tools: list[WebhookTool] | None = None


@router.post("/v2/create-agent", status_code=status.HTTP_201_CREATED)
async def create_agent(body: CreateAgentBody) -> dict:
    tools_list = [t.model_dump() for t in body.tools]
    agent = AgentManager.create_agent(
        name=body.name,
        system_prompt=body.system_prompt,
        model=body.model,
        temperature=body.temperature,
        voice_id=body.voice_id,
        language=body.language,
        begin_message=body.begin_message,
        max_call_duration_ms=body.max_call_duration_ms,
        end_call_after_silence_ms=body.end_call_after_silence_ms,
        salesforce_enabled=body.salesforce_enabled,
        tools=tools_list,
    )
    return agent


@router.get("/v2/get-agent/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    agent = AgentManager.get_agent(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "error", "message": f"Agent {agent_id} not found"},
        )
    return agent


@router.get("/v2/list-agents")
async def list_agents() -> list[dict]:
    return AgentManager.list_agents()


@router.patch("/v2/update-agent/{agent_id}")
async def update_agent(agent_id: str, body: UpdateAgentBody) -> dict:
    existing = AgentManager.get_agent(agent_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "error", "message": f"Agent {agent_id} not found"},
        )

    fields: dict[str, Any] = {}
    data = body.model_dump(exclude_unset=True)
    for key, val in data.items():
        if key == "tools" and val is not None:
            fields[key] = [t if isinstance(t, dict) else t for t in val]
        else:
            fields[key] = val

    if not fields:
        return existing

    return AgentManager.update_agent(agent_id, **fields)


@router.delete("/v2/delete-agent/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str) -> None:
    existing = AgentManager.get_agent(agent_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "error", "message": f"Agent {agent_id} not found"},
        )
    AgentManager.delete_agent(agent_id)