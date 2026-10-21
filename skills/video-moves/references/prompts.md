# Moves in prompts for video models

For the generated lane (the **video-generated** skill, `../video-generated/references/atlas.md`;
Atlas Cloud: Seedance, OmniHuman, MiniMax). Video models follow English camera terms far better
than "make it cinematic". Not yet tested line by line on these models - when a line works or
fails on one, note it here with the model and the date.

Formula: the term first, then the subject, the direction, and the speed or duration -
"slow dolly in toward the subject over 3 seconds". One move per shot; two moves in one
prompt get mixed. Cuts (17-24) inside one generated clip are unreliable: generate two
shots and cut them in HyperFrames, using the term only to describe the intent.

The doctrine in video-generated's `references/atlas.md` still rules: the reference image beats
the prompt, one scene = one generation.

| # | Move | Prompt line |
|---|---|---|
| 01 | Pan | slow pan from left to right across the room |
| 02 | Tilt | tilt up from the person to the screen above them |
| 03 | Dolly in | slow dolly in toward the subject over 3 seconds |
| 04 | Zoom | quick crash zoom in on the character's face |
| 05 | Tracking | tracking shot moving alongside the walking character |
| 06 | Orbit | 180-degree orbit around the character, camera at chest height |
| 07 | Crane up | crane up and away, revealing the empty office |
| 08 | Dolly zoom | dolly zoom, subject stays the same size while the background stretches |
| 09 | Rack focus | rack focus from the phone in the foreground to the person in the background |
| 10 | Handheld | handheld camera with subtle natural shake |
| 11 | FPV | fast FPV drone shot flying low between the desks, banking into turns |
| 12 | Dutch angle | dutch angle, horizon tilted 20 degrees |
| 13 | Slow motion | slow motion, paper floating in the air |
| 14 | Speed ramp | speed ramp, real-time motion slowing into slow motion at the peak |
| 15 | Time-lapse | time-lapse from noon to sunset, clouds racing, people flickering |
| 16 | Freeze frame | freeze frame at the top of the gesture |
| 17 | Jump cut | jump cuts in the same framing, the character in different poses as time passes |
| 18 | Match cut | match cut from the round clock face to the round coffee cup in the same position |
| 19 | Whip pan | whip pan to the second person with motion blur |
| 20 | Dissolve | cross dissolve to the evening scene |
| 21 | Wipe | wipe transition from left to right |
| 22 | Smash cut | smash cut from a quiet office to a loud close-up |
| 23 | J-cut | J-cut, the next speaker's voice is heard before we see them |
| 24 | L-cut | L-cut, the voice keeps going over the next shot |

The film's own content rules apply to the scenes themselves: video-studio
`references/laws.md`, including the "Brand laws (yours)" section (for example, what your
customers' world really looks like - an online call, not a conference hall).
