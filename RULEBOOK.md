# Rulebook

Every rule for turning a stream VOD into an episode: cutting, structure, captions, chapters, zooms, Shorts, thumbnail,
verification. `.claude/skills/letsplay/SKILL.md` says *how* (commands, schema, steps); this file says *what is allowed*.
Read it whole before the first editorial decision of a run. `LEARNINGS.md` collects new rules as they are learned; a
learning that has held for a few episodes is written here and removed there. When a rule and the code disagree, the
rule wins: fix the code (`check` should refuse what the rulebook forbids).

## 1. Who decides

- 1.1 The editor (Claude) makes every editorial decision and delivers finished episodes; the user watches the result.
- 1.2 The user owns: uploading in YouTube Studio, end screens, game titles, the Short's "related video" link to the
  full episode, thumbnail/title tests (Test & Compare), and every publish/schedule go-ahead; none of these is in the
  Data API. `lp.py publish --at/--now` and any YouTube visibility change only after the user's explicit go for that video.
- 1.3 Never upload video files. Never delete an old upload before the user confirms.

## 2. Hard rules

- 2.1 Never upscale raw material. Sources stay at the VOD's native size and episodes render at that size; zoom
  punch-ins are an editorial effect and fine.
- 2.2 Nothing in the stream overlay is blurred (vote list, stats, chat, follower goal, FPS, alert popups).
- 2.3 Captions are verbatim to the spoken words and uncensored: swearing stays, matching the audio. Never paraphrase.
- 2.4 A caption's words must exist in the current transcript (re-transcribing a VOD can invalidate old captions).
- 2.5 Every render or patch is installed only after the clock check passes (exact frame count, every frame's timestamp
  equal to its index / fps, audio as long as the video). A failing file is deleted and the old one kept.
- 2.6 Original recordings (VODs, gameplay and webcam files, the user's Kdenlive project) are read-only: never written,
  re-encoded in place, renamed, moved or deleted, and no tool writes into their folder. Everything derived goes to
  `footage/`, `work/`, `public/`, `out/`.

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
- 4.7 Every kept range earns its place: something happens on screen, or the talk has a payoff (a laugh, a reaction, a
  punchline). Talk with nothing on screen and no payoff is cut, not decorated with captions or zooms. Banter with the
  partner, the mod and the in-jokes belong in the episode (unlike Shorts, 15.4) when they pay off.
- 4.8 Repeats go: a second package pickup, crash or "where is it" search stays only when something different happens.

## 5. Structure

The episode runs: cold open → title card → intro → (recap) → main → freeze ("JATKUU...") → end screen.

- 5.1 Cold open: 2–4 of the episode's best hits, 12–20 s in all, each kept `full`, each cut on its punchline. Two
  short hits read better than one long one. They are picked like Shorts (15.0, 15.4): the first frame shows something
  happening, the hit works with the sound off, the payoff is visible, and no inside jokes (the mod, the editing, the
  channel). The draft's candidates are a start, not the answer.
- 5.1b Title card: 1.5 s, a stinger, not a pause. Retention: viewers left on a longer blurred card right after the
  cold open.
- 5.2 Intro: about 20 s, on screen something is happening (driving, a mission starting, an effect firing) while the
  streamer says what this is (the mod, the goal, the partner) in a sentence or two. No talk about other streams or
  past games, no mod explanation over a static shot: the rest of the explanation goes into main over action, where it
  is relevant. Retention: viewers left during exactly that talk.
  `build` warns over 25 s.
- 5.3 Recap (episode 2+): `"recap": "auto"` replays the previous cold open under a "previously" tag; pick other ranges
  when the story needs a different reminder; drop it when the episodes don't connect.
- 5.3b The recap is set apart from the episode: graded flat (desaturated, darker) under letterbox bars with the
  "previously" tag, and it exits on a 0.3 s fade to black plus 0.5 s of black and silence before the cold open's whoosh.
  User: without that the two blurred together (Vice City ep2).
- 5.4 The same location or moment never appears in both cold open/intro/recap and main: remove it from `main`.
  Exception: when removing it leaves main jumping in and out of the moment (cuts or `pov` switches seconds apart,
  6.10), keep main continuous through it and accept the repeat, or pick another cold open. User: the fast cuts at
  3:48 of RE6 Osa 7 (grab cut out of main between two view switches) were confusing.
- 5.5 Main stays chronological and never goes back inside the intro's span (no `main` range between the first intro
  range's start and the last one's end; `check` refuses them). An intro pulled forward from later in the VOD is fine
  as long as nothing main then shows a menu or cutscene the viewer has just seen.
