---
name: youtube-auto-subs
description: Download auto-generated YouTube subtitles with yt-dlp when a user provides a YouTube URL and wants subtitles without specifying a language.
---

# Youtube Auto Subs

## Overview

Use yt-dlp to fetch auto-generated subtitles for a YouTube video without needing to know the subtitle language in advance.

## Workflow

1. Confirm the user supplied a YouTube URL (single video link).
2. Run yt-dlp with auto-subs enabled and no language specified, saving outputs to `transcriptions/`:

```
yt-dlp --skip-download --write-auto-subs --paths transcriptions -o "%(title)s [%(id)s].%(ext)s" URL
```

If the user explicitly asks to download the video file too, use:

```
yt-dlp --write-auto-subs --paths transcriptions -o "%(title)s [%(id)s].%(ext)s" URL
```

3. If the user provided multiple URLs, run the command once per URL.
4. If the user asks for a specific language, use their language instead and adjust the command accordingly.
