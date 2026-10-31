# Rulebook

Every rule for turning a stream VOD into an episode: cutting, structure, captions, chapters, zooms, Shorts, thumbnail,
verification. `.claude/skills/letsplay/SKILL.md` says *how* (commands, schema, steps); this file says *what is allowed*.
Read it whole before the first editorial decision of a run. `LEARNINGS.md` collects new rules as they are learned; a
learning that has held for a few episodes is written here and removed there. When a rule and the code disagree, the
rule wins: fix the code (`check` should refuse what the rulebook forbids).

## 1. Who decides

- 1.1 The editor (Claude) makes every editorial decision and delivers finished episodes; the user watches the result.
- 1.2 The user owns: uploading in YouTube Studio, end screens, game titles, and every publish/schedule go-ahead.
  `lp.py publish --at/--now` and any YouTube visibility change only after the user's explicit go for that video.
- 1.3 Never upload video files. Never delete an old upload before the user confirms.

## 2. Hard rules

- 2.1 Never upscale raw material. Sources stay at the VOD's native size and episodes render at that size; zoom
  punch-ins are an editorial effect and fine.
- 2.2 Nothing in the stream overlay is blurred (vote list, stats, chat, follower goal, FPS, alert popups).
- 2.3 Captions are verbatim to the spoken words and uncensored: swearing stays, matching the audio. Never paraphrase.
- 2.4 A caption's words must exist in the current transcript (re-transcribing a VOD can invalidate old captions).
- 2.5 Every render or patch is installed only after the clock check passes (exact frame count, every frame's timestamp
  equal to its index / fps, audio as long as the video). A failing file is deleted and the old one kept.

## 3. Kind of video (decide per VOD first)

| Content | `style` | `mode` |
|---|---|---|
| Comedy, chaos, randomizers, co-op, most games | `hype` | – |
| Horror | `horror` | – |
| Calm or cosy (PowerWash, Subnautica, chatting streams) | `chill` | – |
| Speedrun / PB / runtime VODs | any, usually `hype` | `speedrun` |

- 3.1 Speedrun mode keeps every range whole (no silence trimming). Cut only before and after the run, plus long
  pre-run chatting or resets. Run start and finish are chapters, the final time goes in the title and thumbnail, no
  face zooms during the run.
- 3.2 No webcam in the VOD → `"cam": null`, no face zooms, thumbnail from the game frame alone with wider text.
- 3.3 Music-heavy games: trimming raises the loud-moment threshold automatically; set `loudDb` only if the build still
  keeps too much or too little.
- 3.4 Chaos Mod streams ingest with `--game chaosmod`; effect names are the mod's names as printed in the context file.

## 4. Length and what goes

- 4.1 Target 20–30 min per episode (a 3.5 h co-op VOD gave 13.6 min when only the streamer's own moments were kept:
  shorter is fine, padding is not).
- 4.2 Cut dead air, menus, loading, viewer-chat reading with no payoff, resets.
- 4.3 Thank-yous to chat (follows, subs, votes) go; a sarcastic "kiitos" to the game can stay.
- 4.4 Cutscenes and mission dialogue in another language than the commentary: keep a beat of it at most.
- 4.5 Whisper loops / hallucinated repeats (`[REPEATS]`): check the frames for what really happens, then cut or keep.
- 4.6 Chat admin, "miksi ette pelaa X" answers and off-topic chatter stay only when they are funny on their own.

## 5. Structure

The episode runs: cold open → title card → intro → (recap) → main → freeze ("JATKUU...") → end screen.

- 5.1 Cold open: 2–4 of the episode's funniest hits, 12–20 s in all, each kept `full`, each cut on its punchline. Two
  short hits read better than one long one. The draft's candidates are a start, not the answer.
- 5.2 Intro: the streamer explaining what is going on (the mod, the goal, the partner).
- 5.3 Recap (episode 2+): `"recap": "auto"` replays the previous cold open under a "previously" tag; pick other ranges
  when the story needs a different reminder; drop it when the episodes don't connect.
- 5.4 The same location or moment never appears in both cold open/intro/recap and main: remove it from `main`.
- 5.5 Main stays chronological and never goes back inside the intro's span (no `main` range between the first intro
  range's start and the last one's end; `check` refuses them). An intro pulled forward from later in the VOD is fine
  as long as nothing main then shows a menu or cutscene the viewer has just seen.
