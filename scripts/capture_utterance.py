"""
Stage 1 — VAD + mic capture
Listens to the mic, detects when someone is speaking, saves each utterance as a .wav.
"""

import numpy as np
import sounddevice as sd
import soundfile as sf
import time
import os
from collections import deque
from datetime import datetime
from scripts.pipeline_runner import on_audio_ready


SAMPLE_RATE = 16000   # 16kHz is standard for voice APIs
BLOCK_SIZE = 1600    # 100ms per callback block
THRESHOLD = 0.015   # RMS energy above this = speech
CONFIRM_N = 2       # consecutive loud frames before speech is declared
SILENCE_SEC = 1.2     # silence duration to end an utterance
PRE_ROLL_SEC = 0.3     # seconds of audio kept before threshold is crossed
OUTPUT_DIR = "recordings"

PRE_ROLL_FRAMES = int(PRE_ROLL_SEC * SAMPLE_RATE / BLOCK_SIZE)

ring_buffer   = deque(maxlen=PRE_ROLL_FRAMES)
speech_frames = []
confirm_count = 0
speaking      = False
silent_since  = None


def rms(block):
    return float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))


def save_utterance(frames):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio = np.concatenate(frames).astype(np.float32)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
    path = os.path.join(OUTPUT_DIR, f"utterance_{ts}.wav")
    sf.write(path, audio, samplerate=SAMPLE_RATE, subtype="PCM_16")
    print(f"  Saved: {path}  ({len(audio)/SAMPLE_RATE:.2f}s)")
    return path


def on_utterance_complete(frames):
    path = save_utterance(frames)
    on_audio_ready(path)


def audio_callback(indata, frames, time_info, status):
    global confirm_count, speaking, silent_since, speech_frames

    chunk = indata[:, 0]
    volume = rms(chunk)
    now = time.time()

    if not speaking:
        ring_buffer.append(chunk.copy())
        if volume > THRESHOLD:
            confirm_count += 1
            if confirm_count >= CONFIRM_N:
                speech_frames = list(ring_buffer)
                speaking = True
                confirm_count = 0
                silent_since = None
                print("Speech started")
        else:
            confirm_count = 0
    else:
        speech_frames.append(chunk.copy())
        if volume <= THRESHOLD:
            if silent_since is None:
                silent_since = now
            elif now - silent_since >= SILENCE_SEC:
                print("Speech ended — processing...")
                frames_snapshot = speech_frames[:]
                speaking = False
                silent_since = None
                speech_frames = []
                on_utterance_complete(frames_snapshot)
        else:
            silent_since = None


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Listening | threshold={THRESHOLD} | silence={SILENCE_SEC}s | Ctrl+C to stop\n")
    with sd.InputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                        channels=1, dtype="float32", callback=audio_callback):
        while True:
            time.sleep(0.05)