- 5.6 Main's first clip is the new game's first real moment, not a menu, loading screen or a cutscene already shown.
- 5.7 A chapter whose time lies inside a cold-open range lands in the cold open and is dropped: put it just past
  that range.
- 5.8 The ending lands on a payoff: main's last range ends on the best late moment or a cliffhanger, then the freeze.
  Not wherever the time ran out (Osa 1 ends on the 41:57 crash, not on talk).
- 5.9 One through-line per episode with visible progress ("paketit 12 → 20", the next mission reached), so the chapters
  build toward something; cut what doesn't serve it before cutting what does.

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
- 6.6 Moments are scored, not just read: for each candidate stretch, weigh the draft's liveliness picks (laughs,
  screams, action), the audio peaks and a frame sheet (`lp.py frames`). Keep the top, cut the bottom; the transcript
  alone favours talk. The same ranking picks the cold open and Shorts (15.0).
- 6.7 Never build another EDL of an episode that is rendering (it overwrites the props the render reads).
- 6.8 A reveal keeps the quiet before it: don't trim the half second of silence ahead of the thing the viewer is about to
  see, and don't put a sound effect, caption or banner on it (the chapter card goes on the reveal, 11.3).
- 6.9 A minute of main with no cut, caption, zoom or banner is a flag in the script review: either something visible
  carries it (`[ACTION]`) or it goes. Cut first (4.7); check the series' retention files before keeping such a stretch,
  and don't fill it with zooms either: stacked zooms, shakes and cuts bury the moment.
- 6.10 No cluster of cuts: two cuts (range cuts, `pov` switches, or one of each) are never less than ~8 s apart. A
  moment shown in quick pieces leaves the viewer not knowing what happened: merge the ranges, widen or join the `pov`
  spans, or drop the moment. Check the script for `>>`/`<<` and `|` lines close together (RE6 Osa 7, user).
