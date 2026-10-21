# Compositing a three canvas with DOM, GSAP, footage and other films

Proven in a test film (the camera-text reel, its three compositing sections). Files here:
`host-start.js` (`hostStart()`). The names below are the ones that film used: the sub-composition
`compositions/layer3d.html` with its scene in `assets/layer3d.js`, and the GSAP layer in `assets/timeline.js`.

## Canvas under DOM layers animated by GSAP

- GSAP owns the DOM through its timeline (`tl.set(el, { autoAlpha })` at the cuts toggles layers);
  `hf-seek` renders the canvas; they share only t. Measured: a GSAP ring and a three square on one rail
  offset 0.00 px in all 120 frames (a one-frame desync would show as 13 px).
- Lint reads INLINE scripts only: with the timeline in an external file add an inline
  `window.__timelines["main"] = window.__mainTimeline;` after it (else `missing_timeline_registry`).
- A `.clip` wrapper with nested UI raises `nested_structure_needs_subcomposition`: make the UI layer a
  plain `div` and let GSAP own its visibility.
- Marks that must line up with DOM coordinates: an orthographic pixel-space overlay scene
  (`OrthographicCamera(0, 1920, 1080, 0)`), rendered after the main scene.

## Transparent canvas over footage

The footage is a HyperFrames DOM `<video>` clip below (HyperFrames seeks it); the canvas above has
`alpha: true`, clear alpha 0. Pick footage windows inside one shot (find shot changes from per-frame
`signalstats` YAVG jumps).

## A 3D layer as a sub-composition

1. The file must START with `<template>` (otherwise `-c` treats it as a plain page: zero duration).
2. Declare the layer's build hold in `index.html`'s `<head>` (classic script) and again inside the
   template guarded by `if (!window.__hf.buildReady.layer3d)`.
3. A standalone `-c` render keeps index.html's `<head>` (importmap, holds) and only the `<script src>`
   children of `<body>`: put the main scene and the GSAP timeline in EXTERNAL scripts, and let the main
   scene resolve its own hold when its canvas is absent.
4. `data-no-timeline` on the HOST element (the one with `data-composition-src`) - otherwise every render
   waits 45 s (`sub_timeline_readiness_timeout`).
5. Time: `hostStart(canvas)` (root time - every host's `data-start`).
6. `CSS2DRenderer` labels inside the layer: translate only, never scale.

## Alpha export (a 3D layer to composite elsewhere)

```bash
npx hyperframes render -c compositions/layer3d.html --format webm --browser-gpu -o renders/layer3d.webm  # VP9 alpha, 4.5 MB
npx hyperframes render -c compositions/layer3d.html --format mov  --browser-gpu -o layer3d.mov          # ProRes 4444, 186 MB
ffmpeg -c:v libvpx-vp9 -i renders/layer3d.webm ...   # decode VP9 alpha with libvpx: the native vp9 decoder drops alpha
```

Keep the WebM (the test film plays it; the 186 MB ProRes is an intermediate - delete it) and render ProRes
only when an editor needs it.

- No background on the composition root (the renderer clears only `html, body`); put any ground in a
  child `div` - a standalone render clones only the root and the host, so the child is gone there.
- Measured: ProRes 4444 `yuva444p12le`, 186 MB for 3.6 s (~430 Mbit/s); VP9 `yuva420p` 4.5 MB, alpha within
  mean 0.08 / max 22 levels of the ProRes. Alpha is straight (unpremultiplied): along a soft halo the colour
  stays at the accent while alpha falls - no dark fringe.
- `AdditiveBlending` (r181) is `blendFuncSeparate(SRC_ALPHA, ONE, ONE, ONE)`: it writes alpha, so an additive
  glow survives the export like a normal-blend one.
- The alpha layer plays back inside HyperFrames as a `<video>` clip WITH alpha (ProRes: the preview proxies it -
  browsers cannot decode ProRes; the render does not).
