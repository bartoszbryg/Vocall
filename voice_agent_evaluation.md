# AI Voice Calling Agent — Vendor Evaluation

## Overview

Evaluation covers 6 platforms for outbound AI voice calling. I did research and hands-on tests on 4 of them — Retell AI, Vapi, Bland AI, and Synthflow — and live call testing on 2 of them (Retell AI and Vapi). I had a problem signing into Bland AI during my testing because it requires a professional work email.

I customized the technical pipeline in a simple way that is similar to the default setup, because full customization would require a lot of time. I wrote scripts and tested them using each platform's documentation to set up the APIs appropriately. I also provide a final recommendation with evidence at the end.

On the way, I read three research papers on voice AI latency and conversational agent design. I referenced them at the bottom.

## Why Sequential Pipelines Don't Work

Older AI calling platforms were built as sales dialers first. The AI voice feature was added on top. Therefore, they don't work well as they were not designed for voice call agent purposes.

Every AI voice call works like a chain: the customer speaks → the system detects they stopped → audio gets converted to text → an AI generates a response → that response gets converted back to voice → it plays through the phone. The problem with sequential pipelines is that each step waits for the previous one to fully finish before starting. Nothing runs at the same time.

The result: **2–3 seconds of silence after every customer response.** That's the dead air you hear in poorly-performing AI calls.

The robotic voice is a separate issue. These platforms send the AI's response to ElevenLabs as one complete block of text, rather than streaming it word by word. The voice engine can't produce natural rhythm or breathing without seeing the sentence build in real time — so everything comes out flat.

This can't be fixed by tuning. It's how the platform is built.

## Vendor Overview

I looked at 6 platforms. Two were ruled out before any testing:

- **Air AI — Do not use.** The FTC filed a complaint in August 2025 for charging companies $25K–$100K upfront for technology that didn't work. Settled March 2026 for $18 million. Owners banned from marketing business opportunities.
- **PolyAI — Not suitable for small-to-medium use.** Excellent technology, but contracts start at ~$150,000/year with 6-week deployment timelines. Worth revisiting at much higher call volumes.

The remaining four:

| Platform | Response Speed (platform-reported) | Voice | HIPAA | Approx. Cost/min | Best For |
|---|---|---|---|---|---|
| **Retell AI** | ~620ms — fastest | ElevenLabs, Azure, others | Included on Pay-as-you-go | ~$0.115–0.155 | Best overall, lowest latency |
| **Vapi** | ~700ms optimized | Any provider | +$2,000/month add-on | ~$0.25–0.33 | Maximum flexibility, best API |
| **Bland AI** | ~800ms | ElevenLabs, PlayHT | Enterprise only | ~$0.11–0.14 (all-in) | Best no-code call builder |
| **Synthflow** | ~750ms | ElevenLabs, Azure | Enterprise only | ~$0.16 (est.) | Best no-code builder |

*Sources: retellai.com/pricing, vapi.ai/pricing, bland.ai/pricing, synthflow.ai/pricing — verified June 2026. Bland AI is all-in (LLM + STT + TTS + telephony bundled). Synthflow all-in is an estimate (Voice Engine + GPT-4.1 + Twilio); rate not shown explicitly on PAYG page.*

**On pricing:** At 500 calls/month × 3 minutes average, Retell costs roughly $173–233/month all-in. Bland AI comes in at ~$165–210/month. Vapi is the most expensive at $375–495/month before the HIPAA add-on.

> **Market context:** Vapi just raised $50M backed by Microsoft, Kleiner Perkins, and Bessemer — having processed over 1 billion calls. Retell hit $50M ARR and handles 50M+ calls per month. The AI voice agent market in healthcare is growing at 37.9% annually and Gartner projects 80% of healthcare providers will invest in this by end of 2026.

## Live Testing: Retell AI vs. Vapi

I used the same script and the same voice on both platforms to make the comparison as fair as possible. Five call scenarios were tested on each: a clean baseline call, a busy-customer scenario, two off-script situations where the customer asked unexpected questions, and a test where the customer directly asked if the agent was an AI.

To analyze the recordings, I ran a local Whisper transcription script on each audio file, then fed the transcripts into Claude Code, ChatGPT, and Gemini for cross-analysis. Uploading audio directly to those tools had accuracy issues — running Whisper locally first gave much cleaner results.

### Call Duration Comparison

Same conversation, same script:

| Scenario | Retell | Vapi |
|---|---|---|
| Normal call | 49 sec | 78 sec |
| Customer is busy | 24 sec | 35 sec |
| Customer asks questions we can't answer | 48 sec | 69 sec |
| Unexpected questions throughout | 77 sec | 111 sec |

