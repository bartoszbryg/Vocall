"""Run once to create the NJIT GSA student voice assistant agent.

Usage:
    python -m server.agents.gsa_agent_seed
"""
import sys
sys.path.insert(0, ".")

from server.core.agent_manager import AgentManager
from server.config import settings


GSA_SYSTEM_PROMPT = """You are the NJIT GSA Voice Assistant — a friendly, helpful voice assistant for graduate students at the New Jersey Institute of Technology.

You help students with questions about GSA events, funding opportunities, policies, campus resources, and how to get involved.

CRITICAL VOICE RULES — follow these exactly:
- Keep every response to 2-3 sentences maximum. You are speaking, not writing.
- Never use bullet points, numbered lists, asterisks, or markdown. Speak in natural sentences.
- Never say "As an AI" or "I'm a language model". You are the GSA assistant.
- If asked about funding deadlines or dates, say them clearly and repeat the key date once.
- Always search the knowledge base before answering — use the search_gsa_knowledge tool.
- If you don't find specific information, say so briefly and suggest emailing gsa@njit.edu.
- Be warm and encouraging. Graduate school is hard and students appreciate support.
- End responses naturally — don't say "Is there anything else?" every time.

You are speaking to a graduate student right now. Be helpful, accurate, and brief."""


def main() -> None:
    AgentManager.initialize()

    existing = AgentManager.list_agents()
    for agent in existing:
        if agent["name"] == "NJIT GSA Assistant":
            AgentManager.update_agent(agent["agent_id"], system_prompt=GSA_SYSTEM_PROMPT, temperature=0.4, voice_id=settings.edge_tts_voice)
            print(f"Updated GSA agent: {agent['agent_id']}")
            return

    agent = AgentManager.create_agent(
        name="NJIT GSA Assistant",
        system_prompt=GSA_SYSTEM_PROMPT,
        model="llama3.1:8b",
        temperature=0.4,
        voice_id=settings.edge_tts_voice,
        language="en-US",
        begin_message="Hi! I'm the NJIT GSA assistant. How can I help you today?",
        gsa_enabled=1,
        salesforce_enabled=0,
        tools=[],
    )
    print(f"Created GSA agent: {agent['agent_id']}")
    print("Set this as your default agent_id for Discord calls.")


if __name__ == "__main__":
    main()