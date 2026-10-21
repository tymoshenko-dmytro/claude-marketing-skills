# Atlas Cloud

**What it gives you:** generated shots for videos: people, rooms and objects that do not exist as footage or UI. One API for several video and image models (Seedance for shots, OmniHuman to play your own voiceover as a talking person, Nano Banana for keyframes and multi-reference edits).
**Used by:** `video-generated` (its `scripts/atlas.py` client), called from `video-studio`.
**Access:** API key.
**Cost:** pay per generation, no subscription. Top-ups start at $25 (card via Stripe, Alipay, WeChat Pay, crypto). Model prices: <https://www.atlascloud.ai/pricing/models>; the prices the skill measured are in `skills/video-generated/references/atlas.md`.
**Setup time:** ~5 minutes

## 1. Get the key

1. Sign up at <https://www.atlascloud.ai/login>.
2. Top up a small amount first (Console → billing). A test round of keyframes plus two short shots costs a few dollars.
3. Console → **API Keys** (<https://www.atlascloud.ai/console/api-keys>) → create a key. It is shown once; copy it straight into the keys file: `ATLAS_API_KEY=...` (`kit.py open`).

## 2. Check

```bash
python3 skills/connect/scripts/kit.py doctor --live      # ATLAS_API_KEY · accepted (a free request for a job id that does not exist)
```

## Safety

- Every submit spends money. The skill's doctrine keeps spend low: settle identity, geometry and composition on still images first (cents), then generate video once; upscale an approved take instead of regenerating it.
- On a model you have not used before, make one paid call and read the bill in the dashboard before the second.
- Uploaded references (photos of people, product shots) go to Atlas Cloud's servers. Use only material you have the right to use, and never a real person's likeness without consent.

## Gotchas

- The API is `https://api.atlascloud.ai/api/v1` with `Authorization: Bearer <key>`; media you pass by URL must be public or uploaded first (`/model/uploadMedia`, the client does it).
- Jobs are asynchronous: submit, then poll. The client keeps each job's JSON in `~/.local/share/marketing-agent-kit/atlas/jobs` (change it with `--jobs` or `ATLAS_JOBS_DIR`), so a result is never lost when a poll times out; `atlas.py poll <id>` picks it up again.
- Text, captions, UI and logos never go into a generated picture; they are layered on top in HyperFrames (`video-build`).

## Links

- Docs: <https://www.atlascloud.ai/docs> · Keys: <https://www.atlascloud.ai/docs/api-keys> · Top-up: <https://www.atlascloud.ai/docs/billing/topup>

*Checked 2026-10-21.*
