---
name: letsplay
description: Turn a Twitch VOD into finished YouTube let's play episodes and Shorts (split, edit, render, thumbnail, description, YouTube details). Use when the user asks to make, cut, split, edit, render or publish let's play / YouTube episodes from stream recordings.
---

# Let's play pipeline

Project: this repository (Remotion 4 + Python venv); run commands from its root. Driver: `.venv/bin/python scripts/lp.py <cmd>`;
run `lp.py -h` for usage. Channel settings are in `config.json` (from `config.example.json`): the streamer's name, where the
VODs are (`vod_dir`, any 16:9 size), the commentary language (`language`), which is also the language of all on-screen
text, captions, chapters and descriptions, and an optional `translation` language for YouTube titles/descriptions.

The mechanical steps are scripted. Your job is the editorial part: writing one EDL (`edits/<slug>-ep<N>.json`) per episode.
Make the editorial decisions yourself and deliver finished episodes; the user watches the result.

## Hard rules

- **Never upscale raw material.** Sources stay at the VOD's native size and episodes render at that size
  (compositions are laid out in 1920x1080 units; `lp.py` renders at `--scale=<VOD width>/1920`). Zoom punch-ins are an editorial effect and fine.
- Do not blur anything in the stream overlay (vote list, stats, chat, follower goal, FPS, alert popups): it all stays visible.
- Captions are verbatim to the spoken words and uncensored (swearing stays, matching the audio). Never paraphrase.
- Run long steps (`ingest`, `prep`, `render`) with `run_in_background` and wait for the notification.

## Steps

Scripts do the mechanical work; **you are the editor**. Programs cannot judge edit quality, so every draft is curated
by you and every edit is reviewed by you before it renders. Never ship a draft as-is or skip the review to save time.

1. **ingest** `lp.py ingest "<VOD path>" [--game chaosmod]`: copies to `footage/<slug>.mp4`, Whisper transcript (GPU), 100 ms
   loudness map, spoken language per 10 s (finds cutscenes in another language, ~2 min on a GPU), and with `--game chaosmod` (GTA V Chaos
   Mod streams; run `games/chaosmod/build_names.py` once first) the active-effect OCR (~13 min for a 3.5 h VOD, all CPU cores); everything lands in `work/<slug>/`.
2. **split** `lp.py split <slug> [--target 25] [--parts N]`: episodes of ~25 *edited* minutes each (the 20–30 min sweet spot
   for gaming; ≥8 min allows mid-roll ads). It estimates how much each stretch keeps after trimming, so talky streams get
   longer raw parts than quiet ones, and cuts at a speech pause. `--parts N` fixes the count (speedruns: see below).
   It prints each episode's raw and estimated edited length; re-run with another `--target` if they look wrong.
   Then start `lp.py prep <slug> all` in the background: every episode's source is ready by the time its edit is.
