#!/usr/bin/env python3
"""ElevenLabs speech, one file per line, trimmed and levelled.

    gen_voice.py lines.json out_dir [--gate] [--must Acme,Zoom] [--words] [--speed 1.12]
    gen_voice.py lines.json out_dir --model eleven_v3 --stability 0.0   # more emotion, [tags] honoured
    gen_voice.py lines.json out_dir --align --gate     # word timings from ElevenLabs itself, any language

lines.json: [{"tag":"en1","voice":"<voice_id>","text":"..."}, ...]

Why per line rather than one long take: a bad line is re-cut for a fraction of a
cent, the gaps belong to the edit rather than the render, and the measured
durations become the picture's timing grid.

Why every line is levelled: two voices from different sources arrive at different
loudness, so a dB offset between buses in the mix would not mean what it says. The level
is ONE static gain per line (measured, then applied). Single-pass loudnorm is a dynamic
gain rider and makes a line swell and dip inside itself.

Why --must: the gate compares whole lines and passes at 0.90 similarity, so a take that
says "Acne Studio" for "Acme Studio" passes. Names listed in --must have to be heard in every
line whose script contains them, or the line is flagged for a re-take. Spelling variants count
as heard (no recogniser writes "Acme2" - it hears "Acme II", "Acme 2", "Acme two"); a different
sound ("Acne") does not. A flagged name that OPENS the take: regenerate once before anyone
listens - Whisper's verdict on a take's first word flips with the silence in front of it.

Why the gate is Whisper large-v3-turbo and --words is parakeet (a speech-recognition bench on
our takes, 2026-10-14): turbo had the lowest error (EN 1.0%, ES 0.0%) and caught both known-bad
takes; parakeet put 88% of word starts within 100 ms of ElevenLabs' own alignment (turbo 69%)
and splits words at pauses (turbo stretches a word 320 ms into the pause). --words writes
<tag>.words.json: the SCRIPT's words (its spelling) on parakeet's times - the timing grid for
captions and word reveals.

Why --align (a captions test, 2026-10-14): parakeet knows 25 European languages and writes Arabic
as Latin gibberish (4 of 53 words matched). ElevenLabs' own character alignment is exact for any
language at no extra cost: on 7 Arabic takes it put the word after each of 6 comma pauses 43 ms
before the pause ended (worst 54 ms), where whisper turbo was 250 ms early (worst 360) and matched
45 of 53 words. --align takes come as pcm so the alignment's clock is the file's clock; the words
are shifted by exactly what the head trim cut. words.json says which source timed it ("times").

Recognisers (found on PATH, then in ~/.local/bin):
  gate     mlx_whisper (pip install mlx-whisper; Apple Silicon), else whisper (pip install
           openai-whisper; any machine, slower on CPU) - both with large-v3-turbo
  --words  parakeet-mlx (pip install parakeet-mlx; Apple Silicon only). Elsewhere use --align.

Key: env ELEVENLABS_API_KEY, else ~/.config/marketing-agent-kit/.env (env MARKETING_KIT_ENV
points elsewhere). Setup: connections/elevenlabs-api.md.
"""
import argparse, base64, difflib, json, os, pathlib, re, shutil, subprocess, sys, unicodedata, urllib.error, urllib.request

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

def tool(name):
    """A recogniser's CLI: on PATH, else in ~/.local/bin (where pipx and uv tool put them)."""
    found = shutil.which(name)
    if found:
        return found
    p = pathlib.Path.home() / ".local/bin" / name
    return str(p) if p.exists() else None


def transcribe(wav, out):
    """<out>/<stem>.txt from Whisper large-v3-turbo: mlx-whisper, else openai-whisper."""
    mlx = tool("mlx_whisper")
    if mlx:   # one file per call: mlx-whisper 0.4.3 names every result of a multi-file call after the first file
        cmd = [mlx, str(wav), "--model", "mlx-community/whisper-large-v3-turbo", "--output-dir", str(out),
               "--output-format", "txt", "--verbose", "False"]
    elif tool("whisper"):
        cmd = [tool("whisper"), str(wav), "--model", "turbo", "--output_dir", str(out),
               "--output_format", "txt", "--verbose", "False"]
    else:
        sys.exit("--gate needs a Whisper CLI: pip install mlx-whisper (Apple Silicon) or openai-whisper")
    subprocess.run(cmd, capture_output=True, check=True)


def dur(p):
    return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1",str(p)],capture_output=True,text=True).stdout.strip())

def strip_tags(t):
    """v3 audio tags steer delivery; they must not reach the gate as words."""
    out, d = [], 0
    for ch in t:
        if ch == "[": d += 1
        elif ch == "]": d = max(0, d - 1)
        elif d == 0: out.append(ch)
    return "".join(out).strip()