- 5.6 Main's first clip is the new game's first real moment, not a menu, loading screen or a cutscene already shown.
- 5.7 A chapter whose time lies inside a cold-open range lands in the cold open and is dropped: put it just past
  that range.

## 6. Cuts and ranges

- 6.1 Range boundaries never slice words: start just after a sentence ends, end after one (the build snaps to word
  edges, but choose the sentence yourself).
- 6.2 Keep the beat after a punchline, a question or a laugh: the pause is the joke's timing. Don't end a range on the
  last word.
- 6.3 Shots are at least 4 s; clips under 2 s are avoided (the build merges what it can and reports the count).
- 6.4 Jump cuts alternate a slight punch-in and crossfade their audio; cuts over a longer skip get the whoosh. Don't add
  ranges just to hide a cut: the cut is the style.
- 6.5 A `full` range (cold open, Short) ends at least 0.3 s after its last word and 0.3 s before the next one, by the
  audio, not by Whisper's word times: its last word's end often comes early ("mitä täs pelis tapahtuu?" was cut at
  "tapa"). `check` warns when a range end lies on or right after a word; measure the voice band in the VOD when in doubt.
- 6.6 The draft's liveliness picks (laughs, screams, action) are candidates for the cold open and Shorts, not the edit.
- 6.7 Never build another EDL of an episode that is rendering (it overwrites the props the render reads).

## 7. What is on screen decides (co-op and every named thing)

- 7.1 A caption, chapter label, cold-open hit, Short title, thumbnail hook or description line may only name something
  the viewer sees. Talk alone never names anything.
- 7.2 Before `check`, pull frames (`lp.py frames`) at the time of every chapter, caption, cold-open hit and Short, a
  few across each range, and look at the sheet. If the named thing (plane, fire, bank, sniper, motorbike…) is not in
  the game frame, drop it and name the chapter after what the frame shows: the mission text, the vehicle, the place,
  the retry, the on-screen result.
- 7.3 Co-op streams: follow the streamer. The partner's gameplay is not in this stream, so their story about their own
  game shows nothing. Cut long `[GUEST]` stretches unless they set up the streamer's moment.
- 7.4 No captions or banners on `[GUEST]` lines (`check` refuses them); no face zoom there unless the streamer's own
  face is the joke; automatic punch-ins skip them.
- 7.5 The streamer talking to the partner about the partner's game (`[TO GUEST]`: second-person forms from config
  `partner_words`) is treated like `[GUEST]`: `check` refuses captions on it.
- 7.6 Speaker labels (webcam mouth motion) and `[TO GUEST]` are hints, not proof. The streamer watching the partner's
  screen says "mä oon liekeissä" as easily as the partner. Only the frame settles it (7.2).
- 7.7 Speaker identity can't be made reliable from the mixed audio (voice embeddings, envelope correlation and face
  ratios were tried); don't spend a run on it again.

## 8. Captions

- 8.1 Verbatim and uncensored (2.3), words present in the transcript (2.4), on something visible (7.1).
- 8.2 Only the best lines, about 2 per minute at most. Overlapping captions stack automatically.
- 8.3 Not on `[GUEST]` or `[TO GUEST]` lines (7.4, 7.5).
- 8.4 A caption may sit in the cold open; the same line then shows there and in main.
- 8.5 Whisper's ghost words (0 s long, or stretched over silence at a quiet segment end) are never captioned: the
  build drops them from Short cues and subtitles. A caption nobody can hear on the Short is wrong even if the transcript
  has it; when one slips through, check the voice-band loudness at its time.

## 9. Effects and banners (Chaos Mod)

