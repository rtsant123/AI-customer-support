"""Step 1: turn the voiceover into timed text (so every scene lines up with the audio)."""
import json
import re
import subprocess
from dataclasses import dataclass, asdict


@dataclass
class Segment:
    start: float
    end: float
    text: str


def audio_duration(audio_path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def transcribe(audio_path: str, model_size: str = "small") -> list[Segment]:
    """Local Whisper transcription with timestamps. Free, no API key."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="auto", compute_type="auto")
    segments, _info = model.transcribe(audio_path, vad_filter=True)
    return [Segment(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments]


def estimate_from_script(script: str, duration: float) -> list[Segment]:
    """No-Whisper fallback: spread script sentences over the audio by word count."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script.strip()) if s.strip()]
    total_words = sum(len(s.split()) for s in sentences) or 1
    t, out = 0.0, []
    for s in sentences:
        length = duration * len(s.split()) / total_words
        out.append(Segment(round(t, 2), round(t + length, 2), s))
        t += length
    if out:
        out[-1].end = round(duration, 2)
    return out


def save(segments: list[Segment], path: str) -> None:
    with open(path, "w") as f:
        json.dump([asdict(s) for s in segments], f, indent=2)
