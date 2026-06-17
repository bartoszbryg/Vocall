"""
Stage 3 — LLM response via Claude (streaming)
Streams tokens back as they're generated so TTS can start before the full response is ready.
"""

import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

conversation_history = []

# Keep responses short — this goes straight to voice, not a chat window
SYSTEM_PROMPT = """You are a helpful voice assistant.
Keep ALL responses under 3 sentences — this is a voice interface, not a chat.
Never use bullet points, markdown, or lists. Speak naturally.
If you don't know something, say so briefly."""


def get_llm_response_streaming(transcript: str, on_token=None):
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    conversation_history.append({"role": "user", "content": transcript})

    full_response = ""
    with client.messages.stream(
        model = "claude-sonnet-4-6",
        max_tokens = 300,
        system = SYSTEM_PROMPT,
        messages = conversation_history,
    ) as stream:
        for chunk in stream.text_stream:
            full_response += chunk
            if on_token:
                on_token(chunk)

    conversation_history.append({"role": "assistant", "content": full_response})
    return full_response


def reset_conversation():
    conversation_history.clear()


if __name__ == "__main__":
    print("Type a message. Ctrl+C to quit.\n")
    while True:
        user_input = input("You: ").strip()
        if not user_input or user_input.lower() in ("quit", "exit"):
            break
        print("Assistant: ", end="", flush=True)
        get_llm_response_streaming(user_input, on_token=lambda c: print(c, end="", flush=True))
        print()