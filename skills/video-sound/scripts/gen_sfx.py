#!/usr/bin/env python3
"""ElevenLabs sound effects, built once into a reusable library.

    gen_sfx.py sounds.json lib_dir

sounds.json: {"ui_click": {"prompt":"...", "secs":0.5, "influence":0.85}, ...}

Interface sounds must be dry: on a beat of a second or two any reverb tail smears
into the next shot and reads as a mistake, so every UI prompt says "dry, no reverb,
no music". A tail belongs only where a shot holds - an end card, a logo sting.

Each file is trimmed to its transient and levelled, so placement in the mix is by
intended time rather than by however much silence the API prepended.

Sound generation needs a paid ElevenLabs plan (the free tier blocks it).
Key: env ELEVENLABS_API_KEY, else ~/.config/marketing-agent-kit/.env (env MARKETING_KIT_ENV
points elsewhere). Setup: connections/elevenlabs-api.md.
"""
import json, os, pathlib, re, subprocess, sys, urllib.error, urllib.request

KEYS_FILE = pathlib.Path(os.path.expanduser(os.environ.get("MARKETING_KIT_ENV", "~/.config/marketing-agent-kit/.env")))


def env_value(raw: str) -> str:
    """Value of KEY=value: drop an inline comment (a # at the start or after a space), then quotes."""
    return re.split(r"(?:^|\s)#", raw.strip(), maxsplit=1)[0].strip().strip('"').strip("'")


def key():
    """ELEVENLABS_API_KEY from the environment, else from the kit's keys file."""
    v = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if v:
        return v
    if KEYS_FILE.exists():
        for line in KEYS_FILE.read_text().splitlines():
            k, sep, raw = line.strip().removeprefix("export ").partition("=")
            if sep and k.strip() == "ELEVENLABS_API_KEY" and env_value(raw):
                return env_value(raw)
    sys.exit(f"no ELEVENLABS_API_KEY: set it in the environment or add ELEVENLABS_API_KEY=... to {KEYS_FILE} "
             "(chmod 600). Setup: connections/elevenlabs-api.md")

STARTERS = {
 "ui_tap":     "A single soft muted tap on a text field in a modern web app. Very short, dry, clean, no reverb, no music, no room tone.",
 "ui_click":   "One crisp short click of a dropdown opening in modern software. Dry, tight, no reverb, no music.",
 "ui_select":  "A very short quiet tick, selecting one item from a list. Dry, subtle, no reverb, no music.",
 "ui_confirm": "A firm button press followed immediately by a short soft upward confirmation blip. Modern app interface, dry, no reverb, no music.",
 "notify":     "A gentle bright two-note notification chime, like a meeting app alert. Short, clean, minimal tail, no music.",
 "connect":    "A soft warm ascending tone marking a connection established. Short, subtle, clean, no music.",
 "typing":     "Light quick mechanical keyboard typing, several soft keystrokes in a row, close and dry, no reverb, no room, no music.",
 "brand_swell":"A short premium rising whoosh resolving into one soft warm synth impact. Clean, modern, confident, brief tail.",
 "brand_pop":  "A soft rounded pop as a button appears. Quiet, premium, dry.",
 "shimmer":    "A very light high shimmer sweep, like light passing across glass. Brief and subtle, no music.",
 "translate":  "A short bright glint as one word is instantly replaced by another: a quick soft upward sweep ending in a light glassy sparkle. Very brief, dry, no reverb, no music, no room tone.",
}

def main():
    if len(sys.argv) < 3:
        sys.exit(f"usage: gen_sfx.py sounds.json lib_dir\n"
                 f"       (a starter set of {len(STARTERS)} prompts is embedded; "
                 f"pass 'default' as sounds.json to use it)")
    spec, lib = sys.argv[1], pathlib.Path(sys.argv[2])
    sounds = ({k: {"prompt": v, "secs": 0.5 if k.startswith("ui") or k == "translate" else 1.0, "influence": 0.85}
               for k, v in STARTERS.items()} if spec == "default"
              else json.loads(pathlib.Path(spec).read_text()))
    K = key(); lib.mkdir(parents=True, exist_ok=True)
    for name, s in sounds.items():
        mp3, wav = lib / f"{name}.mp3", lib / f"{name}.wav"
        if not mp3.exists():
            body = json.dumps({"text": s["prompt"], "duration_seconds": s.get("secs", 1.0),
                               "prompt_influence": s.get("influence", 0.8)}).encode()
            req = urllib.request.Request("https://api.elevenlabs.io/v1/sound-generation",
                data=body, headers={"xi-api-key": K, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=180) as r: mp3.write_bytes(r.read())
            except urllib.error.HTTPError as e:
                print(f"  {name} FAILED {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
                continue
        if not wav.exists():
            subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",str(mp3),"-af",
                "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.01,"
                "loudnorm=I=-20:TP=-3:LRA=7","-ar","48000","-ac","1",str(wav),"-y"], check=True)
        d = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
            "-of","default=nw=1:nk=1",str(wav)],capture_output=True,text=True).stdout.strip()
        print(f"  {name:<12} {float(d):.2f}s")

main()
