import asyncio
import json
import re as _re

import httpx

from server.config import settings
from server.core.agent_manager import AgentManager
from server.core.gsa_knowledge_tool import GSAKnowledgeTool
from server.core.salesforce_tool import SalesforceTool

from faster_whisper import WhisperModel

# Module-level singleton — loads once, not per-call (loading takes 2-3s)
_whisper_model: WhisperModel | None = None


def _get_whisper() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        size = settings.whisper_model_size  # "tiny", "base", "small", "medium"
        _whisper_model = WhisperModel(size, device="cpu", compute_type="int8")
    return _whisper_model


def _parse_tool_call(text: str) -> dict | None:
    """Extract JSON tool call from model response, handles nested objects."""
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start != -1:
                candidate = text[start:i + 1]
                try:
                    data = json.loads(candidate)
                    if "tool" in data and "input" in data:
                        return data
                except json.JSONDecodeError:
                    pass
                start = -1
    return None


def _strip_markdown(text: str) -> str:
    """Remove markdown so TTS speaks naturally."""
    text = _re.sub(r'\*+', '', text)          # bold/italic
    text = _re.sub(r'#+\s', '', text)          # headers
    text = _re.sub(r'`[^`]*`', '', text)       # code
    text = _re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # links
    text = _re.sub(r'^\s*[-•]\s+', '', text, flags=_re.MULTILINE)  # bullets -> nothing
    text = _re.sub(r'^\s*\d+\.\s+', '', text, flags=_re.MULTILINE)  # numbered lists
    text = _re.sub(r'\n{2,}', '. ', text)      # paragraph breaks -> pause
    text = _re.sub(r'\n', ' ', text)            # single newlines -> space
    return text.strip()


