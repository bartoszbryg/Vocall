"""
Full pipeline — wires all stages together.
Flow: Mic → VAD → .wav → Deepgram STT → Claude LLM (streaming) → ElevenLabs TTS → Speaker

Stages 3, 4, and 5 overlap: TTS starts as soon as the first sentence is ready,
not after the full LLM response arrives.
"""

import time
from scripts.transcribe import transcribe
from scripts.llm import get_llm_response_streaming, reset_conversation
from scripts.tts import speak_streaming
from scripts.capture_utterance import audio_callback, SAMPLE_RATE, BLOCK_SIZE
import sounddevice as sd


def on_audio_ready(wav_path: str):
    """Called by stage 1 when an utterance is saved. Runs stages 2–5."""
    t0 = time.time()
    print(f"\n-- {wav_path} --")

    # Stage 2: STT
    print("  [STT] Transcribing...", end="", flush=True)
    result = transcribe(wav_path)
    transcript = result["transcript"]
    print(f" {time.time()-t0:.2f}s")
    print(f"  [STT] \"{transcript}\"  ({result['confidence']:.0%})")

    if not transcript.strip():
        print("  Empty transcript — skipping")
        return

    # Stages 3+4+5: LLM token stream → TTS → speaker in parallel
    print("  [LLM→TTS] ", end="", flush=True)

    def token_stream():
        accumulated = []
        def capture(tok):
            accumulated.append(tok)
            print(tok, end="", flush=True)
        get_llm_response_streaming(transcript, on_token=capture)
        print()
        yield "".join(accumulated)

    speak_streaming(token_stream())
    print(f"\n  Total: {time.time()-t0:.2f}s\n")


if __name__ == "__main__":
    print("Voice pipeline running. Speak into your mic. Ctrl+C to stop.\n")
    reset_conversation()

    with sd.InputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                        channels=1, dtype="float32", callback=audio_callback):
        try:
            while True:
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nStopped.")