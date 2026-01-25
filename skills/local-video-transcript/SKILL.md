---
name: local-video-transcript
description: Transcribe local audio/video files to plain text and SRT using faster-whisper; use when asked to extract transcripts from local media files or to automate local transcription workflows.
---

# Local Video Transcript

## Use this skill when

- You have a local audio/video file and need a transcript in plain text or SRT.
- You need a repeatable local workflow without external APIs.
- You want to control model size, language, or VAD settings.

## Use the bundled script

- Create a virtual environment in the workspace and install dependencies from `requirements.txt`.
- Run `scripts/transcribe_video.py` with the local file path.
- Output is written as `.txt` and `.srt` in the chosen output directory (default: `transcriptions/`).

Example:

```bash
python3 -m venv .venv
.venv/bin/pip install -r skills/local-video-transcript/requirements.txt
.venv/bin/python skills/local-video-transcript/scripts/transcribe_video.py \
  "path/to/video.mp4" --language ru --model small --vad-filter
```

## Options and defaults

- `--model`: `tiny`, `base`, `small`, `medium`, `large-v3` (default: `small`)
- `--language`: use a language code like `ru` or `en` (default: auto)
- `--device`: `cpu` or `cuda` (default: `cpu`)
- `--compute-type`: `int8`, `int8_float16`, `float16` (default: `int8`)
- `--output-dir`: directory for outputs (default: `transcriptions/`)
- `--output-base`: base filename for outputs (default: input stem)
- `--vad-filter`: enable VAD filtering (default: off)

## Notes

- Prefer `small` or `medium` for better accuracy if runtime allows.
- If the user wants higher accuracy, suggest `--model medium` or `--model large-v3`.
