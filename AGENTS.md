# Project Notes

This repo contains skills and scripts for generating transcripts and summaries from videos. Outputs live in `transcriptions/` and `summaries/`.

If a user provides a YouTube link or a local video file, use `skills/video-transcript-summary-pipeline/SKILL.md`.

For an entire YouTube channel (channel URL or @handle → all videos, cross-video analysis), use `skills/youtube-channel-analyzer/SKILL.md`. Its outputs live in `channels/<channel>/`.

# Tech notes 

Always use a Python virtual environment (`venv`) for any Python work in this repo. Inside the virtual environment, use `python` (not `python3`).
