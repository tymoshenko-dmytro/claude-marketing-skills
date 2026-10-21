# The film brief - the contract executors read

Every film gets ONE `brief.md` in its folder, written by video-studio after the plan and before
any executor starts. video-build, video-sound, video-moves, video-3d, video-generated and
video-check read it as it is. A subagent gets this file verbatim plus its executor's skill - never
a paraphrase. Idea from brag's `composition-brief.md` (github.com/latent-spaces/brag, MIT) and
nanoclip-cutting-room's one contract per subagent (MIT).

**The boundary.** The brief owns what the film says and shows: purpose, copy, claims and their
source, tone, material, the moments, private data. Executors own how: timing to the frame,
layout, easing, exact effects and levels, code. An executor that cannot meet the brief says so
and video-studio changes the brief - nobody changes it silently, and nobody re-decides a
brief-level question inside an executor.

The plan (the format recipe's thinking: candidate structures, "not the last film again") stays
in `plan.md`; the brief is what survives from it as decisions.

## Template

```markdown
# Brief: <film name>

## Purpose
- For: <who sees it> · Where: <channel, placement> · Goal: <what they should do or know after>
- Laws: house laws + <"Brand laws (yours)" | none> (video-studio references/laws.md)
- Format: <recipe> · <W>x<H> · <duration target> s · 30 fps · poster = frame 0

## Source of truth
- Material: <paths/URLs to the product, UI, footage, data, logos>
- Claims on screen, each with its source:
  - "<claim>" - <file/page/product brief line>
- Copy that must appear verbatim: <lines>

## Look
- Palette from the film's source (not a brand by default): ground <hex>, text <hex>, accent <hex>
- Fonts: <display>, <body> (files or Google Fonts names)
- Tone: <preset + freeform direction>; Avoid: <specific things>

## Private data
- On screen: <keys, emails, names, hosts, money ... or "none"> → the user's decision: <keep / stand-in>

## Voice and music
- Voice: <voice id, model> · lines in `lines.json` (tags) · names that must be heard: <list>
- Music: <track or role + BPM range> · shape: <arc, stop/build moments>
- Effects role: <sparse accents / interface / cinematic>

## Scenes
| # | Scene | ~s | Must be seen / read | Voice line | Move / transition | Sound intent | Notes (3D, generated, footage) |
|---|---|---|---|---|---|---|---|
| 1 | Hook | 2-3 | ... | l1 | ... | ... | ... |

Signature moment: <scene #, what only this subject can do>

## Deliverables
- Folder: <path> · `<name>.mp4` (+ `poster.jpg`, captions, other aspects)
- Gates: video-check full set + independent review before the user sees it
```

Fill only what the film has; an empty section is deleted, not left as a placeholder. Durations
are targets - audio first sets the real ones, and video-build writes them back into the
timeline, not into the brief.