NUM = {"zero":"0","one":"1","two":"2","three":"3","four":"4","five":"5","six":"6","seven":"7",
       "eight":"8","nine":"9","ten":"10","twenty":"20","thirty":"30","forty":"40","fifty":"50",
       "sixty":"60","seventy":"70","eighty":"80","ninety":"90","hundred":"00","thousand":"000"}

# Arabic/Hebrew vowel marks and tatweel, and the hamza/ta-marbuta/alef-maqsura spellings that
# Whisper writes either way: dropped and folded, as Arabic WER scoring does.
RTL_MARKS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ֑-ׇ]")
ARABIC_FOLD = str.maketrans("أإآٱىةؤئ", "اااايهوي")

def canon(t):
    """Whisper reliably rewrites correct audio three ways: numbers as digits,
    currency words as symbols, and no space at a sentence break. Normalise those
    and nothing else - a gate with false positives gets switched off.
    Letters of every script are kept: the old Latin-only filter turned an Arabic
    line into an empty string, so its gate compared "" with "" and always passed."""
    t = t.lower().replace("’","'").replace("'","")
    t = re.sub(r"\$\s*([\d,.]+)", r"\1 dollars", t)
    t = RTL_MARKS.sub("", t).translate(ARABIC_FOLD)
    t = re.sub(r"[^\w ]|_", " ", t)
    return "".join(NUM.get(w, w) for w in t.split())

def name_key(t):
    """One form per name: case, spaces, hyphens, punctuation dropped, 'ii'/'two' -> 2."""
    return "".join("2" if w in ("ii", "two") else w for w in re.findall(r"[^\W_]+", t.lower()))

def parakeet_covers(text):
    """parakeet-tdt-0.6b-v3 knows 25 European languages: Latin, Greek and Cyrillic script only."""
    return not re.search(r"[^\W\d_]", re.sub(r"[A-Za-zÀ-ɏͰ-ϿЀ-ӿ]", "", RTL_MARKS.sub("", text)))

def latin(w): return bool(re.search(r"[A-Za-zÀ-ɏ]", w))

def gate_ratio(script, heard):
    """The gate's similarity. Whisper writes a Latin name inside an Arabic or Hebrew line in that
    line's own letters ("Google Maps" -> "جوجل مابس", "Wi-Fi" -> "واي فاي"): a run of Latin script
    words heard as a run of non-Latin words counts as heard. Returns (ratio, those script words) -
    the caller reports names among them as 'check by ear', since no recogniser can confirm them."""
    sw, hw = script.split(), heard.split()
    sm = difflib.SequenceMatcher(None, [canon(w) for w in sw], [canon(w) for w in hw], autojunk=False)
    fixed, crossed = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if (op == "replace" and all(latin(w) for w in sw[i1:i2])
                and all(re.search(r"[^\W\d_]", w) and not latin(w) for w in hw[j1:j2])):
            fixed += sw[i1:i2]; crossed += sw[i1:i2]
        elif op != "delete": fixed += hw[j1:j2]
    return difflib.SequenceMatcher(None, canon(script), canon(" ".join(fixed))).ratio(), crossed

def heard_words(d):
    """parakeet json -> words: a token starting with a space starts a word; punctuation has no time."""
    out = []
    for s in d.get("sentences", []):
        for t in s["tokens"]:
            if re.match(r"^[\s\W]+$", t["text"]): continue
            if t["text"].startswith(" ") or not out:
                out.append({"w": t["text"].strip(), "s": t["start"], "e": t["end"]})
            else:
                out[-1]["w"] += t["text"]; out[-1]["e"] = t["end"]
    return out

def script_on_times(script, heard, dur):
    """The script's words on the recogniser's times. Matched words take their times; a run that
    was misheard takes the span of what was heard instead; a run not heard at all is spread over
    the gap between its neighbours."""
    sw = script.split()
    sm = difflib.SequenceMatcher(None, [canon(w) for w in sw], [canon(h["w"]) for h in heard], autojunk=False)
    at, exact = [None] * len(sw), 0
    def spread(i1, i2, s, e):
        k = (e - s) / max(i2 - i1, 1)
        for n in range(i1, i2): at[n] = (s + (n - i1) * k, s + (n - i1 + 1) * k)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            exact += i2 - i1
            for n in range(i2 - i1): at[i1 + n] = (heard[j1 + n]["s"], heard[j1 + n]["e"])
        elif op == "replace" and i2 - i1 == j2 - j1:
            for n in range(i2 - i1): at[i1 + n] = (heard[j1 + n]["s"], heard[j1 + n]["e"])
        elif op == "replace":
            spread(i1, i2, heard[j1]["s"], heard[j2 - 1]["e"])
    i = 0
    while i < len(sw):
        if at[i] is None:
            j = i
            while j < len(sw) and at[j] is None: j += 1
            s = at[i - 1][1] if i else (heard[0]["s"] if heard else 0.0)
            e = at[j][0] if j < len(sw) else max(s, heard[-1]["e"] if heard else dur)
            spread(i, j, s, max(s, e)); i = j
        else: i += 1
    return [{"w": w, "s": round(s, 3), "e": round(e, 3)} for w, (s, e) in zip(sw, at)], exact

