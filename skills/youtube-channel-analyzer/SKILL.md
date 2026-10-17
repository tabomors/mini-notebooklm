---
name: youtube-channel-analyzer
description: Build a resumable per-channel knowledge base from a YouTube channel URL or @handle — index every video, download auto-generated subtitles, write a detailed per-video summary for each one in the channel's language, then produce a cross-video analysis with thematic chains, clusters, and standalone videos. Use when the user gives a YouTube channel link (e.g. https://www.youtube.com/@name) or handle and wants all videos processed, a channel-wide overview or analysis, or a knowledge base they can later ask questions about the channel's content.
---

# Youtube Channel Analyzer

## Overview

Turn a whole YouTube channel into one self-contained knowledge-base directory:

```
channels/@handle/
  videos.json      index + per-video processing status (the resume point)
  transcripts/     one cleaned "[HH:MM:SS] text" .txt per video
  summaries/       one .md summary per video (template of skills/video-transcript-summary/SKILL.md)
  analysis.md      cross-video analysis: inter-video narrative + thematic chains + standalone videos
  analysis/        batch digests, only for channels too large to analyze in one pass
```

Never write channel outputs into the top-level `transcriptions/` or `summaries/` — those are for single videos.

## Use this skill when

- The user gives a channel URL (`https://www.youtube.com/@name`), an `@handle`, or asks to process/analyze "a channel".
- For a single video, use `skills/video-transcript-summary-pipeline/SKILL.md` instead.

## Environment

- Helper script: `.venv/bin/python skills/youtube-channel-analyzer/scripts/channel_index.py <subcommand> ...` (run from the repo root).
- If `.venv` does not exist yet, create it once: `uv venv .venv`. `channel_index.py` is stdlib-only — no `pip install`, no `requirements.txt`.
- yt-dlp always runs through `uvx` (fresh extractor), matching `skills/youtube-auto-subs/SKILL.md`.
- If a proxy is configured (e.g. `YTDLP_PROXY=http://user:pass@gw.dataimpulse.com:823` in `.env`), `channel_index.py index` picks it up automatically; add `--proxy "$YTDLP_PROXY"` to the yt-dlp download commands too.

## Phase 0 — Resolve the input

- A bare `@handle` or channel URL is used as-is.
- If the user gave a single-video link, resolve its channel first:

```
uvx yt-dlp --skip-download --print "%(channel_url)s" VIDEO_URL
```

## Phase 1 — Index and agree on scope

1. Build the index (cheap, flat playlist, seconds):

```
.venv/bin/python skills/youtube-channel-analyzer/scripts/channel_index.py index --channel "@handle"
```

Re-running `index` later is safe: it merges by id and preserves all processing status. Useful flags: `--tab videos,shorts,streams` (default `videos`), `--limit N`, `--sleep-requests S`, `--yt-dlp "..."` override.

2. Report to the user: channel title, video count, date coverage. Warn that upload dates are approximate.
3. Ask the user to pick the scope, then fix it:

```
... channel_index.py select --channel "@handle" --all
... channel_index.py select --channel "@handle" --newest 10
... channel_index.py select --channel "@handle" --since 2025-01-01 [--until 2025-12-31]
```

The selection is stored in `videos.json` and survives across sessions — do not process anything before `select`. Date-range scoping is fuzzy (approximate dates); `--newest`/`--all` are exact.

## Phase 2 — Resumable per-video loop

Process the selection oldest → newest, in small batches (3–5 videos per turn). At the start of each turn run:

```
... channel_index.py status --channel "@handle" --pending 3
```

and continue where it points. For each video:

1. Download auto-subs — **always the original ASR track, never the default one**:

```
uvx yt-dlp --skip-download --list-subs VIDEO_URL          # find the track marked (Original), e.g. "ru-orig  Russian (Original)"
uvx yt-dlp --skip-download --write-auto-subs --sub-langs ru --no-overwrites --paths "channels/@handle/transcripts" -o "%(title)s [%(id)s].%(ext)s" VIDEO_URL
```

Without `--sub-langs`, yt-dlp takes the default track, which for non-English videos is often an auto-TRANSLATION (e.g. `en` translated from Russian). Translated tracks return flaky HTTP 429 even when the original track downloads fine — and worse, they silently give you machine-translated text instead of the speaker's words. Take the `<lang>` of the `(Original)` track from `--list-subs` and request that language.

2. Clean the `.vtt` (strip markup, dedupe rolling captions, keep timecodes):

```
... channel_index.py clean-vtt "channels/@handle/transcripts/<exact printed stem>.<lang>.vtt" --delete
```

Always reuse the exact filename yt-dlp printed — never re-derive the stem yourself; the `[id]` suffix makes same-titled videos collision-free.

