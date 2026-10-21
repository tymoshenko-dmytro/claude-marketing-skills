# Generated shots (Atlas Cloud)

People, rooms and objects that do not exist as footage. Provider: **Atlas Cloud** - one key, one
bill, several model families behind one API. Everything spoken, written or branded stays out of
the generated picture: text, captions, UI and the end card are HyperFrames layers on top.

## Get a key

1. Sign up at <https://www.atlascloud.ai> (Log in → create an account; the email must be verified
   before you can pay).
2. Add balance: console → **Top-up & Billing** (<https://www.atlascloud.ai/console/billing>). It is
   a prepaid balance; at the time of writing the minimum top-up was $25 (card via Stripe, Alipay,
   WeChat Pay, crypto). A request with too little balance fails with `402 Payment Required`. No free
   credits were mentioned. Check the site for the current terms.
3. Create a key: console → **API Keys** (<https://www.atlascloud.ai/console/api-keys>) → **Create
   API Key**. It is shown once - copy it straight into the keys file.
4. `ATLAS_API_KEY=...` in `~/.config/marketing-agent-kit/.env` (chmod 600). The kit's
   `connections/atlas-cloud.md` has the same steps.

Docs: <https://www.atlascloud.ai/docs>. List prices: <https://www.atlascloud.ai/pricing/models>
(they are base tiers - see "Price as billed" below). Signup and billing steps checked 2026-10-21.

## Client

`scripts/atlas.py` - upload, submit, poll, download; every request and response is kept as JSON
in the jobs folder (`ATLAS_JOBS_DIR` or `--jobs`; default
`~/.local/share/marketing-agent-kit/atlas/jobs`). Point it at the film's own folder
(`--jobs <film>/jobs`) so the payload of every paid shot stays with the film.

```bash
A=${CLAUDE_SKILL_DIR}/scripts/atlas.py
python3 $A upload keyframe.jpg                              # -> public URL for the payload
python3 $A --jobs jobs run video s01.json --tag s01 --out shots/
python3 $A --jobs jobs run image kf01.json --tag kf01 --out keyframes/
```

`s01.json` is the model's request body as its Atlas model page shows it (model id, prompt,
`image` / `last_image` URLs, duration, resolution). From Python: `import atlas;
atlas.run("video", payload, tag, out_dir)`.

- API: `POST https://api.atlascloud.ai/api/v1/model/generateVideo` (or `generateImage`), poll
  `GET /api/v1/model/prediction/{id}`, `Authorization: Bearer <key>`. Media go in as a public URL
  (`POST /model/uploadMedia`) or base64.
- **No balance endpoint. On any new model: one paid call, then read its line on the dashboard,
  before the second call.** The catalogue price and the billed price have differed by 4x.

## Models (picked after a paid side-by-side test, 2026-09-03)

Prices are what the dashboard billed on real jobs, September-October 2026. Re-check them on the
dashboard after your first call of each model.

| Role | Model | Price as billed | Notes |
|---|---|---|---|
| Shot lane default | `Seedance 2.0` with a voice sample | ≈ $0.50 per 1080p second on the meter (tokens ≈ pixels × frames / 1024 ≈ 48k per 1080p second); ≈ 0.44x that at 720p | the catalogue's $0.112/s is the base tier, not 1080p. Order the duration tight to the line - slack gets filled with stray sounds |
| Exact pronunciation, localisation, frontal singles | `OmniHuman 1.5` (portrait + your audio → talking video) | $0.12/s | the only model that plays YOUR track as it is; ≤ 15 s recommended |
| Reserve | `MiniMax H3` | ~$0.08/s at 2K | holds framing and likeness; a rigid body must be told to move |
| Keyframes / stills, multi-reference edits | `google/nano-banana-pro/edit-developer` | $0.07 per image | up to 14 references |
| Out | Seedance 2.5, Veo 3.1 | | 2.5 pushes in and re-voices an audio reference; Veo scores music under the line |

Measured jobs, for planning: 8 s of Seedance 2.0 image-to-video at 720p = 173,700 tokens
(≈ $1.8); 6 s at 720p 3:4 = 131k tokens (≈ $1.37).

Camera terms for a shot's prompt (one move per shot; term + subject + direction + duration):
`../video-moves/references/prompts.md`.

## Doctrine

The production line that held up: story → beat sheet approved by the user → per shot, the voice
first (TTS) → three paper gates at image prices → generate → automated acceptance (video-check).

- **One scene = one generation; no scene is generated twice.** A longer film is multi-scene by
  script; continuity across scenes is carried by the audio and the sheets.
- **Identity, geometry, composition are three artifacts validated at image prices**: character
  sheets, a set plate (blocking decided first, fewest props), shot keyframes.
- **The reference beats the prompt.** Change the reference, never argue in prose. A targeted fix
  is a multi-reference edit: the anchor + a clean reference for one element + "change exactly one
  thing".
- **An approved take is upscaled, never regenerated.**
- **Tiers**: stills → cheap check → master; one variable per iteration; plan one re-roll in three.
- **Proper nouns stay out of natively spoken lines.** If a name must be said, the line goes
  TTS-first through OmniHuman.

## A looping shot

`bytedance/seedance-2.0/image-to-video` takes `image` (first frame) and `last_image` (end frame):
give both the SAME keyframe and the shot ends where it began - the last and first frames differed
by 1.2 (mean abs, 0-255) against a median frame step of 3.7, invisible as a loop. Build the
keyframe in code (the subject on the film's own ground, empty space where text will go) and lay
everything written on top in video-build. The model holds the end pose ~0.8 s; overlays keep that
stretch moving. 8 s at 720p comes back at 24 fps, 193 frames (drop the last). Upload a JPEG
keyframe - a 1.6 MB PNG timed out on `uploadMedia`.

## A transparent loop (a character on a web page)

For a character that must sit on a page (alpha video), generate it on a FLAT ground and
colour-key it yourself: `hyperframes remove-background` (an ML matte) dropped a white robot face
and its speech bubbles in some frames. The Seedance ground stayed flat (Lab std < 1 over the
loop), so a Lab-distance key (alpha ramp 7 → 22, the border median as the ground, the ground
unmixed from edge pixels) was clean on navy, blue and white. Pick the ground close to where the
clip will sit, so any residue disappears. Deliver VP9-alpha WebM for Chrome/Firefox and HEVC-alpha
(`hevc_videotoolbox -alpha_quality`, tag `hvc1`, in .mp4 - many static hosts do not serve .mov)
for Safari, and choose by browser engine in JS: both browsers claim to play both and then drop
the alpha.

## Assembly traps

- Render long video clips with `-w 1` (parallel workers returned black tails).
- A plate generated at 24 fps: render the composition at 24 fps (`data-fps="24"` on the root).
  At 30 fps every 5th frame repeats - visible judder, and video-check's seamscan flags the repeats
  as HELD/FLASH.
- `blackdetect` misses black frames under a caption; scan `signalstats` YHIGH < 30 at 12 fps.
- Pace by speed, not by cutting: speech ~1.12x, silences ~2.6x, one filter pass per scene.