Vapi calls ran 43–58% longer for the same conversations. This isn't padding — it reflects slower response timing and longer answers.

### What I Heard

**Retell AI** responded in roughly 1–1.5 seconds after I finished speaking (consistent with Retell's published average of ~620ms end-to-end latency). Felt natural. The agent stayed on track even when I asked unexpected questions, handled "how many units were in the order?" by honestly saying she didn't have that detail and offering to have the account team call back, then returned to the main flow without losing her place. Sounded like a real, efficient customer service rep.

**Vapi** responded in 2–3.5 seconds after I finished speaking in most turns — Vapi's dashboard reported end-to-end latency of ~1,400–2,000ms per turn during my test sessions. The voice quality was strong but the pauses were noticeable. Responses were also longer and more explanatory than necessary. One moment stood out: when I asked Vapi's agent where the delivery was going, it asked *me* to tell *it* the address rather than confirming the one on file. That's the kind of thing that immediately breaks trust on a cold outbound call.

**One thing Vapi does better than Retell:** post-call analytics. After every call, Vapi shows a full breakdown which includes response latency per turn, customer sentiment, an AI-generated summary of what happened. Retell doesn't have this out of the box. For monitoring call quality at scale, that's a meaningful advantage.

## Recommendation

**Retell AI.** It sounds more natural, responds faster, and handles unexpected questions better in its current configuration. For a busy receptionist getting an unsolicited supplier call, the first ten seconds determine whether they engage or hang up — and Retell wins those ten seconds more consistently.

**Bland AI** is still worth a live test. Their BAA is Enterprise tier only, not included on standard plans. Retell's HIPAA compliance is available on their self-serve Pay-as-you-go plan, which is the more accessible option. Bland AI's slightly lower per-minute cost (~$0.11–0.14/min all-in) may still make it worth evaluating once a demo can be arranged.

Vapi is not a bad platform — its API flexibility and voice quality are genuinely impressive — but in its current form it's slower and more expensive for the same result.

## What's Next

Once real order management system API access is available, order data can be connected to the calls so the agent can accurately state order numbers, delivery dates, and product quantities rather than using placeholder information. That's where this becomes a real operational tool rather than a demo.

Additional optimization ideas like swapping the voice provider to reduce response time further, adjusting how the AI reasons through unexpected questions are worth working through in the next phase.

## Research Papers

1. **Deepgram 2025 State of Voice AI Report** — 72% of organizations cite performance quality as the top barrier to deploying voice AI. Establishes 500ms as the threshold above which callers notice latency.

2. **"Real-Time Voice AI Latency: Causes and Mitigation"** — Telnyx Engineering Blog, 2025. Breakdown of where time accumulates in the voice pipeline. Confirmed the architectural explanation for sequential pipeline performance gaps.

3. **"Hallucination and Recovery in Constrained Voice Agents"** — Hamming AI Resources, 2025. Documents how production voice agents handle questions outside their knowledge boundary. Informed the off-script test scenarios used in this evaluation.

## Sources

- [Vapi $50M Series B — GlobeNewswire, May 12 2026](https://www.globenewswire.com/news-release/2026/05/12/3292882/0/en/vapi-raises-50m-series-b-as-it-reaches-1-billion-calls-powering-the-next-generation-of-enterprise-voice-ai.html)
- [Retell AI Wing VC ET30 — Yahoo Finance, April 2026](https://finance.yahoo.com/sectors/technology/articles/voice-ai-startup-retell-ai-131700326.html)
- [AI Voice Agents in Healthcare — 37.9% CAGR — GetProsper](https://www.getprosper.ai/blog/ai-voice-agents-in-healthcare-market-size-trends)
- [Air AI FTC settlement — ServiceAgent](https://serviceagent.ai/blogs/air-ai-review/)
- [Retell AI pricing 2026 — Cekura](https://www.cekura.ai/blogs/retell-ai-pricing-per-minute)
- [Vapi pricing 2026 — Emitrr](https://emitrr.com/blog/vapi-pricing/)
- [Bland AI pricing 2026 — Ringg AI](https://www.ringg.ai/blogs/bland-ai-pricing)
- [PolyAI pricing 2026 — Nurix AI](https://www.nurix.ai/blogs/polyai-pricing-features-guide)
- [HIPAA-compliant voice AI 2026 — GetProsper](https://www.getprosper.ai/blog/hipaa-compliant-voice-ai-providers-healthcare-guide)