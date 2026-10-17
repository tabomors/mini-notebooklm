#!/usr/bin/env python3
"""Build and maintain a resumable per-channel index for the youtube-channel-analyzer skill.

The script is stdlib-only. yt-dlp is always invoked through uvx (fresh extractor),
so there is deliberately no requirements.txt for this skill.
"""
import argparse
import html
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

CHANNELS_DIR = Path("channels")
MANIFEST_NAME = "videos.json"
STATUS_VALUES = ("pending", "done", "failed")

# Flat listing format: one JSON object per line. %(...)j JSON-escapes titles
# (Cyrillic-safe); missing fields come back as the string "NA" and are nulled.
PRINT_FORMAT = (
    '{"id":"%(id)s","title":%(title)j,"upload_date":%(upload_date)j,'
    '"timestamp":%(timestamp)j,"duration":%(duration)j,"view_count":%(view_count)j}'
)
TAB_NAMES = ("videos", "shorts", "streams")
TIMING_RE = re.compile(r"^\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}.*-->")


def fail(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def run_yt_dlp(yt_dlp_cmd: str, url_args: list) -> str:
    cmd = shlex.split(yt_dlp_cmd) + url_args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        fail(f"yt-dlp failed (exit {proc.returncode}):\n{tail}", code=3)
    return proc.stdout


# ---------------------------------------------------------------------------
# Channel input parsing and manifest lookup
# ---------------------------------------------------------------------------

def sanitize_dir_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name).strip()
    return name.rstrip(". ")


def parse_channel_input(raw: str) -> dict:
    """Return {'base_url', 'dir_key', 'identity'} for a channel URL, @handle or UC id."""
    raw = raw.strip()
    if not raw:
        fail("Empty channel input.")
    if "watch?v=" in raw or "/shorts/" in raw or "/live/" in raw:
        fail(
            "Input looks like a single video link. Resolve its channel first with:\n"
            '  uvx yt-dlp --skip-download --print "%(channel_url)s" VIDEO_URL'
        )
    if raw.startswith("@"):
        handle = raw[1:]
        if not handle:
            fail("Empty handle.")
        return {
            "base_url": f"https://www.youtube.com/@{handle}",
            "dir_key": sanitize_dir_name(raw),
            "identity": "@" + handle.lower(),
        }
    if re.fullmatch(r"UC[\w-]{22}", raw):
        return {
            "base_url": f"https://www.youtube.com/channel/{raw}",
            "dir_key": sanitize_dir_name(raw),
            "identity": raw,
        }
    if raw.startswith("http://") or raw.startswith("https://"):
        parts = [p for p in urlparse(raw).path.split("/") if p]
        if not parts:
            fail(f"Cannot derive a channel from URL: {raw}")
        if parts[0] == "@" or parts[0].startswith("@"):
            key = sanitize_dir_name(parts[0])
            return {
                "base_url": f"https://www.youtube.com/{parts[0]}",
                "dir_key": key,
                "identity": "@" + parts[0][1:].lower(),
            }
        if parts[0] in ("user", "c") and len(parts) >= 2:
            key = sanitize_dir_name(f"{parts[0]}-{parts[1]}")
            return {
                "base_url": f"https://www.youtube.com/{parts[0]}/{parts[1]}",
                "dir_key": key,
                "identity": f"{parts[0]}:" + parts[1].lower(),
            }
        if parts[0] == "channel" and len(parts) >= 2:
            return {
                "base_url": f"https://www.youtube.com/channel/{parts[1]}",
                "dir_key": sanitize_dir_name(parts[1]),
                "identity": parts[1],
            }
        fail(
            f"Unsupported channel URL form: {raw}\n"
            "Expected @handle, /user/x, /c/x or /channel/UC... URLs."
        )
    fail(
        f"Unrecognized channel input: {raw}\n"
        "Use a channel URL, an @handle or a UC... channel id."
    )


def input_identity(raw: str) -> str:
    return parse_channel_input(raw)["identity"]


