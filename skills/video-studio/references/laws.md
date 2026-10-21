# Laws

Rules that survived contact. Each one cost a rejected cut, a wasted render or money.
The source is in brackets where it helps to know where a rule came from: a kind of film it was
learned on, or an outside source - [brag-slim] is the launch-film skill from
github.com/latent-spaces/brag (MIT), lemo-opuscar is github.com/lemomo-ai/lemo-opuscar (MIT).

**Scope.** House laws bind every film. "Brand laws (yours)" binds your own brand's films
only - it starts as a template for you to fill. Executor skills (video-sound, video-build,
video-moves, video-3d, video-generated, video-check) implement these laws and never restate or
contradict them; when one does, the law wins and the executor is fixed in the same change. A
law under test says so and names the test.

# House laws (every film)

## Story and copy

- **The hook lands the essence at once**: either what the thing is or a pain a stranger
  understands in one read (who, what is in the way). No number, mechanism or feature as
  line one.
- **No AI-sounding copy**: no triple parallel lists, no staccato fragments ("Not a sales
  call."), literal wording over clever. Shorten, don't punch up.
- **Every claim is grounded.** Names, numbers, capabilities, quotes - must appear in the
  product, its UI, the brief or the project's own files. Tone, framing, jokes, connective
  lines may be invented. No invented standards (WCAG, SOC 2, GDPR...). Run the claim read
  on every language version: translation quietly strengthens claims. [latent-spaces/brag
  claim-grounding check]
- **Reference sent = copy it to the maximum** - arc, style, pace, devices. Not copied:
  their words (yours, from your brief), their characters (yours), their aspect when your
  channel needs another. (Recipe: `format-reference-copy.md`.)

## Picture

- **Show the subject in use.** Real UI, real copy, real output; a voice product lets real
  voices be heard. Diagrams about the product read as generic.
- **Reuse the real thing rather than redraw it**: the app's own stylesheet, markup, assets.
  Rebuild only what cannot be reused. [brag-slim]
- **A finished element is read from its canonical file**, never re-cut from the raw source.
  Keep one list of your canonical pieces (end card, product panel, demo) and reuse them.
- **Motion has a cause** - a click, a response, a camera following. No decorative
  breathing or density-driven twitching. Watch first, measure second.
- **But no held frame is frozen**: a slow underlay (push-in 2-4% across a scene, or a
  decaying 4-6% scale) keeps a settled frame alive. "Breathes 1.5%" is not motion.
- **Never zoom live UI text continuously.** A slow push on a real app screen re-rasters every
  glyph each frame and is seen as the picture shaking [a product promo, 2026-10-08]. On UI,
  keep the camera still between moves; let the cursor, a marker or a cut keep the frame alive.
  The push-in above is for photos, video and big type. Camera moves on UI (video-moves) are
  short, have a cause and land.
- **The words and the screen say the same thing.** "Gathers facts with their sources" over article
  prose was read as a mismatch: show the research with its source links. Pick the screen by the
  noun in the line. [a product promo, 2026-10-08]
- **Real data beats a sample.** Empty fields, a $0.00 cost and a made-up article read as a demo.
  Use the product's real install (a copy) when one exists. [a product promo, 2026-10-08]
- **Say what private data is on screen - then the user decides.** Before a film (or a proof) is
  shown, list every sensitive item visible or audible in it: API keys and tokens, emails and
  phone numbers, customer and personal names, internal hosts and URLs, money and invoices,
  anything from a .env or a credentials file. Do not silently swap or blur them: the user
  sometimes shows real data on purpose, films themselves, or plants their own stand-ins. Ask once,
  in the plan or with the proof ("on screen: the real Stripe page with 3 customer emails -
  keep, or plausible stand-ins?"), and record the answer in the plan. Never read a .env or a
  key file to put it on screen. [after brag's privacy rule]
- **One idea per line, on a clean card.** A real app page full of text, scrolled and zoomed, reads
  as a gallery of screenshots and nothing is understood. The cut that worked [a product promo,
  2026-10-08] lifted ONE component or fact per spoken line - the keyword with volume/KD, three
  ranking pages, one fact with its source, one diff, one finding - onto cards built from the
  product's own tokens and filled from its real data, with a strip for the pictures. Keep the
  live UI for the one moment of input (the composer, typed into).
- **One idea per screen.** "Who it is for" and "which languages" on one screen read as a jumble;
  two screens, equal-height cards, centred. [a speech-product promo]
- **Show a picture whole.** A UI thumbnail that crops the image, or a frame that cuts a card, reads
  as broken; frame the figure itself.
- **Whole objects** in props and crops; end a beat before the source page transitions.
- **One world, one hand.** Never fan a film out to parallel workers; seams and drift show.
  Build a 10-12 s proof by one hand and get it approved before continuing. (Separate test
  films may be built in parallel - each is its own world.)
- **Readable**: a line meant to be read stays settled ~0.3 s per word, counted from when
  the whole line is on screen. Pace comes from motion and cuts, not from pulling text early. [brag-slim]
  Measured by video-check `scripts/readcheck.mjs` (qa.md 4). This norm suits text the voice also
  says, and one short line on a clean card: a 6-word line needs 1.8 s. Switch to `--norm strict`
  (letters ÷ 15 + 1.5 s - the same line needs ~3.5 s; lemo-opuscar's norm) when the text has to
  be read rather than heard: the voice does not say it; the film will autoplay muted (LinkedIn
  feed); it is a number, URL, name or price to remember; it is a list (eight language chips);
  the viewers read it in a second language. Captions revealed word by word with the voice are
  read as they are spoken: ≥ 0.6 s after the last word, ≥ 1.8 s on screen in all.
- **Stagger transitions**: old content out, then new in - or dip through the ground. A
  crossfade of two busy layouts is a muddy double exposure. [brag-slim]
- **Every frame postable.** The poster is the strongest settled frame and is frame 0: open
  the film on it (a settled first frame), never splice a poster over a fade-in - the
  spliced frame blinks (found by video-check's seam scan, 2026-10-14). [brag-slim]
- **A low-contrast accent never carries small text.** Measure the film's accent against its
  grounds; under 4.5:1 it marks only large numbers (≥ ~48 px bold), borders and lines.
  [a speech-product promo, hyperframes check]
- **A claim about speed or quality is shown with measured data**: run the real thing and
  replay its log. Compare against an honest, labelled baseline. Run each side at least three
  times and replay the MEDIAN run, never the best. Pick material where the difference is the
  product's own claim (an opening item both sides handle equally reads as a tie first). Show
  the state of the slow side in words ("Waiting for the end of the sentence") - a blank panel
  reads as nothing. Comparing against your own previous version reads as self-criticism;
  nobody watching asked for it. [a speech-product promo, v1 → v6]
- **Time stamps next to text are pills with margins on both sides**, placed before the piece they
  belong to; a bare superscript glues to the next word. [a speech-product promo]

## Sound

- **Audio first.** Durations come from the takes; a v3 take of the same words varies by
  0.3 s run to run, so the grid cannot be planned before the audio exists.
- **Nothing with a tail over a voice**, and never on a first syllable. Under speech only
  texture at -24 dB or lower; events that should be heard wait for a gap.
- **Sound only where something visibly happens.**
- **Effects share one room, never under a voice.** A short synthetic room (0.6 s, 250 Hz-7 kHz,
  -16 dB under the dry effects) on the effects outside speech; off while a voice passage runs.
  It replaced "interface sounds dry, no reverb" after a blind A/B picked the room version
  (effects a little louder, more interesting), 2026-10-14. video-sound's mix.py does it by default.
- **Fewer, distinct events.** A palette of 25-30 sounds with low-mid body, pitch-varied;
  hundreds of dry high clicks = ear fatigue. Check `highFrequencyRisk` in the library
  catalogue before repeating a sound.
- **Duck per passage, not per word; no dynamic gain anywhere** (video-sound `references/audio.md`).
  A voice-keyed compressor pumped the bed ~11 dB between words.
- **Names are checked by ear-equivalent**: `--must` in video-sound's gen_voice.py. A take that
  mispronounced the product name (one wrong first consonant) passed the whole-line gate.
- **For a speech or audio product, the wow is HEARING it**: play the product's own output voice,
  placed as a listener hears it, over the ducked original. A text-only speed race reads as a
  chart. Match the output voice's loudness to the input (it came out 6 dB under), and level it:
  a pipeline that voices each translated piece separately lands pieces 10-15 dB apart - under a
  ducked original the quiet ones vanish (`dynaudnorm=f=200:g=5:p=0.9:m=25` on that track only).
  [a speech-product promo, v4-v6]

## Generated video

The **video-generated** skill carries the doctrine (`references/atlas.md` there): one scene =
one generation, identity/geometry/composition validated at image prices, the reference beats
the prompt, approved takes are upscaled not regenerated.

# Brand laws (yours)

Rules that bind only your own brand's films: the things a stranger to your company would get
wrong. Write each as one rule plus the reason or number behind it, with its source in brackets,
like the house laws. Add a rule when a film of yours is rejected for something a law would have
prevented; delete a rule when it stops being true. Keep product facts out of here - they live in
your product brief.

Examples of the kind of rule that belongs here (replace them with your own):

- **Hook pattern for your product**: what it is (`A live AI <product> for <who / which
  situation>`) or the buyer's pain (who, what is in the way). Never the mechanism first.
- **Realism rules for your setting**: show the world your customers actually work in. Example:
  "Our customers' events run online (video calls) - never show a conference hall, headsets or a
  booth." And name the real pain: "The pain with the old way is cost and management overhead -
  people do not simply fail to show up."
- **Aspect per channel**: "16:9 for the YouTube campaign and LinkedIn; vertical only for
  Shorts/Reels; never copied from a reference."
- **Brand accent contrast, in numbers**: "Our accent #XXXXXX is 3:1 on white and 2.3:1 on our
  blue - never for small text. It marks only large numbers (≥ ~48 px bold) on white; small
  accents use the blue."
- **Claims come from your product brief** (`<path to your product brief>`), the product and its
  UI; references are re-cast with your own identity (logo, mascot, colours).
- **Speed claims use your own measurement script**: stream real input through the real API,
  replay the log, and label the baseline honestly.
