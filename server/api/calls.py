import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from server.config import settings
from server.core.auth import require_auth
from server.core.call_manager import CallManager

router = APIRouter(dependencies=[Depends(require_auth)])


def _make_access_token(call_id: str) -> str:
    # Simple random token — no JWT dependency needed
    return secrets.token_hex(32)


def _not_found(call_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"status": "error", "message": f"Call {call_id} not found"},
    )


class CreateWebCallBody(BaseModel):
    agent_id: str
    metadata: dict[str, Any] | None = None
    retell_llm_dynamic_variables: dict[str, Any] | None = None


class CreatePhoneCallBody(BaseModel):
    from_number: str
    to_number: str
    override_agent_id: str | None = None
    metadata: dict[str, Any] | None = None
    retell_llm_dynamic_variables: dict[str, Any] | None = None


class CreateDiscordCallBody(BaseModel):
    agent_id: str
    discord_channel_id: str
    metadata: dict[str, Any] | None = None
    retell_llm_dynamic_variables: dict[str, Any] | None = None


class ListCallsBody(BaseModel):
    filter_criteria: dict[str, Any] | None = None
    sort_order: str = "descending"
    limit: int = 50
    skip: int = 0
    pagination_key: str | None = None


class UpdateCallBody(BaseModel):
    metadata: dict[str, Any] | None = None
    override_dynamic_variables: dict[str, Any] | None = None
    custom_attributes: dict[str, Any] | None = None


class CallControlBody(BaseModel):
    additional_context: str | None = None


class UpdateLiveCallBody(BaseModel):
    fields_to_override: dict[str, Any] | None = None
    call_control: CallControlBody | None = None


@router.post("/v2/create-web-call")
async def create_web_call(body: CreateWebCallBody) -> dict:
    call = CallManager.create_call(
        call_type="web_call",
        agent_id=body.agent_id,
        metadata=body.metadata,
        dynamic_variables=body.retell_llm_dynamic_variables,
        call_status="registered",
        direction="inbound",
    )
    call["access_token"] = _make_access_token(call["call_id"])
    return call


@router.post("/v2/create-phone-call")
async def create_phone_call(body: CreatePhoneCallBody) -> dict:
    agent_id = body.override_agent_id or "default"
    call = CallManager.create_call(
        call_type="phone_call",
        agent_id=agent_id,
        from_number=body.from_number,
        to_number=body.to_number,
        metadata=body.metadata,
        dynamic_variables=body.retell_llm_dynamic_variables,
        call_status="registered",
        direction="outbound",
    )
    return call


@router.post("/v2/create-discord-call")
async def create_discord_call(body: CreateDiscordCallBody) -> dict:
    call = CallManager.create_call(
        call_type="discord_call",
        agent_id=body.agent_id,
        discord_channel_id=body.discord_channel_id,
        metadata=body.metadata,
        dynamic_variables=body.retell_llm_dynamic_variables,
        call_status="registered",
        direction="inbound",
    )

    if settings.discord_bot_token:
        try:
            from server.discord_bot.bot import join_channel

            dynamic_vars = body.retell_llm_dynamic_variables or {}
            import asyncio

            asyncio.create_task(
                join_channel(int(body.discord_channel_id), call["call_id"], dynamic_vars)
            )
        except Exception:
            pass

    return call


@router.get("/v2/get-call/{call_id}")
async def get_call(call_id: str) -> dict:
    call = CallManager.get_call(call_id)
    if call is None:
        raise _not_found(call_id)
    return call


@router.post("/v3/list-calls")
async def list_calls(body: ListCallsBody) -> dict:
    return CallManager.list_calls(
        filter_criteria=body.filter_criteria,
        sort_order=body.sort_order,
        limit=body.limit,
        skip=body.skip,
        pagination_key=body.pagination_key,
    )


@router.patch("/v2/update-call/{call_id}")
async def update_call(call_id: str, body: UpdateCallBody) -> dict:
    call = CallManager.get_call(call_id)
    if call is None:
        raise _not_found(call_id)

    updates: dict[str, Any] = {}
    if body.metadata is not None:
        updates["metadata"] = {**(call.get("metadata") or {}), **body.metadata}
    if body.override_dynamic_variables is not None:
        updates["dynamic_variables"] = body.override_dynamic_variables
    if body.custom_attributes is not None:
        existing_meta = updates.get("metadata", call.get("metadata") or {})
        updates["metadata"] = {**existing_meta, "custom_attributes": body.custom_attributes}

    if updates:
        call = CallManager.update_call(call_id, **updates)
    return call


@router.patch("/v2/update-live-call/{call_id}")
async def update_live_call(call_id: str, body: UpdateLiveCallBody) -> dict:
    call = CallManager.get_call(call_id)
    if call is None:
        raise _not_found(call_id)

    updates: dict[str, Any] = {}
    if body.fields_to_override:
        for key in ("metadata", "dynamic_variables"):
            if key in body.fields_to_override:
                updates[key] = body.fields_to_override[key]

    if body.call_control and body.call_control.additional_context:
        import logging

        logging.getLogger(__name__).info(
            "call_control.additional_context for %s: %s",
            call_id,
            body.call_control.additional_context,
        )

    if updates:
        CallManager.update_call(call_id, **updates)

    return {"success": True}


@router.post("/v2/stop-call/{call_id}", status_code=status.HTTP_204_NO_CONTENT)
async def stop_call(call_id: str) -> Response:
    call = CallManager.get_call(call_id)
    if call is None:
        raise _not_found(call_id)

    now = int(time.time() * 1000)
    start = call.get("start_timestamp") or now
    CallManager.update_call(
        call_id,
        call_status="ended",
        disconnection_reason="manual_stopped",
        end_timestamp=now,
        duration_ms=now - start,
    )

    if call.get("call_type") == "discord_call" and settings.discord_bot_token:
        try:
            from server.discord_bot.bot import leave_channel
            import asyncio

            asyncio.create_task(leave_channel(call_id))
        except Exception:
            pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)


class AgentConfigBody(BaseModel):
    agent_id: str
    name: str | None = None
    voice_id: str | None = None
    system_prompt: str | None = None
    metadata: dict[str, Any] | None = None