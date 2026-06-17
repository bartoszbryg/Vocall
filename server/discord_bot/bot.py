import asyncio
import io
import logging
import tempfile
import os

import discord
from discord.ext import commands

from server.config import settings
from server.core.agent_engine import AgentEngine
from server.core.call_manager import CallManager

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# call_id -> (VoiceClient, AgentEngine)
active_sessions: dict[str, tuple[discord.VoiceClient, AgentEngine]] = {}
# guild_id -> call_id  (so /ask can find the active session)
guild_calls: dict[int, str] = {}


async def _play_tts(vc: discord.VoiceClient, text: str, engine: AgentEngine) -> None:
    """Synthesize text to speech and play it in the voice channel."""
    if not vc.is_connected():
        return
    try:
        audio_bytes = await engine.synthesize(text)
    except Exception as exc:
        logger.error("TTS error: %s", exc)
        return

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(tmp_path), volume=1.5)
        if vc.is_playing():
            vc.stop()
        vc.play(source)
        while vc.is_playing():
            await asyncio.sleep(0.1)
    finally:
        os.unlink(tmp_path)


async def join_channel(channel_id: int, call_id: str, agent_id: str, dynamic_variables: dict | None = None) -> None:
    await bot.wait_until_ready()
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.NotFound:
            logger.error("Channel %s not found", channel_id)
            CallManager.update_call(call_id, call_status="error", disconnection_reason="channel_not_found")
            return

    if not isinstance(channel, discord.VoiceChannel):
        CallManager.update_call(call_id, call_status="error", disconnection_reason="not_voice_channel")
        return

    # Disconnect any existing voice client in this guild before joining
    guild = channel.guild
    existing_vc = guild.voice_client
    if existing_vc is not None:
        logger.info("Disconnecting stale voice client in guild %s", guild.id)
        try:
            await existing_vc.disconnect(force=True)
        except Exception:
            pass

    try:
        vc = await channel.connect()
    except discord.ClientException as exc:
        logger.error("Failed to join: %s", exc)
        CallManager.update_call(call_id, call_status="error", disconnection_reason=str(exc))
        return

    import time
    CallManager.update_call(call_id, call_status="ongoing", start_timestamp=int(time.time() * 1000))

    engine = AgentEngine(call_id=call_id, agent_id=agent_id, dynamic_variables=dynamic_variables or {})
    active_sessions[call_id] = (vc, engine)
    guild_calls[channel.guild.id] = call_id
    asyncio.create_task(_idle_watchdog(call_id, vc))

    # Play begin message if configured
    begin_msg = None
    if engine.agent_config:
        begin_msg = engine.agent_config.get("begin_message")
    if not begin_msg:
        begin_msg = "Hi! I'm the NJIT GSA assistant. Type slash ask followed by your question and I'll answer out loud."

    await _play_tts(vc, begin_msg, engine)


async def leave_channel(call_id: str) -> None:
    import time
    entry = active_sessions.pop(call_id, None)
    if entry is None:
        return
    vc, engine = entry

    # Remove from guild_calls
    for guild_id, cid in list(guild_calls.items()):
        if cid == call_id:
            del guild_calls[guild_id]

    if vc.is_connected():
        await vc.disconnect()

    transcript = engine.get_transcript()
    now = int(time.time() * 1000)
    call = CallManager.get_call(call_id)
    start = (call or {}).get("start_timestamp") or now
    CallManager.update_call(
        call_id,
        call_status="ended",
        end_timestamp=now,
        duration_ms=now - start,
        transcript=transcript,
    )


IDLE_TIMEOUT_SECONDS = 300  # auto-disconnect after 5 min of no /ask activity


async def _idle_watchdog(call_id: str, vc: discord.VoiceClient) -> None:
    """Disconnect and end the call if no activity for IDLE_TIMEOUT_SECONDS."""
    while True:
        await asyncio.sleep(30)
        if call_id not in active_sessions:
            return
        _, engine = active_sessions[call_id]
        if not vc.is_connected():
            await leave_channel(call_id)
            return
        # Check how long since last transcript line was added
        if engine.last_activity_ts and (asyncio.get_event_loop().time() - engine.last_activity_ts) > IDLE_TIMEOUT_SECONDS:
            logger.info("Call %s idle timeout — disconnecting", call_id)
            await leave_channel(call_id)
            return


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    """Auto-disconnect when everyone leaves the voice channel."""
    guild_id = member.guild.id
    call_id = guild_calls.get(guild_id)
    if call_id is None or call_id not in active_sessions:
        return

    vc, _ = active_sessions[call_id]
    if vc.channel is None:
        return

    # Count non-bot members still in the channel
    human_members = [m for m in vc.channel.members if not m.bot]
    if len(human_members) == 0:
        logger.info("Everyone left voice channel — ending call %s", call_id)
        await leave_channel(call_id)


