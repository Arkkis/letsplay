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

## Learnings loop

`RULEBOOK.md` in the repo root is every editorial rule, numbered (cutting, structure, captions, chapters, zooms, Shorts,
thumbnail, verification); `LEARNINGS.md` is this skill's memory; `ROADMAP.md` lists researched but unbuilt pipeline
improvements (read it only when asked to improve the pipeline, never during an episode). **First action of every run: read
the first two whole.** **Last
action of every run, and every time the user corrects a result: append what you learned to `LEARNINGS.md`** (dated, one
line each: what went wrong or what the user asked for, and the rule that follows; measurements too). A learning that has
held for a few episodes becomes a numbered rule in `RULEBOOK.md` and leaves the file; keep it under ~150 lines. Never end
a run without updating it.

## Hard rules

`RULEBOOK.md` §1–2: the user owns uploads and every publish go; original recordings are read-only (2.6); never upscale, never blur the overlay, captions verbatim
and uncensored, no render installed without the clock check. Compositions are laid out in 1920x1080 units and `lp.py`
renders at `--scale=<VOD width>/1920`. Run long steps (`ingest`, `prep`, `render`) with `run_in_background` and wait
for the notification.

## Steps

Scripts do the mechanical work; **you are the editor**. Programs cannot judge edit quality, so every draft is curated
by you and every edit is reviewed by you before it renders. Never ship a draft as-is or skip the review to save time.

