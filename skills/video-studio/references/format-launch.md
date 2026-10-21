# Format: launch film

A 15-25 s film that makes a stranger understand a product, project or site in one view.
Adapted from `/brag-slim` (github.com/latent-spaces/brag, MIT), where this kind of film is
called a "brag". Four launch films were made with this recipe before it was written down; the
lessons below come from them.

## Answer before planning

What is it (one sentence)? Who is it for and what does it do for them? What sets it
apart? The most impressive or funniest TRUE claim? The visual hook? Which real UI or flow
is shown (entry → key action → result)? Tone? The one-line share caption?

The funniest true claim is usually in the product's own data. One film's was that the
product's own editor agent approved only 1 of 7 articles it was given.

## Choose the structure, do not default to it

(Borrowed: lemo-opuscar DIRECTOR §4, MIT.) Launch films drift into hook → reveal →
highlights → end card every time. Before the plan, write in the film's `plan.md`:

1. **Three candidate structures**, a few lines each - e.g. a race (old way vs this), a
   before/after, one user's task from start to result, a countdown, a list that turns, a
   single claim proven live. Pick one and say why. The first idea is usually the last film.
2. **Not the last film again.** Open the previous launch film's plan and poster (keep a list
   of your launch films - name, date, folder, plan, poster - in your films folder, e.g.
   `launch-films.md`, and add a row when one ships). Compare six things: structure, opening,
   the signature shot, the camera path, the shape of the music, the ending. At least four must
   differ; rethink the ones that match. A deliberate series (same look for one campaign) is the
   exception - say so in the plan.
3. **One signature moment** at the peak - a move only this product's UI can make (see
   "Moves for a product UI" below).

## Shape

Hook (2-3 s) → reveal (2-4 s) → 2-3 highlights → punchline / end card (2-4 s).
15-25 s, 18-22 the sweet spot. Narration does not extend the window: if the voice
overruns, cut the script and regenerate.

Tones: `default` punchy, 4-5 scenes, soft transitions · `polished` 3-4 scenes, long holds ·
`yc-parody` deadpan launch, one claim per scene, hard cuts · `deadpan` big empty space ·
`cinematic` trailer type, dramatic wipes · `app-store` clean feature cards. Freeform
direction ("fake Series A launch from 2016") refines a preset.

## Build

- Picture: the **video-build** skill (`references/product-ui.md` - the real UI, composed
  from its own classes, a measure pass, word-by-word captions). Moves and the signature
  moment: **video-moves**.
- Sound: **video-sound**; a beat-mapped track from the library - land the big reveal on a
  strong cue near the word that carries it.
- Gates: **video-check**; poster = the strongest settled frame, which must already be
  frame 0.
- Before any of these start: `brief.md` from `plan.md` (video-studio `references/brief.md`).

## Moves for a product UI

The full camera and editing grammar (24 moves, with code and sound) lives in the
**video-moves** skill; pick the signature moment there. The notes below are the launch-specific ones.

(Borrowed: lemo-opuscar's "Living Screencast" and "Dark Tech Keynote" styles, MIT - ideas
restated, no code taken. Not yet proven in a shipped film: when one survives the user's
review, move it to laws.md with that film as its source; if one is rejected, delete it here
and write the rejection into laws.md.)

- **Spotlight freeze** (video-moves 04 crash zoom + 16 freeze frame, tested on the moves test
  reel) - on the one promise to remember, a quick push-in to one badge or number, the rest of
  the frame dimmed by a vignette, a held beat of near-silence. One per film. (Push in, then hold
  still: the law against continuous zoom on live UI text stands.)
- **Time-lapse with a tag** (video-moves 15, tested) - a long process (indexing, a batch job)
  runs at N× with a small "▶▶ 4×" tag; the viewer is told time is compressed instead of being
  misled.
- **Keystroke HUD** - shortcuts and keys shown as small key caps at the bottom while the
  cursor works; the cursor is the user - never a drawn hand.
- **The film changes state** - a toggle's effect does not stop at the preview, it takes over
  the whole film and returns later. For a translation product: switching the language in the
  UI turns the rest of the film (captions, UI, voice) into that language.
- **Whip between panes** - cause in one pane, effect in another: video-moves 19 (tested: one
  world with both panes, blur from the lens speed, max ~8% of the frame).
- **Captions are a component of the UI**: a pill at the bottom, never over the element being
  discussed. Text the cursor types in frame is its own caption - not shown twice.
- **One accent, one problem colour.** The accent is reserved for what the product is or
  does (the product's element, the key number, the confirmation). A problem colour (red
  badges, warnings) lives only while the problem lives; after the turn it never returns.
  If two things wear the accent, one is wrong.
- **The big number gets its own screen** with nothing over it - no caption on top; the
  voice carries the sentence.
- **Exits are designed too**: an element retracts or collapses, it does not just fade.

## A speed or quality claim (worked pattern)

One launch film proved a latency claim for a speech product: a race replayed from real API logs
(a measure script that streams any audio, any language pair, against production or a dev
build, and logs every output chunk), then a "same sentence, two numbers" freeze, then use cases
and languages, then an end card with a slogan - and no call to action, because the model was not
released yet. The laws it produced are in laws.md: median of three runs, material that shows the
claim, the slow side's state in words, time pills, hear the product's own voice.

## Deliver

`<name>.mp4`, `<name>.jpg` (poster), `share-copy.txt` - 1-3 sentences postable as-is, no
"excited to share", and `plan.md` with where every on-screen number came from.
With the film goes `REVIEW.md` (video-check `references/review.md`) and its open P2 list.
Creation and rendering stay local; publishing is a separate explicit request.