@bot.event
async def on_ready() -> None:
    logger.info("Discord bot ready as %s", bot.user)


# ---------------------------------------------------------------------------
# Agent management slash commands
# ---------------------------------------------------------------------------

@bot.slash_command(name="agent-create", description="Create a new voice agent")
async def agent_create(
    ctx: discord.ApplicationContext,
    name: discord.Option(str, "Display name for the agent"),
    prompt: discord.Option(str, "System prompt / instructions for the agent"),
) -> None:
    from server.core.agent_manager import AgentManager
    await ctx.defer()
    agent = AgentManager.create_agent(name=name, system_prompt=prompt)
    await ctx.followup.send(
        f"Agent created!\n**ID:** `{agent['agent_id']}`\n**Name:** {agent['name']}\n**Model:** {agent['model']}"
    )


@bot.slash_command(name="agent-list", description="List all configured agents")
async def agent_list(ctx: discord.ApplicationContext) -> None:
    from server.core.agent_manager import AgentManager
    await ctx.defer()
    agents = AgentManager.list_agents()
    if not agents:
        await ctx.followup.send("No agents configured yet.")
        return
    lines = ["**Agents:**"]
    for a in agents:
        tools_count = len(a.get("tools") or [])
        lines.append(f"• `{a['agent_id']}` — **{a['name']}** | model: {a['model']} | tools: {tools_count}")
    await ctx.followup.send("\n".join(lines))


@bot.slash_command(name="agent-edit", description="Edit a single field on an agent")
async def agent_edit(
    ctx: discord.ApplicationContext,
    agent_id: discord.Option(str, "Agent ID to update"),
    field: discord.Option(str, "Field: prompt, model, temperature, voice_id, begin_message"),
    value: discord.Option(str, "New value"),
) -> None:
    from server.core.agent_manager import AgentManager
    await ctx.defer()
    allowed = {
        "prompt": "system_prompt", "model": "model", "temperature": "temperature",
        "voice_id": "voice_id", "begin_message": "begin_message", "system_prompt": "system_prompt",
    }
    if field not in allowed:
        await ctx.followup.send(f"Unknown field `{field}`. Allowed: prompt, model, temperature, voice_id, begin_message")
        return
    db_field = allowed[field]
    final_value: object = value
    if db_field == "temperature":
        try:
            final_value = float(value)
        except ValueError:
            await ctx.followup.send("temperature must be a number e.g. 0.7")
            return
    agent = AgentManager.update_agent(agent_id, **{db_field: final_value})
    if agent is None:
        await ctx.followup.send(f"Agent `{agent_id}` not found.")
        return
    await ctx.followup.send(f"Updated `{db_field}` on agent `{agent_id}`.")


@bot.slash_command(name="agent-add-tool", description="Add a webhook tool to an agent")
async def agent_add_tool(
    ctx: discord.ApplicationContext,
    agent_id: discord.Option(str, "Agent ID"),
    name: discord.Option(str, "Tool name (snake_case)"),
    description: discord.Option(str, "What the tool does"),
    url: discord.Option(str, "Webhook URL"),
) -> None:
    from server.core.agent_manager import AgentManager
    await ctx.defer()
    agent = AgentManager.get_agent(agent_id)
    if agent is None:
        await ctx.followup.send(f"Agent `{agent_id}` not found.")
        return
    existing_tools = list(agent.get("tools") or [])
    existing_tools.append({
        "name": name, "description": description, "url": url,
        "method": "POST", "parameters": {"type": "object", "properties": {}, "required": []},
    })
    AgentManager.update_agent(agent_id, tools=existing_tools)
    await ctx.followup.send(f"Tool `{name}` added to agent `{agent_id}`.")


