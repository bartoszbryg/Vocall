# Voice Agent Evaluation — Pipeline Medical

Vendor evaluation of AI voice calling platforms to replace JustCall for outbound medical supplier calls. Covers research, live testing, and a working voice pipeline built to understand the underlying architecture.

**Platforms evaluated:** Retell AI · Vapi · Bland AI · Synthflow · PolyAI · Air AI

## Report

| File | Description |
|---|---|
| `voice_agent_evaluation.md` | Technical Report — JustCall failure analysis, all 6 vendors, live test results |

## Transcribing call recordings

Used this script to convert Retell AI and Vapi call recordings into text before analysis. Runs locally using OpenAI Whisper so no API key was needed - no cost.

```bash
pip install openai-whisper
python transcribe_audio.py recording.wav
```

Outputs a `recording_transcript.txt` file next to the audio file. After transcribing, I pasted the text into Claude Code, ChatGPT, and Gemini for cross-analysis. Uploading audio files directly to those tools had accuracy issues. Running Whisper locally first gave much cleaner results.

Options:

```
--model    tiny / base / small / medium / large   (default: base)
--format   txt / srt / vtt                        (default: txt)
--language en, fr, es, ...                        (default: auto-detect)
```

See `examples/transcribe_audio_output.txt` for expected output.

## Voice pipeline (scripts/)

A minimal end-to-end voice pipeline built to understand how the latency works. Same architecture uses Retell AI and Vapi under the hood.

```
Mic → VAD → .wav → Deepgram STT → Claude LLM (streaming) → ElevenLabs TTS → Speaker
```

Stages 3, 4, and 5 overlap: TTS starts as soon as the first sentence is ready, not after the full LLM response arrives. This is what cuts latency from 2–3s (JustCall) down to under 1s.

### Setup

```bash
pip install anthropic httpx sounddevice soundfile numpy python-dotenv
```

Copy `.env.example` to `.env` and add your API keys:

```bash
cp .env.example .env
```

| Key | Where to get it |
|---|---|
| `DEEPGRAM_API_KEY` | console.deepgram.com — free $200 credit |
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `ELEVENLABS_API_KEY` | elevenlabs.io — free 10k chars/month |

### Test each stage

```bash
# Stage 1 — mic capture + VAD (saves .wav files to recordings/)
python scripts/capture_utterance.py

# Stage 2 — Deepgram STT (pass a saved .wav)
python scripts/transcribe.py recordings/utterance_xyz.wav

# Stage 3 — Claude LLM (interactive chat to test responses)
python scripts/llm.py

# Stage 4 — ElevenLabs TTS (plays test sentence through speakers)
python scripts/tts.py
```

### Run the full pipeline

```bash
python scripts/pipeline_runner.py
```

Speak into your mic → transcribed → AI responds → spoken back to you.

### Expected latency

| Stage | Time |
|---|---|
| Deepgram Nova-2 STT | ~200ms |
| Claude first token | ~300ms |
| ElevenLabs first audio chunk | ~150ms |
| **Total to first audio** | **~0.8–1.2s** |

For comparison: JustCall's sequential pipeline produces 2–3s of dead air because each stage waits for the previous one to fully finish before starting.

## Example outputs

The `examples/` folder contains sample output files for every script so you know exactly what to expect before running anything.

## Call recordings

Live test calls were recorded during testing sessions on Retell AI and Vapi using an identical agent prompt and the same ElevenLabs voice on both platforms. Five scenarios were tested on each: baseline call, busy customer, off-script questions, and AI disclosure test.