TRIM_HEAD = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02"

def head_trim(src):
    """Seconds the trim chain cuts off the head of src: its first filter, run alone."""
    tmp = src.with_suffix(".head.wav")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",str(src),"-af",TRIM_HEAD,str(tmp),"-y"], check=True)
    h = dur(src) - dur(tmp); tmp.unlink()
    return h

def eleven_words(al, head, d):
    """ElevenLabs character alignment -> whitespace-separated words on the trimmed take's clock.
    The first and last word reach into the API's padding; the trim removed it, so clamp."""
    out, cur = [], None
    for c, s, e in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if c.isspace(): cur = None; continue
        s, e = min(max(s - head, 0.0), d), min(max(e - head, 0.0), d)
        if cur is None: cur = {"w": c, "s": s, "e": e}; out.append(cur)
        else:
            cur["w"] += c
            if unicodedata.category(c)[0] in "LNM": cur["e"] = e   # a trailing comma's time is the pause
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lines"); ap.add_argument("out")
    ap.add_argument("--model", default="eleven_multilingual_v2")
    ap.add_argument("--speed", type=float, default=None)
    ap.add_argument("--stability", type=float, default=0.5,
                    help="eleven_v3 takes only 0.0 (creative), 0.5 (natural) or 1.0 (robust)")
    ap.add_argument("--target", type=float, default=-18.0, help="per-line loudness, LUFS")
    ap.add_argument("--gate", action="store_true", help="transcribe and diff against the script")
    ap.add_argument("--must", default="", help="comma-separated names that must be heard (implies --gate)")
    ap.add_argument("--words", action="store_true", help="word timings: <tag>.words.json, script words on parakeet times")
    ap.add_argument("--align", action="store_true",
                    help="new takes come from /with-timestamps (pcm, kept as <tag>.src.wav + <tag>.align.json); "
                         "words.json then takes ElevenLabs' own times - any language. Implies --words")
    a = ap.parse_args()
    must = [w.strip() for w in a.must.split(",") if w.strip()]
    if must: a.gate = True
    if a.align: a.words = True

    K = key()
    lines = json.loads(pathlib.Path(a.lines).read_text())
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    vs = {"stability": a.stability, "similarity_boost": 0.8}
    if a.speed: vs["speed"] = a.speed

    res, flagged = [], []
    for L in lines:
        mp3, raw, wav = out / f"{L['tag']}.mp3", out / f"{L['tag']}.src.wav", out / f"{L['tag']}.wav"
        # the source take: an old mp3 is kept as it is; --align takes come as pcm with their alignment,
        # so the alignment's clock is the file's clock (no mp3 priming delay in between)
        src = mp3 if mp3.exists() or not (a.align or raw.exists()) else raw
        if not src.exists():
            body = json.dumps({"text": L["text"], "model_id": a.model,
                               "voice_settings": vs}).encode()
            path = "/with-timestamps?output_format=pcm_44100" if src == raw else "?output_format=mp3_44100_128"
            req = urllib.request.Request(
                f"https://api.elevenlabs.io/v1/text-to-speech/{L['voice']}{path}",
                data=body, headers={"xi-api-key": K, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=180) as r: got_bytes = r.read()
            except urllib.error.HTTPError as e:
                print(f"  {L['tag']} FAILED {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
                continue
            if src == raw:
                js = json.loads(got_bytes)
                subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-f","s16le","-ar","44100","-ac","1",
                    "-i","-",str(raw),"-y"], input=base64.b64decode(js["audio_base64"]), check=True)
                (out / f"{L['tag']}.align.json").write_text(json.dumps(js["alignment"], ensure_ascii=False))
            else: mp3.write_bytes(got_bytes)
        if not wav.exists():
            # trim the API's head and tail padding, then level - the padding would
            # otherwise show up as dead air between cuts
            trimmed = wav.with_suffix(".trim.wav")
            subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",str(src),"-af",
                f"{TRIM_HEAD},areverse,{TRIM_HEAD},areverse",
                "-ar","48000","-ac","1",str(trimmed),"-y"], check=True)
            meas = subprocess.run(["ffmpeg","-hide_banner","-i",str(trimmed),"-af","ebur128","-f","null","-"],
                capture_output=True, text=True).stderr
            got = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", meas)[-1])
            subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",str(trimmed),"-af",
                f"volume={a.target - got:.2f}dB,afade=t=in:d=0.008,areverse,afade=t=in:d=0.03,areverse",
                "-ar","48000","-ac","1",str(wav),"-y"], check=True)   # edges to zero: a take cut mid-waveform clicks
            trimmed.unlink()
        d = dur(wav)
        row = {**L, "text": strip_tags(L["text"]), "dur": round(d, 3)}
        if a.gate:
            txt = wav.with_suffix(".txt")
            if not txt.exists():
                transcribe(wav, out)
            heard = txt.read_text().strip() if txt.exists() else ""
            r, crossed = gate_ratio(row["text"], heard)
            row["heard"], row["match"] = heard, round(r, 3)
            if r < 0.90: flagged.append((L["tag"], row["text"], heard, round(r, 2)))
            if crossed:
                row["by_ear"] = " ".join(crossed)
                print(f"  {L['tag']}: heard in the line's own script, check by ear: {row['by_ear']}")
            for w in must:
                if name_key(w) in name_key(" ".join(crossed)): continue   # reported above, not a fail
                if name_key(w) in name_key(row["text"]) and name_key(w) not in name_key(heard):
                    flagged.append((L["tag"], row["text"], heard, f"'{w}' not heard"))
        res.append(row)
        print(f"  {L['tag']:<6} {d:>5.2f}s  {row['text'][:62]}")

    if a.words and res:
        # source per take: ElevenLabs' own alignment when the take has one, else parakeet - which only
        # knows Latin, Greek and Cyrillic script; an Arabic, Hebrew or CJK take without alignment gets none
        pk = out / ".parakeet"
        aligned = {r["tag"] for r in res if (out / f"{r['tag']}.align.json").exists()}
        todo, none = [], []
        for r in res:
            if (out / f"{r['tag']}.words.json").exists() or r["tag"] in aligned: continue
            (todo if parakeet_covers(r["text"]) else none).append(r["tag"])
        if todo:   # one call for every take: the model loads once
            if not tool("parakeet-mlx"):
                sys.exit("--words without --align needs parakeet-mlx (pip install parakeet-mlx; Apple Silicon only). "
                         "On other machines re-take the lines with --align: ElevenLabs times the words itself.")
            pk.mkdir(exist_ok=True)
            subprocess.run([tool("parakeet-mlx"), *[str(out / f"{t}.wav") for t in todo],
                "--output-format","json","--output-dir",str(pk)], capture_output=True, check=True)
        src_of = {}
        for r in res:
            wj = out / f"{r['tag']}.words.json"
            if not wj.exists() and r["tag"] not in none:
                if r["tag"] in aligned:
                    src = out / f"{r['tag']}.src.wav"
                    heard = eleven_words(json.loads((out / f"{r['tag']}.align.json").read_text()), head_trim(src), r["dur"])
                    times = "elevenlabs-alignment"
                else:
                    heard, times = heard_words(json.loads((pk / f"{r['tag']}.json").read_text())), "parakeet-tdt-0.6b-v3"
                words, exact = script_on_times(r["text"], heard, r["dur"])
                wj.write_text(json.dumps({"tag": r["tag"], "times": times, "words": words,
                    "exact": f"{exact}/{len(words)}"}, indent=1, ensure_ascii=False))
            if wj.exists():
                r["words"] = wj.name
                src_of[r["tag"]] = json.loads(wj.read_text()).get("times", "?")
        kinds = sorted(set(src_of.values()))
        print(f"word timings: {len(src_of)} x <tag>.words.json (script words on {' / '.join(kinds) or 'nothing'} times)")
        for t in none:
            print(f"  {t}: NO word timings - parakeet does not know this script. Re-take it with --align "
                  f"(move {t}.mp3/.wav aside first), or time it with whisper turbo --word-timestamps", file=sys.stderr)

    (out.parent / "lines.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(f"\n{len(res)}/{len(lines)} lines, {sum(r['dur'] for r in res):.2f}s of speech")
    if flagged:
        print(f"\n{len(flagged)} line(s) differ from the script:")
        for t, w, h, r in flagged:
            print(f"  {t}: ordered {w!r}\n      heard   {h!r}  match={r}")
        sys.exit(1)
    if a.gate: print("gate passed: every line says what was ordered")

main()
