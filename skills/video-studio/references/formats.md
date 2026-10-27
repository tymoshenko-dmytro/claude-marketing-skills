# Formats

A format is a recipe: when to use it, its shape, its build route and anything it needs
beyond the house laws. Add a format when a second video of the same kind is made; until
then the notes live in that film's own notes.

| Format | Use for | Build | Recipe |
|---|---|---|---|
| Motion card | end card, title/CTA/offer card, logo sting, lower third, UI panel with animated text; 3-15 s, exact text | video-build (HyperFrames, one paused GSAP timeline) | `format-motion-card.md` |
| Launch film | 15-25 s film of a product, project or site: hook → reveal → 2-3 highlights → punchline | video-build (HyperFrames, from the product's own UI) + video-moves | `format-launch.md` |
| World film | 45-90 s film of a team, system or process as a place where characters work: a map, interiors, a cast that carries the work; when cards would read as a slideshow | video-build (HyperFrames, one camera over a generated world) + video-moves + generated art | `format-world.md` |
| Generated film | people, rooms, objects that do not exist as footage; dialogue films | Atlas Cloud (Seedance 2.0, OmniHuman 1.5, Nano Banana Pro) + HyperFrames assembly | the **video-generated** skill |
| Reference copy | "make it like this ad" | whichever of the above the reference needs | `format-reference-copy.md` |

Upstream recipes worth knowing (HyperFrames skills, used as they are):
`product-launch-video` (URL/brief → promo), `motion-graphics` (kinetic type, stat hits,
maps, UI animation), `general-video` (longer narrated multi-scene). When one of them fits
better than a recipe above, use it - and still apply laws.md; sound through video-sound,
gates through video-check.

**Reuse before you build.** Keep a short list of your finished, approved pieces (the end card,
a product panel, a setup demo, a full demo) with the path of each canonical file, and start
from one of them when it fits. A finished element is read from its canonical file, never
re-cut from the raw source (laws.md).

Planned, not yet a format: shorts cut from long footage (webinars, calls, talks) -
`backlog-shorts-from-long-footage.md` holds the method and the tools to use when such a
recording arrives.