- 9.1 Effect names are the mod's printed names; the build snaps the badge to the OCR activation time.
- 9.2 Banners need at least 4 s between them (they don't stack).
- 9.3 When two effects activate together, the banner shows the one the commentary reacts to.
- 9.4 Every effect gets a one-line description in the commentary language; new ones are saved for later episodes.

## 10. Zooms

- 10.1 Face zooms only where the streamer's face is funny or strange (look at it with `frames` first) or right as they
  say something funny. Not on routine talk, at least 4 s apart, never covering the gag they react to.
- 10.2 Game zooms on a visible thing worth a closer look, never on talk.
- 10.3 No face zooms during a speedrun or on the partner's lines (7.4).

## 11. Chapters

- 11.1 First at 0:00, at least 10 s apart, one per real story beat.
- 11.2 A label is what the viewer sees at that time: the mission text, the vehicle, the place, the retry, the result.
  Never the topic of the talk (7.1, 7.2).
- 11.3 Put the chapter where its beat starts in the edit, on the reveal itself or on the place, never before the
  payoff: "Lentokone keskellä tietä" 10 s before the plane and "Kaikki tulessa" 20 s before the fire spoil the gag.
- 11.4 Labels are read on screen as cards: 2–4 words, no spoilers of the beat ("Kissat kyydissä", not "Kissat kuolee").
- 11.5 The translation block lists the chapters 1:1 in the same order.

## 12. Music

- 12.1 The music bed under main is on for `hype` and `chill` (ducked under speech); `"bed": false` for games whose own
  music carries the episode.
- 12.2 Tracks are CC0 / CC BY; the credits in the description come from the style's `music` names.

## 13. Thumbnail

- 13.1 A bright, readable game frame (`bg`) plus an expressive webcam frame (`face`) and 2–4 words of hook that say
  what happened (the title already names the series and part). The hook names something visible (7.1).
- 13.2 No word longer than 9 letters in the hook (the planner splits lines at 9).
- 13.3 Pick another `face` if the cut-out comes out see-through; keep `bgOrigin` up and left of the stream's webcam.

## 14. Title, description, translation

- 14.1 Title: series name and part; the final time for speedruns.
- 14.2 Description: two or three sentences on what happens, naming only things the viewer sees (7.1), then one line on
  what the mod is; chapters and credits are appended by the build.
- 14.3 The `translation` block mirrors title, description and chapters in the configured language.
- 14.4 Tags: game, mod, series, co-op partner, language, channel names.

## 15. Shorts

- 15.1 2–4 per episode (fewer when fewer moments pass the frame check); 8–60 s, best 15–35 s.
- 15.2 One continuous VOD stretch, or two stretches (`ranges`, one internal cut on a sentence end) when the setup and
  the payoff are apart.
- 15.3 The first second has to grab: start on the action or the reaction, not on a lead-in sentence.
- 15.4 Moments that work without context: a visual gag, a big reaction, a quotable line. The cold open's hits usually.
- 15.5 Co-op: the streamer's own moment. `check` refuses a Short where `[GUEST]` lines are over a third of the talking,
  unless `"onScreen"` says what the streamer's screen shows, written only after looking at the frames (the partner
  reacting to the streamer's visible explosion is fine).
- 15.6 `title`: 2–4 words in caps that tease the payoff without giving it away.
- 15.7 `cropX` moves the game window when the action is off-centre; check with `frames`.
- 15.8 Shorts stay private until the user's go; post them between episodes.

## 16. Review and verification

- 16.1 `check` must pass; fix everything it reports, then read the check grid.
- 16.2 Read the script top to bottom as the viewer meets it: every cut on a finished sentence, every joke with its
  setup, no thank-yous or chat admin left, captions/banners/zooms on the right beat, each chapter card where its beat
  starts, nothing repeated or confusing.
- 16.3 After the render: loudness about −14 LUFS, the printed frame count and clock check, a look at the output's chapter
  cards and cold open (grab frames from the mp4).
- 16.4 Changing a rendered episode is a patch, never a full re-render, unless source, webcam, style or fps changed.
- 16.5 Never pipe a render through `grep | tail`; log it whole and read the log.
- 16.6 After changing any script, run `npm test`.
- 16.7 A new splice or mux path is tested on 20 s (`-t 20`) before a 20-minute render relies on it.

## 17. Learning

- 17.1 Read `LEARNINGS.md` whole at the start of every run; append at the end of every run and after every correction.
- 17.2 A learning that has held for a few episodes becomes a numbered rule here and leaves `LEARNINGS.md`.
- 17.3 When the user corrects a result, the fix goes into three places: the episode, this rulebook (or `LEARNINGS.md`),
  and `check` where it can be checked mechanically.
