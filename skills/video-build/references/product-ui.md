# Building a film from a real product UI

The pattern behind the launch films (video-studio `references/format-launch.md`): the film is
built from the product's own pages, not from a redrawing of them. A launch film built this way
kept three files in its composition folder - `build.py` (emits the composition), `measure.py`
(the measure pass below) and `timeline.json` (the measured numbers build.py reads).

1. **Get the real UI.** For your own web app render the actual pages (e.g. a Flask test
   client with auth off, or the dev server) and lift the markup + stylesheet; for a site,
   `hyperframes capture <url>` or a headless browser, scrolling section by section.
2. **Compose from the real classes**, adding only wrappers for scale and motion
   (`.bvz` static scale, `.bvpush` underlay, `.bvent` entrance/exit). Scale the app
   1.1-1.4x so 15 px UI text reads on a phone.
3. **Measure, don't guess**: a measure pass with the timeline off gives cursor targets,
   scroll stops, caption fits and scene heights (a headless browser loads the composition,
   reads `getBoundingClientRect()` of every target once, writes them to JSON for build.py).
4. **Captions word by word** from the takes' word timings (video-sound `gen_voice.py --align` →
   `<tag>.words.json`: the script's words on ElevenLabs' own times, any language):
   `scripts/captions.mjs film.json` builds the cues (breaks chosen to pass readcheck, RTL and mixed
   scripts handled) and the block to paste - rules, fonts and checks in `references/captions.md`.
   A caption broken by hand (one `div` per written line) takes its times from the same words.json.
