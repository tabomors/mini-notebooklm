#!/usr/bin/env python3
import argparse
from pathlib import Path

from faster_whisper import WhisperModel


def format_ts(seconds: float) -> str:
    ms = int(seconds * 1000)
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe a local media file with faster-whisper and save TXT/SRT outputs."
    )
    parser.add_argument("input", help="Path to a local audio/video file")
    parser.add_argument(
        "--model",
        default="small",
        help="Whisper model size (tiny/base/small/medium/large-v3)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language code like 'ru' or 'en' (auto if omitted)",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        choices=["cpu", "cuda"],
        help="Device to use",
    )
    parser.add_argument(
        "--compute-type",
        default="int8",
        help="Compute type (e.g., int8, int8_float16, float16)",
    )
    parser.add_argument(
        "--vad-filter",
        action="store_true",
        help="Enable VAD filter (recommended for noisy audio)",
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_base = args.output_base or input_path.stem
    txt_path = output_dir / f"{output_base}.txt"
    srt_path = output_dir / f"{output_base}.srt"

    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
    )

    segments, info = model.transcribe(
        str(input_path),
        language=args.language,
        vad_filter=args.vad_filter,
    )

    segments = list(segments)

    with txt_path.open("w", encoding="utf-8") as f:
        for seg in segments:
            text = seg.text.strip()
            if text:
                f.write(text + "\n")

    with srt_path.open("w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{format_ts(seg.start)} --> {format_ts(seg.end)}\n")
            f.write(seg.text.strip() + "\n\n")

    print(f"Saved: {txt_path}")
    print(f"Saved: {srt_path}")


if __name__ == "__main__":
    main()
