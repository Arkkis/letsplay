# Third-party components

| Component | Used for | License | Notes |
|---|---|---|---|
| [Remotion](https://www.remotion.dev) | rendering episodes, Shorts, thumbnails | [Remotion License](https://www.remotion.dev/license) | Free for individuals, non-profits and companies of up to 3 people; larger companies need a company license. |
| [@remotion/google-fonts](https://www.remotion.dev/docs/google-fonts): Anton, Luckiest Guy, Inter | on-screen text | SIL Open Font License 1.1 (fonts) | Loaded at render time. |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with Whisper large-v3-turbo | transcripts, language detection | MIT | Model downloaded on first use. |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | reading on-screen effect names | Apache-2.0 | |
| [GTA V Chaos Mod (ChaosModV)](https://github.com/gta-chaos-mod/ChaosModV) | effect names (`games/chaosmod/names.json`) | GPL-3.0 | Not shipped: `games/chaosmod/build_names.py` generates the list from the mod's source on your machine. |
| Kevin MacLeod, [incompetech.com](https://incompetech.com) | style music | CC BY 4.0 | Not shipped: `scripts/fetch_music.sh` downloads it; every description credits the tracks used. |
| [Kenney](https://kenney.nl) Impact Sounds, Interface Sounds | sound effects in `public/sfx` (some layered or edited) | CC0 1.0 | |
| [Robust Video Matting](https://github.com/PeterL1n/RobustVideoMatting) (MobileNetV3 fp16 ONNX) | transparent webcam backgrounds (`assemble --cutout`) | GPL-3.0 | Not shipped: `scripts/matte.py` downloads the model to `models/` on first use and runs it with onnxruntime-gpu (MIT) in its own uv environment. |
| ffmpeg | all media processing | LGPL/GPL (your system's build) | Not shipped. |
