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

- 2026-10-31 Publishing: `playlistItems.insert` right after creating a playlist answers 409 SERVICE_UNAVAILABLE for a
  while (now retried 5× with growing waits). Same-length Shorts (two of 22 s) could swap by the ±1 s match; the matcher
  now prefers the upload whose Studio title is the file name. Channel slots: episodes 16:00, Shorts 17:00 Finnish time,
  one Short a day; a new series goes on the free weekday between the running series' days (Kaaosmodi Mon/Fri → Wed).

## Measurements

- 2026-10-31 Vice City ep1 remake: 13.6 min from 3.5 h VOD, −14.3 LUFS, 56 clips (1 under 2 s), 11 captions, 9
  chapters, 3 Shorts of 19–21 s after the frame check (it removed 2 chapters, 7 captions, both cold-open hits and 3
  Shorts of the talk-based cut). The new trim keeps ~18 % more than the old one at the same ranges.