class AgentEngine:
    def __init__(
        self,
        call_id: str,
        agent_id: str | None = None,
        dynamic_variables: dict | None = None,
    ):
        self.call_id = call_id
        self.dynamic_variables = dynamic_variables or {}
        self.conversation_history: list[dict] = []
        self.transcript_lines: list[str] = []
        self._stop_event = asyncio.Event()
        self.last_activity_ts: float | None = None

        # Load agent config
        self.agent_config: dict | None = None
        if agent_id:
            self.agent_config = AgentManager.get_agent(agent_id)

        # Build tools list first (needed for system prompt injection)
        self.tools = self._build_tools()

        # Build system prompt (injects tool descriptions for Ollama ReAct)
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        if self.agent_config:
            prompt = self.agent_config["system_prompt"]
        else:
            prompt = (
                "You are a helpful voice assistant for NJIT graduate students. "
                "Keep responses under 3 sentences."
            )

        # Inject dynamic variables
        for key, value in self.dynamic_variables.items():
            prompt = prompt.replace(f"{{{{{key}}}}}", value)

        # Inject tool descriptions for Ollama ReAct pattern
        if self.tools:
            tool_desc = "\n".join(
                f"- {t['name']}: {t['description']}"
                for t in self.tools
            )
            prompt += f"""

You have access to these tools. To call one, respond with ONLY this exact JSON (nothing else):
{{"tool": "<tool_name>", "input": {{<parameters as JSON>}}}}

After receiving a tool result, respond naturally to the user.

Available tools:
{tool_desc}"""

        return prompt

    def _build_tools(self) -> list[dict]:
        tools: list[dict] = []

        if self.agent_config:
            if self.agent_config.get("salesforce_enabled"):
                tools.append(SalesforceTool.get_tool_definition())

            if self.agent_config.get("gsa_enabled"):
                tools.extend(GSAKnowledgeTool.get_tool_definitions())

            for wh_tool in self.agent_config.get("tools", []):
                tools.append(
                    {
                        "name": wh_tool["name"],
                        "description": wh_tool["description"],
                        "parameters": wh_tool["parameters"],
                    }
                )
        elif settings.gsa_db_path:
            # No agent config but GSA_DB_PATH is set — auto-enable GSA tools
            tools.extend(GSAKnowledgeTool.get_tool_definitions())

        return tools

    async def _call_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return string result."""
        if tool_name == "salesforce_query":
            result = await SalesforceTool.query(tool_input["soql"])
            return json.dumps(result, default=str)

        if tool_name == "search_gsa_knowledge":
            return await GSAKnowledgeTool.search(
                tool_input["query"], tool_input.get("category", "all")
            )
        elif tool_name == "get_upcoming_events":
            return await GSAKnowledgeTool.get_upcoming_events()
        elif tool_name == "get_gsa_contacts":
            return await GSAKnowledgeTool.get_contacts()

        # Look up webhook tool
        if self.agent_config:
            for wh_tool in self.agent_config.get("tools", []):
                if wh_tool["name"] == tool_name:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        method = wh_tool.get("method", "POST").upper()
                        if method == "GET":
                            resp = await client.get(wh_tool["url"], params=tool_input)
                        else:
                            resp = await client.post(wh_tool["url"], json=tool_input)
                        return resp.text

        return f"Tool {tool_name} not found"

    async def transcribe(self, audio_bytes: bytes) -> str:
        import tempfile
        import os

        loop = asyncio.get_event_loop()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            model = _get_whisper()
            segments, _ = await loop.run_in_executor(
                None, lambda: model.transcribe(tmp_path, language="en")
            )
            return " ".join(seg.text for seg in segments).strip()
        finally:
            os.unlink(tmp_path)

    async def generate_response(self, user_text: str) -> str:
        """Generate LLM response via Ollama, handling ReAct tool calls. Returns final text."""
        model = settings.ollama_model
        if self.agent_config:
            model = self.agent_config.get("model", model)

        temperature = 0.3
        if self.agent_config:
            temperature = self.agent_config.get("temperature", temperature)

        ollama_url = settings.ollama_url

        self.conversation_history.append({"role": "user", "content": user_text})

        async with httpx.AsyncClient(timeout=60.0) as client:
            for _ in range(5):  # max 5 tool call iterations
                payload = {
                    "model": model,
                    "messages": [{"role": "system", "content": self.system_prompt}]
                    + self.conversation_history,
                    "stream": False,
                    "options": {"temperature": temperature},
                }
                resp = await client.post(f"{ollama_url}/api/chat", json=payload)
                resp.raise_for_status()
                content = resp.json()["message"]["content"].strip()

                # Check for tool call
                tool_call = _parse_tool_call(content)
                if tool_call and self.tools:
                    result = await self._call_tool(tool_call["tool"], tool_call["input"])
                    self.conversation_history.append({"role": "assistant", "content": content})
                    self.conversation_history.append(
                        {"role": "user", "content": f"Tool result: {result}"}
                    )
                    continue

                self.conversation_history.append({"role": "assistant", "content": content})
                return content

        return "I'm sorry, I couldn't generate a response."

    async def synthesize(self, text: str) -> bytes:
        import edge_tts
        from pydub import AudioSegment
        import io

        voice = settings.edge_tts_voice
        if self.agent_config:
            configured = self.agent_config.get("voice_id") or ""
            # Accept only edge-tts style names (contain a hyphen), ignore ElevenLabs IDs
            if configured and "-" in configured:
                voice = configured

        try:
            communicate = edge_tts.Communicate(text, voice)
            mp3_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_chunks.append(chunk["data"])
        except Exception:
            # Fallback to default voice if configured voice is invalid
            communicate = edge_tts.Communicate(text, settings.edge_tts_voice)
            mp3_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_chunks.append(chunk["data"])

        mp3_bytes = b"".join(mp3_chunks)
        audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))

        # Discord requires 48kHz stereo PCM
        audio = audio.set_frame_rate(48000).set_channels(2)
        buf = io.BytesIO()
        audio.export(buf, format="wav")
        return buf.getvalue()

    async def process_audio(self, audio_bytes: bytes) -> bytes:
        user_text = await self.transcribe(audio_bytes)
        if not user_text.strip():
            return b""
        self.transcript_lines.append(f"User: {user_text}")
        response_text = await self.generate_response(user_text)
        response_text = _strip_markdown(response_text)
        self.transcript_lines.append(f"Agent: {response_text}")
        audio_out = await self.synthesize(response_text)
        return audio_out

    async def chat(self, user_text: str) -> str:
        """Text-only chat mode (for Discord text channel training)."""
        self.last_activity_ts = asyncio.get_event_loop().time()
        self.transcript_lines.append(f"User: {user_text}")
        response = await self.generate_response(user_text)
        response = _strip_markdown(response)
        self.transcript_lines.append(f"Agent: {response}")
        return response

    def get_transcript(self) -> str:
        return "\n".join(self.transcript_lines)

    def stop(self) -> None:
        self._stop_event.set()