3. Write the summary **via a subagent** (dispatch one subagent per video, several in parallel — downloads stay sequential, summaries don't need to be). The subagent's task: read `skills/video-transcript-summary/SKILL.md` and follow its template exactly (language = transcript language, `AD` / `Needs verification` flags, chronological chunking for long transcripts), read the transcript file, take title/link from `videos.json`, write the result to `channels/@handle/summaries/<exact stem>.md` — plain text only, no `#`, `*`, or code fences. The subagent returns only a short confirmation plus 3–8 short topic labels in the channel language; it must not paste the whole summary into its reply. Running summaries in subagents keeps the main context small and processes videos concurrently.
4. Immediately update the manifest yourself — one `mark` per video, never batched (this is what makes interrupting safe). Keep `mark` calls in the main agent: the manifest is a single JSON file with atomic writes, and concurrent writers would race:

```
... channel_index.py mark --channel "@handle" --id VIDEO_ID --transcript done --summary done --file "transcripts/<stem>.txt" --file "summaries/<stem>.md" --topics "topic one, topic two"
```

Topics are short labels in the channel language; they power the cross-video clustering and later Q&A.

5. On any failure (no auto-subs, members-only, removed video, yt-dlp error), record it and move on:

```
... channel_index.py mark --channel "@handle" --id VIDEO_ID --transcript failed --error "<one-line reason>"
```

Never re-download or re-summarize a video already marked `done`. Never skip a `mark`.

### Phase 2b — Fallbacks when subtitles fail

Subtitle downloads are the most rate-limited part of YouTube. In practice, though, most 429s came from requesting translated tracks (fixed by `--sub-langs` in Phase 2 step 1) — real IP throttling is rare. Handle remaining cases in this order:

1. **Backoff and retry.** HTTP 429 on subtitles is a temporary IP-level throttle. Wait (2–5 min, longer on repeat), re-run with `--sleep-requests 3..5`. In a normal channel loop the summarization minutes between downloads usually prevent throttling — avoid burst-retrying.
2. **Proxy with a sticky session.** With `YTDLP_PROXY` set, add `--proxy "$YTDLP_PROXY"` to yt-dlp commands. Per-request IP rotation (default on rotating gateways) looks like session hijacking to YouTube and triggers bot-checks; pin one exit per download instead — for DataImpulse append a session id to the username (`...__sessid.<n>` before the `@`), so one video = one IP and the next video gets a fresh one. Add `--impersonate chrome` and use the `yt-dlp[default,curl-cffi]` build. Note: proxies do not fix 429s caused by requesting translated subtitle tracks — fix that with `--sub-langs` (step 1 above).
3. **Local Whisper** (video has no subtitle track at all, and the user explicitly wants it): follow `skills/local-video-transcript/SKILL.md` on the downloaded audio. Accurate timecodes, but slow on CPU — use `--model small` only for single videos, not for whole channels.

The transcript file in all cases is the same `[HH:MM:SS] text` format, so the summary step does not change.

## Phase 3 — Cross-video analysis

When every selected video has `summary: done` (check `status`), build `channels/@handle/analysis.md`:

- Read all summaries in chronological order, plus `topics` from `videos.json` for orientation. Open a transcript only to verify a suspected link between videos — summaries are enough in almost all cases.
- If the selection has roughly ≤20 videos, write `analysis.md` in one pass. For larger selections, process chronologically in batches of ~15–20, writing a compact digest per batch to `channels/@handle/analysis/batch-NN.md` (skip batch files that already exist — this makes analysis resumable too), then merge the digests into `analysis.md`.
- Language: the channel's language. Formatting: the same strict plain-text rules as `skills/video-transcript-summary/SKILL.md` (no `#`, `*`, code fences). Reference videos as `Title [id] (date)` instead of timecodes.

Structure of `analysis.md`:

```
Header
Channel: <title> — <url>
Period: <first date> – <last date>
Coverage: <N> summarized, <M> failed, <K> not in scope.

Channel in brief
2–3 sentences: what this channel is about and for whom.

How themes develop
A chronological inter-video narrative: which videos continue, develop or
contradict each other, and how the channel's themes evolve over time.

Important numbers and definitions
• Key figures, metrics, dates, formulas mentioned across videos, each with a
  brief explanation.

Thematic chains and clusters
Chain 1: <title>
• Title [id] (date) — what this video contributes to the chain
• Title [id] (date) — ...
Gaps/open questions: what the channel has not covered yet in this chain.
(Repeat for each independent chain/cluster.)

Standalone videos
• Title [id] (date) — one line on why it connects to nothing (news, ad, one-off).

Final block
Main takeaways:
• 5–12 channel-level takeaways, one line each.
```

## Phase 4 — Answering questions about a channel later

When the user asks about a channel that already has a `channels/@handle/` directory:

1. Read `videos.json` first: titles, dates and `topics` give the map of the channel.
2. Read `analysis.md` for the channel-level picture.
3. Open specific files in `summaries/` for detail; `grep` in `transcripts/` for exact wording.
4. Cite answers as `Title [id]` plus a timecode when it comes from a transcript.

## Edge cases and rules

- Empty `/videos` tab: try `--tab shorts` / `--tab streams` before declaring the channel empty. Live streams live under `/streams`, not `/videos`.
- No auto-subs for a video: only a manual fallback helps (download the video, transcribe via `skills/local-video-transcript/SKILL.md`) — and only if the user explicitly asks; it is slow. Otherwise mark `failed` with reason "no subtitles".
- Wrong-language subtitle track: re-run the download with `--sub-langs <lang>`.
- Large channels (>200 videos): warn the user that processing takes hours of summarization and YouTube may throttle; offer `--sleep-requests` on `index` and a `--newest N` start.
- Never produce the summary or the analysis in Markdown syntax, even though files end in `.md`.