def find_manifest(raw: str) -> Path | None:
    """Locate an existing manifest for this channel, matching aliases too.

    First try the directory derived from the input; then scan existing channel
    dirs for a manifest whose stored input has the same identity (so a channel
    first indexed as a full URL can be re-indexed via its @handle).
    """
    info = parse_channel_input(raw)
    exact = CHANNELS_DIR / info["dir_key"] / MANIFEST_NAME
    if exact.is_file():
        return exact
    if CHANNELS_DIR.is_dir():
        for manifest_path in sorted(CHANNELS_DIR.glob(f"*/{MANIFEST_NAME}")):
            try:
                stored = json.loads(manifest_path.read_text(encoding="utf-8"))
                stored_input = stored.get("channel", {}).get("input", "")
            except (json.JSONDecodeError, OSError):
                continue
            if stored_input and input_identity(stored_input) == info["identity"]:
                return manifest_path
    return None


def load_manifest(raw: str) -> tuple[dict, Path]:
    path = find_manifest(raw)
    if path is None:
        fail(f"No index found for {raw}. Run the index subcommand first.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"Corrupted manifest {path}: {exc}")
    return data, path


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def na_to_none(value):
    if value == "NA":
        return None
    return value


def normalize_upload_date(value):
    """yt-dlp returns YYYYMMDD; the manifest stores YYYY-MM-DD."""
    if not value or value == "NA":
        return None
    value = str(value)
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value


def default_video(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "title": entry.get("title"),
        "url": f"https://www.youtube.com/watch?v={entry['id']}",
        "upload_date": entry.get("upload_date"),
        "date_approximate": entry.get("date_approximate", False),
        "duration": entry.get("duration"),
        "view_count": entry.get("view_count"),
        "tabs": entry.get("tabs", []),
        "status": {"transcript": "pending", "summary": "pending"},
        "files": {"transcript": None, "summary": None},
        "topics": [],
        "error": None,
    }


# ---------------------------------------------------------------------------
# yt-dlp calls
# ---------------------------------------------------------------------------

def extractors_args(approximate_date: bool) -> list:
    if approximate_date:
        return ["--extractor-args", "youtubetab:approximate_date"]
    return []


def fetch_channel_metadata(yt_dlp_cmd: str, url: str, approximate: bool, extra: list) -> dict | None:
    args = extractors_args(approximate) + ["--flat-playlist", "-I", ":1", "-J"] + extra + [url]
    stdout = run_yt_dlp(yt_dlp_cmd, args)
    stdout = stdout.strip()
    if not stdout or stdout == "null":
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def fetch_tab_entries(yt_dlp_cmd: str, url: str, approximate: bool, extra: list) -> list:
    args = (
        extractors_args(approximate)
        + ["--flat-playlist", "--print", PRINT_FORMAT]
        + extra
        + [url]
    )
    stdout = run_yt_dlp(yt_dlp_cmd, args)
    entries = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not raw.get("id"):
            continue
        entries.append(
            {
                "id": raw["id"],
                "title": na_to_none(raw.get("title")),
                "upload_date": normalize_upload_date(na_to_none(raw.get("upload_date"))),
                "timestamp": na_to_none(raw.get("timestamp")),
                "duration": na_to_none(raw.get("duration")),
                "view_count": na_to_none(raw.get("view_count")),
            }
        )
    return entries


# ---------------------------------------------------------------------------
# Shared reporting
# ---------------------------------------------------------------------------

def selected_videos(manifest: dict) -> list:
    videos = manifest.get("videos", [])
    selection = manifest.get("channel", {}).get("selection")
    if not selection:
        return list(videos)
    by_id = {v["id"]: v for v in videos}
    return [by_id[i] for i in selection.get("ids", []) if i in by_id]


def counters(videos: list) -> dict:
    counts = {
        "transcript": {"done": 0, "failed": 0, "pending": 0},
        "summary": {"done": 0, "failed": 0, "pending": 0},
    }
    for v in videos:
        for kind in ("transcript", "summary"):
            state = v["status"].get(kind, "pending")
            if state not in STATUS_VALUES:
                state = "pending"
            counts[kind][state] += 1
    return counts


def progress_line(videos: list) -> str:
    c = counters(videos)
    total = len(videos)
    return (
        f"Progress: transcripts {c['transcript']['done']}/{total} done, "
        f"{c['transcript']['failed']} failed, {c['transcript']['pending']} pending; "
        f"summaries {c['summary']['done']}/{total} done, "
        f"{c['summary']['failed']} failed, {c['summary']['pending']} pending."
    )


# ---------------------------------------------------------------------------
# Subcommand: index
# ---------------------------------------------------------------------------

def resolve_tabs(args) -> list:
    if args.tab:
        tabs = [t.strip() for t in args.tab.split(",") if t.strip()]
        for t in tabs:
            if t not in TAB_NAMES:
                fail(f"Unknown tab '{t}'. Valid tabs: {', '.join(TAB_NAMES)}.")
        return tabs
    path = urlparse(args_channel_base_url(args)).path.rstrip("/")
    for t in TAB_NAMES:
        if path.endswith("/" + t):
            return [t]
    return ["videos"]


def args_channel_base_url(args) -> str:
    return args._base_url


def cmd_index(args) -> None:
    info = parse_channel_input(args.channel)
    manifest_path = find_manifest(args.channel)
    existing = None
    if manifest_path is not None:
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"Corrupted manifest {manifest_path}: {exc}")
        channel_dir = CHANNELS_DIR / existing["channel"]["dir"]
    else:
        channel_dir = CHANNELS_DIR / info["dir_key"]
        manifest_path = channel_dir / MANIFEST_NAME

    tabs = resolve_tabs(args)
    approximate = not args.no_approximate_date
    extra = []
    proxy = args.proxy or os.environ.get("YTDLP_PROXY")
    if proxy:
        extra += ["--proxy", proxy]
        host = proxy.split("@")[-1]
        print(f"Using yt-dlp proxy: {host}")
    if args.limit is not None:
        extra += ["-I", f":{args.limit}"]
    if args.sleep_requests is not None:
        extra += ["--sleep-requests", str(args.sleep_requests)]

    metadata = fetch_channel_metadata(
        args.yt_dlp, f"{info['base_url']}/{tabs[0]}", approximate, extra
    )
    if metadata is None:
        print(
            f"Warning: tab '{tabs[0]}' returned no metadata - it may be empty. "
            f"Consider --tab shorts or --tab streams."
        )

    merged: dict = {}
    order: list = []
    for tab in tabs:
        url = f"{info['base_url']}/{tab}"
        entries = fetch_tab_entries(args.yt_dlp, url, approximate, extra)
        entries.reverse()  # tab order is newest-first; store oldest-first
        print(f"Tab '{tab}': {len(entries)} videos.")
        for entry in entries:
            vid = entry["id"]
            if vid in merged:
                if tab not in merged[vid]["tabs"]:
                    merged[vid]["tabs"].append(tab)
                continue
            entry["tabs"] = [tab]
            entry["date_approximate"] = approximate
            merged[vid] = entry
            order.append(vid)

    videos_out = []
    existing_by_id = {}
    if existing:
        existing_by_id = {v["id"]: v for v in existing.get("videos", [])}
    for vid in order:
        entry = merged[vid]
        prev = existing_by_id.get(vid)
        if prev is not None:
            # Refresh metadata, preserve all processing state.
            prev.update(
                {
                    "title": entry.get("title"),
                    "upload_date": entry.get("upload_date"),
                    "duration": entry.get("duration"),
                    "view_count": entry.get("view_count"),
                    "tabs": entry["tabs"],
                    "date_approximate": approximate,
                }
            )
            videos_out.append(prev)
        else:
            videos_out.append(default_video(entry))
    # Keep videos that disappeared from the listing (never delete work).
    listed = set(order)
    for vid, prev in existing_by_id.items():
        if vid not in listed:
            videos_out.append(prev)

    channel = existing.get("channel", {}) if existing else {}
    channel.update(
        {
            "input": channel.get("input") or args.channel,
            "dir": str(channel_dir).replace(os.sep, "/"),
            "title": (metadata or {}).get("channel") or (metadata or {}).get("title") or channel.get("title"),
            "channel_id": (metadata or {}).get("channel_id") or channel.get("channel_id"),
            "url": info["base_url"],
            "tabs": tabs,
            "follower_count": (metadata or {}).get("channel_follower_count", channel.get("follower_count")),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "video_count": len(videos_out),
            "date_approximate": approximate,
        }
    )
    if existing and existing["channel"].get("selection"):
        channel.setdefault("selection", existing["channel"]["selection"])
    new_manifest = {"channel": channel, "videos": videos_out}
    atomic_write_json(manifest_path, new_manifest)

    dated = sum(1 for v in videos_out if v.get("upload_date"))
    print(f"Channel: {channel['title'] or '(unknown title)'}")
    print(f"Manifest: {manifest_path}")
    print(f"Videos: {len(videos_out)} ({dated} dated" + (", approximate dates" if approximate else "") + ")")
    if any(v["status"]["transcript"] != "pending" or v["status"]["summary"] != "pending" for v in videos_out):
        print(progress_line(videos_out))


