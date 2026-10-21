# Third-party notices

Claude Marketing Skills is MIT-licensed (see [LICENSE](LICENSE)). Some files contain code or text from
other open-source projects. Each keeps its own licence, reproduced below. Files that hold such code
also say so in their header.

## Code and text in this repository

| Source | Licence | Where |
|---|---|---|
| [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | MIT | `skills/seo/references/` (six playbooks; commit and sync date in `UPSTREAM.md`) |
| [latent-spaces/brag](https://github.com/latent-spaces/brag) | MIT | the launch-film format and claim-grounding check (`skills/video-studio/references/`), poster / frame-0 technique (`skills/ads-video-library/`), `analyze_music_cues.py` (`skills/video-sound/library-tools/`) |
| [Bodila51/opus-sound-layer](https://github.com/Bodila51/opus-sound-layer) | MIT | `skills/video-sound/scripts/sfxauto.py`, `skills/video-check/scripts/soundqa.py`; ideas in `mix.py` and `sfxlib.py`; the CC0 sound kit in the library |
| [latent-spaces/nanoclip-cutting-room](https://github.com/latent-spaces/nanoclip-cutting-room) | MIT | `skills/video-build/scripts/captions.mjs`, `skills/video-check/scripts/seamscan.py`; ideas in `footage_proxy.py` and the real-footage traps |
| [lemomo-ai/lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) | MIT | the strict reading-time norm in `skills/video-check/scripts/readcheck.mjs` and parts of the launch recipe (ideas restated, no code copied) |
| "24 camera and editing moves" guide | shared publicly by its author for anyone to use and redistribute; no credit requested | the move catalogue and the math in `skills/video-moves/` (rewritten for DOM rigs and tested on our own films) |

Ideas only, no code: [video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft) (PolyForm
Noncommercial; the ideas behind `sfxcheck.py`, the phone-width contact sheet and the freeze-detect
threshold).

Small textbook algorithms in `skills/video-3d/assets/` (mulberry32 PRNG, a PCG-style integer hash
after Jarzynski & Olano 2020, Bayer matrices, Fibonacci sphere, Douglas-Peucker) are written from
their public descriptions.

## Installed separately, not included

| Project | Licence | Used by |
|---|---|---|
| [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) (CLI and skills) | Apache-2.0 | the video skills |
| [three.js](https://github.com/mrdoob/three.js) | MIT | `skills/video-3d` (loaded by the films it builds) |
| [GSAP](https://gsap.com) | GSAP standard licence (free, including commercial use) | HyperFrames compositions |
| [bradautomates/claude-video](https://github.com/bradautomates/claude-video) (/watch) | MIT | optional listen pass in `video-check` |

## Sound library (downloaded by `library.py install`, not in git)

Every file's source and licence is listed in the library's own `LICENSES.md` and `CREDITS.md`.
In short: Kenney sound packs (CC0), Freesound recordings (CC0; the opus-sound-layer kit, every
page re-checked), single keypresses by unicae_games on OpenGameArt (CC0), music by Sascha Ende,
ende.app (CC BY 4.0: credit "Music by Sascha Ende (ende.app), licensed under CC BY 4.0" when you
publish a film with it), and three synth beds and eleven ElevenLabs-generated effects made by this
project, released here as CC0. Two bought music tracks are not included: the catalogue keeps their
titles and beat cues, and `library.py doctor` says where to put your own copy.

## Licence texts

### coreyhaines31/marketingskills

```
MIT License

Copyright (c) 2025 Corey Haines

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### latent-spaces/brag

```
MIT License

Copyright (c) 2026 Shunit Haviv Hakimi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Bodila51/opus-sound-layer

```
MIT License

Copyright (c) 2026 Bodila51

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### latent-spaces/nanoclip-cutting-room

```
MIT License

Copyright (c) 2026 NanoClip (nanoclip.ai)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### lemomo-ai/lemo-opuscar

```
MIT License

Copyright (c) 2026 LemoLab

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
