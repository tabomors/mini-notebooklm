---
name: local-video-transcript
description: Transcribe local audio/video files to plain text and SRT using a local Whisper model by default, with optional OpenAI API support.
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
- Uses a local Whisper model by default; OpenAI API is optional.

Example:

```bash
python -m venv .venv
.venv/bin/pip install -r skills/local-video-transcript/requirements.txt
.venv/bin/python skills/local-video-transcript/scripts/transcribe_video.py \
  "path/to/video.mp4" --language ru --backend local --model small --vad-filter
```

## Options and defaults

- `--model`: `small` for local or `whisper-1` for OpenAI API (default depends on backend)
- `--backend`: `local` or `openai` (default: `local`)
- `--language`: use a language code like `ru` or `en` (default: auto)
- `--output-dir`: directory for outputs (default: `transcriptions/`)
- `--output-base`: base filename for outputs (default: input stem)
- `--vad-filter`: no effect with OpenAI API (kept for compatibility)
- `--no-extract-wav`: skip WAV extraction step (default: extraction on if input is not `.wav`)

## Notes

- OpenAI Whisper API has a 25 MB file limit; compress/split long files if needed.
- WAV extraction requires `ffmpeg` and is used to ensure audio-only input.
