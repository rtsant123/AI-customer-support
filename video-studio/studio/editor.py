"""Step 5: cut every scene to the voiceover, add text overlays, export parts + a rough cut."""
import os
import subprocess

from .director import Scene, VideoPlan
from .transcribe import Segment

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SIZES = {"long": (1920, 1080), "short": (1080, 1920)}


def _wrap_chars(fmt: str) -> int:
    return 18 if fmt == "short" else 32


def _overlay_filter(scene: Scene, txt_path: str, width: int, height: int, fmt: str) -> str:
    # Bold glyphs are ~0.65em wide: keep the longest wrapped line inside ~88% of the frame
    fontsize = min(height // 16, int(width * 1.35 / _wrap_chars(fmt)))
    y = {"top": "h*0.10", "center": "(h-th)/2", "bottom": "h*0.80-th"}[scene.overlay_position]
    font = f"fontfile='{FONT}':" if os.path.exists(FONT) else ""
    return (f",drawtext={font}textfile='{txt_path}':fontcolor=white:fontsize={fontsize}"
            f":x=(w-tw)/2:y={y}:box=1:boxcolor=black@0.55:boxborderw={fontsize // 3}"
            f":line_spacing={fontsize // 5}")


def render_scene(scene: Scene, clip: str, audio: str, out_path: str, fmt: str) -> str:
    width, height = SIZES[fmt]
    duration = scene.end - scene.start
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
          f"crop={width}:{height},fps=30,setsar=1")

    txt = out_path + ".txt"
    if scene.overlay_text.strip():
        with open(txt, "w") as f:
            f.write(_wrap(scene.overlay_text.strip(), _wrap_chars(fmt)))
        vf += _overlay_filter(scene, txt, width, height, fmt)

    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-stream_loop", "-1", "-i", clip,                         # loop short clips
         "-ss", f"{scene.start:.3f}", "-t", f"{duration:.3f}", "-i", audio,
         "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-t", f"{duration:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", out_path],
        check=True,
    )
    if os.path.exists(txt):
        os.remove(txt)
    return out_path


def _wrap(text: str, width: int) -> str:
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    return "\n".join(lines)


def rough_cut(part_paths: list[str], audio: str, out_path: str) -> str:
    """Join all parts' video and lay the original voiceover on top (no audio seams)."""
    list_file = out_path + ".list"
    with open(list_file, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in part_paths)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", list_file,
         "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-shortest", out_path],
        check=True,
    )
    os.remove(list_file)
    return out_path


def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: list[Segment], path: str) -> None:
    with open(path, "w") as f:
        for i, s in enumerate(segments, 1):
            f.write(f"{i}\n{_ts(s.start)} --> {_ts(s.end)}\n{s.text}\n\n")


def write_edit_plan(plan: VideoPlan, sources: dict[int, str], fmt: str, path: str) -> None:
    """Human-readable brief for the real editor who reviews the parts."""
    lines = [f"# Edit plan ({'YouTube Short 9:16' if fmt == 'short' else 'Long-form 16:9'})", ""]
    if plan.title_ideas:
        lines += ["## Title ideas", *[f"- {t}" for t in plan.title_ideas], ""]
    if plan.thumbnail_prompt:
        lines += ["## Thumbnail prompt", plan.thumbnail_prompt, ""]
    if plan.music_mood or plan.hook_notes:
        lines += ["## Overall", f"- Music: {plan.music_mood}", f"- Hook: {plan.hook_notes}", ""]
    lines += ["## Scenes", ""]
    for s in plan.scenes:
        lines += [
            f"### Part {s.number:03d}  ({_ts(s.start)[:-4]} - {_ts(s.end)[:-4]}, {s.end - s.start:.1f}s)",
            f"- **File:** `parts/part_{s.number:03d}.mp4`  (visual: {sources.get(s.number, '?')})",
            f"- **Voiceover:** {s.narration}",
            f"- **Overlay:** {s.overlay_text or '(none)'} [{s.overlay_position}]",
            f"- **AI video prompt:** {s.ai_video_prompt or '-'}",
            f"- **Stock search:** {s.stock_search or '-'}",
            f"- **Edit:** {s.camera_and_edit_notes or '-'}  | transition: {s.transition or '-'}",
            f"- **SFX/Music:** {s.sfx_and_music or '-'}",
        ]
        if s.fact_check_note:
            lines.append(f"- **⚠ Verify:** {s.fact_check_note}")
        lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines))