3. Per episode N:
   1. `lp.py draft <slug> N` → `edits/<slug>-epN.json`, a first pass: main ranges from speech/action with English
      cutscenes and Whisper loops left out, every effect under its real mod name with its known description, chapter
      candidates, intro/cold-open guesses, series metadata copied from a sibling episode. Everything editorial is `TODO`.
   2. `lp.py context <slug> N` → read `work/<slug>/epN.context.txt` **in full**: transcript, `[EFFECT] name — description`,
      `[EN a–b]` (another language than the commentary: cutscene or mission dialogue: keep only a beat of it, if any), `[REPEATS a–b]` (hallucinated
      transcript: check with `frames` what really happens), `[LOUD]`.
   3. Curate the draft like a professional editor (rules below): drop weak or repetitive ranges, tighten boundaries to
      sentence ends, pick the real cold open and intro, write verbatim captions, place face/game zooms, write one-line descriptions
      for effects without one (they're saved to `games/chaosmod/descriptions.<language>.json` for later episodes), chapter labels, title,
      description and the translation.
   4. Shorts: pick 2–4 of the episode's best self-contained moments for `"shorts"` (see Shorts below).
   5. Thumbnail: `lp.py faces <slug> N` (liveliest webcam moments) and `lp.py frames <slug> <m:ss> ...` (game frames)
      → pick `thumb.face`, `thumb.bg` and 2–4 words of text.
   6. `lp.py check edits/<slug>-epN.json` → fix everything it reports (all problems are listed at once), then read the
      grid `work/<slug>/epN-check.jpg`.
   7. **Review** `lp.py script edits/<slug>-epN.json` → read `work/<slug>/epN.script.txt` top to bottom as the viewer
      will meet it: does every cut land on a finished sentence, does each joke get its setup, are there thank-yous or chat
      admin left, do captions/banners/zooms land on the right beat, is anything repeated or confusing? Fix and re-run
      until it reads like a finished episode.
   8. `lp.py render edits/<slug>-epN.json` → `out/<output>.mp4` (≈ 17–27 min), `out/<output>.jpg` (thumbnail),
      `out/<output>.description.txt`, `.<language>.srt`, `.<translation>.json`, and the Shorts in `out/shorts/` (~25 s each to render). Check the printed loudness is about −14 LUFS and look at
      the thumbnail. Later fixes: `--patch` (see below), never a full re-render.
4. Report: per episode the file, length, and anything the user must know in a clause. Never upload video files.
5. **YouTube**: the user uploads the mp4 in Studio. `lp.py publish edits/<slug>-epN.json` (run in the background) waits for
   the upload (matched by length), applies title, description with chapters and credits, tags, thumbnail, subtitles,
   translated title/description, Gaming, the channel's language, recording date, not for kids, no altered content, and the
   `playlist` from the EDL; the video id is kept in `work/<slug>/epN.youtube.json`. Add `--at <ISO>` (schedule) or
   `--now` **only after the user's explicit go for that video**. The MCP server `youtube` (`scripts/youtube_mcp.py`) has
   the same operations as tools. End screens and the game title are not in the API: tell the user to set them in Studio
   (the last 15 s are laid out for a row of video slot, subscribe circle, video slot).
   If it says "not signed in", ask the user to run `! .venv/bin/python scripts/youtube_mcp.py auth`.

Each episode's timeline is passed to Remotion as input props (`work/<slug>/epN.props.json`), so different episodes can
check, render and patch at the same time. `src/edit.json` / `src/thumb.json` are only the Studio preview default.

## One episode = one fresh session

Make each episode in its own new session, not at the end of a long one: the cost of every step is the whole context
re-read, and a long session made episode 2 cost ~350k tokens of context per step against ~160k in a fresh one.
To run an episode autonomously with Remote Control (the user follows and answers from claude.ai or the phone):

```sh
claude --bg --remote-control "<Series> part N" -n "<Series> part N" --permission-mode auto \
  "/letsplay Make episode N of the VOD <slug> (<output>) fully autonomously … Do not upload, publish or touch YouTube. \
   Finish with a short report: output file, length, loudness, anything the user should know."
```

`claude agents --json` lists it, `claude attach <id>` opens it, `lp.py stats <session-id>` measures it afterwards.
Measured: episode 3 in a fresh session took 47 min wall time (11 min editing, 18 min render), 44k output tokens,
7.7M cached input tokens over 49 steps.

Keep the context small: read the context file once; don't `cat` whole reference EDLs (the schema below is enough);
look at contact sheets only as often as needed (every image stays in the context for the rest of the session).

## Pick the kind of video first

Decide per VOD from its title and a look at `frames`/`context`:

| Content | `style` | `mode` | Notes |
|---|---|---|---|
| Comedy, chaos, randomizers, co-op, most games | `hype` | – | purple/yellow, funk intro |
| Horror (Phasmophobia, SCP, Forewarned, Yume Nikki) | `horror` | – | dark red/bone, eerie music, glitch title; captions in Anton |
| Calm or cosy (PowerWash, Subnautica, chatting streams) | `chill` | – | teal/warm, light music, no glitch effect |
| Speedrun / PB / runtime VODs | any (usually `hype`) | `speedrun` | `split --parts 1` (or one part per run); the run itself is never jump-cut |

- **Speedrun mode** keeps every range whole (no silence trimming). Cut only before and after the run, plus long pre-run
  chatting or resets. Put the run start/finish in chapters, the final time in the title/thumbnail, no face zooms during the run.
- **No webcam** (check with `frames`; older VODs may not have one): `"cam": null`, `"faceZooms": []`, `"thumb.face": null`.
  The thumbnail then uses the game frame alone with wider text.
- **Music-heavy games** (Beat Saber etc.): trimming automatically raises the loud-moment threshold to the episode's 90th
  loudness percentile. If the build still keeps too much or too little, set `"loudDb"` (e.g. `-14`) in the EDL.

## EDL schema

All times are VOD times as `m:ss[.s]` (minutes may exceed 59, e.g. `62:18`). See `examples/edit-example.json` for a small complete example.

```jsonc
{
 "vod": "<slug>", "episode": 1, "output": "Example Game - Part 1",
 "style": "hype",                      // hype | horror | chill (src/styles.json: colours, caption font, music)
 "playlist": "Example Game", "tags": ["Example Game", "..."],  // used by `lp.py publish`
 "mode": "speedrun",                   // optional; omit for normal let's plays
 "loudDb": -14,                        // optional loud-moment threshold override (dB, 100 ms RMS)
 "cam": [990, 480, 290, 240],          // webcam rect x,y,w,h in VOD pixels, or null; check with `frames`, layouts changed over the years
 "thumb": {"bg": "48:10.0", "face": "51:02.5", "bgZoom": 1.25, "bgOrigin": "62% 45%", "tag": "EXAMPLE GAME #1", "text": "IT ALL GOES WRONG"},
 "title": {"kicker": "EXAMPLE", "title": "GAME", "episode": "PART 1", "tagline": "...", "bg": "48:10"},
 "lowerThird": {"at": "24:40.0", "text": "YourName", "sub": "Example Game · Twitch stream 31.1.2024"},
 "coldOpen": [["21:05.0", "21:19.5", "full"]],   // ranges; "full" = keep as is, otherwise silences are jump-cut
 "intro":    [["24:30.0", "25:35.0"]],           // music bed under it; the title card sits between coldOpen and intro
 "main":     [["3:40.0", "4:05.5"], ...],         // chronological
 "effects":  [["4:29", "Heavy Recoil", "Guns kick like a mule"]],   // rough time, mod effect name (as in context), one-line description ("" = from the library)
 "captions": [["5:34", "minimap", "I CAN'T SEE MY MINIMAP AT ALL"]], // rough time, a word in the transcript segment, verbatim caps text
 "faceZooms": ["7:28"], "gameZooms": ["17:15"],
 "chapters": [["0:00", "Intro"], ["3:40", "The chaos begins"]],
 "shorts": [{"from": "47:30.0", "to": "47:52.0", "title": "WHO'S IN THE BACK SEAT?", "cropX": 420}],  // VOD times; cropX optional
 "endFreeze": {"text": "TO BE CONTINUED...", "seconds": 2.5},
 "endScreen": {"seconds": 15, "title": "PART 2 COMING", "cta": "SUBSCRIBE"},
 "description": "...",
 "en": {"title": "GTA V Chaos Mod - Part 1", "description": "...", "chapters": ["Intro", ...]},  // key = config "translation"; chapters 1:1 with "chapters"
 "credits": "..."                      // optional; generated from the style's music (Kevin MacLeod CC BY 4.0) + Kenney SFX
}
```

Only footage inside the episode's part range (`work/<slug>/parts.json`) exists in the prepared source.
For non-chaos streams leave `effects` empty and drop "--chaos"; the badge is chaos-mod specific.
The last episode of a VOD gets an end screen without "part N+1 coming" (`draft` uses the config's `thanks` text).

## Shorts

Every episode also yields 2–4 vertical Shorts, chosen while editing, rendered by `lp.py render` (or `lp.py shorts`):
720x1280, the game as a 720x720 native-pixel window (no upscaling), the webcam at native size, a hook title on top,
the episode's captions and banners inside the stretch, and the config's `full_episode` call ("FULL EPISODE: PART N ▶") at the end.

- A Short is one continuous VOD stretch of 8–60 s (best 15–35 s), no jump cuts: setup and punchline must both fit.
  The first second has to grab: start on the action or the reaction, not on a lead-in sentence.
- Pick moments that work without context: a visual gag, a big reaction, a quotable line. The episode's cold open is
  usually one.
- `title`: 2–4 words in caps that tease the payoff without giving it away ("WHO'S IN THE BACK SEAT?!").
- `cropX` (0–840, default 420 = centre) moves the 1080-unit-wide game window when the action is off-centre;
  check with `frames`.
- `lp.py publish` also matches the uploaded Shorts (by length), sets title (#shorts), a description linking the full
  episode, tags, Gaming, the channel's language; they stay private until the user's go. Post them between episodes.

## Editorial rules (from the episode 1 review)

- Target 20–30 min. Cut dead air, menus, loading, viewer-chat reading with no payoff, follow/sub thank-yous.
- Cold open: the funniest 10–20 s moment of the episode, kept `full`. Intro: the streamer explaining what's going on.
- Range boundaries must not slice words: start just after a sentence ends, end after one; `build_edit` also snaps to word edges.
- The same location or moment must not appear in both intro/cold open and main: remove it from `main`.
- Avoid clips under 2 s (the build merges them where it can; it reports the count).
- Face zooms on genuine reactions only, at least 4 s apart, never covering the gag they react to.
- Captions only for the best lines (~2 per minute max); overlapping ones stack automatically.
- Effect names are the mod's names as printed in the context file; the build snaps the badge to the OCR activation time.
  Banners need ≥ 4 s between them (they don't stack).
- Chapters: first at 0:00, at least 10 s apart, short labels for real story beats. Put each chapter where its
  beat starts in the edit (the draft's `TODO (near X)` times are only candidates; check them in the script).
- When two effects activate together, the banner shows the one the commentary reacts to.
- Thank-yous to chat (follows, subs, votes) go; a sarcastic "kiitos" to the game can stay.
- Thumbnail: bright, readable game frame (`bg`) + an expressive webcam frame (`face`), 2–4 words of text.

## Changing a rendered episode: patch, never re-render everything

A full render is only for the first render of an episode, or when the source, webcam, style or fps changed.
Every later fix is a patch render that re-renders only the changed seconds and splices them into the existing mp4:

```sh
lp.py render edits/<slug>-epN.json --patch               # auto: diff the timeline against the last render
lp.py render edits/<slug>-epN.json --patch end           # freeze + end screen (e.g. end-screen design changed)
lp.py render edits/<slug>-epN.json --patch 12:30-13:10   # output-time range(s), comma-separated; can combine: auto,end
```

- **auto** compares `src/edit.json` with the timeline of the last render (`work/<slug>/epN.rendered.json`): changed
  captions, badges, zooms, clips, lower third, title or end are re-rendered with their sound effects. If the episode
  length changed (clips added, removed or retimed), everything from the first change to the end is re-rendered.
  It falls back to a full render when the source, webcam or style changed, or when no previous render state exists.
- **Explicit ranges** are for changes that are not in the timeline data: edits to a component in `src/LetsPlay.tsx`
  or a colour in `src/styles.json` that only shows in one place. Times are output (edited video) times.
  A change to something on screen all the time (caption font, badge design) needs every place it appears, so a
  full render is usually simpler there.
- How it works: ranges widen to the old file's keyframes and unchanged video is stream-copied (cut by frame count,
  never time, because of B-frames). Audio comes from the kept unmastered mix (`work/<slug>/epN.mix.wav`) with the
  new ranges spliced in sample-exactly, then the whole track is re-mastered, so loudness is identical and there are
  no clicks. If the result doesn't have exactly the timeline's frame count, the old file is left untouched.
- Typical patch: 1–2 min (a caption fix re-rendered 1% of the episode in 1 min 24 s; the end screen in 1 min 27 s).
- A YouTube video's file can't be replaced: after a patch the user re-uploads, `apply_episode` the new id, and the
  old upload is deleted (deleting only after the user confirms).

## Gotchas

- Remotion copies `public/` into TMPDIR; `lp.py` points it at `.tmp/` because `/tmp` is a small RAM disk.
- The project is not a git repository: don't try worktree isolation; renders need the shared `footage/` and `public/`.
- `pgrep -f`/`pkill -f` with a pattern also matches the shell running it (a wait loop on `pgrep -f codec=wav` never
  ends; `pkill -f ocr_` kills its own command). Use `pgrep -f "[o]cr_"` style patterns or PIDs.
- Long steps (`prep`, `render`, `publish`, `faces` on a long episode) go in the background; foreground commands time
  out after 10 min.
- After changing any script, run `npm test` (CLI parsing of every subcommand + a build of `examples/edit-example.json`):
  an argparse slip once attached `--patch` to the wrong subcommand and broke `render`.
- Machine-specific settings are detected, not configured: NVENC if the GPU has it (else x264), Whisper on CUDA if
  available (else CPU), render concurrency = half the CPU threads.
- Whisper needs the venv's CUDA libs on `LD_LIBRARY_PATH` (handled by `lp.py`) and `av<16`.
- Prepared sources are ~10–20 GB each; delete `public/<slug>-epN.mp4` once the episode is approved (re-made by `prep`).
- Music and SFX live in `public/music`, `public/sfx`. A new style = an entry in `src/styles.json` (its `music` names feed the
  credits) plus CC0/CC BY tracks in `public/music`.
