# Project scaffold

Copy this skeleton for a new film; once you have one finished film (an end card is a good
first one), copy that instead and keep it as your reference project.

## Files

```
project/
  hyperframes.json
  package.json
  build.py                  emits index.html (+ other aspects) from measured timings
  assets/
    style.css               imports brand-tokens.css by bare filename
    brand-tokens.css        copied in; @import inside a stylesheet is relative to it
    logo-white.png          trimmed to its alpha box
  audio/
    lines/                  one wav per spoken line
    lines.json              written by gen_voice.py
    track.wav               written by mix.py
  timing.json               written by the timing step
  scenes.json               written by build.py: every scene start and how it comes in (for seamscan)
  renders/
```

`hyperframes.json`:

```json
{
  "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
  "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
  "paths": { "blocks": "compositions", "components": "compositions/components", "assets": "assets" },
  "media": { "autoProxy": true }
}
```

`package.json` pins the CLI so renders stay reproducible:

```json
{ "name": "project", "private": true, "type": "module",
  "scripts": {
    "check":  "npx --yes hyperframes@0.8.157 check",
    "render": "npx --yes hyperframes@0.8.157 render"
  } }
```

## Trimming an identity PNG

Logo exports are often square canvases (e.g. 512×512) with wide transparent margins. Laying
one out untrimmed puts the visual centre in the wrong place. Trim to the alpha box:

```python
import subprocess, sys
src, dst = sys.argv[1], sys.argv[2]
w, h = map(int, subprocess.run(["ffprobe","-v","error","-show_entries","stream=width,height",
    "-of","csv=p=0:nk=1",src],capture_output=True,text=True).stdout.strip().split(","))
d = subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",src,"-f","rawvideo",
    "-pix_fmt","rgba","-"],capture_output=True).stdout
x0,y0,x1,y1 = w,h,-1,-1
for y in range(h):
    row = d[y*w*4:(y+1)*w*4]
    for x in range(w):
        if row[x*4+3] > 8:
            x0,x1,y0,y1 = min(x0,x), max(x1,x), min(y0,y), max(y1,y)
subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",src,
    "-vf",f"crop={x1-x0+1}:{y1-y0+1}:{x0}:{y0}","-y",dst],check=True)
```

## build.py pattern

One source, one or more aspects. Everything timed comes from `timing.json`, so the
picture can never drift from the audio.

build.py also writes `scenes.json` from the same numbers - `{"scenes": [{"start", "dur", "in"?,
"seams"?}]}`, where `"in"` is how the scene arrives (`cut`, `dip:3`, `dissolve:0.4`, `whip:0.3`,
`fade:0.5`) and `"seams"` lists transitions inside a scene (`{"at": u, "kind", "dur"}`). video-check's
`seamscan.py --scenes scenes.json` then checks every cut against what was intended, with no flags.

```python
import json, pathlib
HERE = pathlib.Path(__file__).parent
T = json.loads((HERE / "timing.json").read_text())
END = T["total"]

BODY = '''
    <div id="card" class="clip card" data-start="0" data-duration="{dur}" data-track-index="0">
      ...
    </div>
'''

def page(res, w, h):
    return f'''<!doctype html>
<html lang="en" data-resolution="{res}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={w}, height={h}" />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <link rel="stylesheet" href="assets/style.css" />
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{END}"
         data-width="{w}" data-height="{h}">
{BODY.format(dur=END)}
    <audio id="au" data-start="0" data-duration="{END}" data-track-index="9"
           src="audio/track.wav"></audio>
    </div>
    <script>
      var tl = gsap.timeline({{ paused: true }});
      // ... tweens, positioned by absolute time from timing.json
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
'''

(HERE / "index.html").write_text(page("landscape", 1920, 1080))
```

## Stylesheet head

```css
@import url("brand-tokens.css");

* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 1920px; height: 1080px; overflow: hidden; }
body { font-family: "Inter", "Helvetica Neue", Arial, sans-serif; -webkit-font-smoothing: antialiased; }
#root { position: relative; width: 100%; height: 100%; overflow: hidden; }
.clip { position: absolute; inset: 0; }        /* required - see gotchas */

/* the whole stack scaled as one, so a second aspect needs one number, not fifty */
.fit { display: flex; flex-direction: column; align-items: center; gap: 4.4vmin;
       transform: scale(1.42); transform-origin: center center; }

html[data-resolution="portrait"], html[data-resolution="portrait"] body { width: 1080px; height: 1920px; }
html[data-resolution="portrait"] .fit { transform: scale(1.06); }
```

## Commands

```bash
python3 build.py
npx --yes hyperframes@0.8.157 check              # fix everything before rendering
npx --yes hyperframes@0.8.157 render -o renders/out-16x9.mp4 -q high
npx --yes hyperframes@0.8.157 render -c compositions/portrait.html -o renders/out-9x16.mp4 -q high
```

## Inspecting a render without watching it

```bash
# one frame per second, tiled - drift and dead frames show up immediately
# (a quick look only: fps=N tiles sit ~0.23 s off their nominal times; for sheets labelled with times
#  use video-check scripts/stills.py, which selects frames by number)
ffmpeg -i renders/out.mp4 -vf "fps=1,scale=300:-1,tile=6x2:padding=5" -frames:v 1 sheet.jpg
# mix balance at two moments; a mix that reads right on paper can be inverted
ffmpeg -ss 1.0 -t 0.5 -i renders/out.mp4 -af volumedetect -f null - 2>&1 | grep mean_volume
```
