---
name: video-transcript-summary-pipeline
description: Orchestrate transcript retrieval and summarization for videos. Use when the user provides a YouTube link or attaches a local video file and wants a transcript summary.
---

# Video Transcript Summary Pipeline

## Workflow

1. Detect the input type.
   - If the user provides a YouTube link, use `.claude/skills/youtube-auto-subs/SKILL.md` to download the transcript.
   - If the user attaches a local video file, use `.claude/skills/local-video-transcript/SKILL.md` to generate the transcript.
2. If the source was a YouTube link, fetch the top comment threads for the summary's Discussion section (create `.venv` once with `uv venv .venv` if missing; the script is stdlib-only):

   ```
   .venv/bin/python .claude/skills/youtube-channel-analyzer/scripts/channel_index.py fetch-comments "URL" --out-dir comments
   ```

   Reuse the exact printed `.txt` path. If fetching fails or comments are disabled, continue without a comments file. Local files have no comments step.
3. After a transcript is obtained, use `.claude/skills/video-transcript-summary/SKILL.md` to create the summary, passing the comments file path when one exists.

## Notes

- If both a YouTube link and a local video file are provided, ask which source to use.
- If the user only wants a transcript without a summary, confirm whether to proceed with the summary step.
- Comments are fetched only for YouTube sources and only to feed the summary's Discussion section; they are optional and never block the summary.
