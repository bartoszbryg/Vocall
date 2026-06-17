import base64
import logging

from fastapi import WebSocket, WebSocketDisconnect

from server.core.agent_engine import AgentEngine
from server.core.call_manager import CallManager
from server.config import settings

logger = logging.getLogger(__name__)


def _validate_access_token(token: str, call_id: str) -> bool:
    try:
        from jose import jwt, JWTError

        payload = jwt.decode(token, settings.api_key, algorithms=["HS256"])
        return payload.get("call_id") == call_id
    except Exception:
        return False


async def handle_web_call(websocket: WebSocket, call_id: str, access_token: str | None) -> None:
    if not access_token or not _validate_access_token(access_token, call_id):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    call = CallManager.get_call(call_id)
    if call is None:
        await websocket.close(code=4004, reason="Call not found")
        return

    await websocket.accept()

    import time

    CallManager.update_call(
        call_id,
        call_status="ongoing",
        start_timestamp=int(time.time() * 1000),
    )

    engine = AgentEngine(
        call_id=call_id,
        dynamic_variables=call.get("dynamic_variables") or {},
    )

    audio_buffer = bytearray()

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")

            if msg_type == "audio":
                raw = base64.b64decode(message.get("data", ""))
                audio_buffer.extend(raw)

                # Process when buffer reaches ~1 second of 16kHz mono 16-bit PCM (32000 bytes)
                if len(audio_buffer) >= 32000:
                    chunk = bytes(audio_buffer)
                    audio_buffer.clear()

                    try:
                        audio_out = await engine.process_audio(chunk)
                    except Exception as exc:
                        logger.error("Pipeline error for call %s: %s", call_id, exc)
                        audio_out = b""

                    if audio_out:
                        await websocket.send_json(
                            {
                                "type": "audio",
                                "data": base64.b64encode(audio_out).decode(),
                            }
                        )

            elif msg_type == "stop":
                break

    except WebSocketDisconnect:
        pass
    finally:
        now = int(time.time() * 1000)
        start = call.get("start_timestamp") or now
        transcript = engine.get_transcript()
        CallManager.update_call(
            call_id,
            call_status="ended",
            end_timestamp=now,
            duration_ms=now - start,
            transcript=transcript,
            disconnection_reason="client_disconnected",
        )
        try:
            await websocket.send_json({"type": "call_ended", "call_id": call_id})
        except Exception:
            pass