- 6.11 A death, game-over or mission-failed screen is shown only after the death or failure itself is on screen in
  the same stretch, never alone after a cut, in a cold open or in a Short; the exception is talk over it that
  is a payoff on its own. Without the cause the screen means nothing (RE6 Osa 7's "Mission Failed" cold open, user).

## 7. What is on screen decides (co-op and every named thing)

- 7.1 A caption, chapter label, cold-open hit, Short title, thumbnail hook or description line may only name something
  the viewer sees. Talk alone never names anything.
- 7.2 Before `check`, run `lp.py see` (a local vision model describes the frames across every chapter span, caption,
  cold-open hit, Short and the thumbnail and says whether each label names something it sees) and read its file whole;
  pull frames (`lp.py frames`) for anything flagged that the scene line doesn't settle, and for anything it didn't look
  at. If the named thing (plane, fire, bank, sniper, motorbike…) is not in the game frame, drop it and name the chapter
  after what the frames show: the mission text, the vehicle, the place, the retry, the on-screen result. The model's
  verdict is a hint (it mistranslates colloquial Finnish and calls quotes abstract); its scene lines are the evidence.
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
- 7.8 Separate recordings with the partner's gameplay (`assemble --guest-game`) give two views on one clock:
  yours and theirs, each its own track (`prep`: `-epN.mp4`, `-epN-guest.mp4`; the webcams and mics are separate tracks
  drawn over either; `footage/<slug>-guest.mp4` is the reference to look at). Stay in the streamer's
  view; switch with `"pov": [[a, b], ...]` (VOD times) when the moment happens on the partner's screen: their kill, crash,
  find, death, or the thing both are reacting to. Look before switching (`lp.py frames <slug> <times> --guest`): the
  payoff must be in their frame. A switch holds at least ~8 s and starts on a beat (a sentence start, the action's
  start), never for a short reply or a remark. A span edge sits on or past a range edge, never within 1 s inside it
  (the other view flashes up just before the cut; `build` refuses it). Inside a `pov` span 7.3–7.5 don't apply (their game is on screen):
  their lines may get captions, cold-open hits and Shorts; `see` checks labels against the view shown. Mic-energy
  labels (`speakers` with no boxes) are reliable, unlike 7.6.
- 7.9 The partner's tracks may start late or end early (they joined the recording mid-stream) while the partner is in the
  call throughout: there the viewer hears one side of a conversation. Say so on screen: a `"notes"` banner at the first
  gameplay clip ("Puhun Dextan kanssa" / "Hänen mikkinsä ja pelikuvansa mukana vasta {from} alkaen", 8 s; `{from}` and
  `{until}` become the episode times where the tracks start and end, in the descriptions too), plus one line in each description. `draft` adds it,
  `check` refuses an episode without it, the context marks the stretch `[NO PARTNER TRACKS]`. Shorts from that stretch:
  only moments that don't answer the unheard partner.

## 8. Captions

- 8.1 Verbatim and uncensored (2.3), words present in the transcript (2.4), on something visible (7.1).
- 8.2 Only the best lines, about 2 per minute at most. Overlapping captions stack automatically.
- 8.3 Not on `[GUEST]` or `[TO GUEST]` lines (7.4, 7.5).
- 8.4 A caption may sit in the cold open; the same line then shows there and in main.
- 8.4b Every caption and Short cue makes sense to a viewer who sees only that frame and line: it names or reacts to what is
  on screen right then, a joke has its setup in view, a callback has its first half in the episode. A bare exclamation
  ("OI OI OI OI"), a remark on something not shown ("SIVIILI KUOLI" over an empty tunnel) or a line that needs the
  series to get ("LAPPULIISA VASTAAN SUPERSOTILAS") goes. A Short starts on its setup line ("Tää alkaa viskelee näitä
  granaatteja" before the grenades), not after it. A cue that reads as nonsense is a mishearing to fix, never to ship
  ("vetää turvaa" was "vetää turpaan"). User, RE6 Osa 7.
  Captions and cues hold real words: a mispronounced or mangled word is written as the word it stands for
  ("monsteli" → "MONSTERI", in the caption and through `"wordFixes"` for the cues), even when every decode hears it as
  said. Spoken forms stay spoken (mä, tää, ollu, tommonen, kyl). User, RE6 Osa 7.
- 8.4c Separate recordings keep each mic on its own track in the source (OBS multitrack): decode a garbled line from
  that speaker's track alone (faster-whisper on `-map 0:a:<mic>` for the window). Without the other voice and the game
  under it, it settles what the mixed track can't (RE6 Osa 7: six Short cues and two captions fixed that way).
- 8.6 Proof-read before `check`: `lp.py proof` decodes every caption's line and every Short a second time (same model,
  each window alone without stream context; Finnish fine-tunes were tried and standardise the colloquial words the
  captions need, see `LEARNINGS.md`) and flags caption words heard in neither decode and Short words the second pass
  doesn't hear. Whisper garbles colloquial words
  ("Taviraalassa", "päsäpallomaailma"); the caption text is corrected by hand and the Short cues and subtitles through
  `"wordFixes"` in the EDL. Nothing renders with an unread proof file.
- 8.7 Every episode's whole text is proof-read, in both languages, and fixed: `lp.py proof` also writes
  `work/<vod>/epN.text.txt` (on-screen text, captions, cards, notes, the Shorts' cues, both descriptions and titles, and
  every subtitle cue). Read it top to bottom: mishearings ("Teksto" for Dexta, "utsi" for Uzi), misspellings,
  English loanwords spelt the way a Finn writes them ("cutscenessä", "co-oppia", "hidden packagea") and stiff
  translation. Captions and the translation are fixed in the EDL; subtitles and Short cues through `"wordFixes"`, whose
  keys may be several words in a row when the heard word is right elsewhere ("heti seikkailee" → "Dexta seikkailee";
  "heti" alone is a real word). `proof` lists the subtitle suspects (Whisper confidence < 0.45, or rejected by the
  Finnish speller and said at most twice in the stream) with a second decode each; the read still covers every line.
  A line that stays garbled after a second decode is left as heard, never guessed.
  Then `lp.py proof <edl> --read` stamps the text; `render` and `shorts` refuse a build whose text changed since.
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

- 11.1 First at 0:00, one per real story beat of about 2–3 minutes: a 10 min episode has 4–6 chapters, a 25 min one
  8–12. Two cards inside a minute is too many; `check` warns under 90 s (the YouTube minimum of 10 s is not the measure).
- 11.2 A label sums up the whole chapter, from its time to the next chapter's, in things the viewer sees across it:
  the places, vehicles, retries and results of that span ("Rautakauppa ja skootteri", "Kojusta pihalle"), never only
  the frame at the chapter time ("Paloauto" for a span that is mostly a night drive) and never the topic of the talk (7.1, 7.2).
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

- 14.1 File name and `output`: series name and part ("GTA Vice City Randomizer - Osa 3"). The YouTube title
  (`youtubeTitle`, and `youtubeTitle` inside the translation block) adds a hook in front: "<hook> – <series> osa N",
  under 60 characters, the hook naming something visible in the episode (7.1) and different from the thumbnail text,
  no spoiler of a payoff. Speedruns put the final time in the hook. Prefer a claim or stakes the viewer can't get
  elsewhere ("Maailman ensimmäinen GTA 3 co-op") or concrete visible effects ("Aimbot päällä ja rahaa sataa") over a
  list of odd moments; every part of a series gets a hook as strong as part 1's.
- 14.2 Description: two or three sentences on what happens, naming only things the viewer sees (7.1), then one line on
  what the mod is; chapters and credits are appended by the build.
- 14.3 The `translation` block mirrors title, description and chapters in the configured language.
- 14.4 Tags: game, mod, series, co-op partner, language, channel names.
- 14.5 Say "stream" only when it was the user's own stream. A session recorded locally while only the partner
  streamed has no "Twitch stream" in the lower third, description or Shorts label (`"fromStream"` in the EDL).
- 14.6 No subtitle track for Finnish: config `"subtitles": false` makes render write no `.srt` and publish upload
  none (user, RE6 Osa 7). Short cues and on-screen captions are unaffected.

## 15. Shorts

- 15.0 Rank before picking. Every candidate gets a frame sheet (its first frame, the payoff frame) and its audio peak,
  and is scored on three questions: does the first frame show something happening, does it work with the sound off,
  is there a payoff a stranger gets? Pick from the top. Every cold-open hit and every big caption on something seen is a
  candidate by default; one left out gets its reason in `"notShorts"` (`{"<hit start>": "why"}`; `build` warns otherwise).
- 15.1 Up to 4 per episode, fewer as the expected outcome: one strong Short beats three padded ones; 8–60 s, best 15–25 s (shorter ones
  held viewers better). YouTube classifies any
  vertical video up to 3 min as a Short, so a two-range setup-and-payoff Short may run past 60 s when both halves earn it.
- 15.2 One continuous VOD stretch, or two stretches (`ranges`, one internal cut on a sentence end) when the setup and
  the payoff are apart.
- 15.3 The first second has to grab: start on the action or the reaction, not on a lead-in sentence.
- 15.4 Picture first: the payoff is visible (a crash, a fall, a glitch, a chase) and works without context. Talk alone
  isn't a Short; a quotable line counts only when the screen shows what it is about. No inside jokes: a moment that
  needs the channel, the mod or the editing to be funny stays in the episode.
- 15.5 Co-op: the streamer's own moment, or the partner's inside a `pov` span. `check` refuses a Short where `[GUEST]`
  lines are over a third of the talking, unless `"onScreen"` says what the streamer's screen shows, written only after
  looking at the frames, and only when the partner is reacting to something the streamer visibly does (their
  explosion, their crash). The partner's story about their own game is not a Short. The webcam slot and the label
  under it follow the view (the partner's cam and lower-third tag inside `pov` spans).
- 15.6 `title`: 2–4 words in caps that tease the payoff without giving it away. On YouTube it always reads
  "<Title> – <series> #shorts" (`publish` writes it) so Shorts viewers can find the episodes.
- 15.7 `cropX` moves the game window when the action is off-centre; check with `frames`.
- 15.8 Shorts stay private until the user's go; post them between episodes. The description links the full episode
  (`publish` writes it); the Studio-only "related video" link is the user's (1.2): remind them per Short.
- 15.9 Once Shorts are public, read `video_retention` per Short and write in `LEARNINGS.md` (the numbers in gitignored `work/channel-stats.md`) what held viewers at the first
  second and at the payoff; tune the 15.0 scoring against those numbers, not against taste.

## 16. Review and verification

- 16.1 `proof` read and its flags resolved, then `check` must pass; fix everything it reports, then read the check grid.
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
- 17.4 Retention decides: once episodes are public, `video_retention` shows where viewers leave. Write the drop-off
  patterns into `LEARNINGS.md`, the numbers into gitignored `work/channel-stats.md` (the repo is public); they override taste in 4.7–4.8, 5.1, 5.8 and 6.6.