1. **ingest** `lp.py ingest "<VOD path>" [--game chaosmod]`: copies to `footage/<slug>.mp4`, Whisper transcript (GPU; `large-v3`
   with beam search and the config's `transcript_prompt`), 100 ms loudness map, spoken language per 10 s (finds cutscenes in another
   language, ~2 min on a GPU), audio events (laughs, screams, bangs: `work/<slug>/events.json`, 10 s), visual motion of the game
   and of the webcam at the config's `cam` rect (`motion.npz`, ~3 min for 3.5 h), and with `--game chaosmod` (GTA V Chaos
   Mod streams; run `games/chaosmod/build_names.py` once first) the active-effect OCR (~13 min for a 3.5 h VOD, all CPU cores); everything lands in `work/<slug>/`.
   **Co-op streams** (a partner's webcam on screen, both voices on one track): run
   `lp.py speakers <slug> --host x,y,w,h --guest x,y,w,h` with a box over each person's lower face in VOD pixels
   (find them with `frames`; keep each box off moving HUD such as a minimap, and check a few times across the VOD that
   the faces stay inside). It reads mouth movement in both webcams (voices can't be told apart) and labels every
   transcript line; `context` then marks the partner's lines `[GUEST]`, unclear ones `[?]`, and the streamer's lines
   addressed to the partner `[TO GUEST]` (config `partner_words`; talk about the partner's game) (~7 min for a 5 h VOD).
   The labels are a hint, not the truth: they miss and mislabel lines, so anything put on a line is checked against the frame.
   **Separate recordings** (gameplay and webcam as their own files, yours and a co-op partner's; game audio only in the
   gameplay files, each mic only in its webcam file): kept as separate tracks, composited only at render. The files share
   no audio to sync by, so the user aligns them on a Kdenlive timeline (all four tracks; for drift over hours, cut a clip
   later on and re-align the piece) and saves the project. `lp.py assemble <slug> --game <yours> --cam <your webcam>
   --guest-cam <theirs> [--guest-game <theirs>] --kdenlive <project>` (or `--offset cam=m:ss` per file) records the sync,
   webcam boxes (`--cam-box`/`--guest-cam-box x,y,w`, negative = from the right/bottom; defaults stacked bottom-right;
   `--cutout`: transparent backgrounds, side by side on the bottom edge) and measured levels (`--gain role=±dB`) in
   `work/<slug>/assemble.json`, and bakes only a reference for analysis: `footage/<slug>.mp4` (your gameplay, plain
   webcam boxes, the mix) and with `--guest-game` `footage/<slug>-guest.mp4` (the partner's view on the same clock;
   `lp.py frames <slug> <times> --guest` shows it). `prep` then cuts every track for the episode on its own:
   `public/<slug>-epN.mp4` (your game, graded), `-guest.mp4` (theirs, which the EDL's `"pov"` switches to, RULEBOOK 7.8),
   `-cam`/`-guestcam` (the webcam with its mic at its box size; with `--cutout` matted on the GPU for the episode's range
   only, a few minutes per episode, VP9 with alpha). The render draws the webcams over the game at their boxes, so boxes,
   views and cut-outs change with a re-prep, not a re-assembly. `--guest-game-box x,y,w` instead bakes their gameplay as a
   box into yours (no guest track). Run `--preview m:ss` at a few points first and look at the 20 s clips: boxes off the
   HUD, lips in sync. The full reference takes an hour or two for a long session (background) and is followed by
   `lp.py ingest footage/<slug>.mp4 --slug <slug>` and `lp.py speakers <slug>` with no boxes: labels come from which mic
   is louder, far more reliable than mouth reading. For sync that holds over hours, ask both players for a marker at the
   start and at the end: side by side in-game, one counts "3, 2, 1, now" and honks on "now", the other says "now"
   on hearing it. That puts one event in all four files (both mics, both games); aligning both markers in Kdenlive
   fits the drift.
   The webcam rect for motion, faces and the EDL's `cam` comes from the assembly, not config `cam`.
   **Whose stream was it?** Ask before writing the lower third, the descriptions or the Shorts label. When the user
   recorded locally and only the partner streamed, nothing says "Twitch stream": set `"fromStream"` (RULEBOOK 14.5).
2. **split** `lp.py split <slug> [--target 25] [--parts N]`: episodes of ~25 *edited* minutes each (the 20–30 min sweet spot
   for gaming; ≥8 min allows mid-roll ads). It estimates how much each stretch keeps after trimming, so talky streams get
   longer raw parts than quiet ones, and cuts at a speech pause. `--parts N` fixes the count (speedruns: see below).
   It prints each episode's raw and estimated edited length; re-run with another `--target` if they look wrong.
   Then start `lp.py prep <slug> all` in the background: every episode's source is ready by the time its edit is.
3. Per episode N:
   1. `lp.py draft <slug> N` → `edits/<slug>-epN.json`, a first pass: main ranges from speech/action with English
      cutscenes and Whisper loops left out, every effect under its real mod name with its known description, chapter
      candidates, intro guess, a cold-open montage of the three liveliest moments (loudness while talking, laughs and screams
      heard, action on screen, the webcam moving), `"recap": "auto"` from episode 2 on, series metadata copied from a sibling
      episode. Everything editorial is `TODO`. It prints the eight liveliest moments (cold open and Shorts candidates) and
      renders `work/<slug>/epN-draft.jpg`: a frame of each of them, then of the chapter candidates. Look at it once.
   2. `lp.py context <slug> N` → read `work/<slug>/epN.context.txt` **in full**: transcript, `[EFFECT] name — description`,
      `[EN a–b]` (another language than the commentary: cutscene or mission dialogue: keep only a beat of it, if any), `[REPEATS a–b]` (hallucinated
      transcript: check with `frames` what really happens), `[LOUD]`, `[LAUGH]` `[SCREAM]` `[BANG]` (heard, not in the
      transcript: a laugh marks a joke that landed), `[ACTION]` (heavy on-screen motion: something is happening even if
      nobody talks), `[FACE]` (the webcam's liveliest 2 s windows: reactions, the first place to look for face zooms).
   3. Curate the draft like a professional editor (`RULEBOOK.md`). Rank the candidate stretches first (6.6: the draft's
      picks, audio peaks, a `frames` sheet), keep only ranges where something happens on screen or the talk pays off
      (4.7), cut repeats (4.8), keep one through-line (5.9), an intro of about 20 s over action (5.2), a 1.5 s title card (5.1b) and an ending on a payoff (5.8).
      Drop weak or repetitive ranges, tighten boundaries to
      sentence ends, pick the real cold open and intro, write verbatim captions, place face/game zooms, write one-line descriptions
      for effects without one (they're saved to `games/chaosmod/descriptions.<language>.json` for later episodes), chapter labels, title,
      description and the translation. A chapter label sums up the whole span from its time to the next chapter (what the
      viewer sees across it: places, vehicles, retries, results), never just the frame at the chapter time (`RULEBOOK.md` 11.2).
      One chapter per story beat of 2–3 min (4–6 in a 10 min episode), never two inside a minute (11.1).
   4. Shorts: rank the candidates on a frame sheet (RULEBOOK 15.0: every cold-open hit and big caption on something seen
      is one; a hit left out gets its reason in `"notShorts"`), then pick up to 4, picture first and no inside jokes
      (15.4); fewer is fine (see Shorts below).
   5. **Frame check (always).** `lp.py see edits/<slug>-epN.json` (~1 min; a local vision model, config `vision_model`,
      default `gemma4:12b` in Ollama) → read `work/<slug>/epN.see.txt`: for every chapter span, caption, cold-open hit, Short
      and the thumbnail, a `scene` line saying what the game frames show, and for every label a verdict: `ok`, `!! NOT
      VISIBLE` (the named thing isn't in the frames: drop it or relabel), `?? unclear` (an abstract label, or can't tell) or,
      for a caption, `-- talk, nothing to see` (the quote names nothing that should be on screen: fine as it is).
      The model's reading of the label is quoted on the verdict line; a mistranslation voids that verdict, the scene line
      still stands. Open the row sheet named on a flagged line (`work/<slug>/see/epN-<item>.jpg`) only when the scene line
      doesn't settle it, and `lp.py frames <slug> <m:ss> ...` for anything the model didn't look at. A named thing (plane,
      fire, bank, sniper, motorbike…) must be in the game frame; if it isn't, the line was about the partner's game or about
      nothing: drop it and name the chapter after what the scene lines across its span show (the mission screen, the
      vehicle, the place, the on-screen text). Talk alone never names anything. Co-op: every label, no exceptions.
   6. Thumbnail: `lp.py faces <slug> N` (liveliest webcam moments) and `lp.py frames <slug> <m:ss> ...` (game frames)
      → pick `thumb.face`, `thumb.bg` and 2–4 words of text.
   7. **Proof-read** `lp.py proof edits/<slug>-epN.json` → read `work/<slug>/epN.proof.txt`: every caption's line and every
      Short decoded a second time beside the transcript and the caption text. Fix every `!!` (caption words heard in
      neither decode: rewrite the caption to what is said) and every `??` (transcript words the second pass doesn't hear:
      they become the Short's cues and the subtitles, so map them in `"wordFixes"`). Then read `work/<slug>/epN.text.txt`
      whole, every time: every caption, card, note, Short cue, subtitle cue and both languages' title and description.
      `proof.txt` ends with SUBTITLE SUSPECTS: cues with a word Whisper was unsure of or the Finnish speller
      (libvoikko) rejects and the stream rarely says, each with a second decode beside it. Settle those first.
      Fix mishearings, misspellings and stiff translation (RULEBOOK 8.7), re-run `proof`, and when it reads right
      `lp.py proof edits/<slug>-epN.json --read` (render refuses unstamped or changed text). Then `lp.py check edits/<slug>-epN.json`
      → fix everything it reports (all problems are listed at once), then read the grid `work/<slug>/epN-check.jpg`.
   8. **Review** `lp.py script edits/<slug>-epN.json` → read `work/<slug>/epN.script.txt` top to bottom as the viewer
      will meet it: does every cut land on a finished sentence, does each joke get its setup, are there thank-yous or chat
      admin left, do captions/banners/zooms land on the right beat, does each `CHAPTER CARD` sit where its beat starts
      and does its label cover everything up to the next card, is anything repeated or confusing? Fix and re-run until it reads like a finished episode.
   9. `lp.py render edits/<slug>-epN.json` → `out/<playlist>/<output>.mp4` (≈ 17–27 min), `<output>.jpg` (thumbnail),
      `<output>.description.txt`, `.<language>.srt` (none with config `"subtitles": false`), `.<translation>.json`, and the Shorts in `out/<playlist>/shorts/` (~25 s each to render). Check the printed loudness is about −14 LUFS and look at
      the thumbnail. Later fixes: `--patch` (see below), never a full re-render. Look at rendered output with
      `lp.py look edits/<slug>-epN.json <m:ss> ... [--short K] [--last S]` (one sheet, `work/<slug>/epN-look.png`),
      never hand-written ffmpeg grabs; a patch render writes that sheet of what it changed by itself.
      `lp.py at edits/<slug>-epN.json <m:ss> ... [--vod]` maps episode time ↔ VOD time with the line said there.
4. Report: per episode the file, length, and anything the user must know in a clause. Never upload video files.
5. **YouTube**: the user uploads the mp4 in Studio. `lp.py publish edits/<slug>-epN.json` (run in the background) waits for
   the upload (matched by length), applies title, description with chapters and credits, tags, thumbnail, subtitles,
   translated title/description, Gaming, the channel's language, recording date, not for kids, no altered content, and the
   `playlist` from the EDL; the video id is kept in `work/<slug>/epN.youtube.json`. Add `--at <ISO>` (schedule) or
   `--now` **only after the user's explicit go for that video**. The MCP server `youtube` (`scripts/youtube_mcp.py`) has
   the same operations as tools. Not in the API, so the user sets them in Studio: the end screen and the game title on the
   episode (the last 15 s are laid out for a row of video slot, subscribe circle, video slot), the "related video" link to
   the full episode on every Short, and optionally a Test & Compare run (up to 3 thumbnails, a title) when there is a
   second thumbnail worth testing. List these in the report.
   If it says "not signed in", ask the user to run `! .venv/bin/python scripts/youtube_mcp.py auth`.
6. **Learn from the audience**: a few days after an episode went public, `lp.py retention edits/<slug>-epN.json` pulls its
   YouTube audience-retention curve and writes `work/<slug>/epN.retention.txt`: the curve in 10 % steps and the sharpest
   drops with the script lines playing there. Before editing the next episode of a series, read the previous episodes'
   retention files: a drop on a long talky stretch, a recap, a chapter type or a caption-free minute is a rule for this
   series (keep such rulings in the EDL's description of what you did, and in `$DECISIONS` when orchestrating).
   A sign-in from before the analytics scope existed must be renewed once (`! .venv/bin/python scripts/youtube_mcp.py auth`).

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

## Model per task (optional)

Not the default: make an episode in one Opus session as above unless the user asks for this. A replay of episode 3's token log
at API prices put this setup at −4.8% ($3.17 vs $3.33), so it isn't worth the extra sessions for cost alone.

An episode can run with each kind of task on its own model through `/orchestrate`. The fresh episode session (the recipe
above with `--model opus`) is both editor and orchestrator, so workers' `ASK:` messages reach the session that knows the episode.
`ingest`, `split` and `prep all` run once per VOD before it starts. This table replaces orchestrate's "lowest tier that can do a piece".

| Model | Tasks | Steps |
|---|---|---|
| Haiku | Run `draft`, `context`, `render`, `render --patch`, `retention`; report file, length, LUFS. No decisions, never edits the EDL | 3.1, 3.2, 3.9, 6 |
| Sonnet | Missing effect descriptions, the translation block, a thumbnail shortlist from `faces`/`frames` (3 of each with times), fixing what `check` reports | parts of 3.3, 3.6, 3.7 |
| Opus (the episode session) | Cuts, cold open, intro, captions, zooms, chapters, Shorts, title, description, final thumbnail and hook, the `script` review, verifying the render, `publish` after the user's go | the rest of 3.3, 3.4, 3.5, 3.6, 3.8, 4, 5 |

Order: Haiku `draft` + `context` → Opus writes the editorial EDL → Sonnet's tasks → Opus picks the thumbnail, reviews with `script`
and runs `check` again after its own fixes → Haiku `render` → Opus verifies.

- Start each worker with `n=$(SPAWN_FLAGS="--settings .claude/orchestrate-worker.json" ~/.claude/skills/orchestrate/acquire.sh <model> auto <you> $PWD)`:
  the `lp.py` steps are pre-allowed, `lp.py publish` and YouTube are denied. A command outside the list goes to the auto-mode
  classifier; if a worker goes quiet, `peek.sh <name>` shows why, and a refused routine command belongs in that file.
- Only one session touches the EDL at a time. Sonnet changes only effect descriptions, the translation block and the fields `check`
  reports. Editorial fields are Opus's; Sonnet reports a problem it can't fix without changing one.
- Workers run long steps in the background. Only `DONE:` means finished: skip `wait.sh`, ignore idle notifications, and run `peek.sh`
  if no `DONE:` has arrived after 90 min (a timeout must not start a second render). Fixes after a render are `--patch`.
- Editorial calls are the editor's, so workers don't escalate them. `$DECISIONS` is shared across VODs: series-wide rulings only.
- Verify a `DONE:` yourself: `lp.py check` output, `ffprobe` length against the worker's report, `ffmpeg -i <mp4> -af ebur128=framelog=quiet -f null -`
  for about −14 LUFS, and a look at the thumbnail. `edits/` and `out/` are gitignored, so there is no diff to read.
- No `--worktree`: footage, work files, edits, config and environments are all gitignored. End with `~/.claude/skills/orchestrate/release.sh --orch <you> $PWD`.

## Pick the kind of video first

Decide per VOD from its title and a look at `frames`/`context`:

| Content | `style` | `mode` | Notes |
|---|---|---|---|
| Comedy, chaos, randomizers, co-op, most games | `hype` | – | yellow headlines, funk intro |
| Horror (Phasmophobia, SCP, Forewarned, Yume Nikki) | `horror` | – | bone-white headlines, eerie music, glitch punch-ins |
| Calm or cosy (PowerWash, Subnautica, chatting streams) | `chill` | – | warm-yellow headlines, light music, no glitch effect |
| Speedrun / PB / runtime VODs | any (usually `hype`) | `speedrun` | `split --parts 1` (or one part per run); the run itself is never jump-cut |

Rules per kind (speedrun mode, no webcam, music-heavy games): `RULEBOOK.md` §3. No webcam means `"cam": null`,
`"faceZooms": []`, `"thumb.face": null`; music-heavy games may need `"loudDb"` (e.g. `-14`) in the EDL.

## EDL schema

All times are VOD times as `m:ss[.s]` (minutes may exceed 59, e.g. `62:18`). See `examples/edit-example.json` for a small complete example.

```jsonc
{
 "vod": "<slug>", "episode": 1, "output": "Example Game - Part 1",   // file name; the YouTube title is youtubeTitle (RULEBOOK 14.1)
 "youtubeTitle": "It all goes wrong – Example Game part 1",  // hook + series, < 60 chars, hook ≠ thumbnail text
 "style": "hype",                      // hype | horror | chill (src/styles.json: colours, caption font, music)
 "playlist": "Example Game", "tags": ["Example Game", "..."],  // used by `lp.py publish`
 "mode": "speedrun",                   // optional; omit for normal let's plays
 "loudDb": -14,                        // optional loud-moment threshold override (dB, 100 ms RMS)
 "cam": [990, 480, 290, 240],          // webcam rect x,y,w,h in VOD pixels, or null; check with `frames`, layouts changed over the years
 "thumb": {"bg": "48:10.0", "face": "51:02.5", "bgZoom": 1.25, "bgOrigin": "62% 45%", "tag": "EXAMPLE GAME #1", "text": "IT ALL GOES WRONG"},
 "title": {"kicker": "EXAMPLE", "title": "GAME", "episode": "PART 1", "tagline": "...", "bg": "48:10"},
 "lowerThird": {"at": "24:40.0", "text": "YourName", "sub": "Example Game · Twitch stream 31.1.2024"},   // co-op: "guest": {"text", "sub"}; with separate webcam tracks each tag sits above its own cam, one after the other
                                       // optional: "side": "right" (tag over a bottom-right webcam), "guest": {"text", "sub"} = co-op partner's tag on the other side
 "fromStream": "Co-op-sessiosta",           // optional: the Shorts' label under the channel name, when this wasn't your own stream (config text "from_stream" otherwise)
 "recap": "auto",                      // episode 2+: "previously" before the cold open: "auto" = the previous episode's coldOpen, or ranges [[a, b], ...] from anywhere in the VOD
 "coldOpen": [["21:05.0", "21:19.5", "full"], ...],   // a montage of 2–4 hits; "full" = keep as is, otherwise silences are jump-cut
 "intro":    [["24:30.0", "25:35.0"]],           // music bed under it; the title card sits between coldOpen and intro
 "main":     [["3:40.0", "4:05.5"], ...],         // chronological
 "pov":      [["41:12.0", "41:30.5"]],            // optional, separate co-op recordings: VOD spans shown from the partner's view (RULEBOOK 7.8); Shorts then show the partner's webcam and lower-third tag too
 "bed": true,                          // optional: music bed under main, ducked under speech (default: the style's track; false = none; "<track>" = public/music/<track>.mp3)
 "chapterCards": true,                 // optional: on-screen card where each chapter starts (default true)
 "effects":  [["4:29", "Heavy Recoil", "Guns kick like a mule"]],   // rough time, mod effect name (as in context), one-line description ("" = from the library); optional 4th: seconds on screen (default 3.5)
 "effectLabel": "ARVONTA",             // optional: hand-placed banners without a game module; times are exact, description required
 "notes":    [["12:45.5", "Puhun Dextan kanssa", "Hänen mikkinsä ja pelikuvansa mukana vasta {from} alkaen", 8]],  // optional: a note to the viewer, banner with the config "note" label (HUOM); exact time, title, line, seconds (default 8); {from}/{until} = where the co-op partner's tracks start/end in the episode (RULEBOOK 7.9)
 "captions": [["5:34", "minimap", "I CAN'T SEE MY MINIMAP AT ALL"]], // rough time, a word in the transcript segment, verbatim caps text
 "wordFixes": {"Taviraalassa": "Sairaalassa", "heti seikkailee": "Dexta seikkailee"},   // optional, from `proof`: transcript spellings corrected in Short cues and subtitles (bare words, case-insensitive; several words = that run only)
 "faceZooms": ["7:28"], "gameZooms": ["17:15"],
 "chapters": [["0:00", "Intro"], ["3:40", "The chaos begins"]],
 "shorts": [{"from": "47:30.0", "to": "47:52.0", "title": "WHO'S IN THE BACK SEAT?", "cropX": 420},  // VOD times; cropX optional
            {"ranges": [["12:01.0", "12:16.0"], ["12:40.0", "12:58.0"]], "title": "...", "onScreen": "..."}],  // two ranges = one internal cut; onScreen: see Shorts
 "notShorts": {"21:05.0": "inside joke about the editing"},  // optional: why a cold-open hit isn't a Short (RULEBOOK 15.0)
 "endFreeze": {"text": "TO BE CONTINUED...", "seconds": 2.5},
 "endScreen": {"seconds": 15, "title": "PART 2 COMING", "cta": "SUBSCRIBE"},
 "description": "...",
 "en": {"title": "GTA V Chaos Mod - Part 1", "youtubeTitle": "It all goes wrong – GTA V Chaos Mod part 1", "description": "...", "chapters": ["Intro", ...]},  // key = config "translation"; chapters 1:1 with "chapters"
 "credits": "..."                      // optional; generated from the style's music (Kevin MacLeod CC BY 4.0) + Kenney SFX
}
```

Only footage inside the episode's part range (`work/<slug>/parts.json`) exists in the prepared source.
Without a game module leave `effects` empty. `"effectLabel"` (hand-placed banners: exact time, 1–3 word name, one-line
description) exists for a game event viewers can't read from the screen; don't use it for randomizers or anything the
game already shows: extra cards there only confuse.
The last episode of a VOD gets an end screen without "part N+1 coming" (`draft` uses the config's `thanks` text).

## Shorts

Every episode also yields up to 4 vertical Shorts (fewer when fewer pass RULEBOOK 15.0–15.4), chosen while editing, rendered by `lp.py render` (or `lp.py shorts`):
720x1280, the game as a 720x720 native-pixel window (no upscaling), the webcam at native size, a hook title on top,
every spoken word captioned a few words at a time (Shorts are watched muted), the episode's own captions shown big
and its banners inside the stretch, and the config's `full_episode` call ("FULL EPISODE: PART N ▶") at the end.

- What makes a Short, length, `ranges`, co-op and `onScreen`, title, `cropX`: `RULEBOOK.md` §15. `cropX` is 0–840,
  default 420 = centre, for the 1080-unit-wide game window.
- `lp.py publish` also matches the uploaded Shorts (by length), sets title (#shorts), a description linking the full
  episode, tags, Gaming, the channel's language; they stay private until the user's go. Post them between episodes.

## Editorial rules

All of them, numbered, in `RULEBOOK.md`: length and what goes (§4), structure and chronology (§5), cuts (§6), the
frame check and co-op (§7), captions (§8), effects (§9), zooms (§10), chapters (§11), music (§12), thumbnail (§13),
title and description (§14), review (§16). What `check` enforces mechanically is marked there; the rest is yours to
apply while writing the EDL and reading the script.

## Changing a rendered episode: patch, never re-render everything

A full render is only for the first render of an episode, or when the source, webcam, style or fps changed.
Every later fix is a patch render that re-renders only the changed seconds and splices them into the existing mp4:

```sh
lp.py render edits/<slug>-epN.json --patch               # auto: diff the timeline against the last render
lp.py render edits/<slug>-epN.json --patch end           # freeze + end screen (e.g. end-screen design changed)
lp.py render edits/<slug>-epN.json --patch 12:30-13:10   # output-time range(s), comma-separated; can combine: auto,end
```

- A patch also re-renders each Short whose props changed (a Short.tsx-only change needs `lp.py shorts`).
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
  no clicks. Unchanged pieces are cut at a keyframe's own timestamp and checked (exact frame count, starts on a keyframe),
  the concat list carries each piece's exact duration, and every render or patch is installed only after `sync_error`
  passes: exactly the timeline's frame count, every frame's timestamp equal to its index / fps, audio as long as the
  video. A file that fails is deleted and the old one kept, so a desynced episode can't land in `out/`.
- Typical patch: 1–2 min (a caption fix re-rendered 1% of the episode in 1 min 24 s; the end screen in 1 min 27 s).
- A YouTube video's file can't be replaced: after a patch the user re-uploads, `apply_episode` the new id, and the
  old upload is deleted (deleting only after the user confirms).

## Gotchas

- Remotion copies `public/` into TMPDIR; `lp.py` points it at `.tmp/` because `/tmp` is a small RAM disk. A hand-run
  `npx remotion still/render` needs `TMPDIR=$PWD/.tmp` too, or it copies the multi-GB tracks into /tmp and fails with ENOSPC.
- Two EDLs of one episode (an alternative cut) share `work/<slug>/epN.*`: props, subtitles, text and the proof stamp.
  Back those files up before building the second, re-run `proof` and `proof --read` for it, render, then restore.
- The Finnish speller (`proof`) needs libvoikko and a dictionary. On Arch `voikko-fi` is AUR-only and needs `foma`,
  which isn't packaged: install `libvoikko` from the repos and unzip the prebuilt https://www.puimula.org/htp/testing/voikko-snapshot-v5/dict.zip
  into `~/.voikko/5/mor-standard/`.
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
  A recap's own cut (`public/<slug>-epN-recap.mp4`, made by the build from the raw VOD) is small and rebuilt when its ranges change.
- VODs ingested before audio events and motion existed have no `events.json` / `motion.npz`; everything still works
  without them (no `[LAUGH]`/`[ACTION]`/`[FACE]` lines, trimming on speech and loudness only). Re-running `ingest`
  adds them without touching the transcript (which an older Whisper setup made: word times in existing EDLs stay valid).
- The auto-trim now keeps about 15 % more than before (beats, laughs, action, 4 s shots); re-measure `edit_ratio` in
  `config.json` from the next finished episode (finished length ÷ `draft`'s estimate × the old ratio).
- Music and SFX live in `public/music`, `public/sfx`. A new style = an entry in `src/styles.json` (its `music` names feed the
  credits) plus CC0/CC BY tracks in `public/music`.
