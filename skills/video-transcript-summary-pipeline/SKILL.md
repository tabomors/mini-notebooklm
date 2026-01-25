---
name: video-transcript-summary-pipeline
description: Orchestrate transcript retrieval and summarization for videos. Use when the user provides a YouTube link or attaches a local video file and wants a transcript summary.
---

# Video Transcript Summary Pipeline

## Workflow

1. Detect the input type.
   - If the user provides a YouTube link, use `skills/youtube-auto-subs/SKILL.md` to download the transcript.
   - If the user attaches a local video file, use `skills/local-video-transcript/SKILL.md` to generate the transcript.
2. After a transcript is obtained, use `skills/video-transcript-summary/SKILL.md` to create the summary.

## Notes

- If both a YouTube link and a local video file are provided, ask which source to use.
- If the user only wants a transcript without a summary, confirm whether to proceed with the summary step.