@bot.slash_command(name="agent-test", description="Test an agent with a text message (no voice needed)")
async def agent_test(
    ctx: discord.ApplicationContext,
    agent_id: discord.Option(str, "Agent ID to test"),
    message: discord.Option(str, "Message to send to the agent"),
) -> None:
    await ctx.defer()
    engine = AgentEngine(call_id="discord-test", agent_id=agent_id)
    try:
        response = await engine.chat(message)
    except Exception as exc:
        await ctx.followup.send(f"Error: {exc}")
        return
    await ctx.followup.send(f"**Agent:** {response}")


@bot.slash_command(name="agent-enable-salesforce", description="Enable Salesforce on an agent")
async def agent_enable_salesforce(
    ctx: discord.ApplicationContext,
    agent_id: discord.Option(str, "Agent ID"),
) -> None:
    from server.core.agent_manager import AgentManager
    await ctx.defer()
    agent = AgentManager.get_agent(agent_id)
    if agent is None:
        await ctx.followup.send(f"Agent `{agent_id}` not found.")
        return
    AgentManager.update_agent(agent_id, salesforce_enabled=1)
    await ctx.followup.send(f"Salesforce enabled on agent `{agent_id}`.")


# ---------------------------------------------------------------------------
# Call slash commands
# ---------------------------------------------------------------------------

@bot.slash_command(name="call-start", description="Bot joins your voice channel and listens for /ask commands")
async def call_start(
    ctx: discord.ApplicationContext,
    agent_id: discord.Option(str, "Agent ID to use"),
) -> None:
    await ctx.defer()
    if ctx.author.voice is None:
        await ctx.followup.send("You must be in a voice channel to start a call.")
        return
    voice_channel = ctx.author.voice.channel
    call = CallManager.create_call(
        call_type="discord_call",
        agent_id=agent_id,
        discord_channel_id=str(voice_channel.id),
        call_status="registered",
        direction="inbound",
    )
    call_id = call["call_id"]
    asyncio.create_task(join_channel(voice_channel.id, call_id, agent_id, {}))
    await ctx.followup.send(
        f"Call started! **Call ID:** `{call_id}`\n"
        f"I'll join your voice channel and speak responses out loud.\n"
        f"Use `/ask` to ask questions — I'll answer both here and in voice."
    )


@bot.slash_command(name="ask", description="Ask the voice agent a question — it responds out loud in the voice channel")
async def ask(
    ctx: discord.ApplicationContext,
    message: discord.Option(str, "Your question"),
) -> None:
    await ctx.defer()

    guild_id = ctx.guild_id
    call_id = guild_calls.get(guild_id)

    if call_id is None or call_id not in active_sessions:
        await ctx.followup.send("No active call. Use `/call-start` first while in a voice channel.")
        return

    vc, engine = active_sessions[call_id]

    try:
        response = await engine.chat(message)
    except Exception as exc:
        await ctx.followup.send(f"Error: {exc}")
        return

    # Reply in text channel
    await ctx.followup.send(f"**You:** {message}\n**Agent:** {response}")

    # Also speak in voice channel
    asyncio.create_task(_play_tts(vc, response, engine))


@bot.slash_command(name="call-stop", description="Stop the active voice call")
async def call_stop(
    ctx: discord.ApplicationContext,
    call_id: discord.Option(str, "Call ID to stop (or 'current' for active call)"),
) -> None:
    await ctx.defer()

    if call_id == "current":
        call_id = guild_calls.get(ctx.guild_id or 0, "")

    if not call_id:
        # Try to at least disconnect the bot from voice if it's stuck
        if ctx.guild and ctx.guild.voice_client:
            await ctx.guild.voice_client.disconnect(force=True)
            await ctx.followup.send("Bot disconnected from voice (no tracked call).")
        else:
            await ctx.followup.send("No active call found.")
        return

    asyncio.create_task(leave_channel(call_id))
    await ctx.followup.send(f"Call `{call_id}` stopped.")


@bot.slash_command(name="call-status", description="Show the current active call status")
async def call_status(ctx: discord.ApplicationContext) -> None:
    await ctx.defer()
    call_id = guild_calls.get(ctx.guild_id or 0)
    if call_id is None or call_id not in active_sessions:
        vc_info = "Bot in voice: Yes" if (ctx.guild and ctx.guild.voice_client) else "Bot in voice: No"
        await ctx.followup.send(f"No active call session tracked.\n{vc_info}")
        return
    vc, engine = active_sessions[call_id]
    await ctx.followup.send(
        f"**Active call:** `{call_id}`\n"
        f"Bot connected: {vc.is_connected()}\n"
        f"Transcript lines: {len(engine.transcript_lines)}"
    )