# ---------------------------------------------------------------------------
# Subcommand: select
# ---------------------------------------------------------------------------

def cmd_select(args) -> None:
    manifest, path = load_manifest(args.channel)
    videos = manifest.get("videos", [])
    undated = 0
    if args.all:
        chosen = list(videos)
        spec = "all"
    elif args.newest is not None:
        if args.newest <= 0:
            fail("--newest expects a positive number.")
        chosen = videos[-args.newest :]
        spec = f"newest {args.newest}"
    else:
        chosen = []
        for v in videos:
            date = v.get("upload_date")
            if not date:
                undated += 1
                continue
            if args.since and date < args.since:
                continue
            if args.until and date > args.until:
                continue
            chosen.append(v)
        if not any(v.get("upload_date") for v in videos):
            fail(
                "No videos have upload dates in the index; "
                "use --all or --newest N instead of a date range."
            )
        spec = f"since {args.since}" + (f" until {args.until}" if args.until else "")

    manifest["channel"]["selection"] = {"spec": spec, "ids": [v["id"] for v in chosen]}
    atomic_write_json(path, manifest)

    print(f"Selection '{spec}': {len(chosen)} videos.")
    if undated:
        print(f"Warning: {undated} undated videos were excluded (dates are approximate).")
    if chosen:
        first, last = chosen[0], chosen[-1]
        print(f"First: {first['title']} [{first['id']}] ({first.get('upload_date') or 'date unknown'})")
        print(f"Last:  {last['title']} [{last['id']}] ({last.get('upload_date') or 'date unknown'})")


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def cmd_status(args) -> None:
    manifest, _ = load_manifest(args.channel)
    videos = selected_videos(manifest)
    total = len(videos)
    scope = (manifest["channel"].get("selection") or {}).get("spec", "all videos")
    print(f"Scope '{scope}': {total} videos.")
    print(progress_line(videos))

    work = []
    for pos, v in enumerate(videos, 1):
        states = []
        if v["status"].get("transcript") != "done":
            states.append(f"transcript {v['status'].get('transcript', 'pending')}")
        if v["status"].get("summary") != "done":
            states.append(f"summary {v['status'].get('summary', 'pending')}")
        if states:
            work.append((pos, v, states))
        if len(work) >= args.pending:
            break
    if work:
        print(f"Next {len(work)} pending:")
        for pos, v, states in work:
            date = v.get("upload_date") or "date unknown"
            print(f"  {pos}/{total}  {v['title']} [{v['id']}] ({date}) - {', '.join(states)}")
            print(f"          {v['url']}")
    else:
        print("Nothing pending in the selection.")

    failed = [v for v in videos if "failed" in (v["status"]["transcript"], v["status"]["summary"])]
    if failed:
        print(f"Failed ({len(failed)}):")
        for v in failed:
            error = (v.get("error") or "unknown error").splitlines()[0]
            print(f"  {v['title']} [{v['id']}] - {error}")


