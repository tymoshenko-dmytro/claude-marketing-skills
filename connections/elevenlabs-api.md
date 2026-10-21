# ElevenLabs

**What it gives you:** voiceover (text to speech in 30–90+ languages, many voices) and generated sound effects — the audio layer of ad videos.
**Used by:** `video-sound` (voiceover with a transcript and name check, generated sound effects); voiceover for any video pipeline.
**Access:** API key (`ELEVENLABS_API_KEY`) for scripts; OAuth for the hosted MCP server.
**Cost:** free tier 10k credits a month (no commercial licence; **sound effects are blocked on free**). Starter $6/mo with a commercial licence. API speech ~$0.08 per 1k characters on Multilingual v2 / v3, ~$0.04 on Flash. Sound effects ~$0.12 per minute.
**Setup time:** ~5 minutes

## 1. Get a key

1. <https://elevenlabs.io/app/settings/api-keys> → Create.
2. **Restrict it:** allow only Text to Speech and Sound Effects, set a credit quota. The key is shown once.
3. Keys file: `ELEVENLABS_API_KEY=...`

## 2. Connect

**Scripts** call the API with the header `xi-api-key: <key>`:

- Speech: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}` with `{"text": "...", "model_id": "eleven_multilingual_v2"}`
- Sound effects: `POST https://api.elevenlabs.io/v1/sound-generation` with `{"text": "...", "duration_seconds": 0.5–30}`

**Hosted MCP** (OAuth only, voice generation from chat):

```bash
python3 skills/connect/scripts/kit.py mcp add elevenlabs
#   = claude mcp add --scope user --transport http elevenlabs https://api.elevenlabs.io/v1/mcp
```

Then `/mcp` → elevenlabs → Authenticate. Also in the Claude connector directory, and as a plugin: `/plugin marketplace add elevenlabs/plugin`.

## 3. Check

```bash
python3 skills/connect/scripts/kit.py doctor --live      # ELEVENLABS_API_KEY · accepted
```

(A key restricted to TTS may report "restricted" on the account check — that's fine if speech works.)

## Models (autumn 2026)

| Model | Use |
|---|---|
| `eleven_v4` | new flagship (GA 2026-09-28), 90+ languages — test before switching |
| `eleven_v4_turbo` | real-time |
| `eleven_multilingual_v2` | API default; reliable for non-English |
| `eleven_v3` | expressive; now "previous generation" |
| `eleven_flash_v2_5` | fast and cheap; replaces the deprecated Turbo v2.5 |

## Gotchas

- The old local MCP (`uvx elevenlabs-mcp`) is deprecated and archived; use the hosted one.
- Your account's own voice list is often English-only. For other languages, find native voices in the shared library (`GET /v1/shared-voices?language=es`) — their ids work in TTS directly.
- **Audio first, picture second:** generate the voiceover, measure it, then cut the video to it.
- **Transcribe and compare** every generated line against the script before it ships (Whisper or any STT) — models occasionally skip or repeat words. Normalise digits and currency first, or the check cries wolf.
- Level every line before mixing; voices arrive at different loudness.

## Links

- Auth: <https://elevenlabs.io/docs/api-reference/authentication> · Models: <https://elevenlabs.io/docs/models>
- Hosted MCP: <https://elevenlabs.io/docs/eleven-agents/operate/hosted-mcp> · Pricing: <https://elevenlabs.io/pricing/api>

*Checked 2026-10-01.*
