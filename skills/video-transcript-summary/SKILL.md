---
name: video-transcript-summary
description: Create detailed, topic-structured summaries of videos from transcripts with timecodes, ad labeling, verification flags, and strict plain-text formatting. Use when a user asks to summarize a video, especially if they provide a transcript (optionally title/link/duration), and wants a comprehensive summary organized by topics and time intervals.
---

# Video Transcript Summary

## Overview

Produce a detailed, chronological summary of a video based on its transcript, formatted as plain text with topic blocks, timecodes, key points, and a final topic list.

## Use this skill when

- The user asks for a summary of a video or a transcript.
- The transcript is available or already prepared.

## Workflow

### 1) Intake and language

- Require a full transcript; accept optional title, link, and duration.
- Detect the transcript language and write the summary in the same language unless the user explicitly requests another language.
- Translate common terms into the output language while keeping original brand, product, project, and personal names unchanged.

### 2) Segment topics and timecodes

- Split the transcript into logical topics in chronological order.
- Assign timecodes in `[HH:MM:SS]` or `[MM:SS]`; use ranges for contiguous spans.
- If a topic appears in non-adjacent segments, list all intervals separated by commas.
- Mark advertisements as `AD: <brief description of what is being promoted>`.

### 3) Write the output (plain text only)

Follow this exact structure, keeping content concise and sequential:

Header
Title: <if available>
Link: <if available>
Short context, 1–2 sentences: what the video is about and for whom.

Main topics
For each topic use the template:
Topic N: <short title> [start-time – end-time] (and, if applicable, additional intervals separated by commas)
Context: 1–2 sentences — why this topic is raised and how it connects to the previous one.
Discussion flow: a detailed, sequential retelling in chronological order. Include:
• facts and numbers in parentheses;
• examples and case studies;
• mentioned names, companies, products;
• caveats, limitations, conditions;
• intermediate conclusions as the argument develops.
Key points:
• item 1
• item 2
• item 3
Conclusion for the topic: 1–3 sentences — the core meaning in concentrated form.
Tags: if needed, add labels such as AD or Needs verification.

Important numbers and definitions
• list key figures, metrics, dates, formulas, and briefly explain their meaning.

Final block
Main topics in brief:
• <Topic 1> [timecodes] — one short sentence with the essence
• <Topic 2> [timecodes] — one short sentence with the essence
• <Topic 3> [timecodes] — one short sentence with the essence
(total 5–12 items)

After producing the summary, save the same content into a separate `.md` file in `summaries/`.

### 4) Special handling and flags

- Mark unclear segments as `[unintelligible]`; if the likely meaning is obvious, add a brief guess after it.
- Mark doubtful or unverified claims as `Needs verification: <what exactly>`.
- Preserve chronology; avoid long quotes; keep the argument flow and caveats intact.

### 5) Large transcripts and context limits

- If the transcript does not fit in context, split it into chronological chunks and summarize each chunk separately.
- Merge chunk summaries into the final topic-structured output, keeping timecodes and chronology intact.
- Do not assume unseen parts of the transcript; if coverage is incomplete, state it briefly in the context line.

### 6) Quality control checklist

- Verify that all major topics and time segments are covered.
- Ensure every topic block includes timecodes, context, discussion flow, key points, and a conclusion.
- Confirm the summary is plain text only with no Markdown symbols such as `#`, `*`, or fenced blocks.
