"""
Stage 4 — Text to speech via ElevenLabs (streaming)
Streams audio back as it's generated — playback starts before the clip finishes downloading.
First audio chunk in ~100–150ms.
"""

import os
import io
import queue
import threading
import httpx
import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel (default)
TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"
OUTPUT_FORMAT = "mp3_44100_128"


def _headers():
    return {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}


def _payload(text: str):
    return {
        "text": text,
        "model_id": "eleven_turbo_v2_5",  # fastest model
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.0, "use_speaker_boost": True},
        "output_format": OUTPUT_FORMAT,
    }


def speak_text(text: str):
    """Send text, download audio, play it. Blocks until done."""
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not set in .env")
    if not text.strip():
        return

    with httpx.stream("POST", TTS_URL, json=_payload(text), headers=_headers(), timeout=30) as r:
        if r.status_code != 200:
            raise RuntimeError(f"ElevenLabs {r.status_code}: {r.read()[:200].decode()}")
        mp3 = b"".join(r.iter_bytes(4096))

    audio, sr = sf.read(io.BytesIO(mp3), dtype="float32")
    sd.play(audio, samplerate=sr)
    sd.wait()


def speak_streaming(text_iterator):
    """
    Accepts a generator of text tokens (from LLM streaming).
    Buffers into sentences, sends each to ElevenLabs immediately, plays in parallel.
    """
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not set in .env")

    audio_queue = queue.Queue()
    DONE = object()

    def synthesise(sentence: str):
        if not sentence.strip():
            return
        with httpx.stream("POST", TTS_URL, json=_payload(sentence),
                          headers=_headers(), timeout=30) as r:
            if r.status_code == 200:
                for chunk in r.iter_bytes(4096):
                    audio_queue.put(chunk)

    def player():
        buf = io.BytesIO()
        while True:
            item = audio_queue.get()
            if item is DONE:
                break
            buf.write(item)
        buf.seek(0)
        try:
            audio, sr = sf.read(buf, dtype="float32")
            sd.play(audio, samplerate=sr)
            sd.wait()
        except Exception:
            pass

    t = threading.Thread(target=player, daemon=True)
    t.start()

    buf = ""
    for token in text_iterator:
        buf += token
        if any(buf.rstrip().endswith(p) for p in (".", "!", "?")):
            synthesise(buf.strip())
            buf = ""

    if buf.strip():
        synthesise(buf.strip())

    audio_queue.put(DONE)
    t.join()


if __name__ == "__main__":
    speak_text("Hello! This is a test of the ElevenLabs text to speech system.")
    print("Done.")