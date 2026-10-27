# letsplay

Turn long Twitch VODs into finished YouTube let's play episodes and Shorts. The mechanical work (transcription,
splitting, cutscene detection, silence trimming, grading, rendering, loudness, subtitles, YouTube details) is scripted;
the editing itself is done by [Claude Code](https://claude.com/claude-code) following a project skill, because a program
can't judge what's funny, what needs its setup, or where a chapter really starts.

Each episode gets: a cold open, title card, intro with a music bed, jump-cut main part, verbatim pop-up captions, face
and game zooms, banners for on-screen events (GTA V Chaos Mod effects), a "to be continued" freeze, an end screen laid
out for YouTube's end-screen elements, a thumbnail, a description with chapters and credits, subtitles, an optional
translated title/description, and 2–4 vertical Shorts. Footage is never upscaled: everything renders at the VOD's
native resolution.

Built for a Finnish GTA V Chaos Mod channel; the language, names and game module are configuration.

## How it works

```
VOD ─ ingest ─ split ─┬─ episode 1: draft → edit (Claude) → check → script review → render → publish
                      ├─ episode 2: …
                      └─ prep all (graded sources, in the background)
```

| Command (`.venv/bin/python scripts/lp.py …`) | What it does |
|---|---|
| `ingest <vod> [--game chaosmod]` | copy the VOD, Whisper transcript with word timestamps, loudness map, language per 10 s, game OCR |
| `split <slug> [--target 25]` | episodes of ~25 edited minutes, cut at speech pauses |
| `prep <slug> all` | graded per-episode sources at native resolution |
| `draft <slug> <ep>` | first-pass edit: ranges without cutscenes or transcript hallucinations, effects, chapter candidates |
| `context <slug> <ep>` | the episode as text (speech with start–end, effects, cutscenes, loud moments) for the editor |
| `frames`, `faces` | contact sheets of moments and of the liveliest webcam frames (thumbnail face) |
| `check <edit>` | build the timeline, report every problem at once, render a grid of check stills |
| `script <edit>` | the finished edit as a timed script, for reviewing it the way a viewer meets it |
| `render <edit> [--patch [ranges]]` | render, master to −14 LUFS, thumbnail, Shorts; `--patch` re-renders only what changed |
| `publish <edit> [--at ISO \| --now]` | wait for the Studio upload, then set details, subtitles, translation, playlist, Shorts |
| `stats <session-id>` | token use and activity of a Claude Code session |

`scripts/youtube_mcp.py` exposes the YouTube operations as an MCP server (registered in `.mcp.json`).

Measured on a 3.5 h 720p60 stream (RTX 4080 SUPER, 28 threads): effect OCR ≈ 13 min, language detection ≈ 2 min,
prep ≈ 25 min per 50 min of stream, render ≈ 17–27 min per 20–23 min episode, Shorts ≈ 25 s each, a patch 1–2 min. Editing one episode in a
fresh Claude Code session took ≈ 11 min and ≈ 44k output tokens.

## Setup

Requirements: Linux (that's what it's tested on), Python 3.12, Node 20+, a recent ffmpeg (with the `cas` filter). An NVIDIA GPU makes
transcription and encoding much faster; without one, Whisper runs on the CPU and encoding uses x264.

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
npm install
cp config.example.json config.json        # your name, VOD folder, language, texts
sh scripts/fetch_music.sh                 # Kevin MacLeod tracks (CC BY 4.0)
.venv/bin/python games/chaosmod/build_names.py   # only for GTA V Chaos Mod streams
npm test
```

YouTube (optional): create a Google Cloud project, enable the YouTube Data API v3, set up an External OAuth consent
screen in production status, create a Desktop-app OAuth client and save its JSON as
`~/.config/letsplay-youtube/client_secret.json`, then run `.venv/bin/python scripts/youtube_mcp.py auth`. API uploads
from unaudited projects are locked to private, so the workflow leaves the upload to you in YouTube Studio and fills in
everything else; end screens and the game title are Studio-only.

## Making an episode

In Claude Code, from the repository root: `/letsplay make episode 1 of <VOD>`. The skill
(`.claude/skills/letsplay/SKILL.md`) has the whole procedure, the edit-file schema and the editorial rules. To run an
episode unattended and follow it from your phone:

```sh
claude --bg --remote-control "My Game part 2" --permission-mode auto "/letsplay Make episode 2 of <slug> …"
```

Use one fresh session per episode: every step re-reads the session's context, so a long session costs about twice as
much per episode.

Edit files (`edits/*.json`) are plain JSON; `examples/edit-example.json` is a small complete one (it is also the test
fixture). Styles (`hype`, `horror`, `chill`: colours, caption font, music) are in `src/styles.json`.

## Game modules

`games/chaosmod/` reads the GTA V Chaos Mod effect list from the screen (OCR), maps it to the mod's real effect names
and keeps one-line descriptions per language (`descriptions.fi.json`). Banners, the draft's effect list and Shorts use
it. Without a game module everything else works the same.

## License

MIT for this code (see `LICENSE`). Remotion has its own license (free for individuals and small companies); the Chaos
Mod effect names and the music are fetched, not shipped. Details in `THIRD_PARTY.md`.
