# Learnings

Running memory of the `/letsplay` skill. Read it whole before the first editorial decision of every run; append to it at the
end of every run (and whenever the user corrects a result). One line per learning, newest last, dated, concrete: what went
wrong or what the user asked for, and the rule that follows. When a line has proven itself over a few episodes, move it
into `RULEBOOK.md` as a numbered rule and delete it here. Keep this file under ~150 lines.

## Editing

- 2026-10-31 Intro and main must stay chronological. The Vice City ep1 intro jumped ahead to the mod explanation (10:41)
  and main then rewound to the new-game menu (9:28), so the viewer saw the main menu, loading screen and opening cutscene
  twice. Check the `[intro …]`/`[main …]` VOD times in the script run in order; drop the rewind clips (menus and
  cutscenes under the partner's talk are the first to go).
- 2026-10-31 Chapter cards spoil: "Lentokone keskellä tietä" 10 s before the plane and "Kaikki tulessa" 20 s before the
  fire gave the gag away. Put the chapter on the reveal itself or name the place, not the payoff.
- 2026-10-31 Speaker labels beat memory: two captions and a Short in the first Vice City cut were on lines the labels
  attribute to the partner (`[GUEST]`). Grep the context for the line before captioning it; `check` refuses `[GUEST]` captions.
- 2026-10-31 A caption's words must exist in the current transcript: "Stop it you maniac" was a game voice line the new
  Whisper setup no longer hears. Re-transcribing a VOD (old file kept as `transcript.old.json`) can invalidate old EDLs' caption matches.
- 2026-10-31 User: captions were named after what the partner talked about and nothing of it happened on screen
  (Vice City ep1: "kaksi samaa tyyppiä puhelimessa", "tässäkin vaihtuu värit", "Candy Sachsilla", "sun autotalli",
  "sä et oo niin pitkällä pelissä"). Mouth-motion speaker labels had all five as host. Frames at the caption times
  settled it (hotel room, steady-colour yacht cutscene, a tank). Rule: verify every doubtful caption against the frame.
- 2026-10-31 User: the chapter names had nothing to do with what happens in the game, only with the talk. Frames at
  every chapter time of Vice City ep1 showed it: "Lentokone keskellä tietä" (no plane anywhere 22:04–22:30, a
  mission-passed screen), "Kaikki tulessa" (a green car driving calmly, no fire), "Pankkiryöstö" (a walk to Diaz's yacht),
  "Pakkosniperi" (the mission retry); the "Mä haluun kuolla" cold open was a mall cutscene. Even the lines the
  frame check of the captions had "verified" earlier were wrong because only the doubtful ones were checked.
  Rule: pull frames at every chapter, caption, cold-open and Short time before `check` and name chapters after the
  frame (mission text, vehicle, place, retry). Now a skill step (3.5).
- 2026-10-31 A cold open of two short hits ("Mä haluun kuolla" 12 s + "Kaikki syttyy" 5 s) reads better than one long one;
  keep each `full` and cut on the punchline.
- 2026-10-31 The draft's liveliness picks (laughs, screams, action) are candidates for the cold open and Shorts, not the
  edit: the curated EDL stayed, the picks only confirmed where the hits were.

- 2026-10-31 User: Short 3 cut off at "mitä täs pelis tapa?". The range ended exactly on Whisper's end time of the
  last word, which was 0.8 s early (voice-band loudness in the VOD showed speech to 34:40.8). Three other `full`
  ranges ended within 0.3 s of a word too. Rule 6.5: ≥ 0.3 s of tail after the last word by the audio; `check` warns.

- 2026-10-31 User: Short 3 ended on a caption "EI SAAKELIS" nobody said. Whisper writes ghost words at quiet segment
  ends ("Ei" 0 s long, "saakelis." stretched over 2.6 s of silence); 328 zero-length and 50 stretched-over-silence
  words in this one VOD. Shorts caption every word, so ghosts get cues. `real_words` (trimming.py) now drops them for
  Short cues and the subtitle file; the trim still sees every word so no cut moves. Rule 8.5.

- 2026-11-04 Session review (user asked where a script should replace Claude's judgement): `proof` now lists subtitle
  suspects (Whisper word confidence, kept by transcribe.py from now on, + libvoikko + rarity in the stream) with a
  second decode; `look` replaces hand-written ffmpeg frame grabs (a fast seek in the last second returns no frame, and
  JPEG out of a limited-range PNG fails); `at` maps episode ↔ VOD time; a patch render re-renders changed Shorts (the
  end-hold change was silently skipped before) and writes a look sheet; lp.py re-execs itself in .venv (system Python
  has no ctranslate2 / CUDA wheels).
- 2026-11-04 User: the Finnish subtitles and captions read "a bit off". `proof` only covered caption lines and Shorts; the
  .fi.srt was raw Whisper + wordFixes. Now `proof` writes the whole text (epN.text.txt, both languages) and render
  needs `proof --read`'s stamp (rule 8.7). GTA 3 co-op ep1: 21 fixes (Dexta ×2, Uzi ×2, cutscenessä, synkkaa ×3,
  co-oppia, hidden package ×2, …); ~15 lines stayed garbled after a second decode ("tahkoomistepariin", "Apachun",
  "Pahattelin…") and were left as heard. Whisper also split hyphen compounds ("Co -op", "IP -osoitetta"): fix_words joins
  them now; Finnish multi-word compounds keep the space ("GTA 3 -co-oppia"), so those need a wordFix.
- 2026-11-04 Co-op with the partner's gameplay: `lp.py frames <slug> <times> --guest` beside the host sheet settled the
  `pov` spans at once (stuck car 36:17, wrecked car 41:46: both payoffs only on the partner's screen). A Short wholly
  inside a `pov` span passes the guest-share check without `onScreen`. Cold-open hits must leave main (5.4), so a joke
  with a later callback (the "tekoäly, synkkaa" bits) keeps the callback in main and the first hit in the cold open.
- 2026-11-04 `[REPEATS]`-free "Hei, hei, hei…" bursts (20 words inside 1 s) are Whisper ghosts too: cut around them,
  the subtitles would print them. Whisper also "translates" English cutscene lines into Finnish ("ambitiivinen naisi"):
  drop those clips, the subtitles would carry the wrong text.
- 2026-11-04 Co-op where the partner's tracks start late (guest offset +29:53): the host talks to the partner from
  the start, but viewers hear one side only. Now built in (RULEBOOK 7.9): a `"notes"` banner with `{from}`/`{until}`,
  added by `draft`, required by `check`, `[NO PARTNER TRACKS]` in the context. 8 s on screen; 3.5 s was too short to read.
  `{from}` came out 5:15, not the 5:17 typed by hand from the lower third: let the build compute times.
- 2026-11-04 Co-op name tags over two cam tracks take turns (5 s each) above the higher cam; the 10 s that takes can
  push a chapter card out (`no chapter card` warning): start the tags after the card.
- 2026-11-04 A Short cut tight before the next word stopped dead (no music under it): Shorts now end on a 1 s held
  frame with a hit, under the call to the full episode.
- 2026-11-04 `see` on spoken captions: 12 of 23 "NOT VISIBLE" were quotes with nothing to show. Captions are now asked
  whether they name something concrete first; talk reads `-- talk, nothing to see`.

## Pipeline

- 2026-10-31 `--patch auto` after removing clips from the start re-renders 100 % of the episode anyway (everything
  shifts); it is the same cost as a full render, so either is fine, but it keeps the Shorts untouched.
- 2026-10-31 Never pipe a render through `grep | tail`: Remotion's error line was filtered away and the failure looked
  silent. Redirect the whole output to a log file in the scratchpad and read that.
- 2026-10-31 Old VODs (ingested before `events.json`/`motion.npz` existed) ingest the extras with `ingest` again; the
  transcript is not touched, so existing EDL word times stay valid.
- 2026-10-31 `lp.py retention` needs the YouTube Analytics API enabled in the Google Cloud project and one
  `youtube_mcp.py auth` with the new scope; until then it says to run auth again.

- 2026-10-31 Tried to make the co-op speaker labels reliable; nothing beat the mouth-motion labels, and none is good:
  YAMNet embeddings and a WeSpeaker CAM++ speaker model (sherpa-onnx) cluster the mixed stream audio by game noise,
  not by voice (both voices in one track, cross-validated agreement with mouth labels at chance); mouth motion
  correlated with the speech envelope decides half the lines and is no more consistent; lower-face/upper-face motion
  ratio agrees 84 % with the plain mouth motion. And the streamer watches the partner's stream, so a line about the
  partner's game can be the streamer's own: speaker identity can't catch it. The frame check is the detector.
- 2026-10-31 Building a scratch EDL for the same vod/episode overwrites `work/<slug>/epN.props.json` while a patch
  render may still be launching pieces from it. Never build another EDL of an episode that is rendering.

- 2026-10-31 User: audio out of sync after 5:55. Two patches in a row: the first's concat drifted timestamps by fractions
  of a frame at each seam, the second seeked by computed time into that file, missed the keyframes and stream-copied
  pre-roll frames with squashed timestamps (video 819.8 s for 50590 frames, audio 843.2 s). Fixed by seeking with the
  keyframe's own pts, explicit piece durations in the concat list, and `sync_error` rejecting any output whose frame
  timestamps don't equal index / fps. Rule: never trust a splice; measure the clocks of every file before installing it.

- 2026-10-31 The sync gate caught its first real one: a 100 % patch came out 43 ms late on the picture. The Remotion
  piece's own AAC track starts 2048 samples early (encoder priming), the concat demuxer takes that as the file's start
  and shifts the video by it. Pieces are now video-only before concat. Note the cost: the rejected render was 20 min of
  work thrown away, so a new splice path is worth a 20 s `-t 20` mux test first.
- 2026-10-31 A chapter whose VOD time lies inside a cold-open range lands at the cold open (output 0:02) and is
  dropped by the 10 s rule without a word; `check` now warns. Put such chapters just past the cold open's range.

- 2026-10-31 Web research on AI editing for the pipeline is in `ROADMAP.md` (candidates with the deciding test each);
  the platform facts went into the rulebook (1.2 Studio-only items, 15.1 Shorts up to 3 min) and the craft into 6.8–6.9.
- 2026-10-31 `lp.py see` built (skill step 3.5, rule 7.2): Gemma 4 12B through Ollama reads 4 frames per item in ~2 s; the
  old talk-based Vice City ep1 cut got 17 of 34 labels rejected, among them the fire ("no fire in any frame"), the plane
  ("mission passed screen, no plane"), the Banshee (a tank) and the garbage truck chapter (taxi and SUV); the remade cut
  got 14 of 21 confirmed and 3 flagged, two of them Finnish quotes it couldn't translate. Its scene lines are reliable, the
  verdict on colloquial Finnish is not ("Mä oon liekeissä" → "I am awesome"); hence the quoted reading on every verdict.
  `qwen2.5vl:7b` produced token salad on Ollama 0.32 (100 % GPU, any image size): don't retry it there.
- 2026-11-01 A Finnish fine-tune as `proof`'s second decoder is disproved: `GAIK-project/whisper-large-v3-fi-dialects`
  (converted with `ct2-transformers-converter` after adding the base model's `preprocessor_config.json`, which the repo lacks)
  on Vice City ep2 found "Jes, haulikko" and "Sairaalassa" that large-v3 missed, but writes standard Finnish for colloquial
  speech ("mä" → "minä", "kaks" → "kaksi", "kuollu" → "kuollut") and invents words ("kissinko" for "sinko", "hoopaita" for
  "HP:tä"), so the Short-cue `??` list tripled with false hits. Its training references are standardised transcripts; the
  same goes for the Common Voice fine-tunes. Captions need verbatim colloquial words, so the second pass stays large-v3.
- 2026-11-01 Vice City ep3 (first episode with `see`): a scratch EDL of 40 s `coldOpen` windows run through `see` gives a text
  sweep of the whole part (57 windows, ~1 min) that found the story (first failed taxi attempt, the reload at 100:32, the boat
  on the street, the jumbo jet) before any image was read; three frame sheets then settled the labels. `see` on the real
  EDL flagged 11 of 29: real catches were a fire truck never on the streamer's screen (caption and chapter dropped), a
  woman named in a caption with no woman in frame, "MINIKANI!" over an ambulance; the rest were quotes (`??`) or the model
  missing a subtitle it had itself transcribed. Read the scene line before trusting a `!!`.
- 2026-11-01 `proof` with a caption spanning two transcript segments flags the second segment's words ("PLEASE!"): captions
  are one segment. Whisper standardises colloquial speech in the transcript ("Tämä", "minä", "olen") while the second
  pass hears "Tää", "mä", "oon": map them in `wordFixes` and write captions as spoken. `proof` now counts a `wordFixes`
  value as heard ("rajekka" → "rekka").
- 2026-11-01 A laugh right after a sentence became a 1.2 s ghost word ("Jani") that `check` treated as the next word;
  the loudness map showed silence from 0.1 s after the real last word. GHOST_LONG lowered to 1.0 s so such words leave
  the cues; end the range 0.3 s after the ghost's end to silence the warning. Rule 11.1 bit again at 13 min: 8 chapters
  → 5 after `check`'s spacing warnings; a 13 min episode has 4–6.
- 2026-11-01 User: "reschedule all optimally". Rule used: one Short every day at 17:00 without gaps, an episode's first Short
  on the episode's own day an hour after it (the FULL EPISODE call sends viewers to the fresh upload), the rest on the days
  after, newest episode's Shorts first and the oldest episode's as fillers; a series takes a weekday another series has
  finished with (Vice City ep3 on Kaaosmodi's free Monday). Studio shows an upload as "draft" when its dialog was closed
  before the Visibility page; the API can't see it, and an explicit private + publishAt clears it.
- 2026-11-01 User asked whether YouTube details are up to date: they match the uploads, but the local description, en.json
  and srt of all four Kaaosmodi episodes were rewritten on 31.10 16:05 by a build with the newer trimmer (chapters 2–3 min
  later than the 27.10 renders on YouTube). Any build rewrites `out/` text files even when the mp4 is older; `publish` now
  refuses when the out mp4's length differs from the current build's timeline, so stale text can't be pushed.
- 2026-11-01 User asked for better episode titles: rule 14.1 now adds a hook before the series name ("Rouva Dawson ajaa
  tankkia – GTA Vice City Randomizer osa 3") in `youtubeTitle` / `en.youtubeTitle`; `output` stays the file name. The seven
  live episodes were retitled through the API. Measure the effect with Test & Compare on one episode (hook-first vs series-first).
- 2026-11-01 Ollama keeps the vision model on the GPU for minutes after `see`; Whisper then fails with CUDA out of memory.
  `see` now unloads it (`keep_alive: 0`) when done. Another GPU tenant (an image server holding 7 GB) leaves ~9 GB: enough.
- 2026-10-31 Publishing: `playlistItems.insert` right after creating a playlist answers 409 SERVICE_UNAVAILABLE for a
  while (now retried 5× with growing waits). Same-length Shorts (two of 22 s) could swap by the ±1 s match; the matcher
  now prefers the upload whose Studio title is the file name. Channel slots: episodes 16:00, Shorts 17:00 Finnish time,
  one Short a day; a new series goes on the free weekday between the running series' days (Kaaosmodi Mon/Fri → Wed).

- 2026-11-04 Separate co-op recordings as tracks (`assemble` + `prep`): a lavfi `color=black@0` base negotiates to
  yuv420p and silently drops the matte's alpha; put `,format=yuva420p` inside the lavfi source string. An overlay input
  that outlives its matte hangs the encode: bound every source with `-t (T - delay)/k + 1`. Test a new track path on 20 s
  first (23 s incl. matting start-up). Prep of a 43 min part: both webcams matted in parallel on the 4080 (~20 min),
  then four tracks (host 8.7 GB, guest 3.9 GB, VP9 alpha cams 0.7/0.1 GB) in ~10 min more.
- 2026-11-04 The first `check` still after a fresh prep timed out (28 s delayRender on the 8.7 GB host track); the same
  frame rendered in 6 s on its own and the re-run passed: a cold page cache, not a bug.
- 2026-11-04 Osa 1 Shorts 2–4: a phrase wordFix ("itsepäin toisin" → "itsepähän toit") made one word entry show as two
  words, so a cue had 5 words and 4 timings and Remotion died on "Frame NaN is not finite" (spring in Kinetic.tsx). Bisect
  a failing Short with single `remotion still --frame=N`. `fix_words` now splits a fix into one timed word per shown word,
  and the extra words are marked `glued` so they stay on the cue with the first word. A cue that ran into a big caption
  showed the same words twice; the dedupe now tests overlap. Short 3's guest-heavy talk was kept with `onScreen` after a
  frame check (8-Ball's hands are on screen).
- 2026-11-04 Finnish speller: `libvoikko` is in the repos; `voikko-fi` is AUR-only and needs `foma`, which is AUR-only
  too. Install the prebuilt dictionary instead: puimula.org `voikko-snapshot-v5/dict.zip` unzipped into `~/.voikko`.
  On Osa 1 it flagged 38 subtitle cues, mostly spoken Finnish (meitsi, löytäny, tiiän) and English terms, and 3 real
  fixes (tahkoomistepariin, tiinni, 8-ballin).
- 2026-11-04 User: Short 2 showed Dexta's gameplay (a "pov" span) under Arkkis's webcam. Shorts now put the webcam of
  whoever's view is on screen in the slot (guestcam inside pov spans, the hold too); Shorts 1 and 2 re-rendered. Any
  hand-run `remotion still` needs `TMPDIR=.tmp` like `lp.py` sets: without it Remotion copied the 8.7 GB host track into
  the /tmp RAM disk and failed with ENOSPC.

## Measurements

- 2026-11-04 GTA 3 Co-op ep1 (first two-player pov episode, separate tracks): 11.6 min from a 43.2 min part, −14.4 LUFS,
  57 clips, 12 captions, 6 chapters, 2 pov spans, 1 Short of 11.5 s inside a pov span. Prep ~30 min (matting + tracks),
  render ~25 min for the episode + ~1 min for the Short.
- 2026-10-31 Vice City ep1 remake: 13.6 min from 3.5 h VOD, −14.3 LUFS, 56 clips (1 under 2 s), 11 captions, 9
  chapters, 3 Shorts of 19–21 s after the frame check (it removed 2 chapters, 7 captions, both cold-open hits and 3
  Shorts of the talk-based cut). The new trim keeps ~18 % more than the old one at the same ranges.

- 2026-11-01 Vice City ep3: 13.3 min from a 37.7 min part, −14.5 LUFS, 95 clips (5 under 2 s), 13 captions, 5 chapters,
  4 Shorts of 10–21 s; render 25 min for the episode plus 3 min for the Shorts. Editing in this (long) session: text sweep
  with `see`, 3 frame sheets, `see` on the EDL, `proof`, 3 × `check`, 2 × `script`.
- 2026-10-31 Vice City ep2 remake: the frame sweep (every 30 s, 3 sheets) before reading captions settled the episode in
  one pass: the old talk-based cut's "Tehtävä läpi" was the partner's pass, "Lentokone sairaalalla" had no plane in any frame
  69:31–69:52, the Red Dead line and "Kuka ampui?" sat over a calm drive. Rule: sweep the whole part at 30 s first, then
  close frames (2–3 s apart) only around the candidates; ~6 sheets for a 36 min part.
- 2026-10-31 Chapter cards wait for a caption that starts at the same time (card 2.5–3 s later), so a chapter placed on a
  captioned line lands on the next clip. Put the chapter on the reveal and drop the caption there, or place the chapter 3 s earlier.
- 2026-10-31 A main range ending at Whisper's word boundary where the next word starts at the same instant
  ("pamppuja"[…33.54] "Mun"[33.54…]) snaps to include the next word; end such ranges 0.2 s inside the last wanted word.
- 2026-10-31 A `[?]`/`[GUEST]` line about a thing on the streamer's screen (the rooftop rocket pickup, the 130 shells) is a
  mislabel; the frame decides, but it still can't be captioned (check refuses GUEST), so the Short carries it in `onScreen`.
- 2026-10-31 Thumbnail: a subject in the frame's centre (the burning character at x 51 %) ends up behind the face cut-out with
  the default origin, and `bgOrigin` "100% 100%" moves it left but keeps the stream webcam. Zoom 1.5 with origin "100% 16%"
  put it bottom-left under the hook text and pushed the webcam off the bottom (webcam top 72 % → 0.16 + 0.56 × 1.5 = 1.0).
  Look at the rendered jpg every time: the hook must show the thing it names (7.1).
- 2026-10-31 User: chapter ("Luku") titles described only the frame at the chapter time ("Paloauto", "Sairaalan pickup"),
  not the chapter. A label covers the whole span to the next chapter, in visible things ("Paloauto ja yöajelu",
  "Pickup-kierros"); write it after reading the script's lines between the two chapters. Rule 11.2 updated; ep2 relabelled and patched.
- 2026-10-31 User: too many chapters (13 in 9.9 min, two inside a minute). A chapter is a 2–3 min story beat; ep2 cut to 6.
  `check` now warns when chapters are under 90 s apart; rule 11.1 rewritten.
- 2026-10-31 User asked for caption proof-reading before rendering: `lp.py proof` (second Whisper decode per caption line and
  per Short, flags unheard words) and `"wordFixes"` in the EDL for the Short cues and subtitles. Skill step 3.7, rule 8.6.
- 2026-10-31 User: the recap and the cold open mixed up. The recap now has its own look (saturate 0.45, letterbox 90 px) and exits
  through 18 frames of fade and 30 frames of black (build_edit RECAP_FADE_F/RECAP_GAP_F, LetsPlay.tsx `fade`). Rule 5.3b.
- 2026-11-04 User: "I wasn't streaming that session, only Dexta was." The GTA 3 Co-op ep1 lower third ("Twitch-striimi"),
  descriptions ("striimin puolivälistä", "mid-stream") and every Short's "TWITCH-STRIIMISTÄ" label claimed the user's own
  stream. Ask whose stream it was before writing any of them; the EDL's `"fromStream"` now overrides the Shorts label. Rule 14.5.
- 2026-11-04 New-rules comparison cut of GTA 3 Co-op ep1: 8.2 min vs 11.6 min. It drops the long talk blocks (21:46–22:47,
  24:54–25:35, 27:48–28:04, 35:09–36:02, 42:32–43:00), the stunt nobody can see at 21:10 and the recap-style ending, and
  ends on the 41:57 crash. Two EDLs of one episode share `work/<vod>/ep<N>.*` (props, proof stamp): back up and restore them
  around the second render, and re-stamp the proof for each one.
- 2026-11-04 User: Shorts 1–2 said "ARKKIS / CO-OP-SESSIOSTA" over Dexta's game and webcam. The Shorts label now follows
  the pov spans like the webcam slot: the partner's lower-third tag ("DEXTA / DEXTAN PELIT") while their view is on screen.
- 2026-11-04 User adopted the "new rules" after comparing cuts: they are now RULEBOOK 4.7–4.8, 5.1–5.2, 5.8–5.9, 6.6, 6.9,
  15.0–15.1, 15.4–15.5, 15.9, 17.4 (picture-first Shorts and cold open, ranked candidates, no inside jokes in Shorts,
  ~30 s intro, ending on a payoff, cut talk without payoff, retention decides). `build` warns on an intro over 35 s and on
  a cold-open hit that isn't a Short without a `"notShorts"` reason. GTA 3 Co-op Osa 1 is now the 8.2 min cut with 4
  Shorts; the old cut's outputs are in `out/GTA 3 Co-op/vanhat säännöt/`, its EDL in `work/gta3-coop-2026-11-03/ep1-oldrules.edl.json`.
- 2026-11-04 The 8.2 min GTA 3 Co-op Osa 1 failed the sync gate: audio 489.40 s vs video 489.28 s, while the raw mix was
  489.30 s. Mastering (acompressor + loudnorm + AAC) had stretched it by 0.1 s. The master filter now ends with
  `atrim=end=<timeline length>` (`master(e)` in lp.py) for full renders and patches.
- 2026-11-04 GTA 3 Co-op Osa 1 had a ~0.2 s flash of Arkkis's view at 5:14: the pov span ended at 36:37.3, 0.2 s before
  its range ended at 36:37.5. `build` now refuses a pov edge within 1 s inside a range (`POV_SLIVER_S`), and
  `render --patch` now re-renders clips whose pov span changed (it only diffed timing and props before).
- 2026-11-04 GTA 3 Co-op Osa 1 upload details: the hook names what's new ("Tein GTA 3:een kaksinpelin" / "I made GTA 3 a
  two-player game"), with search tags in both languages. Short titles now end with the series ("<title> – GTA 3 Co-op
  #shorts"), so a Short found on its own still says what game it is. Don't claim "the first GTA 3 co-op": Liberty
  Unleashed (GTA III multiplayer, since about 2009) has YouTube footage. Story co-op with shared cutscenes is a defensible
  angle, but it's unverified as a first.
- 2026-11-04 The user's call: Osa 1 claims "Maailman ensimmäinen GTA 3 co-op" / "The world's first GTA 3 co-op" in the title. The
  description hedges it ("tietääksemme" / "as far as we know"), because CoopIII (GitHub noxxUY/CoopIII) is a GTA III story
  co-op still in development.
- 2026-11-04 The user said to schedule GTA 3 Co-op Osa 1 as soon as possible. It went to the next channel slot: the episode at
  14:00Z on 5.11, then its Shorts at 15:00Z on 5.–8.11. The queued Shorts moved +4 days, keeping one a day at 15:00Z;
  the episodes didn't move. The Data/Analytics API has no hour-of-day audience report, so the slot times stay the
  channel's own. Partner credit in descriptions and Shorts uses the handle (`@DextanPelit`) so it links to their channel.
- 2026-11-04 GTA 3 Co-op: English subtitles were done by hand and uploaded to Osa 1 and its 4 Shorts. The episode's track
  translates `<output>.fi.srt` cue for cue (`<output>.en.srt`). The Shorts' tracks come from their caption timing,
  merged into sentences (`shorts/<name>.en.srt`). The pipeline itself still uploads only `<language>.srt`.
- 2026-11-05 `wordFixes` keys are matched on bare words, so a key with punctuation inside it ("Ville, tonne päälle")
  never matches and fails silently. Write keys without punctuation. Zero-length Whisper words are dropped before the
  fixes run, so a fix that has to bring a dropped word back puts it in the value ("mä luottanut" → "mä oon luottanut").
- 2026-11-05 GTA 3 Co-op Osa 2: the guest's lower third (second half of `lowerThird.dur`) ran into the first caption, 6 s
  later. Put the lower third where no caption falls within ~10 s of it.

## Channel stats

- YouTube numbers (views, subscribers, retention) are private: they live in `work/channel-stats.md`, which is
  gitignored. Read it with this file; write new numbers there, and only the lesson (no numbers) here or in the rulebook.
