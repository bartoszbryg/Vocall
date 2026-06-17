#!/usr/bin/env python3

import sys
import os
import argparse


def install_whisper():
    import subprocess
    print("Installing openai-whisper...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai-whisper", "-q"])


def format_timestamp(seconds: float, vtt: bool = False) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    sep = "." if vtt else ","
    return f"{h:02}:{m:02}:{s:02}{sep}{ms:03}"


def transcribe(audio_path: str, model_size: str = "base", output_format: str = "txt", language: str = None):
    try:
        import whisper
    except ImportError:
        install_whisper()
        import whisper

    if not os.path.exists(audio_path):
        print(f"File not found: {audio_path}")
        sys.exit(1)

    print(f"Loading model: {model_size}")
    model = whisper.load_model(model_size)

    print(f"Transcribing: {audio_path}")
    options = {"language": language} if language else {}
    result = model.transcribe(audio_path, **options)
    transcript = result["text"].strip()

    base = os.path.splitext(audio_path)[0]
    out = f"{base}_transcript.{output_format}"

    if output_format == "txt":
        with open(out, "w", encoding="utf-8") as f:
            f.write(transcript)

    elif output_format == "srt":
        with open(out, "w", encoding="utf-8") as f:
            for i, seg in enumerate(result["segments"], 1):
                f.write(f"{i}\n{format_timestamp(seg['start'])} --> {format_timestamp(seg['end'])}\n{seg['text'].strip()}\n\n")

    elif output_format == "vtt":
        with open(out, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for seg in result["segments"]:
                f.write(f"{format_timestamp(seg['start'], vtt=True)} --> {format_timestamp(seg['end'], vtt=True)}\n{seg['text'].strip()}\n\n")

    print(f"\nSaved: {out}")
    print(f"\n--- Preview ---\n{transcript[:500]}")
    return transcript


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe audio using local Whisper model")
    parser.add_argument("audio", help="Path to audio file (mp3, wav, m4a, ogg, flac, webm)")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large"])
    parser.add_argument("--format", default="txt", choices=["txt", "srt", "vtt"])
    parser.add_argument("--language", default=None, help="e.g. 'en', 'fr' — auto-detect if omitted")
    args = parser.parse_args()
    transcribe(args.audio, args.model, args.format, args.language)