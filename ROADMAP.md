# Roadmap

Candidate pipeline improvements, researched 2026-10-31 and not built. Each entry: what it would change, the tool, the
caveat, and the test that decides it. A session that builds one moves it to `README.md`/`SKILL.md`; one that disproves
one writes the result in `LEARNINGS.md` and deletes it here. Don't re-research these.

Ordered by expected effect on the edit.

1. **Twitch chat as a liveliness signal.** `draft` ranks moments by loudness, laughs, motion and webcam; chat is unused.
   `TwitchDownloaderCLI chatdownload --id <vod> -o chat.json -E` ([lay295/TwitchDownloader](https://github.com/lay295/TwitchDownloader),
   undocumented Twitch endpoints, may break) gives every message with its VOD offset. Message rate and emote bursts (LUL,
   KEKW, "clip it") per 10 s, shifted back 10–20 s for stream delay and typing, become one more `[CHAT]` line in `context`
   and a term in the cold-open/Shorts score. Test: on a finished episode, do chat peaks land on the chosen cold open and Shorts?

2. **Vocal stem before the audio analysis.** Demucs `htdemucs` two-stem vocals on the VOD audio, then loudness-while-talking,
   laugh/scream events, the rule 6.5 tail check and the ghost-word filter run on the stem, so game explosions stop counting
   as loud talk. Nobody has published results on game audio; NPC dialogue will land in the stem too. Rule 7.7 stands: a
   1 h test on one VOD, not a run on speaker identity. Test: event precision on a 10 min stretch against the context file.

3. **Forced alignment for word times.** Whisper's word ends come early (the 0.8 s "tapa" cut, rule 6.5). WhisperX
   ([m-bain/whisperX](https://github.com/m-bain/whisperx)) re-aligns the transcript with a wav2vec2 model inside VAD
   boundaries; needs a Finnish wav2vec2 (Finnish-NLP XLS-R). New word times invalidate caption matches in existing EDLs
   like a re-transcribe does (rule 2.4). Test: word ends against the voice band on the 20 `full` ranges of a finished episode.

4. **Most-replayed heatmap beside retention.** yt-dlp's `heatmap` field (start, end, intensity 0–1, unofficial, can break:
   [yt-dlp #3888](https://github.com/yt-dlp/yt-dlp/issues/3888)) is the replay graph, the opposite signal from
   `retention`'s drop-offs. Peaks of a published episode are Shorts not yet cut and say which beats get rewatched. Belongs
   in `lp.py retention` output as `[REPLAY]` lines.

5. **Proposed `cropX` for Shorts.** A motion centroid over the Short's range (what
   [clipwright-reframe](https://pypi.org/project/clipwright-reframe/) does) proposes the crop; the editor confirms with
   `frames`. Static per Short, no panning. Saliency tools ([pyautoflip](https://pypi.org/project/pyautoflip/),
   [auto-vertical-reframe](https://github.com/KazKozDev/auto-vertical-reframe)) are face-trained and chase the HUD.

6. **Expression score in `faces`.** [`fer`](https://pypi.org/project/fer) (MIT) gives emotion scores per face; rank
   candidates by expression intensity and sharpness instead of webcam motion alone. Small job.

7. **Thumbnail variants for Test & Compare.** YouTube Studio tests up to 3 thumbnails and a title per video, Studio only.
   `render` could emit 2–3 variants (another face, another hook) next to the thumbnail. Cheap once the planner takes a list.