# ---------------------------------------------------------------------------
# Subcommand: mark
# ---------------------------------------------------------------------------

def cmd_mark(args) -> None:
    manifest, path = load_manifest(args.channel)
    videos = manifest.get("videos", [])
    target = next((v for v in videos if v["id"] == args.id), None)
    if target is None:
        fail(f"Video id {args.id} not found in the manifest.")
    selection = manifest["channel"].get("selection")
    if selection and args.id not in selection.get("ids", []):
        print(f"Warning: {args.id} is outside the current selection '{selection.get('spec')}'.")

    if args.transcript:
        target["status"]["transcript"] = args.transcript
    if args.summary:
        target["status"]["summary"] = args.summary
    for relpath in (args.file or []):
        parts = Path(relpath).parts
        if parts and parts[0] == "transcripts":
            target["files"]["transcript"] = relpath.replace(os.sep, "/")
        elif parts and parts[0] == "summaries":
            target["files"]["summary"] = relpath.replace(os.sep, "/")
        else:
            fail("--file paths must live under transcripts/ or summaries/ of the channel dir.")
    if args.error is not None:
        target["error"] = args.error or None
    elif "done" in (args.transcript, args.summary):
        target["error"] = None
    if args.topics is not None:
        target["topics"] = [t.strip() for t in args.topics.split(",") if t.strip()]

    atomic_write_json(path, manifest)
    print(f"Marked {args.id}: transcript={target['status']['transcript']}, summary={target['status']['summary']}.")
    print(progress_line(selected_videos(manifest)))


