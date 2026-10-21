# Sound of the moves

Sound does half the work of a move. Keep one timeline that the picture and the sound both
read (`scenes.json`), so moving a cut moves its sound. Synths and helpers:
`scripts/move_audio.py` (its docstring shows how a film's audio script uses it). Mix with
video-sound's `scripts/mix.py` (voice on `fg`, bed on `bg`, effects flat); video-studio's
audio laws apply (nothing with a tail over a voice, sound only where something happens).

## Per move

| Move | Sound | In move_audio | Level used on the test reel (effects stem, before master) |
|---|---|---|---|
| pan, tilt, dolly, orbit, crane, tracking | soft moving air under the move | `air(dur)` | -24 to -27 dB |
| dolly - props pass the lens | a short whoosh when they exit | `whoosh(0.55, 500, 2600)` | -14 dB |
| crash zoom | a fast rising whoosh into a soft hit on the landing | `whoosh(0.4, 400, 3200)` + `kenney("soft_hit")` | -18 / -12 dB |
| dolly zoom | tone 110 → 520 Hz + rising noise | `riser(dur)` | -14 dB |
| rack focus | one soft click on the pull | `kenney("tick")` | -6 dB |
| FPV | saw buzz ~185 Hz with vibrato, whooshes as things pass | `buzz`, `whoosh(0.35, 700, 2800)` | -20 / -22 dB |
| dutch angle | a detuned low swell | `drone(dur)` | -20 dB |
| slow motion | the voice slowed like tape, heartbeats | `story_curve` + `voice_at`, `heartbeat()` | voice 0, beats -10/-12 dB |
| speed ramp | voice x2 → tape stop → x2, a tape-stop tone, a heartbeat in the slow part | `tape_stop(0.55)`, `heartbeat()` | -20 / -10 dB |
| time-lapse | ticks that speed up, an arpeggio up at the end | `ticks(...)` + `kenney("tick")`, `arpeggio()` | -8 / -16 dB |
| freeze frame | voice and bed cut, a 1760 Hz ring, a whoosh out | `gate(r > 0.03)`, `bed_gap`, `ring()`, `whoosh(0.3, 600, 3000)` | -18 dB |
| jump cut | a click on every jump | `kenney("switch")` | -10 dB |
| match cut | a bell on the cut frame | `kenney("bell")` | -5 dB (at -10 it sank under the bed in 0.1 s) |
| whip pan | a click, then noise with the band rising | `kenney("click")`, `whoosh(0.62, 300, 3600)` | -8 / -12 dB |
| wipe | a soft moving swish | `whoosh(1.1, 900, 1600) * 0.6` | -24 dB |
| smash cut | quiet half: hum only, bed cut; the hit and the voice on the cut frame | `hum`, `bed_gap`, `kenney("punch")` | hum -34 dB, hit -9 dB |
| J-cut | B's sound 0.3-0.5 s before B's picture | `speech_onset` to place it | voice 0 |
| L-cut | A's sound 0.3-1.5 s past the cut, fading over its last 0.5 s | `env_ad` + a fade | voice 0 |

## Story time

`story_curve(scene["story"], dur)` uses the same `segs` and `s0` as `CK.makeStoryTime`, so
the voice and the picture slow and stop together. `voice_at(recording, s)` is tape-style
varispeed (pitch follows speed) - right for slow motion and ramps. Multiply by
`gate(r > 0.03)` (silent in a freeze) and `env_ad(n, 0.01, 0.08)` (no clicks at the clip's
edges; a clip that started mid-word at full level clicked on the test reel).

Sounds tied to the world (steps, ticks of a clock in the scene) are placed at
`T.real(s)` - they thin out in slow motion and vanish in a freeze.

## J and L cuts

- Measure where the recording actually starts speaking: `speech_onset(voice)` (the test
  reel's call recording starts at 0.22 s). Place the clip so the FIRST AUDIBLE WORD is `lead` before the
  picture cut. Reading from 0 s gave a 0.25 s lead instead of 0.45.
- Start every clip on a phrase, with a 10 ms attack; end it with a fade.
- Over 1 s of lead reads as a sync error; B's sound must be recognisable.

## Levels and mastering (what the test reel taught)

- A real recording's voice is far denser than a bed: at 0 dB it sat 5-7 dB over the
  bed-only scenes and the master hit the limiter. Voice bus -4 dB, bed -7 dB, the bed cut
  from 10 s into the track (its intro was 5 dB quieter) gave -14.6 LUFS evenly.
- Write each voice segment as its own event; one long voice stem makes mix.py duck the
  bed under the whole film.
- AAC adds inter-sample overshoot: a -2.1 dBTP WAV came out -0.5 dBTP in the MP4.
  `true_peak_pass(src, dst, limit=0.66)` left -3.4 dBTP after AAC at -14.9 LUFS.
- `sfxcheck.py` judges events; a single effects stem gives it nothing - keep effects as
  separate events when the check matters.
