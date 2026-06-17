"""
Stage 2 — Speech to text via Deepgram Nova-2
Sends a .wav file to Deepgram and returns the transcript + word timings.
~200ms for a short utterance. Free $200 credit at deepgram.com.
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


def transcribe(wav_path: str) -> dict:
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY not set in .env")

    with open(wav_path, "rb") as f:
        audio_bytes = f.read()

    params = {
        "model": "nova-2",
        "smart_format": "true",
        "language": "en",
        "utterances": "true",
        "punctuate": "true",
    }
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type":  "audio/wav",
    }

    response = httpx.post(DEEPGRAM_URL, content=audio_bytes,
                          headers=headers, params=params, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Deepgram {response.status_code}: {response.text[:300]}")

    alt = response.json()["results"]["channels"][0]["alternatives"][0]
    return {
        "transcript": alt.get("transcript", ""),
        "confidence": alt.get("confidence", 0.0),
        "words": alt.get("words", []),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python 2_transcribe.py <path_to_wav>")
        sys.exit(1)
    result = transcribe(sys.argv[1])
    print(f"Transcript : {result['transcript']}")
    print(f"Confidence : {result['confidence']:.1%}")
    print(f"Words      : {len(result['words'])}")