# ---------------------------------------------------------------------------
# Subcommand: clean-vtt
# ---------------------------------------------------------------------------

def parse_timestamp(ts: str) -> str:
    """Normalize a VTT timestamp to HH:MM:SS."""
    ts = ts.strip()
    parts = re.split(r"[:.,]", ts)
    if len(parts) == 4:
        h, m, s = parts[0], parts[1], parts[2]
    elif len(parts) == 3:
        h, m, s = "0", parts[0], parts[1]
    else:
        return "00:00:00"
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"


def clean_lines(vtt_text: str) -> list:
    """Return ['[HH:MM:SS] text', ...] with markup and rolling duplicates removed."""
    out: list = []
    last_text = None
    current_start = "00:00:00"
    in_note = False
    for line in vtt_text.splitlines():
        stripped = line.strip()
        if in_note:
            if not stripped:
                in_note = False
            continue
        if not stripped:
            continue
        if stripped.startswith(("WEBVTT", "NOTE", "Kind:", "Language:")):
            if stripped.startswith("NOTE"):
                in_note = True
            continue
        if "-->" in stripped:
            current_start = parse_timestamp(stripped.split("-->")[0])
            continue
        if TIMING_RE.match(stripped):
            continue
        text = html.unescape(re.sub(r"<[^>]+>", "", stripped))
        text = re.sub(r"\s+", " ", text).strip()
        if not text or text == last_text:
            continue
        last_text = text
        out.append(f"[{current_start}] {text}")
    return out


def default_vtt_out(vtt_path: Path) -> Path:
    stem = re.sub(r"\.[A-Za-z0-9]{2,8}(-[A-Za-z0-9]+)*$", "", vtt_path.stem)
    return vtt_path.with_name(stem + ".txt")


