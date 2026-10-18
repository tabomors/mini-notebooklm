#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def format_ts(seconds: float) -> str:
    ms = int(seconds * 1000)
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Transcribe a local media file with Whisper and save TXT/SRT outputs."
        )
    )
    parser.add_argument("input", help="Path to a local audio/video file")
    parser.add_argument(
        "--model",
        default=None,
        help="Whisper model name (default: small for local, whisper-1 for OpenAI API)",
    )
    parser.add_argument(
        "--backend",
        choices=["local", "openai"],
        default="local",
        help="Transcription backend (default: local)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language code like 'ru' or 'en' (auto if omitted)",
    )
    parser.add_argument(
        "--vad-filter",
        action="store_true",
        help="Enable VAD filter (no effect with OpenAI API; kept for compatibility)",
    )
    parser.add_argument(
        "--output-dir",
        default="transcriptions",
        help="Directory for output files",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Base name for output files (defaults to input stem)",
    )
    parser.add_argument(
        "--no-extract-wav",
        action="store_true",
        help="Disable WAV extraction before transcription",
    )
    return parser.parse_args()


def extract_wav(input_path: Path, wav_path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print("ffmpeg not found; cannot extract audio.")
        sys.exit(2)

    if wav_path.exists():
        return wav_path

    wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    subprocess.run(cmd, check=True)
    return wav_path


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in {
        ".wav",
        ".mp3",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".opus",
        ".wma",
        ".aiff",
        ".aif",
        ".aifc",
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_base = args.output_base or input_path.stem
    txt_path = output_dir / f"{output_base}.txt"
    srt_path = output_dir / f"{output_base}.srt"
    wav_path = output_dir / f"{output_base}.wav"

    if not is_audio_file(input_path):
        if args.no_extract_wav:
            print("Input is not an audio file; WAV extraction is required.")
            sys.exit(2)
        audio_path = extract_wav(input_path, wav_path)
    else:
        audio_path = input_path

    if not args.no_extract_wav and audio_path.suffix.lower() != ".wav":
        audio_path = extract_wav(audio_path, wav_path)

    if args.backend == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            print("OPENAI_API_KEY is not set in the environment.")
            sys.exit(2)
        model_name = args.model or "whisper-1"
        max_bytes = 25 * 1024 * 1024
        if audio_path.stat().st_size > max_bytes:
            size_mb = audio_path.stat().st_size / (1024 * 1024)
            print(
                f"Audio file is {size_mb:.1f} MB, which exceeds the 25 MB OpenAI API limit."
            )
            print("Consider compressing to mp3 or splitting the file.")
            sys.exit(2)

        from openai import OpenAI

        client = OpenAI()
        with audio_path.open("rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=model_name,
                file=audio_file,
                response_format="verbose_json",
                language=args.language,
            )

        segments = getattr(transcription, "segments", None) or []
    else:
        model_name = args.model or "small"
        try:
            import whisper
        except ModuleNotFoundError:
            print("Missing dependency: openai-whisper. Install it in your venv.")
            sys.exit(2)

        model = whisper.load_model(model_name)
        transcription = model.transcribe(
            str(audio_path),
            language=args.language,
            verbose=False,
        )
        segments = transcription.get("segments", []) if isinstance(transcription, dict) else []

    with txt_path.open("w", encoding="utf-8") as f:
        if isinstance(transcription, dict):
            text = transcription.get("text", "").strip()
        else:
            text = getattr(transcription, "text", "").strip()
        if text:
            f.write(text + "\n")

    def seg_value(seg, key: str):
        if isinstance(seg, dict):
            return seg.get(key)
        return getattr(seg, key, None)

    with srt_path.open("w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            start = seg_value(seg, "start")
            end = seg_value(seg, "end")
            text = seg_value(seg, "text") or ""
            if start is None or end is None:
                continue
            f.write(f"{i}\n")
            f.write(f"{format_ts(start)} --> {format_ts(end)}\n")
            f.write(text.strip() + "\n\n")

    print(f"Saved: {txt_path}")
    print(f"Saved: {srt_path}")


if __name__ == "__main__":
    main()
