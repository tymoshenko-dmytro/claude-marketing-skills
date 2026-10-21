# Intake: how something new gets into the studio

Sources: an outside repo or skill, a reference film, a rejection in review, a trap found
while building. Each lands in exactly one place.

Every topic has ONE owner skill. The orchestrator (video-studio) owns what a film is and
what binds it; executors own how a craft is done. Nothing is written in two places - the
second place links to the owner.

| What it is | Where it goes |
|---|---|
| A rule that would have prevented a bad cut, any film | video-studio `references/laws.md` (house laws), with its source in brackets |
| A rule only for your brand's films | video-studio `references/laws.md`, "Brand laws (yours)" |
| The user's taste (a phrase from a review) | video-studio `references/laws.md`, in their words plus what it means in practice |
| What every film's handoff must carry (a brief field), the brief/executor boundary | video-studio `references/brief.md` |
| A rule about one kind of video, its shape or story | that format's recipe in video-studio |
| A new kind of video, made a second time | a new `references/format-*.md` + a row in `references/formats.md` (video-studio) |
| How to build a composition; a HyperFrames / GSAP / render trap | video-build (`scaffold.md`, `product-ui.md`, `captions.md`, `hyperframes-gotchas.md`) |
| A camera or editing move, its staging, numbers, code or sound | video-moves (`references/moves.md`, `references/rigs.md`, `scripts/`) |
| A three.js scene, a WebGL trap, a 3D recipe | video-3d (`references/contract.md`, `recipes.md`, `qa-3d.md`) |
| Voice, music, effects, the mix, a sound check | video-sound (`references/audio.md`, `scripts/`) |
| Music, sound effects as assets | the sound library (video-sound): licence row first, then the file, then analyse, then rebuild the catalogue |
| A generated-video model, price or doctrine | video-generated (`references/atlas.md`) |
| A check that would have caught a defect; a review rule | video-check (`references/qa.md`, `references/review.md`) |
| A tool or script | `scripts/` of the executor that calls it; the library's `tools/` if it measures assets |
| A new craft (e.g. real 3D) | a test film first; a new executor only after the user approves the test |
| An outside rule not yet tried in one of your films | the owner's file, under "borrowed, not yet proven"; it moves to `laws.md` when a film passes the user's review with it, and is replaced by a rule against it if rejected |

## Taking from an outside source

1. Clone it somewhere temporary, but **copy what you keep into the library or the skill
   before the session ends** - one clone sat in a scratch folder and the OS deleted it, music
   and all, while a finished video still pointed at it.
2. Read its licence and every asset's licence. No licence stated = find the original
   source (one sound set named its source only inside an analysis file).
   - **Noncommercial** (PolyForm Noncommercial, CC BY-NC): ideas only, restated in your own
     words and written from scratch; no code, cards or assets. Marketing films are commercial
     use.
   - **MIT, Apache-2.0, BSD**: code may come in. Keep the original copyright and licence header
     at the top of every file you take or port (e.g. `../video-build/scripts/captions.mjs`, ported
     from nanoclip-cutting-room, MIT), and name the source where it lands.
   - **CC0, CC BY**: assets may come in; CC BY needs the credit line in the library's licence
     file.
3. Prove a tool reproduces its published output before trusting it (the music cue script was
   re-run on its source's own published example: identical tempo and all 206 beats).
4. Upstream skills you merely use (heygen-com/hyperframes and friends) are never edited;
   if one of their ideas is worth keeping, restate it in the owner skill in your terms.
5. Write down where it came from: in the film's own notes for a film-only change.

## Where a change to these skills goes

In your own copy, edit the owner file from the table above. To send it back to this kit, open a
pull request as the kit's CONTRIBUTING.md describes: one change per PR, the source (film, repo,
review) and how you tested it. Third-party code also gets a line in THIRD_PARTY_NOTICES.md.