def cmd_clean_vtt(args) -> None:
    vtt_path = Path(args.vtt)
    if not vtt_path.is_file():
        fail(f"File not found: {vtt_path}")
    out_path = Path(args.out) if args.out else default_vtt_out(vtt_path)
    if out_path.resolve() == vtt_path.resolve():
        fail("Output path must differ from the input .vtt file.")
    lines = clean_lines(vtt_path.read_text(encoding="utf-8", errors="replace"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"Cleaned: {vtt_path} -> {out_path} ({len(lines)} lines)")
    if args.delete:
        vtt_path.unlink()
        print(f"Deleted: {vtt_path}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Maintain a resumable per-channel index (channels/<channel>/videos.json) "
            "for the youtube-channel-analyzer skill."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_channel(p: argparse.ArgumentParser) -> None:
        p.add_argument("--channel", required=True, help="Channel URL, @handle or UC... id")

    p_index = sub.add_parser("index", help="Index (or re-index) a channel's videos")
    add_channel(p_index)
    p_index.add_argument(
        "--tab",
        default=None,
        help="Comma-separated tabs to index: videos, shorts, streams (default: videos)",
    )
    p_index.add_argument(
        "--no-approximate-date",
        action="store_true",
        help="Do not request approximate upload dates via extractor args",
    )
    p_index.add_argument("--limit", type=int, default=None, help="Fetch at most N videos")
    p_index.add_argument(
        "--sleep-requests", type=float, default=None, help="Pass --sleep-requests to yt-dlp"
    )
    p_index.add_argument(
        "--yt-dlp", default="uvx yt-dlp", help='yt-dlp command prefix (default: "uvx yt-dlp")'
    )
    p_index.add_argument(
        "--proxy", default=None, help="Proxy for yt-dlp (overrides YTDLP_PROXY env var)"
    )
    p_index.set_defaults(func=cmd_index)

    p_select = sub.add_parser("select", help="Fix the processing scope (all / newest N / date range)")
    add_channel(p_select)
    group = p_select.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Select every indexed video")
    group.add_argument("--newest", type=int, metavar="N", help="Select the N most recent videos")
    group.add_argument("--since", metavar="YYYY-MM-DD", help="Select videos from this date")
    p_select.add_argument("--until", metavar="YYYY-MM-DD", help="Optional end date (with --since)")
    p_select.set_defaults(func=cmd_select)

    p_status = sub.add_parser("status", help="Show progress and the next pending videos")
    add_channel(p_status)
    p_status.add_argument("--pending", type=int, default=3, metavar="N", help="List up to N pending videos")
    p_status.set_defaults(func=cmd_status)

    p_mark = sub.add_parser("mark", help="Update per-video processing status")
    add_channel(p_mark)
    p_mark.add_argument("--id", required=True, help="Video id from the manifest")
    p_mark.add_argument(
        "--transcript", choices=STATUS_VALUES, help="Transcript status for this video"
    )
    p_mark.add_argument("--summary", choices=STATUS_VALUES, help="Summary status for this video")
    p_mark.add_argument(
        "--file",
        action="append",
        default=None,
        metavar="RELPATH",
        help="File path relative to the channel dir (repeatable; bucket inferred "
        "from the leading transcripts/ or summaries/ component)",
    )
    p_mark.add_argument("--error", default=None, help="Error text (for failed); empty string clears it")
    p_mark.add_argument("--topics", default=None, help='Comma-separated topic labels, e.g. "LP pools, hedging"')
    p_mark.set_defaults(func=cmd_mark)

    p_clean = sub.add_parser("clean-vtt", help="Convert a yt-dlp .vtt to clean '[HH:MM:SS] text' lines")
    p_clean.add_argument("vtt", help="Path to the .vtt file")
    p_clean.add_argument("--out", default=None, help="Output path (default: same stem without language suffix, .txt)")
    p_clean.add_argument("--delete", action="store_true", help="Delete the .vtt after writing the output")
    p_clean.set_defaults(func=cmd_clean_vtt)

    args = parser.parse_args()
    if getattr(args, "channel", None):
        args._base_url = parse_channel_input(args.channel)["base_url"]
    if args.command == "select" and args.since and args.until and args.until < args.since:
        fail("--until must not be earlier than --since.")
    return args


def main() -> None:
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
